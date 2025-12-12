# app/core/ai/smart_chunk_detector.py

from datetime import datetime
from typing import List, Tuple
from collections import Counter
import re
from app.core.log_manager import logger

class SmartChunkDetector:
    """
    Автоматически определяет, какие чанки нужно создать
    на основе текущего содержимого БД.
    """
    
    @staticmethod
    def _generate_key(title: str) -> str:
        # Простая нормализация для группировки: берем первые 3 слова
        clean = re.sub(r'\b(продам|куплю|торг|новый|бу|цена)\b', '', title.lower(), flags=re.I)
        words = clean.split()
        return " ".join(words[:3]) if words else "unknown"

    @staticmethod
    def detect_new_chunks(memory_manager) -> List[Tuple[str, str, str]]:
        """
        Сканирует БД (таблицу items) и возвращает кандидатов на создание.
        """
        to_create = []
        
        try:
            # 1. CATEGORY чанки (Сканируем живые данные)
            # Получаем все заголовки товаров
            rows = memory_manager._execute("SELECT title FROM items", fetch_all=True)
            if rows:
                titles = [r['title'] for r in rows]
                
                # Группируем по ключам
                key_counts = Counter()
                key_titles = {} # Сохраняем пример заголовка для названия
                
                for t in titles:
                    k = SmartChunkDetector._generate_key(t)
                    if len(k) > 3: # Игнорируем слишком короткие ключи
                        key_counts[k] += 1
                        if k not in key_titles:
                            key_titles[k] = t

                # Анализируем группы
                for key, count in key_counts.items():
                    # ПОРОГ: Если товаров > 5 и это не мусор
                    if count >= 5:
                        # Проверяем, есть ли уже такой чанк
                        existing = memory_manager.get_chunk_by_key("PRODUCT", key) # Проверяем как PRODUCT (он универсальнее)
                        if not existing:
                            # Проверяем как CATEGORY
                            existing_cat = memory_manager.get_chunk_by_key("CATEGORY", key)
                            if not existing_cat:
                                # Создаем PRODUCT чанк, так как он более детальный для конкретной группы
                                nice_title = " ".join([w.capitalize() for w in key.split()])
                                to_create.append((
                                    "PRODUCT", # Лучше создавать PRODUCT для конкретных групп (видеокарта X)
                                    key,
                                    f"Анализ: {nice_title}"
                                ))

            # 2. DATABASE чанк (Общая аналитика)
            base_stats = memory_manager.get_stats()
            total_items = base_stats.get("total", 0)
            
            if total_items >= 20:
                existing_db = memory_manager.get_chunk_by_key("DATABASE", "general")
                if not existing_db:
                    to_create.append((
                        "DATABASE",
                        "general",
                        "Глобальная аналитика базы данных"
                    ))
                
        except Exception as e:
            logger.error(f"Error detecting new chunks: {e}", token="ai-det")
        
        return to_create
    
    @staticmethod
    def create_missing_chunks(memory_manager, chunk_manager):
        missing = SmartChunkDetector.detect_new_chunks(memory_manager)
        
        created_count = 0
        for chunk_type_str, chunk_key, title in missing:
            from app.core.ai.chunk_cultivation import ChunkType
            
            ctype = None
            if chunk_type_str == "CATEGORY": ctype = ChunkType.CATEGORY
            elif chunk_type_str == "DATABASE": ctype = ChunkType.DATABASE
            elif chunk_type_str == "PRODUCT": ctype = ChunkType.PRODUCT
            elif chunk_type_str == "AI_BEHAVIOR": ctype = ChunkType.AI_BEHAVIOR
            
            if ctype:
                chunk_manager.create_pending_chunk(ctype, chunk_key, title)
                created_count += 1
        
        if created_count > 0:
            logger.info(f"SmartDetector: Создано {created_count} новых задач для памяти", token="ai-det")