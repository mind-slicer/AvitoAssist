import os
from datetime import datetime
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG

from .dev_logger import LogHandler, LogLevel


class FileHandler(LogHandler):
    """
    File-based log handler with rotation support
    
    Example:
        handler = FileHandler("app.log", max_size_mb=10)
    """
    
    def __init__(self, filepath: str, max_size_mb: int = 5, encoding: str = "utf-8"):
        self.filepath = filepath
        self.max_size_mb = max_size_mb
        self.encoding = encoding
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w', encoding=self.encoding) as f:
                f.write(f"=== Log started at {datetime.now().isoformat()} ===\n")
    
    def _rotate_if_needed(self):
        if not os.path.exists(self.filepath):
            return
        
        size_mb = os.path.getsize(self.filepath) / (1024 * 1024)
        if size_mb > self.max_size_mb:
            # Rename old log
            backup = f"{self.filepath}.old"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(self.filepath, backup)
            self._ensure_file_exists()
    
    def emit(self, level: LogLevel, message: str, timestamp: datetime):
        self._rotate_if_needed()
        
        ts_str = timestamp.strftime('%H:%M:%S')
        level_name = level.value[0]
        line = f"[{ts_str}] [{level_name:8}] {message}\n"
        
        try:
            with open(self.filepath, 'a', encoding=self.encoding) as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            import sys
            print(f"[FileHandler] Write error: {e}", file=sys.stderr)


class ConsoleHandler(LogHandler):
    """
    Console output handler with colors
    
    Example:
        handler = ConsoleHandler(use_colors=True)
    """
    
    # ANSI color codes
    COLORS = {
        LogLevel.DEBUG: "\033[90m",      # Gray
        LogLevel.INFO: "\033[96m",       # Cyan
        LogLevel.SUCCESS: "\033[92m",    # Green
        LogLevel.WARNING: "\033[93m",    # Yellow
        LogLevel.ERROR: "\033[91m",      # Red
        LogLevel.PROGRESS: "\033[94m",   # Blue
        LogLevel.AI_STATUS: "\033[95m",  # Magenta
    }
    RESET = "\033[0m"
    
    def __init__(self, use_colors: bool = True, prefix: str = ""):
        self.use_colors = use_colors
        self.prefix = prefix
    
    def emit(self, level: LogLevel, message: str, timestamp: datetime):
        ts_str = timestamp.strftime('%H:%M:%S')
        level_name = level.value[0]
        
        if self.use_colors:
            color = self.COLORS.get(level, "")
            line = f"{color}[{ts_str}] [{level_name:8}] {self.prefix}{message}{self.RESET}"
        else:
            line = f"[{ts_str}] [{level_name:8}] {self.prefix}{message}"
        
        print(line)


class UIHandler(LogHandler, QObject):
    """
    Qt UI widget handler (for LogWidget)
    Thread-safe through Qt signals
    
    Example:
        from app.ui.widgets.logger import LogWidget
        widget = LogWidget()
        handler = UIHandler(widget)
    """
    
    log_signal = pyqtSignal(str, str, str)
    
    def __init__(self, widget: Optional[QObject] = None):
        QObject.__init__(self)
        self.widget = widget
        
        if widget:
            self.log_signal.connect(self._update_widget_slot)
    
    def set_widget(self, widget: QObject):
        if self.widget:
            try:
                self.log_signal.disconnect()
            except:
                pass
        
        self.widget = widget
        if widget:
            self.log_signal.connect(self._update_widget_slot)
    
    def _update_widget_slot(self, level_name: str, message: str, color: str):
        if not self.widget:
            return
        
        method_map = {
            "DEBUG": "info",
            "INFO": "info",
            "SUCCESS": "success",
            "WARNING": "warning",
            "ERROR": "error",
            "PROGRESS": "progress",
            "AI_STATUS": "ai_status",
        }
        
        method_name = method_map.get(level_name, "info")
        
        if hasattr(self.widget, method_name):
            method = getattr(self.widget, method_name)
            try:
                method(message)
            except Exception as e:
                print(f"[UIHandler] Widget update failed: {e}")
    
    def emit(self, level: LogLevel, message: str, timestamp: datetime):
        if not self.widget:
            return
        
        level_name, color = level.value
        
        self.log_signal.emit(level_name, message, color)


class MultiHandler(LogHandler):
    """
    Broadcast to multiple handlers
    
    Example:
        handler = MultiHandler([
            FileHandler("app.log"),
            ConsoleHandler()
        ])
    """
    
    def __init__(self, handlers: list):
        self.handlers = handlers
    
    def emit(self, level: LogLevel, message: str, timestamp: datetime):
        for handler in self.handlers:
            try:
                handler.emit(level, message, timestamp)
            except Exception as e:
                print(f"[MultiHandler] Sub-handler failed: {e}")