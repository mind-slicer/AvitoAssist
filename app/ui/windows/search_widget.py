import os
import json
from typing import List, Dict, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox,
    QSizePolicy, QFrame, QLabel, QDialog, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QTreeWidgetItemIterator, QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QColor

from app.ui.widgets.tags import TagsInput
from app.ui.widgets.category_selection_dialog import CategorySelectionDialog
from app.ui.widgets.tag_presets_dialog import TagPresetsDialog
from app.ui.styles import Components, Palette, Spacing
from app.ui.windows.controls_widget import SearchParametersPanel
from app.config import BASE_APP_DIR


class TagSettingsDialog(QDialog):
    def __init__(self, tag_value: str, current_params: dict, parent=None):
        super().__init__(parent)
        self.tag_value = tag_value
        self.setWindowTitle(f"Настройки тега: {tag_value}")
        self.resize(1000, 650)
        self.setStyleSheet(Components.dialog())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        header = QFrame()
        header.setStyleSheet(f"background: {Palette.BG_DARK_2}; border-bottom: 1px solid {Palette.BORDER_SOFT};")
        h_layout = QHBoxLayout(header)
        title = QLabel(f"Параметры для: <span style='color:{Palette.PRIMARY}'>{tag_value}</span>")
        title.setStyleSheet(Components.section_title())
        h_layout.addWidget(title)
        layout.addWidget(header)

        self.params_panel = SearchParametersPanel()
        if current_params:
            self.params_panel.set_parameters(current_params)
        
        layout.addWidget(self.params_panel)

        footer = QHBoxLayout()
        footer.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet(Components.stop_button())
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("Сохранить")
        btn_save.setStyleSheet(Components.start_button())
        btn_save.clicked.connect(self.accept)
        
        footer.addStretch()
        footer.addWidget(btn_cancel)
        footer.addWidget(btn_save)
        layout.addLayout(footer)

    def get_params(self):
        return self.params_panel.get_parameters()
    

class PresetsSelectPopup(QDialog):
    def __init__(self, parent, 
                 search_presets: dict, 
                 ignore_presets: dict, 
                 saved_checked: Set[str], 
                 saved_expanded: Set[str],
                 primary_is_ignore: bool):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self.saved_checked = set(saved_checked)
        self.saved_expanded = set(saved_expanded)
        self.primary_is_ignore = primary_is_ignore
        
        self.indicators_map = {} 
        self.current_editing_node = None
        self.current_editing_item = None
        
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Palette.BG_DARK};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {Palette.TEXT};
                outline: none;
            }}
            QTreeWidget::item {{ 
                padding: 2px; 
                border-bottom: 1px solid transparent;
            }}
            QTreeWidget::item:hover {{ background-color: {Palette.BG_DARK_3}; }}
            QTreeWidget::item:selected {{ 
                background-color: {Palette.with_alpha(Palette.PRIMARY, 0.1)}; 
                color: {Palette.TEXT}; 
                border-bottom: 1px solid {Palette.with_alpha(Palette.PRIMARY, 0.3)};
            }}
            QLabel {{ color: {Palette.TEXT_MUTED}; }}
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.left_container = QWidget()
        self.left_container.setFixedWidth(450)
        left_layout = QVBoxLayout(self.left_container)
        left_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        left_layout.setSpacing(Spacing.SM)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        
        lbl = QLabel("ПРЕСЕТЫ")
        lbl.setStyleSheet(Components.section_title())
        
        manage_text = "⚙ Редактировать"
        manage_mode = 'ignore' if primary_is_ignore else 'search'
        
        btn_manage = QPushButton(manage_text)
        btn_manage.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_manage.setStyleSheet(f"border: none; color: {Palette.PRIMARY}; font-size: 12px; font-weight: bold; text-align: right;")
        btn_manage.clicked.connect(lambda: self._on_manage(manage_mode))
        
        header_layout.addWidget(lbl)
        header_layout.addStretch()
        header_layout.addWidget(btn_manage)
        left_layout.addLayout(header_layout)
        
        # ДЕРЕВО
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setIndentation(15) 
        
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, 65) 
        
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        left_layout.addWidget(self.tree)
        
        if primary_is_ignore:
            self._add_root_section("ИСКЛЮЧАЕМ", ignore_presets, "ignore")
            self._add_root_section("ИЩЕМ", search_presets, "search")
        else:
            self._add_root_section("ИЩЕМ", search_presets, "search")
            self._add_root_section("ИСКЛЮЧАЕМ", ignore_presets, "ignore")

        # ЗОНА ПРЕДПРОСМОТРА
        summary_container = QFrame()
        summary_container.setStyleSheet(f"background-color: {Palette.BG_DARK_3}; border-radius: 4px; border: 1px solid {Palette.BORDER_PRIMARY};")
        summary_layout = QVBoxLayout(summary_container)
        summary_layout.setContentsMargins(8, 8, 8, 8)
        summary_layout.setSpacing(4)
        
        sum_header = QHBoxLayout()
        self.lbl_summary_count = QLabel("Выбрано: 0")
        self.lbl_summary_count.setStyleSheet("font-weight: bold; font-size: 11px; color: " + Palette.TEXT)
        
        btn_clear = QPushButton("Очистить всё")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setFixedSize(80, 20)
        btn_clear.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Palette.ERROR}; border: none; font-size: 11px; }}
            QPushButton:hover {{ text-decoration: underline; }}
        """)
        btn_clear.clicked.connect(self._clear_all_checks)
        
        sum_header.addWidget(self.lbl_summary_count)
        sum_header.addStretch()
        sum_header.addWidget(btn_clear)
        summary_layout.addLayout(sum_header)
        
        self.lbl_summary_text = QLabel("Нет тегов")
        self.lbl_summary_text.setWordWrap(True)
        self.lbl_summary_text.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_summary_text.setMaximumHeight(40)
        summary_layout.addWidget(self.lbl_summary_text)
        
        left_layout.addWidget(summary_container)

        # КНОПКИ ДЕЙСТВИЙ
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)
        
        self.btn_apply_curr = QPushButton("✅ Применить в текущую очередь")
        self.btn_apply_curr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_curr.setStyleSheet(self._btn_style(Palette.PRIMARY))
        self.btn_apply_curr.clicked.connect(self._on_apply_current)
        btn_layout.addWidget(self.btn_apply_curr)
        
        if not primary_is_ignore:
            self.btn_apply_new = QPushButton("➕ Применить в новую очередь")
            self.btn_apply_new.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_apply_new.setStyleSheet(self._btn_style(Palette.SECONDARY))
            self.btn_apply_new.clicked.connect(self._on_apply_new)
            btn_layout.addWidget(self.btn_apply_new)
            
        left_layout.addLayout(btn_layout)
        
        self.vertical_separator = QFrame()
        self.vertical_separator.setFrameShape(QFrame.Shape.VLine)
        self.vertical_separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.vertical_separator.setStyleSheet(f"background-color: {Palette.DIVIDER}; width: 1px;")
        self.vertical_separator.hide()  # Скрыт по умолчанию

        # --- ПРАВАЯ ЧАСТЬ (ПАНЕЛЬ НАСТРОЕК) ---
        self.right_container = QFrame()
        self.right_container.setStyleSheet(Components.panel())
        self.right_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.MD) 
        right_layout.setSpacing(Spacing.MD)
        
        # Header правой панели
        rh_layout = QHBoxLayout()
        rh_layout.setSpacing(10)
        
        self.tag_title_lbl = QLabel("ПАРАМЕТРЫ")
        self.tag_title_lbl.setStyleSheet(Components.section_title())
        rh_layout.addWidget(self.tag_title_lbl)
        
        rh_layout.addStretch()
        
        # 1. Кнопка "Применить" (Зеленая зона)
        self.btn_use_params = QPushButton("< Применить настройки к тегу")
        self.btn_use_params.setCheckable(True)
        self.btn_use_params.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_use_params.setFixedSize(220, 28)
        self.btn_use_params.clicked.connect(self._toggle_usage)
        rh_layout.addWidget(self.btn_use_params)
        
        # 2. Кнопка "Сбросить" (Желтая зона)
        self.btn_reset = QPushButton("Сбросить настройки")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setFixedSize(130, 28)
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Palette.WARNING};
                color: {Palette.WARNING}; border-radius: 4px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {Palette.with_alpha(Palette.WARNING, 0.1)}; }}
        """)
        self.btn_reset.clicked.connect(self._reset_params)
        rh_layout.addWidget(self.btn_reset)
        
        # 3. Кнопка закрытия
        btn_close_p = QPushButton("✕")
        btn_close_p.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_p.setFixedSize(28, 28)
        btn_close_p.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Palette.TEXT_MUTED}; border: none; font-size: 16px; }}
            QPushButton:hover {{ color: {Palette.TEXT}; }}
        """)
        btn_close_p.clicked.connect(self._toggle_right_panel)
        rh_layout.addWidget(btn_close_p)
        
        right_layout.addLayout(rh_layout)
        
        # Панель параметров
        self.params_panel = SearchParametersPanel()
        self.params_panel.set_tag_mode() 
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(Components.scroll_area())
        scroll.setWidget(self.params_panel)
        
        right_layout.addWidget(scroll)
        
        self.right_container.hide()
        
        main_layout.addWidget(self.left_container)
        main_layout.addWidget(self.vertical_separator)
        main_layout.addWidget(self.right_container)
        
        #self.resize(470, 700)
        self.resize(450, 700)
        
        self._refresh_summary() 

        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)

    def _btn_style(self, color):
        return f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {Palette.TEXT};
                padding: 10px;
                text-align: center;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Palette.with_alpha(color, 0.1)};
                color: {color};
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
                item.setData(0, Qt.ItemDataRole.UserRole + 3, ch) 

                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

                state_key = f"{tag_type}|{tag_val}"
                if state_key in self.saved_checked:
                    item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    item.setCheckState(0, Qt.CheckState.Unchecked)

                parent_item.addChild(item)
                
                if tag_type == "search":
                    # КОНТЕЙНЕР ДЛЯ ШЕСТЕРЕНКИ И ИНДИКАТОРА
                    widget = QWidget()
                    l = QHBoxLayout(widget)
                    l.setContentsMargins(0, 0, 0, 0)
                    l.setSpacing(6)
                    # Выравниваем ВПРАВО
                    l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    
                    # 1. Индикатор
                    indicator = QLabel()
                    indicator.setFixedSize(8, 8)
                    is_active = ch.get("use_params", False)
                    color = Palette.SUCCESS if is_active else Palette.TEXT_MUTED
                    indicator.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
                    l.addWidget(indicator)
                    self.indicators_map[id(ch)] = indicator 
                    
                    # 2. Шестеренка
                    btn_settings = QPushButton("⚙")
                    font = btn_settings.font()
                    font.setFamily("Segoe UI")
                    btn_settings.setFont(font)
                    btn_settings.setFixedSize(24, 24)
                    btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_settings.setToolTip("Настроить параметры поиска для этого тега")
                    
                    btn_settings.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent;
                            color: {Palette.TEXT_MUTED};
                            border: none;
                            padding-bottom: 10px;
                            font-size: 24;
                        }}
                        QPushButton:hover {{ color: {Palette.PRIMARY}; background-color: {Palette.BG_DARK_3}; border-radius: 4px; }}
                    """)
                    
                    btn_settings.clicked.connect(lambda checked, node=ch, val=tag_val, it=item, btn=btn_settings: self.on_gear_clicked(node, val, it, btn))
                    l.addWidget(btn_settings)
                    
                    # Отступ справа чтобы не прилипало к краю
                    l.addSpacing(4)
                    
                    self.tree.setItemWidget(item, 1, widget)

    def _update_use_params_btn_style(self, is_active: bool):
        if is_active:
            self.btn_use_params.setText("> Выключить настройки тега")
            self.btn_use_params.setChecked(True)
            self.btn_use_params.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.with_alpha(Palette.SUCCESS, 0.1)};
                    border: 1px solid {Palette.SUCCESS};
                    color: {Palette.SUCCESS};
                    border-radius: 4px; font-weight: bold; font-size: 11px;
                }}
                QPushButton:hover {{ background-color: {Palette.with_alpha(Palette.SUCCESS, 0.2)}; }}
            """)
        else:
            self.btn_use_params.setText("< Применить настройки к тегу")
            self.btn_use_params.setChecked(False)
            self.btn_use_params.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {Palette.TEXT_MUTED};
                    color: {Palette.TEXT_MUTED};
                    border-radius: 4px; font-size: 11px;
                }}
                QPushButton:hover {{ border-color: {Palette.TEXT}; color: {Palette.TEXT}; }}
            """)

    def _toggle_usage(self):
        if not self.current_editing_node: return
        
        is_active = self.btn_use_params.isChecked()
        self.current_editing_node["use_params"] = is_active
        
        if self.current_editing_item:
            self.current_editing_item.setData(0, Qt.ItemDataRole.UserRole + 3, self.current_editing_node)

        indicator = self.indicators_map.get(id(self.current_editing_node))
        if indicator:
            color = Palette.SUCCESS if is_active else Palette.TEXT_MUTED
            indicator.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        
        self._update_use_params_btn_style(is_active)
        self._save_tag_presets_request()

    def _reset_params(self):
        if not self.current_editing_node: return
        self.params_panel.set_parameters({}) 
        self.current_editing_node["params"] = self.params_panel.get_parameters()
        self._save_tag_presets_request()

    def on_gear_clicked(self, tag_node: dict, tag_value: str, item: QTreeWidgetItem, btn_widget: QPushButton):
        if self.right_container.isVisible() and self.current_editing_node == tag_node:
            self._save_current_to_node()
            self._toggle_right_panel()
            return

        if self.right_container.isVisible() and self.current_editing_node is not None:
            self._save_current_to_node()

        self.current_editing_node = tag_node
        self.current_editing_item = item
        self.tree.setCurrentItem(item)
        
        current_params = tag_node.get('params', {})
        self.params_panel.set_parameters(current_params)
        
        is_active = tag_node.get('use_params', False)
        self._update_use_params_btn_style(is_active)
        
        self.tag_title_lbl.setText(f"<span style='color:{Palette.PRIMARY}'>{tag_value.upper()}</span>")

        if not self.right_container.isVisible():
            self.right_container.show()
            self.vertical_separator.show()
            
            # --- ИСПРАВЛЕНИЕ: Динамический расчет ширины ---
            # Принудительно обновляем геометрию, чтобы получить актуальный sizeHint
            self.params_panel.adjustSize()
            content_w = self.params_panel.sizeHint().width()
            
            # Формула: Фиксированная левая панель (450) + Контент справа + Отступы (~60px)
            target_w = 450 + content_w + 60
            
            # Проверка на ширину экрана (чтобы не улетело за границы)
            screen_geom = QApplication.primaryScreen().availableGeometry()
            if target_w > screen_geom.width() - 50:
                target_w = screen_geom.width() - 50
                
            # Применяем размер, если он больше текущего
            if self.width() != target_w:
                self.resize(target_w, self.height())
            # -----------------------------------------------

    def _save_current_to_node(self):
        if self.current_editing_node is not None:
            new_params = self.params_panel.get_parameters()
            self.current_editing_node["params"] = new_params
            self._save_tag_presets_request()

    def _save_tag_presets_request(self):
        if hasattr(self.parent(), "_save_tag_presets"):
            self.parent()._save_tag_presets()

    def _toggle_right_panel(self):
        if self.right_container.isVisible():
            self._save_current_to_node()
            self.right_container.hide()
            self.vertical_separator.hide()

            self.setFixedSize(450, self.height())
            QTimer.singleShot(50, lambda: self.setMinimumSize(450, 0))
            QTimer.singleShot(50, lambda: self.setMaximumSize(16777215, 16777215))

            self.current_editing_node = None
            self.current_editing_item = None

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
            self.lbl_summary_text.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-style: italic; font-size: 11px;")
        else:
            txt = ", ".join(preview_text)
            if count > 5: txt += f" ... и еще {count - 5}"
            self.lbl_summary_text.setText(txt)
            self.lbl_summary_text.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 11px;")

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
        self._save_current_to_node()
        self.final_checked_state = set()
        self.final_expanded_state = set()
        def _traverse(item):
            if item.isExpanded():
                key = item.data(0, Qt.ItemDataRole.UserRole + 2)
                if key: self.final_expanded_state.add(key)
            if item.checkState(0) == Qt.CheckState.Checked:
                tag = item.data(0, Qt.ItemDataRole.UserRole)
                t_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
                if tag and t_type: self.final_checked_state.add(f"{t_type}|{tag}")
            for i in range(item.childCount()): _traverse(item.child(i))
        for i in range(self.tree.topLevelItemCount()): _traverse(self.tree.topLevelItem(i))
        super().done(result)

    def get_state(self):
        if not hasattr(self, 'final_checked_state'):
            return self.saved_checked, self.saved_expanded
        return self.final_checked_state, self.final_expanded_state

    def _collect_final_state(self):
        s_tags = []
        i_tags = []
        new_checked = set()
        self.collected_tag_params = {}
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            tag = item.data(0, Qt.ItemDataRole.UserRole)
            t_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            node_data = item.data(0, Qt.ItemDataRole.UserRole + 3)
            
            if tag and t_type:
                if t_type == 'search': 
                    s_tags.append(tag)
                    if node_data and node_data.get("params") and node_data.get("use_params", False):
                        self.collected_tag_params[tag] = node_data["params"]
                elif t_type == 'ignore': 
                    i_tags.append(tag)
                new_checked.add(f"{t_type}|{tag}")
            iterator += 1
        self.selected_search_tags = list(set(s_tags))
        self.selected_ignore_tags = list(set(i_tags))
        self.new_checked_state = new_checked

    def _on_apply_current(self):
        self._save_current_to_node()
        self._collect_final_state()
        self._clear_all_checks()
        self.action_type = 'apply_curr'
        self.accept()

    def _on_apply_new(self):
        self._save_current_to_node()
        self._collect_final_state()
        self._clear_all_checks()
        self.action_type = 'apply_new'
        self.accept()
        
    def _on_manage(self, mode):
        self._save_current_to_node()
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
    parameters_update_requested = pyqtSignal(dict)
    apply_tags_to_new_queue_requested = pyqtSignal(list, list, dict)
    
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
        popup.move(global_pos.x() - 20, global_pos.y())
        
        res = popup.exec()
        
        new_checked, new_expanded = popup.get_state()
        self.presets_checked_state = new_checked
        self.presets_expanded_state = new_expanded
        
        if res == QDialog.DialogCode.Accepted:
            action = popup.action_type
            s_tags = popup.selected_search_tags
            i_tags = popup.selected_ignore_tags
            
            if action == 'manage_search':
                self._open_tag_presets_editor()
            elif action == 'manage_ignore':
                self._open_ignore_tag_presets_editor()
            
            elif action == 'apply_curr':
                tag_params = getattr(popup, 'collected_tag_params', {})
                last_params = None
                
                if s_tags:
                    curr_s = self.search_tags_input.get_tags()
                    self.search_tags_input.set_tags(list(set(curr_s + s_tags)))
                    
                    for t in s_tags:
                        if t in tag_params:
                            last_params = tag_params[t] 
                
                if i_tags:
                    curr_i = self.ignore_tags_input.get_tags()
                    self.ignore_tags_input.set_tags(list(set(curr_i + i_tags)))
                
                if last_params:
                    self.parameters_update_requested.emit(last_params)

            elif action == 'apply_new':
                if not s_tags and not i_tags:
                    QMessageBox.warning(self, "Пусто", "Выберите хотя бы один тег!")
                    return
                
                tag_params = getattr(popup, 'collected_tag_params', {})
                self.apply_tags_to_new_queue_requested.emit(s_tags, i_tags, tag_params)

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

    def _make_tag(self, value: str, params=None, use_params=False) -> dict:
        d = {"type": "tag", "value": value}
        if params: d["params"] = params
        if use_params: d["use_params"] = use_params
        return d

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
                        norm_children.append(self._make_tag(val, c.get("params"), c.get("use_params", False)))
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