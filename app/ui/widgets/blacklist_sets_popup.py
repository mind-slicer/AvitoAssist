from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QListWidget, QPushButton, QLineEdit, QDialog,
                               QListWidgetItem, QMessageBox, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal
from app.ui.styles import Components, Palette, Spacing, Typography
from app.core.blacklist_manager import get_blacklist_manager


class BlacklistSetsPopup(QWidget):
    closed = pyqtSignal()
    set_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.manager = get_blacklist_manager()

        self.setStyleSheet(f"""
            BlacklistSetsPopup {{
                background-color: {Palette.BG_DARK};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
            QListWidget {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {Palette.TEXT};
                font-family: {Typography.UI};
                outline: none;
            }}
            QListWidget::item {{
                padding: {Spacing.XS}px;
                border-bottom: 1px solid {Palette.with_alpha(Palette.BORDER_SOFT, 0.5)};
            }}
            QListWidget::item:selected {{
                background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)};
                border-left: 2px solid {Palette.PRIMARY};
                color: {Palette.TEXT};
            }}
        """)

        self.setFixedSize(350, 400)
        self._init_ui()
        self._load_sets()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        title = QLabel("УПРАВЛЕНИЕ НАБОРАМИ")
        title.setStyleSheet(Components.section_title()) 
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.verticalScrollBar().setStyleSheet(Components.global_scrollbar())
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

        btns_layout = QVBoxLayout()
        btns_layout.setSpacing(Spacing.SM)

        def create_tool_btn(text, color_hover=Palette.PRIMARY):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_DARK_3};
                    border: 1px solid {Palette.BORDER_PRIMARY};
                    border-radius: {Spacing.RADIUS_NORMAL}px;
                    color: {Palette.TEXT};
                    padding: 6px;
                    text-align: left;
                    padding-left: 12px;
                }}
                QPushButton:hover {{
                    background-color: {Palette.with_alpha(color_hover, 0.1)};
                    border-color: {color_hover};
                    color: {color_hover};
                }}
                QPushButton:disabled {{
                    color: {Palette.TEXT_MUTED};
                    background-color: {Palette.BG_DARK};
                    border-color: {Palette.BORDER_SOFT};
                }}
            """)
            return btn

        self.btn_activate = create_tool_btn("✓  Активировать этот набор", Palette.SUCCESS)
        self.btn_create = create_tool_btn("+  Создать новый", Palette.PRIMARY)
        self.btn_rename = create_tool_btn("✎  Переименовать", Palette.WARNING)
        self.btn_delete = create_tool_btn("✖  Удалить", Palette.ERROR)

        self.btn_activate.clicked.connect(self._on_activate)
        self.btn_create.clicked.connect(self._on_create)
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_delete.clicked.connect(self._on_delete)

        btns_layout.addWidget(self.btn_activate)
        btns_layout.addWidget(self.btn_create)
        btns_layout.addWidget(self.btn_rename)
        btns_layout.addWidget(self.btn_delete)

        layout.addLayout(btns_layout)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        btn_close = QPushButton("Закрыть")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{ 
                background-color: transparent; 
                border: 1px solid {Palette.BORDER_SOFT}; 
                color: {Palette.TEXT_MUTED}; 
                border-radius: 4px; padding: 4px 12px;
            }}
            QPushButton:hover {{ background-color: {Palette.BG_DARK_3}; color: {Palette.TEXT}; }}
        """)
        btn_close.clicked.connect(self.close)
        close_layout.addWidget(btn_close)
        
        layout.addLayout(close_layout)

        self._update_buttons()

    def showEvent(self, event):
        self._ensure_visible_position()
        super().showEvent(event)

    def _ensure_visible_position(self):
        current_geo = self.geometry()
        
        screen = QApplication.screenAt(current_geo.center())
        if not screen:
            screen = QApplication.primaryScreen()
        
        avail_geo = screen.availableGeometry()

        x = current_geo.x()
        y = current_geo.y()
        w = current_geo.width()
        h = current_geo.height()
        padding = 5

        if x < avail_geo.left() + padding:
            x = avail_geo.left() + padding
        elif x + w > avail_geo.right() - padding:
            x = avail_geo.right() - w - padding
        
        if y < avail_geo.top() + padding:
            y = avail_geo.top() + padding
        elif y + h > avail_geo.bottom() - padding:
            y = avail_geo.bottom() - h - padding

        if x != current_geo.x() or y != current_geo.y():
            self.move(x, y)

    def _create_button(self, text: str, color: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.with_alpha(color, 0.2)};
                border: 1px solid {color};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {color};
                font-size: {Typography.SIZE_MD}px;
                font-weight: {Typography.WEIGHT_SEMIBOLD};
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: {Palette.with_alpha(color, 0.3)};
                border-width: 2px;
            }}
            QPushButton:pressed {{
                background-color: {Palette.with_alpha(color, 0.4)};
            }}
            QPushButton:disabled {{
                background-color: {Palette.BG_DARK};
                border-color: {Palette.DIVIDER};
                color: {Palette.TEXT_MUTED};
            }}
        """)
        return btn

    def _load_sets(self):
        self.list_widget.clear()

        for i, bl_set in enumerate(self.manager.sets):
            count = len(bl_set.entries)
            active_marker = "★ " if bl_set.is_active else ""
            text = f"{active_marker}{bl_set.name} ({count})"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list_widget.addItem(item)

            if bl_set.is_active:
                self.list_widget.setCurrentRow(i)

    def _on_selection_changed(self):
        self._update_buttons()

    def _update_buttons(self):
        has_selection = self.list_widget.currentRow() >= 0
        current_row = self.list_widget.currentRow()
        is_active = (current_row >= 0 and 
                     current_row < len(self.manager.sets) and 
                     self.manager.sets[current_row].is_active)
        can_delete = len(self.manager.sets) > 1

        self.btn_activate.setEnabled(has_selection and not is_active)
        self.btn_rename.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection and can_delete)

    def _on_activate(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.manager.activate_set(row)
            self.manager.save()
            self._load_sets()
            self.set_changed.emit(row)

    def _on_create(self):
        name, ok = self._input_dialog("Создать набор", "Название набора:", f"Набор {len(self.manager.sets) + 1}")

        if ok and name:
            self.manager.create_set(name)
            self.manager.save()
            self._load_sets()

    def _on_rename(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return

        current_name = self.manager.sets[row].name
        name, ok = self._input_dialog("Переименовать набор", "Новое название:", current_name)

        if ok and name:
            self.manager.rename_set(row, name)
            self.manager.save()
            self._load_sets()

    def _on_delete(self):
        row = self.list_widget.currentRow()
        if row < 0 or len(self.manager.sets) <= 1:
            return

        set_name = self.manager.sets[row].name
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить набор '{set_name}'?\n\nВсе записи в этом наборе будут потеряны.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.manager.delete_set(row)
            self.manager.save()
            self._load_sets()
            self.set_changed.emit(self.manager.active_set_index or 0)

    def _input_dialog(self, title: str, label: str, default: str = "") -> tuple:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setStyleSheet(Components.dialog())
        dialog.setFixedWidth(300)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(Spacing.MD)

        lbl = QLabel(label)
        lbl.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            color=Palette.TEXT
        ))
        layout.addWidget(lbl)

        line_edit = QLineEdit(default)
        line_edit.setStyleSheet(Components.text_input())
        line_edit.selectAll()
        layout.addWidget(line_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {Palette.TEXT_MUTED};
                padding: 6px 12px;
                font-family: {Typography.UI};
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_DARK_3};
                color: {Palette.TEXT};
                border-color: {Palette.TEXT_MUTED};
            }}
        """)
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("OK")
        btn_ok.setStyleSheet(Components.start_button())
        btn_ok.clicked.connect(dialog.accept)
        btn_ok.setDefault(True)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)

        result = dialog.exec()
        return line_edit.text().strip(), result == QDialog.DialogCode.Accepted

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
