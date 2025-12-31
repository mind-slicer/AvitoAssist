import os
import json
import glob
import asyncio
import re
import requests
import gc
import time
from typing import List, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, Qt

from app.config import AI_CTX_SIZE, AI_GPU_LAYERS, AI_SERVER_PORT, MODELS_DIR
from app.core.ai.server_manager import ServerManager
from app.core.ai.llama_client import LlamaClient
from app.core.ai.prompts import PromptBuilder
from app.core.text_utils import TextMatcher
from app.core.log_manager import logger


class AIProcessingWorker(QThread):
    progress_value = pyqtSignal(int)
    result_signal = pyqtSignal(int, str, dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, port: int, items: List[Dict], prompts: List[str], rag_messages: List[Optional[str]], context: Dict, model_name: str):
        super().__init__()
        self.port = port
        self.items = items
        self.prompts = prompts
        self.rag_messages = rag_messages
        self.context = context
        self.model_name = model_name
        self._is_running = True

    def stop(self):
        self._is_running = False
        TextMatcher.clear_cache()

    def run(self):
        asyncio.run(self._process_async())

    async def _process_async(self):
        client = LlamaClient(self.port)
        try:
            total = len(self.items)
            
            gen_params = {
                "response_format": {"type": "json_object"}, 
                "temperature": 0.2,
                "top_k": 64,
                "top_p": 0.95,
                "min_p": 0.05,
                "repeat_penalty": 1.05,
                "max_tokens": 2048,
                "mirostat_mode": 0
            }

            for i, item in enumerate(self.items):
                if not self._is_running: break
                
                if i < len(self.rag_messages) and self.rag_messages[i]:
                    logger.success(self.rag_messages[i])

                logger.progress(f"Нейросеть анализирует: {i + 1}/{total}...", token="ai_batch")
                self.progress_value.emit(int(((i + 1) / total) * 100))
                
                prompt_text = self.prompts[i] if i < len(self.prompts) else self.prompts[-1]
                
                clean_item = {
                    k: v for k, v in item.items() 
                    if k in ['title', 'price', 'description', 'city', 'condition', 'seller_id', 'views', 'date_text']
                }
                item_dump = json.dumps(clean_item, ensure_ascii=False)

                messages = [
                    {"role": "system", "content": "Ты — аналитик, работающий с данными в формате JSON."},
                    {"role": "user", "content": f"{prompt_text}\n\nДАННЫЕ:\n{item_dump}"}
                ]

                response = await client.chat_completion(
                    model=self.model_name,
                    messages=messages,
                    params=gen_params
                )

                if response:
                    cleaned = self._clean_json(response)
                    self.result_signal.emit(i, cleaned, self.context)
                    if i % 5 == 0:
                        gc.collect()
                else:
                    self.error_signal.emit(f"Пустой ответ ИИ для #{i}...")
            
            logger.success("Анализ завершен...")
            self.finished_signal.emit()

        except Exception as e:
            logger.error(f"Ошибка ИИ воркера: {e}...")
            self.error_signal.emit(str(e))
        finally:
            await client.close()
            TextMatcher.clear_cache()

    def _clean_json(self, text: str) -> str:
        if not text: return "{}"
        
        match_code = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match_code:
            return match_code.group(1)

        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]

        return text.replace("```json", "").replace("```", "").strip()


class AIChatWorker(QThread):
    response_signal = pyqtSignal(str)

    def __init__(self, port: int, messages: List[Dict], model_name: str):
        super().__init__()
        self.port = port
        self.messages = messages
        self.model_name = model_name

    def run(self):
        asyncio.run(self._chat_async())

    async def _chat_async(self):
        client = LlamaClient(self.port)
        try:
            chat_params = {
                "temperature": 1.0,
                "top_k": 64,
                "top_p": 0.95,
                "min_p": 0.0,
                "max_tokens": 2048 #TODO: Увеличить?
            }
            
            resp = await client.chat_completion(
                self.model_name, 
                self.messages, 
                params=chat_params
            )
            
            if resp:
                self.response_signal.emit(resp)
            else:
                self.response_signal.emit("Ошибка: сервер молчит.")
        except Exception as e:
            self.response_signal.emit(f"Ошибка связи: {e}")
        finally:
            await client.close()

class AIChunkCultivationWorker(QThread):
    finished = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)

    def __init__(self, port: int, chunk_id: int, chunk_type: str,
                 memory_manager, model_name: str, prompt: str, user_instructions: str = ""):
        super().__init__()
        self.port = port
        self.chunk_id = chunk_id
        self.chunk_type = chunk_type
        self.memory = memory_manager
        self.model_name = model_name
        self.prompt = prompt
        self._is_running = True
        self.user_instructions = user_instructions

    def stop(self):
        self._is_running = False

    def run(self):
        asyncio.run(self._cultivate_chunk())

    async def _cultivate_chunk(self):
        self.progress_signal.emit(5, "Подключение к нейросети...")
        self.progress_signal.emit(10, "Формирование контекста...")

        client = LlamaClient(self.port)
        try:
            if hasattr(self, '_is_running') and not self._is_running:
                self.finished.emit({"status": "error", "error": "cancelled", "chunk_id": self.chunk_id})
                return

            gen_params = {
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "top_k": 40,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
                "max_tokens": 4096,
                "mirostat_mode": 0
            }

            system_content = "Ты аналитик рынка объявлений Авито. Твоя задача — свести данные в единый JSON."
            if self.user_instructions:
                system_content += f"\n\nВАЖНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ:\n{self.user_instructions}"

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": self.prompt},
            ]

            logger.progress(
                f"Культивация чанка {self.chunk_id} ({self.chunk_type})...",
                token="ai-cult",
            )

            # 2. Sending Request with Progress Emulation
            self.progress_signal.emit(15, "Отправка данных в LLM...")

            # Запускаем задачу в фоне, чтобы обновлять прогресс
            task = asyncio.create_task(client.chat_completion(
                model=self.model_name,
                messages=messages,
                params=gen_params,
            ))

            # Эмуляция "мыслительного процесса"
            elapsed = 0
            while not task.done():
                if hasattr(self, '_is_running') and not self._is_running:
                    task.cancel()
                    self.finished.emit({"status": "error", "error": "cancelled", "chunk_id": self.chunk_id})
                    return
                
                await asyncio.sleep(0.5)
                elapsed += 0.5
                
                # Динамический прогресс, чтобы пользователь не скучал
                if elapsed < 5:
                    self.progress_signal.emit(20 + int(elapsed * 2), "ИИ анализирует цены...")
                elif elapsed < 10:
                    self.progress_signal.emit(30 + int(elapsed), "ИИ ищет аномалии...")
                elif elapsed < 20:
                    self.progress_signal.emit(40 + int(elapsed / 2), "ИИ формирует выводы...")
                else:
                    self.progress_signal.emit(50, "Генерация отчета (большой объем)...")

            response = await task

            # 3. Processing Response
            self.progress_signal.emit(80, "Ответ получен. Обработка...")

            if not response or not isinstance(response, str) or len(response.strip()) < 10:
                msg = f"ИИ вернул пустой или слишком короткий ответ для чанка {self.chunk_id}..."
                logger.error(msg, token="ai-cult")
                if hasattr(self, 'error_signal'):
                    self.error_signal.emit(msg)
                self.finished.emit({"status": "error", "error": msg, "chunk_id": self.chunk_id})
                return

            text = response.strip()

            if '```' in text:
                match_json = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                if match_json:
                    text = match_json.group(1)
                else:
                    parts = text.split('```')
                    if len(parts) > 1:
                        text = parts[1]
                        if text.strip().lower().startswith('json'):
                            text = text.strip()[4:].strip()

            self.progress_signal.emit(90, "Валидация JSON...")

            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                err = f"В ответе ИИ не найден JSON-объект..."
                self.finished.emit({"status": "error", "error": err, "chunk_id": self.chunk_id})
                return

            clean_json_text = match.group(0).strip()

            try:
                data = json.loads(clean_json_text)
            except json.JSONDecodeError as e:
                err = f"Ошибка парсинга JSON: {str(e)}..."
                self.finished.emit({"status": "error", "error": err, "chunk_id": self.chunk_id})
                return

            # Извлечение новых полей для умного статуса
            summary = data.get("summary")
            # Legacy fallback
            if not summary:
                analysis = data.get("analysis", {})
                if isinstance(analysis, dict):
                    summary = analysis.get("summary")
                if not summary:
                    summary = data.get("summary")

            formation_reason = data.get("formation_reason", "Причина не указана")
            data_sufficiency = data.get("data_sufficiency", "MEDIUM")

            # Если LLM считает, что данных мало, помечаем это в саммари
            if data_sufficiency == "LOW":
                summary = f"[НЕДОСТАТОЧНО ДАННЫХ] {summary}" if summary else "[НЕДОСТАТОЧНО ДАННЫХ]"

            # 4. Finalizing
            self.progress_signal.emit(98, "Сохранение знаний...")

            result = {
                "status": "success",
                "content": data,
                "summary": summary if summary else "Анализ завершен",
                "formation_reason": formation_reason, # Причина создания/обновления
                "data_sufficiency": data_sufficiency, # Хватает ли данных
                "chunk_id": self.chunk_id
            }
            self.finished.emit(result)

        except Exception as e:
            err = f"Критический сбой при культивации: {str(e)}"
            logger.error(err, token="ai-cult", exc_info=True)
            self.finished.emit({"status": "error", "error": str(e), "chunk_id": self.chunk_id})
        finally:
            await client.close()


class AIManager(QObject):
    progress_signal = pyqtSignal(str)
    ai_progress_value = pyqtSignal(int)
    result_signal = pyqtSignal(int, str, dict)
    finished_signal = pyqtSignal()
    all_finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    server_ready_signal = pyqtSignal()
    chat_response_signal = pyqtSignal(str)

    def __init__(self, memory_manager=None):
        super().__init__()
        self.memory_manager = memory_manager
        self.current_model_path = self._find_default_model()
        self._model_name = os.path.basename(self.current_model_path) if self.current_model_path else "No Model"
        
        self.server_manager = ServerManager(self.current_model_path, port=AI_SERVER_PORT)
        self.server_manager.server_started.connect(self._on_server_started_process)
        self.server_manager.error_occurred.connect(self.error_signal.emit)
        
        self.processing_worker: Optional[AIProcessingWorker] = None
        self.chat_worker: Optional[AIChatWorker] = None
        
        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._check_health_and_notify)
        self._server_ready = False

        self._ctx_size = AI_CTX_SIZE
        self._gpu_layers = AI_GPU_LAYERS or -1
        self._gpu_device = 0
        self._backend = "auto"
        self._debug_logs = False

        self._chunk_workers: Dict[int, AIChunkCultivationWorker] = {}
        self._cultivation_queue = []
        self._is_cultivating_now = False

        self.analysis_timer = QTimer()
        self.analysis_timer.timeout.connect(self._tick_analysis_timer)
        self.start_ts = 0

    def _find_default_model(self) -> Optional[str]:
        if not os.path.exists(MODELS_DIR):
            os.makedirs(MODELS_DIR, exist_ok=True)
            return None
        files = glob.glob(os.path.join(MODELS_DIR, "*.gguf"))
        if files: return sorted(files)[0]
        return None

    def has_model(self) -> bool:
        return self.current_model_path and os.path.exists(self.current_model_path)
    
    def set_model(self, filename: str):
        path = os.path.join(MODELS_DIR, filename)
        if os.path.exists(path):
            self.current_model_path = path
            self._model_name = filename
            self.server_manager.set_model_path(path)
            if self.server_manager.is_running():
                self.server_manager.stop_server()

    def update_config(self, settings: dict):
        model_name = settings.get("ai_model")
        self._ctx_size = settings.get("ai_ctx_size", AI_CTX_SIZE)
        self._gpu_layers = settings.get("ai_gpu_layers", -1)
        self._gpu_device = settings.get("ai_gpu_device", 0)
        self._backend = settings.get("ai_backend", "auto")
        
        should_restart = False
        if model_name and model_name != self._model_name:
            self.set_model(model_name)
            should_restart = True

        if self.server_manager.is_running() or should_restart:
            if self.server_manager.is_running():
                 self.server_manager.stop_server()
            QTimer.singleShot(500, self.ensure_server)

    def ensure_server(self):
        if not self.has_model():
            self.error_signal.emit("Модель не найдена!")
            return

        if not self.server_manager.is_running():
            self.progress_signal.emit("Запуск AI сервера...")
            self.server_manager.start_server(
                ctx_size=self._ctx_size, 
                gpu_layers=self._gpu_layers,
                gpu_device=self._gpu_device,
                backend_preference=self._backend
            )
        elif not self._server_ready:
            if not self.health_timer.isActive():
                self.progress_signal.emit("Подключение к нейросети...")
                self.health_timer.start(1000)
        elif self._server_ready:
            self.server_ready_signal.emit()

    def _on_server_started_process(self):
        self.progress_signal.emit("Загрузка нейросети...")
        self.health_timer.start(1000)

    def _check_health_and_notify(self):
        port = self.server_manager.get_port()
        try:
            resp = requests.get(
                f"http://127.0.0.1:{port}/health",
                timeout=5.0,
                proxies={"http": None, "https": None}
            )
            
            if resp.status_code == 200:
                self._server_ready = True
                self.server_ready_signal.emit()
                self.server_manager._is_starting = False
                self.health_timer.stop()
                logger.success("AI готов к работе (Health OK)", token="ai-manager")
            elif resp.status_code == 503:
                self.progress_signal.emit("Модель загружается в память...")
                logger.dev("AI: 503 Loading...", level="DEBUG")
            else:
                logger.warning(f"AI ответил кодом: {resp.status_code}", token="ai-manager")
        
        except requests.exceptions.ConnectionError:
            logger.dev("AI: Нет соединения с 127.0.0.1 (порт еще закрыт)", level="DEBUG")
        except Exception as e:
            logger.error(f"AI Health ошибка: {e}")

    def _save_items_to_database(self, items: List[Dict], context: Dict):
        if not self.memory_manager:
            return

        product_key = context.get('product_key') # Это может быть использовано внутри add_item для контекста, но сам item должен содержать semantic_data
        category = context.get('category') # Аналогично

        saved_count = 0
        for item in items:
            try:
                # Теперь вызываем унифицированный метод add_item,
                # который сам выполнит семантический анализ и логирование.
                # Больше не нужно передавать categories и product_keys отдельно.
                self.memory_manager.add_item(item=item)
                saved_count += 1
            except Exception as e:
                logger.dev(f"Failed to save item to raw_data: {e}", level="DEBUG", exc_info=True)

        if saved_count > 0:
            logger.info(f"Сохранено {saved_count} items в базу для культивации", token="ai-mem")

    def start_processing(self, items: List[Dict], prompt: Optional[str], debug_mode: bool, context: Dict):
        self._save_items_to_database(items, context)

        self.ensure_server()
        if not self._server_ready:
            self.server_ready_signal.connect(lambda: self.start_processing(items, prompt, debug_mode, context), Qt.ConnectionType.SingleShotConnection)
            return
        
        if not prompt:
            logger.info("Подготовка поискового индекса...", token="text_match")
            TextMatcher.precompute_corpus(items)

        prompts_list = []
        rag_messages_list = []
        interests = context.get('interests', "")
        search_mode = context.get('search_mode', 'full')

        self.start_ts = time.time()
        self.analysis_timer.start(1000) 

        if prompt: 
            prompts_list = [prompt] * len(items)
            rag_messages_list = [None] * len(items)
        else:
            instr = context.get('user_instructions', "")
            
            for item in items:
                rag = None
                log_msg = None

                if self.memory_manager:
                    rag = self.memory_manager.get_rag_context_for_item(item.get('title', ''))

                if rag:
                    knowledge_text = rag.get('knowledge', '')
                    is_smart_chunk = knowledge_text and "Нет детального" not in knowledge_text

                    status_icon = "✅ Чанк активен" if is_smart_chunk else "⚠️ Live-статистика"
                    preview = knowledge_text[:40] + "..." if is_smart_chunk else "Опора на мат. ожидание"

                    stats_str = (
                        f"📊 {rag.get('sample_count', 0)} лотов | "
                        f"Med: {rag.get('median_price', 0)}₽ | "
                        f"Avg: {rag.get('avg_price', 0)}₽"
                    )

                    log_msg = (
                        f"🧠 ПАМЯТЬ ({item.get('title', '')[:20]}...):\n"
                        f"   └─ {stats_str}\n"
                        f"   └─ Режим: {status_icon} -> {preview}"
                    )

                rag_messages_list.append(log_msg)

                similar_items = TextMatcher.filter_similar_items(
                    target_title=item.get('title', ''), 
                    all_items=items,
                    threshold=0.35
                )

                p = PromptBuilder.build_analysis_prompt(
                    items=similar_items,
                    current_item=item,
                    user_instructions=instr,
                    interests=interests,
                    rag_context=rag,
                    search_mode=search_mode
                )
                prompts_list.append(p)

        if self.processing_worker and self.processing_worker.isRunning():
            self.processing_worker.stop()
            self.processing_worker.wait()

        self.processing_worker = AIProcessingWorker(
            port=self.server_manager.get_port(),
            items=items,
            prompts=prompts_list,
            rag_messages=rag_messages_list,
            context=context,
            model_name=self._model_name
        )
        self.processing_worker.progress_value.connect(self.ai_progress_value.emit)
        self.processing_worker.result_signal.connect(self.result_signal.emit)
        self.processing_worker.finished_signal.connect(self.finished_signal.emit)
        self.processing_worker.finished_signal.connect(self.all_finished_signal.emit)
        self.processing_worker.finished_signal.connect(self._on_processing_finished)
        self.processing_worker.error_signal.connect(self.error_signal.emit)
        self.processing_worker.start()

    def start_cultivation_for_chunk(self, chunk_id, chunk_type, prompt, on_complete, user_instructions: str = ""):
        if any(item['id'] == chunk_id for item in self._cultivation_queue):
            return

        self._cultivation_queue.append({
            "id": chunk_id,
            "type": chunk_type,
            "prompt": prompt,
            "callback": on_complete,
            "user_instructions": user_instructions
        })
        
        logger.info(f"Чанк {chunk_id} добавлен в очередь (всего: {len(self._cultivation_queue)})", token="ai-cult")
        
        QTimer.singleShot(100, self._process_cultivation_queue)

    def _process_cultivation_queue(self):
        if self._is_cultivating_now:
            return

        if not self._cultivation_queue:
            return

        if not self._server_ready:
            self.ensure_server()
            QTimer.singleShot(1000, self._process_cultivation_queue)
            return

        self._is_cultivating_now = True
        task = self._cultivation_queue.pop(0)
        
        chunk_id = task["id"]
        logger.info(f"Начало обработки из очереди: чанк {chunk_id}", token="ai-cult")

        port = self.server_manager.get_port()
        worker = AIChunkCultivationWorker(
            port=port,
            chunk_id=chunk_id,
            chunk_type=task["type"],
            memory_manager=self.memory_manager,
            model_name=self._model_name,
            prompt=task["prompt"],
            user_instructions=task.get("user_instructions", "")
        )
        
        self._chunk_workers[chunk_id] = worker

        def _handle_finished(result: dict):
            try:
                task["callback"](result)
            finally:
                w = self._chunk_workers.pop(chunk_id, None)
                if w:
                    w.quit()
                    w.wait()
                    w.deleteLater()
                
                self._is_cultivating_now = False
                QTimer.singleShot(1000, self._process_cultivation_queue)

        worker.finished.connect(_handle_finished)
        worker.error_signal.connect(self.error_signal.emit)
        worker.start()

    def _build_table_summary(self, items: List[Dict]) -> str:
        if not items:
            return "Таблица пуста."
        
        total = len(items)
        prices = [i.get('price', 0) for i in items if i.get('price', 0) > 0]
        
        if not prices:
            return f"В таблице {total} объявлений (цены не указаны)."
            
        avg_price = sum(prices) // len(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        from collections import Counter
        cat_counts = Counter()
        for i in items:
            title = i.get('title', '').split()
            if title:
                key = " ".join(title[:2]).lower()
                cat_counts[key] += 1
                
        top_cats = ", ".join([f"{k} ({v})" for k, v in cat_counts.most_common(3)])
        
        return (
            f"[СВОДКА ТЕКУЩЕЙ ТАБЛИЦЫ]\n"
            f"Всего товаров: {total}\n"
            f"Ценовой диапазон: {min_price} - {max_price} руб. (Средняя: {avg_price} руб.)\n"
            f"Топ категорий: {top_cats}\n"
            f"Примеры лотов: {items[0].get('title')} ({items[0].get('price')}р), {items[-1].get('title')}..."
        )

    def start_chat_request(self, messages: list, user_instructions: list = None, current_table_data: list = None):
        self.ensure_server()
        if not self._server_ready:
            self.server_ready_signal.connect(lambda: self.start_chat_request(messages, user_instructions, current_table_data), Qt.ConnectionType.SingleShotConnection)
            return

        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.wait()

        sys_content = PromptBuilder.get_chat_system_prompt()

        if user_instructions:
            rules = "\n".join([f"- {r}" for r in user_instructions])
            sys_content += f"\n\n[ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ]:\n{rules}"

        last_user_msgs = [m['content'] for m in messages if m['role'] == 'user'][-2:]
        search_context_query = " ".join(last_user_msgs).lower()
        
        db_search_context = ""
        rag_injection = ""

        if self.memory_manager:
            import re
            keywords = [w for w in re.split(r'\W+', search_context_query) if len(w) > 3 and w not in ['цена', 'сколько', 'стоит', 'привет']]

            if keywords:
                search_query = " ".join(keywords[:3])
                
                items = self.memory_manager.get_raw_items(search_query=search_query, limit=30)
                if items:
                    prices = [i['price'] for i in items if i['price'] > 0]
                    if prices:
                        avg_p = sum(prices) // len(prices)
                        db_search_context = (
                            f"\n[ПОИСК В БАЗЕ ПО '{search_query}']:\n"
                            f"- Найдено лотов: {len(items)}\n"
                            f"- Средняя цена: {avg_p} руб. (Мин: {min(prices)})\n"
                        )

                rag_data = self.memory_manager.get_rag_context_for_item(search_query)
                if rag_data:
                    q25 = rag_data.get('q25_price', 0)
                    median = rag_data.get('median_price', 0)
                    
                    rag_injection = (
                        f"\n\n[ЗНАНИЯ RAG ПО '{search_query}']\n"
                        f"• Справедливая цена (частник): ~{q25:,} руб.\n"
                        f"• Рыночная медиана: {median:,} руб.\n"
                        f"• Анализ: {rag_data.get('knowledge', '')[:200]}...\n"
                    )

        table_context = ""
        if current_table_data:
            table_context = self._build_table_summary(current_table_data)

        final_system_content = (sys_content + "\n" + db_search_context + "\n" + table_context + rag_injection)
        
        MAX_HISTORY = 6
        trimmed_messages = messages[-MAX_HISTORY:]
        
        final_messages = [{"role": "system", "content": final_system_content}]
        for m in trimmed_messages:
            if m['role'] != 'system':
                final_messages.append(m)

        self.chat_worker = AIChatWorker(
            port=self.server_manager.get_port(),
            messages=final_messages,
            model_name=self._model_name
        )
        self.chat_worker.response_signal.connect(self.chat_response_signal.emit)
        self.chat_worker.start()
    
    def _tick_analysis_timer(self):
        elapsed = int(time.time() - self.start_ts)
        time_str = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        logger.info(f"Прошедшее время анализа: {time_str}...", token="ai_timer")

    def _on_processing_finished(self):
        self.analysis_timer.stop()
        logger.delete_log("ai_batch") 

    def has_pending_tasks(self) -> bool:
        return (self.processing_worker and self.processing_worker.isRunning()) or (self.chat_worker and self.chat_worker.isRunning())

    def stop(self):
        if self.processing_worker:
            self.processing_worker.stop()
            self.processing_worker.wait()
            self.processing_worker = None
        if self.chat_worker:
            self.chat_worker.wait()
            self.chat_worker = None
        self.server_manager.stop_server()
        self._server_ready = False

    def refresh_resource_usage(self) -> dict:
        ram = self.server_manager.get_memory_info()
        return {
            "loaded": self._server_ready,
            "backend": self._backend,
            "model_name": self._model_name,
            "ram_mb": round(ram, 1),
            "vram_mb": 0.0, 
            "cpu_percent": 0.0,
            "gpu_percent": 0.0,
            "parser_eta_sec": 0,
            "ai_eta_sec": 0
        }
    
    def cleanup(self):
        self.stop()