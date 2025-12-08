import os
import sys
import json
import time
import subprocess
import threading
import psutil
from typing import List, Dict, Optional
from datetime import datetime
import glob
import requests

from PyQt6.QtCore import QObject, pyqtSignal, QProcess, QThread

from app.config import (
    AI_CTX_SIZE,
    AI_GPU_LAYERS,
    AI_SERVER_PORT,
    AI_BACKEND_PREFERENCE,
    BASE_APP_DIR,
    MODELS_DIR
)

class HealthCheckWorker(QThread):
    """Фоновый монитор здоровья сервера"""
    server_died = pyqtSignal()

    def __init__(self, port, callback):
        super().__init__()
        self.port = port
        self.callback = callback
        self.is_running = True

    def run(self):
        url = f"http://127.0.0.1:{self.port}/health"
        fails = 0
        while self.is_running:
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    fails = 0
                else:
                    fails += 1
            except:
                fails += 1
            
            if fails > 3: # 3 failures in a row
                if self.is_running:
                    self.callback()
                break
            
            time.sleep(5)

    def stop(self):
        self.is_running = False

class AIManager(QObject):
    progress_signal = pyqtSignal(str)
    result_signal = pyqtSignal(int, str, dict)
    finished_signal = pyqtSignal()
    all_finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    server_ready_signal = pyqtSignal()
    chat_response_signal = pyqtSignal(str)

    def __init__(self, memory_manager=None):
        super().__init__()
        self.log_file = os.path.join(BASE_APP_DIR, "debug_ai.log")
        self.process: QProcess | None = None
        self.task_queue = []
        self.current_context: dict = {}
        self.is_processing_batch = False
        self.server_port = AI_SERVER_PORT
        self.backend_type: str | None = None
        self._worker_thread: threading.Thread | None = None
        self._server_ready: bool = False
        self._debug_logs: bool = False
        self._shutting_down = False
        self._shutdown_event = threading.Event()
        self.server_ready_signal.connect(self._on_server_ready)

        self.current_model_path = self._find_default_model()
        self._model_name: str = os.path.basename(self.current_model_path) if self.current_model_path else "No Model"
        self._model_available: bool = self.current_model_path is not None
        self._model_loaded: bool = False
        self._ram_mb: float = 0.0
        self._vram_mb: float = 0.0
        self._cpu_percent: float = 0.0
        self._gpu_percent: float = 0.0

        self.processing_lock = False
        self.pending_items = []
        self.item_prompts = []
        self.use_individual_prompts = False
        self.base_prompt = ""

        self.memory_manager = memory_manager

        self.health_worker = None
    
    def _find_default_model(self) -> str | None:
        if not os.path.exists(MODELS_DIR):
            try:
                os.makedirs(MODELS_DIR)
                self._log_to_file(f"Создана папка моделей: {MODELS_DIR}", force=True)
            except Exception as e:
                self._log_to_file(f"Ошибка создания папки: {e}", force=True)
                return None

        files = glob.glob(os.path.join(MODELS_DIR, "*.gguf"))
        if files:
            files.sort()
            selected = files[0]
            self._log_to_file(f"Найдена модель: {os.path.basename(selected)}", force=True)
            return selected

        self._log_to_file("Модели не найдены в папке models/", force=True)
        return None

    def has_model(self) -> bool:
        return self._model_available and self.current_model_path and os.path.exists(self.current_model_path)

    def set_model(self, model_filename: str):
        path = os.path.join(MODELS_DIR, model_filename)
        if not os.path.exists(path):
            self._log_to_file(f"Модель не найдена: {path}", force=True)
            return

        if path == self.current_model_path and self.is_process_alive():
            return

        self._log_to_file(f"Переключение на модель: {model_filename}", force=True)
        self.stop_async(is_restart=True)
        self.current_model_path = path
        self._model_name = model_filename
        self._model_available = True
        self._model_loaded = False
        self._server_ready = False
        self.backend_type = None

    def refresh_model_list(self) -> list[str]:
        if not os.path.exists(MODELS_DIR):
            return []
        files = glob.glob(os.path.join(MODELS_DIR, "*.gguf"))
        return [os.path.basename(f) for f in sorted(files)]

    def _log_to_file(self, msg: str, force: bool = False):
        if self._shutting_down:
            return

        if force or self._debug_logs:
            print(f"[AI LOG] {msg}")

        if self._debug_logs or force:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    ts = datetime.now().strftime('%H:%M:%S')
                    f.write(f"[{ts}] {msg}\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                print(f"[AI Manager] Log Error: {e}")

    def detect_backend_type(self) -> str:
        pref = (AI_BACKEND_PREFERENCE or "auto").lower()
        if pref in {"cuda", "cpu", "vulkan"}:
            return pref

        try:
            subprocess.check_output(
                "nvidia-smi",
                stderr=subprocess.STDOUT,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            return "cuda"
        except Exception:
            pass

        base_dir = self._base_dir()
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        vulkan_exe = os.path.join(base_dir, "backends", "vulkan", "llama_cpp", exe_name)
        if os.path.exists(vulkan_exe):
            return "vulkan"

        return "cpu"

    def _server_executable_path(self, base_dir: str) -> tuple[str, str]:
        backend = self.detect_backend_type()
        exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        exe_path = os.path.join(base_dir, "backends", backend, "llama_cpp", exe_name)
        return backend, exe_path

    def is_process_alive(self) -> bool:
        return self.process is not None and self.process.state() == QProcess.ProcessState.Running

    def has_pending_tasks(self) -> bool:
        return bool(self.task_queue) or self.is_processing_batch

    def _base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.getcwd()

    def _ensure_server(self, debug_mode: bool) -> bool:
        if not self.has_model():
            self.error_signal.emit("Модель не загружена. Откройте 'Настройки' для установки.")
            return False

        if self.is_process_alive() and self._server_ready:
            return True

        if not self.is_process_alive():
            self._launch_server(debug_mode)
            return False
    
    def _launch_server(self, debug_mode: bool) -> None:
        if self._shutting_down:
            return

        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

        self._kill_process_on_port(self.server_port)

        base_dir = self._base_dir()
        backend, exe_path = self._server_executable_path(base_dir)
        self.backend_type = backend
        self._debug_logs = debug_mode
        self._vram_mb = 0.0
        self._ram_mb = 0.0
        self._model_loaded = False

        self._log_to_file(f"--- SERVER STARTING ({backend}) MODEL: {self._model_name} ---", force=True)

        if not os.path.exists(exe_path):
            self.error_signal.emit(f"Не найден llama-server: {exe_path}")
            return

        if not self.current_model_path or not os.path.exists(self.current_model_path):
            self.error_signal.emit(f"Модель не найдена: {self.current_model_path}")
            return

        self.process = QProcess()
        self.process.setProgram(exe_path)

        args = [
            "-m", self.current_model_path,
            "--ctx-size", str(AI_CTX_SIZE),
            "--port", str(self.server_port),
            "--host", "127.0.0.1",
            "--batch-size", "512",
        ]

        if AI_GPU_LAYERS is not None and AI_GPU_LAYERS >= 0:
            args += ["--gpu-layers", str(AI_GPU_LAYERS)]

        self.process.setArguments(args)
        self.process.setWorkingDirectory(os.path.dirname(exe_path))
        self.process.readyReadStandardError.connect(self._handle_server_stderr)
        self.process.readyReadStandardOutput.connect(self._handle_server_stdout)
        self.process.finished.connect(self.on_process_died)

        self._server_ready = False
        self.progress_signal.emit(f"Запуск LLM ({self._model_name})...")
        self.process.start()

        threading.Thread(target=self._wait_for_server_ready_bg, daemon=True).start()

    def _wait_for_server_ready_bg(self, timeout: float = 30.0) -> None:
        start = time.time()
        url_health = f"http://127.0.0.1:{self.server_port}/health"

        while time.time() - start < timeout:
            if self._shutdown_event.is_set():
                return

            if self.process and self.process.state() == QProcess.ProcessState.NotRunning:
                return

            try:
                resp = requests.get(url_health, timeout=1)
                if resp.status_code == 200:
                    self._server_ready = True
                    self.progress_signal.emit("AI сервер готов к работе.")
                    self.server_ready_signal.emit()
                    return
            except Exception:
                pass

            if self._shutdown_event.wait(timeout=1.0):
                return

        if not self._shutting_down:
            self.error_signal.emit("Таймаут запуска AI (30с).")
            self._log_to_file("TIMEOUT waiting for server health check", force=True)

    def _handle_server_stderr(self) -> None:
        if self._shutting_down or not self.process:
            return

        try:
            raw = self.process.readAllStandardError().data().decode("utf-8", errors="ignore")
            if not raw:
                return

            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue

                self._log_to_file(f"[AI STDERR] {line}")

                # Track model loading
                if "main: model loaded" in line:
                    self._model_loaded = True
                    print("[AI Manager] ✅ Model loaded successfully")

                # Track port binding errors
                if "bind" in line and "fail" in line:
                    self.error_signal.emit("Порт занят! Перезапустите приложение.")
                    self.stop()

                # Parse memory usage from logs
                if "model buffer size" in line or "KV buffer size" in line:
                    mb = self._parse_mib_from_line(line)
                    if mb:
                        self._vram_mb += mb
                        print(f"[AI Manager] Memory: +{mb:.1f} MiB (total: {self._vram_mb:.1f} MiB)")

        except Exception:
            pass

    def _handle_server_stdout(self) -> None:
        if self._shutting_down or not self.process:
            return

        try:
            raw = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            if raw.strip():
                self._log_to_file(f"[AI STDOUT] {raw.strip()}")
        except:
            pass
    
    def _kill_process_on_port(self, port):
        """Forcefully kills any process listening on the specific port."""
        print(f"[AI Manager] Checking port {port} for zombies...")
        found = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for con in proc.connections():
                    if con.laddr.port == port:
                        print(f"[AI Manager] Found zombie {proc.info['name']} (PID {proc.info['pid']}). Killing...")
                        proc.kill()
                        found = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if found:
            time.sleep(1) # Wait for OS to release port

    def on_process_died_unexpectedly(self):
        print("[AI Manager] Heartbeat lost! Restarting server...")
        self.stop_async(is_restart=True)

    def _on_server_ready(self) -> None:
        """Вызывается когда сервер готов"""
        # Новая система (pending_items) - для индивидуальных промптов
        if self.pending_items and self.processing_lock:
            self.progress_signal.emit("AI запущен...")
            self._process_next_item()

        # Старая система (task_queue) - для фильтрации
        self._process_next_task()

        if self.health_worker:
            self.health_worker.stop()
        self.health_worker = HealthCheckWorker(self.server_port, self.on_server_died_unexpectedly)
        self.health_worker.start()

    def on_server_died_unexpectedly(self):
        if self._shutting_down: return
        print("[AI Manager] CRITICAL: Server heartbeat lost. Restarting...")
        self.log_to_file("CRITICAL: Server heartbeat lost. Restarting...", force=True)
        self.server_ready = False
        
        # Trigger restart from main thread context if possible, or just re-launch
        # Since we are in a thread, be careful calling QObject methods directly if they touch UI
        # But launch_server only touches QProcess which is fine-ish, mostly need to be careful.
        # Safer to emit a signal connected to restart logic.
        self.error_signal.emit("AI Server Crashed. Restarting...")
        self._launch_server(self._debug_logs) # Quick restart

    def on_process_died(self, exit_code, exit_status) -> None:
        if self._shutting_down:
            return

        msg = f"[AI Manager] AI server process died. Code: {exit_code}"
        print(msg)
        self._log_to_file(msg, force=True)
        self.process = None
        self.is_processing_batch = False
        self._server_ready = False
        self.error_signal.emit(f"AI сервер упал (код {exit_code}).")

    def stop(self) -> None:
        self.stop_async()

    def stop_async(self, on_finished=None, is_restart=False) -> None:
        if self.health_worker:
            self.health_worker.stop()
        
        if not is_restart:
            self._shutting_down = True
            self._shutdown_event.set()

        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            print("[AI] Stopping server...")
            self.process.kill()
            self.process.waitForFinished(2000)

        self.process = None
        self._server_ready = False

    def shutdown_app(self, on_finished=None):
        self._shutting_down = True
        self.stop_async(on_finished=on_finished, is_restart=False)

    def start_processing(self, items: List[Dict], prompt: Optional[str], debug_mode: bool, context: Dict):
        """Запуск обработки списка товаров"""
        if self.processing_lock:
            print("[AI] ⚠️ Processing already in progress")
            return

        self.processing_lock = True
        self.pending_items = items.copy()
        self.current_context = context

        mode = context.get('mode', 'analysis')
        store_in_memory = context.get('store_in_memory', False)
        print(f"[AI Manager] 🔍 Получен контекст: store_in_memory={store_in_memory}, mode={mode}")

        # Строим промпты (с RAG если нужно)
        if prompt is None and mode == 'analysis':
            from app.core.ai.prompts import PromptBuilder, AnalysisPriority
            priority = context.get('priority', 1)
            user_instructions = context.get('user_instructions', "")

            self.item_prompts = []
            for item in items:
                rag_context = None
                if self.memory_manager:
                    title = item.get('title', '')
                    try:
                        rag_context = self.memory_manager.get_stats_for_title(item.get('title', ''))
                        if rag_context:
                            print(f"[AI Manager] RAG found stats for '{item['title']}': {rag_context}")
                        else:
                            print(f"[AI Manager] RAG: НЕ найдено для '{title['title']}'")
                    except Exception as e:
                        print(f"[AI Manager] RAG error: {e}")

                item_prompt = PromptBuilder.build_analysis_prompt(
                    items=items,
                    priority=AnalysisPriority(priority),
                    current_item=item,
                    user_instructions=user_instructions,
                    rag_context=rag_context
                )
                self.item_prompts.append(item_prompt)

            self.use_individual_prompts = True
        else:
            self.base_prompt = prompt
            self.use_individual_prompts = False

        # Запускаем сервер
        if not self._ensure_server(debug_mode):
            self.progress_signal.emit("Запуск AI сервера...")
            return

        # Сервер уже готов
        self.progress_signal.emit("AI запущен...")
        self._process_next_item()

    def _format_item_prompt(self, item: dict, prompt: str) -> str:
        """Форматирует промпт с данными товара"""
        item_dump = json.dumps(item, ensure_ascii=False, indent=2)
        full_prompt = f"""{prompt}

АНАЛИЗИРУЕМОЕ ОБЪЯВЛЕНИЕ:
{item_dump}

Верни JSON с анализом."""
        return full_prompt

    def _send_request(self, user_prompt: str, idx: int, item: dict):
        """Отправляет запрос к AI и обрабатывает ответ"""
        def worker():
            # Ждём готовности сервера
            wait = 0
            while not self._server_ready and wait < 60:
                if self._shutting_down:
                    self.processing_lock = False
                    return
                time.sleep(1)
                wait += 1

            if not self._server_ready:
                self.error_signal.emit("⚠️ Сервер не запустился за 60 секунд")
                self.processing_lock = False
                return

            # Вызов LLM
            try:
                response = self._call_llm_v2(user_prompt)
                if response:
                    self.result_signal.emit(idx, response, self.current_context)
                else:
                    self.error_signal.emit(f"Ошибка анализа товара #{idx}")
            except Exception as e:
                self._log_to_file(f"Error in _send_request: {e}", force=True)
                self.error_signal.emit(f"AI ошибка: {e}")
            finally:
                # Переходим к следующему товару
                self._process_next_item()

        # Запускаем в отдельном потоке
        threading.Thread(target=worker, daemon=True).start()

    def _process_next_item(self):
        """Обработка следующего товара в очереди"""
        if not self.pending_items:
            self.finished_signal.emit()
            if not self.has_pending_tasks():
                self.all_finished_signal.emit()
            self.processing_lock = False
            return

        item = self.pending_items.pop(0)
        idx = self.current_context.get('offset', 0)
        self.current_context['offset'] = idx + 1

        # Выбираем промпт: индивидуальный или общий
        if self.use_individual_prompts:
            prompt = self.item_prompts[idx] if idx < len(self.item_prompts) else self.base_prompt
        else:
            prompt = self.base_prompt

        # Формируем user_prompt с данными товара
        user_prompt = self._format_item_prompt(item, prompt)
        self.progress_signal.emit(f"AI анализ: {idx + 1}/{len(self.pending_items) + idx + 1}")

        # Отправляем запрос
        self._send_request(user_prompt, idx, item)

    def _process_next_task(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        if not self.task_queue:
            self.is_processing_batch = False
            self.all_finished_signal.emit()
            return

        next_task = self.task_queue[0]
        debug_mode = next_task.get("debug_mode", False)
        self._debug_logs = debug_mode

        if self._shutting_down:
            self.task_queue.clear()
            return

        if not self._ensure_server(debug_mode):
            return

        task = self.task_queue.pop(0)
        self.is_processing_batch = True
        self.current_context = task["context"]
        items = task["items"]
        prompt = task["prompt"]
        debug_mode_local = task.get("debug_mode", False)
        mode = self.current_context.get("mode", "analysis")
        verb = "Фильтрация" if mode == "filter" else "Анализ"
        total = len(items) if items else 0

        def worker():
            try:
                for idx, item in enumerate(items):
                    if self._shutting_down or not self.is_process_alive():
                        self.error_signal.emit("AI-сервер остановился.")
                        break

                    if total > 0:
                        self.progress_signal.emit(f"AI: {verb} {idx + 1}/{total}...")

                    answer = self._call_llm(prompt, item, debug_mode_local)
                    if answer is None:
                        continue

                    self.result_signal.emit(idx, answer, self.current_context)

                self.finished_signal.emit()
            finally:
                self.is_processing_batch = False
                self._worker_thread = None
                self._process_next_task()

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _call_llm(self, prompt: str, item: dict, debug_mode: bool) -> str | None:
        url = f"http://127.0.0.1:{self.server_port}/v1/chat/completions"
        system_prompt = "Ты — строгий эксперт. Отвечай ТОЛЬКО в JSON: { \"verdict\": \"GOOD\"|\"BAD\", ... }"
        item_dump = json.dumps(item, ensure_ascii=False)
        full_content = f"{system_prompt}\n\nЗАДАЧА:\n{prompt}\n\nОБЪЯВЛЕНИЕ:\n{item_dump}"

        if self._debug_logs:
            self._log_to_file(f"--- AI FILTER REQ ---\n{full_content[:200]}...")

        payload = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": full_content}],
            "temperature": 0.4,
            "stop": ["<start_of_turn>", "<end_of_turn>", "User:", "Assistant:", "\n\nUser"],
            "max_tokens": 8096,
            "top_p": 0.9,
            "min_p": 0.05,
            "repeat_penalty": 1.1,
        }

        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            if self._debug_logs:
                self._log_to_file(f"--- AI FILTER RESP ---\n{content}")
            return self._clean_json_response(content)
        except Exception as e:
            self.error_signal.emit(f"AI Req Error: {e}")
            return None

    def _call_llm_v2(self, full_prompt: str) -> str | None:
        """Вызов AI для анализа (версия 2 - для индивидуальных промптов)"""
        url = f"http://127.0.0.1:{self.server_port}/v1/chat/completions"

        if self._debug_logs:
            self._log_to_file(f"--- AI ANALYSIS REQ ---\n{full_prompt[:300]}...")

        payload = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": full_prompt}],
            "temperature": 0.1,
            "max_tokens": 256,
            "min_p": 0.05,
            "repeat_penalty": 1.1,
            "response_format": {"type": "json_object"}
        }

        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            if self._debug_logs:
                self._log_to_file(f"--- AI ANALYSIS RESP ---\n{content}")
            return self._clean_json_response(content)
        except Exception as e:
            self._log_to_file(f"AI Request Error: {e}", force=True)
            return None

    def _clean_json_response(self, text: str) -> str:
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False)
        except:
            return json.dumps({"verdict": "BAD", "reason": text[:50]}, ensure_ascii=False)

    def start_chat_request(self, messages: list):
        if self._shutting_down:
            return

        if not self._ensure_server(debug_mode=True):
            pass

        merged_content = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                merged_content += f"ИНСТРУКЦИЯ: {content}\n\n"
            else:
                merged_content += f"ПОЛЬЗОВАТЕЛЬ: {content}\n\n"

        final_messages = [{"role": "user", "content": merged_content}]

        def worker():
            wait = 0
            while not self._server_ready and wait < 60:
                if self._shutting_down:
                    return
                time.sleep(1)
                wait += 1

            if not self._server_ready:
                self.chat_response_signal.emit("⚠️ Ошибка: Сервер не запустился (см. debug_ai.log).")
                return

            response = self._raw_chat_completion(final_messages)
            if response:
                self.chat_response_signal.emit(response)
            else:
                self.chat_response_signal.emit("⚠️ Ошибка генерации ответа.")

        threading.Thread(target=worker, daemon=True).start()

    def _raw_chat_completion(self, messages: list) -> str | None:
        url = f"http://127.0.0.1:{self.server_port}/v1/chat/completions"

        if self._debug_logs:
            self._log_to_file(f"--- CHAT REQ ---\n{json.dumps(messages, indent=2)}")

        payload = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0.7,
            "stop": ["<|im_end|>", "<|endoftext|>", "user:", "system:"],
            "mirostat": 2,
            "mirostat_tau": 5.0,
            "mirostat_eta": 0.1,
            "repeat_penalty": 1.05,
            "min_p": 0.05,
            "max_tokens": 1024
        }

        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            if self._debug_logs:
                self._log_to_file(f"--- CHAT RESP ---\n{content}")
            return content
        except Exception as e:
            self._log_to_file(f"Chat Error: {e}", force=True)
            return None

    def _parse_mib_from_line(self, line: str) -> float | None:
        try:
            return float(line.split("MiB", 1)[0].strip().split()[-1])
        except:
            return None

    def _refresh_cuda_gpu_usage(self) -> None:
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                stderr=subprocess.STDOUT,
                creationflags=0x08000000 if sys.platform == "win32" else 0,
                timeout=1.0
            ).decode("utf-8", errors="ignore").strip()

            parts = [p.strip() for p in output.splitlines()[0].split(",")]
            if len(parts) >= 2:
                self._vram_mb = float(parts[0])
                self._gpu_percent = float(parts[1])
        except:
            return

    def refresh_resource_usage(self) -> dict:
        try:
            import psutil
        except ImportError:
            return self.get_stats()

        # Get RAM usage of llama-server process
        rss_server = 0
        if self.process and self.process.processId() != 0:
            try:
                rss_server = psutil.Process(int(self.process.processId())).memory_info().rss
            except:
                pass

        self._ram_mb = rss_server / (1024 * 1024)

        # Get CPU usage
        try:
            self._cpu_percent = psutil.cpu_percent(interval=0.0)
        except:
            pass

        # Get GPU stats if using CUDA
        if (self.backend_type or "").lower() == "cuda":
            self._refresh_cuda_gpu_usage()

        return self.get_stats()

    def get_stats(self) -> dict:
        """Get current AI stats"""
        return {
            "loaded": self._model_loaded and self._server_ready,
            "backend": self.backend_type or "unknown",
            "model_name": self._model_name,
            "ram_mb": round(self._ram_mb, 1),
            "vram_mb": round(self._vram_mb, 1),
            "cpu_percent": round(self._cpu_percent, 1),
            "gpu_percent": round(self._gpu_percent, 1),
        }