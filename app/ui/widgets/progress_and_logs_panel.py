from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel, QProgressBar
from PyQt6.QtCore import Qt

from app.ui.styles import Components, Palette, Spacing
from app.ui.widgets.smart_log_widget import SmartLogWidget
from app.core.log_manager import logger

class ProgressAndLogsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self._connect_logger()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        # --- Прогресс бары ---
        bars_container = QWidget()
        bars_layout = QVBoxLayout(bars_container)
        bars_layout.setContentsMargins(0, 0, 0, 0)
        bars_layout.setSpacing(4)

        # Парсер бар
        self.parser_label = QLabel("Прогресс поиска:")
        self.parser_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px;")
        
        self.parser_bar = QProgressBar()
        # По умолчанию обычный режим, скрыт или на нуле
        self.parser_bar.setRange(0, 100)
        self.parser_bar.setValue(0)
        self.parser_bar.setStyleSheet(Components.progress_bar(Palette.PRIMARY))
        self.parser_bar.setFixedHeight(6)
        self.parser_bar.setTextVisible(False)
        
        # AI бар
        self.ai_label = QLabel("Прогресс нейросети:")
        self.ai_label.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px;")
        
        self.ai_bar = QProgressBar()
        self.ai_bar.setRange(0, 100)
        self.ai_bar.setStyleSheet(Components.progress_bar(Palette.SECONDARY))
        self.ai_bar.setFixedHeight(6)
        self.ai_bar.setTextVisible(False)

        bars_layout.addWidget(self.parser_label)
        bars_layout.addWidget(self.parser_bar)
        bars_layout.addWidget(self.ai_label)
        bars_layout.addWidget(self.ai_bar)
        
        layout.addWidget(bars_container)

        # --- Табы с логами ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {Palette.BORDER_SOFT}; background-color: {Palette.BG_DARK_2}; }}
            QTabBar::tab {{
                background-color: {Palette.BG_DARK};
                color: {Palette.TEXT_MUTED};
                padding: 6px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {Palette.BG_DARK_2};
                color: {Palette.TEXT};
                border-bottom: 2px solid {Palette.PRIMARY};
            }}
        """)
        
        self.main_log_widget = SmartLogWidget()
        self.tabs.addTab(self.main_log_widget, "Журнал событий")
        
        layout.addWidget(self.tabs)

    def _connect_logger(self):
        logger.ui_log_signal.connect(self.main_log_widget.add_log)
    
    def set_parser_mode(self, mode: str):
        self.parser_bar.reset() # Сброс внутренних состояний Qt
        
        if mode == "primary":
            # Бесконечный режим: min=0, max=0 запускает анимацию Marquee
            self.parser_bar.setRange(0, 0)
            self.parser_bar.setTextVisible(False)
        else:
            # Обычный режим: 0-100%
            self.parser_bar.setRange(0, 100)
            self.parser_bar.setValue(0)
            self.parser_bar.setTextVisible(False) # Или True, если хочешь видеть %

    def reset_parser_progress(self):
        self.parser_bar.setRange(0, 100)
        self.parser_bar.setValue(0)

    def set_finished_state(self):
        self.parser_bar.setRange(0, 100)
        self.parser_bar.setValue(100)
    
    @property
    def parser_log(self):
        return _LegacyLogAdapter("PARSER")
        
    @property
    def ai_log(self):
        return _LegacyLogAdapter("AI")

class _LegacyLogAdapter:
    def __init__(self, prefix):
        self.prefix = prefix
    
    def info(self, msg):
        logger.info(msg)
        
    def success(self, msg):
        logger.success(msg)
        
    def warning(self, msg):
        logger.warning(msg)
        
    def error(self, msg):
        logger.error(msg)
        
    def progress(self, msg):
        logger.progress(msg, token=f"{self.prefix}_general_progress")
        
    def ai_status(self, msg):
        logger.progress(msg, token="ai_status")