import os
import threading
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.text_utils import FeatureExtractor
from app.core.memory.raw_data_manager import RawDataManager
from app.core.memory.knowledge_manager import KnowledgeManager
from app.core.diagnostic_logger import get_diagnostic_logger
from app.core.log_manager import logger
from app.config import BASE_APP_DIR


class MemoryManager:
    def __init__(self):
        self.raw_data = RawDataManager()
        self.knowledge = KnowledgeManager()
        self.raw_data.cleanup_old_actions(keep_last=500)
        self._processing_lock = threading.Lock()
        logger.success("MemoryManager initialized with persistent storage")

    def add_items_bulk(self, items: List[Dict]) -> int:
        if not items:
            return 0

        diag = get_diagnostic_logger()
        FeatureExtractor.extract_semantic_data("")

        import time
        timeout = 30
        start = time.time()
        while not FeatureExtractor.is_model_ready():
            if time.time() - start > timeout:
                logger.error("NLP модель не загрузилась за 30 секунд!")
                return 0
            time.sleep(0.1)

        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Обработка батчами по 500 элементов
        BATCH_SIZE = 500
        total_added = 0
        
        for batch_start in range(0, len(items), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(items))
            batch = items[batch_start:batch_end]
            
            logger.info(f"Обработка батча {batch_start+1}-{batch_end} из {len(items)}")
            
            prepared_data = []
            import os
            max_workers = min(4, os.cpu_count() or 1, len(batch))
            
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    def get_price_safe(itm):
                        try:
                            p = itm.get('price')
                            return int(p) if p is not None else 0
                        except (ValueError, TypeError):
                            return 0

                    future_to_item = {
                        executor.submit(
                            FeatureExtractor.extract_semantic_data_with_debug,
                            item.get('title', ''),
                            item.get('description', ''),
                            get_price_safe(item)
                        ): item
                        for item in batch
                    }

                    failed_count = 0
                    for future in as_completed(future_to_item):
                        original_item = future_to_item[future]
                        try:
                            semantic_data, debug_data = future.result()
                            
                            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Валидация перед добавлением
                            if not self._validate_semantic_data(semantic_data, original_item.get('title', '')):
                                # Retry NLP один раз
                                logger.info(f"Retry NLP для: '{original_item.get('title', '')[:50]}'")
                                try:
                                    semantic_data, debug_data = FeatureExtractor.extract_semantic_data_with_debug(
                                        original_item.get('title', ''),
                                        original_item.get('description', ''),
                                        get_price_safe(original_item)
                                    )
                                    if not self._validate_semantic_data(semantic_data, original_item.get('title', '')):
                                        logger.error(f"Retry не помог для: '{original_item.get('title', '')[:30]}'")
                                        failed_count += 1
                                        continue
                                except Exception as retry_e:
                                    logger.error(f"Retry NLP failed: {retry_e}")
                                    failed_count += 1
                                    continue
                            
                            item_for_db = original_item.copy()
                            item_for_db['semantic_data'] = semantic_data
                            prepared_data.append({'item': item_for_db})

                            if diag.enabled:
                                diag.log_item_processing(
                                    original_item=original_item,
                                    semantic_data=semantic_data,
                                    intermediate_data=debug_data
                                )
                        except Exception as e:
                            logger.error(f"NLP error for item '{original_item.get('title', '')[:50]}': {e}")
                            failed_count += 1
                            # НЕ добавляем fallback - пропускаем элемент

                    # Предупреждение, если много ошибок
                    if failed_count > len(batch) * 0.3:  # Более 30% ошибок
                        logger.error(f"КРИТИЧЕСКАЯ СИТУАЦИЯ: {failed_count}/{len(batch)} элементов упали с ошибкой NLP!")
                        
            except Exception as e:
                logger.error(f"Parallel NLP failed для батча: {e}", exc_info=True)
                continue

            if prepared_data:
                count = self.raw_data.add_raw_items_bulk(prepared_data)
                total_added += count
                logger.success(f"Батч {batch_start+1}-{batch_end}: добавлено {count} элементов")
                
                if diag.enabled:
                    diag.save_session()

        logger.success(f"Всего добавлено: {total_added}/{len(items)} элементов")
        return total_added

    def add_item(self, item: Dict) -> bool:
        diag = get_diagnostic_logger()
        original_item = item.copy()
    
        price_safe = 0
        try:
            p = item.get('price')
            if p is not None:
                price_safe = int(p)
        except (ValueError, TypeError):
            pass
        
        # Выполняем семантический анализ с retry
        max_retries = 2
        semantic_data = None
        debug_data = None
    
        for attempt in range(max_retries):
            try:
                semantic_data, debug_data = FeatureExtractor.extract_semantic_data_with_debug(
                    item.get('title', ''),
                    item.get('description', ''),
                    price_safe
                )
    
                if self._validate_semantic_data(semantic_data, item.get('title', '')):
                    break
                else:
                    if attempt < max_retries - 1:
                        logger.warning(f"Попытка {attempt+1}/{max_retries} не прошла валидацию")
                    else:
                        logger.error(f"Не удалось получить валидный semantic_data для: '{item.get('title', '')[:50]}'")
                        return False
            except Exception as e:
                logger.error(f"NLP error (attempt {attempt+1}): {e}")
                if attempt == max_retries - 1:
                    return False
    
        item_for_db = item.copy()
        item_for_db['semantic_data'] = semantic_data
    
        if diag.enabled:
            diag.log_item_processing(
                original_item=original_item,
                semantic_data=semantic_data,
                intermediate_data=debug_data,
                db_result={'status': 'processing'}
            )
    
        result = self.raw_data.add_raw_item(item_for_db)
    
        if diag.enabled:
            diag.log_item_processing(
                original_item=original_item,
                semantic_data=semantic_data,
                intermediate_data=debug_data,
                db_result={'status': str(result), 'item_id': result.item_id, 'product_id': semantic_data.get('product_key')}
            )
            diag.save_session()
    
        # ИСПОЛЬЗУЕМ УЖЕ ПОЛУЧЕННЫЕ semantic_data (БЕЗ повторного вызова)
        product_key = semantic_data.get('product_key')
        cluster_key = semantic_data.get('cluster_key')
    
        # Инкремент для PRODUCT чанка
        if product_key:
            chunk = self.knowledge.get_chunk_by_key_and_type(product_key, 'PRODUCT')
            if chunk and chunk.get('status') in ['READY', 'ACCUMULATING']:
                self.knowledge.increment_data_count(chunk['id'], count=1)
                logger.dev(f"📈 PRODUCT чанк {chunk['id']} ({product_key}): +1 новый item", level="DEBUG")
    
            # Проверка hash-based ключей
            if '_unknown_' in product_key:
                item_title = item.get('title', '')
                logger.info(
                    f"Элемент '{item_title[:50]}' использует hash-based product_key: '{product_key}' "
                    f"(это нормально для неопознанных товаров)"
                )
    
        return True

    def get_raw_items(self, category: Optional[str] = None,
                      product_key: Optional[str] = None,
                      search_query: Optional[str] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[Dict]:
        """Get raw items with filtering."""
        return self.raw_data.get_raw_items(category, product_key, search_query, limit, offset)

    def get_raw_items_count(self, category: Optional[str] = None,
                            product_key: Optional[str] = None) -> int:
        """Get count of raw items."""
        return self.raw_data.get_raw_items_count(category, product_key)

    def get_raw_item_by_id(self, item_id: int) -> Optional[Dict]:
        """Get single raw item by id."""
        return self.raw_data.get_raw_item_by_id(item_id)

    def delete_raw_items(self, item_ids: List[int]) -> int:
        """Delete items by ids."""
        return self.raw_data.delete_raw_items(item_ids)

    def clear_all_raw_items(self) -> int:
        """Clear all raw items."""
        return self.raw_data.clear_all_raw_items()

    def get_items_for_product_key(self, product_key: str) -> List[Dict]:
        """Get all items for a product key."""
        return self.raw_data.get_items_for_product_key(product_key)

    def get_all_categories(self) -> List[Dict]:
        """Get all categories."""
        return self.raw_data.get_all_categories()

    def get_or_create_category(self, name: str) -> int:
        """Get or create category."""
        return self.raw_data.get_or_create_category(name)

    def get_all_product_keys(self, category_id: Optional[int] = None) -> List[Dict]:
        """Get all product keys."""
        return self.raw_data.get_all_product_keys(category_id)

    def get_or_create_product_key(self, key: str, display_name: Optional[str] = None,
                                   category_id: Optional[int] = None) -> int:
        """Get or create product key."""
        return self.raw_data.get_or_create_product_key(key, display_name, category_id)

    def get_raw_data_statistics(self) -> Dict:
        """Get raw data statistics."""
        return self.raw_data.get_statistics()

    def _validate_semantic_data(self, semantic_data: Dict, item_title: str) -> bool:
        """
        РАСШИРЕННАЯ ВАЛИДАЦИЯ для ФАЗЫ 1.
        Проверяет не только обязательные поля, но и качество данных.

        КЛЮЧЕВЫЕ ПРОВЕРКИ:
        1. Product Key не должен быть пустым или одна категория
        2. Product Key не должен заканчиваться на подчёркивание
        3. MISC категория только для неуверенных случаев
        4. Критические категории должны иметь либо бренд, либо модель
        5. Clean Name не должен быть generic
        6. ACCESSORY может быть без бренда/модели, но не без clean_name
        7. Product Key должен быть достаточно информативным (min 5 символов)
        """

        if not semantic_data:
            logger.warning(f"Пустой semantic_data для элемента: '{item_title[:50]}'")
            return False

        required_fields = ['category', 'product_key', 'entity_type', 'clean_name']
        for field in required_fields:
            if field not in semantic_data or not semantic_data[field]:
                logger.warning(f"Отсутствует поле '{field}' в semantic_data для: '{item_title[:50]}'")
                return False

        category = semantic_data.get('category', '')
        product_key = semantic_data.get('product_key', '')
        model = semantic_data.get('model', '') or semantic_data.get('features', {}).get('model', '')
        brand = semantic_data.get('brand', '')
        clean_name = semantic_data.get('clean_name', '')

        # ✅ НОВОЕ: Проверка 1 - Product Key не должен быть пустой или одна категория
        if not product_key or product_key == category.lower():
            logger.warning(
                f"Элемент '{item_title[:50]}' имеет невалидный product_key: '{product_key}' "
                f"(равен категории или пуст)"
            )
            return False

        # ✅ НОВОЕ: Проверка 2 - Product Key не должен заканчиваться на подчёркивание
        if product_key.endswith('_') or product_key.startswith('_'):
            logger.warning(
                f"Элемент '{item_title[:50]}' имеет некорректный product_key: '{product_key}' "
                f"(starts/ends with _)"
            )
            return False

        # ✅ НОВОЕ: Проверка 3 - MISC категория только для неуверенных случаев
        if category == 'MISC' and product_key == 'misc_unknown':
            # Если это явно не MISC по заголовку - это ошибка
            if len(item_title) > 15 and not any(
                word in item_title.lower() for word in ['прочее', 'разное', 'другое', 'misc']
            ):
                logger.warning(
                    f"Элемент '{item_title[:50]}' неправильно категоризирован как MISC_UNKNOWN"
                )
                return False

        # ✅ НОВОЕ: Проверка 4 - Критические категории должны иметь либо бренд, либо модель
        critical_categories = ['GPU', 'CPU', 'LAPTOP', 'MOTHERBOARD', 'RAM', 'STORAGE', 'PSU']
        if category in critical_categories:
            # Исключение для Ретро-GPU (они часто без бренда, просто модель чипа)
            is_retro = any(x in clean_name.lower() for x in ['agp', 'pci', 'isa', 's3', 'trident', 'sis'])
            
            if not model and not brand and not is_retro:
                logger.warning(
                    f"Элемент '{item_title[:50]}' (категория {category}) без бренда И модели. "
                    f"БЛОКИРОВАН."
                )
                return False

            # ✅ НОВОЕ: Убедимся, что clean_name не просто категория
            if clean_name == category or clean_name == f"{category} (Unknown Model)":
                logger.warning(
                    f"Элемент '{item_title[:50]}' имеет generic clean_name: '{clean_name}' "
                    f"(категория = {category})"
                )
                return False
            
        if category in ['GPU', 'CPU', 'RAM', 'STORAGE', 'MOTHERBOARD', 'PSU']:
            # Если в заголовке есть и процессор, и видеокарта — это не может быть просто "диском" или "памятью"
            has_cpu_cues = any(x in item_title.lower() for x in ['ryzen', 'core i', 'i3-', 'i5-', 'i7-', 'i9-'])
            has_gpu_cues = any(x in item_title.lower() for x in ['rtx', 'gtx', 'rx ', 'geforce', 'radeon'])
            
            # Если найдены оба признака в "мелком" компоненте (например, STORAGE)
            if category in ['STORAGE', 'RAM', 'PSU'] and (has_cpu_cues or has_gpu_cues):
                logger.warning(f"Элемент '{item_title[:50]}' помечен как {category}, но содержит CPU/GPU. БЛОКИРОВАН.")
                return False

        # ✅ НОВОЕ: Проверка 5 - ACCESSORY может быть без бренда/модели, но не без clean_name
        if category == 'ACCESSORY':
            bad_keys = ['accessory_nvidia', 'accessory_amd', 'accessory_asus', 'accessory_msi', 'accessory_gigabyte']
            if product_key in bad_keys:
                # Пытаемся уточнить ключ, если clean_name содержит больше инфо
                if len(clean_name) > 10:
                     # Разрешаем, но логируем
                     pass
                else:
                     # Слишком мусорный элемент (просто "кабель nvidia")
                     logger.info(f"Skipping generic accessory: {product_key}")
                     return False
            
            if clean_name.startswith('ACCESSORY (') and 'UNKNOWN' in clean_name.upper():
                logger.warning(
                    f"Элемент '{item_title[:50]}' (ACCESSORY) имеет невалидный clean_name: "
                    f"'{clean_name}'"
                )
                return False

        # ✅ НОВОЕ: Проверка 6 - Product Key должен быть достаточно информативным (min 5 символов)
        if len(product_key) < 5:
            # Исключение: accessory_009s, accessory_x16 - это OK (5+ символов)
            # Но accessory_ - это NOT OK
            if category not in ['ACCESSORY', 'SERVICE']:
                logger.warning(
                    f"Элемент '{item_title[:50]}' имеет слишком короткий product_key: "
                    f"'{product_key}' (длина: {len(product_key)})"
                )
                return False
            else:
                # Даже для ACCESSORY/SERVICE, если ключ = "accessory_" - это плохо
                if product_key.endswith('_') or product_key.count('_') == 1:
                    logger.warning(
                        f"Элемент '{item_title[:50]}' (категория {category}) имеет пустой "
                        f"product_key суффикс: '{product_key}'"
                    )
                    return False

        # ✅ НОВОЕ: Проверка 7 - Product Key содержит хешевый суффикс для fallback
        # Если product_key содержит hash (_unknown_xxxxx), это OK, но лучше бы этого не было
        if '_unknown_' in product_key:
            # Допускаем, но логируем как warning для отладки
            logger.info(
                f"Элемент '{item_title[:50]}' использует hash-based product_key: '{product_key}' "
                f"(это нормально для неопознанных товаров)"
            )

        return True

    def add_knowledge(self, chunk_type: str, chunk_key: str, title: str,
                      content: Optional[Dict] = None, status: str = 'PENDING',
                      priority: int = 1, source_hash: str = None, parent_chunk_id: int = None) -> int:
        """Add or update knowledge chunk."""
        return self.knowledge.add_knowledge(chunk_type, chunk_key, title, content, status, priority, source_hash, parent_chunk_id)

    def get_knowledge(self, chunk_id: Optional[int] = None,
                      chunk_key: Optional[str] = None,
                      chunk_type: Optional[str] = None,
                      status: Optional[str] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[Dict]:
        """Get knowledge chunks."""
        return self.knowledge.get_knowledge(chunk_id, chunk_key, chunk_type, status, limit, offset)

    def get_chunk_by_id(self, chunk_id: int) -> Optional[Dict]:
        """Get chunk by id."""
        return self.knowledge.get_chunk_by_id(chunk_id)

    def delete_knowledge(self, chunk_id: int) -> bool:
        """Delete chunk by id."""
        return self.knowledge.delete_knowledge(chunk_id)

    def update_chunk_content(self, chunk_id: int, content: Dict, summary: Optional[str] = None, source_hash: str = None, embedding_blob: bytes = None):
        """Update chunk content."""
        self.knowledge.update_chunk_content(chunk_id, content, summary, source_hash, embedding_blob)

    def update_chunk_status(self, chunk_id: int, status: str, progress: Optional[int] = None):
        """Update chunk status."""
        self.knowledge.update_chunk_status(chunk_id, status, progress)

    def update_chunk_with_retry(self, chunk_id: int, status: str, retry_count: int):
        """Update chunk with retry count."""
        self.knowledge.update_chunk_with_retry(chunk_id, status, retry_count)

    def get_pending_chunks(self) -> List[Dict]:
        """Get pending chunks."""
        return self.knowledge.get_pending_chunks()

    def get_ready_chunks(self) -> List[Dict]:
        """Get ready chunks."""
        return self.knowledge.get_ready_chunks()

    def get_knowledge_status_summary(self) -> Dict:
        """Get knowledge status summary."""
        return self.knowledge.get_status_summary()

    def get_recent_knowledge(self, limit: int = 10) -> List[Dict]:
        """Get recently updated knowledge."""
        return self.knowledge.get_recent_knowledge(limit)

    def get_knowledge_statistics(self) -> Dict:
        """Get knowledge statistics."""
        return self.knowledge.get_statistics()

    def get_rag_context_for_item(self, title: str) -> Optional[Dict]:
        """Get RAG context for item with Graph lookups."""
        # 1. Базовый поиск
        rag = self.knowledge.get_rag_context_for_item(title)
        if not rag:
            return None

        # --- FIX START: Graph RAG (подтягивание компонентов) ---
        # Если мы смотрим ПК (PC_BUILD), попробуем найти внутри CPU и GPU
        knowledge_text = rag.get('knowledge', '')
        
        # Простая эвристика: если это PC_BUILD, ищем упоминания железа в заголовке
        # и пытаемся найти их чанки
        extra_context = []
        lower_title = title.lower()
        
        if 'pc_build' in rag.get('chunk_key', '').lower() or 'системный' in lower_title:
            # Ищем GPU
            gpu_markers = ['rtx', 'gtx', 'rx', '3060', '3070', '4060', '4070', '1660']
            for marker in gpu_markers:
                if marker in lower_title:
                    # Пытаемся найти чанк GPU по маркеру (упрощенно)
                    # В идеале здесь нужен поиск через vector store, но пока через SQL LIKE
                    found_chunks = self.knowledge.get_knowledge(chunk_type='PRODUCT', limit=5)
                    for chunk in found_chunks:
                        if marker in chunk['chunk_key'] and 'gpu' in chunk['chunk_key']:
                             extra_context.append(f"Инфо о карте ({chunk['chunk_key']}): {chunk.get('summary', '')[:100]}...")
                             break
        
        if extra_context:
            rag['knowledge'] = knowledge_text + "\n\n[СВЯЗАННЫЕ КОМПОНЕНТЫ]:\n" + "\n".join(extra_context)
        # --- FIX END ---

        return rag

    def get_rag_status(self) -> Dict:
        """Get RAG status."""
        return self.knowledge.get_rag_status()

    def get_stats(self) -> Dict:
        """Get combined stats."""
        return {
            'total': self.raw_data.get_statistics().get('total_items', 0)
        }

    def find_similar_items(self, chunk_key: str, limit: int = 500) -> List[Dict]:
        """Find similar items (for cultivation prompts)."""
        items = self.raw_data.get_items_for_product_key(product_key=chunk_key)
        if len(items) > limit:
            return items[:limit] 
        return items

    def get_chunk_children(self, parent_chunk_id: int) -> List[Dict]:
        """Получает дочерние чанки"""
        return self.knowledge.get_chunk_children(parent_chunk_id)


    def get_chunk_parent(self, chunk_id: int) -> Optional[Dict]:
        """Получает родительский чанк"""
        return self.knowledge.get_chunk_parent(chunk_id)


    def get_chunks_by_priority(self, limit: int = 10) -> List[Dict]:
        """Получает чанки по приоритету"""
        return self.knowledge.get_chunks_by_priority(limit)


    def get_chunk_by_key_and_type(self, chunk_key: str, chunk_type: str) -> Optional[Dict]:
        """Получает чанк по ключу и типу"""
        return self.knowledge.get_chunk_by_key_and_type(chunk_key, chunk_type)


    def save_chunk_history_snapshot(self, product_key: str, stats: Dict):
        """Сохраняет снепшот истории чанка"""
        self.raw_data.save_history_snapshot(product_key, stats)


    def get_chunk_history(self, product_key: str, limit: int = 10) -> List[Dict]:
        """Получает историю чанка"""
        return self.raw_data.get_chunk_history(product_key, limit)


    def calculate_data_signature(self, product_key: Optional[str] = None, category_name: Optional[str] = None) -> str:
        """Вычисляет сигнатуру данных"""
        return self.raw_data.calculate_data_signature(product_key, category_name)

    def export_all(self, base_dir: str = BASE_APP_DIR):
        """Export all data to JSON files."""
        raw_path = os.path.join(base_dir, "export_raw_data.json")
        knowledge_path = os.path.join(base_dir, "export_knowledge.json")

        self.raw_data.export_to_json(raw_path)
        self.knowledge.export_to_json(knowledge_path)

        return {'raw_data': raw_path, 'knowledge': knowledge_path}

    def import_all(self, raw_path: Optional[str] = None,
                   knowledge_path: Optional[str] = None,
                   clear_first: bool = False):
        """Import all data from JSON files."""
        if raw_path and os.path.exists(raw_path):
            self.raw_data.import_from_json(raw_path, clear_first)
        if knowledge_path and os.path.exists(knowledge_path):
            self.knowledge.import_from_json(knowledge_path, clear_first)

    def reset_all(self):
        """Reset all data."""
        self.raw_data.reset_database()
        self.knowledge.reset_database()
        logger.info("All memory data reset complete")