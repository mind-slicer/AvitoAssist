from typing import List, Dict
from app.core.log_manager import logger
from app.core.text_utils import FeatureExtractor

class SmartChunkDetector:

    @staticmethod
    def detect_candidates(memory_manager) -> List[Dict]:
        """
        Сканирует Raw Data и предлагает кандидатов для создания чанков знаний.
        Исправлено: Дедупликация заголовков и улучшенная связь Родитель-Ребенок.
        """
        candidates = []

        try:
            products = memory_manager.raw_data.get_all_product_keys()
            categories = memory_manager.raw_data.get_all_categories()

            # Кэш существующих чанков (ключ и заголовок)
            existing_keys = set()
            existing_titles = set()
            
            all_kn = memory_manager.knowledge.get_knowledge(limit=10000)
            for k in all_kn:
                existing_keys.add((k['chunk_type'], k['chunk_key'].lower().strip()))
                existing_titles.add(k['title'].strip())

            def exists(ctype, ckey):
                return (ctype, ckey.lower().strip()) in existing_keys

            # 1. Сначала обрабатываем КАТЕГОРИИ (чтобы они стали родителями)
            for cat in categories:
                c_key = cat.get('name', 'UNKNOWN')
                count = cat.get('item_count', 0)

                if count >= 3 and not exists("CATEGORY", c_key):
                    title = f"Обзор категории: {c_key}"
                    candidates.append({
                        "type": "CATEGORY",
                        "key": c_key,
                        "title": title,
                        "parent_key": None
                    })
                    # Добавляем в локальный кэш, чтобы продукты могли ссылаться
                    existing_keys.add(("CATEGORY", c_key.lower().strip()))

            # 2. Обрабатываем ПРОДУКТЫ
            for prod in products:
                p_key = prod.get('key')
                count = prod.get('item_count', 0)
                display_name = prod.get('display_name') or p_key
                category_name = prod.get('category_name')

                # Фильтр мусора
                if count < 5: continue
                if 'unknown' in p_key.lower() or 'misc' in p_key.lower(): continue

                if not exists("PRODUCT", p_key):
                    # Формируем заголовок
                    title = f"Слепок товара: {display_name}"
                    
                    # --- FIX: Дедупликация заголовков ---
                    if title in existing_titles:
                        # Если такой заголовок уже есть, пробуем уникализировать через ключ
                        # Например: "Слепок товара: RTX 4060 (MSI)"
                        short_suffix = p_key.split('_')[-1].upper()
                        if short_suffix not in title.upper():
                            title = f"{title} ({short_suffix})"
                        
                        # Если все равно дубль - пропускаем (слишком похожие данные)
                        if title in existing_titles:
                            continue

                    existing_titles.add(title)

                    candidates.append({
                        "type": "PRODUCT",
                        "key": p_key,
                        "title": title,
                        "parent_key": category_name # Используем точное имя категории из БД
                    })

            # Глобальные чанки
            stats = memory_manager.get_stats()
            total = stats.get("total", 0)
            if not candidates and total > 10:
                if not exists("DATABASE", "general"):
                    candidates.append({"type": "DATABASE", "key": "general", "title": "Глобальная аналитика", "parent_key": None})
                if not exists("AI_BEHAVIOR", "user_behavior"):
                    candidates.append({"type": "AI_BEHAVIOR", "key": "user_behavior", "title": "Портрет пользователя", "parent_key": "general"})

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det", exc_info=True)

        return candidates

    @staticmethod
    def create_missing_chunks(memory_manager, cultivation_manager):
        """Создает отсутствующие чанки на основе анализа данных"""
        candidates = SmartChunkDetector.detect_candidates(memory_manager)
        if not candidates:
            return 0
            
        created_count = 0
        
        # Сортируем: Сначала КАТЕГОРИИ, потом остальное
        # Это критично для parent_id
        candidates.sort(key=lambda x: 0 if x['type'] == 'CATEGORY' else 1)

        for c in candidates:
            # Пытаемся найти ID родителя
            parent_id = None
            if c.get('parent_key'):
                # Ищем по ключу (имя категории)
                parent_chunk = memory_manager.knowledge.get_chunk_by_key_and_type(c['parent_key'], "CATEGORY")
                if parent_chunk:
                    parent_id = parent_chunk['id']

            try:
                # Проверка на существование перед созданием (double check)
                existing = memory_manager.knowledge.get_chunk_by_key_and_type(c['key'], c['type'])
                if existing: continue

                new_id = memory_manager.add_knowledge(
                    chunk_type=c['type'],
                    chunk_key=c['key'],
                    title=c['title'],
                    status='PENDING',
                    parent_chunk_id=parent_id
                )
                
                if cultivation_manager:
                    cultivation_manager.chunk_status_changed.emit(new_id, 'PENDING')
                
                created_count += 1
                logger.info(f"Создан чанк [{new_id}] {c['title']}", token="ai-det")
                
            except Exception as e:
                logger.error(f"Ошибка создания {c['key']}: {e}", token="ai-det")
                
        return created_count