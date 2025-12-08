from typing import List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from app.ui.styles import Components, Palette, Typography, Spacing

class CategorySelectionDialog(QDialog):
    def __init__(self, categories: List[dict], parent=None):
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

        for cat in categories:
            # cat is usually dict {'text': '...', 'type': '...'}
            text = cat.get('text', str(cat))
            typ = cat.get('type', '')
            item = QListWidgetItem(f"[{typ}] {text}" if typ else text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, text)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        # Style buttons roughly
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