from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QPushButton, QTableWidget, QTableWidgetItem, 
                           QHeaderView, QTabWidget, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import json
import threading

from app.ui.styles import Components, Palette, Typography, Spacing
from app.core.memory import MemoryManager
from app.ui.widgets.rag_status_widget import RAGStatusWidget
from app.ui.widgets.ai_control_panel import AIControlPanel
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

        # Tabs
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

        # 1. Управление ИИ (бывший Tab 2) - теперь первый
        self.ai_control = AIControlPanel()
        self.ai_control.send_message_signal.connect(self.send_message_signal.emit)
        self.tabs.addTab(self.ai_control, "Управление ИИ")

        self.ai_control.cultivate_requested.connect(self.on_cultivation_requested)
        self.ai_control.cultivation_finished.connect(self.on_cultivation_finished)
        self.ai_control.set_memory_manager(self.memory)
        
        if self.controller:
            self.controller.cultivation_finished.connect(self.ai_control.cultivation_finished.emit)

        # 2. Тренды (бывший RAG-Статус) - теперь второй
        self.rag_status_widget = RAGStatusWidget(self.memory)
        self.rag_status_widget.rebuild_requested.connect(self.on_rebuild_requested)
        self.tabs.addTab(self.rag_status_widget, "Тренды")

        # 3. WIP (бывшая База Знаний) - заблокирован
        self.knowledge_widget = self.create_knowledge_widget()
        idx_wip1 = self.tabs.addTab(self.knowledge_widget, "WIP")
        self.tabs.setTabEnabled(idx_wip1, False)
        self.tabs.setTabToolTip(idx_wip1, "В разработке")

        # 4. WIP2 - заблокирован
        wip2_widget = QWidget() # Пустой виджет
        idx_wip2 = self.tabs.addTab(wip2_widget, "WIP2")
        self.tabs.setTabEnabled(idx_wip2, False)
        self.tabs.setTabToolTip(idx_wip2, "В разработке")

        main_layout.addWidget(self.tabs)

    def on_ai_reply(self, text: str):
        """Получаем ответ от AI и передаем в панель"""
        if hasattr(self, 'ai_control'):
            self.ai_control.on_ai_reply(text)

    def on_cultivation_requested(self):
        if not self.controller:
            logger.error("Контроллер не передан в виджет Аналитики...", token="ai-cult")
            return

        logger.info("Запуск агрегации памяти...", token="ai-cult")
        self.controller.start_cultivation()
        self.controller.cultivation_finished.connect(self.on_cultivation_finished)
    
    def on_cultivation_finished(self):
        """Обработчик завершения культивации"""
        if hasattr(self, 'ai_control'):
            self.ai_control._reset_cultivate_button()

    # --- Knowledge Base Methods (Logic kept for future) ---

    def create_knowledge_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)

        lbl_mem = QLabel("Сохраненные записи (Обучающая выборка)")
        lbl_mem.setStyleSheet(Components.section_title())
        layout.addWidget(lbl_mem)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Вердикт", "Заголовок", "Цена", "ID"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(Components.table())
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # Buttons
        btns_layout = QHBoxLayout()
        
        btn_refresh = QPushButton("Обновить")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(Components.small_button())
        btn_refresh.clicked.connect(self.refresh_knowledge_data)
        btns_layout.addWidget(btn_refresh)

        btn_del = QPushButton("Удалить выбранное")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet(Components.small_button())
        btn_del.clicked.connect(self.delete_selected)
        btns_layout.addWidget(btn_del)
        
        btns_layout.addStretch()
        layout.addLayout(btns_layout)

        return widget

    def refresh_data(self):
        """Вызывается извне для обновления всех вкладок"""
        self.rag_status_widget.refresh_data()
        self.refresh_knowledge_data()

    def refresh_knowledge_data(self):
        items = self.memory.get_all_items(limit=200)
        self.table.setRowCount(len(items))
        
        for r, item in enumerate(items):
            verdict = item.get('verdict') or "N/A"
            v_item = QTableWidgetItem(verdict)
            
            if verdict == "GREAT_DEAL": v_item.setForeground(QColor(Palette.INFO))
            elif verdict == "GOOD": v_item.setForeground(QColor(Palette.SUCCESS))
            elif verdict == "BAD": v_item.setForeground(QColor(Palette.WARNING))
            else: v_item.setForeground(QColor(Palette.TEXT_MUTED))
            
            v_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            self.table.setItem(r, 0, v_item)
            self.table.setItem(r, 1, QTableWidgetItem(item.get('title', '')))
            
            price = item.get('price', 0)
            self.table.setItem(r, 2, QTableWidgetItem(f"{price:,}".replace(",", " ") if price else "0"))
            
            # ID column (hidden data)
            id_item = QTableWidgetItem(str(item.get('added_at') or ''))
            id_item.setData(Qt.ItemDataRole.UserRole, item.get('avito_id'))
            self.table.setItem(r, 3, id_item)

    def on_rebuild_requested(self):
        threading.Thread(target=self._rebuild_bg, daemon=True).start()

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

    def delete_selected(self):
        rows = sorted([index.row() for index in self.table.selectedIndexes()], reverse=True)
        if not rows: return
        
        for r in rows:
            aid_item = self.table.item(r, 3)
            if aid_item:
                aid = aid_item.data(Qt.ItemDataRole.UserRole)
                if self.memory.delete_item(aid):
                    self.table.removeRow(r)