from typing import List, Dict
from app.core.log_manager import logger

class SmartChunkDetector:

    @staticmethod
    def detect_candidates(memory_manager) -> List[Dict]:
        candidates = []
        try:
            products = memory_manager.raw_data.get_all_product_keys()
            categories = memory_manager.raw_data.get_all_categories()
            
            # Кэш существующих (Type, Key)
            existing_keys = set()
            all_kn = memory_manager.knowledge.get_knowledge(limit=10000)
            for k in all_kn:
                existing_keys.add((k['chunk_type'], k['chunk_key'].lower().strip()))

            def exists(ctype, ckey):
                return (ctype, ckey.lower().strip()) in existing_keys

            # 1. CATEGORY (Обязательно создаем, если есть хоть 1 товар)
            for cat in categories:
                c_key = cat.get('name', 'UNKNOWN')
                count = cat.get('item_count', 0)
                
                if count >= 1 and not exists("CATEGORY", c_key):
                    # Привязываем к тематической БД
                    db_parent = f"db_{c_key.split('_')[0].lower()}" 
                    candidates.append({
                        "type": "CATEGORY",
                        "key": c_key,
                        "title": f"Обзор категории: {c_key}",
                        "parent_key": db_parent
                    })
                    # Добавляем в existing, чтобы продукты могли ссылаться
                    existing_keys.add(("CATEGORY", c_key.lower().strip()))

            # 2. PRODUCT (Порог 10+)
            for prod in products:
                p_key = prod.get('key')
                count = prod.get('item_count', 0)
                
                # --- ЛОГИКА ОЧИСТКИ ЗАГОЛОВКА ---
                display_name = prod.get('display_name') or p_key
                brand = prod.get('brand', '').upper()
                
                # Убираем бренд из названия (ОБЯЗАТЕЛЬНО)
                if brand and brand in display_name.upper():
                    # Case insensitive replace
                    import re
                    pattern = re.compile(re.escape(brand), re.IGNORECASE)
                    clean_title = pattern.sub("", display_name).strip()
                    # Убираем лишние скобки/пробелы
                    clean_title = clean_title.strip("()[]- ")
                else:
                    clean_title = display_name

                # Если после очистки пусто - возвращаем ключ
                if len(clean_title) < 2: 
                    clean_title = p_key

                category_name = prod.get('category_name')

                if count < 10: continue 
                if 'unknown' in p_key.lower() or 'misc' in p_key.lower(): continue

                if not exists("PRODUCT", p_key):
                    candidates.append({
                        "type": "PRODUCT",
                        "key": p_key,
                        "title": f"Слепок: {clean_title}",
                        "parent_key": category_name 
                    })

            # 3. DATABASE (Тематические срезы - РАЗБЛОКИРОВАНО)
            top_level_cats = set()
            for c in categories:
                # Берем первое слово из категории (GPU из GPU_NVIDIA)
                parts = c.get('name', '').split('_')
                if parts: top_level_cats.add(parts[0].upper())
            
            for tlc in top_level_cats:
                db_key = f"db_{tlc.lower()}"
                if not exists("DATABASE", db_key):
                     candidates.append({
                         "type": "DATABASE", 
                         "key": db_key, 
                         "title": f"База данных: {tlc}", 
                         "parent_key": "global"
                     })

            # Глобальная БД (Root)
            if not exists("DATABASE", "global"):
                candidates.append({"type": "DATABASE", "key": "global", "title": "Глобальная аналитика", "parent_key": None})

            # 4. AI_BEHAVIOR (Только если есть действия!)
            actions = memory_manager.raw_data.get_recent_actions(limit=5)
            if actions and not exists("AI_BEHAVIOR", "self_correction"):
                candidates.append({
                    "type": "AI_BEHAVIOR", 
                    "key": "self_correction", 
                    "title": "Модуль самокоррекции", 
                    "parent_key": "global"
                })

        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det", exc_info=True)

        return candidates

    @staticmethod
    def create_missing_chunks(memory_manager, cultivation_manager):
        candidates = SmartChunkDetector.detect_candidates(memory_manager)
        if not candidates: return 0
        
        # Сортировка: DATABASE -> CATEGORY -> PRODUCT -> AI_BEHAVIOR
        order = {"DATABASE": 0, "CATEGORY": 1, "PRODUCT": 2, "AI_BEHAVIOR": 3}
        candidates.sort(key=lambda x: order.get(x['type'], 99))
        
        created_count = 0
        for c in candidates:
            # Ищем родителя (сначала в БД, потом в памяти созданных)
            parent_id = None
            if c.get('parent_key'):
                # Сначала ищем среди DATABASE
                p_chunk = memory_manager.knowledge.get_chunk_by_key_and_type(c['parent_key'], "DATABASE")
                # Потом среди CATEGORY
                if not p_chunk:
                    p_chunk = memory_manager.knowledge.get_chunk_by_key_and_type(c['parent_key'], "CATEGORY")
                
                if p_chunk:
                    parent_id = p_chunk['id']

            try:
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