from __future__ import annotations
from enum import Enum
from typing import Optional, Dict
from datetime import datetime
import numpy as np
import json
import random
import os

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from app.core.ai.ai_manager import AIChunkCultivationWorker
from app.core.log_manager import logger
from app.core.ai.prompts import ChunkCultivationPrompts
from app.core.text_utils import FeatureExtractor
from app.config import BASE_APP_DIR

class ChunkType(Enum):
    PRODUCT = "PRODUCT"
    CATEGORY = "CATEGORY"
    DATABASE = "DATABASE"
    AI_BEHAVIOR = "AI_BEHAVIOR"

class ChunkStatus(Enum):
    PENDING = "PENDING"
    NEED_REFRESH = "NEED_REFRESH"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    COMPRESSED = "COMPRESSED"
    FAILED = "FAILED"

class ChunkCultivationTrigger(Enum):
    TIME_ELAPSED = "TIME_ELAPSED"
    DATA_VOLUME = "DATA_VOLUME"
    MARKET_DEVIATION = "MARKET_DEVIATION"
    LLM_DECISION = "LLM_DECISION"
    USER_BUTTON = "USER_BUTTON"

class ChunkCultivationManager(QObject):
    cultivation_ready = pyqtSignal(int)
    chunk_status_changed = pyqtSignal(int, str)
    chunk_progress = pyqtSignal(int, int, str)
    config_updated_signal = pyqtSignal(dict)
    pause_state_changed = pyqtSignal(bool)

    def __init__(self, memory_manager, ai_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self.ai = ai_manager

        self.master_switch = True
        self._paused_remaining_time = 0
        self._is_resuming_from_pause = False

        self._cultivation_timer = QTimer(self)
        self._cultivation_timer.timeout.connect(self._check_triggers)
        
        self._target_poll_interval = 30_000 
        self._cultivation_timer.start(self._target_poll_interval)

        self._integrity_timer = QTimer(self)
        self._integrity_timer.timeout.connect(self.validate_chunks_integrity)
        self._integrity_timer.start(300_000)

        self.default_time_threshold = 120
        self.default_data_threshold = 10

    def toggle_master_switch(self, enabled: bool):
        """Переключение паузы с сохранением прогресса таймера"""
        if self.master_switch == enabled:
            return

        self.master_switch = enabled
        
        if not enabled:
            if self._cultivation_timer.isActive():
                self._paused_remaining_time = self._cultivation_timer.remainingTime()
                self._cultivation_timer.stop()
            else:
                self._paused_remaining_time = 0
            
            logger.info(f"⏸️ Система культивации: ПАУЗА (осталось {self._paused_remaining_time/1000:.1f}с)", token="ai-ctrl")
        else:
            delay = self._paused_remaining_time
            if delay <= 100: 
                delay = 1000 
            
            self._is_resuming_from_pause = True
            
            self._cultivation_timer.start(delay)
            
            logger.info(f"▶️ Система культивации: АКТИВНА (продолжение через {delay/1000:.1f}с)", token="ai-ctrl")
            
        self.pause_state_changed.emit(enabled)

    def validate_chunks_integrity(self):
        chunks = self.memory.knowledge.get_knowledge(status='READY')
        for chunk in chunks:
            chunk_id = chunk['id']
            stored_hash = chunk.get('source_hash')
            if not stored_hash: continue

            key = chunk.get('chunk_key')
            ctype = chunk.get('chunk_type')

            current_hash = None
            if ctype == 'CATEGORY':
                current_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
            else:
                current_hash = self.memory.raw_data.calculate_data_signature(product_key=key)

            if current_hash != stored_hash:
                logger.info(f"Чанк {chunk_id} ({key}) устарел (данные изменились).", token="ai-mem")
                self.memory.update_chunk_status(chunk_id, ChunkStatus.NEED_REFRESH.value)
                self.chunk_status_changed.emit(chunk_id, ChunkStatus.NEED_REFRESH.value)

    def _on_worker_timeout(self, chunk_id: int):
        logger.error(f"Таймаут культивации чанка {chunk_id}.", token="ai-cult")
        self.cancel_task(chunk_id)
        self.memory.update_chunk_status(chunk_id, ChunkStatus.FAILED.value)
        self.chunk_status_changed.emit(chunk_id, ChunkStatus.FAILED.value)
        self._process_cultivation_queue()

    def cancel_task(self, chunk_id: int):
        if not self.ai: return
        
        # Удаляем из очереди
        self.ai._cultivation_queue = [t for t in self.ai._cultivation_queue if t['id'] != chunk_id]
        
        # Останавливаем воркер, если он активен
        if chunk_id in self.ai._chunk_workers:
            worker = self.ai._chunk_workers[chunk_id]
            worker.stop()
            worker.quit()
            worker.wait(1000)
            self.ai._chunk_workers.pop(chunk_id, None)
            self.ai._is_cultivating_now = False
            QTimer.singleShot(1000, self._process_cultivation_queue)

    def check_and_cultivate(self):
        """Автоматическая проверка триггеров."""
        # 1. Принудительные обновления (кнопка Refresh)
        refresh_chunks = self.memory.knowledge.get_knowledge(status=ChunkStatus.NEED_REFRESH.value)
        for chunk in refresh_chunks:
            if not any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                self._initiate_cultivation(chunk, ChunkCultivationTrigger.USER_BUTTON)

        # 2. Новые чанки (PENDING)
        pending_chunks = self.memory.get_pending_chunks()
        for chunk in pending_chunks:
            if not any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                # Проверяем объем данных перед запуском PENDING
                # (Хотя детектор уже должен был проверить, но для надежности)
                self._initiate_cultivation(chunk, ChunkCultivationTrigger.DATA_VOLUME)

        # 3. Готовые чанки (READY) - проверка времени и аномалий
        ready_chunks = self.memory.knowledge.get_ready_chunks()
        for chunk in ready_chunks:
            if any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                continue
            
            trigger = self._evaluate_triggers(chunk)
            if trigger:
                self.memory.update_chunk_status(chunk['id'], ChunkStatus.NEED_REFRESH.value)
                self.chunk_status_changed.emit(chunk['id'], ChunkStatus.NEED_REFRESH.value)
                self._initiate_cultivation(chunk, trigger)

    def create_pending_chunk(self, chunk_type, chunk_key: str, title: str) -> int:
        type_str = chunk_type.value if isinstance(chunk_type, Enum) else str(chunk_type)
        chunk_id = self.memory.add_knowledge(
            chunk_type=type_str, chunk_key=chunk_key, title=title, status=ChunkStatus.PENDING.value
        )
        self.chunk_status_changed.emit(chunk_id, ChunkStatus.PENDING.value)
        return chunk_id

    def _create_safe(self, c_data):
        key = c_data['key'].strip() # Нормализация
        try:
            # Проверка дублей (на всякий случай, хоть детектор и проверял)
            exists = self.memory.knowledge.get_chunk_by_key_and_type(key, c_data['type'])
            if exists: return

            new_id = self.memory.add_knowledge(
                chunk_type=c_data['type'],
                chunk_key=key,
                title=c_data['title'],
                status=ChunkStatus.PENDING.value,
                parent_chunk_id=c_data.get('parent_id')
            )
            # Сигнал для UI
            self.chunk_status_changed.emit(new_id, ChunkStatus.PENDING.value)
            logger.info(f"Создан чанк [{new_id}] {key}", token="ai-det")
            
        except Exception as e:
            logger.error(f"Create error {key}: {e}", token="ai-det")

    def cultivate_pending_chunks(self, user_instructions: str = ""):
        """Ручной запуск всех PENDING и NEED_REFRESH."""
        # Получаем чанки (get_pending_chunks уже сортирует по приоритету DESC)
        # Но для надежности перепроверим порядок
        targets = self.memory.get_pending_chunks() + \
                  self.memory.knowledge.get_knowledge(status=ChunkStatus.NEED_REFRESH.value)

        # Удаляем дубликаты по ID
        unique_targets = {t['id']: t for t in targets}.values()
        
        # Сортируем: PRODUCT (100) -> CATEGORY (50) -> ...
        sorted_targets = sorted(
            unique_targets, 
            key=lambda x: x.get('priority', 0), 
            reverse=True
        )

        if not sorted_targets:
            logger.info("Нет чанков, требующих обновления.", token="ai-cult")
            return

        logger.info(f"Запуск культивации для {len(sorted_targets)} чанков (Приоритет макс: {sorted_targets[0].get('priority')})...", token="ai-cult")
        
        for chunk in sorted_targets:
            self._initiate_cultivation(
                chunk,
                ChunkCultivationTrigger.USER_BUTTON,
                user_instructions=user_instructions
            )

    def request_user_cultivation(self, user_instructions: str = ""):
        self._create_new_chunks_from_data()
        self.cultivate_pending_chunks(user_instructions)

    def _check_triggers(self):
        if self._is_resuming_from_pause:
            self._is_resuming_from_pause = False
            self._cultivation_timer.setInterval(self._target_poll_interval)

        if not self.master_switch:
            return

        try:
            self._create_new_chunks_from_data()
            self.check_and_cultivate()
        except Exception as e:
            logger.error(f"Timer error: {e}")

    def _evaluate_triggers(self, chunk: Dict) -> Optional[ChunkCultivationTrigger]:
        """Проверяет триггеры в порядке приоритета"""

        # Приоритет 1: Накопление данных (легкая проверка)
        if self._check_data_volume_trigger(chunk):
            return ChunkCultivationTrigger.DATA_VOLUME

        # Приоритет 2: Время (легкая проверка)
        if self._check_time_trigger(chunk):
            return ChunkCultivationTrigger.TIME_ELAPSED

        # Приоритет 3: Аномалия цен (средняя сложность)
        if self._check_market_deviation(chunk):
            return ChunkCultivationTrigger.MARKET_DEVIATION

        # Приоритет 4: Решение LLM (тяжелая проверка, только если сервер готов)
        if self.ai and self.ai._server_ready:
            if self._check_llm_decision_trigger(chunk):
                return ChunkCultivationTrigger.LLM_DECISION

        return None

    def _check_data_volume_trigger(self, chunk: Dict) -> bool:
        new_count = chunk.get("new_data_items_count") or 0
        return new_count >= self.default_data_threshold

    def _check_time_trigger(self, chunk: Dict) -> bool:
        last_attempt = chunk.get("last_cultivation_attempt")
        if not last_attempt: return True
        try:
            dt_last = datetime.fromisoformat(last_attempt)
            elapsed = (datetime.now() - dt_last).total_seconds()
            random.seed(chunk.get('id', 0))
            jitter = random.uniform(-0.2, 0.2)
            threshold = self.default_time_threshold * (1.0 + jitter)
            return elapsed > threshold
        except: return True

    def _check_market_deviation(self, chunk: Dict) -> bool:
        """Проверяет, не ушел ли рынок далеко от сохраненных знаний."""
        try:
            # Пропускаем, если чанк не является ПРОДУКТОМ (для категорий сложнее считать)
            if chunk.get('chunk_type') != 'PRODUCT':
                return False

            content = chunk.get('content') or {}
            if isinstance(content, str): content = json.loads(content)
            
            # Достаем сохраненную среднюю цену
            stored_avg = content.get('analysis', {}).get('price_analysis', {}).get('avg', 0)
            if not stored_avg or stored_avg < 100: 
                return False
                
            key = chunk.get('chunk_key')
            
            # Берем последние 10 сырых товаров
            items = self.memory.find_similar_items(key, limit=10)
            if not items or len(items) < 3: 
                return False
            
            prices = [i['price'] for i in items if i.get('price', 0) > 0]
            if not prices: return False
            
            current_avg = sum(prices) / len(prices)
            
            # Считаем отклонение
            deviation = abs(current_avg - stored_avg) / stored_avg
            
            # Порог 25%
            if deviation > 0.25:
                logger.info(
                    f"📈 Аномалия цены для {key}: Было ~{stored_avg}, Стало ~{int(current_avg)} (Diff: {int(deviation*100)}%)", 
                    token="ai-cult"
                )
                return True
                
        except Exception as e:
            # logger.warning(f"Deviation check error for {chunk.get('id')}: {e}")
            return False
            
        return False

    def _initiate_cultivation(self, chunk: Dict, trigger: ChunkCultivationTrigger, user_instructions: str = ""):
        chunk_id = chunk.get("id")
        chunk_type = chunk.get("chunk_type")
        self.memory.update_chunk_status(chunk_id, ChunkStatus.INITIALIZING.value)
        self.chunk_status_changed.emit(chunk_id, ChunkStatus.INITIALIZING.value)

        try:
            prompt = self._build_cultivation_prompt(chunk)
            self.ai.start_cultivation_for_chunk(
                chunk_id=chunk_id, chunk_type=chunk_type, prompt=prompt,
                on_complete=lambda result: self._on_cultivation_complete(chunk_id, result),
                user_instructions=user_instructions
            )
        except Exception as e:
            logger.error(f"Failed to start chunk {chunk_id}: {e}")
            self.memory.update_chunk_status(chunk_id, ChunkStatus.FAILED.value)

    def _process_cultivation_queue(self):
        if self.ai._is_cultivating_now: return
        if not self.ai._cultivation_queue: return
        if not self.ai._server_ready:
            self.ai.ensure_server()
            QTimer.singleShot(1000, self._process_cultivation_queue)
            return

        self.ai._is_cultivating_now = True
        task = self.ai._cultivation_queue.pop(0)
        chunk_id = task["id"]

        # Запускаем таймер таймаута
        self._active_timeout_chunk = chunk_id
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(lambda: self._on_worker_timeout(chunk_id))
        self._timeout_timer.start(180_000)

        worker = AIChunkCultivationWorker(
            port=self.ai.server_manager.get_port(),
            chunk_id=chunk_id,
            chunk_type=task["type"],
            memory_manager=self.memory,
            model_name=self.ai._model_name,
            prompt=task["prompt"],
            user_instructions=task.get("user_instructions", "")
        )
        self.ai._chunk_workers[chunk_id] = worker

        def _handle_finished(result: dict):
            if hasattr(self, '_timeout_timer'): self._timeout_timer.stop()
            try:
                task["callback"](result)
            finally:
                self.ai._chunk_workers.pop(chunk_id, None)
                self.ai._is_cultivating_now = False
                QTimer.singleShot(500, self._process_cultivation_queue)

        worker.finished.connect(_handle_finished)
        worker.start()

    def _on_cultivation_complete(self, chunk_id: int, result: Dict):
        status = result.get("status")
        content = result.get("content")
        summary = result.get("summary")

        if status == "success" and isinstance(content, dict):
            final_status = ChunkStatus.READY.value
            chunk_info = self.memory.get_chunk_by_id(chunk_id)
            key = chunk_info.get('chunk_key')
            ctype = chunk_info.get('chunk_type')
            
            source_hash = None
            if ctype == 'CATEGORY':
                source_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
            elif ctype == 'PRODUCT':
                source_hash = self.memory.raw_data.calculate_data_signature(product_key=key)

            embedding_blob = None
            try:
                vec_text = f"{chunk_info.get('title', '')} {summary or ''}"
                vec = FeatureExtractor.get_string_vector(vec_text)
                if vec is not None:
                    embedding_blob = vec.astype(np.float32).tobytes()
            except: pass

            stats_snapshot = {
                'avg': content.get('price_analysis', {}).get('avg', 0),
                'sufficiency': content.get('data_sufficiency', 'UNKNOWN'),
                'phase': content.get('target_status', 'UNKNOWN')
            }
            self.memory.knowledge.save_history_snapshot(chunk_id, stats_snapshot)

            self.memory.update_chunk_content(
                chunk_id=chunk_id, content=content, summary=summary,
                source_hash=source_hash, embedding_blob=embedding_blob
            )
            self.chunk_status_changed.emit(chunk_id, final_status)
            self.chunk_progress.emit(chunk_id, 100, "Готово")
            logger.success(f"✅ Чанк {chunk_id} обновлен.", token="ai-cult")
        else:
            self.memory.update_chunk_status(chunk_id, ChunkStatus.FAILED.value)
            self.chunk_status_changed.emit(chunk_id, ChunkStatus.FAILED.value)

    def _extract_chunk_text(self, chunk_key: str, chunk_type: str) -> str:
        chunk = self.memory.knowledge.get_chunk_by_key_and_type(chunk_key, chunk_type)
        if chunk and chunk.get('status') == 'READY':
            content = chunk.get('content')
            if isinstance(content, str):
                try: content = json.loads(content)
                except: content = {}
            if isinstance(content, dict):
                desc = content.get('main_description') or content.get('summary')
                if desc: return f"[{chunk_type} {chunk_key}]: {desc}"
        return ""

    def _build_cultivation_prompt(self, chunk: Dict) -> str:
        """Формирует промпт для культивации чанка (переделан для новой системы)"""
        chunk_type = str(chunk.get("chunk_type", "")).upper()
        chunk_key = chunk.get("chunk_key")
        chunk_id = chunk.get("id")

        # 1. ПРЕДЫДУЩИЙ КОНТЕКСТ (если был)
        prev_summary = ""
        try:
            # FIX: Handle potential None content in older/failed chunks
            raw_content = chunk.get("content")
            if raw_content:
                prev_content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                prev_summary = prev_content.get("main_description") or prev_content.get("summary") or ""
        except: prev_summary = ""

        # 2. ИНТЕРЕСЫ ПОЛЬЗОВАТЕЛЯ
        user_interests = ""
        try:
            path = os.path.join(BASE_APP_DIR, "user_interests.txt")
            with open(path, "r", encoding="utf-8") as f:
                user_interests = f.read().strip()
        except:
            user_interests = "Не заданы."

        # 3. ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ
        user_instructions = ""
        try:
            path = os.path.join(BASE_APP_DIR, "user_instructions.txt")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    user_instructions = f.read().strip()
        except:
            user_instructions = "Нет."

        # 4. РОДИТЕЛЬСКИЙ КОНТЕКСТ (Linked Context)
        linked_context = ""
        parent_id = chunk.get('parent_chunk_id')
        if parent_id:
            try:
                parent_chunk = self.memory.get_chunk_by_id(parent_id)
                if parent_chunk:
                    p_content = parent_chunk.get('content')
                    if p_content:
                        if isinstance(p_content, str):
                            try: p_content = json.loads(p_content)
                            except: p_content = {}
                        
                        p_status = p_content.get('target_status', 'N/A')
                        p_desc = p_content.get('main_description', '') or p_content.get('summary', '')
                        linked_context = f"[РОДИТЕЛЬСКИЙ ЧАНК: {parent_chunk.get('title')}]\nСтатус: {p_status}\nСуть: {p_desc[:400]}..."
            except Exception as e:
                logger.error(f"Error building linked context for {chunk_id}: {e}")
            
        # === PRODUCT ===
        if chunk_type == "PRODUCT":
            raw_items = self.memory.find_similar_items(chunk_key, limit=1000)
            valid_prices = [i['price'] for i in raw_items if i.get('price', 0) > 50 and not i.get('is_outlier', 0)]
            
            if valid_prices:
                math_block = {
                    "count": len(valid_prices),
                    "min": min(valid_prices),
                    "max": max(valid_prices),
                    "avg": int(sum(valid_prices) / len(valid_prices)),
                    "med": int(sorted(valid_prices)[len(valid_prices) // 2]),
                    "q25": int(sorted(valid_prices)[len(valid_prices) // 4]) if len(valid_prices) > 3 else 0
                }
            else:
                math_block = {"count": 0, "min": 0, "max": 0, "avg": 0, "med": 0, "q25": 0}

            # История цен
            history_text = ""
            try:
                history = self.memory.knowledge.get_chunk_history(chunk_id, limit=5)
                if history:
                    history_text = "\n".join([
                        f"{h['recorded_at'][:10]}: Avg={h.get('avg_price', 'N/A')}₽"
                        for h in history
                    ])
            except:
                history_text = "История недоступна."

            return ChunkCultivationPrompts.build_product_cultivation_prompt(
                chunk_key=chunk_key,
                items=raw_items[:50],
                math_block=math_block,
                history_block=history_text,
                previous_context=prev_summary,
                user_interests=user_interests,
                user_instructions=user_instructions,
                linked_context=linked_context
            )

        # === CATEGORY ===
        elif chunk_type == "CATEGORY":
            all_chunks = self.memory.knowledge.get_knowledge(limit=10000)
            sub_chunks = [c for c in all_chunks if c.get('parent_chunk_id') == chunk_id and c.get('chunk_type') == 'PRODUCT']

            # FIX: Get Raw Data Preview + Count
            try:
                raw_items = self.memory.raw_data.get_raw_items(category=chunk_key, limit=15)
                raw_count = self.memory.raw_data.get_raw_items_count(category=chunk_key)
                
                if raw_items:
                    raw_preview_list = [f"- {i.get('title')[:60]}... ({i.get('price')}р)" for i in raw_items]
                    raw_preview_str = "\n".join(raw_preview_list)
                else:
                    raw_preview_str = "Нет сырых данных."
            except Exception as e:
                raw_preview_str = "Ошибка получения данных."
                raw_count = 0

            return ChunkCultivationPrompts.build_category_cultivation_prompt(
                category_key=chunk_key, sub_products=sub_chunks,
                previous_context=prev_summary, user_interests=user_interests,
                linked_context=linked_context, 
                raw_fallback_preview=raw_preview_str,
                raw_count=raw_count
            )

        # === DATABASE ===
        elif chunk_type == "DATABASE":
            db_stats = self.memory.raw_data.get_scoped_statistics(chunk_key)
            try: vocab = self.memory.raw_data.get_database_vocabulary(limit=50)
            except: vocab = []

            return ChunkCultivationPrompts.build_database_cultivation_prompt(
                db_stats=db_stats, vocabulary=vocab,
                linked_context=linked_context, topic=chunk_key
            )

        # === AI_BEHAVIOR ===
        elif chunk_type == "AI_BEHAVIOR":
            actions = self.memory.raw_data.get_recent_actions(limit=50)

            return ChunkCultivationPrompts.build_ai_behavior_cultivation_prompt(
                actions_log=actions,
                user_interests=user_interests,
                previous_context=prev_summary,
                linked_context=linked_context
            )

        else:
            raise ValueError(f"Unknown chunk type: {chunk_type}")

    def _create_new_chunks_from_data(self):
        """Единая точка входа для создания чанков."""
        if not self.master_switch: return
        
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        # Детектор теперь сам ставит правильные приоритеты (PRODUCT=100)
        count = SmartChunkDetector.create_missing_chunks(self.memory, self)
        if count > 0:
            logger.info(f"Создано {count} новых структурных единиц памяти.", token="ai-det")

    # --- UI HELPERS ---

    def get_monitor_data(self) -> Dict:
        """Данные для UI"""
        next_check_in = 0
        current_cycle_total = self._target_poll_interval // 1000
        
        if not self.master_switch:
            next_check_in = self._paused_remaining_time // 1000
        else:
            if self._cultivation_timer.isActive():
                next_check_in = self._cultivation_timer.remainingTime() // 1000
                current_cycle_total = self._cultivation_timer.interval() // 1000

        queue_len = 0
        active_workers = 0
        is_cultivating = False

        if self.ai:
            queue_len = len(getattr(self.ai, '_cultivation_queue', []))
            active_workers = len(getattr(self.ai, '_chunk_workers', {}))
            is_cultivating = getattr(self.ai, '_is_cultivating_now', False)

        nearest_time = self._get_nearest_time_trigger()
        market_deviations = self._get_pending_market_deviations()

        return {
            "next_check": next_check_in,
            "current_cycle_total": current_cycle_total,
            "queue_size": queue_len,
            "active_workers": active_workers,
            "is_cultivating": is_cultivating,
            "nearest_time_trigger": nearest_time,
            "pending_market_deviations": market_deviations,
            "is_paused": not self.master_switch,
            "config": {
                "poll_interval": self._target_poll_interval // 1000,
                "time_threshold": self.default_time_threshold,
                "data_threshold": self.default_data_threshold,
                "integrity_interval": self._integrity_timer.interval() // 1000
            }
        }

    def _get_nearest_time_trigger(self) -> Optional[Dict]:
        """Находит чанк, который обновится раньше всех по TIME_ELAPSED"""
        ready_chunks = self.memory.knowledge.get_ready_chunks()

        nearest = None
        min_time_left = float('inf')

        for chunk in ready_chunks:
            # Пропускаем чанки уже в очереди
            if any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                continue

            last_attempt = chunk.get("last_cultivation_attempt")
            if not last_attempt:
                continue
            
            try:
                # Рассчитываем порог с джиттером (детерминированно)
                random.seed(chunk.get('id', 0))
                jitter_percent = random.uniform(-0.20, 0.20)
                threshold = self.default_time_threshold * (1.0 + jitter_percent)

                # Сколько прошло времени
                dt_last = datetime.fromisoformat(last_attempt)
                elapsed = (datetime.now() - dt_last).total_seconds()

                # Сколько осталось до срабатывания
                time_left = threshold - elapsed

                if 0 < time_left < min_time_left:
                    min_time_left = time_left
                    nearest = {
                        "chunk_title": chunk.get('title', 'Unknown'),
                        "seconds_left": int(time_left),
                        "chunk_id": chunk['id']
                    }
            except Exception as e:
                logger.dev(f"Error calculating time trigger for chunk {chunk.get('id')}: {e}", level="DEBUG")
                continue
            
        return nearest

    def _get_pending_market_deviations(self) -> List[Dict]:
        """Находит чанки с аномальными ценами"""
        ready_chunks = self.memory.knowledge.get_ready_chunks()

        deviations = []
        for chunk in ready_chunks:
            if chunk.get('chunk_type') != 'PRODUCT':
                continue
            
            # Пропускаем чанки уже в очереди
            if any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                continue
            
            try:
                content = chunk.get('content')
                if isinstance(content, str):
                    content = json.loads(content)

                stored_avg = content.get('analysis', {}).get('price_analysis', {}).get('avg', 0)

                if not stored_avg or stored_avg < 100:
                    continue
                
                key = chunk.get('chunk_key')
                items = self.memory.find_similar_items(key, limit=10)
                prices = [i['price'] for i in items if i.get('price', 0) > 0]

                if len(prices) < 3:
                    continue
                
                current_avg = sum(prices) / len(prices)
                deviation = ((current_avg - stored_avg) / stored_avg) * 100

                # Показываем отклонения >15%
                if abs(deviation) > 15:
                    deviations.append({
                        "chunk_title": chunk.get('title', 'Unknown'),
                        "deviation_percent": round(deviation, 1),
                        "chunk_id": chunk['id'],
                        "stored_avg": int(stored_avg),
                        "current_avg": int(current_avg)
                    })
            except Exception as e:
                logger.dev(f"Error calculating deviation for chunk {chunk.get('id')}: {e}", level="DEBUG")
                continue
            
        # Сортируем по величине отклонения
        return sorted(deviations, key=lambda x: abs(x["deviation_percent"]), reverse=True)[:3]

    def _check_llm_decision_trigger(self, chunk: Dict) -> bool:
        """LLM решает, нужно ли обновлять чанк (реальный запрос)"""
        # Условия для запроса LLM
        new_count = chunk.get("new_data_items_count") or 0
        if new_count < 3:  # Слишком мало новых данных
            return False

        # Проверяем качество текущего чанка
        content = chunk.get('content')
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except:
                content = {}

        data_sufficiency = content.get('data_sufficiency', 'MEDIUM')

        # Если LLM ранее отметил недостаток данных - спрашиваем снова
        if data_sufficiency != 'LOW' and new_count < 5:
            return False

        # Формируем запрос к LLM
        chunk_key = chunk.get('chunk_key')
        chunk_type = chunk.get('chunk_type')
        summary = content.get('summary', '') if isinstance(content, dict) else ''

        # Получаем новые данные
        new_items = []
        if chunk_type == 'PRODUCT':
            new_items = self.memory.find_similar_items(chunk_key, limit=5)

        if not new_items:
            return False

        # Формируем промпт для LLM
        prompt = self._build_llm_decision_prompt(chunk, new_items, summary)

        try:
            # Синхронный вызов LLM (быстрый запрос)
            from app.core.ai.llama_client import LlamaClient
            import asyncio

            port = self.ai.server_manager.get_port()
            client = LlamaClient(port)

            messages = [
                {"role": "system", "content": "Ты аналитик данных. Ответь ТОЛЬКО 'YES' или 'NO'."},
                {"role": "user", "content": prompt}
            ]

            # Быстрый запрос с таймаутом
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(
                asyncio.wait_for(
                    client.chat_completion(
                        model=self.ai._model_name,
                        messages=messages,
                        params={"temperature": 0.1, "max_tokens": 10}
                    ),
                    timeout=5.0
                )
            )
            loop.close()

            if response and 'YES' in response.upper():
                logger.info(f"🤖 LLM_DECISION: Чанк {chunk['id']} требует обновления", token="ai-cult")
                return True
            else:
                logger.dev(f"LLM_DECISION: Чанк {chunk['id']} актуален (ответ: {response})", level="DEBUG")
                return False

        except Exception as e:
            logger.dev(f"LLM_DECISION error for chunk {chunk['id']}: {e}", level="DEBUG")
            return False

    def _build_llm_decision_prompt(self, chunk: Dict, new_items: List[Dict], old_summary: str) -> str:
        """Формирует промпт для LLM_DECISION"""

        new_count = len(new_items)
        avg_price = sum(i['price'] for i in new_items if i.get('price', 0) > 0) / max(1, len([i for i in new_items if i.get('price', 0) > 0]))

        titles_sample = "\n".join([f"- {i.get('title', '')[:50]} ({i.get('price', 0)}₽)" for i in new_items[:3]])

        return f"""ЗАДАЧА: Определить, нужно ли обновлять аналитический отчет.

    ТЕКУЩИЙ ОТЧЕТ:
    {old_summary[:200]}...

    НОВЫЕ ДАННЫЕ ({new_count} лотов, средняя цена: {int(avg_price)}₽):
    {titles_sample}

    ВОПРОС: Содержат ли новые данные значимую информацию, противоречащую старому отчету или существенно дополняющую его?

    Ответь 'YES' если обновление необходимо (новые тренды, аномалии цен, изменение характеристик).
    Ответь 'NO' если новые данные подтверждают существующий анализ."""

    def update_config_full(self, config: Dict):
        """Обновление настроек без лимитов и с оповещением UI"""
        poll_interval_sec = int(config.get('poll_interval', 30))
        # Технический минимум 1 сек, чтобы не повесить UI
        if poll_interval_sec < 1: poll_interval_sec = 1
        
        new_interval_ms = poll_interval_sec * 1000

        if self._target_poll_interval != new_interval_ms:
            self._target_poll_interval = new_interval_ms
            
            if self.master_switch:
                self._cultivation_timer.stop()
                
                self._is_resuming_from_pause = False 
                self._paused_remaining_time = 0      
                
                self._cultivation_timer.setInterval(new_interval_ms)
                self._cultivation_timer.start()
                
            logger.info(f"⏱️ Частота опроса изменена: {poll_interval_sec}с (таймер перезапущен)", token="ai-conf")

        self.default_time_threshold = int(config.get('time_threshold', 120))
        self.default_data_threshold = int(config.get('data_threshold', 10))

        integrity_sec = int(config.get('integrity_interval', 300))
        if integrity_sec < 10: integrity_sec = 10
        integrity_ms = integrity_sec * 1000

        if self._integrity_timer.interval() != integrity_ms:
            self._integrity_timer.setInterval(integrity_ms)
            if self.master_switch:
                self._integrity_timer.start()
            logger.info(f"🔒 Интервал целостности изменен: {integrity_sec}с", token="ai-conf")
        
        # Важно: эмитим сигнал, чтобы синхронизировать все открытые виджеты
        self.config_updated_signal.emit({
            'poll_interval': poll_interval_sec,
            'time_threshold': self.default_time_threshold,
            'data_threshold': self.default_data_threshold,
            'integrity_interval': integrity_sec
        })