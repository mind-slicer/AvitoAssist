import logging
from datetime import datetime
from typing import Optional, List
from enum import Enum


class LogLevel(Enum):
    """Log levels with color codes for UI"""
    DEBUG = ("DEBUG", "#888888")
    INFO = ("INFO", "#00eaff")
    SUCCESS = ("SUCCESS", "#4CAF50")
    WARNING = ("WARNING", "#FFA726")
    ERROR = ("ERROR", "#f44336")
    PROGRESS = ("PROGRESS", "#2196F3")
    AI_STATUS = ("AI_STATUS", "#E0B0FF")


class LogHandler:
    def emit(self, level: LogLevel, message: str, timestamp: datetime):
        raise NotImplementedError


# Usage:
#     logger = DevLogger(name="parser", debug=True)
#     logger.add_handler(FileHandler("parser.log"))
#     logger.add_handler(ConsoleHandler())
#     logger.add_handler(UIHandler(qt_widget))
#     
#     logger.info("Starting search...")
#     logger.success("Found 100 items")
#     logger.error("Connection failed")
# ----------------------------------------------------
class DevLogger:    
    def __init__(self, name: str = "app", debug: bool = False):
        self.name = name
        self.debug_enabled = debug
        self.handlers: List[LogHandler] = []
        
        self._stdlib_logger = logging.getLogger(name)
        self._stdlib_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    def add_handler(self, handler: LogHandler):
        if handler not in self.handlers:
            self.handlers.append(handler)
    
    def remove_handler(self, handler: LogHandler):
        if handler in self.handlers:
            self.handlers.remove(handler)
    
    def set_debug(self, enabled: bool):
        self.debug_enabled = enabled
        self._stdlib_logger.setLevel(logging.DEBUG if enabled else logging.INFO)
    
    def _log(self, level: LogLevel, message: str):
        if level == LogLevel.DEBUG and not self.debug_enabled:
            return
        
        timestamp = datetime.now()
        
        for handler in self.handlers:
            try:
                handler.emit(level, message, timestamp)
            except Exception as e:
                import sys
                print(f"[LOGGER ERROR] Handler {handler} failed: {e}", file=sys.stderr)
        
        stdlib_level = self._map_level(level)
        self._stdlib_logger.log(stdlib_level, message)
    
    @staticmethod
    def _map_level(level: LogLevel) -> int:
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.SUCCESS: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.PROGRESS: logging.INFO,
            LogLevel.AI_STATUS: logging.INFO,
        }
        return mapping.get(level, logging.INFO)
    
    # ============ Public API ============
    
    def debug(self, message: str):
        self._log(LogLevel.DEBUG, message)
    
    def info(self, message: str):
        self._log(LogLevel.INFO, message)
    
    def success(self, message: str):
        self._log(LogLevel.SUCCESS, message)
    
    def warning(self, message: str):
        self._log(LogLevel.WARNING, message)
    
    def error(self, message: str):
        self._log(LogLevel.ERROR, message)
    
    def progress(self, message: str):
        self._log(LogLevel.PROGRESS, message)
    
    def ai_status(self, message: str):
        self._log(LogLevel.AI_STATUS, message)
    
    # ============ Legacy compatibility ============
    
    def log(self, message: str):
        self.info(message)
    
    def __call__(self, message: str):
        self.info(message)


_loggers = {}

def get_logger(name: str = "app", debug: bool = False) -> DevLogger:
    """
    Get or create logger instance
    
    Args:
        name: Logger name (e.g., "parser", "ai", "ui")
        debug: Enable debug logging
    
    Returns:
        AppLogger instance
    
    Example:
        logger = get_logger("parser", debug=True)
        logger.info("Starting...")
    """
    if name not in _loggers:
        _loggers[name] = DevLogger(name=name, debug=debug)
    else:
        # Update debug mode if provided
        _loggers[name].set_debug(debug)
    
    return _loggers[name]


def configure_logger(name: str, handlers: List[LogHandler], debug: bool = False) -> DevLogger:
    """
    Configure logger with specific handlers
    
    Args:
        name: Logger name
        handlers: List of handlers to attach
        debug: Enable debug mode
    
    Returns:
        Configured logger
    
    Example:
        logger = configure_logger(
            "parser",
            [FileHandler("parser.log"), ConsoleHandler()],
            debug=True
        )
    """
    logger = get_logger(name, debug)
    
    logger.handlers.clear()
    
    for handler in handlers:
        logger.add_handler(handler)
    
    return logger