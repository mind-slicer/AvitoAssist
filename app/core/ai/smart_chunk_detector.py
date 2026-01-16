import re
from typing import List, Dict
from app.core.log_manager import logger

class SmartChunkDetector:

    @staticmethod
    def detect_candidates(memory_manager) -> List[Dict]:
        """
        Детектирует кандидатов для создания чанков.

        ЛОГИКА:
        1. DATABASE чанки создаются для TOP-5 категорий по объёму
        2. CATEGORY чанки создаются для всех категорий (даже если мало данных)
        3. PRODUCT чанки создаются ТОЛЬКО если >=10 товаров в продукте
        4. AI_BEHAVIOR чанк создается всегда (если его нет)

        ВАЖНО: Не линкуем Products на Clusters (бренды)!
        Products независимы, CATEGORY их группирует по семантике.
        """
        candidates = []

        try:
            # 1. DATABASE CANDIDATES (TOP-5 категорий)
            categories = memory_manager.raw_data.get_all_categories()
            top_categories = sorted(categories, key=lambda x: x.get('item_count', 0), reverse=True)[:5]

            for cat in top_categories:
                cat_name = cat.get('name', 'UNKNOWN')
                item_count = cat.get('item_count', 0)

                # Создаем DATABASE чанк для каждой топ-категории
                db_key = f"db_{cat_name.lower()}"

                candidates.append({
                    'type': 'DATABASE',
                    'key': db_key,
                    'title': f'База: {cat_name}',
                    'parent_key': None,  # DATABASE не имеет родителей
                    'item_count': item_count,
                    'priority': 100
                })

            # 2. CATEGORY CANDIDATES (все категории, даже если пусто)
            for cat in categories:
                cat_key = cat.get('name', 'UNKNOWN').strip()
                if not cat_key or cat_key == 'UNKNOWN':
                    continue
                
                item_count = cat.get('item_count', 0)

                # Определяем родительскую DATABASE
                # (берем первую TOP-5, к которой принадлежит эта категория)
                parent_db_key = f"db_{cat_key.lower().split('_')[0]}"

                candidates.append({
                    'type': 'CATEGORY',
                    'key': cat_key,
                    'title': cat.get('display_name', cat_key),
                    'parent_key': parent_db_key,  # Родитель - DATABASE
                    'item_count': item_count,
                    'priority': 50
                })

            # 3. PRODUCT CANDIDATES (ТОЛЬКО если >=10 товаров)
            products = memory_manager.raw_data.get_all_product_keys()

            for prod in products:
                p_key = prod.get('key')
                item_count = prod.get('item_count', 0)

                # КРИТИЧЕСКИЙ ФИЛЬТР: создаем PRODUCT чанк ТОЛЬКО если >=10 товаров
                if item_count < 10:
                    logger.dev(
                        f"PRODUCT '{p_key}' имеет {item_count} товаров (требуется >=10). Пропускаем.",
                        level="DEBUG"
                    )
                    continue
                
                display_name = prod.get('display_name') or p_key
                
                # Очищаем название от бренда (если есть)
                brand = prod.get('brand', '').upper()
                if brand:
                    pattern = re.compile(re.escape(brand), re.IGNORECASE)
                    clean_title = pattern.sub("", display_name).strip()
                    clean_title = clean_title.strip("()[]- ")
                    if not clean_title:
                        clean_title = p_key
                else:
                    clean_title = display_name

                # Определяем родительскую CATEGORY
                # Берем категорию из продукта
                category_name = prod.get('category_name', 'UNKNOWN')

                # Если категория не найдена, пытаемся определить из названия
                if not category_name or category_name == 'UNKNOWN':
                    # Берем первое слово из ключа продукта как категорию
                    parts = p_key.split('_')
                    category_name = parts[0] if parts else 'UNKNOWN'

                candidates.append({
                    'type': 'PRODUCT',
                    'key': p_key,
                    'title': clean_title,
                    'parent_key': category_name,  # Родитель - CATEGORY
                    'item_count': item_count,
                    'priority': 30
                })

            # 4. AI_BEHAVIOR CANDIDATE (всегда создаем)
            candidates.append({
                'type': 'AI_BEHAVIOR',
                'key': 'general_behavior',
                'title': 'Поведение ИИ (Self-Correction)',
                'parent_key': 'db_general',  # Родитель - DATABASE
                'item_count': 0,
                'priority': 200
            })

            # 5. Сортируем по приоритету
            candidates.sort(key=lambda x: x['priority'], reverse=True)

            return candidates

        except Exception as e:
            logger.error(f"Ошибка при детектировании кандидатов: {e}")
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