import logging
import sys
import os
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

from app.config import BASE_APP_DIR

class SingletonMeta(type(QObject)):
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class LogManager(QObject, metaclass=SingletonMeta):
    """
    Единый центр управления логами.
    - Отправляет красивые сообщения в UI (через сигналы).
    - Пишет технические подробности в файл debug.log.
    """
    
    # Сигнал для UI: (token, text, style, replace_existing)
    # token - уникальный ID строки (нужен для обновления, например, прогресс-бара)
    # style - 'info', 'success', 'warning', 'error', 'process'
    # replace - True, если нужно заменить строку с таким же token
    ui_log_signal = pyqtSignal(str, str, str, bool) 

    def __init__(self):
        super().__init__()
        if not hasattr(self, '_initialized'):
            self._init_logger()
            self._initialized = True

    def _init_logger(self):
        # Настройка системного логгера (для файла и консоли)
        self.dev_logger = logging.getLogger("AvitoAssist")
        self.dev_logger.setLevel(logging.DEBUG)
        self.dev_logger.propagate = False # Чтобы не дублировалось в рут логгере
        
        # Очищаем старые хендлеры, если были
        if self.dev_logger.hasHandlers():
            self.dev_logger.handlers.clear()
        
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
        
        # 1. Хендлер файла (пишет всё подряд)
        log_path = os.path.join(BASE_APP_DIR, "debug.log")
        try:
            fh = logging.FileHandler(log_path, encoding='utf-8')
            fh.setFormatter(formatter)
            fh.setLevel(logging.DEBUG)
            self.dev_logger.addHandler(fh)
        except Exception as e:
            print(f"Ошибка создания лог-файла: {e}")
        
        # 2. Хендлер консоли (IDE)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        ch.setLevel(logging.INFO)
        self.dev_logger.addHandler(ch)

    # --- Публичное API для использования в коде ---

    def info(self, text: str, token: str = None):
        """Обычное сообщение (синий/белый)"""
        self.dev_logger.info(f"[UI:INFO] {text}")
        self.ui_log_signal.emit(token, text, "info", token is not None)

    def success(self, text: str):
        """Успех (зеленый)"""
        self.dev_logger.info(f"[UI:OK] {text}")
        self.ui_log_signal.emit(None, text, "success", False)

    def warning(self, text: str):
        """Предупреждение (желтый)"""
        self.dev_logger.warning(f"[UI:WARN] {text}")
        self.ui_log_signal.emit(None, text, "warning", False)

    def error(self, text: str, exc_info=False):
        """Ошибка (красный)"""
        self.dev_logger.error(f"[UI:ERR] {text}", exc_info=exc_info)
        self.ui_log_signal.emit(None, text, "error", False)

    def progress(self, text: str, token: str):
        """
        Обновляемая строка с анимацией. 
        Обязательно передавать token (например, 'parser_progress'), 
        чтобы строка обновлялась, а не дублировалась.
        """
        # В файл не пишем каждый шаг прогресса, чтобы не замусорить диск
        # Но можно писать в консоль IDE с возвратом каретки, если хочется
        self.ui_log_signal.emit(token, text, "process", True)

    def dev(self, text: str, level="DEBUG"):
        """Чисто технический лог, в UI не попадает"""
        if level == "DEBUG": self.dev_logger.debug(text)
        elif level == "INFO": self.dev_logger.info(text)
        elif level == "ERROR": self.dev_logger.error(text)

# Глобальный экземпляр для импорта
logger = LogManager()