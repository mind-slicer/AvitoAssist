import os
import sys
import subprocess
import socket
import psutil
import logging
from PyQt6.QtCore import QObject, pyqtSignal

# Импортируем настройку предпочтений
from app.config import AI_BACKEND_PREFERENCE

class ServerManager(QObject):
    """
    Управляет жизненным циклом процесса llama-server.
    Автоматически выбирает лучший доступный бэкенд (CUDA -> Vulkan -> CPU).
    """
    server_started = pyqtSignal()
    server_stopped = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, model_path: str, port: int = 8080):
        super().__init__()
        self.model_path = model_path
        self.requested_port = port
        self.actual_port = port
        self.process: subprocess.Popen = None
        self.logger = logging.getLogger("ServerManager")

    def _find_free_port(self, start_port: int) -> int:
        """Ищет свободный порт"""
        port = start_port
        while port < 65535:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
                port += 1
        return start_port

    def _kill_existing_on_port(self, port: int):
        """Убивает зомби-процессы на нужном порту"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for con in proc.connections():
                    if con.laddr.port == port:
                        self.logger.warning(f"Killing zombie process on port {port}: {proc.info['name']}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _has_nvidia_gpu(self) -> bool:
        """Проверка наличия NVIDIA GPU через nvidia-smi"""
        try:
            subprocess.check_output(
                "nvidia-smi",
                stderr=subprocess.STDOUT,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            return True
        except Exception:
            return False

    def _detect_server_executable(self) -> tuple[str, str]:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"

        # Пути к разным версиям бэкендов
        paths = {
            "cuda": os.path.join(base_dir, "backends", "cuda", "llama_cpp", exe_name),
            "vulkan": os.path.join(base_dir, "backends", "vulkan", "llama_cpp", exe_name),
            "cpu": os.path.join(base_dir, "backends", "cpu", "llama_cpp", exe_name)
        }

        # 1. Проверяем явную настройку пользователя
        pref = (AI_BACKEND_PREFERENCE or "auto").lower()
        if pref in paths and os.path.exists(paths[pref]):
            return pref, paths[pref]

        # 2. Авто-определение (CUDA)
        if self._has_nvidia_gpu() and os.path.exists(paths["cuda"]):
            return "cuda", paths["cuda"]

        # 3. Авто-определение (Vulkan)
        # Если нет NVIDIA или драйверов, пробуем Vulkan (AMD/Intel/Integrated)
        if os.path.exists(paths["vulkan"]):
            return "vulkan", paths["vulkan"]

        # 4. Fallback на CPU
        if os.path.exists(paths["cpu"]):
            return "cpu", paths["cpu"]
            
        return "unknown", ""

    def start_server(self, ctx_size: int = 2048, gpu_layers: int = -1, batch_size: int = 512):
        if self.is_running():
            self.server_started.emit()
            return

        if not os.path.exists(self.model_path):
            self.error_occurred.emit(f"Файл модели не найден: {self.model_path}")
            return

        # 1. Подготовка порта
        self.actual_port = self._find_free_port(self.requested_port)
        self._kill_existing_on_port(self.actual_port)

        # 2. Поиск exe файла с учетом логики бэкендов
        backend_name, server_exe = self._detect_server_executable()
        
        if not server_exe:
            self.error_occurred.emit("Не найден исполняемый файл llama-server (ни CUDA, ни Vulkan, ни CPU)!")
            return

        self.logger.info(f"Selected AI Backend: {backend_name.upper()} ({server_exe})")

        # 3. Аргументы запуска
        cmd = [
            server_exe,
            "-m", self.model_path,
            "--ctx-size", str(ctx_size),
            "--port", str(self.actual_port),
            "--host", "127.0.0.1",
            "--batch-size", str(batch_size)
        ]
        
        # Для Vulkan тоже полезно передавать слои, если GPU поддерживает
        if gpu_layers != 0:
            cmd += ["--gpu-layers", str(gpu_layers)]

        try:
            # Запускаем процесс
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            self.server_started.emit()
            
        except Exception as e:
            self.error_occurred.emit(f"Ошибка запуска сервера: {e}")

    def stop_server(self):
        if self.process:
            self.logger.info("Stopping server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.server_stopped.emit(0)

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
    
    def get_port(self) -> int:
        return self.actual_port
    
    def get_memory_info(self):
        """Возвращает потребление памяти (MB)"""
        try:
            if self.process:
                return psutil.Process(self.process.pid).memory_info().rss / 1024 / 1024
        except:
            pass
        return 0.0