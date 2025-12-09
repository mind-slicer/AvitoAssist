import os
import json
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QPushButton, QMessageBox, QSizePolicy, QFrame, QLabel, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.ui.widgets.tags import TagsInput
from app.ui.widgets.category_selection_dialog import CategorySelectionDialog
from app.ui.widgets.tag_presets_dialog import TagPresetsDialog
from app.ui.styles import Components, Palette, Spacing, Typography
from app.config import BASE_APP_DIR

class SearchWidget(QWidget):
    tags_changed = pyqtSignal(list)
    ignore_tags_changed = pyqtSignal(list)
    scan_categories_requested = pyqtSignal(list)
    categories_selected = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        from app.ui.windows.controls_widget import SearchModeWidget
        self.search_mode_widget = SearchModeWidget()
        self.cached_scanned_categories: List[str] = []
        self.cached_forced_categories: List[str] = []
        self.tag_presets: Dict[str, List[str]] = {}
        self.ignore_tag_presets: Dict[str, List[str]] = {}
        self._load_tag_presets()
        self._load_ignore_tag_presets()
        self._load_categories_cache()
        self._init_ui()
        self._connect_signals()
    
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
        self.cached_scanned_categories = []
        self.cached_forced_categories = []
        self._save_categories_cache()
        self.tags_changed.emit(tags)

    def _on_scan_categories(self):
        tags = self.get_search_tags()
        if not tags:
            QMessageBox.warning(self, "Ошибка", "Введите теги для сканирования!")
            return
        self.scan_categories_requested.emit(tags)

    def _on_view_categories(self):
        if not self.cached_scanned_categories:
            QMessageBox.information(self, "Информация", "Сначала выполните сканирование.")
            return

        dlg = CategorySelectionDialog(
            self.cached_scanned_categories, 
            self, 
            selected_categories=self.cached_forced_categories
        )
        if dlg.exec():
            selected = dlg.get_selected()
            self.cached_forced_categories = selected
            self._save_categories_cache()
            self.categories_selected.emit(selected)

    def set_scanned_categories(self, categories: List[str]):
        self.cached_scanned_categories = categories
        self._save_categories_cache()

    def get_forced_categories(self) -> List[str]: return self.cached_forced_categories
    def set_forced_categories(self, categories: List[str]):
        self.cached_forced_categories = categories
        self._save_categories_cache()

    def _on_tag_presets_clicked(self):
        self._show_presets_menu(self.btn_presets, self.tag_presets, self.search_tags_input, is_ignore=False)

    def _on_ignore_tag_presets_clicked(self):
        self._show_presets_menu(self.btn_presets_ignore, self.ignore_tag_presets, self.ignore_tags_input, is_ignore=True)

    def _show_presets_menu(self, btn, presets_dict, input_widget, is_ignore):
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background-color: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; }}")
        for name in sorted(presets_dict.keys()):
            action = menu.addAction(f"📂 {name}")
            action.setData(name)
        if presets_dict: menu.addSeparator()
        act_manage = menu.addAction("⚙ Управление пресетами...")
        selected_action = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        
        if not selected_action: return
        if selected_action == act_manage:
            if is_ignore: self._open_ignore_tag_presets_editor()
            else: self._open_tag_presets_editor()
        else:
            name = selected_action.data()
            tags = presets_dict.get(name, [])
            input_widget.set_tags(tags)

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
    def _load_tag_presets(self): self.tag_presets = self._load_json(self._presets_file_path())
    def _load_ignore_tag_presets(self): self.ignore_tag_presets = self._load_json(self._ignore_presets_file_path())
    def _save_tag_presets(self): self._save_json(self._presets_file_path(), self.tag_presets)
    def _save_ignore_tag_presets(self): self._save_json(self._ignore_presets_file_path(), self.ignore_tag_presets)
    def _load_categories_cache(self):
        data = self._load_json(self._categories_cache_path())
        self.cached_scanned_categories = data.get("categories", [])
        self.cached_forced_categories = data.get("forced_selection", [])
    def _save_categories_cache(self):
        data = {"categories": self.cached_scanned_categories, "forced_selection": self.cached_forced_categories}
        self._save_json(self._categories_cache_path(), data)
    def _load_json(self, path) -> dict:
        if not os.path.exists(path): return {}
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    def _save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def get_search_tags(self) -> List[str]: return self.search_tags_input.get_tags()
    def set_search_tags(self, tags: List[str]): self.search_tags_input.set_tags(tags)
    def get_ignore_tags(self) -> List[str]: return self.ignore_tags_input.get_tags()
    def set_ignore_tags(self, tags: List[str]): self.ignore_tags_input.set_tags(tags)