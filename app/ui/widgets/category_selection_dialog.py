from typing import List, Callable
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox, QPushButton
)
from PyQt6.QtCore import Qt
from app.ui.styles import Components, Palette, Typography, Spacing

class CategorySelectionDialog(QDialog):
    def __init__(self, categories: List[dict], parent=None, selected_categories: List[str] = None, on_clear: Callable = None):
        super().__init__(parent)
        self.setWindowTitle("Выберите категории")
        self.resize(450, 600) # Чуть выше для новых кнопок
        self.setStyleSheet(Components.dialog())
        self.on_clear_callback = on_clear

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        
        lbl = QLabel("Доступные разделы:")
        lbl.setStyleSheet(Components.section_title())
        layout.addWidget(lbl)

        # Инструменты управления списком
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(Spacing.SM)
        
        btn_all = QPushButton("Вкл. все")
        btn_none = QPushButton("Выкл. все")
        btn_clear = QPushButton("🗑 Очистить кэш")
        
        for btn in (btn_all, btn_none, btn_clear):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(Components.small_button())
            
        btn_clear.setStyleSheet(f"""
            QPushButton {{ 
                background-color: {Palette.BG_DARK_3}; 
                border: 1px solid {Palette.ERROR}; 
                color: {Palette.ERROR}; 
                border-radius: 4px; padding: 4px;
            }}
            QPushButton:hover {{ background-color: {Palette.ERROR}; color: {Palette.TEXT}; }}
        """)
        
        btn_all.clicked.connect(self.select_all)
        btn_none.clicked.connect(self.deselect_all)
        btn_clear.clicked.connect(self.clear_cache)
        
        tools_layout.addWidget(btn_all)
        tools_layout.addWidget(btn_none)
        tools_layout.addStretch()
        tools_layout.addWidget(btn_clear)
        
        layout.addLayout(tools_layout)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                color: {Palette.TEXT};
                font-family: {Typography.UI};
            }}
            QListWidget::item {{ padding: {Spacing.XS}px; }}
            QListWidget::item:selected {{ background: {Palette.PRIMARY_DARK}; }}
        """)

        selected_set = set(selected_categories) if selected_categories else set()

        for cat in categories:
            text = cat.get('text', str(cat))
            typ = cat.get('type', '')
            item = QListWidgetItem(f"[{typ}] {text}" if typ else text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if not selected_categories or text in selected_set:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, text)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Применить")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        for btn in btns.buttons():
            btn.setStyleSheet(Components.small_button())
            
        layout.addWidget(btns)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def clear_cache(self):
        from PyQt6.QtWidgets import QMessageBox
        ans = QMessageBox.question(self, "Подтверждение", "Удалить все сохраненные категории?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            if self.on_clear_callback:
                self.on_clear_callback()
            self.reject() # Закрываем диалог

    def get_selected(self) -> list:
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected