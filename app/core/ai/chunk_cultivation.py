from __future__ import annotations
from enum import Enum
from typing import Optional, Dict
from datetime import datetime
import json
import random

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
    ACCUMULATING = "ACCUMULATING"
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

    def __init__(self, memory_manager, ai_manager, parent=None):
        super().__init__(parent)
        self.memory = memory_manager
        self.ai = ai_manager

        self.master_switch = True

        self._cultivation_timer = QTimer(self)
        self._cultivation_timer.timeout.connect(self._check_triggers)
        self._cultivation_timer.start(30_000) 

        self._integrity_timer = QTimer(self)
        self._integrity_timer.timeout.connect(self.validate_chunks_integrity)
        self._integrity_timer.start(300_000)

        self.default_time_threshold = 120
        self.default_data_threshold = 10

    def toggle_master_switch(self, enabled: bool):
        self.master_switch = enabled
        logger.info(f"AI Master Switch: {'ON' if enabled else 'PAUSED'}", token="ai-ctrl")

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
        # 1. Сначала подхватываем то, что уже ждет очереди (создано вручную или детектором)
        pending_chunks = self.memory.get_pending_chunks()
        if pending_chunks:
            for chunk in pending_chunks:
                # Если чанк уже в PENDING, не проверяем триггеры — просто запускаем
                # Но проверяем, не в очереди ли он уже
                if not any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                    self._initiate_cultivation(chunk, ChunkCultivationTrigger.USER_BUTTON)

        # 2. Проверяем "протухание" ГОТОВЫХ чанков (чего раньше не было)
        ready_chunks = self.memory.knowledge.get_ready_chunks()
        if ready_chunks:
            for chunk in ready_chunks:
                # Если чанк уже в очереди на культивацию, пропускаем проверку
                if any(t['id'] == chunk['id'] for t in self.ai._cultivation_queue):
                    continue
                
                trigger = self._evaluate_triggers(chunk)
                if trigger:
                    chunk_key = chunk.get('chunk_key', 'unknown')
                    logger.info(
                        f"🔄 ТРИГГЕР [{trigger.value}] сработал для '{chunk_key}'", 
                        token="ai-cult"
                    )
                    # Принудительно ставим PENDING и запускаем
                    self.memory.update_chunk_status(chunk['id'], ChunkStatus.PENDING.value)
                    self.chunk_status_changed.emit(chunk['id'], ChunkStatus.PENDING.value)
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
        """Только поиск новых чанков в сырых данных и их создание"""
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        logger.info("Запуск сканирования базы на новые знания...", token="ai-det")
        
        # 1. Получаем кандидатов (чистые данные, без записи в БД)
        candidates = SmartChunkDetector.detect_candidates(self.memory)
        
        if not candidates:
            logger.info("Новых кластеров не обнаружено.", token="ai-det")
            return

        created_count = 0
        
        # 2. Проходим и создаем
        for c in candidates:
            c_type = c['type']
            c_key = c['key']
            c_title = c['title']
            parent_key = c.get('parent_key')
            
            parent_id = None
            
            # Попытка найти ID родителя, если указан ключ
            if parent_key:
                # Ищем среди существующих (в БД)
                parent_chunk = self.memory.knowledge.get_chunk_by_key_and_type(parent_key, "CATEGORY")
                
                # Или, если родитель - это DATABASE (для AI_BEHAVIOR)
                if not parent_chunk and parent_key == "general":
                     parent_chunk = self.memory.knowledge.get_chunk_by_key_and_type("general", "DATABASE")
                
                if parent_chunk:
                    parent_id = parent_chunk['id']
                else:
                    # Если родителя нет в БД, возможно мы его создаем прямо сейчас в этом цикле?
                    # Для простоты пока пропускаем сложную рекурсию, привяжем в следующий раз
                    pass

            # 3. ЯВНАЯ ЗАПИСЬ + СИГНАЛЫ
            try:
                new_id = self.memory.add_knowledge(
                    chunk_type=c_type,
                    chunk_key=c_key,
                    title=c_title,
                    status=ChunkStatus.PENDING.value,
                    parent_chunk_id=parent_id
                )
                
                # !!! ВОТ ЭТО ЧИНИТ ВАШ UI !!!
                self.chunk_status_changed.emit(new_id, ChunkStatus.PENDING.value)
                logger.info(f"Создан чанк [{new_id}] {c_key}", token="ai-det")
                created_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка создания чанка {c_key}: {e}", token="ai-det")

        if created_count > 0:
            logger.success(f"Сформировано {created_count} новых узлов знаний.", token="ai-det")
        else:
            logger.info("Все кандидаты уже существуют в базе.", token="ai-det")

    def scan_and_create_structure(self):
        """Сканирует БД и создает структуру знаний (Категории -> Продукты)"""
        if not self.master_switch: return

        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        # Используем новый метод, который сам сортирует и линкует
        count = SmartChunkDetector.create_missing_chunks(self.memory, self)
        
        if count > 0:
            logger.success(f"Структура знаний обновлена: +{count} новых узлов.", token="ai-det")

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
        if not self.master_switch:
            return
        try:
            self.scan_and_create_structure()
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

    def _check_time_trigger(self, chunk: Dict) -> bool:
        last_attempt = chunk.get("last_cultivation_attempt")
        if not last_attempt: 
            return True # Если никогда не обновлялся — пора

        try:
            dt_last = datetime.fromisoformat(last_attempt)
            elapsed = (datetime.now() - dt_last).total_seconds()
            
            # Добавляем "джиттер" (случайный разброс +/- 20%), 
            # чтобы все чанки не обновлялись одновременно в одну секунду.
            # Для каждого чанка генерируем уникальный seed на основе ID, 
            # чтобы порог был стабильным для конкретного чанка, но разным для всех.
            random.seed(chunk.get('id', 0))
            jitter_percent = random.uniform(-0.20, 0.20)
            threshold_with_jitter = self.default_time_threshold * (1.0 + jitter_percent)
            
            return elapsed > threshold_with_jitter
        except Exception: 
            return True

    def _check_data_volume_trigger(self, chunk: Dict) -> bool:
        new_count = chunk.get("new_data_items_count") or 0
        if new_count >= self.default_data_threshold:
            logger.dev(f"Trigger Volume: {new_count} new items (threshold {self.default_data_threshold}) for chunk {chunk.get('id')}", level="DEBUG")
            return True
        return False

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

            # 2. Сохраняем данные в БД
            chunk_info = self.memory.get_chunk_by_id(chunk_id)
            source_hash = None
            if chunk_info:
                key = chunk_info.get('chunk_key')
                ctype = chunk_info.get('chunk_type')
                if ctype == 'CATEGORY':
                    source_hash = self.memory.raw_data.calculate_data_signature(category_key=key)
                else:
                    source_hash = self.memory.raw_data.calculate_data_signature(product_key=key)

            from app.core.text_utils import FeatureExtractor
            import numpy as np

            embedding_blob = None
            vector_text = f"{chunk_info.get('title', '')} {summary}"
            vec = FeatureExtractor.get_string_vector(vector_text)
            if vec is not None:
                embedding_blob = vec.astype(np.float32).tobytes()

            self.memory.update_chunk_content(chunk_id, content, summary=summary, source_hash=source_hash, embedding_blob=embedding_blob)
            self.memory.update_chunk_status(chunk_id, final_status)
            
            # --- [NEW] Сохраняем снепшот истории ---
            try:
                analysis = content.get('analysis', {})
                price_analysis = analysis.get('price_analysis', {})
                if not price_analysis and 'price_analysis' in content:
                     price_analysis = content['price_analysis']

                stats_snapshot = {
                    'avg': price_analysis.get('avg', 0),
                    'sufficiency': data_sufficiency,
                    'phase': analysis.get('market_phase', 'UNKNOWN')
                }
                # Вызов метода сохранения в историю (убедись, что он есть в KnowledgeManager)
                if hasattr(self.memory.knowledge, 'save_history_snapshot'):
                    self.memory.knowledge.save_history_snapshot(chunk_id, stats_snapshot)
            except Exception as e:
                logger.error(f"Failed to save history snapshot for {chunk_id}: {e}")
            # ---------------------------------------

            # 3. Отправляем сигналы в UI
            self.chunk_status_changed.emit(chunk_id, final_status)
            
            progress_message = f"{status_text}: {formation_reason[:40]}..." if formation_reason else status_text
            self.chunk_progress.emit(chunk_id, 100, progress_message)

            if final_status == ChunkStatus.READY.value:
                self.cultivation_ready.emit(chunk_id)
                logger.success(f"Чанк {chunk_id} готов. Причина: {formation_reason}", token="ai-cult")
        else:
            # Обработка ошибок (без изменений)
            error_msg = result.get("error") or "unknown"
            self.chunk_progress.emit(chunk_id, 0, f"Ошибка: {error_msg[:20]}...")

            if error_msg == "cancelled":
                 logger.info(f"Чанк {chunk_id} отменен.", token="ai-cult")
                 return

            chunk = self.memory.get_chunk_by_id(chunk_id)
            # Защита от None, если чанк был удален в процессе
            if chunk:
                retry_count = chunk.get('retry_count', 0) + 1
                MAX_RETRIES = 3

                if retry_count < MAX_RETRIES:
                    self.memory.update_chunk_with_retry(chunk_id, ChunkStatus.PENDING.value, retry_count)
                    logger.warning(f"Chunk {chunk_id} retry {retry_count}/{MAX_RETRIES}", token="ai-cult")
                else:
                    self.memory.update_chunk_status(chunk_id, ChunkStatus.FAILED.value)
                    self.chunk_status_changed.emit(chunk_id, ChunkStatus.FAILED.value)
            
            logger.error(f"Чанк {chunk_id} сбой: {error_msg}...", token="ai-cult")

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
        import statistics

        chunk_type = str(chunk.get("chunk_type", "")).upper()
        chunk_id = chunk.get("id")
        chunk_key = chunk.get("chunk_key")

        # 1. История
        prev_summary = ""
        if chunk.get("content"):
             try:
                 prev_content = json.loads(chunk.get("content"))
                 prev_summary = prev_content.get("main_description") or prev_content.get("summary") or ""
             except: pass

        # 2. Интересы
        user_interests = ""
        try:
            import os
            from app.config import BASE_APP_DIR
            path = os.path.join(BASE_APP_DIR, "user_interests.txt")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f: user_interests = f.read().strip()
        except: pass

        # 3. Контекст (Linked Context)
        linked_context = ""
        parent_id = chunk.get('parent_chunk_id')
        if parent_id:
            parent_chunk = self.memory.get_chunk_by_id(parent_id)
            if parent_chunk:
                p_content = parent_chunk.get('content')
                if isinstance(p_content, str):
                    try: p_content = json.loads(p_content)
                    except: p_content = {}
                elif not p_content: p_content = {}
                p_status = p_content.get('target_status', 'N/A') # Используем новый статус
                p_desc = p_content.get('main_description', '') or p_content.get('summary', '')
                linked_context = f"[РОДИТЕЛЬ: {parent_chunk.get('title')}]\nСтатус: {p_status}\nСуть: {p_desc[:600]}..."

        # === PRODUCT ===
        if chunk_type == "PRODUCT":
            raw_items = self.memory.find_similar_items(chunk_key, limit=1000)
            valid_prices = [i['price'] for i in raw_items if i.get('price', 0) > 100 and not i.get('is_outlier', 0)]
            
            math_block = {"count": len(valid_prices), "min": 0, "max": 0, "avg": 0, "med": 0, "q25": 0}
            if valid_prices:
                math_block["min"] = min(valid_prices)
                math_block["max"] = max(valid_prices)
                math_block["avg"] = int(statistics.mean(valid_prices))
                math_block["med"] = int(statistics.median(valid_prices))
                math_block["q25"] = int(sorted(valid_prices)[int(len(valid_prices)*0.25)])

            # История цен
            history_text = ""
            try:
                if hasattr(self.memory.knowledge, 'get_chunk_history'):
                    history = self.memory.knowledge.get_chunk_history(chunk_id)
                    history_text = "\n".join([f"{h['recorded_at'][:10]}: Avg={h['avg_price']}" for h in history])
            except: pass

            return ChunkCultivationPrompts.build_product_cultivation_prompt(
                chunk_key, raw_items,
                math_block=math_block,
                history_block=history_text,
                previous_context=prev_summary,
                user_interests=user_interests,
                user_instructions=chunk.get('user_instructions', ''),
                linked_context=linked_context
            )

        # === CATEGORY ===
        if chunk_type == "CATEGORY":
            all_chunks = self.memory.knowledge.get_chunks_by_type("PRODUCT")
            # Ищем детей строго по parent_id
            sub_chunks = [c for c in all_chunks if c.get('parent_chunk_id') == chunk_id and c.get('status') == 'READY']
            
            # Fallback для старых данных: ищем по ключу
            if not sub_chunks:
                sub_chunks = [c for c in all_chunks if c.get('chunk_key', '').startswith(chunk_key) and c.get('status') == 'READY']

            # Fallback на сырые данные, если нет чанков
            raw_fallback = ""
            if not sub_chunks:
                count = self.memory.raw_data.get_raw_items_count(category=chunk_key)
                if count > 0:
                    raw_fallback = f"Найдено {count} сырых объявлений. Детального анализа пока нет."

            return ChunkCultivationPrompts.build_category_cultivation_prompt(
                chunk_key, sub_chunks,
                previous_context=prev_summary,
                user_interests=user_interests,
                linked_context=linked_context,
                raw_fallback=raw_fallback
            )

        # === DATABASE ===
        if chunk_type == "DATABASE":
            # Собираем статистику
            raw_stats = self.memory.get_raw_data_statistics()
            # Если это тематическая БД (db_gpu), можно было бы отфильтровать, 
            # но пока берем общую статистику + словарь
            
            db_stats = {
                "total_items": raw_stats.get("total_items", 0),
                "total_categories": raw_stats.get("total_categories", 0),
                "avg_price": int(raw_stats.get("avg_price", 0))
            }
            vocab = self.memory.raw_data.get_database_vocabulary(limit=50)
            
            return ChunkCultivationPrompts.build_database_cultivation_prompt(
                db_stats, vocab,
                linked_context=linked_context,
                topic=chunk_key
            )

        # === AI_BEHAVIOR ===
        if chunk_type == "AI_BEHAVIOR":
            actions = self.memory.raw_data.get_recent_actions(limit=50)
            return ChunkCultivationPrompts.build_ai_behavior_cultivation_prompt(
                actions,
                user_interests=user_interests,
                previous_context=prev_summary,
                linked_context=linked_context
            )

        raise ValueError(f"Unknown chunk type: {chunk_type}")

    def _create_new_chunks_from_data(self):
        from app.core.ai.smart_chunk_detector import SmartChunkDetector
        
        logger.info("Сканирование базы на новые знания...", token="ai-det")
        SmartChunkDetector.create_missing_chunks(self.memory, self)

    # --- UI HELPERS ---

    def get_monitor_data(self) -> Dict:
        """Возвращает данные для виджета мониторинга"""
        next_check_in = 0
        if self._cultivation_timer and self._cultivation_timer.isActive():
            next_check_in = self._cultivation_timer.remainingTime() // 1000
        
        # Безопасное получение данных AI
        queue_len = 0
        active_workers = 0
        is_cultivating = False
        
        if self.ai:
            queue_len = len(getattr(self.ai, '_cultivation_queue', []))
            active_workers = len(getattr(self.ai, '_chunk_workers', {}))
            is_cultivating = getattr(self.ai, '_is_cultivating_now', False)
        
        # Новые данные
        nearest_time = self._get_nearest_time_trigger()
        market_deviations = self._get_pending_market_deviations()
        
        return {
            "next_check": next_check_in,
            "queue_size": queue_len,
            "active_workers": active_workers,
            "is_cultivating": is_cultivating,
            "nearest_time_trigger": nearest_time,
            "pending_market_deviations": market_deviations,
            "config": {
                "poll_interval": self._cultivation_timer.interval() // 1000,  # НОВОЕ
                "time_threshold": self.default_time_threshold,
                "data_threshold": self.default_data_threshold,
                "integrity_interval": self._integrity_timer.interval() // 1000  # НОВОЕ
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

    def update_config(self, time_threshold: int, data_threshold: int):
        """Обновление настроек из UI."""
        self.default_time_threshold = time_threshold
        self.default_data_threshold = data_threshold
        logger.info(f"Настройки культивации обновлены: Time={time_threshold}s, Data={data_threshold} items", token="ai-conf")

    def update_config_full(self, config: Dict):
        """Обновление всех настроек из UI"""

        # Частота опроса
        poll_interval = config.get('poll_interval', 30) * 1000  # в миллисекунды
        if self._cultivation_timer.interval() != poll_interval:
            self._cultivation_timer.setInterval(poll_interval)
            logger.info(f"⏱️ Частота опроса изменена: {poll_interval // 1000}с", token="ai-conf")

        # Срок актуальности чанка
        self.default_time_threshold = config.get('time_threshold', 120)

        # Порог новых данных
        self.default_data_threshold = config.get('data_threshold', 10)

        # Проверка целостности
        integrity_interval = config.get('integrity_interval', 300) * 1000
        if self._integrity_timer.interval() != integrity_interval:
            self._integrity_timer.setInterval(integrity_interval)
            logger.info(f"🔒 Интервал целостности изменен: {integrity_interval // 1000}с", token="ai-conf")
