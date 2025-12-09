from typing import List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from app.ui.styles import Components, Palette, Typography, Spacing

class CategorySelectionDialog(QDialog):
    def __init__(self, categories: List[dict], parent=None, selected_categories: List[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Выберите категории")
        self.resize(400, 500)
        self.setStyleSheet(Components.dialog())

        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        
        lbl = QLabel("Доступные разделы:")
        lbl.setStyleSheet(Components.section_title())
        layout.addWidget(lbl)

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

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        btns.rejected.connect(self.accept)
        
        for btn in btns.buttons():
            btn.setStyleSheet(Components.small_button())
            
        layout.addWidget(btns)

    def get_selected(self) -> list:
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected