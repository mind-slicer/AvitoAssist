from collections import Counter, defaultdict
from typing import List, Tuple, Dict
from app.core.log_manager import logger
from app.core.text_utils import FeatureExtractor

class SmartChunkDetector:
    
    @staticmethod
    def detect_new_chunks(memory_manager) -> List[Tuple[str, str, str]]:
        to_create = []

        try:
            rows = memory_manager.raw_data.get_items(limit=5000)
            if not rows:
                return []

            product_prices: Dict[str, List[int]] = defaultdict(list)
            category_counts = Counter()
            product_examples = {} 
            
            for row in rows:
                title = row.get('title', '')
                price = row.get('price', 0)
                
                # Используем обновленный FeatureExtractor (с поддержкой PC/System)
                semantic = FeatureExtractor.extract_semantic_data(title)

                cat = semantic['category']
                sub = semantic['sub_category']
                pkey = semantic['product_key']

                if not pkey: continue

                # Собираем цены для проверки качества данных
                if price > 100: # Игнорируем совсем мусор/договорные
                    product_prices[pkey].append(price)
                
                if pkey not in product_examples:
                    product_examples[pkey] = semantic['clean_name']

                if cat != 'MISC':
                    cat_key = f"{cat}_{sub}" if sub != 'general' else cat
                    category_counts[cat_key] += 1

            # Анализ продуктов с проверкой качества данных
            for pkey, prices in product_prices.items():
                count = len(prices)
                
                # 1. Порог количества
                if count < 5: continue

                # 2. Проверка валидности данных (Price Consistency Check)
                if not SmartChunkDetector._is_data_clean(prices):
                    logger.dev(f"Skipping dirty chunk candidate: {pkey} (High variance)", level="DEBUG")
                    continue

                # 3. Проверка существования
                existing = memory_manager.knowledge.get_chunk_by_key_and_type(pkey, "PRODUCT")
                if not existing:
                    nice_name = product_examples.get(pkey, pkey).upper()
                    to_create.append(("PRODUCT", pkey, f"Анализ товара: {nice_name}"))

            # Анализ категорий
            for cat_key, count in category_counts.items():
                if count >= 8:
                    existing = memory_manager.knowledge.get_chunk_by_key_and_type(cat_key, "CATEGORY")
                    if not existing:
                        nice_cat = cat_key.replace('_', ' ').upper()
                        to_create.append(("CATEGORY", cat_key, f"Обзор рынка: {nice_cat}"))

            # Глобальные чанки
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
    def _is_data_clean(prices: List[int]) -> bool:
        """
        Проверяет, не содержит ли набор данных явных выбросов (мусора),
        которые могут испортить статистику.
        Например: [30000, 32000, 29000, 1500] -> 1500 это коробка или кабель.
        """
        if not prices: return False
        avg = sum(prices) / len(prices)
        
        # Если среднее слишком мало, анализ не имеет смысла (мелочевка)
        if avg < 1000: return True 

        # Считаем товары, которые стоят дешевле 20% от средней цены
        # Это грубый, но эффективный фильтр "коробок и кабелей"
        low_threshold = avg * 0.2
        outliers = sum(1 for p in prices if p < low_threshold)
        
        # Если "мусора" больше 20% от выборки - данные грязные
        if outliers / len(prices) > 0.2:
            return False
            
        return True

    @staticmethod
    def create_missing_chunks(memory_manager, chunk_manager):
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
            logger.info(f"Обнаружено и создано {created} новых областей знаний.", token="ai-det")