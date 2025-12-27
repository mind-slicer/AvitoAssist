from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget)
from PyQt6.QtCore import pyqtSignal

from app.ui.styles import Palette, Spacing
from app.core.memory import MemoryManager
from app.ui.widgets.ai_control_panel import AIControlPanel
from app.ui.pages.database_tab import DatabaseTab
from app.core.log_manager import logger

class AnalyticsWidget(QWidget):
    send_message_signal = pyqtSignal(list) 
    rebuild_finished_signal = pyqtSignal(int)

    def __init__(self, memory_manager: MemoryManager, controller=None, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self.controller = controller
        self.rebuild_finished_signal.connect(self.on_rebuild_finished)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background-color: {Palette.BG_DARK}; }}
            QTabBar::tab {{
                background-color: {Palette.BG_DARK_2};
                color: {Palette.TEXT_MUTED};
                padding: {Spacing.SM}px {Spacing.MD}px;
                border: 1px solid {Palette.BORDER_SOFT};
                border-bottom: none;
                border-top-left-radius: {Spacing.RADIUS_NORMAL}px;
                border-top-right-radius: {Spacing.RADIUS_NORMAL}px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {Palette.BG_DARK};
                color: {Palette.SECONDARY};
                border-bottom: 2px solid {Palette.SECONDARY};
            }}
            QTabBar::tab:hover {{ color: {Palette.TEXT}; }}
            QTabBar::tab:disabled {{ color: {Palette.with_alpha(Palette.TEXT_MUTED, 0.3)}; }}
        """)

        self.ai_control = AIControlPanel()
        self.ai_control.send_message_signal.connect(self.send_message_signal.emit)
        self.tabs.addTab(self.ai_control, "Чат")

        self.ai_control.set_memory_manager(self.memory)
        
        if self.controller:
            self.controller.cultivation_finished.connect(self.ai_control.cultivation_finished.emit)

        self.database_tab = DatabaseTab(self.memory)
        self.tabs.addTab(self.database_tab, "База Данных")

        wip2_widget = QWidget()
        idx_wip2 = self.tabs.addTab(wip2_widget, "WIP")
        self.tabs.setTabEnabled(idx_wip2, False)
        self.tabs.setTabToolTip(idx_wip2, "В разработке")

        main_layout.addWidget(self.tabs)

    def on_ai_reply(self, text: str):
        if hasattr(self, 'ai_control'):
            self.ai_control.on_ai_reply(text)

    def _rebuild_bg(self):
        try:
            if hasattr(self.memory, 'rebuild_statistics_cache'):
                count = self.memory.rebuild_statistics_cache()
            else:
                count = 0
            self.rebuild_finished_signal.emit(count)
        except Exception as e:
            self.rebuild_finished_signal.emit(0)

    def on_rebuild_finished(self, count: int):
        self.refresh_data()