import re
from typing import List, Dict
from app.core.log_manager import logger

class SmartChunkDetector:

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Приводит ключ к единому формату: lowercase, без пробелов."""
        if not key: return ""
        return key.strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def detect_candidates(memory_manager, threshold: int = 10) -> List[Dict]:
        candidates = []
        try:
            # 1. DATABASE (100)
            categories = memory_manager.raw_data.get_all_categories()
            top_categories = sorted(categories, key=lambda x: x.get('item_count', 0), reverse=True)[:5]
            for cat in top_categories:
                cat_name = cat.get('name', 'UNKNOWN')
                if cat.get('item_count', 0) > 0:
                    candidates.append({
                        'type': 'DATABASE',
                        'key': f"db_{SmartChunkDetector._normalize_key(cat_name)}",
                        'title': f'База: {cat_name}',
                        'parent_key': None,
                        'priority': 100
                    })

            # 2. CATEGORY (50)
            for cat in categories:
                cat_name = cat.get('name', 'UNKNOWN')
                cat_key = SmartChunkDetector._normalize_key(cat_name)
                item_count = cat.get('item_count', 0)
                if item_count > 0:
                    candidates.append({
                        'type': 'CATEGORY',
                        'key': cat_key,
                        'title': cat.get('display_name', cat_name),
                        'parent_key': f"db_{cat_key.split('_')[0]}",
                        'priority': 50
                    })

            # 3. PRODUCT (30)
            products = memory_manager.raw_data.get_all_product_keys()
            for prod in products:
                raw_key = prod.get('key')
                item_count = prod.get('item_count', 0)
                if item_count < threshold: continue

                display_name = prod.get('display_name') or raw_key
                category_name = prod.get('category_name') or raw_key.split('_')[0]
                p_key = SmartChunkDetector._normalize_key(raw_key)

                candidates.append({
                    'type': 'PRODUCT',
                    'key': p_key,
                    'title': display_name,
                    'parent_key': SmartChunkDetector._normalize_key(category_name),
                    'priority': 30
                })

            # 4. AI_BEHAVIOR (200)
            candidates.append({
                'type': 'AI_BEHAVIOR',
                'key': 'general_behavior',
                'title': 'Поведение ИИ',
                'parent_key': 'db_general',
                'priority': 200
            })

            candidates.sort(key=lambda x: x['priority'], reverse=True)
            return candidates

        except Exception as e:
            logger.error(f"Detector error: {e}")
            return []

    @staticmethod
    def create_missing_chunks(memory_manager, cultivation_manager) -> int:
        candidates = SmartChunkDetector.detect_candidates(memory_manager)
        if not candidates: return 0
        
        type_order = {"DATABASE": 0, "CATEGORY": 1, "PRODUCT": 2, "AI_BEHAVIOR": 3}
        candidates.sort(key=lambda x: type_order.get(x['type'], 999))
        
        created_count = 0
        
        # Загружаем существующие для проверки
        existing_chunks = {} 
        all_existing = memory_manager.knowledge.get_knowledge(limit=10000)
        for chunk in all_existing:
            key = (chunk['chunk_type'], SmartChunkDetector._normalize_key(chunk['chunk_key']))
            existing_chunks[key] = chunk['id']
        
        newly_created = {}

        for candidate in candidates:
            c_type = candidate['type']
            norm_key = SmartChunkDetector._normalize_key(candidate['key'])
            c_title = candidate['title'].strip()
            priority = candidate.get('priority', 1)
            
            # --- FIX: Если чанк существует, ОБНОВЛЯЕМ ПРИОРИТЕТ ---
            if (c_type, norm_key) in existing_chunks:
                chunk_id = existing_chunks[(c_type, norm_key)]
                # Принудительное обновление приоритета в БД
                try:
                    conn = memory_manager.knowledge._get_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE ai_knowledge SET priority = ? WHERE id = ?", (priority, chunk_id))
                    conn.commit()
                    conn.close()
                except: pass
                
                newly_created[(c_type, norm_key)] = chunk_id
                continue

            # Определяем родителя
            parent_id = None
            parent_key_raw = candidate.get('parent_key')
            if parent_key_raw:
                parent_key_norm = SmartChunkDetector._normalize_key(parent_key_raw)
                parent_type = "DATABASE" if c_type in ["CATEGORY", "AI_BEHAVIOR"] else "CATEGORY"
                
                if (parent_type, parent_key_norm) in newly_created:
                    parent_id = newly_created[(parent_type, parent_key_norm)]
                elif (parent_type, parent_key_norm) in existing_chunks:
                    parent_id = existing_chunks[(parent_type, parent_key_norm)]
            
            try:
                new_id = memory_manager.add_knowledge(
                    chunk_type=c_type,
                    chunk_key=norm_key,
                    title=c_title,
                    status='PENDING',
                    parent_chunk_id=parent_id,
                    priority=priority # <-- Передаем приоритет при создании
                )
                newly_created[(c_type, norm_key)] = new_id
                
                if cultivation_manager:
                    cultivation_manager.chunk_status_changed.emit(new_id, 'PENDING')
                
                logger.success(f"✅ Создан чанк [{new_id}] {c_type} (P:{priority})", token="ai-det")
                created_count += 1
            except Exception as e:
                logger.error(f"Create error {c_title}: {e}")
        
        return created_count