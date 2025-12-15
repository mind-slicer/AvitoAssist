import os
import json
from typing import List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox,
    QSizePolicy, QFrame, QLabel, QMenu, QWidgetAction
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.ui.widgets.tags import TagsInput
from app.ui.widgets.category_selection_dialog import CategorySelectionDialog
from app.ui.widgets.tag_presets_dialog import TagPresetsDialog
from app.ui.styles import Components, Palette, Spacing
from app.config import BASE_APP_DIR

class SearchWidget(QWidget):
    tags_changed = pyqtSignal(list)
    ignore_tags_changed = pyqtSignal(list)
    scan_categories_requested = pyqtSignal(list)
    categories_selected = pyqtSignal(list)
    categories_changed = pyqtSignal()
    apply_tags_to_new_queue_requested = pyqtSignal(list, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        from app.ui.windows.controls_widget import SearchModeWidget
        self.search_mode_widget = SearchModeWidget()
        self.cached_scanned_categories: List[dict] = [] # Теперь точно List[dict]
        self.cached_forced_categories: List[str] = []
        self.tag_presets: Dict[str, dict] = {}
        self.ignore_tag_presets: Dict[str, dict] = {}
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

    def set_scanned_categories(self, categories: List[dict]):
        """
        Принимает список словарей категорий и автоматически выбирает одну 'ГЛАВНУЮ' (или первую).
        """
        self.cached_scanned_categories = categories
        
        # Умный выбор дефолтной категории
        best_choice = None
        
        # 1. Ищем помеченную как ГЛАВНАЯ
        for cat in categories:
            if cat.get('type') == 'ГЛАВНАЯ':
                best_choice = cat.get('text')
                break
        
        # 2. Если нет, берем первую попавшуюся
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
        self._show_cross_presets_menu(self.btn_presets, primary_is_ignore=False)

    def _on_ignore_tag_presets_clicked(self):
        self._show_cross_presets_menu(self.btn_presets_ignore, primary_is_ignore=True)

    def _show_cross_presets_menu(self, btn, primary_is_ignore: bool):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; }}"
        )

        action_payload = {}

        def _safe_add_single_tag(tag: str, target_input, target_is_ignore: bool):
            tag = str(tag or "").strip()
            if not tag:
                return

            # конфликт между полями (как в твоих validator’ах, но для клика из меню)
            other_input = self.search_tags_input if target_is_ignore else self.ignore_tags_input
            if tag in (other_input.get_tags() or []):
                self._show_tooltip(target_input, f"'{tag}' уже в соседнем поле!")
                return

            cur = target_input.get_tags() or []
            if tag in cur:
                return

            target_input.set_tags(cur + [tag])

        def _add_disabled_line(m: QMenu, text: str):
            a = m.addAction(text)
            a.setEnabled(False)
            return a

        def _add_folder_preview(m: QMenu, folder_node: dict, target_input, target_is_ignore: bool):
            folder_tags = self._collect_folder_only_tags(folder_node)  # только текущая папка
            m.addSeparator()

            if not folder_tags:
                _add_disabled_line(m, " (нет тегов в папке)")
                m.addSeparator()
                return

            max_show = 10
            for t in folder_tags[:max_show]:
                wa = QWidgetAction(m)
                btn = QPushButton(f"🏷 {t}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFlat(True)
                btn.setStyleSheet(
                    f"QPushButton {{ color: {Palette.TEXT}; background: transparent; padding: 4px 8px; text-align: left; }}"
                    f"QPushButton:hover {{ background-color: {Palette.BG_DARK_3}; }}"
                )
                btn.clicked.connect(lambda _, tag=t: _safe_add_single_tag(tag, target_input, target_is_ignore))
                wa.setDefaultWidget(btn)
                m.addAction(wa)

            if len(folder_tags) > max_show:
                _add_disabled_line(m, f"… ещё {len(folder_tags) - max_show}")

            m.addSeparator()

        def _add_section(
            *,
            title: str,
            presets_dict: dict,
            target_input,
            target_is_ignore: bool,
        ):
            _add_disabled_line(menu, f"── {title} ──")

            def add_folder_submenu(parent_menu: QMenu, preset_name: str, folder_node: dict):
                for ch in (folder_node.get("children") or []):
                    if self._is_folder_node(ch):
                        sub = parent_menu.addMenu(f"📁 {ch.get('name', '')}")

                        act_apply_folder = sub.addAction("✅ Применить папку")
                        act_apply_folder_newq = sub.addAction("➕ Применить папку к новой очереди")

                        action_payload[act_apply_folder] = ("folder", preset_name, ch, target_input, target_is_ignore)
                        action_payload[act_apply_folder_newq] = ("folder_new_queue", preset_name, ch, target_input, target_is_ignore)

                        _add_folder_preview(sub, ch, target_input, target_is_ignore)
                        add_folder_submenu(sub, preset_name, ch)

            # Корни наборов
            for preset_name in sorted((presets_dict or {}).keys()):
                root = self._normalize_preset_value_to_root_folder(presets_dict.get(preset_name))

                act_root = menu.addAction(f"📂 {preset_name}")
                action_payload[act_root] = ("root", preset_name, None, target_input, target_is_ignore)

                if not self._has_root_tags(root):
                    _add_disabled_line(menu, " (нет тегов в корне)")

                # Папки 1-го уровня (как у тебя было)
                for ch in (root.get("children") or []):
                    if self._is_folder_node(ch):
                        sub = menu.addMenu(f" 📁 {preset_name} / {ch.get('name', '')}")

                        act_apply_folder = sub.addAction("✅ Применить папку")
                        act_apply_folder_newq = sub.addAction("➕ Применить папку к новой очереди")

                        action_payload[act_apply_folder] = ("folder", preset_name, ch, target_input, target_is_ignore)
                        action_payload[act_apply_folder_newq] = ("folder_new_queue", preset_name, ch, target_input, target_is_ignore)

                        _add_folder_preview(sub, ch, target_input, target_is_ignore)
                        add_folder_submenu(sub, preset_name, ch)

            # Управление пресетами именно этой секции
            if not (presets_dict or {}):
                _add_disabled_line(menu, " (нет наборов)")
            
            menu.addSeparator()
            manage_text = "⚙ Управление пресетами фильтра..." if target_is_ignore else "⚙ Управление пресетами поиска..."
            act_manage = menu.addAction(manage_text)
            action_payload[act_manage] = ("manage", None, None, None, target_is_ignore)
            menu.addSeparator()

        own_suffix = " → применить к этому полю"
        other_suffix = " → применить к соседнему полю"

        # Порядок секций: сначала та, по которой кликнули, потом соседняя
        if not primary_is_ignore:
            _add_section(title="ИЩЕМ" + own_suffix, presets_dict=self.tag_presets,
                         target_input=self.search_tags_input, target_is_ignore=False)
            _add_section(title="ИСКЛЮЧАЕМ" + other_suffix, presets_dict=self.ignore_tag_presets,
                         target_input=self.ignore_tags_input, target_is_ignore=True)
        else:
            _add_section(title="ИСКЛЮЧАЕМ" + own_suffix, presets_dict=self.ignore_tag_presets,
                         target_input=self.ignore_tags_input, target_is_ignore=True)
            _add_section(title="ИЩЕМ" + other_suffix, presets_dict=self.tag_presets,
                         target_input=self.search_tags_input, target_is_ignore=False)

        selected_action = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if not selected_action:
            return

        payload = action_payload.get(selected_action)
        if not payload:
            return

        kind, preset_name, folder_node, target_input, target_is_ignore = payload

        if kind == "manage":
            if target_is_ignore:
                self._open_ignore_tag_presets_editor()
            else:
                self._open_tag_presets_editor()
            return

        if kind == "root":
            root = self._normalize_preset_value_to_root_folder(
                (self.ignore_tag_presets if target_is_ignore else self.tag_presets).get(preset_name)
            )
            tags = self._collect_root_only_tags(root)
            if tags:
                target_input.set_tags(tags)
            return

        if kind == "folder":
            tags = self._collect_tags_recursive(folder_node)
            if tags:
                target_input.set_tags(tags)
            return

        if kind == "folder_new_queue":
            tags = self._collect_tags_recursive(folder_node)
            if tags:
                self.apply_tags_to_new_queue_requested.emit(tags, target_is_ignore)
            return

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