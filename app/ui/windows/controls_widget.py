import math
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
                             QLabel, QGroupBox, QSpinBox, QPlainTextEdit, QGridLayout, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from app.ui.widgets.controls import PriceSpinBox, AnimatedToggle, ParamInput, NoScrollComboBox
from app.ui.styles import Components, Palette, Spacing, Typography


class SearchModeWidget(QWidget):
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XS)

        self.btn_primary = self._create_mode_button("⚡\n Первичный", "Сбор ID и цен")
        self.btn_full = self._create_mode_button("📄\n Полный", "С описанием")
        self.btn_neuro = self._create_mode_button("🧠\n Нейро", "Анализ с AI")

        layout.addWidget(self.btn_primary)
        layout.addWidget(self.btn_full)
        layout.addWidget(self.btn_neuro)

        self.current_mode = "full"
        self._updating = False
        self._update_buttons()

        self.btn_primary.toggled.connect(lambda checked: self._on_button_toggled("primary", checked))
        self.btn_full.toggled.connect(lambda checked: self._on_button_toggled("full", checked))
        self.btn_neuro.toggled.connect(lambda checked: self._on_button_toggled("neuro", checked))

    def _create_mode_button(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setFixedHeight(45)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                color: {Palette.TEXT_MUTED};
                font-family: {Typography.UI};
                font-size: {Typography.SIZE_NORMAL}px;
                padding: {Spacing.XS}px {Spacing.MD}px;
            }}
            QPushButton:hover {{
                border-color: {Palette.PRIMARY};
                color: {Palette.TEXT};
            }}
            QPushButton:checked {{
                background-color: {Palette.with_alpha(Palette.PRIMARY, 0.2)};
                border: 1px solid {Palette.PRIMARY};
                color: {Palette.PRIMARY};
                font-weight: {Typography.WEIGHT_BOLD};
            }}
        """)
        return btn

    def _on_button_toggled(self, mode: str, checked: bool):
        if self._updating:
            return
        if not checked and self.current_mode == mode:
            self._updating = True
            self._update_buttons()
            self._updating = False
            return
        if checked and self.current_mode != mode:
            self._set_mode(mode)

    def _set_mode(self, mode: str):
        if self.current_mode == mode:
            return
        self.current_mode = mode
        self._update_buttons()
        self.mode_changed.emit(mode)

    def _update_buttons(self):
        self._updating = True
        for btn, mode in [(self.btn_primary, "primary"), (self.btn_full, "full"), (self.btn_neuro, "neuro")]:
            btn.setChecked(self.current_mode == mode)
        self._updating = False

    def get_mode(self) -> str:
        return self.current_mode

    def set_mode(self, mode: str):
        self._set_mode(mode)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        for btn in [self.btn_primary, self.btn_full, self.btn_neuro]:
            btn.setEnabled(enabled)

class ControlsWidget(QWidget):
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    stop_neuro_analysis_requested = pyqtSignal()
    pause_neuronet_requested = pyqtSignal()
    parameters_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress_param_signals = False
        self._current_tags_count = 1  # Default to 1 category
        self._init_ui()
        self._connect_signals()
        self._update_pages_info()

    def _update_toggle_label(self, label_widget: QLabel, is_checked: bool):
        text = "Вкл" if is_checked else "Выкл"
        weight = Typography.WEIGHT_BOLD if is_checked else Typography.WEIGHT_NORMAL
        color = Palette.PRIMARY if is_checked else Palette.TEXT_MUTED
        
        label_widget.setText(text)
        label_widget.setStyleSheet(Typography.style(
            family=Typography.UI,
            size=Typography.SIZE_SMALL,
            weight=weight,
            color=color
        ))

    def _create_param_card(self, title: str = None):
        card = QFrame()
        card.setObjectName("param_card")
        card.setStyleSheet(Components.card())
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        card_layout.setSpacing(Spacing.GAP_LOOSE)
        if title:
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(Components.subsection_title())
            card_layout.addWidget(title_lbl)
        return card, card_layout

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.MD, Spacing.XS)
        main_layout.setSpacing(Spacing.MD)
        blacklist_panel = self._create_blacklist_panel()
        blacklist_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(blacklist_panel, stretch=1)
        params_panel = self._create_params_panel()
        params_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(params_panel, stretch=3)
        self.ai_column = QFrame()
        self.ai_column.setStyleSheet("background-color: transparent; border: none;")
        self.ai_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ai_layout = QVBoxLayout(self.ai_column)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.setSpacing(Spacing.MD)
        self._ai_column_layout = ai_layout
        main_layout.addWidget(self.ai_column, stretch=2)
        actions_panel = self._create_actions_panel()
        actions_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(actions_panel, stretch=0)

    def attach_ai_stats(self, stats_panel: QWidget):
        if hasattr(self, "_ai_column_layout"):
            stats_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._ai_column_layout.addWidget(stats_panel, stretch=0)

    def attach_progress_panel(self, progress_panel: QWidget):
        if hasattr(self, "_ai_column_layout"):
            progress_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._ai_column_layout.addWidget(progress_panel, stretch=1)

    def _create_blacklist_panel(self) -> QFrame:
        from app.ui.widgets.managers import BlacklistWidget
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.blacklist_widget = BlacklistWidget()
        layout.addWidget(self.blacklist_widget, stretch=1)
        return panel

    def _create_actions_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(280)
        panel.setStyleSheet(Components.panel())
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        self.start_button = QPushButton("НАЧАТЬ\nПОИСК")
        self.start_button.setMinimumHeight(60)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.setStyleSheet(Components.start_button())
        layout.addWidget(self.start_button)
        self.stop_button = QPushButton("ОСТАНОВИТЬ\nПОИСК")
        self.stop_button.setMinimumHeight(60)
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setStyleSheet(Components.stop_button())
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)
        self.stop_neuro_analysis_btn = QPushButton("ОСТАНОВИТЬ\nНЕЙРО-АНАЛИЗ")
        self.stop_neuro_analysis_btn.setMinimumHeight(45)
        self.stop_neuro_analysis_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_neuro_analysis_btn.setStyleSheet(Components.stop_button())
        self.stop_neuro_analysis_btn.setEnabled(False)
        layout.addWidget(self.stop_neuro_analysis_btn)
        self.pause_neuronet_btn = QPushButton("ПРИОСТАНОВИТЬ\nНЕЙРОСЕТЬ")
        self.pause_neuronet_btn.setMinimumHeight(45)
        self.pause_neuronet_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_neuronet_btn.setStyleSheet(Components.stop_button())
        self.pause_neuronet_btn.setEnabled(False)
        layout.addWidget(self.pause_neuronet_btn)
        layout.addWidget(self._create_separator())
        layout.addStretch()
        return panel

    def _create_params_panel(self) -> QGroupBox:
        group = QGroupBox()
        group.setStyleSheet(Components.panel())
        main_layout = QVBoxLayout(group)
        main_layout.setContentsMargins(*Spacing.PADDING_PANEL, *Spacing.PADDING_PANEL)
        main_layout.setSpacing(Spacing.GAP_NORMAL)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        title_label = QLabel("ПАРАМЕТРЫ ПОИСКА")
        title_label.setStyleSheet(Components.section_title())
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addWidget(header)
        params_layout = QHBoxLayout()
        params_layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        params_layout.setSpacing(int(Spacing.MD * 0.75))
        params_layout.addLayout(self._create_search_column(), 2)
        params_layout.addLayout(self._create_limits_column(), 2)
        params_layout.addLayout(self._create_merge_column(), 2)
        main_layout.addLayout(params_layout, stretch=1)
        return group

    def _create_merge_column(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.MD)
        unified_card, unified_layout = self._create_param_card(None)
        unified_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        
        queue_header = QWidget()
        queue_header_layout = QHBoxLayout(queue_header)
        queue_header_layout.setContentsMargins(0, 0, 0, 0)
        queue_header_layout.setSpacing(Spacing.SM)
        queue_title = QLabel("ОЧЕРЕДЬ ЗАДАЧ")
        queue_title.setStyleSheet(Components.subsection_title())
        queue_header_layout.addWidget(queue_title)
        queue_header_layout.addStretch()
        self.queue_add_btn = QPushButton("+")
        self.queue_remove_btn = QPushButton("-")
        btn_style = f"""
            QPushButton {{ background-color: {Palette.BG_DARK_3}; border: 1px solid {Palette.BORDER_PRIMARY}; border-radius: {Spacing.RADIUS_NORMAL}px; color: {Palette.TEXT}; font-size: 16px; font-weight: {Typography.WEIGHT_BOLD}; padding: 0; }}
            QPushButton:hover {{ background-color: {Palette.BG_LIGHT}; border-color: {Palette.PRIMARY}; color: {Palette.PRIMARY}; }}
            QPushButton:pressed {{ background-color: {Palette.BG_DARK_2}; }}
            QPushButton:disabled {{ background-color: {Palette.BG_DARK}; border-color: {Palette.DIVIDER}; color: {Palette.TEXT_MUTED}; }}
        """
        for btn in (self.queue_add_btn, self.queue_remove_btn):
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(btn_style)
        queue_header_layout.addWidget(self.queue_add_btn)
        queue_header_layout.addWidget(self.queue_remove_btn)
        unified_layout.addWidget(queue_header)
        
        from app.ui.widgets.managers import QueueManagerWidget
        self.queue_manager_widget = QueueManagerWidget()
        unified_layout.addWidget(self.queue_manager_widget, stretch=2)
        self.queue_add_btn.clicked.connect(self.queue_manager_widget.add_queue)
        self.queue_remove_btn.clicked.connect(self.queue_manager_widget.remove_queue)
        self.queue_add_btn.clicked.connect(self._update_queue_ui_state)
        self.queue_remove_btn.clicked.connect(self._update_queue_ui_state)
        self.queue_manager_widget.list_widget.model().rowsInserted.connect(self._update_queue_ui_state)
        self.queue_manager_widget.list_widget.model().rowsRemoved.connect(self._update_queue_ui_state)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(f"background-color: {Palette.with_alpha(Palette.TEXT, 0.1)}; max-height: 1px;")
        unified_layout.addWidget(separator)
        
        merge_title = QLabel("УПРАВЛЕНИЕ РЕЗУЛЬТАТАМИ")
        merge_title.setStyleSheet(Components.subsection_title())
        unified_layout.addWidget(merge_title)
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setSpacing(Spacing.SM)
        grid.addWidget(self._create_split_results_toggle(), 0, 0, 1, 2)
        lbl_add_to = QLabel("Обновить/Добавить к Таблице")
        lbl_add_to.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        grid.addWidget(lbl_add_to, 1, 0, 1, 2)
        self.merge_table_combo = NoScrollComboBox()
        self.merge_table_combo.setMinimumWidth(80)
        self.merge_table_combo.setStyleSheet(Components.styled_combobox())
        self.merge_table_combo.setObjectName("merge_table_combo")
        self.merge_table_combo.addItem("Новая таблица", None)
        self.merge_table_combo.currentIndexChanged.connect(self._update_duplicates_toggle_state)
        grid.addWidget(self.merge_table_combo, 2, 0, 1, 2)
        grid.addWidget(self._create_rewrite_duplicates_toggle(), 3, 0, 1, 2)
        unified_layout.addLayout(grid)
        layout.addWidget(unified_card, stretch=1)
        self._update_queue_buttons()
        return layout

    def _update_queue_ui_state(self):
        """Обновляет состояние кнопок очереди"""
        if not hasattr(self, 'queue_manager_widget'): return
        queue_count = self.queue_manager_widget.list_widget.count()
        self.queue_remove_btn.setEnabled(queue_count > 1)

    def _update_queue_buttons(self):
        if not hasattr(self, 'queue_manager_widget'): return
        queue_count = self.queue_manager_widget.list_widget.count()
        self.queue_remove_btn.setEnabled(queue_count > 1)

    def _update_duplicates_toggle_state(self):
        has_table = self.merge_table_combo.currentData() is not None
        is_split = self.split_results_sw.isChecked()
        self.rewrite_duplicates_sw.setEnabled(has_table and not is_split)
        if not has_table or is_split:
            self.rewrite_duplicates_sw.setChecked(False)

    def _on_split_results_toggled(self, checked):
        self.merge_table_combo.setEnabled(not checked)
        if checked:
            self.merge_table_combo.setCurrentIndex(0)
        self._update_duplicates_toggle_state()
        self._emit_parameters_changed()

    def _create_rewrite_duplicates_toggle(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(Spacing.XS * 1.5))
        title = QLabel("Обновлять дубликаты")
        title.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        layout.addWidget(title)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(Spacing.SM)
        self.rewrite_duplicates_sw = AnimatedToggle()
        self.rewrite_duplicates_sw.setFixedSize(55, 30)
        self.rewrite_duplicates_sw.setChecked(False)
        self.rewrite_duplicates_sw.setEnabled(False)
        self.rewrite_duplicates_lbl = QLabel("Выкл")
        self._update_toggle_label(self.rewrite_duplicates_lbl, False)
        
        self.rewrite_duplicates_sw.stateChanged.connect(
            lambda s: self._update_toggle_label(self.rewrite_duplicates_lbl, s)
        )
        row_layout.addWidget(self.rewrite_duplicates_sw)
        row_layout.addWidget(self.rewrite_duplicates_lbl)
        row_layout.addStretch()
        layout.addLayout(row_layout)
        return container

    def _create_split_results_toggle(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(Spacing.XS * 1.5))
        title = QLabel("Разделять результаты очередей")
        title.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        layout.addWidget(title)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(Spacing.SM)
        self.split_results_sw = AnimatedToggle()
        self.split_results_sw.setFixedSize(55, 30)
        self.split_results_sw.setChecked(False)
        self.split_results_sw.stateChanged.connect(self._on_split_results_toggled)
        self.split_results_lbl = QLabel("Выкл")
        self._update_toggle_label(self.split_results_lbl, False)
        
        self.split_results_sw.stateChanged.connect(
            lambda s: self._update_toggle_label(self.split_results_lbl, s)
        )
        row_layout.addWidget(self.split_results_sw)
        row_layout.addWidget(self.split_results_lbl)
        row_layout.addStretch()
        layout.addLayout(row_layout)
        return container

    def _create_search_column(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.MD)
        price_card, price_card_layout = self._create_param_card("ДИАПАЗОН ЦЕН")
        grid = QGridLayout()
        grid.setSpacing(Spacing.SM)
        self.min_price_input = PriceSpinBox(0, "∞")
        self.max_price_input = PriceSpinBox(0, "∞")
        grid.addWidget(ParamInput("От", self.min_price_input), 0, 0)
        grid.addWidget(ParamInput("До", self.max_price_input), 0, 1)
        price_card_layout.addLayout(grid)
        layout.addWidget(price_card)
        self.min_price_input.valueChanged.connect(self._on_min_price_changed)
        self.max_price_input.valueChanged.connect(self._on_max_price_changed)
        mode_card, mode_card_layout = self._create_param_card("РЕЖИМ ПОИСКА")
        mode_grid = QGridLayout()
        mode_grid.setSpacing(Spacing.SM)
        self.search_mode_widget = SearchModeWidget()
        mode_grid.addWidget(self.search_mode_widget, 0, 0, 1, 2)
        self.ai_criteria_container = self._create_ai_criteria()
        self.ai_criteria_container.setEnabled(False)
        mode_grid.addWidget(self.ai_criteria_container, 1, 0, 1, 2)
        mode_grid.setRowStretch(1, 1)
        mode_card_layout.addLayout(mode_grid)
        layout.addWidget(mode_card, stretch=1)
        return layout

    def _create_limits_column(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.MD)
        
        limits_card, limits_layout = self._create_param_card("ЛИМИТЫ")
        
        grid = QGridLayout()
        grid.setSpacing(Spacing.SM)
        
        # 1. Настройка инпута (фиксируем ширину, чтобы не растягивался)
        self.max_items_input = QSpinBox()
        self.max_items_input.setFixedWidth(80)  # <-- ФИКС: Ограничиваем ширину
        self.max_items_input.setRange(0, 99_999)
        self.max_items_input.setSpecialValueText("∞")
        self.max_items_input.setSingleStep(10)
        self.max_items_input.setStyleSheet(Components.text_input())
        self.max_items_input.valueChanged.connect(self._update_pages_info)
        
        # Обертка ParamInput должна подстраиваться под контент, а не растягиваться
        input_wrapper = ParamInput("Объявлений", self.max_items_input)
        input_wrapper.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        grid.addWidget(input_wrapper, 0, 0)
        
        # 2. Настройка инфо-блока (делаем его больше и ровнее)
        self.pages_info_lbl = QLabel()
        # Убираем жесткий стиль здесь, он будет задаваться через HTML в _update_pages_info
        self.pages_info_lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED};")
        self.pages_info_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2) # Чуть плотнее
        
        lbl_caption = QLabel("Обходим")
        lbl_caption.setStyleSheet(
            Typography.style(
                family=Typography.UI,
                size=Typography.SIZE_NORMAL, # Чуть крупнее заголовок
                color=Palette.TEXT_SECONDARY,
            )
        )
        info_layout.addWidget(lbl_caption)
        info_layout.addWidget(self.pages_info_lbl)
        
        # Добавляем во вторую колонку
        grid.addWidget(info_container, 0, 1)

        # 3. Нижний ряд (Toggle buttons)
        grid.addWidget(self._create_region_toggle(), 1, 0)
        grid.addWidget(self._create_defects_toggle(), 1, 1)

        # 4. ВАЖНО: Настройка растяжения колонок
        # Колонка 0 (Инпут) занимает минимум места
        # Колонка 1 (Инфо) занимает всё остальное место
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        
        limits_layout.addLayout(grid)
        layout.addWidget(limits_card)

        # Сортировка и нейро-опции (без изменений)
        sort_card, sort_layout = self._create_param_card("СОРТИРОВКА")
        self.sort_combo = NoScrollComboBox()
        self.sort_combo.setMinimumWidth(80)
        self.sort_combo.setStyleSheet(Components.styled_combobox())
        self.sort_combo.addItem("По умолчанию (релевантность)", userData="default")
        self.sort_combo.addItem("Дешевле", userData="price_asc")
        self.sort_combo.addItem("Дороже", userData="price_desc")
        self.sort_combo.addItem("По дате", userData="date")
        self.sort_combo.addItem("По скидке", userData="discount")
        for i in range(self.sort_combo.count()):
            if self.sort_combo.itemData(i) == "date":
                self.sort_combo.setCurrentIndex(i)
                break
        sort_layout.addWidget(self.sort_combo)
        layout.addWidget(sort_card)
        
        neuro_card, neuro_layout = self._create_param_card("НЕЙРО-ОПЦИИ")
        neuro_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        neuro_grid = QGridLayout()
        neuro_grid.setSpacing(Spacing.SM)
        neuro_grid.addWidget(self._create_include_ai_toggle(), 0, 0)
        neuro_grid.addWidget(self._create_rag_toggle(), 0, 1)
        neuro_grid.setRowStretch(1, 1)
        neuro_layout.addLayout(neuro_grid)
        layout.addWidget(neuro_card, stretch=1)
        
        return layout

    def update_category_count(self, count: int):
        """Обновляет количество категорий для расчета расхода"""
        self._current_tags_count = max(1, count)
        self._update_pages_info()

    def _update_pages_info(self):
        if not hasattr(self, 'max_items_input'):
            return
        items = self.max_items_input.value()
        categories = self._current_tags_count if self._current_tags_count >= 1 else 1

        if hasattr(self, '_parent') and hasattr(self._parent, 'search_widget'):
            if not self._parent.search_widget.cached_scanned_categories and not self._parent.search_widget.cached_forced_categories:
                categories = 1

        is_all_regions = False
        if hasattr(self, 'search_all_regions_checkbox'):
            is_all_regions = self.search_all_regions_checkbox.isChecked()
        
        # Множитель: 2 если все регионы, 1 если только Москва
        region_mult = 2 if is_all_regions else 1
        
        # Кол-во "задач" для парсера (Category * Mult)
        tasks_count = categories * region_mult
        # --- UPDATED LOGIC END ---

        if items == 0:
            items_per_cat = "∞"
            pages_per_cat = 100
            total_items = "∞"
        else:
            items_per_cat = items
            pages_per_cat = math.ceil(items / 50)
            total_items = tasks_count * items

        region_suffix = " <span style='color:#e67e22;'>(x2 рег.)</span>" if is_all_regions else ""

        text = f"""
        <html>
        <head/>
        <body>
        <div style="line-height: 120%">
            <span style="font-size:13px; color:{Palette.TEXT};"><b>{categories}</b> кат.{region_suffix}</span><br>
            <span style="font-size:13px; color:{Palette.TEXT};">✕ <b>{items_per_cat}</b> об.</span><br>
            <span style="font-size:11px; color:{Palette.TEXT_MUTED};">(<b>{pages_per_cat}</b> стр.)</span>
        </div>
        <div style="margin-top:6px;">
            <span style="font-size:14px; color:{Palette.PRIMARY};">Всего: <b>{total_items}</b></span>
        </div>
        </body>
        </html>
        """
        self.pages_info_lbl.setText(text)
        self.pages_info_lbl.setToolTip(f"Будет проверено {tasks_count} направлений (Категории x Регионы)...")

    def _create_rag_toggle(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(Spacing.XS * 1.5))
        title = QLabel("Поместить в память ИИ")
        title.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        layout.addWidget(title)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(Spacing.SM)
        self.store_memory_sw = AnimatedToggle()
        self.store_memory_sw.setFixedSize(55, 30)
        self.store_memory_sw.setChecked(False)
        self.store_memory_lbl = QLabel("Выкл")
        self._update_toggle_label(self.store_memory_lbl, False)
        
        self.store_memory_sw.stateChanged.connect(
            lambda s: self._update_toggle_label(self.store_memory_lbl, s)
        )
        row_layout.addWidget(self.store_memory_sw)
        row_layout.addWidget(self.store_memory_lbl)
        layout.addLayout(row_layout)
        return container

    def _create_ai_criteria(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, Spacing.XS, 0, 0)
        layout.setSpacing(Spacing.XS)
        lbl = QLabel("ДОП. КРИТЕРИИ ИИ")
        lbl.setStyleSheet(Components.subsection_title() + f" color: {Palette.SECONDARY};")
        layout.addWidget(lbl)
        self.ai_criteria_input = QPlainTextEdit()
        self.ai_criteria_input.setPlaceholderText("Например: только на гарантии, полная предоплата...")
        self.ai_criteria_input.setMinimumHeight(120)
        self.ai_criteria_input.setStyleSheet(Components.text_input())
        layout.addWidget(self.ai_criteria_input, stretch=1)
        return container

    def _create_include_ai_toggle(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(Spacing.XS * 1.5))
        title = QLabel("Нейро-анализ")
        title.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        layout.addWidget(title)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(Spacing.SM)
        self.include_ai_sw = AnimatedToggle()
        self.include_ai_sw.setFixedSize(55, 30)
        self.include_ai_sw.setChecked(True)
        self.include_ai_lbl = QLabel("Вкл")
        self._update_toggle_label(self.include_ai_lbl, True)
        
        self.include_ai_sw.stateChanged.connect(
            lambda s: self._update_toggle_label(self.include_ai_lbl, s)
        )
        row_layout.addWidget(self.include_ai_sw)
        row_layout.addWidget(self.include_ai_lbl)
        layout.addLayout(row_layout)
        return container

    def _create_region_toggle(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(Spacing.XS * 1.5))
        title = QLabel("Регион")
        title.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        layout.addWidget(title)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(Spacing.SM)
        self.search_all_regions_checkbox = AnimatedToggle()
        self.search_all_regions_checkbox.setFixedSize(55, 30)
        self.region_status_label = QLabel("Москва")
        self._update_toggle_label(self.region_status_label, False)
        self.region_status_label.setText("Москва")
        self.search_all_regions_checkbox.stateChanged.connect(
            lambda s: self._update_region_label(s)
        )
        self.search_all_regions_checkbox.stateChanged.connect(
            lambda: self._update_pages_info()
        )
        
        row_layout.addWidget(self.search_all_regions_checkbox)
        row_layout.addWidget(self.region_status_label)
        layout.addLayout(row_layout)
        return container

    def _update_region_label(self, is_checked):
        text = "Все регионы" if is_checked else "Москва"
        weight = Typography.WEIGHT_BOLD if is_checked else Typography.WEIGHT_NORMAL
        color = Palette.PRIMARY if is_checked else Palette.TEXT_MUTED
        self.region_status_label.setText(text)
        self.region_status_label.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_SMALL, weight=weight, color=color))

    def _create_defects_toggle(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(Spacing.XS * 1.5))
        title = QLabel("Фильтр дефектов")
        title.setStyleSheet(Typography.style(family=Typography.UI, size=Typography.SIZE_NORMAL, color=Palette.TEXT_SECONDARY))
        layout.addWidget(title)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(Spacing.SM)
        self.filter_defects_sw = AnimatedToggle()
        self.filter_defects_sw.setFixedSize(55, 30)
        self.filter_defects_lbl = QLabel("Выкл")
        self._update_toggle_label(self.filter_defects_lbl, False)
        
        self.filter_defects_sw.stateChanged.connect(
            lambda s: self._update_toggle_label(self.filter_defects_lbl, s)
        )
        row_layout.addWidget(self.filter_defects_sw)
        row_layout.addWidget(self.filter_defects_lbl)
        layout.addLayout(row_layout)
        return container

    def _create_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {Palette.with_alpha(Palette.TEXT, 0.1)}; max-height: 1px; margin: {Spacing.XS}px 0px;")
        return line

    def _on_min_price_changed(self, min_val: int):
        if not hasattr(self, "max_price_input"): return
        max_val = self.max_price_input.value()
        if max_val == 0:
            self._emit_parameters_changed()
            return
        if min_val > max_val: self.max_price_input.setValue(min_val)
        self._emit_parameters_changed()

    def _on_max_price_changed(self, max_val: int):
        if not hasattr(self, "min_price_input"): return
        min_val = self.min_price_input.value()
        if max_val == 0:
            self._emit_parameters_changed()
            return
        if max_val < min_val: self.min_price_input.setValue(max_val)
        self._emit_parameters_changed()

    def _connect_signals(self):
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_neuro_analysis_btn.clicked.connect(self.stop_neuro_analysis_requested.emit)
        self.pause_neuronet_btn.clicked.connect(self.pause_neuronet_requested.emit)
        self.min_price_input.valueChanged.connect(lambda _: self._emit_parameters_changed())
        self.max_price_input.valueChanged.connect(lambda _: self._emit_parameters_changed())
        self.max_items_input.valueChanged.connect(lambda _: self._emit_parameters_changed())
        self.search_all_regions_checkbox.stateChanged.connect(lambda _: self._emit_parameters_changed())
        self.filter_defects_sw.stateChanged.connect(lambda _: self._emit_parameters_changed())
        self.include_ai_sw.stateChanged.connect(lambda _: self._emit_parameters_changed())
        self.store_memory_sw.stateChanged.connect(lambda _: self._emit_parameters_changed())
        self.sort_combo.currentIndexChanged.connect(lambda _: self._emit_parameters_changed())
        self.merge_table_combo.currentIndexChanged.connect(lambda _: self._emit_parameters_changed())
        self.search_mode_widget.mode_changed.connect(self._on_mode_changed)
        if hasattr(self, "rewrite_duplicates_sw"):
            self.rewrite_duplicates_sw.stateChanged.connect(lambda _: self._emit_parameters_changed())
        if hasattr(self, "split_results_sw"):
            self.split_results_sw.stateChanged.connect(lambda _: self._emit_parameters_changed())

    def _on_mode_changed(self, mode: str):
        is_neuro = mode == "neuro"
        self.ai_criteria_container.setEnabled(is_neuro)
        if is_neuro:
            self.ai_criteria_input.setStyleSheet(Components.text_input())
        else:
            self.ai_criteria_input.setStyleSheet(Components.text_input() + f"""
                QPlainTextEdit {{
                    background-color: {Palette.BG_DARK_3};
                    color: {Palette.TEXT_MUTED};
                    border-color: {Palette.DIVIDER};
                }}
                """)
        self._emit_parameters_changed()

    def get_parameters(self) -> dict:
        sort_type = "date"
        if hasattr(self, "sort_combo"):
            idx = self.sort_combo.currentIndex()
            if idx >= 0:
                data = self.sort_combo.itemData(idx)
                if data: sort_type = data
        merge_with_table = None
        if hasattr(self, "merge_table_combo"):
            data = self.merge_table_combo.currentData()
            if data: merge_with_table = data
        return {
            "min_price": self.min_price_input.value(),
            "max_price": self.max_price_input.value(),
            "search_mode": self.search_mode_widget.get_mode(),
            "ai_criteria": self.ai_criteria_input.toPlainText(),
            "include_ai": self.include_ai_sw.isChecked(),
            "store_in_memory": self.store_memory_sw.isChecked(),
            "max_pages": 0,
            "max_items": self.max_items_input.value(),
            "all_regions": self.search_all_regions_checkbox.isChecked(),
            "filter_defects": self.filter_defects_sw.isChecked(),
            "rewrite_duplicates": getattr(self, "rewrite_duplicates_sw", None) and self.rewrite_duplicates_sw.isChecked(),
            "split_results": getattr(self, "split_results_sw", None) and self.split_results_sw.isChecked(),
            "merge_with_table": merge_with_table,
            "sort_type": sort_type,
        }

    def set_parameters(self, params: dict):
        self._suppress_param_signals = True
        try:
            self.min_price_input.setValue(params.get("min_price", 0))
            self.max_price_input.setValue(params.get("max_price", 0))
            self.search_mode_widget.set_mode(params.get("search_mode", "full"))
            self.ai_criteria_input.setPlainText(params.get("ai_criteria", ""))
            self.include_ai_sw.setChecked(params.get("include_ai", True))
            self.store_memory_sw.setChecked(params.get("store_in_memory", False))
            self.max_items_input.setValue(params.get("max_items", 0))
            self.search_all_regions_checkbox.setChecked(params.get("all_regions", False))
            self.filter_defects_sw.setChecked(params.get("filter_defects", False))
            if hasattr(self, "rewrite_duplicates_sw"):
                self.rewrite_duplicates_sw.setChecked(bool(params.get("rewrite_duplicates", False)))
            if hasattr(self, "split_results_sw"):
                self.split_results_sw.setChecked(bool(params.get("split_results", False)))
            if hasattr(self, "sort_combo"):
                sort_type = params.get("sort_type", "date")
                for i in range(self.sort_combo.count()):
                    if self.sort_combo.itemData(i) == sort_type:
                        self.sort_combo.setCurrentIndex(i)
                        break
            if hasattr(self, "merge_table_combo"):
                target = params.get("merge_with_table")
                if target:
                    for i in range(self.merge_table_combo.count()):
                        if self.merge_table_combo.itemData(i) == target:
                            self.merge_table_combo.setCurrentIndex(i)
                            break
                else:
                    self.merge_table_combo.setCurrentIndex(0)
            self._update_duplicates_toggle_state()
        finally:
            self._suppress_param_signals = False

    def set_merge_targets(self, targets: list[tuple[str, str]]):
        if not hasattr(self, "merge_table_combo"): return
        current = self.merge_table_combo.currentData()
        self.merge_table_combo.blockSignals(True)
        self.merge_table_combo.clear()
        self.merge_table_combo.addItem("Новая таблица", None)
        for path, label in targets:
            self.merge_table_combo.addItem(label, path)
        if current:
            for i in range(self.merge_table_combo.count()):
                if self.merge_table_combo.itemData(i) == current:
                    self.merge_table_combo.setCurrentIndex(i)
                    break
        self.merge_table_combo.blockSignals(False)
        self._update_duplicates_toggle_state()

    def _emit_parameters_changed(self):
        if self._suppress_param_signals: return
        self.parameters_changed.emit(self.get_parameters())

    def set_ui_locked(self, locked: bool):
        self.start_button.setEnabled(not locked)
        self.stop_button.setEnabled(locked)
        self.min_price_input.setEnabled(not locked)
        self.max_price_input.setEnabled(not locked)
        self.max_items_input.setEnabled(not locked)
        self.search_all_regions_checkbox.setEnabled(not locked)
        self.filter_defects_sw.setEnabled(not locked)
        self.include_ai_sw.setEnabled(not locked)
        self.store_memory_sw.setEnabled(not locked)
        if hasattr(self, "sort_combo"): self.sort_combo.setEnabled(not locked)
        if hasattr(self, "rewrite_duplicates_sw"): self.rewrite_duplicates_sw.setEnabled(not locked and self.merge_table_combo.currentData() is not None)
        if hasattr(self, "split_results_sw"): self.split_results_sw.setEnabled(not locked)
        if hasattr(self, "merge_table_combo"): self.merge_table_combo.setEnabled(not locked and not self.split_results_sw.isChecked())
        if hasattr(self, "queue_manager_widget"): self.queue_manager_widget.setEnabled(not locked)
        if hasattr(self, "blacklist_widget"): self.blacklist_widget.setEnabled(not locked)
        if hasattr(self, "search_mode_widget"): self.search_mode_widget.setEnabled(not locked)
        if hasattr(self, 'btn_start'):
            self.start_button.setVisible(not locked)
        if hasattr(self, 'btn_stop'):
            self.stop_button.setVisible(locked)
            self.stop_button.setEnabled(True)
            self.stop_button.setText("Остановить")

        self.setEnabled(True)

    def set_rewrite_controls_enabled(self, has_context: bool):
        self._update_duplicates_toggle_state()