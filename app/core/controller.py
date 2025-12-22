import math
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from app.core.worker import ParserWorker, CategoryScannerWorker
from app.core.ai.ai_manager import AIManager
from app.core.ai.prompts import PromptBuilder
from app.core.log_manager import logger


@dataclass
class QueueState:
    queues_config: List[Dict[str, Any]] = field(default_factory=list)
    current_queue_index: int = 0
    total_queues: int = 0
    is_sequence_running: bool = False
    waiting_for_ai_sequence: bool = False

class ParserController(QObject):
    parser_started = pyqtSignal()
    parser_finished = pyqtSignal(list)

    progress_updated = pyqtSignal(int)
    results_ready = pyqtSignal(list)
    ai_progress_updated = pyqtSignal(int)
    ai_result_ready = pyqtSignal(int, str, dict)
    ai_chat_reply = pyqtSignal(str)
    
    sequence_started = pyqtSignal()
    sequence_finished = pyqtSignal()
    queue_finished = pyqtSignal(list, int, bool)
    cultivation_finished = pyqtSignal()

    filter_group_started = pyqtSignal(list)
    
    ai_batch_finished = pyqtSignal()
    ai_all_finished = pyqtSignal()
    
    scan_finished = pyqtSignal(list)
    
    error_occurred = pyqtSignal(str)
    request_increment = pyqtSignal(int, int)
    
    ui_lock_requested = pyqtSignal(bool)
    
    def __init__(self, memory_manager=None):
        super().__init__()
        
        self.worker: Optional[ParserWorker] = None
        self.worker_thread: Optional[QThread] = None
        self.scan_worker: Optional[CategoryScannerWorker] = None
        self.scan_worker_thread: Optional[QThread] = None
        self.ai_manager: Optional[AIManager] = None
        self.queue_state = QueueState()
        self.zombie_threads: List[QThread] = []
        self.memory_manager = memory_manager
        self.parser_progress_callback = None
        self._is_stopping = False
        self.chunk_manager = None
    
    def set_progress_callback(self, callback):
        self.parser_progress_callback = callback

    def _on_parser_progress(self, value):
        if self.parser_progress_callback:
            self.parser_progress_callback(value)
        self.progress_updated.emit(value)

    def ensure_ai_manager(self):
        if not self.ai_manager:
            self.ai_manager = AIManager(memory_manager=self.memory_manager)
            self.ai_manager.progress_signal.connect(self._on_ai_text_progress)
            self.ai_manager.ai_progress_value.connect(self.ai_progress_updated.emit)
            self.ai_manager.result_signal.connect(self.ai_result_ready.emit)
            self.ai_manager.finished_signal.connect(self._on_ai_batch_finished)
            self.ai_manager.all_finished_signal.connect(self._on_ai_all_finished)
            self.ai_manager.all_finished_signal.connect(self.cultivation_finished.emit)
            self.ai_manager.error_signal.connect(self.error_occurred.emit)
            self.ai_manager.chat_response_signal.connect(self.ai_chat_reply.emit)

    def _on_ai_text_progress(self, text: str):
        logger.info(text, token="ai_progress")

    def set_ai_model(self, model_name: str):
        self.ensure_ai_manager()
        self.ai_manager.set_model(model_name)

    def start_sequence(self, configs):
        if self._is_stopping:
            logger.warning("Дождитесь завершения остановки...")
            return

        self.cleanup_worker()

        self.queue_state.is_sequence_running = True
        self.queue_state.queues_config = configs
        self.queue_state.total_queues = len(configs)
        self.queue_state.current_queue_index = 0
        
        self.session_seen_ids = set() 

        self.sequence_started.emit()
        self.ui_lock_requested.emit(True)

        self._execute_queue(0)
    
    def request_soft_stop(self):
        if self._is_stopping: return
        self._is_stopping = True
        
        if not self.queue_state.is_sequence_running and not (self.worker_thread and self.worker_thread.isRunning()):
            self._finalize_stop()
            return

        self.queue_state.is_sequence_running = False
        self.progress_updated.emit("Остановка по запросу пользователя...")
        if self.worker:
            self.worker.request_stop()
        
        QTimer.singleShot(2000, self._async_force_stop)

    def stop_sequence(self):
        self.request_soft_stop()
    
    def _execute_queue(self, queue_index: int):
        self.cleanup_worker()

        if queue_index >= self.queue_state.total_queues or not self.queue_state.is_sequence_running:
            self._finish_sequence()
            return

        self.queue_state.current_queue_index = queue_index
        config = self.queue_state.queues_config[queue_index]

        logger.info(f"Очередь {queue_index + 1} из {self.queue_state.total_queues}...", token="queue_start")
        
        self.progress_updated.emit(0)

        if not config.get('search_tags'):
            QTimer.singleShot(100, lambda: self._execute_queue(queue_index + 1))
            return
        
        max_items = config.get('max_items', 0)
    
        if max_items and max_items > 0:
             calc_pages = (math.ceil(max_items / 50) * 5) + 3
        else:
             calc_pages = 100

        self.worker_thread = QThread()
        self.worker = ParserWorker(
            keywords=config.get('search_tags', []),
            ignore_keywords=config.get('ignore_tags', []),
            max_pages=calc_pages,
            max_total_items=config.get('max_items', 0) or None,
            min_price=config.get('min_price') or None,
            max_price=config.get('max_price') or None,
            sort_type = config.get('sort_type', 'date'),
            search_all_regions=config.get('all_regions', False),
            debug_mode=config.get('debug_mode', False),
            search_mode=config.get('search_mode', 'full'),
            forced_categories=config.get('forced_categories'),
            filter_defects=config.get('filter_defects', False),
            skip_duplicates = config.get('skip_duplicates', False),
            allow_rewrite_duplicates = config.get('allow_rewrite_duplicates', False),
            existing_ids=self.session_seen_ids
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.started.connect(self.parser_started.emit)
        self.worker.finished.connect(lambda res: self._on_queue_finished(res, queue_index, config))
        self.worker.finished.connect(lambda res: self.on_parser_worker_finished(res))
        self.worker.error.connect(self._on_worker_error)
        self.worker.progress.connect(self.progress_updated.emit)
        self.worker.requests_count.connect(self.request_increment.emit)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.start()
    
    def _on_queue_finished(self, results: List[Dict], queue_idx: int, config: Dict):
        if self._is_stopping: return

        if results:
            for item in results:
                if 'id' in item:
                    self.session_seen_ids.add(str(item['id']))
        else:
            logger.warning(f"Очередь {queue_idx + 1}: результатов не найдено...")
        
        is_split = config.get('is_split', False)

        if self._handle_neuro_filter(results, config, queue_idx, is_split):
            return

        self.queue_finished.emit(results, queue_idx, is_split)

        ai_started = self.maybe_start_post_ai_analysis(results, config, queue_idx, is_split)

        if not ai_started:
            self._advance_or_finish(queue_idx)

    def _handle_neuro_filter(
        self,
        results: List[Dict],
        config: Dict,
        queue_idx: int,
        is_split: bool,
    ) -> bool:
        search_mode = config.get('search_mode', 'full')
        
        if not results: return False

        if search_mode != 'neuro':
            return False

        logger.info("Нейро-фильтрация...")
        self.filter_group_started.emit(results)

        search_tags = config.get('search_tags', [])
        ignore_tags = config.get('ignore_tags', [])
        user_criteria = config.get('ai_criteria', "")

        neuro_prompt = PromptBuilder.build_neuro_filter_prompt(
            search_tags=search_tags,
            ignore_tags=ignore_tags,
            user_criteria=user_criteria
        )

        store_in_mem = config.get('store_in_memory', False)

        self._start_ai_filter(results, neuro_prompt, queue_idx, is_split, store_in_memory=store_in_mem)

        return True

    def maybe_start_post_ai_analysis(
            self, results: List[Dict], config: Dict, queue_idx: int, is_split: bool
        ) -> bool:
        if not results: return False
        include_ai = config.get('include_ai', False)
        store_in_memory = config.get('store_in_memory', False)
        
        if (not include_ai and not store_in_memory):
            return False
            
        if store_in_memory and not include_ai:
            if self.memory_manager:
                logger.info(f"Сохранение {len(results)} товаров в память (без AI анализа)...")
                for item in results:
                    self.memory_manager.add_item(item)
            return False

        user_instructions = "" 

        search_tags = config.get('search_tags', [])
        has_rag = config.get('store_in_memory', False)
        
        priority = PromptBuilder.select_priority(
            table_size=len(results),
            user_instructions=user_instructions,
            has_rag=has_rag,
            search_tags=search_tags
        )
        
        ai_debug = config.get('ai_debug_mode', False)
        store = config.get('store_in_memory', False)
        base_offset = config.get('ai_offset', 0)

        search_mode = config.get('search_mode', 'full')
        
        context = {
            "mode": "analysis",
            "offset": base_offset,
            "queue_idx": queue_idx,
            "is_split": is_split,
            "store_in_memory": store,
            "include_ai": include_ai,
            "priority": priority,
            "user_instructions": user_instructions,
            "has_rag": has_rag,
            "search_mode": search_mode,
            "items": results,
        }
        self.queue_state.waiting_for_ai_sequence = True
        
        self._run_ai_process(results, prompt=None, debug_mode=ai_debug, context=context)
        return True

    def _advance_or_finish(self, queue_idx: int):
        if not self.queue_state.is_sequence_running:
            self._finish_sequence()
            return

        next_idx = queue_idx + 1
        QTimer.singleShot(100, lambda: self._execute_queue(next_idx))

    def _finish_sequence(self):
        self.queue_state.is_sequence_running = False
        self.progress_updated.emit(100)
        self.sequence_finished.emit()
        self.ui_lock_requested.emit(False)
    
    def _async_force_stop(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            QTimer.singleShot(1500, self._check_thread_stopped)
        else:
            self._finalize_stop()
    
    def _check_thread_stopped(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.terminate()
            QTimer.singleShot(500, self._finalize_stop)
        else:
            self._finalize_stop()

    def _finalize_stop(self):
        self.cleanup_worker()
        self._is_stopping = False
        self.queue_state.is_sequence_running = False
        self.ui_lock_requested.emit(False)
        self.progress_updated.emit(0)

    def cleanup_worker(self):
        if self.worker:
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker.request_stop()
            
            self.worker.deleteLater()
            self.worker = None
        
        if self.worker_thread:
            if self.worker_thread.isRunning():
                self.worker_thread.quit()
                self.worker_thread.wait(500)
            
            if self.worker_thread.isRunning():
                old_thread = self.worker_thread
                self.zombie_threads.append(old_thread)
                def on_zombie_finished():
                    if old_thread in self.zombie_threads:
                        self.zombie_threads.remove(old_thread)
                        old_thread.deleteLater()
                old_thread.finished.connect(on_zombie_finished)
            else:
                self.worker_thread.deleteLater()
            
            self.worker_thread = None
    
    def _on_worker_error(self, msg: str):
        self.error_occurred.emit(msg)

        self.queue_state.is_sequence_running = False
        self.queue_state.waiting_for_ai_sequence = False

        self.ui_lock_requested.emit(False)
    
    def scan_categories(self, keywords: List[str], debug_mode: bool = False):
        if not keywords:
            self.error_occurred.emit("Не указаны ключевые слова")
            return
        self.ui_lock_requested.emit(True)
        logger.info("Сканирование категорий...")
        self.scan_worker_thread = QThread()
        self.scan_worker = CategoryScannerWorker(keywords)
        self.scan_worker.moveToThread(self.scan_worker_thread)
        self.scan_worker_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_worker_error)
        self.scan_worker.finished.connect(self.scan_worker_thread.quit)
        self.scan_worker_thread.start()
    
    def _on_scan_finished(self, categories: List[Dict]):
        self.ui_lock_requested.emit(False)
        self.scan_finished.emit(categories)
    
    def start_manual_ai_analysis(self, items: List[Dict], prompt: str, debug_mode: bool = False, store_in_memory: bool = False):
        if not items:
            self.error_occurred.emit("Нет элементов для анализа")
            return

        self.ui_lock_requested.emit(True)

        user_instructions = prompt if prompt else ""

        priority = PromptBuilder.select_priority(
            table_size=len(items),
            user_instructions=user_instructions,
            has_rag=False,
            search_tags=[]
        )

        context = {
            "mode": "analysis",
            "offset": 0,
            "queue_idx": -1,
            "is_split": False,
            "store_in_memory": store_in_memory,
            "include_ai": True,
            "priority": priority,
            "user_instructions": user_instructions,
            "has_rag": False,
            "items": items,
        }

        self._run_ai_process(items, prompt=None, debug_mode=debug_mode, context=context)
    
    def _start_ai_filter(self, items: List[Dict], prompt: str,
                         queue_idx: int, is_split: bool,
                         store_in_memory: bool = False):
        context = {
            "mode": "filter",
            "offset": 0,
            "queue_idx": queue_idx,
            "is_split": is_split,
            "store_in_memory": store_in_memory,
            "items": items,
        }

        self.queue_state.waiting_for_ai_sequence = True

        ai_debug = False
        if 0 <= queue_idx < len(self.queue_state.queues_config):
            ai_debug = self.queue_state.queues_config[queue_idx].get('ai_debug_mode', False)

        self._run_ai_process(items, prompt, debug_mode=ai_debug, context=context)

    
    def _start_ai_analysis(self, items: List[Dict], prompt: str, parallel: bool, queue_idx: int, is_split: bool, store_in_memory: bool = False):
        context = {
            'mode': 'analysis',
            'offset': 0,
            'parallel': parallel,
            'queue_idx': queue_idx,
            'is_split': is_split,
            'store_in_memory': store_in_memory,
        }

        ai_criteria = ""
        ai_debug = False
        if 0 <= queue_idx < len(self.queue_state.queues_config):
            cfg = self.queue_state.queues_config[queue_idx]
            ai_criteria = cfg.get('ai_criteria', "")
            ai_debug = cfg.get('ai_debug_mode', False)

        market_prompt = self._build_market_context_prompt(items, ai_criteria)

        if parallel:
            self._run_ai_process(items, market_prompt, debug_mode=ai_debug, context=context)
            if self.queue_state.is_sequence_running:
                QTimer.singleShot(100, lambda: self._execute_queue(queue_idx + 1))
            else:
                self.queue_state.waiting_for_ai_sequence = True
                self._run_ai_process(items, market_prompt, debug_mode=ai_debug, context=context)
        else:
            self.queue_state.waiting_for_ai_sequence = True
            self._run_ai_process(items, market_prompt, debug_mode=ai_debug, context=context)

    def _run_ai_process(self, items: List[Dict], prompt: str, debug_mode: bool, context: Dict):
        if not items: return
        self.ensure_ai_manager()
        self.ai_manager._debug_logs = debug_mode
        self.ai_manager.start_processing(items, prompt, debug_mode=debug_mode, context=context)
    
    def send_chat_message(self, messages: list, debug_mode: bool = False):
        self.ensure_ai_manager()
        self.ai_manager._debug_logs = debug_mode
        self.ai_manager.start_chat_request(messages)
    
    def start_cultivation(self):
        if self.chunk_manager:
            user_instr = ""
            if hasattr(self.parent(), '_get_current_ai_instructions'):
                user_instr = self.parent()._get_current_ai_instructions()

            logger.info("Запуск актуализации памяти...", token="ai-cult")
            self.chunk_manager.request_user_cultivation(user_instructions=user_instr)
        else:
            logger.error("Менеджер \"Памяти ИИ\" не инициализирован...")

    def _on_cultivation_finished(self):
        logger.info("Культивация завершена...", token="ai-cult")
        self.ui_lock_requested.emit(False)

    def on_parser_worker_finished(self, results: list):
        self.parser_finished.emit(results) 

    def _on_ai_batch_finished(self):
        self.ai_batch_finished.emit()
        if self.queue_state.waiting_for_ai_sequence:
            self.queue_state.waiting_for_ai_sequence = False
            next_idx = self.queue_state.current_queue_index + 1
            QTimer.singleShot(100, lambda: self._execute_queue(next_idx))

    def _on_ai_all_finished(self):
        self.ai_all_finished.emit()
        if not self.queue_state.is_sequence_running:
            self.ui_lock_requested.emit(False)

    def has_active_tasks(self) -> bool:
        return self.queue_state.is_sequence_running or (self.ai_manager and self.ai_manager.has_pending_tasks())

    def get_total_queues(self) -> int:
        return self.queue_state.total_queues
    
    def cleanup(self):
        self._is_stopping = True
        
        if self.queue_state.is_sequence_running:
            self.stop_sequence()
            
        self.cleanup_worker()

        if self.scan_worker:
            self.scan_worker.deleteLater()
            self.scan_worker = None

        if self.scan_worker_thread:
            if self.scan_worker_thread.isRunning():
                self.scan_worker_thread.quit()
                self.scan_worker_thread.wait(1000)
            self.scan_worker_thread.deleteLater()
            self.scan_worker_thread = None

        for thread in self.zombie_threads:
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
            thread.deleteLater()

        self.zombie_threads.clear()

        if self.ai_manager:
            try:
                self.ai_manager.cleanup()
            except Exception as e:
                logger.dev(f"AIManager cleanup error: {e}", level="ERROR")
            self.ai_manager = None