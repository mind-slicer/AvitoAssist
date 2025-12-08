import os
import sys
import subprocess
import socket
import psutil
import logging
from PyQt6.QtCore import QObject, pyqtSignal

class ServerManager(QObject):
    """
    Управляет жизненным циклом процесса llama-server.
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

        # 2. Поиск exe файла
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        
        # Пытаемся найти CUDA версию, иначе CPU
        possible_paths = [
            os.path.join(base_dir, "backends", "cuda", "llama_cpp", exe_name),
            os.path.join(base_dir, "backends", "vulkan", "llama_cpp", exe_name),
            os.path.join(base_dir, "backends", "cpu", "llama_cpp", exe_name),
        ]
        
        server_exe = None
        for p in possible_paths:
            if os.path.exists(p):
                server_exe = p
                break
        
        if not server_exe:
            self.error_occurred.emit(f"Не найден исполняемый файл {exe_name}!")
            return

        # 3. Аргументы запуска
        cmd = [
            server_exe,
            "-m", self.model_path,
            "--ctx-size", str(ctx_size),
            "--port", str(self.actual_port),
            "--host", "127.0.0.1",
            "--batch-size", str(batch_size)
        ]
        
        if gpu_layers != 0:
            cmd += ["--gpu-layers", str(gpu_layers)]

        self.logger.info(f"Starting server: {' '.join(cmd)}")

        try:
            # Запускаем процесс
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, # Можно перенаправить в файл
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            # Мы не ждем тут healthcheck, это сделает менеджер верхнего уровня
            self.server_started.emit()
            
        except Exception as e:
            self.error_occurred.emit(f"Ошибка запуска: {e}")

    def stop_server(self):
        if self.process:
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