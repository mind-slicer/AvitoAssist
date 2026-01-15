from typing import List, Dict
from app.core.log_manager import logger

class SmartChunkDetector:

    @staticmethod
    def detect_candidates(memory_manager) -> List[Dict]:
        candidates = []
        try:
            # Получаем данные
            products = memory_manager.raw_data.get_all_product_keys()
            categories = memory_manager.raw_data.get_all_categories()
            
            # Кэш существующих (Type, Key)
            existing_keys = set()
            all_kn = memory_manager.knowledge.get_knowledge(limit=10000)
            for k in all_kn:
                existing_keys.add((k['chunk_type'], k['chunk_key'].lower().strip()))

            def exists(ctype, ckey):
                return (ctype, ckey.lower().strip()) in existing_keys

            # 1. CATEGORY (Всегда создаем, если есть хоть что-то)
            # Это "Вены" системы.
            for cat in categories:
                c_key = cat.get('name', 'UNKNOWN')
                count = cat.get('item_count', 0)
                
                # Порог для категории минимальный, чтобы структура существовала
                if count >= 1 and not exists("CATEGORY", c_key):
                    candidates.append({
                        "type": "CATEGORY",
                        "key": c_key,
                        "title": f"Обзор категории: {c_key}",
                        "parent_key": f"db_{c_key.split('_')[0].lower()}" # Привязка к тематической БД
                    })
                    existing_keys.add(("CATEGORY", c_key.lower().strip()))

            # 2. PRODUCT (Только если > 10 элементов)
            # Это "Единицы смысла".
            for prod in products:
                p_key = prod.get('key')
                count = prod.get('item_count', 0)
                display_name = prod.get('display_name') or p_key
                category_name = prod.get('category_name')

                # НОВЫЙ ПОРОГ: 10
                if count < 10: continue 
                
                # Игнорируем совсем мусорные ключи
                if 'unknown' in p_key.lower() or 'misc' in p_key.lower(): continue

                if not exists("PRODUCT", p_key):
                    # Проверка на дубликаты заголовков здесь не нужна, 
                    # если мы доверяем уникальности p_key из RawData.
                    # RawData уже должен был слить "gpu_msi_3060" и "gpu_asus_3060" в один продукт,
                    # ЕСЛИ мы это настроили в парсере. Если нет - память будет иметь два чанка.
                    # Но мы можем попробовать очистить имя от бренда для заголовка.
                    
                    clean_title = display_name
                    # (Опционально) Можно убрать бренд из заголовка, если он там есть, 
                    # чтобы подчеркнуть, что чанк про модель, а не про вендора.
                    
                    candidates.append({
                        "type": "PRODUCT",
                        "key": p_key,
                        "title": f"Слепок: {clean_title}",
                        "parent_key": category_name # Ссылка на категорию
                    })

            # 3. DATABASE (Тематические срезы)
            # Вместо одной 'general', делаем срезы по префиксам категорий или просто уникальные БД
            # Логика: Создаем DATABASE для каждой уникальной категории верхнего уровня (если их много)
            # Для упрощения пока создадим 3 базовых среза, если есть данные:
            
            # A. Глобальная (всегда нужна как корень)
            if not exists("DATABASE", "global"):
                candidates.append({"type": "DATABASE", "key": "global", "title": "Глобальная аналитика рынка", "parent_key": None})

            # B. Тематические (если есть категории)
            # Пробегаем по категориям и создаем для них "Папки" баз данных, если категорий много
            # Например: DATABASE: GPU_MARKET
            # Пока оставим простую реализацию - одна глобальная БД, чтобы не усложнять граф.
            # Но если пользователь захочет - можно раскомментировать логику ниже.
            
            """
            top_level_cats = set()
            for c in categories:
                # Предполагаем, что имя категории это что-то вроде GPU, LAPTOP
                top_level_cats.add(c.get('name'))
            
            for tlc in top_level_cats:
                db_key = f"db_{tlc.lower()}"
                if not exists("DATABASE", db_key):
                     candidates.append({"type": "DATABASE", "key": db_key, "title": f"База данных: {tlc}", "parent_key": "global"})
            """

            # 4. AI_BEHAVIOR
            if not exists("AI_BEHAVIOR", "self_correction"):
                candidates.append({
                    "type": "AI_BEHAVIOR", 
                    "key": "self_correction", 
                    "title": "Модуль самокоррекции (Behavior)", 
                    "parent_key": "global"
                })

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det", exc_info=True)

        return candidates

    @staticmethod
    def create_missing_chunks(memory_manager, cultivation_manager):
        # Метод остается прежним, он просто вызывает detect_candidates и сохраняет в БД
        # ... (код копировать из предыдущего ответа не буду, он идентичен) ...
        # Главное - порядок сортировки: DATABASE -> CATEGORY -> PRODUCT -> AI_BEHAVIOR
        
        candidates = SmartChunkDetector.detect_candidates(memory_manager)
        if not candidates: return 0
        
        # Порядок создания важен для parent_id
        order = {"DATABASE": 0, "CATEGORY": 1, "PRODUCT": 2, "AI_BEHAVIOR": 3}
        candidates.sort(key=lambda x: order.get(x['type'], 99))
        
        created_count = 0
        for c in candidates:
            # Ищем родителя
            parent_id = None
            if c.get('parent_key'):
                # Ищем среди всех типов, так как иерархия теперь сложнее
                # Сначала ищем в CATEGORY, потом в DATABASE
                p_chunk = memory_manager.knowledge.get_chunk_by_key_and_type(c['parent_key'], "CATEGORY")
                if not p_chunk:
                    p_chunk = memory_manager.knowledge.get_chunk_by_key_and_type(c['parent_key'], "DATABASE")
                
                if p_chunk:
                    parent_id = p_chunk['id']

            try:
                # Double check existence
                if memory_manager.knowledge.get_chunk_by_key_and_type(c['key'], c['type']):
                    continue

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
            except Exception as e:
                logger.error(f"Create chunk error: {e}")
        
        return created_count