from typing import List, Tuple
from app.core.log_manager import logger


class SmartChunkDetector:
    
    @staticmethod
    def detect_new_chunks(memory_manager) -> List[Tuple[str, str, str]]:
        """
        Анализирует нормализованные данные (Products/Categories) из БД 
        и предлагает кандидатов на создание чанков.
        """
        to_create = []

        try:
            # 1. Получаем статистику по Продуктам (уже сгруппировано в БД)
            # Возвращает список dict: {'key': '...', 'display_name': '...', 'item_count': N, ...}
            products = memory_manager.raw_data.get_all_product_keys()
            
            # 2. Получаем статистику по Категориям
            categories = memory_manager.raw_data.get_all_categories()
            
            # 3. Анализ Категорий (CATEGORY chunks)
            for cat in categories:
                # cat: {'id': 1, 'name': 'GPU', 'item_count': 50}
                count = cat.get('item_count', 0)
                c_key = cat.get('name', 'UNKNOWN')
                
                # Порог: создаем чанк категории, если есть хотя бы 10 товаров
                if count >= 10:
                    existing = memory_manager.knowledge.get_chunk_by_key_and_type(c_key, "CATEGORY")
                    if not existing:
                        to_create.append(("CATEGORY", c_key, f"Обзор категории: {c_key}"))

            # 4. Анализ Продуктов (PRODUCT chunks)
            for prod in products:
                # prod: {'key': 'gpu_nvidia_rtx3060', 'display_name': 'RTX 3060', 'item_count': 12, ...}
                count = prod.get('item_count', 0)
                p_key = prod.get('key')
                display_name = prod.get('display_name') or p_key
                
                # Порог для конкретного товара
                if count < 5: 
                    continue
                
                # Пропускаем "мусорные" ключи
                if 'unknown' in p_key.lower() or 'misc' in p_key.lower():
                    continue

                existing = memory_manager.knowledge.get_chunk_by_key_and_type(p_key, "PRODUCT")
                if not existing:
                    to_create.append(("PRODUCT", p_key, f"Слепок товара: {display_name}"))

            # 5. Глобальные чанки (База и Поведение)
            stats = memory_manager.get_stats()
            total_items = stats.get("total", 0) if isinstance(stats, dict) else 0
            
            if total_items >= 20:
                if not memory_manager.knowledge.get_chunk_by_key_and_type("general", "DATABASE"):
                    to_create.append(("DATABASE", "general", "Глобальная аналитика базы"))

            if not memory_manager.knowledge.get_chunk_by_key_and_type("user_behavior", "AI_BEHAVIOR"):
                 to_create.append(("AI_BEHAVIOR", "user_behavior", "Портрет пользователя"))

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det", exc_info=True)

        return to_create

    @staticmethod
    def create_missing_chunks(memory_manager, chunk_manager):
        """
        Запускает детекцию и создание.
        """
        missing = SmartChunkDetector.detect_new_chunks(memory_manager)
        created = 0
        for chunk_type_str, key, title in missing:
            try:      
                chunk_manager.create_pending_chunk(
                    chunk_type_str,
                    key,
                    title
                )
                created += 1
            except Exception as e:
                logger.error(f"Failed to auto-create chunk {key}: {e}", token="ai-det")

        if created:
            logger.info(f"Сформировано {created} новых узлов знаний.", token="ai-det")