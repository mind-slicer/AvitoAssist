import os
import sys
import subprocess
import socket
import psutil
import atexit
import time
from PyQt6.QtCore import QObject, pyqtSignal
from app.core.log_manager import logger
from app.config import AI_BACKEND_PREFERENCE

class ServerManager(QObject):
    server_started = pyqtSignal()
    server_stopped = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, model_path: str, port: int = 8080):
        super().__init__()
        self._is_starting = False
        self.model_path = model_path
        self.requested_port = port
        self.actual_port = port
        self.process: subprocess.Popen = None

        atexit.register(self.stop_server)

    def _find_free_port(self, start_port: int) -> int:
        port = start_port
        while port < 65535:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
                port += 1
        return start_port

    def _kill_existing_on_port(self, port: int):
        """Убивает процессы, занимающие порт"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for con in proc.connections():
                    if con.laddr.port == port:
                        try:
                            if sys.platform == "win32":
                                subprocess.run(
                                    f"taskkill /F /PID {proc.info['pid']} /T", 
                                    shell=True, 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL
                                )
                            else:
                                proc.kill()
                        except:
                            pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _has_nvidia_gpu(self) -> bool:
        try:
            subprocess.check_output(
                "nvidia-smi",
                stderr=subprocess.STDOUT,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            return True
        except Exception:
            return False

    def _detect_server_executable(self, explicit_backend: str = "auto") -> tuple[str, str]:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"

        paths = {
            "cuda": os.path.join(base_dir, "backends", "cuda", "llama_cpp", exe_name),
            "vulkan": os.path.join(base_dir, "backends", "vulkan", "llama_cpp", exe_name),
            "cpu": os.path.join(base_dir, "backends", "cpu", "llama_cpp", exe_name)
        }

        if explicit_backend and explicit_backend != "auto":
            if explicit_backend in paths and os.path.exists(paths[explicit_backend]):
                return explicit_backend, paths[explicit_backend]
            else:
                logger.warning(f"Запрошенный бэкенд '{explicit_backend}' не найден, переключение на auto.")

        config_pref = (AI_BACKEND_PREFERENCE or "auto").lower()
        if config_pref != "auto" and config_pref in paths and os.path.exists(paths[config_pref]):
             return config_pref, paths[config_pref]

        if self._has_nvidia_gpu() and os.path.exists(paths["cuda"]):
            return "cuda", paths["cuda"]

        if os.path.exists(paths["vulkan"]):
            return "vulkan", paths["vulkan"]

        if os.path.exists(paths["cpu"]):
            return "cpu", paths["cpu"]
            
        return "unknown", ""

    # TODO КОНТЕКСТ ЗДЕСЬ!
    def start_server(self, ctx_size: int = 2048, gpu_layers: int = -1, batch_size: int = 512, gpu_device: int = 0, backend_preference: str = "auto"):
        if self.is_running() or self._is_starting:
            return

        self._is_starting = True

        if not os.path.exists(self.model_path):
            self.error_occurred.emit(f"Файл модели не найден: {self.model_path}")
            return

        self.actual_port = self._find_free_port(self.requested_port)
        self._kill_existing_on_port(self.actual_port)

        backend_name, server_exe = self._detect_server_executable(backend_preference)
        
        if not server_exe:
            self.error_occurred.emit("Не найден исполняемый файл llama-server! Проверьте папку backends.")
            return

        logger.info(f"Запуск AI бэкенда: {backend_name.upper()}")
        logger.dev(f"Exe: {server_exe}")

        final_gpu_layers = gpu_layers
        if backend_name == "cpu":
            final_gpu_layers = 0

        cmd = [
            server_exe,
            "-m", self.model_path,
            "--port", str(self.actual_port),
            "--host", "127.0.0.1",
            "--ctx-size", str(ctx_size),
            "--batch-size", str(batch_size),
            "--no-mmap"
        ]
        
        if final_gpu_layers != 0:
            cmd += ["--gpu-layers", str(final_gpu_layers)]

        env = os.environ.copy()
        if backend_name != "cpu":
            env["CUDA_VISIBLE_DEVICES"] = str(gpu_device)
            env["GGML_VULKAN_DEVICE"] = str(gpu_device)

        try:
            self.process = subprocess.Popen(
                cmd,
                env=env, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                text=True
            )
            
            time.sleep(1.0)
            
            if self.process.poll() is not None:
                _, stderr = self.process.communicate()
                error_msg = stderr if stderr else f"Код выхода: {self.process.returncode}"
                logger.error(f"AI сервер упал при старте: {error_msg}")
                self.error_occurred.emit(f"Сбой старта AI: {error_msg[:200]}...")
                self.process = None
                return

            self.server_started.emit()
            logger.info(f"AI сервер успешно работает на порту {self.actual_port}")
            
        except Exception as e:
            self.error_occurred.emit(f"Ошибка Popen: {e}")

    def stop_server(self):
        if not self.process:
            return

        try:
            if logger:
                logger.info("AI: Остановка llama-server...")

            try:
                # 1) Акуратно пытаемся завершить всё дерево процессов
                parent = psutil.Process(self.process.pid)
                children = parent.children(recursive=True)
                for p in children:
                    try:
                        p.terminate()
                    except Exception:
                        pass

                parent.terminate()

                # 2) Ждем до 3 секунд
                gone, alive = psutil.wait_procs([parent] + children, timeout=3)
                if alive:
                    # 3) Жестко убиваем, кто остался
                    for p in alive:
                        try:
                            p.kill()
                        except Exception:
                            pass
            except psutil.NoSuchProcess:
                pass

            # На Windows можно дополнительно продублировать taskkill, если нужно:
            if sys.platform == "win32":
                try:
                    subprocess.run(
                        f"taskkill /F /PID {self.process.pid} /T",
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.dev(f"AI stop_server error: {e}", level="ERROR")
        finally:
            self.process = None
            self.server_stopped.emit(0)

    def set_model_path(self, new_path: str):
        self.stop_server()
        self.model_path = new_path

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
    
    def get_port(self) -> int:
        return self.actual_port
    
    def get_memory_info(self):
        try:
            if self.process:
                return psutil.Process(self.process.pid).memory_info().rss / 1024 / 1024
        except:
            pass
        return 0.0