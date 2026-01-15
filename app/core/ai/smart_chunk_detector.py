from typing import List, Dict
from app.core.log_manager import logger
from app.core.text_utils import FeatureExtractor

class SmartChunkDetector:
    
    @staticmethod
    def detect_candidates(memory_manager) -> List[Dict]:
        """
        Возвращает СПИСОК кандидатов на создание.
        """
        candidates = []

        try:
            # 1. Получаем статистику
            products = memory_manager.raw_data.get_all_product_keys()
            categories = memory_manager.raw_data.get_all_categories()
            
            # Кеш существующих ключей (чтобы не дублировать)
            existing_keys = set()
            all_kn = memory_manager.knowledge.get_knowledge(limit=10000)
            for k in all_kn:
                existing_keys.add((k['chunk_type'], k['chunk_key'].lower().strip()))

            def exists(ctype, ckey):
                return (ctype, ckey.lower().strip()) in existing_keys

            # 2. Категории (CATEGORY)
            for cat in categories:
                c_key = cat.get('name', 'UNKNOWN')
                count = cat.get('item_count', 0)
                
                # Порог 5 элементов
                if count >= 5 and not exists("CATEGORY", c_key):
                    candidates.append({
                        "type": "CATEGORY",
                        "key": c_key,
                        "title": f"Обзор категории: {c_key}",
                        "parent_key": None
                    })

            # 3. Продукты (PRODUCT)
            for prod in products:
                p_key = prod.get('key')
                count = prod.get('item_count', 0)
                display_name = prod.get('display_name') or p_key
                
                # Порог 8 элементов (чтобы была статистика)
                if count < 8: continue 
                if 'unknown' in p_key.lower() or 'misc' in p_key.lower(): continue

                if not exists("PRODUCT", p_key):
                    # Пытаемся определить родителя (Category Key)
                    semantic = FeatureExtractor.extract_semantic_data(display_name)
                    cat_key = semantic.get('category')
                    
                    candidates.append({
                        "type": "PRODUCT",
                        "key": p_key,
                        "title": f"Слепок товара: {display_name}",
                        "parent_key": cat_key
                    })

            # 4. Глобальные
            stats = memory_manager.get_stats()
            total = stats.get("total_chunks", 0) # Исправил ключ (был total)
            if not candidates and total > 10:
                if not exists("DATABASE", "general"):
                    candidates.append({"type": "DATABASE", "key": "general", "title": "Глобальная аналитика", "parent_key": None})
                if not exists("AI_BEHAVIOR", "user_behavior"):
                    candidates.append({"type": "AI_BEHAVIOR", "key": "user_behavior", "title": "Портрет пользователя", "parent_key": "general"})

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det", exc_info=True)

        return candidates