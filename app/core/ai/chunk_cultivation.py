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
    PRODUCT = "PRODUCT"
    CATEGORY = "CATEGORY"
    DATABASE = "DATABASE"
    AI_BEHAVIOR = "AI_BEHAVIOR"
    CUSTOM = "CUSTOM"

class ChunkStatus(Enum):
    PENDING = "PENDING"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    COMPRESSED = "COMPRESSED"

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

    def validate_chunks_integrity(self):
        """
        Проверяет, соответствуют ли знания текущим сырым данным.
        Если хэш изменился -> статус PENDING (нужна перегенерация).
        """
        logger.dev("Запуск проверки целостности знаний...", level="DEBUG")
        chunks = self.memory.knowledge.get_knowledge(status='READY')
        
        updated_count = 0
        
        for chunk in chunks:
            chunk_id = chunk['id']
            stored_hash = chunk.get('source_hash')
            
            # Если хэша нет (старый чанк), пропускаем или помечаем на обновление
            if not stored_hash:
                continue
                
            key = chunk.get('chunk_key')
            ctype = chunk.get('chunk_type')
            
            # Считаем актуальный хэш
            current_hash = None
            if ctype == 'CATEGORY':
                current_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
            else:
                current_hash = self.memory.raw_data.calculate_data_signature(product_key=key)
            
            if current_hash != stored_hash:
                logger.info(f"Чанк {chunk_id} ({key}) устарел. Данные изменились.", token="ai-mem")
                # Сбрасываем статус на PENDING, чтобы культиватор подхватил его позже
                self.memory.update_chunk_status(chunk_id, 'PENDING')
                self.chunk_status_changed.emit(chunk_id, 'PENDING')
                updated_count += 1
        
        if updated_count > 0:
            logger.info(f"Помечено на обновление: {updated_count} чанков.", token="ai-mem")

    def cancel_task(self, chunk_id: int):
        """Удаляет чанк из очереди обработки, если он там есть."""
        if not self.ai: return

        # 1. Удаляем из очереди ожидания
        initial_len = len(self.ai._cultivation_queue)
        self.ai._cultivation_queue = [t for t in self.ai._cultivation_queue if t['id'] != chunk_id]
        
        if len(self.ai._cultivation_queue) < initial_len:
            logger.info(f"Чанк {chunk_id} удален из очереди культивации.", token="ai-cult")
            
        # 2. Если воркер прямо сейчас работает над этим чанком
        if chunk_id in self.ai._chunk_workers:
            logger.warning(f"Прерывание активной культивации чанка {chunk_id}...", token="ai-cult")
            worker = self.ai._chunk_workers[chunk_id]
            worker.stop()
            worker.quit()

    def check_and_cultivate(self):
        pending_chunks = self.memory.get_pending_chunks()
        if not pending_chunks:
            return

        for chunk in pending_chunks:
            trigger = self._evaluate_triggers(chunk)
            if trigger:
                self._initiate_cultivation(chunk, trigger)

    def create_pending_chunk(self, chunk_type, chunk_key: str, title: str) -> int:
        type_str = chunk_type.value if hasattr(chunk_type, "value") else str(chunk_type)
        
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

    def request_user_cultivation(self, user_instructions: str = ""):
        self._create_new_chunks_from_data()
        
        pending = self.memory.get_pending_chunks()
        
        if not pending:
            logger.info("Нет чанков, требующих обновления...", token="ai-cult")
            return
            
        logger.info(f"Запуск культивации для {len(pending)} чанков...", token="ai-cult")
        for chunk in pending:
            self._initiate_cultivation(
                chunk, 
                ChunkCultivationTrigger.USER_BUTTON, 
                user_instructions=user_instructions
            )

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
            
        # НОВОЕ: Проверка отклонения рынка
        if self._check_market_deviation(chunk):
            logger.warning(f"Чанк {chunk.get('id')} устарел из-за изменения цен!", token="ai-cult")
            return ChunkCultivationTrigger.DATA_VOLUME # Используем тот же триггер для перезапуска
            
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
        
        # Получаем source_hash для фиксации состояния данных на момент начала
        # Это нужно, чтобы при следующем обновлении понять, устарели ли данные
        # Пока просто запускаем процесс
        
        logger.info(f"Начало обработки из очереди: чанк {chunk_id}", token="ai-cult")

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

        # CONNECT SIGNALS
        worker.progress_signal.connect(
            lambda pct, txt: self.chunk_progress.emit(chunk_id, pct, txt)
        )

        def _handle_finished(result: dict):
            try:
                task["callback"](result)
            finally:
                w = self.ai._chunk_workers.pop(chunk_id, None)
                if w:
                    w.quit()
                    w.wait()
                    w.deleteLater()

                self.ai._is_cultivating_now = False
                # Небольшая пауза перед следующим, чтобы дать UI обновиться
                QTimer.singleShot(500, self._process_cultivation_queue)

        worker.finished.connect(_handle_finished)
        worker.error_signal.connect(self.ai.error_signal.emit)
        worker.start()

    def _on_cultivation_complete(self, chunk_id: int, result: Dict):
        status = result.get("status")
        content = result.get("content")
        summary = result.get("summary")

        if status == "success" and isinstance(content, dict):
            # Получаем хэш данных, чтобы привязать результат к состоянию базы
            chunk_info = self.memory.get_chunk_by_id(chunk_id)
            source_hash = None
            if chunk_info:
                # Определяем, какой hash считать.
                # Для простоты считаем хэш по ключу чанка.
                # Если это категория - хэш категории, если продукт - продукта.
                # В данном контексте это не блокирует поток UI, т.к. SQLite быстрая.
                key = chunk_info.get('chunk_key')
                ctype = chunk_info.get('chunk_type')
                
                if ctype == 'CATEGORY':
                    source_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
                else:
                    source_hash = self.memory.raw_data.calculate_data_signature(product_key=key)

            self.memory.update_chunk_content(chunk_id, content, summary=summary, source_hash=source_hash)
            self.chunk_status_changed.emit(chunk_id, ChunkStatus.READY.value)
            self.cultivation_ready.emit(chunk_id)
            
            # 100% прогресс
            self.chunk_progress.emit(chunk_id, 100, "Готово")
            
            logger.success(f"Чанк {chunk_id} готов...", token="ai-cult")
        else:
            # Ошибка
            error_msg = result.get("error") or "unknown"
            self.chunk_progress.emit(chunk_id, 0, f"Ошибка: {error_msg[:20]}...")
            
            # ... (логика ретраев остается прежней)
            chunk = self.memory.get_chunk_by_id(chunk_id)
            retry_count = chunk.get('retry_count', 0) + 1
            MAX_RETRIES = 3

            if retry_count < MAX_RETRIES:
                self.memory.update_chunk_with_retry(chunk_id, 'PENDING', retry_count)
                logger.warning(f"Chunk {chunk_id} retry {retry_count}/{MAX_RETRIES}", token="ai-cult")
            else:
                self.memory.update_chunk_status(chunk_id, 'FAILED')
            
            logger.error(f"Чанк {chunk_id} не готов: {error_msg}...", token="ai-cult")

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
        chunk_type = chunk.get("chunk_type")
        chunk_key = chunk.get("chunk_key")

        # 1. PRODUCT CHUNK (Стандартный)
        if chunk_type == ChunkType.PRODUCT.value:
            items = self.memory.find_similar_items(chunk_key, limit=50)
            return ChunkCultivationPrompts.build_product_cultivation_prompt(chunk_key, items)

        # 2. CATEGORY CHUNK (Агрегация продуктов)
        if chunk_type == ChunkType.CATEGORY.value:
            # Находим все PRODUCT чанки, которые начинаются с ключа категории (например, "GPU_Nvidia")
            # chunk_key здесь ожидается, например, "GPU_Nvidia"
            
            all_chunks = self.memory.knowledge.get_chunks_by_type("PRODUCT")
            sub_chunks = []
            
            for c in all_chunks:
                # Проверяем, относится ли продукт к этой категории
                # Ключи продуктов: "GPU_Nvidia_RTX3060"
                if c.get('chunk_key', '').startswith(chunk_key) and c.get('status') == 'READY':
                    sub_chunks.append(c)
            
            # Если дочерних чанков нет, пытаемся собрать статистику из сырых данных как фоллбэк
            if not sub_chunks:
                items = self.memory.raw_data.get_items_for_product_key(chunk_key) # Пытаемся найти сырые
                stats = self.memory.get_raw_data_statistics() # Заглушка, тут надо улучшать, но пока хватит
                # Используем старый метод как фоллбэк, если структура ключей не совпала
                return ChunkCultivationPrompts.build_category_cultivation_prompt(chunk_key, []) # Пустой список заставит ИИ галлюцинировать меньше
            
            return ChunkCultivationPrompts.build_category_cultivation_prompt(chunk_key, sub_chunks)

        # 3. DATABASE CHUNK (Глобальный контекст)
        if chunk_type == ChunkType.DATABASE.value:
            raw_stats = self.memory.get_raw_data_statistics()
            db_stats = {
                "total_items": raw_stats.get("total_items", 0),
                "total_categories": raw_stats.get("total_categories", 0)
            }
            # NEW: Получаем реальный словарь
            vocab = self.memory.raw_data.get_database_vocabulary(limit=60)
            return ChunkCultivationPrompts.build_database_cultivation_prompt(db_stats, vocab)

        # 4. AI_BEHAVIOR CHUNK (Портрет пользователя)
        if chunk_type == ChunkType.AI_BEHAVIOR.value:
            # NEW: Получаем лог действий
            actions = self.memory.raw_data.get_recent_actions(limit=50)
            if not actions:
                return """{ "summary": "Нет данных о поведении пользователя." }"""
            return ChunkCultivationPrompts.build_ai_behavior_cultivation_prompt(actions)

        raise ValueError(f"Unknown chunk type: {chunk_type}")

    def _create_new_chunks_from_data(self):
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        logger.info("Сканирование базы на новые знания...", token="ai-det")
        SmartChunkDetector.create_missing_chunks(self.memory, self)