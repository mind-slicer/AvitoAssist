from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QWidget, QHBoxLayout, 
                           QSizePolicy, QStackedLayout, QLabel, QLineEdit, QComboBox, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QWheelEvent
from app.ui.widgets.browsers import MiniFileBrowser
from app.ui.widgets.results_table import ResultsTable
from app.ui.styles import Components, Spacing, Typography, Palette

class NoScrollComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def wheelEvent(self, event: QWheelEvent):
        event.ignore()

class ResultsAreaWidget(QGroupBox):
    file_loaded = pyqtSignal(str, list)
    file_deleted = pyqtSignal(str)
    table_item_deleted = pyqtSignal(str)
    table_closed = pyqtSignal()
    item_starred = pyqtSignal(str, bool)
    analyze_table_requested = pyqtSignal(list)
    add_to_memory_requested = pyqtSignal(list)
    export_table_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(Components.panel())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        group_v = QVBoxLayout(self)
        group_v.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        group_v.setSpacing(Spacing.SM)
        
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(Spacing.MD)

        # --- LEFT: Browser ---
        left_widget = QWidget()
        left_widget.setMinimumWidth(345)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Spacing.SM)

        self.mini_browser = MiniFileBrowser()
        self.mini_browser.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.mini_browser.table_closed.connect(self._on_table_closed)
        left_layout.addWidget(self.mini_browser, 1)
        
        left_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        # --- RIGHT: Table & Search ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Spacing.SM)

        # Header Area
        self.header_widget = QWidget()
        self.header_widget.setStyleSheet(Components.section_title())
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, Spacing.SM, 0, Spacing.SM)
        header_layout.setSpacing(Spacing.LG)
        
        # Metadata
        meta_widget = QWidget()
        meta_layout = QHBoxLayout(meta_widget)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(Spacing.MD)
        
        self.table_title_label = QLabel("")
        self.table_title_label.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_LARGE, weight=Typography.WEIGHT_BOLD, color=Palette.TEXT))
        
        separator1 = QLabel("|")
        separator1.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_LARGE, color=Palette.TEXT_MUTED))
            
        self.table_date_label = QLabel("")
        self.table_date_label.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_MD, color=Palette.TEXT_MUTED))
            
        separator2 = QLabel("|")
        separator2.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_LARGE, color=Palette.TEXT_MUTED))
            
        self.table_count_label = QLabel("")
        self.table_count_label.setStyleSheet(Typography.style(
            family=Typography.UI, size=Typography.SIZE_MD, color=Palette.SECONDARY, weight=Typography.WEIGHT_SEMIBOLD))

        meta_layout.addWidget(self.table_title_label, 0)
        meta_layout.addWidget(separator1, 0)
        meta_layout.addWidget(self.table_date_label, 0)
        meta_layout.addWidget(separator2, 0)
        meta_layout.addWidget(self.table_count_label, 0)
        meta_layout.addStretch(1)
        
        header_layout.addWidget(meta_widget, 1)

        actions_container = QWidget()
        actions_layout = QHBoxLayout(actions_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Spacing.SM)

        self.analyze_btn = QPushButton("🔍 Проанализировать")
        self.analyze_btn.setStyleSheet(Components.small_button())
        self.analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analyze_btn.setToolTip("Запустить AI-анализ для всех элементов таблицы")
        self.analyze_btn.clicked.connect(self.on_analyze_table)

        self.addmemory_btn = QPushButton("🧠 Добавить в память ИИ")
        self.addmemory_btn.setStyleSheet(Components.small_button())
        self.addmemory_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.addmemory_btn.setToolTip("Добавить все элементы таблицы в RAG-память")
        self.addmemory_btn.clicked.connect(self.on_add_to_memory)

        self.export_btn = QPushButton("📊 Выгрузить в таблицу")
        self.export_btn.setStyleSheet(Components.small_button())
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setToolTip("Экспортировать таблицу в CSV/Excel")
        self.export_btn.clicked.connect(self.on_export_table)

        actions_layout.addWidget(self.analyze_btn)
        actions_layout.addWidget(self.addmemory_btn)
        actions_layout.addWidget(self.export_btn)

        header_layout.addWidget(actions_container, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Search Controls
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(Spacing.SM)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по таблице...")
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setMinimumHeight(36)
        self.search_edit.setMaximumHeight(36)
        self.search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_edit.setStyleSheet(Components.text_input())
        self.search_edit.textChanged.connect(self._apply_search) # Сигнал текста

        self.search_mode = NoScrollComboBox()
        self.search_mode.addItems(["По заголовку", "По цене", "По ID"])
        self.search_mode.setFixedWidth(180)
        self.search_mode.setMinimumHeight(36)
        self.search_mode.setMaximumHeight(36)
        self.search_mode.setStyleSheet(Components.styled_combobox())
        self.search_mode.currentTextChanged.connect(lambda: self._apply_search(self.search_edit.text()))

        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(self.search_mode)
        
        header_layout.addWidget(search_container, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Table Stack
        self.results_table = ResultsTable()
        self.results_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.results_table.setMinimumHeight(0)
        
        self.empty_label = QLabel("Нет данных для отображения")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #a0a0a0; font-size: 14px;")
        
        table_container = QWidget()
        self.right_stack = QStackedLayout(table_container)
        self.right_stack.setContentsMargins(0, 0, 0, 0)
        self.right_stack.addWidget(self.empty_label)
        self.right_stack.addWidget(self.results_table)
        self.right_stack.setCurrentWidget(self.empty_label)

        right_layout.addWidget(self.header_widget, 0)
        right_layout.addWidget(table_container, 1)

        self.header_widget.setVisible(False)

        content_layout.addWidget(left_widget, 0)
        content_layout.addWidget(right_widget, 1)
        
        content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        group_v.addWidget(content_widget, 1)

        # Connections
        self.mini_browser.file_loaded.connect(self.file_loaded)
        self.mini_browser.file_deleted.connect(self.file_deleted)
        self.results_table.item_deleted.connect(self.table_item_deleted)
        self.results_table.item_favorited.connect(self._on_item_favorited)

    def _on_item_favorited(self, item_id: str, is_favorite: bool):
        self.item_starred.emit(item_id, is_favorite)

    def clear_table(self):
        self.results_table.source_model.clear()
        self.update_header("", "", 0)
        self.right_stack.setCurrentWidget(self.empty_label)
        self.header_widget.setVisible(False)

    def _on_table_closed(self):
        self.clear_table()
        self.table_closed.emit()

    def on_analyze_table(self):
        items = self.results_table.source_model.get_all_items()
        if not items:
            return
        self.analyze_table_requested.emit(items)

    def on_add_to_memory(self):
        items = self.results_table.source_model.get_all_items()
        if not items:
            return
        self.add_to_memory_requested.emit(items)

    def on_export_table(self):
        items = self.results_table.source_model.get_all_items()
        if not items:
            return
        self.export_table_requested.emit(items)

    def load_full_history(self, items: list[dict]):
        self.clear_table()
        if not items:
            self.right_stack.setCurrentWidget(self.empty_label)
            self.header_widget.setVisible(False)
            return

        self.right_stack.setCurrentWidget(self.results_table)
        self.header_widget.setVisible(True)
        self.results_table.add_items(items)

    def _apply_search(self, text: str):
        query = text.strip()
        mode = self.search_mode.currentText()
        
        col_idx = 3
        if mode == "По заголовку":
            col_idx = 3
        elif mode == "По цене":
            col_idx = 2
        elif mode == "По ID":
            col_idx = 1
            
        self.results_table.filter_data(query, col_idx)

    def update_header(self, table_name: str, full_date: str, count: int):
        if not table_name:
            self.table_title_label.setText("")
            self.table_date_label.setText("")
            self.table_count_label.setText("")
            self.header_widget.setVisible(False)
        else:
            self.table_title_label.setText(table_name)
            self.table_date_label.setText(full_date)
            self.table_count_label.setText(f"{count} шт.")
            self.header_widget.setVisible(True)