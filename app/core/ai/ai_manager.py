import os
import json
import glob
import asyncio
import re
from typing import List, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, Qt

from app.config import AI_CTX_SIZE, AI_GPU_LAYERS, AI_SERVER_PORT, MODELS_DIR
from app.core.ai.server_manager import ServerManager
from app.core.ai.llama_client import LlamaClient
from app.core.ai.prompts import PromptBuilder, AnalysisPriority
from app.core.log_manager import logger

# --- Воркер для пакетной обработки товаров ---
class AIProcessingWorker(QThread):
    progress_value = pyqtSignal(int)
    result_signal = pyqtSignal(int, str, dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, port: int, items: List[Dict], prompts: List[str], context: Dict, model_name: str):
        super().__init__()
        self.port = port
        self.items = items
        self.prompts = prompts
        self.context = context
        self.model_name = model_name
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        asyncio.run(self._process_async())

    async def _process_async(self):
        client = LlamaClient(self.port)
        try:
            total = len(self.items)
            
            # --- НАСТРОЙКИ ГЕНЕРАЦИИ (SMART PARAMS) ---
            gen_params = {
                "response_format": {"type": "json_object"}, 
                "temperature": 0.2,       # Низкая температура для строгой логики
                "top_k": 40,              # Ограничиваем выбор токенов
                "top_p": 0.9,             # Nucleus sampling
                "repeat_penalty": 1.1,    # Чтобы не зацикливался
                "max_tokens": 1024,
                # Mirostat делает ответы более "умными" и связными, жертвуя скоростью
                "mirostat_mode": 2,       
                "mirostat_tau": 5.0,
                "mirostat_eta": 0.1
            }

            for i, item in enumerate(self.items):
                if not self._is_running: break
                
                logger.progress(f"Нейросеть анализирует: {i + 1}/{total}", token="ai_batch")
                self.progress_value.emit(int(((i + 1) / total) * 100))
                
                prompt_text = self.prompts[i] if i < len(self.prompts) else self.prompts[-1]
                
                # Мини-дамп для экономии токенов, убираем лишнее
                clean_item = {k: v for k, v in item.items() if k in ['title', 'price', 'description', 'city', 'condition', 'seller_id']}
                item_dump = json.dumps(clean_item, ensure_ascii=False)
                
                messages = [
                    {"role": "system", "content": "Ты — строгий эксперт-скупщик. Отвечай ТОЛЬКО валидным JSON."},
                    {"role": "user", "content": f"{prompt_text}\n\nОБЪЯВЛЕНИЕ:\n{item_dump}"}
                ]

                response = await client.chat_completion(
                    model=self.model_name,
                    messages=messages,
                    params=gen_params
                )

                if response:
                    cleaned = self._clean_json(response)
                    self.result_signal.emit(i, cleaned, self.context)
                else:
                    self.error_signal.emit(f"Пустой ответ AI для #{i}")
            
            logger.success("Анализ нейросетью завершен")
            self.finished_signal.emit()

        except Exception as e:
            logger.error(f"Ошибка AI воркера: {e}")
            self.error_signal.emit(str(e))
        finally:
            await client.close()

    def _clean_json(self, text: str) -> str:
        # Пытаемся найти JSON объект, если модель выдала лишний текст
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        return text.replace("```json", "").replace("```", "").strip()

# --- Воркер для чата ---
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
            # Для чата параметры мягче, чтобы он был "креативнее" в общении
            chat_params = {
                "temperature": 0.7,
                "top_k": 50,
                "top_p": 0.95,
                "repeat_penalty": 1.1,
                "max_tokens": 2048
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

class AICultivationWorker(QThread):
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, port, memory_manager, model_name):
        super().__init__()
        self.port = port
        self.memory = memory_manager
        self.model_name = model_name
        self._is_running = True

    def run(self):
        asyncio.run(self._cultivate())

    async def _cultivate(self):
        client = LlamaClient(self.port)
        try:
            # Берем категории, где много товаров (топ-10 по активности)
            # Используем прямой SQL к MemoryManager, так как метода get_top пока нет
            raw_stats = self.memory.get_all_statistics(limit=15)
            
            processed_count = 0
            for st in raw_stats:
                if not self._is_running: break
                
                key = st['product_key']
                items = self.memory.find_similar_items(key, limit=50)
                
                # Анализируем только если набралось хотя бы 5 товаров
                if len(items) < 5: continue 

                prompt = PromptBuilder.build_knowledge_prompt(key, items)
                if not prompt: continue

                logger.progress(f"Культивация знаний: {key}...", token="ai_cult")
                
                response = await client.chat_completion(
                    self.model_name,
                    [{"role": "user", "content": prompt}],
                    params={"response_format": {"type": "json_object"}, "temperature": 0.2}
                )

                if response:
                    try:
                        # ✅ УЛУЧШЕННАЯ очистка JSON
                        clean_json = response.strip()

                        # Удалить markdown обертки
                        if clean_json.startswith("``````"):
                            clean_json = clean_json[7:-3].strip()
                        elif clean_json.startswith("``````"):
                            clean_json = clean_json[3:-3].strip()

                        # Удалить "json" в начале если есть
                        if clean_json.lower().startswith("json"):
                            clean_json = clean_json[4:].strip()

                        # ✅ ДОБАВИТЬ - попытка восстановить незакрытые кавычки
                        # Если строка обрывается посередине - обрезать до последней закрытой скобки
                        if clean_json.count('"') % 2 != 0:
                            logger.warning(f"Незакрытые кавычки в JSON для {key}, пытаюсь восстановить...", token="ai-cult")
                            # Найти последнюю закрытую фигурную скобку
                            last_brace = clean_json.rfind('}')
                            if last_brace > 0:
                                clean_json = clean_json[:last_brace + 1]

                        data = json.loads(clean_json)

                        self.memory.add_knowledge(
                            product_key=key,
                            summary=data.get('summary', ''),
                            risks=data.get('risk_factors', ''),
                            prices=data.get('price_range_notes', '')
                        )
                        processed_count += 1
                        logger.success(f"✅ Сохранены знания для: {key}", token="ai-cult")

                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка сохранения знаний для {key}: {e}...", token="ai-cult")
                        logger.dev(f"Проблемный JSON: {clean_json[:500]}", level="ERROR")
                    except Exception as e:
                        logger.error(f"Ошибка для {key}: {e}...", token="ai-cult")

            if processed_count > 0:
                logger.success(f"База знаний обновлена: +{processed_count} записей", token="ai_cult")
            else:
                logger.info("Нет новых данных для культивации", token="ai_cult")
                
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            await client.close()

# --- Главный менеджер (Оркестратор) ---
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
        elif self._server_ready:
            self.server_ready_signal.emit()

    def _on_server_started_process(self):
        self.progress_signal.emit("Загрузка нейросети...")
        self.health_timer.start(1000)

    def _check_health_and_notify(self):
        import requests
        try:
            port = self.server_manager.get_port()
            logger.info(f"Checking AI server health on port {port}", token="ai-health")
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if resp.status_code == 200:
                self.health_timer.stop()
                self._server_ready = True
                logger.info("AI server is ready", token="ai-health")
                self.progress_signal.emit("AI готов к работе")
                self.server_ready_signal.emit()
            else:
                logger.error(f"AI server health check failed with status code {resp.status_code}", token="ai-health")
        except Exception as e:
            logger.error(f"AI server health check failed: {e}", token="ai-health")

    def start_processing(self, items: List[Dict], prompt: Optional[str], debug_mode: bool, context: Dict):
        self.ensure_server()
        if not self._server_ready:
            self.server_ready_signal.connect(lambda: self.start_processing(items, prompt, debug_mode, context), Qt.ConnectionType.SingleShotConnection)
            return

        prompts_list = []
        if prompt: 
            prompts_list = [prompt] * len(items)
        else:
            # Авто-промпт
            prio = context.get('priority', 1)
            instr = context.get('user_instructions', "")
            for item in items:
                rag = None
                if self.memory_manager:
                    # Получаем RAG контекст для товара
                    rag = self.memory_manager.get_rag_context_for_item(item.get('title', ''))
                
                # Строим промпт с новой структурой
                p = PromptBuilder.build_analysis_prompt(
                    items=[item], 
                    priority=prio, 
                    current_item=item, 
                    user_instructions=instr, 
                    rag_context=rag
                )
                prompts_list.append(p)

        if self.processing_worker and self.processing_worker.isRunning():
            self.processing_worker.stop()
            self.processing_worker.wait()

        self.processing_worker = AIProcessingWorker(
            port=self.server_manager.get_port(),
            items=items,
            prompts=prompts_list,
            context=context,
            model_name=self._model_name
        )
        self.processing_worker.progress_value.connect(self.ai_progress_value.emit)
        self.processing_worker.result_signal.connect(self.result_signal.emit)
        self.processing_worker.finished_signal.connect(self.finished_signal.emit)
        self.processing_worker.finished_signal.connect(self.all_finished_signal.emit)
        self.processing_worker.error_signal.connect(self.error_signal.emit)
        self.processing_worker.start()

    def start_cultivation(self):
        # 1. Убедиться, что есть модель и сервер запущен
        self.ensure_server()
        
        # Если сервер ещё поднимается – подождать готовности
        if not self._server_ready:
            # Повторно запустим культивацию, когда сервер станет готов
            self.server_ready_signal.connect(
                lambda: self.start_cultivation(),
                Qt.ConnectionType.SingleShotConnection
            )
            # Мягкий информационный сигнал в UI (а не ошибка)
            logger.info("Идёт запуск AI сервера, культивация начнётся автоматически...", token="ai-cult")
            return
        
        # 2. Если уже что-то делает – не запускать вторую задачу
        if self.has_pending_tasks():
            logger.warning("ИИ занят другой задачей...", token="ai-cult")
            self.error_signal.emit("ИИ занят другой задачей")
            # Считаем операцию «отменённой» – сообщаем об окончании
            self.all_finished_signal.emit()
            return
        
        # 3. Нормальный путь: запускаем воркер культивации
        logger.info("Запуск воркера культивации...", token="ai-cult")
        self.cultivation_worker = AICultivationWorker(
            port=self.server_manager.get_port(),
            memory_manager=self.memory_manager,
            model_name=self._model_name
        )
        # По завершении воркера поднимем all_finished, чтобы UI разблокировался
        self.cultivation_worker.finished_signal.connect(self.all_finished_signal.emit)
        self.cultivation_worker.error_signal.connect(self.error_signal.emit)
        self.cultivation_worker.start()

    def start_chat_request(self, messages: list, user_instructions: list = None):
        self.ensure_server()
        if not self._server_ready:
            self.server_ready_signal.connect(lambda: self.start_chat_request(messages, user_instructions), Qt.ConnectionType.SingleShotConnection)
            return
            
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.wait()

        # 1. Подготовка системного промпта
        sys_content = PromptBuilder.SYSTEM_BASE
        
        # Добавляем инструкции пользователя (ПРИКАЗЫ)
        if user_instructions:
            rules = "\n".join([f"- {r}" for r in user_instructions])
            sys_content += f"\n\n[ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ]:\n{rules}"

        # 2. ОРКЕСТРАТОР: Анализ намерения
        last_msg = messages[-1]['content'].lower() if messages else ""
        # Триггеры вопроса о цене/рынке
        is_market_query = any(w in last_msg for w in ['цена', 'сколько', 'рынок', 'стоит', 'стоимость', 'почем', 'анализ', 'статистика', 'средняя', 'медиана'])
        
        rag_injection = ""
        if is_market_query and self.memory_manager:
            logger.info("Чат: Запрос данных из памяти...", token="ai_chat")
            
            # Эвристика: ищем контекст по всему тексту запроса (обрезая лишнее)
            search_key = last_msg[:60]
            rag_data = self.memory_manager.get_rag_context_for_item(search_key)
            
            if rag_data:
                rag_injection = (
                    f"\n\n[ДАННЫЕ ИЗ ПАМЯТИ ПО ЗАПРОСУ]:\n"
                    f"Найдено лотов: {rag_data['sample_count']}\n"
                    f"Медианная цена: {rag_data['median_price']} руб.\n"
                    f"Тренд: {rag_data.get('trend', 'N/A')}.\n"
                    f"Знания ИИ: {rag_data.get('knowledge', 'Нет')}\n"
                    f"ВАЖНО: ИСПОЛЬЗУЙ ЭТИ ЦИФРЫ ДЛЯ ОТВЕТА."
                )
            else:
                rag_injection = "\n\n[ПАМЯТЬ]: Данных по этому конкретному товару в базе пока нет. Честно скажи об этом."

        MAX_HISTORY = 5
        trimmed_messages = messages[-MAX_HISTORY:] if len(messages) > MAX_HISTORY else messages

        MAX_MSG_LENGTH = 1000
        for msg in trimmed_messages:
            if len(msg.get('content', '')) > MAX_MSG_LENGTH:
                msg['content'] = msg['content'][:MAX_MSG_LENGTH] + "...[обрезано]"

        final_messages = [{"role": "system", "content": sys_content + rag_injection}]
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
        self.server_ready = False

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