import os
import json
import time
from typing import List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
    QSplitter, QScrollArea, QFrame, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor

from app.core.controller import ParserController
from app.core.memory import MemoryManager
from app.config import BASE_APP_DIR, RESULTS_DIR
from app.ui.pages.analytics import AnalyticsWidget
from app.ui.windows.search_widget import SearchWidget
from app.ui.windows.controls_widget import ControlsWidget
from app.ui.windows.queue_state_manager import QueueStateManager
from app.ui.windows.settings_manager import SettingsDialog
from app.ui.widgets.results_area import ResultsAreaWidget
from app.ui.widgets.ai_stats_panel import AIStatsPanel
from app.ui.widgets.progress_and_logs_panel import ProgressAndLogsPanel
from app.ui.styles import Components, Palette, Spacing, Typography
from app.ui.widgets.rag_stats_panel import RAGStatsPanel

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.memory_manager = MemoryManager()
        self.controller = ParserController(memory_manager=self.memory_manager)
        self.controller.ai_result_ready.connect(self._on_ai_result_with_memory)
        
        self.queue_manager = QueueStateManager()
        self.current_results = []
        self.current_json_file = None
        self.is_sequence_running = False
        self.cnt_parser = 0
        self.cnt_neuro = 0
        self.parser_progress_timer = None
        self.current_search_mode = "full"
        self.app_settings = self._load_settings()
        self.init_ui()
        self._connect_signals()
        self._restore_queues_from_state()
        self._start_timers()
        self.rag_rebuild_timer = QTimer(self)
        self.rag_rebuild_timer.timeout.connect(self.rebuild_rag_cache)
        self.rag_rebuild_timer.start(600000)  # 10 минут = 600000 мс
        QTimer.singleShot(100, self._check_ai_availability)
        QTimer.singleShot(0, self._apply_initial_size)
        QTimer.singleShot(0, self.center_on_current_screen)
        self._load_queue_to_ui(0)

    def init_ui(self):
        self.setWindowTitle("Avito Assist")
        self.setStyleSheet(Components.main_window())
        self.setObjectName("ParserWidget")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self._init_top_bar(main_layout)
        self._init_navigation(main_layout)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        self.parser_page = self._create_parser_page()
        self.stack.addWidget(self.parser_page)
        self.analytics_page = self._create_analytics_page()
        self.stack.addWidget(self.analytics_page)
        self.btn_parser.setChecked(True)
        self.stack.setCurrentIndex(0)

    def _init_top_bar(self, parent_layout):
        top_bar = QWidget()
        top_bar.setStyleSheet(f"background-color: {Palette.BG_DARK}; border-bottom: 1px solid {Palette.BORDER_SOFT};")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        
        title = QPushButton("AVITO ASSIST")
        title.setFlat(True)
        title.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 16px; border: none; text-align: left;")
        top_layout.addWidget(title)
        top_layout.addStretch()
        
        self.settings_button = QPushButton("⚙ Настройки")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Palette.TEXT_MUTED};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                padding: {Spacing.XS}px {Spacing.MD}px;
            }}
            QPushButton:hover {{
                color: {Palette.TEXT};
                border-color: {Palette.TEXT_MUTED};
                background: {Palette.BG_DARK_2};
            }}
        """)
        self.settings_button.clicked.connect(self._on_settings_clicked)
        top_layout.addWidget(self.settings_button)
        parent_layout.addWidget(top_bar)

    def _init_navigation(self, parent_layout):
        nav_container = QWidget()
        nav_container.setStyleSheet(f"background-color: {Palette.BG_DARK};")
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        nav_layout.setSpacing(Spacing.MD)
        self.btn_parser = QPushButton("ПАРСЕР")
        self.btn_analytics = QPushButton("АНАЛИТИКА")
        for btn in (self.btn_parser, self.btn_analytics):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setStyleSheet(Components.nav_button())
        nav_layout.addWidget(self.btn_parser)
        nav_layout.addWidget(self.btn_analytics)
        nav_layout.addStretch()
        parent_layout.addWidget(nav_container)
        self.btn_parser.clicked.connect(lambda: self._switch_page(0))
        self.btn_analytics.clicked.connect(lambda: self._switch_page(1))

    def _create_parser_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_scroll = QScrollArea()
        top_scroll.setWidgetResizable(True)
        top_scroll.setFrameShape(QFrame.Shape.NoFrame)
        top_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        top_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        top_content = QWidget()
        top_layout = QVBoxLayout(top_content)
        top_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        top_layout.setSpacing(Spacing.GAP_SECTION)

        self.search_widget = SearchWidget()
        top_layout.addWidget(self.search_widget)

        self.controls_widget = ControlsWidget()
        top_layout.addWidget(self.controls_widget)

        stats_container = QWidget()
        stats_layout = QHBoxLayout(stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(Spacing.MD)

        self.ai_stats_panel = AIStatsPanel(self)
        stats_layout.addWidget(self.ai_stats_panel)

        self.rag_stats_panel = RAGStatsPanel(self)
        self.rag_stats_panel.navigate_to_rag.connect(self._open_rag_tab)
        stats_layout.addWidget(self.rag_stats_panel)

        self.search_widget.attach_ai_stats(stats_container)

        self.progress_panel = ProgressAndLogsPanel()
        self.controls_widget.attach_progress_panel(self.progress_panel)

        top_scroll.setWidget(top_content)
        self.results_area = ResultsAreaWidget(self)
        self.results_area.context_cleared.connect(self._on_results_context_cleared)
        #self.results_area.results_table.itemSelectionChanged.connect(self._on_result_selected)
        self._refresh_merge_targets()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(9)
        splitter.addWidget(top_scroll)
        splitter.addWidget(self.results_area)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        splitter.setCollapsible(0, True)
        splitter.setSizes([600, 300])

        layout.addWidget(splitter)
        return page

    def _create_analytics_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        self.analytics_widget = AnalyticsWidget(self.memory_manager)
        layout.addWidget(self.analytics_widget)
        return page

    def _connect_signals(self):
        self.controller.parser_started.connect(self._on_parser_started_logic)
        self.controller.progress_updated.connect(self._on_parser_progress)
        self.controller.queue_finished.connect(self._on_queue_finished)
        self.controller.parser_finished.connect(self._on_parsing_finished)
        self.controller.error_occurred.connect(lambda msg: self.progress_panel.parser_log.error(msg))
        self.controller.ui_lock_requested.connect(self.controls_widget.set_ui_locked)
        self.controller.request_increment.connect(self._on_request_increment)
        self.controller.ai_progress_updated.connect(self._on_ai_progress)
        self.controller.ai_batch_finished.connect(lambda: self.progress_panel.ai_log.success("AI пакет обработан"))
        self.controller.scan_finished.connect(self._on_scan_finished)
        self.controller.ai_all_finished.connect(self._on_ai_all_finished)
        self.search_widget.scan_categories_requested.connect(lambda tags: self.controller.scan_categories(tags))
        self.search_widget.categories_selected.connect(self._on_categories_selected)
        self.controls_widget.start_requested.connect(self._on_start_search)
        self.controls_widget.stop_requested.connect(self._on_stop_search)
        self.controls_widget.parameters_changed.connect(self._on_parameters_changed)
        if hasattr(self.controls_widget, 'queue_manager_widget'):
            self.controls_widget.queue_manager_widget.queue_changed.connect(self._on_queue_changed)
            self.controls_widget.queue_manager_widget.queue_removed.connect(self.queue_manager.delete_queue)
            self.controls_widget.queue_manager_widget.queue_toggled.connect(self._on_queue_toggled)
        self.results_area.file_loaded.connect(self._on_file_loaded)
        self.results_area.file_deleted.connect(self._on_file_deleted)
        self.results_area.table_item_deleted.connect(self._on_table_item_deleted)
        self.controls_widget.pause_neuronet_requested.connect(self._on_pause_neuronet_requested)
        self.analytics_widget.send_message_signal.connect(self.on_chat_message_sent)
        self.controller.ai_chat_reply.connect(self.analytics_widget.on_ai_reply)

    def _save_current_queue_state(self):
        idx = self.queue_manager.get_current_index()
        state = self.controls_widget.get_parameters()
        state.update({
            "search_tags": self.search_widget.get_search_tags(),
            "ignore_tags": self.search_widget.get_ignore_tags(),
            "forced_categories": self.search_widget.get_forced_categories()
        })
        self.queue_manager.set_state(state, idx)
    
    def _sync_queues_with_ui(self):
        """Оставляет в менеджере только те очереди, что реально есть в списке UI."""
        if not hasattr(self.controls_widget, "queue_manager_widget"):
            return

        ui_mgr = self.controls_widget.queue_manager_widget
        ui_count = ui_mgr.get_all_queues_count()  # количество строк в QListWidget

        # 1) Гарантируем, что для каждого индекса в UI есть состояние
        for idx in range(ui_count):
            self.queue_manager.get_state(idx)  # _ensure_queue_exists внутри

        # 2) Удаляем все очереди с индексами >= ui_count (их уже нет в UI)
        for idx in list(self.queue_manager.get_all_queue_indices()):
            if idx >= ui_count:
                self.queue_manager.delete_queue(idx)

    def _restore_queues_from_state(self):
        """Досоздаёт строки очередей в UI под все сохранённые индексы."""
        if not hasattr(self.controls_widget, "queue_manager_widget"):
            return

        indices = self.queue_manager.get_all_queue_indices()
        if not indices:
            return

        ui_mgr = self.controls_widget.queue_manager_widget

        # Досоздаём очереди в UI, пока их меньше, чем сохранённых состояний
        while ui_mgr.get_all_queues_count() < len(indices):
            ui_mgr.add_queue()

        # Проставляем включенность чекбоксов из состояния
        for idx in indices:
            state = self.queue_manager.get_state(idx)
            is_enabled = state.get("queue_enabled", True)
            ui_mgr.set_queue_checked(idx, is_enabled)

    def _load_queue_to_ui(self, index: int):
        self.queue_manager.set_current_index(index)
        state = self.queue_manager.get_state(index)
        
        self.search_widget.set_search_tags(state.get("search_tags", []))
        self.search_widget.set_ignore_tags(state.get("ignore_tags", []))
        self.search_widget.set_forced_categories(state.get("forced_categories", []))
        self.controls_widget.set_parameters(state)
        
        is_enabled = state.get("queue_enabled", True)
        if hasattr(self.controls_widget, 'queue_manager_widget'):
            self.controls_widget.queue_manager_widget.set_queue_checked(index, is_enabled)
            
        self.progress_panel.parser_log.info(f"Загружена очередь #{index + 1}")

    def _on_queue_changed(self, new_index: int):
        self._save_current_queue_state()
        self._load_queue_to_ui(new_index)

    def _on_queue_toggled(self, index: int, is_checked: bool):
        """
        ✅ Немедленно синхронизируем состояние при клике на чекбокс
        """
        # СРАЗУ обновляем состояние в памяти
        self.queue_manager.update_state({"queue_enabled": is_checked}, index)
        
        # Логируем действие
        status = "включена ✓" if is_checked else "отключена ✗"
        self.progress_panel.parser_log.info(f"Очередь #{index + 1} {status}")
        
        # ⚠️ ВАЖНО: Если парсер уже запущен и очередь отключена,
        # это может потребовать остановки. Но в текущей логике
        # это не влияет на уже запущенный процесс (как и должно быть)

    def _on_pause_neuronet_requested(self):
        self.progress_panel.ai_log.warning("Функция паузы нейросети еще не реализована в контроллере.")

    def _on_start_search(self):
        self._save_current_queue_state()
        
        # Собираем только ВКЛЮЧЕННЫЕ очереди
        all_indices = self.queue_manager.get_all_queue_indices()
        active_configs = []
        
        for idx in all_indices:
            state = self.queue_manager.get_state(idx)
            if state.get("queue_enabled", True):
                # Валидация тегов
                if not state.get("search_tags"):
                    self.progress_panel.parser_log.warning(f"Очередь #{idx+1} пропущена: нет тегов")
                    continue
                # Добавляем оригинальный индекс очереди для корректного переключения UI
                state['original_index'] = idx
                active_configs.append(state)
        
        if not active_configs:
            QMessageBox.warning(self, "Ошибка", "Нет активных очередей с тегами для поиска!")
            return

        self.is_sequence_running = True
        self.controls_widget.set_ui_locked(True)
        
        # Берем режим поиска из первой активной очереди (или текущей, для UI)
        self.current_search_mode = active_configs[0].get("search_mode", "full")
        self.cnt_parser = 0
        self.cnt_neuro = 0
        
        # Подготовка глобального файла, если разделение выключено
        first_config = active_configs[0]
        split_results = first_config.get("split_results", False)
        
        if not split_results:
            merge_file = first_config.get("merge_with_table")
            if merge_file and os.path.exists(merge_file):
                self.current_json_file = merge_file
                self.current_results = self._load_results_file_silent(merge_file)
                self.progress_panel.parser_log.info(f"Режим добавления: {os.path.basename(merge_file)}")
            else:
                self._create_new_results_file()
                self.current_results = []
                self.progress_panel.parser_log.info("Режим слияния: Создан новый файл для всех очередей")
        
        base_count = len(self.current_results or [])

        # Конфигурируем очереди
        for cfg in active_configs:
            cfg['debug_mode'] = self.app_settings.get('debug_mode', False)
            cfg['ai_debug_mode'] = self.app_settings.get('ai_debug', False)
            
            if not split_results:
                cfg['context_table'] = self.current_json_file
            else:
                cfg['context_table'] = None

            cfg['ai_offset'] = base_count
        
        # Переключаем UI на первую активную очередь
        if active_configs:
            first_idx = active_configs[0]['original_index']
            self.queue_manager.set_current_index(first_idx)
            if hasattr(self.controls_widget, 'queue_manager_widget'):
                self.controls_widget.queue_manager_widget.set_current_queue(first_idx)
            self._load_queue_to_ui(first_idx)
                
        self.controller.start_sequence(active_configs)
        self.progress_panel.parser_log.info(f"🚀 Запуск {len(active_configs)} очередей...")

    def _on_stop_search(self):
        # 1. Сообщаем контроллеру об остановке
        self.controller.request_soft_stop()
        self.progress_panel.parser_log.warning("Остановка по запросу пользователя...")
        
        # 2. Визуально блокируем кнопку стоп, чтобы не тыкали много раз
        if hasattr(self.controls_widget, 'btn_stop'):
            self.controls_widget.stop_button.setEnabled(False)
            self.controls_widget.stop_button.setText("Останавливаемся...")

        # 3. Принудительно сбрасываем флаг последовательности
        self.is_sequence_running = False
        if self.controller.queue_state:
            self.controller.queue_state.is_sequence_running = False

        # 4. Создаем "страховочный" таймер. 
        # Если через 2 секунды штатный сигнал finished не придет, мы сбросим UI вручную.
        QTimer.singleShot(2000, self._force_ui_reset)

    def _force_ui_reset(self):
        """Гарантированно возвращает интерфейс в исходное состояние"""
        self.controls_widget.set_ui_locked(False)
        self.progress_panel.parser_bar.setValue(0)
        # Возвращаем текст кнопке стоп (set_ui_locked это сделает, но для надежности)
        if hasattr(self.controls_widget, 'btn_stop'):
            self.controls_widget.stop_button.setText("Остановить")

    def _on_parameters_changed(self, params: dict):
        merge_target = params.get("merge_with_table")
        if hasattr(self.results_area, "mini_browser"):
            self.results_area.mini_browser.set_merge_target(merge_target)
        
        is_split = params.get("split_results", False)
        has_context = bool(merge_target and not is_split)
        
        self.controls_widget.set_rewrite_controls_enabled(has_context)

    def _merge_results(self, new_items: List[Dict], base_items: List[Dict], rewrite_duplicates: bool):
        base_map = {str(item.get("id", "")): item for item in base_items if item.get("id")}
        added = 0
        updated = 0
        skipped = 0
        processed_ids = set()
        new_entries = []
        
        for item in new_items:
            iid = str(item.get("id", ""))
            if not iid: continue
            
            if iid in base_map:
                if rewrite_duplicates:
                    old = base_map[iid]
                    user_flags = {
                        "starred": old.get("starred", False),
                        "ai_comment": old.get("ai_comment", "") if not item.get("ai_comment") else item.get("ai_comment")
                    }
                    base_map[iid].update(item)
                    base_map[iid].update(user_flags)
                    updated += 1
                else: 
                    skipped += 1
            else:
                if iid not in processed_ids:
                    item.setdefault("starred", False)
                    new_entries.append(item)
                    added += 1
            processed_ids.add(iid)
            
        final_list = list(base_map.values()) + new_entries
        return final_list, added, updated, skipped

    def _on_parsing_finished(self, results: List[Dict]):
        idx = self.controller.queue_state.current_queue_index
        if idx < len(self.controller.queue_state.queues_config):
            config = self.controller.queue_state.queues_config[idx]
        else:
            config = self.controls_widget.get_parameters()
            
        split_results = config.get("split_results", False)
        rewrite = config.get("rewrite_duplicates", False)
        
        if split_results:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            # Получаем оригинальный номер очереди для имени файла, если есть
            q_num = config.get('original_index', idx) + 1
            filename = f"avito_search_q{q_num}_{timestamp}.json"
            target_file = os.path.join(RESULTS_DIR, filename)
            base_items = []
            
            merged, added, updated, skipped = self._merge_results(results, base_items, rewrite)
            self._save_list_to_file(merged, target_file)
            self.progress_panel.parser_log.success(f"Очередь #{q_num}: Сохранено в {filename}")
            
        else:
            if not self.current_json_file:
                 self._create_new_results_file()
            
            base_items = self.current_results
            merged, added, updated, skipped = self._merge_results(results, base_items, rewrite)
            self.current_results = merged
            
            self._save_results_to_file()
            # q_num = config.get('original_index', idx) + 1
            # self.progress_panel.parser_log.success(f"Очередь #{q_num}: Добавлено {added}, Обновлено {updated}")
        
        if not split_results:
             self.results_area.load_full_history(self.current_results)
             if self.current_json_file:
                basename = os.path.basename(self.current_json_file).replace("avito_", "").replace(".json", "")
                fulldate = time.strftime("%d.%m.%Y %H:%M")
                self.results_area.update_header(
                    table_name=basename,
                    full_date=fulldate,
                    count=len(self.current_results)
                )

        self.results_area.mini_browser.refresh_files()
        
        if not self.controller.queue_state.is_sequence_running:
            self.controls_widget.set_ui_locked(False)
            self.is_sequence_running = False
            self.progress_panel.parser_bar.setValue(100)

    def _create_new_results_file(self):
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f"avito_search_{timestamp}.json"
        self.current_json_file = os.path.join(RESULTS_DIR, filename)

    def _save_results_to_file(self):
        if not self.current_json_file: return
        self._save_list_to_file(self.current_results, self.current_json_file)

    def _save_list_to_file(self, data: list, filepath: str):
        import gzip
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._refresh_merge_targets()
        except Exception as e:
            self.progress_panel.parser_log.error(f"Save failed: {e}")

    def _on_parser_started_logic(self):
        self.progress_panel.parser_bar.setValue(0)
        self.progress_panel.ai_bar.setValue(0)
        
    def _on_queue_finished(self, results, idx, is_split):
        config = {}
        if idx < len(self.controller.queue_state.queues_config):
            config = self.controller.queue_state.queues_config[idx]
        q_num = config.get('original_index', idx) + 1
        
        self.progress_panel.parser_log.info(f"Очередь #{q_num} завершена. Получено {len(results)} шт.")
        
        # Переключение UI на следующую очередь (если есть)
        next_idx = idx + 1
        if next_idx < len(self.controller.queue_state.queues_config):
            next_config = self.controller.queue_state.queues_config[next_idx]
            original_next_idx = next_config.get('original_index', next_idx)
            
            # Переключаем UI
            self.queue_manager.set_current_index(original_next_idx)
            if hasattr(self.controls_widget, 'queue_manager_widget'):
                self.controls_widget.queue_manager_widget.set_current_queue(original_next_idx)
            
            # Загружаем настройки, чтобы пользователь видел, что выполняется
            self._load_queue_to_ui(original_next_idx)

    def _on_parser_progress(self, val: int):
        self.progress_panel.parser_bar.setValue(val)

    def _check_ai_availability(self):
        self.controller.ensure_ai_manager()
        
        if not self.controller.ai_manager.has_model():
            self._disable_ai_features()
            self._show_no_model_notification()
        else:
            self._enable_ai_features()

    def _show_no_model_notification(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle("AI модель не найдена")
        msg_box.setText(
            "<b>Модель нейросети не обнаружена</b><br><br>"
            "Все ИИ-функции будут недоступны до установки модели:<br>"
            "• Вкладка \"Аналитика\"<br>"
            "• Режим поиска \"Нейро\"<br>"
            "• Опции \"Вкл. в анализ\" и \"RAG\"<br><br>"
            "Откройте <b>Настройки → Нейросеть</b> для скачивания стандартной модели."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setStyleSheet(Components.dialog())
        msg_box.exec()

    def _enable_ai_features(self):
        self.btn_analytics.setEnabled(True)
        self.btn_analytics.setToolTip("")
        self.btn_analytics.setStyleSheet(Components.nav_button())
        
        if hasattr(self.search_widget, 'search_mode_widget'):
            mode_widget = self.search_widget.search_mode_widget
            if hasattr(mode_widget, 'btn_neuro'):
                mode_widget.btn_neuro.setEnabled(True)
                mode_widget.btn_neuro.setToolTip("Анализ с ИИ")
                mode_widget._update_buttons()
        
        if hasattr(self.controls_widget, 'include_ai_sw'):
            self.controls_widget.include_ai_sw.setEnabled(True)
            self.controls_widget.include_ai_sw.setToolTip("")

            if hasattr(self.controls_widget, 'include_ai_lbl'):
                # Восстанавливаем текст в зависимости от состояния
                is_on = self.controls_widget.include_ai_sw.isChecked()
                self.controls_widget.include_ai_lbl.setText("Вкл" if is_on else "Выкл")
                self.controls_widget.include_ai_lbl.setStyleSheet(
                    Typography.style(
                        family=Typography.UI,
                        size=Typography.SIZE_SMALL,
                        weight=Typography.WEIGHT_BOLD if is_on else Typography.WEIGHT_NORMAL,
                        color=Palette.SECONDARY if is_on else Palette.TEXT_MUTED
                    )
                )
        
        if hasattr(self.controls_widget, 'store_memory_sw'):
            self.controls_widget.store_memory_sw.setEnabled(True)
            self.controls_widget.store_memory_sw.setToolTip("")
            self.controls_widget.store_memory_sw.setEnabled(self.controller.ai_manager.has_model()) 

            if hasattr(self.controls_widget, 'store_memory_lbl'):
                is_on = self.controls_widget.store_memory_sw.isChecked()
                self.controls_widget.store_memory_lbl.setText("Вкл" if is_on else "Выкл")
                self.controls_widget.store_memory_lbl.setStyleSheet(
                    Typography.style(
                        family=Typography.UI,
                        size=Typography.SIZE_SMALL,
                        weight=Typography.WEIGHT_BOLD if is_on else Typography.WEIGHT_NORMAL,
                        color=Palette.SECONDARY if is_on else Palette.TEXT_MUTED
                    )
                )
        
        if hasattr(self.controls_widget, 'ai_criteria_container'):
            mode = self.controls_widget.search_mode_widget.get_mode()
            self.controls_widget.ai_criteria_container.setEnabled(mode == "neuro")

            if hasattr(self.controls_widget, 'ai_criteria_input'):
                self.controls_widget.ai_criteria_input.setPlaceholderText(
                    "Например: только на гарантии, белый цвет..."
                )
                self.controls_widget.ai_criteria_input.setStyleSheet(
                    Components.text_input()
                )
        
        self.progress_panel.ai_log.success("ИИ функции доступны")

        if hasattr(self, '_model_was_just_downloaded') and self._model_was_just_downloaded:
            self._model_was_just_downloaded = False
            QMessageBox.information(
                self,
                "ИИ активирован",
                "Модель успешно загружена!\n"
                "Все ИИ-функции теперь доступны:\n\n"
                "• Вкладка Аналитика\n"
                "• Режим поиска Нейро\n"
                "• Опции \"Вкл. в анализ\" и \"RAG\"",
                QMessageBox.StandardButton.Ok
            )

    def _disable_ai_features(self):
        # 1. Блокируем вкладку Аналитика
        self.btn_analytics.setEnabled(False)
        self.btn_analytics.setToolTip("Требуется модель нейросети. Откройте 'Настройки'.")
        
        self.btn_analytics.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_DARK_3};
                color: {Palette.TEXT_MUTED};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
                padding: {Spacing.SM}px {Spacing.MD}px;
                opacity: 0.5;
            }}
            QPushButton:hover {{
                border-color: {Palette.WARNING};
                color: {Palette.WARNING};
            }}
        """)

        # 2. Блокируем кнопку "Нейро" в режимах поиска
        if hasattr(self.search_widget, 'search_mode_widget'):
            mode_widget = self.search_widget.search_mode_widget
            if hasattr(mode_widget, 'btn_neuro'):
                mode_widget.btn_neuro.setEnabled(False)
                mode_widget.btn_neuro.setToolTip(
                    "Нейро-режим недоступен\n"
                    "Требуется модель AI\n\n"
                    "Откройте Настройки → Нейросеть для установки"
                )

                # Визуальный стиль заблокированной кнопки
                mode_widget.btn_neuro.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Palette.BG_DARK_3};
                        border: 1px solid {Palette.BORDER_SOFT};
                        border-radius: {Spacing.RADIUS_NORMAL}px;
                        color: {Palette.TEXT_MUTED};
                        padding: {Spacing.XS}px {Spacing.MD}px;
                        text-decoration: line-through;
                    }}
                    QPushButton:hover {{
                        border-color: {Palette.WARNING};
                        background-color: {Palette.with_alpha(Palette.WARNING, 0.1)};
                    }}
                """)

                # Если текущий режим "neuro" - переключаем на "full"
                current_mode = mode_widget.get_mode()
                if current_mode == "neuro":
                    mode_widget.set_mode("full")

        # 3. Блокируем тумблеры AI в контролах
        if hasattr(self.controls_widget, 'include_ai_sw'):
            self.controls_widget.include_ai_sw.setEnabled(False)
            self.controls_widget.include_ai_sw.setChecked(False)
            self.controls_widget.include_ai_sw.setToolTip(
                "Требуется модель нейросети\nОткройте Настройки"
            )

            # Обновляем стиль лейбла
            if hasattr(self.controls_widget, 'include_ai_lbl'):
                self.controls_widget.include_ai_lbl.setText("Недоступно")
                self.controls_widget.include_ai_lbl.setStyleSheet(
                    Typography.style(
                        family=Typography.UI,
                        size=Typography.SIZE_SMALL,
                        color=Palette.TEXT_MUTED
                    )
                )

        if hasattr(self.controls_widget, 'store_memory_sw'):
            self.controls_widget.store_memory_sw.setEnabled(False)
            self.controls_widget.store_memory_sw.setChecked(False)
            self.controls_widget.store_memory_sw.setToolTip(
                "RAG требует модель нейросети"
            )

            if hasattr(self.controls_widget, 'store_memory_lbl'):
                self.controls_widget.store_memory_lbl.setText("Недоступно")
                self.controls_widget.store_memory_lbl.setStyleSheet(
                    Typography.style(
                        family=Typography.UI,
                        size=Typography.SIZE_SMALL,
                        color=Palette.TEXT_MUTED
                    )
                )
        
        # 4. Блокируем AI Criteria
        if hasattr(self.controls_widget, 'ai_criteria_container'):
            self.controls_widget.ai_criteria_container.setEnabled(False)

            # Добавляем визуальное затемнение
            if hasattr(self.controls_widget, 'ai_criteria_input'):
                self.controls_widget.ai_criteria_input.setPlaceholderText(
                    "Недоступно: требуется модель нейросети"
                )
                self.controls_widget.ai_criteria_input.setStyleSheet(
                    Components.text_input() + f"""
                    QPlainTextEdit {{
                        background-color: {Palette.BG_DARK_2};
                        color: {Palette.TEXT_MUTED};
                        opacity: 0.5;
                    }}
                    """
                )
        
        self.progress_panel.ai_log.warning("ИИ функции отключены: модель не найдена")
        self.progress_panel.ai_log.info("Откройте Настройки → Нейросеть для установки модели")

    def on_chat_message_sent(self, messages: list):
        """Обработка отправки сообщения в чат"""
        if not self.controller.ai_manager:
            self.analytics_widget.on_ai_reply("❌ AI не доступен. Загрузите модель в настройках.")
            return

        # Отправляем в AI Manager
        debug_mode = self.app_settings.get('ai_debug', False)
        self.controller.send_chat_message(messages, debug_mode=debug_mode)


    def rebuild_rag_cache(self):
        """Фоновая агрегация RAG-статистики (каждые 10 минут)"""
        if self.is_sequence_running:
            return

        print("[MainWindow] 🔄 Background RAG rebuild started...")

        # Запускаем в фоне
        import threading
        def rebuild_task():
            try:
                count = self.memory_manager.rebuild_statistics_cache()
                print(f"[MainWindow] ✅ Background RAG rebuild complete: {count} categories")
                if hasattr(self, "analyticswidget"):
                    self.analytics_widget.refresh_data()
            except Exception as e:
                print("MainWindow RAG rebuild error", e)

        threading.Thread(target=rebuild_task, daemon=True).start()

    def _on_settings_closed_with_model(self):
        if self.controller.ai_manager and self.controller.ai_manager.has_model():
            self._enable_ai_features()
            QMessageBox.information(
                self,
                "ИИ активирован",
                "Модель успешно загружена!\nВсе ИИ-функции теперь доступны.",
                QMessageBox.StandardButton.Ok
            )

    def _on_ai_progress(self, val: int):
        self.progress_panel.ai_bar.setValue(val)

    def _on_ai_result(self, idx, json_text, ctx):
        self.progress_panel.ai_log.info(f"AI обновил элемент #{idx}")

        if 0 <= idx < len(self.current_results):
            self.current_results[idx]["ai_comment"] = json_text
            self.results_area.results_table.update_ai_column(idx, json_text)
            self._save_results_to_file()

    def _on_ai_all_finished(self):
        self.progress_panel.ai_log.success("ИИ анализ завершён")

        ai_column_index = 7
        #self.results_area.results_table.sortItems(ai_column_index, Qt.SortOrder.DescendingOrder)

        #self.progress_panel.ai_log.info("Таблица отсортирована: лучшие предложения вверху")

    def _on_ai_result_with_memory(self, idx: int, ai_json: str, context: dict):
        """Обработка результата AI: разделение на UI и Память"""
        
        # Получаем флаги из контекста
        include_ai = context.get('include_ai', True)
        store_in_memory = context.get('store_in_memory', False)

        # 1. Если включен визуальный анализ - обновляем таблицу UI и JSON файл
        if include_ai:
            self._on_ai_result(idx, ai_json, context)
        
        # 2. Если включен RAG - сохраняем в базу знаний
        if store_in_memory:
            if 0 <= idx < len(self.current_results):
                item = self.current_results[idx].copy() # Копия, чтобы не портить отображение, если include_ai=False
                
                # Парсим ответ AI
                try:
                    import json
                    ai_data = json.loads(ai_json)
                    item.update(ai_data) # Добавляем данные AI к товару
                except Exception as e:
                    print(f"[MainWindow] JSON Parse Error for Memory: {e}")

                # Сохраняем
                success = self.memory_manager.add_item(item)
                
                if success:
                    # Если визуальный анализ выключен, пишем в лог, что сохранили "тихо"
                    if not include_ai:
                        print(f"[MainWindow] 💾 Saved to memory (Silent): {item.get('title', '')[:30]}")
                    else:
                        print(f"[MainWindow] ✅ Saved to memory: {item.get('title', '')[:30]}")

    def _open_rag_tab(self):
        """Переключиться на Аналитику → вкладка RAG‑статус"""
        # Страница Аналитика
        self._switch_page(1)
        # Вкладка RAG‑статус (первая)
        if hasattr(self.analytics_widget, "tabs"):
            self.analytics_widget.tabs.setCurrentIndex(0)

    def _on_scan_finished(self, categories):
        self.search_widget.set_scanned_categories(categories)
        self.progress_panel.parser_log.success(f"Найдено {len(categories)} категорий")

    def _on_categories_selected(self, cats):
        self.progress_panel.parser_log.info(f"Выбрано {len(cats)} категорий")

    def _on_file_loaded(self, path, data):
        self.current_json_file = path 
        self.current_results = data
        self.results_area.load_full_history(data)

        import os
        from datetime import datetime
        basename = os.path.basename(path).replace("avito_", "").replace(".json", "")
        # Добавлена проверка на существование файла во избежание краша, если файл удален извне
        if os.path.exists(path):
            fulldate = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d.%m.%Y %H:%M")
        else:
            fulldate = datetime.now().strftime("%d.%m.%Y %H:%M")
            
        self.results_area.update_header(
            table_name=basename,
            full_date=fulldate,
            count=len(data)
        )

        self.progress_panel.parser_log.info(f"Загружен: {os.path.basename(path)}")
        self._refresh_merge_targets()

    def _on_file_deleted(self, path):
        if self.current_json_file == path:
            self.current_json_file = None
            self.current_results = []
            self.results_area.clear_table()
        self._refresh_merge_targets()

    def _on_results_context_cleared(self):
        self.current_json_file = None
        self.current_results = []
        self.results_area.clear_table()
        self.controls_widget.set_rewrite_controls_enabled(False)
    
    def _on_result_selected(self):
        rows = self.results_area.results_table.selectedItems()
        if not rows:
            return
        # Берем первую выделенную строку, колонка с названием у тебя известна, допустим 2
        row = rows[0].row()
        title_item = self.results_area.results_table.item(row, 2)
        if not title_item:
            return
        title = title_item.text()
        stats = self.memory_manager.get_stats_for_title(title)
        print("[RAG] Stats for selected:", title, "->", stats)

    def _on_table_item_deleted(self, item_id):
        self.current_results = [x for x in self.current_results if str(x.get("id")) != str(item_id)]
        self._save_results_to_file()

    def _on_item_starred(self, item_id, is_starred):
        for x in self.current_results:
            if str(x.get("id")) == str(item_id):
                x["starred"] = is_starred
                break
        self._save_results_to_file()

    def _on_request_increment(self, p_count, ai_count):
        self.cnt_parser += p_count
        self.cnt_neuro += ai_count

    def _refresh_merge_targets(self):
        if hasattr(self.results_area, "mini_browser"):
            files = self.results_area.mini_browser.iter_files()
            targets = []
            for fpath, _, _ in files:
                name = os.path.basename(fpath).replace("avito_", "").replace(".json", "")
                targets.append((fpath, name))
            self.controls_widget.set_merge_targets(targets)
            has_context = bool(self.controls_widget.get_parameters().get("merge_with_table") or self.current_json_file)
            self.controls_widget.set_rewrite_controls_enabled(has_context)

    def _load_results_file_silent(self, path):
        if not path or not os.path.exists(path): return []
        import gzip
        try:
            try:
                with open(path, "r", encoding="utf-8") as f: return json.load(f)
            except:
                with gzip.open(path, "rt", encoding="utf-8") as f: return json.load(f)
        except: return []

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.btn_parser.setChecked(index == 0)
        self.btn_analytics.setChecked(index == 1)
        
        if index == 1:
            # Обновляем все вкладки аналитики
            self.analytics_widget.refresh_data()

    def _on_settings_clicked(self):
        dlg = SettingsDialog(self.app_settings, self)

        dlg.model_downloaded.connect(self._on_model_downloaded)

        if dlg.exec():
            self.app_settings = dlg.get_settings()
            self._save_settings()

            if self.controller.ai_manager:
                self.controller.set_ai_debug_mode(self.app_settings.get("ai_debug", False))

                selected_model = self.app_settings.get("ai_model")
                if selected_model:
                    self.controller.ai_manager.set_model(selected_model)

    def _on_model_downloaded(self, file_path: str):
        self._model_was_just_downloaded = True

        if self.controller.ai_manager:
            model_name = os.path.basename(file_path)
            self.controller.ai_manager.set_model(model_name)

        self._enable_ai_features()

    def _load_settings(self):
        path = os.path.join(BASE_APP_DIR, "app_settings.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}
        
    def _save_settings(self):
        path = os.path.join(BASE_APP_DIR, "app_settings.json")
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(self.app_settings, f, indent=2)
        except: pass

    def _start_timers(self):
        self.ai_stats_timer = QTimer(self)
        self.ai_stats_timer.timeout.connect(self._update_ai_stats)
        self.ai_stats_timer.start(1000)

        self.rag_stats_timer = QTimer(self)
        self.rag_stats_timer.timeout.connect(self._update_rag_stats)
        self.rag_stats_timer.start(5000)

    def _update_ai_stats(self):
        if self.controller.ai_manager:
            stats = self.controller.ai_manager.refresh_resource_usage()
            self.ai_stats_panel.update_stats(stats)

    def _update_rag_stats(self):
        """Обновить RAG статистику в панели"""
        stats = self.memory_manager.get_rag_status()
        self.rag_stats_panel.update_stats(stats)

    def _apply_initial_size(self):
        self.resize(2200, 1320)

    def center_on_current_screen(self):
        app = QApplication.instance()
        screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
        geo = screen.availableGeometry()
        rect = self.frameGeometry()
        rect.moveCenter(geo.center())
        self.move(rect.topLeft())

    def closeEvent(self, event):
        self._save_current_queue_state()
        self._sync_queues_with_ui() 
        self.queue_manager.save_current_state()
        self.controller.cleanup()
        event.accept()