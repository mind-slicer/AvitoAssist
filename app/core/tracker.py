import time
import os
import json
import gzip
import random
from PyQt6.QtCore import QThread, pyqtSignal

from app.core.parser import AvitoParser
from app.core.log_manager import logger
from app.config import RESULTS_DIR

class AdTracker(QThread):
    item_updated = pyqtSignal(dict)  # Сигнал: (item_dict_with_source_path)
    
    def __init__(self, settings: dict, notifier):
        super().__init__()
        self.settings = settings
        self.notifier = notifier
        self._is_running = False
        self._starred_items = [] # Список словарей
        
        self.interval = self.settings.get("favorites_monitor_interval", 15) * 60

    def update_items_from_current_table(self, items: list, current_file_path: str):
        """
        Обновляет список, добавляя товары из ТЕКУЩЕЙ открытой таблицы.
        Не удаляет товары из ДРУГИХ файлов.
        """
        # 1. Удаляем из памяти старые записи, относящиеся к этому файлу (чтобы обновить их состояние)
        self._starred_items = [
            x for x in self._starred_items 
            if x.get('_source_file') != current_file_path
        ]
        
        # 2. Добавляем актуальные избранные
        count = 0
        for item in items:
            if item.get('starred', False):
                # Создаем копию, чтобы не менять данные в UI напрямую
                tracker_item = item.copy()
                tracker_item['_source_file'] = current_file_path # Запоминаем, откуда товар
                self._starred_items.append(tracker_item)
                count += 1
        
        # logger.info(f"Трекер: обновлен список из текущей таблицы (+{count} шт). Всего: {len(self._starred_items)}")

    def scan_global_favorites(self):
        """Сканирует ВСЕ файлы в папке results и ищет избранное"""
        if not os.path.exists(RESULTS_DIR): return

        logger.info("Трекер: Глобальное сканирование избранного...")
        total_found = 0
        self._starred_items = [] # Полный сброс перед глобальным сканом

        try:
            files = [f for f in os.listdir(RESULTS_DIR) if f.endswith('.json')]
            for filename in files:
                path = os.path.join(RESULTS_DIR, filename)
                try:
                    data = []
                    # Пытаемся открыть как JSON
                    try:
                        with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
                    except:
                        # Пытаемся как GZIP
                        with gzip.open(path, 'rt', encoding='utf-8') as f: data = json.load(f)
                    
                    if not isinstance(data, list): continue

                    file_stars = 0
                    for item in data:
                        if item.get('starred', False):
                            item['_source_file'] = path
                            self._starred_items.append(item)
                            file_stars += 1
                    
                    if file_stars > 0:
                        total_found += file_stars
                        
                except Exception as e:
                    pass # Битый файл пропускаем
            
            if total_found > 0:
                logger.success(f"Трекер: Загружено {total_found} товаров на слежение из {len(files)} файлов.")
            else:
                logger.info("Трекер: Избранных товаров в архивах не найдено.")

        except Exception as e:
            logger.error(f"Ошибка глобального сканирования: {e}")

    def update_settings(self, new_settings: dict):
        self.settings = new_settings
        self.interval = self.settings.get("favorites_monitor_interval", 15) * 60
        if self.notifier:
            self.notifier.update_config(
                new_settings.get("telegram_token", ""),
                new_settings.get("telegram_chat_id", "")
            )

    def run(self):
        self._is_running = True
        # Сначала делаем глобальный скан при запуске потока
        self.scan_global_favorites()
        
        while self._is_running:
            # Спим
            for _ in range(int(self.interval)):
                if not self._is_running: return
                time.sleep(1)
            
            if not self._starred_items: continue
            self._check_items()

    def stop(self):
        self._is_running = False
        self.wait()

    def _check_items(self):
        if not self.notifier.enabled: return

        logger.info(f"Трекер: Проверка {len(self._starred_items)} товаров...")
        
        try:
            with AvitoParser(debug_mode=False) as parser:
                # Копия списка для безопасной итерации
                items_snapshot = list(self._starred_items)
                
                for item in items_snapshot:
                    if not self._is_running: break
                    
                    link = item.get('link')
                    if not link: continue
                    
                    fresh_details = parser._deep_dive_get_details(link)
                    if not fresh_details: continue
                        
                    self._compare_and_notify(item, fresh_details)
                    time.sleep(random.uniform(5, 10))
                    
        except Exception as e:
            logger.error(f"Ошибка цикла трекера: {e}")

    def _compare_and_notify(self, old_item: dict, new_details: dict):
        changes = []
        updated_fields = {}

        # 1. Цена
        old_price = old_item.get('price', 0)
        new_price = new_details.get('price', 0)

        if new_price > 0 and old_price > 0 and new_price != old_price:
            diff = new_price - old_price
            icon = "📈" if diff > 0 else "📉"
            changes.append(f"{icon} Цена: {old_price:,} -> {new_price:,} ₽ ({diff:+,})")
            updated_fields['price'] = new_price

        # 2. Описание / Статус
        old_desc = old_item.get('description', '').strip()
        new_desc = new_details.get('description', '').strip()
        
        if old_desc and new_desc and old_desc != new_desc:
            stop_phrases = ["снято с публикации", "товар зарезервирован", "объявление закрыто", "товар купили"]
            is_closed = any(p in new_desc.lower() for p in stop_phrases)
            
            if is_closed:
                self.notifier.send_closed(old_item)
                updated_fields['starred'] = False # Снимаем звезду
            else:
                # changes.append("📝 Изменилось описание") # Можно раскомментировать, если нужно
                pass
            updated_fields['description'] = new_desc

        if changes:
            self.notifier.send_update(old_item, changes)
        
        # Если есть обновления - отправляем сигнал
        if updated_fields:
            # Обновляем локальную копию в памяти трекера
            old_item.update(updated_fields)
            
            # Если сняли звезду - удаляем из списка слежения
            if updated_fields.get('starred') is False:
                if old_item in self._starred_items:
                    self._starred_items.remove(old_item)
            
            # Отправляем сигнал для сохранения на диск
            self.item_updated.emit(old_item)