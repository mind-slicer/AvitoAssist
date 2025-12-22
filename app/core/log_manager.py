import logging
import sys
import os
from PyQt6.QtCore import QObject, pyqtSignal

from app.config import BASE_APP_DIR

class SingletonMeta(type(QObject)):
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class LogManager(QObject, metaclass=SingletonMeta):
    ui_log_signal = pyqtSignal(str, str, str, bool)
    ui_delete_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        if not hasattr(self, '_initialized'):
            self._init_logger()
            self._initialized = True

    def _init_logger(self):
        self.dev_logger = logging.getLogger("AvitoAssist")
        self.dev_logger.setLevel(logging.DEBUG)
        self.dev_logger.propagate = False
        
        if self.dev_logger.hasHandlers():
            self.dev_logger.handlers.clear()
        
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        
        log_path = os.path.join(BASE_APP_DIR, "debug.log")
        try:
            fh = logging.FileHandler(log_path, encoding='utf-8')
            fh.setFormatter(formatter)
            fh.setLevel(logging.DEBUG)
            self.dev_logger.addHandler(fh)
        except Exception as e:
            print(f"Ошибка создания лог-файла: {e}")
        
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        ch.setLevel(logging.INFO)
        self.dev_logger.addHandler(ch)

    def delete_log(self, token: str):
        if token:
            self.ui_delete_signal.emit(token)

    # --- Публичное API ---

    def info(self, text: str, token: str = None):
        self.dev_logger.info(f"[UI:INFO] {text}")
        replace = token is not None
        self.ui_log_signal.emit(token, text, "info", replace)

    def success(self, text: str, token: str = None):
        self.dev_logger.info(f"[UI:OK] {text}")
        replace = token is not None
        self.ui_log_signal.emit(token, text, "success", replace)

    def warning(self, text: str, token: str = None):
        self.dev_logger.warning(f"[UI:WARN] {text}")
        replace = token is not None
        self.ui_log_signal.emit(token, text, "warning", replace)

    def error(self, text: str, token: str = None, exc_info=False):
        self.dev_logger.error(f"[UI:ERR] {text}", exc_info=exc_info)
        replace = token is not None
        self.ui_log_signal.emit(token, text, "error", replace)

    def progress(self, text: str, token: str):
        self.ui_log_signal.emit(token, text, "process", True)

    def dev(self, text: str, level="DEBUG"):
        if level == "DEBUG": self.dev_logger.debug(text)
        elif level == "INFO": self.dev_logger.info(text)
        elif level == "ERROR": self.dev_logger.error(text)

logger = LogManager()