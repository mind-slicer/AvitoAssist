from __future__ import annotations
from enum import Enum
from typing import Optional, Dict
from datetime import datetime
import json

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from app.core.ai.ai_manager import AIChunkCultivationWorker
from app.core.log_manager import logger
from app.core.ai.prompts import ChunkCultivationPrompts

class ChunkType(Enum):
    PRODUCT = "ПРОДУКТ"
    CATEGORY = "КАТЕГОРИЯ"
    DATABASE = "БАЗА ДАННЫХ"
    AI_BEHAVIOR = "ПОВЕДЕНИЕ ИИ"
    CUSTOM = "ПОЛЬЗОВАТЕЛЬСКИЙ"

class ChunkStatus(Enum):
    PENDING = "В ОЖИДАНИИ"
    INITIALIZING = "ИНИЦИАЛИЗАЦИЯ"
    ACCUMULATING = "НАКОПЛЕНИЕ"
    READY = "ГОТОВ"
    COMPRESSED = "СЖАТ"
    FAILED = "ОШИБКА"

class ChunkCultivationTrigger(Enum):
    TIME_ELAPSED = "TIME_ELAPSED"
    DATA_VOLUME = "DATA_VOLUME"
    LLM_DECISION = "LLM_DECISION"
    USER_BUTTON = "USER_BUTTON"

class ChunkCultivationManager(QObject):
    cultivation_ready = pyqtSignal(int)
    chunk_status_changed = pyqtSignal(int, str)
    chunk_progress = pyqtSignal(int, int, str)

    def __init__(self, memory_manager, ai_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self.ai = ai_manager

        self._cultivation_timer = QTimer(self)
        self._cultivation_timer.timeout.connect(self._check_triggers)
        self._cultivation_timer.start(60_000)

        self._integrity_timer = QTimer(self)
        self._integrity_timer.timeout.connect(self.validate_chunks_integrity)
        self._integrity_timer.start(300_000)

        self.default_time_threshold = 30 * 60
        self.default_data_threshold = 30

    def validate_chunks_integrity(self): # TODO
        logger.dev("Запуск проверки целостности знаний...", level="DEBUG")
        chunks = self.memory.knowledge.get_knowledge(status='READY')
        
        updated_count = 0
        
        for chunk in chunks:
            chunk_id = chunk['id']
            stored_hash = chunk.get('source_hash')
            
            if not stored_hash:
                continue
                
            key = chunk.get('chunk_key')
            ctype = chunk.get('chunk_type')
            
            current_hash = None
            if ctype == 'CATEGORY':
                current_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
            else:
                current_hash = self.memory.raw_data.calculate_data_signature(product_key=key)
            
            if current_hash != stored_hash:
                logger.info(f"Чанк {chunk_id} ({key}) устарел. Данные изменились.", token="ai-mem")
                self.memory.update_chunk_status(chunk_id, 'PENDING')
                self.chunk_status_changed.emit(chunk_id, 'PENDING')
                updated_count += 1
        
        if updated_count > 0:
            logger.info(f"Помечено на обновление: {updated_count} чанков.", token="ai-mem")

    def _on_worker_timeout(self, chunk_id: int):
        logger.error(f"Таймаут культивации чанка {chunk_id}. Принудительная отмена.", token="ai-cult")
        self.cancel_task(chunk_id)
        self.ai._is_cultivating_now = False
        self.memory.update_chunk_status(chunk_id, ChunkStatus.FAILED.value)
        self.chunk_status_changed.emit(chunk_id, ChunkStatus.FAILED.value)
        self._process_cultivation_queue()

    def cancel_task(self, chunk_id: int):
        if not self.ai: return

        if hasattr(self, '_active_timeout_chunk') and self._active_timeout_chunk == chunk_id:
            if hasattr(self, '_timeout_timer') and self._timeout_timer.isActive():
                self._timeout_timer.stop()
            self._active_timeout_chunk = None

        initial_len = len(self.ai._cultivation_queue)
        self.ai._cultivation_queue = [t for t in self.ai._cultivation_queue if t['id'] != chunk_id]

        if len(self.ai._cultivation_queue) < initial_len:
            logger.info(f"Чанк {chunk_id} удален из очереди культивации.", token="ai-cult")

        if chunk_id in self.ai._chunk_workers:
            logger.warning(f"Прерывание активной культивации чанка {chunk_id}...", token="ai-cult")
            worker = self.ai._chunk_workers[chunk_id]
            worker.stop()
            worker.quit()
            worker.wait(1000)
            if worker.isRunning():
                worker.terminate()
            
            self.ai._chunk_workers.pop(chunk_id, None)
            self.ai._is_cultivating_now = False
            
            QTimer.singleShot(1000, self._process_cultivation_queue)

    def check_and_cultivate(self):
        pending_chunks = self.memory.get_pending_chunks()
        if not pending_chunks:
            return

        for chunk in pending_chunks:
            trigger = self._evaluate_triggers(chunk)
            if trigger:
                self._initiate_cultivation(chunk, trigger)

    def create_pending_chunk(self, chunk_type, chunk_key: str, title: str) -> int:
        if isinstance(chunk_type, Enum):
            type_str = chunk_type.value
        else:
            type_str = str(chunk_type)
        
        chunk_id = self.memory.add_knowledge(
            chunk_type=type_str,
            chunk_key=chunk_key,
            title=title,
            status=ChunkStatus.PENDING.value,
            content=None,
        )
        logger.info(
            f"Created PENDING chunk {chunk_id}: {type_str} key={chunk_key}",
            token="ai-cult"
        )
        self.chunk_status_changed.emit(chunk_id, ChunkStatus.PENDING.value)
        return chunk_id

    def scan_database_only(self):
        """Только поиск новых чанков в сырых данных"""
        self._create_new_chunks_from_data()
        logger.info("Сканирование базы завершено.", token="ai-cult")

    def cultivate_pending_chunks(self, user_instructions: str = ""):
        """Запуск обработки для всех чанков со статусом PENDING"""
        pending = self.memory.get_pending_chunks()

        if not pending:
            logger.info("Нет чанков, требующих обновления.", token="ai-cult")
            return

        logger.info(f"Запуск культивации для {len(pending)} чанков...", token="ai-cult")
        for chunk in pending:
            self._initiate_cultivation(
                chunk,
                ChunkCultivationTrigger.USER_BUTTON,
                user_instructions=user_instructions
            )

    def request_user_cultivation(self, user_instructions: str = ""):
        """Legacy метод: делает всё сразу (для обратной совместимости, если где-то используется)"""
        self.scan_database_only()
        self.cultivate_pending_chunks(user_instructions)

    def _check_triggers(self):
        try:
            self.check_and_cultivate()
        except Exception as e:
            logger.error(f"ChunkCultivationManager timer error: {e}")

    def _evaluate_triggers(self, chunk: Dict) -> Optional[ChunkCultivationTrigger]:
        if self._check_time_trigger(chunk):
            return ChunkCultivationTrigger.TIME_ELAPSED
        
        if self._check_data_volume_trigger(chunk):
            return ChunkCultivationTrigger.DATA_VOLUME
            
        if self._check_market_deviation(chunk):
            logger.warning(f"Чанк {chunk.get('id')} устарел из-за изменения цен!", token="ai-cult")
            return ChunkCultivationTrigger.DATA_VOLUME
            
        return None

    def _check_time_trigger(self, chunk: Dict) -> bool:
        last_attempt = chunk.get("last_cultivation_attempt")
        if not last_attempt: return True
        try:
            dt_last = datetime.fromisoformat(last_attempt)
            elapsed = (datetime.now() - dt_last).total_seconds()
            return elapsed > self.default_time_threshold
        except: return True

    def _check_data_volume_trigger(self, chunk: Dict) -> bool:
        new_count = chunk.get("new_data_items_count") or 0
        return new_count >= self.default_data_threshold

    def _initiate_cultivation(self, chunk: Dict, trigger: ChunkCultivationTrigger, user_instructions: str = ""):
        chunk_id = chunk.get("id")
        chunk_type = chunk.get("chunk_type")

        if not chunk_id or not chunk_type: return

        logger.info(
            f"Cultivating chunk {chunk_id} ({chunk_type}) via {trigger.value}",
            token="ai-cult",
        )

        self.memory.update_chunk_status(
            chunk_id=chunk_id,
            status=ChunkStatus.INITIALIZING.value,
            progress=0,
        )
        self.chunk_status_changed.emit(chunk_id, ChunkStatus.INITIALIZING.value)

        try:
            prompt = self._build_cultivation_prompt(chunk)
            
            self.ai.start_cultivation_for_chunk(
                chunk_id=chunk_id,
                chunk_type=chunk_type,
                prompt=prompt,
                on_complete=lambda result: self._on_cultivation_complete(chunk_id, result),
                user_instructions=user_instructions
            )
        except Exception as e:
            logger.error(f"Failed to build prompt/start for chunk {chunk_id}: {e}")
            self._on_cultivation_complete(chunk_id, {"status": "error", "error": str(e)})

    def _process_cultivation_queue(self):
        if self.ai._is_cultivating_now:
            return

        if not self.ai._cultivation_queue:
            return

        if not self.ai._server_ready:
            self.ai.ensure_server() # Предполагается, что self.ai.ensure_server()
            QTimer.singleShot(1000, self._process_cultivation_queue)
            return

        self.ai._is_cultivating_now = True
        task = self.ai._cultivation_queue.pop(0)
        chunk_id = task["id"]
        
        logger.info(f"Начало обработки из очереди: чанк {chunk_id}...", token="ai-cult")

        self._active_timeout_chunk = chunk_id
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(lambda: self._on_worker_timeout(chunk_id))
        self._timeout_timer.start(180_000)

        port = self.ai.server_manager.get_port()
        worker = AIChunkCultivationWorker(
            port=port,
            chunk_id=chunk_id,
            chunk_type=task["type"],
            memory_manager=self.memory,
            model_name=self.ai._model_name,
            prompt=task["prompt"],
            user_instructions=task.get("user_instructions", "")
        )

        self.ai._chunk_workers[chunk_id] = worker

        worker.progress_signal.connect(
            lambda pct, txt: self.chunk_progress.emit(chunk_id, pct, txt)
        )

        def _handle_finished(result: dict):
            if hasattr(self, '_timeout_timer') and self._timeout_timer.isActive():
                self._timeout_timer.stop()
            self._active_timeout_chunk = None

            try:
                task["callback"](result)
            finally:
                w = self.ai._chunk_workers.pop(chunk_id, None)
                if w:
                    w.quit()
                    w.wait()
                    w.deleteLater()

                self.ai._is_cultivating_now = False
                QTimer.singleShot(500, self._process_cultivation_queue)

        worker.finished.connect(_handle_finished)
        worker.error_signal.connect(self.ai.error_signal.emit)
        worker.start()

    def _on_cultivation_complete(self, chunk_id: int, result: Dict):
        status = result.get("status")
        content = result.get("content")
        summary = result.get("summary")
        formation_reason = result.get("formation_reason", "")
        data_sufficiency = result.get("data_sufficiency", "MEDIUM")

        if status == "success" and isinstance(content, dict):
            # 1. Определяем финальный статус и текст для UI
            final_status = ChunkStatus.READY.value
            status_text = "Готово"
            
            if data_sufficiency == "LOW":
                final_status = ChunkStatus.ACCUMULATING.value
                status_text = "Мало данных"
                logger.warning(f"Чанк {chunk_id}: ИИ определил недостаток данных. Статус -> ACCUMULATING", token="ai-cult")
            elif summary and "нет данных" in summary.lower():
                final_status = ChunkStatus.ACCUMULATING.value
                status_text = "Ожидание данных"

            # 2. Сохраняем данные в БД (как и раньше)
            chunk_info = self.memory.get_chunk_by_id(chunk_id)
            source_hash = None
            if chunk_info:
                key = chunk_info.get('chunk_key')
                ctype = chunk_info.get('chunk_type')
                if ctype == 'CATEGORY':
                    source_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
                else:
                    source_hash = self.memory.raw_data.calculate_data_signature(product_key=key)

            self.memory.update_chunk_content(chunk_id, content, summary=summary, source_hash=source_hash)
            self.memory.update_chunk_status(chunk_id, final_status)
            
            # 3. Отправляем сигналы в UI
            self.chunk_status_changed.emit(chunk_id, final_status)
            
            # Используем status_text для финального сообщения прогресса
            progress_message = f"{status_text}: {formation_reason[:40]}..." if formation_reason else status_text
            self.chunk_progress.emit(chunk_id, 100, progress_message)

            if final_status == ChunkStatus.READY.value:
                self.cultivation_ready.emit(chunk_id)
                logger.success(f"Чанк {chunk_id} готов. Причина: {formation_reason}", token="ai-cult")
        else:
            # Блок обработки ошибок остается без изменений
            error_msg = result.get("error") or "unknown"
            self.chunk_progress.emit(chunk_id, 0, f"Ошибка: {error_msg[:20]}...")

            if error_msg == "cancelled":
                 logger.info(f"Чанк {chunk_id} отменен.", token="ai-cult")
                 return

            chunk = self.memory.get_chunk_by_id(chunk_id)
            retry_count = chunk.get('retry_count', 0) + 1
            MAX_RETRIES = 3

            if retry_count < MAX_RETRIES:
                self.memory.update_chunk_with_retry(chunk_id, ChunkStatus.PENDING.value, retry_count)
                logger.warning(f"Chunk {chunk_id} retry {retry_count}/{MAX_RETRIES}", token="ai-cult")
            else:
                self.memory.update_chunk_status(chunk_id, ChunkStatus.FAILED.value)
                self.chunk_status_changed.emit(chunk_id, ChunkStatus.FAILED.value)

            logger.error(f"Чанк {chunk_id} сбой: {error_msg}...", token="ai-cult")

    def _check_market_deviation(self, chunk: Dict) -> bool:
        """Проверяет, не ушел ли рынок далеко от сохраненных знаний."""
        try:
            content = chunk.get('content') or {}
            if isinstance(content, str): content = json.loads(content)
            
            stored_avg = content.get('analysis', {}).get('price_analysis', {}).get('avg', 0)
            if not stored_avg: 
                return False
                
            # Получаем свежие данные по ключу чанка
            key = chunk.get('chunk_key')
            chunk_type = chunk.get('chunk_type')
            
            if chunk_type == 'PRODUCT':
                items = self.memory.find_similar_items(key, limit=20)
                if not items: return False
                
                prices = [i['price'] for i in items if i.get('price', 0) > 0]
                if len(prices) < 5: return False
                
                current_avg = sum(prices) / len(prices)
                
                # Если отклонение > 25%, считаем чанк устаревшим
                deviation = abs(current_avg - stored_avg) / stored_avg
                return deviation > 0.25
                
        except Exception:
            return False
            
        return False

    def _build_cultivation_prompt(self, chunk: Dict) -> str:
        chunk_type = str(chunk.get("chunk_type", "")).upper()
        chunk_key = chunk.get("chunk_key")

        prev_summary = chunk.get("summary") or ""
        if not prev_summary and chunk.get("content"):
             try:
                 prev_content = json.loads(chunk.get("content"))
                 prev_summary = prev_content.get("summary", "")
             except: pass

        if chunk_type == "PRODUCT":
            items = self.memory.find_similar_items(chunk_key, limit=50)
            return ChunkCultivationPrompts.build_product_cultivation_prompt(
                chunk_key, items, previous_context=prev_summary
            )

        if chunk_type == "CATEGORY":
            all_chunks = self.memory.knowledge.get_chunks_by_type("PRODUCT")
            sub_chunks = []
            
            for c in all_chunks:
                if c.get('chunk_key', '').startswith(chunk_key) and c.get('status') == 'READY':
                    sub_chunks.append(c)
            
            if not sub_chunks:
                return ChunkCultivationPrompts.build_category_cultivation_prompt(
                    chunk_key, [], previous_context=prev_summary
                )
            
            return ChunkCultivationPrompts.build_category_cultivation_prompt(
                chunk_key, sub_chunks, previous_context=prev_summary
            )

        if chunk_type == "DATABASE":
            raw_stats = self.memory.get_raw_data_statistics()
            db_stats = {
                "total_items": raw_stats.get("total_items", 0),
                "total_categories": raw_stats.get("total_categories", 0)
            }
            vocab = self.memory.raw_data.get_database_vocabulary(limit=60)
            return ChunkCultivationPrompts.build_database_cultivation_prompt(db_stats, vocab)

        if chunk_type == "AI_BEHAVIOR":
            actions = self.memory.raw_data.get_recent_actions(limit=50)
            if not actions:
                return """{ "summary": "Нет данных о поведении пользователя." }"""
            return ChunkCultivationPrompts.build_ai_behavior_cultivation_prompt(
                actions, previous_context=prev_summary
            )

        raise ValueError(f"Unknown chunk type: {chunk_type}")

    def _create_new_chunks_from_data(self):
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        logger.info("Сканирование базы на новые знания...", token="ai-det")
        SmartChunkDetector.create_missing_chunks(self.memory, self)