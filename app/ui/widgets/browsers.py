import os
from typing import Optional
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPushButton, QListWidgetItem, QMessageBox, QMenu, QLineEdit, QSizePolicy, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QValidator
from app.ui.styles import Components, Palette, Typography, Spacing, InputComponents
from app.config import RESULTS_DIR
from app.core.log_manager import logger

class FilenameValidator(QValidator):
    def validate(self, text, pos):
        forbidden = r'\/:*?"<>|'
        if any(char in text for char in forbidden):
            return (QValidator.State.Invalid, text, pos)
        return (QValidator.State.Acceptable, text, pos)

class BaseJsonFileBrowser(QWidget):
    file_loaded = pyqtSignal(str, list)
    file_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_list = None

    def iter_files(self):
        files_info = []
        try:
            files = [f for f in os.listdir(RESULTS_DIR) if f.endswith('.json') and f.startswith('avito_')]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(RESULTS_DIR, x)), reverse=True)
            for f in files:
                full_path = os.path.join(RESULTS_DIR, f)
                mtime = os.path.getmtime(full_path)
                size_kb = os.path.getsize(full_path) / 1024
                files_info.append((full_path, mtime, size_kb))
        except: pass
        return files_info

    def refresh_files(self):
        if self.file_list is None: return
        self.file_list.clear()
        for fname, mtime, size_kb in self.iter_files():
            item, widget = self.create_item_widget(fname, mtime, size_kb)
            if item is None: continue
            self.file_list.addItem(item)
            if widget is not None: self.file_list.setItemWidget(item, widget)

    def load_selected_file(self):
        if not self.file_list: return
        item = self.file_list.currentItem()
        if not item: return
        fname = item.data(Qt.ItemDataRole.UserRole)
        if not fname: return

        import json, gzip
        try:
            try:
                with open(fname, 'r', encoding='utf-8') as f: data = json.load(f)
            except:
                with gzip.open(fname, 'rt', encoding='utf-8') as f: data = json.load(f)
            self.file_loaded.emit(fname, data)
        except Exception: pass

    def delete_selected_file(self):
        item = self.file_list.currentItem()
        if not item: return
        fname = item.data(Qt.ItemDataRole.UserRole)
        if not fname or not self.confirm_delete(fname): return

        try:
            os.remove(fname)
            self.refresh_files()
            self.file_deleted.emit(fname)
        except: pass

    def create_item_widget(self, filename: str, mtime: float, size_kb: float): raise NotImplementedError
    def confirm_delete(self, filename: str) -> bool: return True

class MiniFileBrowser(BaseJsonFileBrowser):
    table_closed = pyqtSignal()
    analyze_file_requested = pyqtSignal(str)
    addmemory_file_requested = pyqtSignal(str)
    export_file_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_editing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        # Header Container matching Table Header Height
        header_container = QWidget()
        header_container.setFixedHeight(46) # Approximate height of section title area in ResultsArea
        h = QHBoxLayout(header_container)
        h.setContentsMargins(0, Spacing.SM, 0, Spacing.SM)
        
        title_lbl = QLabel("РЕЗУЛЬТАТЫ")
        title_lbl.setStyleSheet(Components.section_title())
        h.addWidget(title_lbl)
        h.addStretch()
        layout.addWidget(header_container)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(345)
        self.file_list.setUniformItemSizes(True)
        self.file_list.setWordWrap(False)
        self.file_list.setStyleSheet(Components.styled_list_widget())
        self.file_list.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)
        self.file_list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.file_list)

        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._on_context_menu)

        self.refresh_files()

    def _on_double_click(self, item):
        if item and not self._is_editing:
            self.file_list.setCurrentItem(item)
            self.load_selected_file()

    def _on_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item: return

        menu = QMenu(self)
        menu.setStyleSheet(f"background: {Palette.BG_DARK_2}; color: {Palette.TEXT};")
        act_clear = menu.addAction("Закрыть таблицу")
        act_rename = menu.addAction("Переименовать")
        menu.addSeparator()
        act_analyze = menu.addAction("🔍 Проанализировать")
        act_addmemory = menu.addAction("🧠 Добавить в память ИИ")
        act_export = menu.addAction("📊 Выгрузить в таблицу")
        menu.addSeparator()
        act_delete = menu.addAction("Удалить")

        action = menu.exec(self.file_list.mapToGlobal(pos))

        if action == act_rename: self._start_rename(item)
        elif action == act_analyze:
            self.file_list.setCurrentItem(item)
            self.analyze_file_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        elif action == act_addmemory:
            self.file_list.setCurrentItem(item)
            self.addmemory_file_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        elif action == act_export:
            self.file_list.setCurrentItem(item)
            self.export_file_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        elif action == act_delete:
            self.file_list.setCurrentItem(item)
            self.delete_selected_file()
        elif action == act_clear:
            self.file_list.clearSelection()
            self.table_closed.emit()
        

    def _start_rename(self, item):
        widget = self.file_list.itemWidget(item)
        if not widget: return

        name_label = widget.findChild(QLabel, "name_label")
        if not name_label: return

        layout = widget.layout()
        old_name = name_label.text()

        item.setData(Qt.ItemDataRole.UserRole + 2, old_name)

        name_edit = QLineEdit(old_name)
        name_edit.setObjectName("name_edit")
        name_edit.setFrame(False)
        name_edit.setValidator(FilenameValidator())

        name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name_edit.setFixedHeight(24)
        name_edit.setStyleSheet(InputComponents.text_input() + """
            QLineEdit {
                padding: 2px 4px;
                margin: 0px;
            }
        """)

        layout_index = layout.indexOf(name_label)
        layout.removeWidget(name_label)
        name_label.hide()
        layout.insertWidget(layout_index, name_edit, 3)

        self._is_editing = True

        name_edit.setFocus()
        name_edit.selectAll()

        name_edit.editingFinished.connect(lambda: self._finish_rename(item, name_edit))

    def _finish_rename(self, item, name_edit):
        if not self._is_editing: return
        self._is_editing = False

        old_filename = item.data(Qt.ItemDataRole.UserRole)
        new_name = name_edit.text().strip()

        if not new_name:
            self.refresh_files()
            return

        new_filename = f"avito_{new_name}.json"
        old_path = old_filename
        new_path = os.path.join(RESULTS_DIR, new_filename)

        if old_path == new_path:
            self.refresh_files()
            return

        try:
            os.rename(old_path, new_path)
            logger.info(f"Переименовано: {os.path.basename(old_path)} -> {os.path.basename(new_path)}...")
        except Exception as e:
            logger.error(f"Ошибка переименования: {e}...")

        self.refresh_files()

    def create_item_widget(self, filename: str, mtime: float, size_kb: float):
        dt = datetime.fromtimestamp(mtime).strftime("%d-%m-%Y %H:%M")
        base = os.path.basename(filename)
        dn = base.replace("avito_", "").replace(".json", "")

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, filename)
        item.setData(Qt.ItemDataRole.UserRole + 3, dn)
        item.setToolTip(base)

        widget = QWidget()
        widget.setObjectName("file_item_widget")
        widget.setStyleSheet("background: transparent;")

        widget_layout = QHBoxLayout(widget)
        widget_layout.setContentsMargins(6, 4, 6, 4)
        widget_layout.setSpacing(6)
        widget_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        name_label = QLabel(dn)
        name_label.setObjectName("name_label")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        name_label.setStyleSheet(Typography.style(family=Typography.MONO, size=Typography.SIZE_LG, color=Palette.TEXT, weight=Typography.WEIGHT_SEMIBOLD))

        date_label = QLabel(f"{dt}")
        date_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        date_label.setFixedWidth(120)
        date_label.setStyleSheet(Typography.style(family=Typography.MONO, size=Typography.SIZE_MD, weight=Typography.WEIGHT_SEMIBOLD, color=Palette.TEXT_MUTED))

        widget_layout.addWidget(name_label, 3)
        widget_layout.addWidget(date_label, 0)

        item.setSizeHint(QSize(widget.sizeHint().width(), 36))

        return item, widget

    def confirm_delete(self, filename: str) -> bool:
        reply = QMessageBox.question(self, "Удаление", "Удалить файл навсегда?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes