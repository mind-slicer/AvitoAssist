from collections import defaultdict
from typing import List, Tuple
from app.core.log_manager import logger
from app.core.text_utils import FeatureExtractor

class SmartChunkDetector:
    
    @staticmethod
    def detect_new_chunks(memory_manager) -> List[Tuple[str, str, str]]:
        """
        Анализирует сырые данные и предлагает кандидатов на создание чанков.
        Использует двухуровневую группировку: Кластер (Семейство) -> Продукт.
        """
        to_create = []

        try:
            rows = memory_manager.raw_data.get_items(limit=3000)
            if not rows:
                return []

            cluster_stats = defaultdict(int)
            product_stats = defaultdict(list)
            
            # Для сохранения красивых имен
            cluster_display_names = {}
            product_display_names = {}

            for row in rows:
                title = row.get('title', '')
                price = row.get('price', 0)
                
                # Safe integer conversion
                try:
                    price_int = int(price)
                except (ValueError, TypeError):
                    price_int = 0

                # ВАЖНО: Теперь передаем цену для улучшения точности экстрактора
                semantic = FeatureExtractor.extract_semantic_data(title, description="", price=price_int)

                p_key = semantic['product_key']
                c_key = semantic['cluster_key']
                entity_type = semantic['entity_type']
                clean_name = semantic['clean_name']

                valid_price = price_int > 100

                if c_key:
                    cluster_stats[c_key] += 1
                    if c_key not in cluster_display_names:
                        cluster_display_names[c_key] = clean_name

                if p_key and entity_type == 'PRODUCT':
                    if valid_price:
                        product_stats[p_key].append(price_int)

                    if p_key not in product_display_names:
                        product_display_names[p_key] = clean_name

            # 3. Анализ Кластеров (CATEGORY chunks)
            # Если в семействе (например, RTX 30 Series) много товаров -> создаем чанк категории
            for c_key, count in cluster_stats.items():
                if count >= 8: # Порог создания кластера
                    existing = memory_manager.knowledge.get_chunk_by_key_and_type(c_key, "CATEGORY")
                    if not existing:
                        # Формируем красивое название
                        display_name = cluster_display_names.get(c_key, c_key).upper()
                        # Если это спец. ключи из экстрактора, делаем их читаемыми
                        if "series" in c_key:
                            display_name = c_key.replace("gpu_", "").replace("cpu_", "").replace("_", " ").upper()
                        
                        to_create.append(("CATEGORY", c_key, f"Обзор семейства: {display_name}"))

            # 4. Анализ Продуктов (PRODUCT chunks)
            for p_key, prices in product_stats.items():
                count = len(prices)
                
                # Порог для конкретного товара ниже, чем для кластера
                if count < 5: continue

                # Проверка на качество данных (отсеиваем шум)
                if not SmartChunkDetector._is_data_clean(prices):
                    continue

                existing = memory_manager.knowledge.get_chunk_by_key_and_type(p_key, "PRODUCT")
                if not existing:
                    display_name = product_display_names.get(p_key, p_key)
                    to_create.append(("PRODUCT", p_key, f"Слепок товара: {display_name}"))

            # 5. Глобальные чанки (База и Поведение)
            total_items = memory_manager.get_stats().get("total", 0)
            if total_items >= 20:
                if not memory_manager.knowledge.get_chunk_by_key_and_type("general", "DATABASE"):
                    to_create.append(("DATABASE", "general", "Глобальная аналитика базы"))

            if not memory_manager.knowledge.get_chunk_by_key_and_type("user_behavior", "AI_BEHAVIOR"):
                 to_create.append(("AI_BEHAVIOR", "user_behavior", "Портрет пользователя"))

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det")

        return to_create

    @staticmethod
    def _is_data_clean(prices: List[int]) -> bool:
        """
        Фильтр "мусорных" чанков.
        Если разброс цен слишком дикий (коробка за 500р и карта за 30к),
        лучше не создавать чанк продукта, а оставить анализ на уровне кластера.
        """
        if not prices: return False
        avg = sum(prices) / len(prices)
        if avg < 500: return False # Слишком дешево для серьезного анализа

        # 1. Фильтр совсем низких выбросов (< 20% от средней)
        low_threshold = avg * 0.2
        valid_prices = [p for p in prices if p > low_threshold]
        
        # Если после фильтрации осталось мало товаров -> мусор
        if len(valid_prices) < len(prices) * 0.7:
            return False
            
        return True

    @staticmethod
    def create_missing_chunks(memory_manager, chunk_manager):
        """Запускает детекцию и создание."""
        missing = SmartChunkDetector.detect_new_chunks(memory_manager)
        created = 0
        for chunk_type_str, key, title in missing:
            try:      
                # Используем метод менеджера, он теперь принимает английские типы
                chunk_manager.create_pending_chunk(
                    chunk_type_str,
                    key,
                    title
                )
                created += 1
            except Exception as e:
                logger.error(f"Failed to auto-create chunk {key}: {e}", token="ai-det")

        if created:
            logger.info(f"Сформировано {created} новых узлов 'Нейро-БД'.", token="ai-det")