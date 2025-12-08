import os
import json
import glob
import time
import asyncio
import threading
from typing import List, Dict, Optional
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, Qt

from app.config import AI_CTX_SIZE, AI_GPU_LAYERS, AI_SERVER_PORT, BASE_APP_DIR, MODELS_DIR
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
            for i, item in enumerate(self.items):
                if not self._is_running: break
                
                logger.progress(f"Нейросеть анализирует: {i + 1}/{total}", token="ai_batch")

                pct = int(((i + 1) / total) * 100)
                self.progress_value.emit(pct)
                
                # Формируем промпт
                prompt_text = self.prompts[i] if i < len(self.prompts) else self.prompts[-1]
                item_dump = json.dumps(item, ensure_ascii=False, indent=2)
                
                messages = [
                    {"role": "system", "content": "Ты — строгий эксперт. Твой ответ должен быть валидным JSON объектом."},
                    {"role": "user", "content": f"{prompt_text}\n\nОБЪЯВЛЕНИЕ:\n{item_dump}"}
                ]

                # Запрос
                response = await client.chat_completion(
                    model=self.model_name,
                    messages=messages,
                    params={"response_format": {"type": "json_object"}, "temperature": 0.1}
                )

                if response:
                    cleaned = self._clean_json(response)
                    self.result_signal.emit(i, cleaned, self.context)
                else:
                    self.error_signal.emit(f"Пустой ответ для товара #{i}")
            
            logger.success("Анализ нейросетью завершен")
            self.finished_signal.emit()

        except Exception as e:
            logger.error(f"Ошибка AI воркера: {e}")
            self.error_signal.emit(str(e))
        finally:
            await client.close()

    def _clean_json(self, text: str) -> str:
        text = text.replace("```json", "").replace("```", "").strip()
        return text

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
            resp = await client.chat_completion(self.model_name, self.messages, params={"temperature": 0.7})
            if resp:
                self.response_signal.emit(resp)
            else:
                self.response_signal.emit("Ошибка: сервер вернул пустой ответ.")
        except Exception as e:
            self.response_signal.emit(f"Ошибка связи: {e}")
        finally:
            await client.close()

# --- Главный менеджер (Оркестратор) ---
class AIManager(QObject):
    # Сигналы для совместимости с UI
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
        
        # Для мониторинга готовности (healthcheck)
        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._check_health_and_notify)
        self._server_ready = False

    def _find_default_model(self) -> Optional[str]:
        if not os.path.exists(MODELS_DIR):
            os.makedirs(MODELS_DIR, exist_ok=True)
            return None
        files = glob.glob(os.path.join(MODELS_DIR, "*.gguf"))
        if files:
            return sorted(files)[0]
        return None

    def has_model(self) -> bool:
        return self.current_model_path and os.path.exists(self.current_model_path)
    
    def set_model(self, filename: str):
        path = os.path.join(MODELS_DIR, filename)
        if os.path.exists(path):
            self.current_model_path = path
            self._model_name = filename
            # Перезапускаем менеджер с новой моделью
            self.server_manager.stop_server()
            self.server_manager = ServerManager(path, port=AI_SERVER_PORT)
            self.server_manager.server_started.connect(self._on_server_started_process)
            self.server_manager.error_occurred.connect(self.error_signal.emit)

    def ensure_server(self):
        """Запускает сервер, если он лежит"""
        if not self.has_model():
            self.error_signal.emit("Модель не найдена!")
            return

        if not self.server_manager.is_running():
            self.progress_signal.emit("Запуск локального AI сервера...")
            self.server_manager.start_server(ctx_size=AI_CTX_SIZE, gpu_layers=AI_GPU_LAYERS)
        elif self._server_ready:
            self.server_ready_signal.emit()

    def _on_server_started_process(self):
        """Процесс запущен, начинаем поллинг /health"""
        self.progress_signal.emit("Ожидание загрузки модели...")
        self.health_timer.start(1000) # Проверять каждую секунду

    def _check_health_and_notify(self):
        """Асинхронно проверяем хелсчек (через запуск одноразовой таски или клиента)"""
        # Здесь мы немного упростим и используем requests в потоке таймера, 
        # но по-хорошему тут тоже нужен async. Для простоты оставим requests с малым таймаутом,
        # так как это происходит редко.
        import requests
        try:
            port = self.server_manager.get_port()
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if resp.status_code == 200:
                self.health_timer.stop()
                self._server_ready = True
                self.progress_signal.emit("AI сервер готов!")
                self.server_ready_signal.emit()
        except:
            pass

    # --- Обработка товаров ---
    def start_processing(self, items: List[Dict], prompt: Optional[str], debug_mode: bool, context: Dict):
        self.ensure_server()
        
        # Если сервер еще не готов, сохраняем задачу и ждем сигнала
        if not self._server_ready:
            self.server_ready_signal.connect(lambda: self.start_processing(items, prompt, debug_mode, context), Qt.ConnectionType.SingleShotConnection)
            return

        # Подготовка промптов (RAG)
        prompts_list = []
        
        # Если это простой анализ
        if prompt: 
            prompts_list = [prompt] * len(items)
        else:
            # Если сложный анализ через PromptBuilder
            priority = context.get('priority', 1)
            user_instructions = context.get('user_instructions', "")
            for item in items:
                rag_context = None
                if self.memory_manager:
                    rag_context = self.memory_manager.get_stats_for_title(item.get('title', ''))
                
                p = PromptBuilder.build_analysis_prompt(
                    items=[item], # Передаем как список из 1 элемента, т.к. билдер ожидает список
                    priority=AnalysisPriority(priority),
                    current_item=item,
                    user_instructions=user_instructions,
                    rag_context=rag_context
                )
                prompts_list.append(p)

        # Запуск воркера
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

    # --- Чат ---
    def start_chat_request(self, messages: list, debug_mode: bool = False):
        self.ensure_server()

        if not self._server_ready:
            self.server_ready_signal.connect(lambda: self.start_chat_request(messages, debug_mode), Qt.ConnectionType.SingleShotConnection)
            return
            
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.wait()

        self.chat_worker = AIChatWorker(
            port=self.server_manager.get_port(),
            messages=messages,
            model_name=self._model_name
        )
        self.chat_worker.response_signal.connect(self.chat_response_signal.emit)
        self.chat_worker.start()

    def stop(self):
        if self.processing_worker:
            self.processing_worker.stop()
        self.server_manager.stop_server()
        self._server_ready = False

    def refresh_resource_usage(self) -> dict:
        ram = self.server_manager.get_memory_info()
        return {
            "loaded": self._server_ready,
            "backend": "auto",
            "model_name": self._model_name,
            "ram_mb": round(ram, 1),
            "vram_mb": 0.0, # Можно дописать через nvidia-smi, если нужно
            "cpu_percent": 0.0,
            "gpu_percent": 0.0
        }
    
    def cleanup(self):
        self.stop()