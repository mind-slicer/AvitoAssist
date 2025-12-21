from __future__ import annotations
from enum import Enum
from typing import Optional, List, Dict
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from app.core.log_manager import logger
# Импортируем новый класс промптов
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
        # 1. Сначала проверим, не нужно ли создать новые чанки
        # (вызываем редко или по таймеру, но здесь для надежности можно проверить)
        # self._create_new_chunks_from_data() # Можно включить авто-создание здесь

        # 2. Обрабатываем существующие
        pending_chunks = self.memory.get_pending_chunks()
        if not pending_chunks:
            return

        for chunk in pending_chunks:
            trigger = self._evaluate_triggers(chunk)
            if trigger:
                self._initiate_cultivation(chunk, trigger)

    def create_pending_chunk(self, chunk_type: ChunkType, chunk_key: str, title: str) -> int:
        chunk_id = self.memory.add_knowledge_v2(
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

    def request_user_cultivation(self):
        """Пользователь нажал кнопку"""
        # 1. Сначала ищем новые паттерны в данных
        self._create_new_chunks_from_data()
        
        # 2. Потом запускаем обработку всего, что есть
        pending = self.memory.get_pending_chunks()
        
        if not pending:
            logger.info("Нет чанков, требующих обновления.", token="ai-cult")
            return
            
        logger.info(f"Запуск культивации для {len(pending)} чанков...", token="ai-cult")
        for chunk in pending:
            self._initiate_cultivation(chunk, ChunkCultivationTrigger.USER_BUTTON)

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

    def _initiate_cultivation(self, chunk: Dict, trigger: ChunkCultivationTrigger):
        chunk_id = chunk.get("id")
        chunk_type = chunk.get("chunk_type")

        if not chunk_id or not chunk_type: return

        logger.info(
            f"Cultivating chunk {chunk_id} ({chunk_type}) via {trigger.value}",
            token="ai-cult",
        )

        self.memory.update_chunk_status(
            chunk_id=chunk_id,
            new_status=ChunkStatus.INITIALIZING.value,
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
            # Статус READY ставится внутри update_chunk_content, но эмитим сигнал явно
            self.chunk_status_changed.emit(chunk_id, ChunkStatus.READY.value)
            self.cultivation_ready.emit(chunk_id)
            logger.success(f"Chunk {chunk_id} готов!", token="ai-cult")
        else:
            error_msg = result.get("error") or "unknown"
            logger.error(f"Chunk {chunk_id} failed: {error_msg}", token="ai-cult")
            # Можно сбросить в PENDING или оставить FAILED
            # self.memory.update_chunk_status(chunk_id, ChunkStatus.PENDING.value) 
            # Пока оставим как есть, чтобы не зациклить ошибки

    def _build_cultivation_prompt(self, chunk: Dict) -> str:
        """Строит промпт используя ChunkCultivationPrompts"""
        chunk_type = chunk.get("chunk_type")
        chunk_key = chunk.get("chunk_key")

        if chunk_type == ChunkType.PRODUCT.value:
            items = self.memory.find_similar_items(chunk_key, limit=50)
            return ChunkCultivationPrompts.build_product_cultivation_prompt(chunk_key, items)

        if chunk_type == ChunkType.CATEGORY.value:
            stats = self.memory.get_stats_for_product_key(chunk_key)
            if not stats:
                # Попробуем найти хоть какую-то статистику
                all_s = self.memory.get_all_statistics(limit=200)
                for s in all_s:
                    if s.get('product_key') == chunk_key:
                        stats = s
                        break
            if not stats: stats = {}
            return ChunkCultivationPrompts.build_category_cultivation_prompt(chunk_key, stats)

        if chunk_type == ChunkType.DATABASE.value:
            base_stats = self.memory.get_stats() or {}
            all_cats = self.memory.get_all_statistics(limit=1) # count check only
            # Нужно получить реальное кол-во категорий, сейчас хак через items count
            # Лучше добавить метод в memory. get_stats() уже возвращает total items.
            db_stats = {
                "total_items": base_stats.get("total", 0),
                "total_categories": "Много" # Заглушка, если нет точного счетчика
            }
            return ChunkCultivationPrompts.build_database_cultivation_prompt(db_stats)

        if chunk_type == ChunkType.AI_BEHAVIOR.value:
            return ChunkCultivationPrompts.build_ai_behavior_cultivation_prompt([])

        raise ValueError(f"Unknown chunk type: {chunk_type}")

    def _create_new_chunks_from_data(self):
        """
        Использует SmartChunkDetector для поиска и создания новых PENDING чанков.
        """
        # Импорт внутри метода во избежание циклического импорта
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        logger.info("SmartDetector: сканирование базы на новые знания...", token="ai-det")
        SmartChunkDetector.create_missing_chunks(self.memory, self)