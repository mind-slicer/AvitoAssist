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
        FeatureExtractor.extract_semantic_data("")

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
                
                # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Валидация
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

        return result.status in ['created', 'updated']

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
        if not semantic_data:
            logger.warning(f"Пустой semantic_data для элемента: '{item_title[:50]}'")
            return False
        
        required_fields = ['category', 'product_key', 'entity_type', 'clean_name']
        for field in required_fields:
            if field not in semantic_data or not semantic_data[field]:
                logger.warning(f"Отсутствует поле '{field}' в semantic_data для: '{item_title[:50]}'")
                return False
        
        # Проверка, что это не fallback-значения
        if semantic_data['category'] == 'MISC' and semantic_data['product_key'] == 'misc_unknown':
            critical_categories = ['GPU', 'CPU', 'LAPTOP', 'MOTHERBOARD', 'RAM']
            if semantic_data['category'] in critical_categories:
                model = semantic_data.get('features', {}).get('model', '') or semantic_data.get('model', '')
                brand = semantic_data.get('brand', '')

                # Если нет ни бренда, ни модели - блокируем
                if not model and not brand:
                    logger.warning(f"Элемент '{item_title[:50]}' категории {semantic_data['category']} без бренда и модели. БЛОКИРОВАН.")
                    return False
        
        if len(semantic_data['product_key']) < 5:  # Например, "gpu_" = 4 символа
            logger.warning(f"Элемент '{item_title[:50]}' имеет слишком короткий product_key: '{semantic_data['product_key']}'")
            return False

        return True

    def add_knowledge(self, chunk_type: str, chunk_key: str, title: str,
                      content: Optional[Dict] = None, status: str = 'PENDING',
                      priority: int = 1, source_hash: str = None) -> int:
        """Add or update knowledge chunk."""
        return self.knowledge.add_knowledge(chunk_type, chunk_key, title, content, status, priority, source_hash)

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

    def update_chunk_content(self, chunk_id: int, content: Dict, summary: Optional[str] = None, source_hash: str = None):
        """Update chunk content."""
        self.knowledge.update_chunk_content(chunk_id, content, summary, source_hash)

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
        """Get RAG context for item."""
        return self.knowledge.get_rag_context_for_item(title)

    def get_rag_status(self) -> Dict:
        """Get RAG status."""
        return self.knowledge.get_rag_status()

    def get_stats(self) -> Dict:
        """Get combined stats."""
        return {
            'total': self.raw_data.get_statistics().get('total_items', 0)
        }

    def get_all_statistics(self, limit: int = 200) -> List[Dict]:
        """Get all statistics (legacy method)."""
        return []

    def get_stats_for_product_key(self, product_key: str) -> Optional[Dict]:
        """Get stats for product key (legacy method)."""
        return None

    def find_similar_items(self, chunk_key: str, limit: int = 50) -> List[Dict]:
        """Find similar items (for cultivation prompts)."""
        return self.raw_data.get_items_for_product_key(chunk_key)[:limit]

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