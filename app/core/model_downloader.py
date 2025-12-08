"""
Модуль для скачивания моделей с HuggingFace Hub
"""
import os
import threading
import time
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal
from app.config import MODELS_DIR, DEFAULT_MODEL_NAME, DEFAULT_MODEL_REPO


class ModelDownloader(QObject):
    """
    Скачивание моделей с прогрессом и возможностью отмены
    """
    # Сигналы
    progress_updated = pyqtSignal(int, float, float, str)
    download_finished = pyqtSignal(str)
    download_failed = pyqtSignal(str)
    download_cancelled = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._cancel_flag = threading.Event()
        self._download_thread: Optional[threading.Thread] = None
        self._is_downloading = False
    
    def is_downloading(self) -> bool:
        """Проверка активного скачивания"""
        return self._is_downloading
    
    def start_download(self, repo_id: str = None, filename: str = None):
        """
        Начать скачивание модели
        
        Args:
            repo_id: ID репозитория на HuggingFace (по умолчанию из config)
            filename: Имя файла модели (по умолчанию из config)
        """
        if self._is_downloading:
            self.download_failed.emit("Уже идет скачивание")
            return
        
        repo_id = repo_id or DEFAULT_MODEL_REPO
        filename = filename or DEFAULT_MODEL_NAME
        
        self._cancel_flag.clear()
        self._is_downloading = True
        
        self._download_thread = threading.Thread(
            target=self._download_worker,
            args=(repo_id, filename),
            daemon=True
        )
        self._download_thread.start()
    
    def cancel_download(self):
        """Отменить текущее скачивание"""
        if self._is_downloading:
            self._cancel_flag.set()
    
    def _download_worker(self, repo_id: str, filename: str):
        """Worker thread для скачивания"""
        try:
            from huggingface_hub import hf_hub_download
            import requests
            from requests.exceptions import RequestException
            
            # Создаем папку если нужно
            os.makedirs(MODELS_DIR, exist_ok=True)
            
            target_path = os.path.join(MODELS_DIR, filename)
            
            if os.path.exists(target_path) and os.path.getsize(target_path) > 1024:
                self.download_finished.emit(target_path)
                self._is_downloading = False
                return
            
            try:
                from huggingface_hub import hf_hub_url
                
                url = hf_hub_url(repo_id=repo_id, filename=filename)
                
                # Скачивание с прогрессом
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                chunk_size = 8192  # 8KB chunks
                
                start_time = time.time()
                last_update_time = start_time
                last_downloaded = 0
                
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        # Проверка на отмену
                        if self._cancel_flag.is_set():
                            # Удаляем частично скачанный файл
                            try:
                                f.close()
                                os.remove(target_path)
                            except:
                                pass
                            self.download_cancelled.emit()
                            self._is_downloading = False
                            return
                        
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            current_time = time.time()
                            if current_time - last_update_time >= 0.5:
                                elapsed = current_time - last_update_time
                                speed_bytes = (downloaded_size - last_downloaded) / elapsed
                                speed_mb = speed_bytes / (1024 * 1024)
                                
                                percent = int((downloaded_size / total_size) * 100) if total_size > 0 else 0
                                downloaded_mb = downloaded_size / (1024 * 1024)
                                total_mb = total_size / (1024 * 1024)
                                
                                if speed_bytes > 0:
                                    remaining_bytes = total_size - downloaded_size
                                    eta_seconds = remaining_bytes / speed_bytes
                                    eta_str = self._format_time(eta_seconds)
                                else:
                                    eta_str = "Расчет..."
                                
                                speed_str = f"{speed_mb:.1f} MB/s"
                                
                                self.progress_updated.emit(
                                    percent, 
                                    downloaded_mb, 
                                    total_mb, 
                                    f"{speed_str} | ETA: {eta_str}"
                                )
                                
                                last_update_time = current_time
                                last_downloaded = downloaded_size
                
                if total_size > 0:
                    self.progress_updated.emit(
                        100,
                        total_size / (1024 * 1024),
                        total_size / (1024 * 1024),
                        "Завершено"
                    )
                
                self.download_finished.emit(target_path)
                
            except RequestException as e:
                self.download_failed.emit(f"Ошибка сети: {str(e)}")
            except Exception as e:
                self.download_failed.emit(f"Ошибка скачивания: {str(e)}")
        
        except ImportError:
            self.download_failed.emit(
                "Библиотека huggingface_hub не установлена.\n"
                "Установите: pip install huggingface_hub"
            )
        except Exception as e:
            self.download_failed.emit(f"Критическая ошибка: {str(e)}")
        finally:
            self._is_downloading = False
    
    def _format_time(self, seconds: float) -> str:
        """Форматирование времени в читаемый вид"""
        if seconds < 60:
            return f"{int(seconds)}с"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}м {int(seconds % 60)}с"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}ч {minutes}м"