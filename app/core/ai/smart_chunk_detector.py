import re
from typing import List, Dict
from app.core.log_manager import logger

class SmartChunkDetector:

    @staticmethod
    def detect_candidates(memory_manager, threshold: int = 10) -> List[Dict]:
        """
        Сканирует БД и предлагает кандидатов для создания чанков.
        threshold: минимальное количество товаров для создания PRODUCT чанка.
        """
        candidates = []
        try:
            # 1. DATABASE (Всегда проверяем топ категорий)
            categories = memory_manager.raw_data.get_all_categories()
            top_categories = sorted(categories, key=lambda x: x.get('item_count', 0), reverse=True)[:5]

            for cat in top_categories:
                cat_name = cat.get('name', 'UNKNOWN')
                # DB чанк создаем, если есть хоть что-то
                if cat.get('item_count', 0) > 0:
                    candidates.append({
                        'type': 'DATABASE',
                        'key': f"db_{cat_name.lower()}",
                        'title': f'База: {cat_name}',
                        'parent_key': None,
                        'item_count': cat.get('item_count', 0),
                        'priority': 100
                    })

            # 2. CATEGORY
            for cat in categories:
                cat_key = cat.get('name', 'UNKNOWN').strip()
                item_count = cat.get('item_count', 0)
                
                # Категорию создаем, если в ней есть товары (даже меньше порога, т.к. это агрегатор)
                if item_count > 0:
                    candidates.append({
                        'type': 'CATEGORY',
                        'key': cat_key,
                        'title': cat.get('display_name', cat_key),
                        'parent_key': f"db_{cat_key.lower().split('_')[0]}",
                        'item_count': item_count,
                        'priority': 50
                    })

            # 3. PRODUCT (Здесь применяем threshold)
            products = memory_manager.raw_data.get_all_product_keys()
            for prod in products:
                p_key = prod.get('key')
                item_count = prod.get('item_count', 0)

                if item_count < threshold:
                    # Слишком мало данных для отдельного чанка
                    continue

                display_name = prod.get('display_name') or p_key
                category_name = prod.get('category_name') or p_key.split('_')[0]

                candidates.append({
                    'type': 'PRODUCT',
                    'key': p_key,
                    'title': display_name,
                    'parent_key': category_name, # Родитель - Категория
                    'item_count': item_count,
                    'priority': 30
                })

            # 4. AI_BEHAVIOR
            candidates.append({
                'type': 'AI_BEHAVIOR',
                'key': 'general_behavior',
                'title': 'Поведение ИИ',
                'parent_key': 'db_general',
                'item_count': 0,
                'priority': 200
            })

            candidates.sort(key=lambda x: x['priority'], reverse=True)
            return candidates

        except Exception as e:
            logger.error(f"Detector error: {e}")
            return []

    @staticmethod
    def create_missing_chunks(memory_manager, cultivation_manager) -> int:
        """
        Создает недостающие чанки на основе детектированных кандидатов.
        
        ВАЖНО:
        - Сначала создаем DATABASE
        - Потом CATEGORY (с parent_chunk_id на DATABASE)
        - Потом PRODUCT (с parent_chunk_id на CATEGORY)
        - Потом AI_BEHAVIOR
        
        Порядок важен для правильной иерархии!
        """
        candidates = SmartChunkDetector.detect_candidates(memory_manager)
        
        if not candidates:
            logger.info("Новых кандидатов не найдено.", token="ai-det")
            return 0
        
        # Сортируем по типу для правильного порядка создания
        type_order = {"DATABASE": 0, "CATEGORY": 1, "PRODUCT": 2, "AI_BEHAVIOR": 3}
        candidates.sort(key=lambda x: type_order.get(x['type'], 999))
        
        created_count = 0
        
        # Словарь для отслеживания созданных чанков (ключ -> ID)
        created_chunks = {}
        
        # Словарь для отслеживания существующих чанков
        existing_chunks = {}
        all_existing = memory_manager.knowledge.get_knowledge(limit=10000)
        for chunk in all_existing:
            key = (chunk['chunk_type'], chunk['chunk_key'])
            existing_chunks[key] = chunk['id']
        
        for candidate in candidates:
            c_type = candidate['type']
            c_key = candidate['key'].strip()
            c_title = candidate['title']
            parent_key = candidate.get('parent_key')
            
            # Проверяем, не существует ли уже такой чанк
            if (c_type, c_key) in existing_chunks:
                logger.dev(f"Чанк [{c_type}] {c_key} уже существует. Пропускаем.", level="DEBUG")
                created_chunks[(c_type, c_key)] = existing_chunks[(c_type, c_key)]
                continue
            
            # Определяем parent_chunk_id
            parent_id = None
            
            if parent_key:
                # Для DATABASE: parent_key всегда None
                # Для CATEGORY: parent_key - это DATABASE ключ (например, "db_gpu")
                # Для PRODUCT: parent_key - это CATEGORY ключ (например, "video_cards")
                # Для AI_BEHAVIOR: parent_key - это DATABASE ключ (например, "db_general")
                
                # Ищем parent чанк либо в только что созданных, либо в БД
                parent_type = "DATABASE" if c_type in ["CATEGORY", "AI_BEHAVIOR"] else "CATEGORY"
                
                if (parent_type, parent_key) in created_chunks:
                    parent_id = created_chunks[(parent_type, parent_key)]
                elif (parent_type, parent_key) in existing_chunks:
                    parent_id = existing_chunks[(parent_type, parent_key)]
                else:
                    # Если родителя нет, логируем предупреждение, но не блокируем создание
                    logger.warning(
                        f"⚠️ Родитель [{parent_type}] {parent_key} не найден для [{c_type}] {c_key}. "
                        f"Создаем без родителя.",
                        token="ai-det"
                    )
            
            # Создаем чанк
            try:
                new_id = memory_manager.add_knowledge(
                    chunk_type=c_type,
                    chunk_key=c_key,
                    title=c_title,
                    status='PENDING',
                    parent_chunk_id=parent_id,  # ВАЖНО: передаём parent_id
                    priority=candidate.get('priority', 1)
                )
                
                # Сохраняем в словарь созданных
                created_chunks[(c_type, c_key)] = new_id
                
                # Отправляем сигнал в UI
                if cultivation_manager:
                    cultivation_manager.chunk_status_changed.emit(new_id, 'PENDING')
                
                logger.success(f"✅ Создан чанк [{new_id}] {c_type} : {c_key}", token="ai-det")
                created_count += 1
            
            except Exception as e:
                logger.error(f"❌ Ошибка создания чанка [{c_type}] {c_key}: {e}", token="ai-det")
                continue
            
        if created_count > 0:
            logger.success(
                f"🎯 Структура знаний обновлена: создано {created_count} новых узлов.",
                token="ai-det"
            )
        else:
            logger.info("Все кандидаты уже существуют в базе знаний.", token="ai-det")
        
        return created_count