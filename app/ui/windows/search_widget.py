import os
import json
from typing import List, Dict, Set, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox,
    QSizePolicy, QFrame, QLabel, QMenu, QWidgetAction, QDialog,
    QTreeWidget, QTreeWidgetItem, QApplication, QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor

from app.ui.widgets.tags import TagsInput
from app.ui.widgets.category_selection_dialog import CategorySelectionDialog
from app.ui.widgets.tag_presets_dialog import TagPresetsDialog
from app.ui.styles import Components, Palette, Spacing
from app.config import BASE_APP_DIR


class PresetsSelectPopup(QDialog):
    def __init__(self, parent, 
                 search_presets: dict, 
                 ignore_presets: dict, 
                 saved_checked: Set[str],    # Состояние галочек
                 saved_expanded: Set[str],   # Состояние раскрытых папок
                 primary_is_ignore: bool):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self.saved_checked = set(saved_checked)
        self.saved_expanded = set(saved_expanded)
        self.primary_is_ignore = primary_is_ignore
        
        self.selected_search_tags = []
        self.selected_ignore_tags = []
        self.new_checked_state = set()
        self.action_type = None 
        
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Palette.BG_DARK_2};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {Palette.TEXT};
            }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:hover {{ background-color: {Palette.BG_DARK_3}; }}
            QTreeWidget::item:selected {{ background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)}; color: {Palette.TEXT}; }}
            QLabel {{ color: {Palette.TEXT_MUTED}; }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS)
        layout.setSpacing(Spacing.SM)
        
        # --- 1. ЗАГОЛОВОК И НАСТРОЙКИ ---
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        
        lbl = QLabel("")
        lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        
        manage_text = "⚙ Управление наборами фильтров" if primary_is_ignore else "⚙ Управление наборами поиска"
        manage_mode = 'ignore' if primary_is_ignore else 'search'
        
        btn_manage = QPushButton(manage_text)
        btn_manage.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_manage.setStyleSheet(f"border: none; color: {Palette.PRIMARY}; font-size: 11px; text-align: right;")
        btn_manage.clicked.connect(lambda: self._on_manage(manage_mode))
        
        header_layout.addWidget(lbl)
        header_layout.addStretch()
        header_layout.addWidget(btn_manage)
        layout.addLayout(header_layout)
        
        # --- 2. ДЕРЕВО ---
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.tree)
        
        # Наполняем дерево (сигналы еще НЕ подключены, ошибок не будет)
        if primary_is_ignore:
            self._add_root_section("ИСКЛЮЧАЕМ", ignore_presets, "ignore")
            self._add_root_section("ИЩЕМ", search_presets, "search")
        else:
            self._add_root_section("ИЩЕМ", search_presets, "search")
            self._add_root_section("ИСКЛЮЧАЕМ", ignore_presets, "ignore")

        # --- 3. ЗОНА ПРЕДПРОСМОТРА ВЫБРАННОГО ---
        summary_container = QFrame()
        summary_container.setStyleSheet(f"background-color: {Palette.BG_DARK_3}; border-radius: 4px;")
        summary_layout = QVBoxLayout(summary_container)
        summary_layout.setContentsMargins(6, 6, 6, 6)
        summary_layout.setSpacing(4)
        
        sum_header = QHBoxLayout()
        self.lbl_summary_count = QLabel("Выбрано: 0")
        self.lbl_summary_count.setStyleSheet("font-weight: bold; font-size: 10px;")
        
        btn_clear = QPushButton("Очистить всё")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setFixedSize(80, 16)
        btn_clear.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Palette.ERROR}; border: none; font-size: 10px; }}
            QPushButton:hover {{ text-decoration: underline; }}
        """)
        btn_clear.clicked.connect(self._clear_all_checks)
        
        sum_header.addWidget(self.lbl_summary_count)
        sum_header.addStretch()
        sum_header.addWidget(btn_clear)
        summary_layout.addLayout(sum_header)
        
        self.lbl_summary_text = QLabel("Нет тегов")
        self.lbl_summary_text.setWordWrap(True)
        self.lbl_summary_text.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 10px;")
        self.lbl_summary_text.setMaximumHeight(40)
        summary_layout.addWidget(self.lbl_summary_text)
        
        layout.addWidget(summary_container)

        # --- 4. КНОПКИ ДЕЙСТВИЙ ---
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(2)
        
        self.btn_apply_curr = QPushButton("✅ Применить в текущую очередь")
        self.btn_apply_curr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_curr.setStyleSheet(self._btn_style(Palette.PRIMARY))
        self.btn_apply_curr.clicked.connect(self._on_apply_current)
        btn_layout.addWidget(self.btn_apply_curr)
        
        if not primary_is_ignore:
            self.btn_apply_new = QPushButton("➕ Применить в новую очередь")
            self.btn_apply_new.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_apply_new.setStyleSheet(self._btn_style(Palette.PRIMARY))
            self.btn_apply_new.clicked.connect(self._on_apply_new)
            btn_layout.addWidget(self.btn_apply_new)
            
        layout.addLayout(btn_layout)
        
        self.resize(340, 600)
        
        # Обновляем текст summary первый раз (вручную, так как сигналы еще отключены)
        self._refresh_summary() 

        # --- 5. ВАЖНО: ПОДКЛЮЧАЕМ СИГНАЛЫ ТОЛЬКО СЕЙЧАС ---
        # (чтобы избежать AttributeError при инициализации)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)

    def _btn_style(self, color):
        return f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: 4px;
                color: {Palette.TEXT};
                padding: 8px;
                text-align: center;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {color};
                color: {Palette.BG_DARK};
                border-color: {color};
            }}
        """

    def _add_root_section(self, title: str, presets: dict, tag_type: str):
        root = QTreeWidgetItem([title])
        root.setFlags(Qt.ItemFlag.ItemIsEnabled) 
        root.setBackground(0, QColor(Palette.BG_DARK_3))
        root.setForeground(0, QColor(Palette.TEXT_MUTED))
        font = root.font(0)
        font.setBold(True)
        root.setFont(0, font)
        self.tree.addTopLevelItem(root)
        
        root_key = f"ROOT:{tag_type}"
        root.setData(0, Qt.ItemDataRole.UserRole + 2, root_key)
        if root_key in self.saved_expanded:
            root.setExpanded(True)

        sorted_keys = sorted(presets.keys())
        for name in sorted_keys:
            node_data = presets[name]
            preset_item = QTreeWidgetItem([f"📂 {name}"])
            preset_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            
            expand_key = f"{tag_type}|PRESET:{name}"
            preset_item.setData(0, Qt.ItemDataRole.UserRole + 2, expand_key)
            if expand_key in self.saved_expanded:
                preset_item.setExpanded(True)
                
            root.addChild(preset_item)
            self._add_children_recursive(preset_item, node_data, tag_type, expand_key)

    def _add_children_recursive(self, parent_item, node_data, tag_type, parent_key_path):
        children = node_data.get("children", [])
        
        for ch in children:
            if ch.get("type") == "folder":
                fname = ch.get('name', '')
                item = QTreeWidgetItem([f"📁 {fname}"])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                
                expand_key = f"{parent_key_path}|{fname}"
                item.setData(0, Qt.ItemDataRole.UserRole + 2, expand_key)
                parent_item.addChild(item)
                if expand_key in self.saved_expanded:
                    item.setExpanded(True)
                
                self._add_children_recursive(item, ch, tag_type, expand_key)
                
            elif ch.get("type") == "tag":
                tag_val = ch.get("value", "")
                item = QTreeWidgetItem([f"🏷 {tag_val}"])
                
                item.setData(0, Qt.ItemDataRole.UserRole, tag_val) 
                item.setData(0, Qt.ItemDataRole.UserRole + 1, tag_type)
                
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                
                state_key = f"{tag_type}|{tag_val}"
                if state_key in self.saved_checked:
                    item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                
                parent_item.addChild(item)

    def _on_item_changed(self, item, column):
        self._refresh_summary()

    def _on_item_expanded(self, item):
        key = item.data(0, Qt.ItemDataRole.UserRole + 2)
        if key: self.saved_expanded.add(key)

    def _on_item_collapsed(self, item):
        key = item.data(0, Qt.ItemDataRole.UserRole + 2)
        if key and key in self.saved_expanded:
            self.saved_expanded.remove(key)

    def _refresh_summary(self):
        count = 0
        preview_text = []
        
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            tag = item.data(0, Qt.ItemDataRole.UserRole)
            if tag:
                count += 1
                if count <= 5: 
                    preview_text.append(tag)
            iterator += 1
            
        self.lbl_summary_count.setText(f"Выбрано: {count}")
        
        if count == 0:
            self.lbl_summary_text.setText("Ничего не выбрано")
            self.lbl_summary_text.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-style: italic; font-size: 10px;")
        else:
            txt = ", ".join(preview_text)
            if count > 5: txt += f" ... и еще {count - 5}"
            self.lbl_summary_text.setText(txt)
            self.lbl_summary_text.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 10px;")

    def _clear_all_checks(self):
        self.tree.blockSignals(True)
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            item.setCheckState(0, Qt.CheckState.Unchecked)
            iterator += 1
        self.tree.blockSignals(False)
        self._refresh_summary()

    def done(self, result):
        """
        Переопределяем закрытие диалога.
        Используем рекурсивный обход вместо итератора, чтобы гарантированно 
        сохранить состояние ВСЕХ элементов (даже скрытых внутри свернутых папок).
        """
        self.final_checked_state = set()
        self.final_expanded_state = set()

        def _traverse(item):
            # 1. Сохраняем РАСКРЫТИЕ
            # Важно: проверяем isExpanded(), даже если родитель свернут.
            if item.isExpanded():
                key = item.data(0, Qt.ItemDataRole.UserRole + 2)
                if key:
                    self.final_expanded_state.add(key)

            # 2. Сохраняем ГАЛОЧКИ
            if item.checkState(0) == Qt.CheckState.Checked:
                tag = item.data(0, Qt.ItemDataRole.UserRole)
                t_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
                if tag and t_type:
                    self.final_checked_state.add(f"{t_type}|{tag}")
            
            # 3. Рекурсивно идем вглубь
            for i in range(item.childCount()):
                _traverse(item.child(i))

        # Запускаем обход для всех корневых элементов
        for i in range(self.tree.topLevelItemCount()):
            _traverse(self.tree.topLevelItem(i))
            
        super().done(result)

    def get_state(self):
        """
        Возвращает сохраненное состояние. 
        Безопасно вызывать после закрытия окна.
        """
        # Если окно закрыли до инициализации (теоретически), возвращаем пустые/исходные наборы
        if not hasattr(self, 'final_checked_state'):
            return self.saved_checked, self.saved_expanded
            
        return self.final_checked_state, self.final_expanded_state

    def _collect_final_state(self):
        s_tags = []
        i_tags = []
        new_checked = set()
        
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            tag = item.data(0, Qt.ItemDataRole.UserRole)
            t_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            
            if tag and t_type:
                if t_type == 'search': s_tags.append(tag)
                elif t_type == 'ignore': i_tags.append(tag)
                new_checked.add(f"{t_type}|{tag}")
            iterator += 1
            
        self.selected_search_tags = list(set(s_tags))
        self.selected_ignore_tags = list(set(i_tags))
        self.new_checked_state = new_checked

    def _on_apply_current(self):
        self._collect_final_state()
        self._clear_all_checks()
        self.action_type = 'apply_curr'
        self.accept()

    def _on_apply_new(self):
        self._collect_final_state()
        self._clear_all_checks()
        self.action_type = 'apply_new'
        self.accept()
        
    def _on_manage(self, mode):
        self._collect_final_state()
        if mode == 'search': self.action_type = 'manage_search'
        else: self.action_type = 'manage_ignore'
        self.accept()

class SearchWidget(QWidget):
    tags_changed = pyqtSignal(list)
    ignore_tags_changed = pyqtSignal(list)
    scan_categories_requested = pyqtSignal(list)
    categories_selected = pyqtSignal(list)
    categories_changed = pyqtSignal()
    
    # --- ИЗМЕНЕНИЕ: Сигнал теперь передает (search_tags, ignore_tags)
    apply_tags_to_new_queue_requested = pyqtSignal(list, list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        from app.ui.windows.controls_widget import SearchModeWidget
        self.search_mode_widget = SearchModeWidget()
        self.cached_scanned_categories: List[dict] = []
        self.cached_forced_categories: List[str] = []
        
        self.tag_presets: Dict[str, dict] = {}
        self.ignore_tag_presets: Dict[str, dict] = {}
        
        self.presets_checked_state: Set[str] = set()
        self.presets_expanded_state: Set[str] = {"ROOT:search", "ROOT:ignore"}
        
        self._current_category_count = 1
        self._load_tag_presets()
        self._load_ignore_tag_presets()
        self._init_ui()
        self._connect_signals()
        self._emit_categories_changed()
    
    def _init_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(Spacing.GAP_NORMAL)
        main_panel = QFrame()
        main_panel.setStyleSheet(Components.panel())
        main_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main_panel.setMinimumHeight(200)
        panel_layout = QVBoxLayout(main_panel)
        panel_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        panel_layout.setSpacing(Spacing.GAP_NORMAL)
        title = QLabel("КЛЮЧЕВЫЕ СЛОВА")
        title.setStyleSheet(Components.section_title())
        panel_layout.addWidget(title)
        tags_area = QHBoxLayout()
        tags_area.setSpacing(Spacing.GAP_NORMAL)
        self.search_group = self._create_search_group()
        tags_area.addWidget(self.search_group, stretch=1)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"background-color: {Palette.DIVIDER}; width: 1px;")
        tags_area.addWidget(sep)
        self.ignore_group = self._create_ignore_group()
        tags_area.addWidget(self.ignore_group, stretch=1)
        panel_layout.addLayout(tags_area)
        root_layout.addWidget(main_panel, stretch=1)
        self.right_placeholder = QWidget()
        self.right_placeholder.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.right_layout = QVBoxLayout(self.right_placeholder)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)
        root_layout.addWidget(self.right_placeholder, stretch=1)

    def attach_ai_stats(self, stats_panel: QWidget):
        while self.right_layout.count():
            child = self.right_layout.takeAt(0)
            if child.widget(): child.widget().setParent(None)
        self.right_layout.addWidget(stats_panel)

    def _create_search_group(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        def validate_search(text: str) -> bool:
            if text in self.ignore_tags_input.get_tags():
                self._show_tooltip(self.search_tags_input, f"'{text}' уже в игнор-листе!")
                return False
            return True
        self.search_tags_input = TagsInput(title="ИЩЕМ", tag_color=Palette.TERTIARY, validator=validate_search)
        self.search_tags_input.setMinimumHeight(120)
        toolbar = self.search_tags_input.header_layout
        self.btn_scan = self._create_tool_btn("🔍", "Сканировать категории")
        self.btn_cats = self._create_tool_btn("≡", "Выбрать категории (из кэша)")
        self.btn_presets = self._create_tool_btn("★", "Пресеты поиска")
        self.btn_clear_search = self._create_tool_btn("✖", "Очистить")
        toolbar.addStretch()
        toolbar.addWidget(self.btn_scan)
        toolbar.addWidget(self.btn_cats)
        toolbar.addWidget(self.btn_presets)
        toolbar.addWidget(self.btn_clear_search)
        layout.addWidget(self.search_tags_input)
        return container

    def _create_ignore_group(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        def validate_ignore(text: str) -> bool:
            if text in self.search_tags_input.get_tags():
                self._show_tooltip(self.ignore_tags_input, f"'{text}' уже в списке поиска!")
                return False
            return True
        self.ignore_tags_input = TagsInput(title="ИСКЛЮЧАЕМ", tag_color=Palette.ERROR, validator=validate_ignore)
        self.ignore_tags_input.setMinimumHeight(120)
        toolbar = self.ignore_tags_input.header_layout
        self.btn_presets_ignore = self._create_tool_btn("★", "Пресеты игнора")
        self.btn_clear_ignore = self._create_tool_btn("✖", "Очистить")
        toolbar.addStretch()
        toolbar.addWidget(self.btn_presets_ignore)
        toolbar.addWidget(self.btn_clear_ignore)
        layout.addWidget(self.ignore_tags_input)
        return container

    def _create_tool_btn(self, text, tooltip):
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(Components.small_button())
        return btn

    def _show_tooltip(self, widget, text):
        QMessageBox.warning(self, "Конфликт тегов", text)

    def _connect_signals(self):
        self.btn_scan.clicked.connect(self._on_scan_categories)
        self.btn_cats.clicked.connect(self._on_view_categories)
        self.btn_presets.clicked.connect(self._on_tag_presets_clicked)
        self.btn_clear_search.clicked.connect(self.search_tags_input.clear_tags)
        self.btn_presets_ignore.clicked.connect(self._on_ignore_tag_presets_clicked)
        self.btn_clear_ignore.clicked.connect(self.ignore_tags_input.clear_tags)
        self.search_tags_input.tags_changed.connect(self._on_search_tags_changed)
        self.search_tags_input.tags_changed.connect(lambda t: self.tags_changed.emit(t))
        self.ignore_tags_input.tags_changed.connect(lambda t: self.ignore_tags_changed.emit(t))

    def _on_search_tags_changed(self, tags):
        if self.cached_scanned_categories or self.cached_forced_categories:
            self.cached_scanned_categories = []
            self.cached_forced_categories = []
            self._emit_categories_changed()
        self.tags_changed.emit(tags)

    def _on_scan_categories(self):
        tags = self.get_search_tags()
        if not tags:
            QMessageBox.warning(self, "Ошибка", "Введите теги для сканирования!")
            return
        self.cached_scanned_categories = []
        self.cached_forced_categories = []
        self.scan_categories_requested.emit(tags)

    def _on_view_categories(self):
        if not self.cached_scanned_categories:
            QMessageBox.information(self, "Информация", "Сначала выполните сканирование.")
            return

        dlg = CategorySelectionDialog(
            self.cached_scanned_categories, 
            self, 
            selected_categories=self.cached_forced_categories,
            on_clear=self._clear_categories_cache
        )
        if dlg.exec():
            selected = dlg.get_selected()
            if selected != self.cached_forced_categories:
                self.cached_forced_categories = selected
                self.categories_selected.emit(selected)
                self._emit_categories_changed()

    def _clear_categories_cache(self):
        self.cached_scanned_categories = []
        self.cached_forced_categories = []
        self._emit_categories_changed()

    def get_scanned_categories(self) -> List[dict]:
        return self.cached_scanned_categories

    def set_scanned_categories(self, categories: List[dict]):
        self.cached_scanned_categories = categories
        best_choice = None
        for cat in categories:
            if cat.get('type') == 'ГЛАВНАЯ':
                best_choice = cat.get('text')
                break
        if not best_choice and categories:
            best_choice = categories[0].get('text')
        if best_choice:
            self.cached_forced_categories = [best_choice]
        else:
            self.cached_forced_categories = []
        self._emit_categories_changed()

    def get_forced_categories(self) -> List[str]: return self.cached_forced_categories
    def set_forced_categories(self, categories: List[str]):
        if categories != self.cached_forced_categories:
            self.cached_forced_categories = categories
            self._emit_categories_changed()

    def _emit_categories_changed(self):
        count = len(self.cached_forced_categories) if self.cached_forced_categories else 1
        self._current_category_count = count
        self.categories_changed.emit()

    def get_category_count(self) -> int:
        return self._current_category_count
    
    def _on_tag_presets_clicked(self):
        self._show_presets_popup(self.btn_presets, primary_is_ignore=False)

    def _on_ignore_tag_presets_clicked(self):
        self._show_presets_popup(self.btn_presets_ignore, primary_is_ignore=True)

    def _show_presets_popup(self, btn, primary_is_ignore: bool):
        # (код выбора словарей остается прежним...)
        if primary_is_ignore:
            presets_dict = self.ignore_tag_presets
            target_input = self.ignore_tags_input
        else:
            presets_dict = self.tag_presets
            target_input = self.search_tags_input

        popup = PresetsSelectPopup(
            parent=self, 
            search_presets=self.tag_presets,
            ignore_presets=self.ignore_tag_presets,
            saved_checked=self.presets_checked_state,   
            saved_expanded=self.presets_expanded_state,
            primary_is_ignore=primary_is_ignore
        )
        
        global_pos = btn.mapToGlobal(QPoint(0, btn.height()))
        popup.move(global_pos)
        
        # 1. Запускаем диалог
        res = popup.exec()
        
        # 2. ИЗМЕНЕНИЕ: ВСЕГДА сохраняем состояние (галочки и папки),
        # даже если кликнули мимо (Rejected) или нажали Отмена.
        new_checked, new_expanded = popup.get_state()
        self.presets_checked_state = new_checked
        self.presets_expanded_state = new_expanded
        
        # 3. Обрабатываем действия только если была нажата кнопка (Accepted)
        if res == QDialog.DialogCode.Accepted:
            action = popup.action_type
            s_tags = popup.selected_search_tags
            i_tags = popup.selected_ignore_tags
            
            if action == 'manage_search':
                self._open_tag_presets_editor()
            elif action == 'manage_ignore':
                self._open_ignore_tag_presets_editor()
            
            elif action == 'apply_curr':
                # Логика применения в текущую очередь
                if s_tags:
                    curr_s = self.search_tags_input.get_tags()
                    self.search_tags_input.set_tags(list(set(curr_s + s_tags)))
                
                if i_tags:
                    curr_i = self.ignore_tags_input.get_tags()
                    self.ignore_tags_input.set_tags(list(set(curr_i + i_tags)))
                    
            elif action == 'apply_new':
                # Логика применения в новую очередь
                if not s_tags and not i_tags:
                    QMessageBox.warning(self, "Пусто", "Выберите хотя бы один тег!")
                    return
                self.apply_tags_to_new_queue_requested.emit(s_tags, i_tags)

    def _open_tag_presets_editor(self):
        dlg = TagPresetsDialog(self.tag_presets, self, window_title="Пресеты поиска", tag_color=Palette.TERTIARY)
        if dlg.exec():
            self.tag_presets = dlg.get_presets()
            self._save_tag_presets()

    def _open_ignore_tag_presets_editor(self):
        dlg = TagPresetsDialog(self.ignore_tag_presets, self, window_title="Пресеты игнора", tag_color=Palette.ERROR)
        if dlg.exec():
            self.ignore_tag_presets = dlg.get_presets()
            self._save_ignore_tag_presets()

    def _presets_file_path(self): return os.path.join(BASE_APP_DIR, "tag_presets.json")
    def _ignore_presets_file_path(self): return os.path.join(BASE_APP_DIR, "tag_presets_ignore.json")
    def _categories_cache_path(self): return os.path.join(BASE_APP_DIR, "categories_cache.json")
    def _load_tag_presets(self):
        raw = self._load_json(self._presets_file_path())
        self.tag_presets = self._normalize_presets_dict(raw)

    def _load_ignore_tag_presets(self):
        raw = self._load_json(self._ignore_presets_file_path())
        self.ignore_tag_presets = self._normalize_presets_dict(raw)
    def _save_tag_presets(self): self._save_json(self._presets_file_path(), self.tag_presets)
    def _save_ignore_tag_presets(self): self._save_json(self._ignore_presets_file_path(), self.ignore_tag_presets)
    def get_search_tags(self) -> List[str]: return self.search_tags_input.get_tags()
    def set_search_tags(self, tags: List[str]): self.search_tags_input.set_tags(tags); self._emit_categories_changed()
    def get_ignore_tags(self) -> List[str]: return self.ignore_tags_input.get_tags()
    def set_ignore_tags(self, tags: List[str]): self.ignore_tags_input.set_tags(tags)
    
    def _is_tag_node(self, n) -> bool:
        return isinstance(n, dict) and n.get("type") == "tag"

    def _is_folder_node(self, n) -> bool:
        return isinstance(n, dict) and n.get("type") == "folder"

    def _make_folder(self, name: str, children=None) -> dict:
        return {"type": "folder", "name": name, "children": list(children or [])}

    def _make_tag(self, value: str) -> dict:
        return {"type": "tag", "value": value}

    def _normalize_preset_value_to_root_folder(self, v) -> dict:
        if isinstance(v, list):
            children = []
            for t in v:
                t = str(t).strip()
                if t:
                    children.append(self._make_tag(t))
            return self._make_folder("ROOT", children)

        if self._is_folder_node(v):
            name = str(v.get("name") or "ROOT")
            children = v.get("children") if isinstance(v.get("children"), list) else []
            norm_children = []
            for c in children:
                if self._is_tag_node(c):
                    val = str(c.get("value") or "").strip()
                    if val:
                        norm_children.append(self._make_tag(val))
                elif self._is_folder_node(c):
                    norm_children.append(self._normalize_preset_value_to_root_folder(c))
            return self._make_folder(name if name else "ROOT", norm_children)

        return self._make_folder("ROOT", [])

    def _normalize_presets_dict(self, d: dict) -> dict:
        out = {}
        if not isinstance(d, dict):
            return out
        for k, v in d.items():
            name = str(k).strip()
            if not name:
                continue
            out[name] = self._normalize_preset_value_to_root_folder(v)
        return out

    def _collect_tags_recursive(self, folder_node: dict) -> List[str]:
        out: List[str] = []
        for ch in (folder_node.get("children") or []):
            if self._is_tag_node(ch):
                val = str(ch.get("value") or "").strip()
                if val:
                    out.append(val)
            elif self._is_folder_node(ch):
                out.extend(self._collect_tags_recursive(ch))
        return out

    def _collect_root_only_tags(self, root_folder: dict) -> List[str]:
        out: List[str] = []
        for ch in (root_folder.get("children") or []):
            if self._is_tag_node(ch):
                val = str(ch.get("value") or "").strip()
                if val:
                    out.append(val)
        return out

    def _collect_folder_only_tags(self, folder_node: dict) -> List[str]:
        out: List[str] = []
        for ch in (folder_node.get("children") or []):
            if self._is_tag_node(ch):
                val = str(ch.get("value") or "").strip()
                if val:
                    out.append(val)
        return out

    def _has_root_tags(self, root_folder: dict) -> bool:
        return len(self._collect_root_only_tags(root_folder)) > 0
    
    def _load_json(self, path) -> dict:
        if not os.path.exists(path): return {}
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    def _save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass