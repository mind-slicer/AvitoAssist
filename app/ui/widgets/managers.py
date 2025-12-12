from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                            QPushButton, QListWidgetItem, QMenu, QLineEdit,
                            QDialog, QMessageBox, QGroupBox, QAbstractItemView,
                            QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QMouseEvent, QCursor
import re

from app.ui.styles import Palette, Components, Spacing, Typography
from app.core.blacklist_manager import get_blacklist_manager

class BlacklistWidget(QWidget):
    enabled_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = get_blacklist_manager()
        self.popup = None
        
        main_frame = QGroupBox()
        main_frame.setStyleSheet(Components.panel())
        main_layout = QVBoxLayout(main_frame)
        # Уменьшаем отступы, чтобы было компактнее
        main_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        main_layout.setSpacing(Spacing.SM)
        
        # 1. Верхний ряд: Только Заголовок
        title = QLabel("ЧЕРНЫЙ СПИСОК")
        title.setStyleSheet(Components.section_title())
        main_layout.addWidget(title)
        
        # 2. Список (по центру)
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(Components.styled_list_widget() + """QListWidget::item { padding: 4px 8px; }""")
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.itemSelectionChanged.connect(self._update_remove_button)
        main_layout.addWidget(self.list_widget)

        # 3. Нижний ряд: Имя набора (слева) и Кнопки (справа)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(Spacing.SM)

        # ЛЕВАЯ ЧАСТЬ: Имя активного набора
        self.active_set_label = QLabel()
        self.active_set_label.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_MD,
            color=Palette.PRIMARY,
            weight=Typography.WEIGHT_BOLD
        ))
        bottom_bar.addWidget(self.active_set_label)
        
        bottom_bar.addStretch() # Распорка

        # ПРАВАЯ ЧАСТЬ: Кнопки
        
        # Кнопка "+"
        self.btn_add = QPushButton("+")
        self.btn_add.setFixedSize(28, 28)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setStyleSheet(self._get_button_style())
        self.btn_add.clicked.connect(self._on_add_clicked)
        
        # Кнопка "-"
        self.btn_remove = QPushButton("-")
        self.btn_remove.setFixedSize(28, 28)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setStyleSheet(self._get_button_style())
        self.btn_remove.clicked.connect(self._on_remove_clicked)

        # Кнопка "Меню наборов"
        self.btn_sets = QPushButton("≡")
        self.btn_sets.setToolTip("Управление наборами ЧС")
        self.btn_sets.setFixedSize(28, 28)
        self.btn_sets.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sets.setStyleSheet(self._get_button_style())
        self.btn_sets.clicked.connect(self._on_sets_clicked)

        # НОВАЯ КНОПКА: Глобальное включение/выключение
        self.btn_toggle = QPushButton("⏻") # Символ Power
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(True) # По умолчанию включено
        self.btn_toggle.setFixedSize(28, 28)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setToolTip("Вкл/Выкл фильтрацию по ЧС")
        # Стиль для toggle кнопки (зеленый/серый)
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_PRIMARY};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {Palette.TEXT_MUTED};
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:checked {{
                background-color: {Palette.with_alpha(Palette.SUCCESS, 0.2)};
                border: 1px solid {Palette.SUCCESS};
                color: {Palette.SUCCESS};
            }}
            QPushButton:hover {{ border-color: {Palette.PRIMARY}; }}
        """)
        self.btn_toggle.toggled.connect(self.enabled_toggled.emit)

        # Добавляем кнопки в ряд
        bottom_bar.addWidget(self.btn_add)
        bottom_bar.addWidget(self.btn_remove)
        bottom_bar.addWidget(self.btn_sets)
        bottom_bar.addWidget(self.btn_toggle) # Новая кнопка справа

        main_layout.addLayout(bottom_bar)
        
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(main_frame)
        
        self._refresh_list()
        self._update_remove_button()
    
    def _get_button_style(self):
        return (
            f"QPushButton {{ "
            f" background-color: {Palette.BG_DARK_3}; "
            f" border: 1px solid {Palette.BORDER_PRIMARY}; "
            f" border-radius: {Spacing.RADIUS_NORMAL}px; "
            f" color: {Palette.TEXT}; "
            f" font-size: 16px; "
            f" font-weight: {Typography.WEIGHT_BOLD}; "
            f" padding: 0; "
            f"}} "
            f"QPushButton:hover {{ background-color: {Palette.BG_LIGHT}; border-color: {Palette.PRIMARY}; color: {Palette.PRIMARY};}} "
            f"QPushButton:pressed {{ background-color: {Palette.BG_DARK_2}; }} "
            f"QPushButton:disabled {{ "
            f" background-color: {Palette.BG_DARK}; "
            f" border-color: {Palette.DIVIDER}; "
            f" color: {Palette.TEXT_MUTED}; "
            f"}} "
        )
    
    def _refresh_list(self):
        self.list_widget.clear()
        active_set = self.manager.get_active_set()
        if not active_set:
            self.active_set_label.setText("НЕТ НАБОРА")
            return
        
        self.active_set_label.setText(f"{active_set.name.upper()}")
        for entry in active_set.entries:
            display_text = f"{entry.custom_name} (ID: {entry.seller_id})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, entry.seller_id)
            self.list_widget.addItem(item)
    
    def is_blacklist_enabled(self) -> bool:
        return self.btn_toggle.isChecked()

    def get_blocked_seller_ids(self) -> set:
        if not self.is_blacklist_enabled():
            return set()
        return self.manager.get_active_seller_ids()

    def _update_remove_button(self):
        has_selection = len(self.list_widget.selectedItems()) > 0
        self.btn_remove.setEnabled(has_selection)
    
    def _on_sets_clicked(self):
        if self.popup is None or not self.popup.isVisible():
            from app.ui.widgets.blacklist_sets_popup import BlacklistSetsPopup
            self.popup = BlacklistSetsPopup(self)
            self.popup.set_changed.connect(self._on_set_changed)
            self.popup.closed.connect(self._on_popup_closed)
            btn_global_pos = self.btn_sets.mapToGlobal(self.btn_sets.rect().topLeft())
            self.popup.move(btn_global_pos.x() + 30, btn_global_pos.y())
            self.popup.show()
    
    def _on_set_changed(self, index):
        self._refresh_list()
    
    def _on_popup_closed(self):
        self.popup = None
    
    def _on_add_clicked(self):
        active_set = self.manager.get_active_set()
        if not active_set:
            QMessageBox.warning(self, "Ошибка", "Нет активного набора!")
            return
        seller_id, ok = self._input_dialog("Добавить в ЧС", "ID продавца:", "")
        if not ok or not seller_id: return
        if seller_id in active_set.get_seller_ids():
            QMessageBox.warning(self, "Дубликат", f"Seller ID '{seller_id}' уже в списке!")
            return
        custom_name, ok = self._input_dialog("Имя продавца", "Кастомное имя (необязательно):", f"Seller_{seller_id}")
        if not ok: return
        active_set.add_entry(seller_id, custom_name)
        self.manager.save()
        self._refresh_list()
    
    def _on_remove_clicked(self):
        current_item = self.list_widget.currentItem()
        if not current_item: return
        seller_id = current_item.data(Qt.ItemDataRole.UserRole)
        active_set = self.manager.get_active_set()
        if active_set:
            active_set.remove_entry(seller_id)
            self.manager.save()
            self._refresh_list()
    
    def _on_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item: return
        seller_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(f"background: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT};")
        act_rename = menu.addAction("Изменить имя")
        menu.addSeparator()
        act_delete = menu.addAction("Удалить")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == act_rename: self._rename_entry(seller_id)
        elif action == act_delete:
            active_set = self.manager.get_active_set()
            if active_set:
                active_set.remove_entry(seller_id)
                self.manager.save()
                self._refresh_list()
    
    def _rename_entry(self, seller_id: str):
        active_set = self.manager.get_active_set()
        if not active_set: return
        current_name = ""
        for entry in active_set.entries:
            if entry.seller_id == seller_id:
                current_name = entry.custom_name
                break
        new_name, ok = self._input_dialog("Изменить имя", f"Новое имя для ID {seller_id}:", current_name)
        if ok and new_name:
            active_set.update_entry_name(seller_id, new_name)
            self.manager.save()
            self._refresh_list()
    
    def _input_dialog(self, title: str, label: str, default: str = "") -> tuple:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setStyleSheet(Components.dialog())
        dialog.setFixedWidth(350)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(Spacing.MD)
        lbl = QLabel(label)
        lbl.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_MD, color=Palette.TEXT))
        layout.addWidget(lbl)
        line_edit = QLineEdit(default)
        line_edit.setStyleSheet(Components.text_input())
        line_edit.selectAll()
        layout.addWidget(line_edit)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet(Components.stop_button())
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

class QueueItemWidget(QWidget):
    """
    Виджет для элемента очереди.
    Содержит Чекбокс (для вкл/выкл) и Лейбл (для названия).
    """
    toggled = pyqtSignal(bool)
    clicked = pyqtSignal() # Сигнал клика по телу (для выбора)

    def __init__(self, text, is_checked=True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 0, Spacing.SM, 0)
        layout.setSpacing(Spacing.SM)
        
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.checkbox.setFixedWidth(24)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.checkbox.toggled.connect(self.toggled.emit)
        
        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"color: {Palette.TEXT}; font-size: {Typography.SIZE_MD}px; background: transparent;"
        )
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.label, 1)
        layout.setAlignment(self.checkbox, Qt.AlignmentFlag.AlignVCenter)
        layout.setAlignment(self.label, Qt.AlignmentFlag.AlignVCenter)
        
        self.setLayout(layout)

    def mousePressEvent(self, event: QMouseEvent):
        # Если клик не попал в чекбокс (а он не попадет, т.к. чекбокс отдельный виджет),
        # то это клик по телу виджета -> значит выбор строки
        self.clicked.emit()
        # Не вызываем super(), чтобы не портить логику
    
    def set_text(self, text):
        self.label.setText(text)
    
    def text(self):
        return self.label.text()
    
    def set_checked(self, checked):
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)
        
    def set_checkbox_enabled(self, enabled):
        self.checkbox.setEnabled(enabled)


class QueueManagerWidget(QWidget):
    
    queue_changed = pyqtSignal(int)
    queue_removed = pyqtSignal(int)
    queue_toggled = pyqtSignal(int, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setStyleSheet(f"""
        QueueManagerWidget {{
            background-color: {Palette.with_alpha(Palette.BG_DARK, 0.5)};
            border: 1px solid {Palette.BORDER_SOFT};
            border-radius: {Spacing.RADIUS_NORMAL}px;
            padding: {Spacing.SM}px;
        }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(Spacing.SM)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            Components.styled_list_widget()
            + Components.styled_checkbox()   # ← добавили стиль чекбокса
            + f"""
        QListWidget::item {{
            height: 32px;
            border-bottom: 1px solid {Palette.BORDER_PRIMARY};
        }}
        
        QListWidget::item:selected {{
            background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)};
            border-left: 4px solid {Palette.PRIMARY};
        }}
        """
        )
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        # Контекстное меню
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_queue_context_menu)
        
        # Сигнал смены выбора
        self.list_widget.currentRowChanged.connect(
            lambda r: self.queue_changed.emit(r) if r >= 0 else None
        )
        
        main_layout.addWidget(self.list_widget)
        
        # Добавляем первую очередь при старте
        self.add_queue()
    
    def add_queue(self):
        # Создаем контейнер-итем
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 34)) # Высота строки
        
        # Создаем наш кастомный виджет
        idx = self.list_widget.count() + 1
        widget = QueueItemWidget(f"Очередь {idx}", is_checked=True)
        
        # Добавляем в список
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)
        
        # Подключаем сигналы виджета к методам
        # Используем замыкание (item=item), чтобы привязаться к конкретному объекту
        widget.toggled.connect(lambda c, i=item: self._on_widget_toggled(i, c))
        widget.clicked.connect(lambda i=item: self.list_widget.setCurrentItem(i))
        
        # Обновляем блокировки (если теперь > 1, разблокируем первую)
        self._update_checkable_state()
        
        if self.list_widget.count() == 1:
            self.list_widget.setCurrentRow(0)
    
    def remove_queue(self):
        row = self.list_widget.currentRow()
        if row >= 0 and self.list_widget.count() > 1:
            self.list_widget.takeItem(row)
            
            # Переименовываем, чтобы сохранить порядок "Очередь 1, 2..." (опционально)
            for i in range(self.list_widget.count()):
                itm = self.list_widget.item(i)
                w = self.list_widget.itemWidget(itm)
                if w and re.match(r"^Очередь \d+$", w.text()):
                    w.set_text(f"Очередь {i + 1}")
            
            self.queue_removed.emit(row)
            self._update_checkable_state()
    
    def _update_checkable_state(self):
        """
        Блокирует чекбокс, если осталась ВСЕГО одна очередь.
        """
        count = self.list_widget.count()
        for i in range(count):
            itm = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(itm)
            if widget:
                if count == 1:
                    # Одна очередь: всегда включена и заблокирована
                    widget.set_checked(True)
                    widget.set_checkbox_enabled(False)
                else:
                    # Много очередей: разблокированы
                    widget.set_checkbox_enabled(True)

    def _on_widget_toggled(self, item, is_checked):
        row = self.list_widget.row(item)
        if row >= 0:
            self.queue_toggled.emit(row, is_checked)

    def _on_queue_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item: return
        
        menu = QMenu(self)
        menu.setStyleSheet(f"background: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT};")
        act_rename = menu.addAction("Переименовать")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        
        if action == act_rename:
            self._rename_item(item)
            
    def _rename_item(self, item):
        widget = self.list_widget.itemWidget(item)
        if not widget: return
        
        # Используем диалог, чтобы избежать проблем с фокусом в списке
        new_name, ok = self._input_dialog("Переименовать", "Новое имя:", widget.text())
        if ok and new_name:
            widget.set_text(new_name)

    def _input_dialog(self, title: str, label: str, default: str = "") -> tuple:
        # Дублируем метод диалога, т.к. он удобен
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setStyleSheet(Components.dialog())
        dialog.setFixedWidth(300)
        
        layout = QVBoxLayout(dialog)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(lbl)
        
        inp = QLineEdit(default)
        inp.setStyleSheet(Components.text_input())
        inp.selectAll()
        layout.addWidget(inp)
        
        btns = QHBoxLayout()
        b_ok = QPushButton("OK")
        b_ok.clicked.connect(dialog.accept)
        b_ok.setStyleSheet(Components.start_button())
        btns.addWidget(b_ok)
        layout.addLayout(btns)
        
        res = dialog.exec()
        return inp.text().strip(), res == QDialog.DialogCode.Accepted

    def set_queue_checked(self, index, checked):
        if 0 <= index < self.list_widget.count():
            item = self.list_widget.item(index)
            widget = self.list_widget.itemWidget(item)
            if widget:
                widget.set_checked(checked)
                # После программного изменения тоже проверяем блокировку
                self._update_checkable_state()

    def get_all_queues_count(self):
        return self.list_widget.count()
    
    def set_current_queue(self, index):
        if 0 <= index < self.list_widget.count():
            self.list_widget.setCurrentRow(index)