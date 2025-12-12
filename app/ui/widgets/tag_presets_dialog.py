from typing import Dict, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QInputDialog
)
from PyQt6.QtCore import Qt
from app.ui.widgets.tags import TagsInput
from app.ui.styles import Components, Palette, Typography, Spacing

class TagPresetsDialog(QDialog):
    def __init__(self, presets: Dict[str, List[str]], parent=None, *, window_title="Наборы", tag_color=Palette.PRIMARY):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(600, 400)
        self.setStyleSheet(Components.dialog())
        
        self.presets = {k: list(v) for k, v in presets.items()}
        layout = QHBoxLayout(self)
        layout.setSpacing(Spacing.LG)

        # LEFT
        left = QVBoxLayout()
        lbl_left = QLabel("СПИСОК НАБОРОВ")
        lbl_left.setStyleSheet(Components.section_title())
        left.addWidget(lbl_left)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                color: {Palette.TEXT};
            }}
            QListWidget::item:selected {{ background: {Palette.with_alpha(tag_color, 0.2)}; color: {tag_color}; }}
        """)
        for name in sorted(self.presets.keys()):
            self._add_list_item(name)
        left.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_style = f"""
            QPushButton {{ background-color: {Palette.BG_DARK_3}; border: 1px solid {Palette.BORDER_PRIMARY}; border-radius: {Spacing.RADIUS_NORMAL}px; color: {Palette.TEXT}; font-size: 12px; font-weight: {Typography.WEIGHT_BOLD}; padding: 0; }}
            QPushButton:hover {{ background-color: {Palette.BG_LIGHT}; border-color: {Palette.PRIMARY}; color: {Palette.PRIMARY}; }}
            QPushButton:pressed {{ background-color: {Palette.BG_DARK_2}; }}
            QPushButton:disabled {{ background-color: {Palette.BG_DARK}; border-color: {Palette.DIVIDER}; color: {Palette.TEXT_MUTED}; }}
        """
        for txt, func in [("✚", self._add_preset), ("━", self._delete_preset), ("Переименовать", self._rename_preset)]:
            b = QPushButton(txt)
            b.setMinimumSize(30, 25)
            b.setStyleSheet(btn_style)
            b.clicked.connect(func)
            b.setAutoDefault(False)
            b.setDefault(False)
            btn_row.addWidget(b)
        btn_row.addStretch(0)
        left.addLayout(btn_row)

        # RIGHT
        right = QVBoxLayout()
        lbl_right = QLabel("ТЕГИ НАБОРА")
        lbl_right.setStyleSheet(Components.section_title())
        right.addWidget(lbl_right)

        self.tags_input = TagsInput(tag_color=tag_color)
        right.addWidget(self.tags_input)
        self.tags_input.tags_changed.connect(self._on_tags_changed)
        self.tags_input.input_field.setFocus()

        btn_box = QHBoxLayout()
        b_close = QPushButton("Закрыть")
        b_close.setMinimumSize(30, 25)
        b_close.setStyleSheet(btn_style)
        b_close.clicked.connect(self.accept)
        b_close.setAutoDefault(False)
        b_close.setDefault(False)
        btn_box.addStretch()
        btn_box.addWidget(b_close)
        right.addLayout(btn_box)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)
        
        self.list_widget.currentItemChanged.connect(self._on_preset_changed)
        if self.list_widget.count() > 0: self.list_widget.setCurrentRow(0)

    def _add_list_item(self, name):
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, name)
        self.list_widget.addItem(item)

    def _on_tags_changed(self, tags):
        item = self.list_widget.currentItem()
        if item:
            name = item.data(Qt.ItemDataRole.UserRole)
            self.presets[name] = [t for t in tags if t]
        else:
            if tags:
                name, ok = QInputDialog.getText(self, "Новый набор", "Имя:")
                if ok and name.strip():
                    self.presets[name] = [t for t in tags if t]
                    self._add_list_item(name)
                    self.list_widget.setCurrentRow(self.list_widget.count() - 1)
                    self.tags_input.input_field.setFocus()
                else:
                    self.tags_input.clear_tags()

    def _on_preset_changed(self, curr, prev):
        if not curr: 
            self.tags_input.clear_tags()
            return
        name = curr.data(Qt.ItemDataRole.UserRole)
        self.tags_input.set_tags(self.presets.get(name, []))

    def _add_preset(self):
        name, ok = QInputDialog.getText(self, "Новый набор", "Имя:")
        if ok and name.strip():
            self.presets[name] = []
            self._add_list_item(name)
            self.list_widget.setCurrentRow(self.list_widget.count() - 1)
            self.tags_input.input_field.setFocus()

    def _rename_preset(self):
        item = self.list_widget.currentItem()
        if not item: return
        old = item.data(Qt.ItemDataRole.UserRole)
        name, ok = QInputDialog.getText(self, "Переименовать", "Имя:", text=old)
        if ok and name.strip() and name != old:
            self.presets[name] = self.presets.pop(old)
            item.setText(name)
            item.setData(Qt.ItemDataRole.UserRole, name)

    def _delete_preset(self):
        item = self.list_widget.currentItem()
        if not item: return
        name = item.data(Qt.ItemDataRole.UserRole)
        del self.presets[name]
        self.list_widget.takeItem(self.list_widget.row(item))

    def get_presets(self): return self.presets