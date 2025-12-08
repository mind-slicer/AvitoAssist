"""
Popup окно для управления наборами черного списка.
Можно создавать, активировать, переименовывать и удалять наборы.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QListWidget, QPushButton, QLineEdit, QDialog,
                               QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from app.ui.styles import Components, Palette, Spacing, Typography
from app.core.blacklist_manager import get_blacklist_manager


class BlacklistSetsPopup(QWidget):
    """
    Popup окно для управления наборами ЧС.
    Закрывается кликом вне окна, ESC или кнопкой "Закрыть".
    """

    closed = pyqtSignal()
    set_changed = pyqtSignal(int)  # Индекс активного набора изменился

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.manager = get_blacklist_manager()

        self._init_ui()
        self._load_sets()

        # Стили
        self.setStyleSheet(f"""
            BlacklistSetsPopup {{
                background-color: {Palette.BG_DARK_2};
                border: 2px solid {Palette.PRIMARY};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
        """)

        self.setFixedSize(400, 450)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        # Заголовок
        title = QLabel("НАБОРЫ ЧС")
        title.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_XL,
            weight=Typography.WEIGHT_BOLD,
            color=Palette.PRIMARY
        ))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Список наборов
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(Components.styled_list_widget() + f"""
            QListWidget::item {{
                height: 20px;
                padding-left: 8px;
                border-left: 4px solid transparent;
            }}
            QListWidget::item:selected {{
                border-left-color: {Palette.PRIMARY};
                background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)};
            }}
        """)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

        # Кнопки управления
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(Spacing.SM)

        self.btn_activate = self._create_button("✓ Активировать", Palette.SUCCESS)
        self.btn_create = self._create_button("+ Создать новый", Palette.PRIMARY)
        self.btn_rename = self._create_button("✎ Переименовать", Palette.WARNING)
        self.btn_delete = self._create_button("✖ Удалить", Palette.ERROR)

        self.btn_activate.clicked.connect(self._on_activate)
        self.btn_create.clicked.connect(self._on_create)
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_delete.clicked.connect(self._on_delete)

        btn_layout.addWidget(self.btn_activate)
        btn_layout.addWidget(self.btn_create)
        btn_layout.addWidget(self.btn_rename)
        btn_layout.addWidget(self.btn_delete)

        layout.addLayout(btn_layout)

        # Кнопка закрытия
        btn_close = QPushButton("Закрыть")
        btn_close.setStyleSheet(Components.stop_button())
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        self._update_buttons()

    def _create_button(self, text: str, color: str) -> QPushButton:
        """Создать кнопку с заданным цветом"""
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
        """Загрузить наборы в список"""
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
        """Обновить состояние кнопок при смене выбора"""
        self._update_buttons()

    def _update_buttons(self):
        """Обновить доступность кнопок"""
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
        """Активировать выбранный набор"""
        row = self.list_widget.currentRow()
        if row >= 0:
            self.manager.activate_set(row)
            self.manager.save()
            self._load_sets()
            self.set_changed.emit(row)

    def _on_create(self):
        """Создать новый набор"""
        name, ok = self._input_dialog("Создать набор", "Название набора:", f"Набор {len(self.manager.sets) + 1}")

        if ok and name:
            self.manager.create_set(name)
            self.manager.save()
            self._load_sets()

    def _on_rename(self):
        """Переименовать набор"""
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
        """Удалить набор"""
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
        """Простой диалог ввода текста"""
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
        btn_cancel.setStyleSheet(Components.secondary_button())
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("OK")
        btn_ok.setStyleSheet(Components.primary_button())
        btn_ok.clicked.connect(dialog.accept)
        btn_ok.setDefault(True)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)

        result = dialog.exec()
        return line_edit.text().strip(), result == QDialog.DialogCode.Accepted

    def keyPressEvent(self, event):
        """ESC закрывает окно"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Испустить сигнал при закрытии"""
        self.closed.emit()
        super().closeEvent(event)
