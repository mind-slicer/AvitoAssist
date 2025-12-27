"""
MemoryManager - Unified facade for raw data and knowledge management.
Combines RawDataManager and KnowledgeManager for comprehensive data persistence.
"""

import sys
import os
from typing import List, Dict, Optional

# Add workspace root to path for imports
_workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from app.config import BASE_APP_DIR

from app.core.text_utils import FeatureExtractor
from app.core.memory.raw_data_manager import RawDataManager
from app.core.memory.knowledge_manager import KnowledgeManager
from app.core.log_manager import logger


class MemoryManager:
    """
    Unified access point for all memory storage operations.
    Combines raw items storage and AI knowledge management.
    """

    def __init__(self):
        # Initialize both managers
        self.raw_data = RawDataManager()
        self.knowledge = KnowledgeManager()
        logger.success("MemoryManager initialized with persistent storage")

    # === Delegated methods for raw data ===

    def add_raw_item(self, item: Dict, categories: Optional[List[str]] = None,
                     product_keys: Optional[List[str]] = None) -> int:
        """Add raw item with categories and product keys."""
        return self.raw_data.add_raw_item(item, categories, product_keys)

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

    # === Delegated methods for knowledge ===

    def add_knowledge(self, chunk_type: str, chunk_key: str, title: str,
                      content: Optional[Dict] = None, status: str = 'PENDING',
                      priority: int = 1) -> int:
        """Add or update knowledge chunk."""
        return self.knowledge.add_knowledge(chunk_type, chunk_key, title, content, status, priority)

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

    def update_chunk_content(self, chunk_id: int, content: Dict, summary: Optional[str] = None):
        """Update chunk content."""
        self.knowledge.update_chunk_content(chunk_id, content, summary)

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

    # === RAG methods ===

    def get_rag_context_for_item(self, title: str) -> Optional[Dict]:
        """Get RAG context for item."""
        return self.knowledge.get_rag_context_for_item(title)

    def get_rag_status(self) -> Dict:
        """Get RAG status."""
        return self.knowledge.get_rag_status()

    # === Legacy/statistics methods (for backward compatibility) ===

    def add_item(self, item: Dict) -> bool:
        """
        Возвращает True, если элемент был добавлен или обновлен.
        """
        title = item.get('title', '')
        
        # Умная генерация ключа
        product_key = FeatureExtractor.generate_product_key(title)
        
        # В качестве категории берем первое слово из ключа или 'unknown'
        category = product_key.split('_')[0] if '_' in product_key else 'misc'

        status = self.raw_data.add_raw_item(
            item, 
            categories=[category], 
            product_keys=[product_key]
        )
        
        return status in ['created', 'updated']

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

    # === Export/Import ===

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

    # === Reset ===

    def reset_all(self):
        """Reset all data."""
        self.raw_data.reset_database()
        self.knowledge.reset_database()
        logger.info("All memory data reset complete")