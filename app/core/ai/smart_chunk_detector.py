from collections import Counter
from typing import List, Tuple
from app.core.log_manager import logger
from app.core.text_utils import FeatureExtractor

class SmartChunkDetector:
    
    @staticmethod
    def detect_new_chunks(memory_manager) -> List[Tuple[str, str, str]]:
        """
        Возвращает список кандидатов на создание чанка:
        (CHUNK_TYPE, CHUNK_KEY, SUGGESTED_TITLE)
        """
        to_create = []

        try:
            # Получаем все сырые данные (лимит для скорости)
            rows = memory_manager.raw_data.get_items(limit=5000)
            if not rows:
                return []

            # Статистика
            product_counts = Counter()
            category_counts = Counter()
            product_examples = {} 
            
            for row in rows:
                title = row.get('title', '')
                semantic = FeatureExtractor.extract_semantic_data(title)
                
                cat = semantic['category']
                sub = semantic['sub_category']
                pkey = semantic['product_key']
                
                if not pkey: continue

                # Считаем конкретные продукты (для PRODUCT chunk)
                product_counts[pkey] += 1
                if pkey not in product_examples:
                    product_examples[pkey] = semantic['clean_name']

                # Считаем категории (для CATEGORY chunk)
                # Ключ категории: "CATEGORY_SUB", например "GPU_Nvidia"
                if cat != 'MISC':
                    cat_key = f"{cat}_{sub}" if sub != 'general' else cat
                    category_counts[cat_key] += 1

            # 1. Анализ кандидатов на PRODUCT чанки
            # Порог: > 5 товаров одной модели
            for pkey, count in product_counts.items():
                if count >= 3:
                    # Проверяем, нет ли уже такого чанка
                    existing = memory_manager.knowledge.get_chunk_by_key_and_type(pkey, "PRODUCT")
                    if not existing:
                        nice_name = product_examples.get(pkey, pkey).upper()
                        to_create.append(("PRODUCT", pkey, f"Анализ товара: {nice_name}"))

            # 2. Анализ кандидатов на CATEGORY чанки
            # Порог: > 15 товаров в одной категории
            for cat_key, count in category_counts.items():
                if count >= 8:
                    existing = memory_manager.knowledge.get_chunk_by_key_and_type(cat_key, "CATEGORY")
                    if not existing:
                        nice_cat = cat_key.replace('_', ' ').upper()
                        to_create.append(("CATEGORY", cat_key, f"Обзор рынка: {nice_cat}"))

            # 3. Глобальный DATABASE чанк
            total_items = memory_manager.get_stats().get("total", 0)
            if total_items >= 10:
                existing_db = memory_manager.knowledge.get_chunk_by_key_and_type("general", "DATABASE")
                if not existing_db:
                    to_create.append(("DATABASE", "general", "Глобальная аналитика базы"))

            existing_beh = memory_manager.knowledge.get_chunk_by_key_and_type("user_behavior", "AI_BEHAVIOR")
            if not existing_beh:
                 to_create.append(("AI_BEHAVIOR", "user_behavior", "Портрет пользователя"))

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det")

        return to_create

    @staticmethod
    def create_missing_chunks(memory_manager, chunk_manager):
        # Этот метод остается связующим звеном
        missing = SmartChunkDetector.detect_new_chunks(memory_manager)
        created = 0
        for chunk_type_str, key, title in missing:
            # Преобразуем строку в Enum, если нужно, или передаем строкой
            # В ChunkCultivationManager ожидается строка (обычно) или Enum.value
            try:
                # Простая проверка на дубликаты в очереди Pending происходит внутри create_pending_chunk
                # но мы можем проверить и здесь, чтобы не спамить логами
                chunk_manager.create_pending_chunk(
                    chunk_manager.__class__.ChunkType[chunk_type_str] if hasattr(chunk_manager.__class__, 'ChunkType') else chunk_type_str, 
                    key, 
                    title
                )
                created += 1
            except Exception as e:
                # Иногда тип может быть передан как строка, если Enum не импортирован здесь напрямую
                # Используем fallback
                try:
                    chunk_manager.create_pending_chunk(chunk_type_str, key, title)
                    created += 1
                except:
                    pass

        if created:
            logger.info(f"Обнаружено и создано {created} новых областей знаний.", token="ai-det")