from __future__ import annotations
from enum import Enum
from typing import Optional, List, Dict
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

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

    def __init__(self, memory_manager, ai_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self.ai = ai_manager

        self._cultivation_timer = QTimer(self)
        self._cultivation_timer.timeout.connect(self._check_triggers)
        self._cultivation_timer.start(60_000)

        self.default_time_threshold = 30 * 60
        self.default_data_threshold = 30

    def check_and_cultivate(self):
        pending_chunks = self.memory.get_pending_chunks()
        if not pending_chunks:
            return

        for chunk in pending_chunks:
            trigger = self._evaluate_triggers(chunk)
            if trigger:
                self._initiate_cultivation(chunk, trigger)

    def create_pending_chunk(self, chunk_type: ChunkType, chunk_key: str, title: str) -> int:
        chunk_id = self.memory.add_knowledge(
            chunk_type=chunk_type.value,
            chunk_key=chunk_key,
            title=title,
            status=ChunkStatus.PENDING.value,
            content=None,
        )
        logger.info(
            f"Created PENDING chunk {chunk_id}: {chunk_type.value} key={chunk_key}",
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

    def _on_cultivation_complete(self, chunk_id: int, result: Dict):
        status = result.get("status")
        content = result.get("content")
        summary = result.get("summary")

        if status == "success" and isinstance(content, dict):
            self.memory.update_chunk_content(chunk_id, content, summary=summary)
            self.chunk_status_changed.emit(chunk_id, ChunkStatus.READY.value)
            self.cultivation_ready.emit(chunk_id)
            logger.success(f"Чанк {chunk_id} готов...", token="ai-cult")
        else:
            error_msg = result.get("error") or "unknown"
            logger.error(f"Чанк {chunk_id} не готов из-за ошибки: {error_msg}...", token="ai-cult")
            
            chunk = self.memory.get_chunk_by_id(chunk_id)
            retry_count = chunk.get('retry_count', 0) + 1
            MAX_RETRIES = 3

            if retry_count < MAX_RETRIES:
                self.memory.update_chunk_with_retry(chunk_id, 'PENDING', retry_count)
                logger.warning(f"Chunk {chunk_id} retry {retry_count}/{MAX_RETRIES}", token="ai-cult")
            else:
                self.memory.update_chunk_status(chunk_id, 'FAILED')
            logger.error(f"Chunk {chunk_id} permanently failed after {MAX_RETRIES} attempts", token="ai-cult")

    def _build_cultivation_prompt(self, chunk: Dict) -> str:
        chunk_type = chunk.get("chunk_type")
        chunk_key = chunk.get("chunk_key")

        if chunk_type == ChunkType.PRODUCT.value:
            items = self.memory.find_similar_items(chunk_key, limit=50)
            return ChunkCultivationPrompts.build_product_cultivation_prompt(chunk_key, items)

        if chunk_type == ChunkType.CATEGORY.value:
            # Get items from raw_data for category cultivation
            items = self.memory.get_items_for_product_key(chunk_key)[:200]
            if items:
                stats = self.memory.get_raw_data_statistics()
            else:
                stats = {}
            return ChunkCultivationPrompts.build_category_cultivation_prompt(chunk_key, stats)

        if chunk_type == ChunkType.DATABASE.value:
            raw_stats = self.memory.get_raw_data_statistics()
            db_stats = {
                "total_items": raw_stats.get("total_items", 0),
                "total_categories": raw_stats.get("total_categories", 0)
            }
            return ChunkCultivationPrompts.build_database_cultivation_prompt(db_stats)

        if chunk_type == ChunkType.AI_BEHAVIOR.value:
            return ChunkCultivationPrompts.build_ai_behavior_cultivation_prompt([])

        raise ValueError(f"Unknown chunk type: {chunk_type}")

    def _create_new_chunks_from_data(self):
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        logger.info("Сканирование базы на новые знания...", token="ai-det")
        SmartChunkDetector.create_missing_chunks(self.memory, self)