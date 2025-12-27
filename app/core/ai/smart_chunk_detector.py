import re
from collections import Counter
from typing import List, Tuple
from app.core.log_manager import logger
from app.core.text_utils import TextMatcher

class SmartChunkDetector:
    CATEGORY_NORMALIZATION = {
        'rtx': 'nvidia rtx',
        'gtx': 'nvidia gtx',
        'rx': 'amd rx',
        'ryzen': 'amd ryzen',
        'core i': 'intel core i',
        'игровой пк': 'игровой пк',
        'озу': 'озу ddr',
        'ssd': 'ssd',
        'материнская плата': 'материнская плата',
    }

    @staticmethod
    def _normalize_title(title: str) -> str:
        t = title.lower()
        t = re.sub(r'[^\w\s]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        
        for variant, norm in SmartChunkDetector.CATEGORY_NORMALIZATION.items():
            if variant in t:
                t = t.replace(variant, norm)
        
        trash = ['продам', 'куплю', 'новый', 'бу', 'срочно', 'торг', 'обмен']
        for word in trash:
            t = t.replace(word, '')
        
        return re.sub(r'\s+', ' ', t).strip()

    @staticmethod
    def detect_new_chunks(memory_manager) -> List[Tuple[str, str, str]]:
        to_create = []
        
        try:
            rows = memory_manager.raw_data.get_items()
            if not rows:
                return []
                
            titles = [r['title'] for r in rows]
            normalized = [SmartChunkDetector._normalize_title(t) for t in titles]
            
            key_counts = Counter()
            key_examples = {}
            
            for norm, orig in zip(normalized, titles):
                words = [w for w in norm.split() if len(w) > 3]
                if len(words) >= 2:
                    key = " ".join(words[:3])
                    key_counts[key] += 1
                    if key not in key_examples:
                        key_examples[key] = orig
            
            for key, count in key_counts.items():
                if count >= 6:
                    existing = memory_manager.knowledge.get_chunk_by_key("PRODUCT", key)
                    if not existing:
                        nice_title = " ".join(word.capitalize() for word in key.split())
                        to_create.append(("PRODUCT", key, f"Анализ рынка: {nice_title}"))
            
            total_items = memory_manager.get_stats().get("total", 0)
            if total_items >= 20:
                existing_db = memory_manager.get_chunk_by_key("DATABASE", "general")
                if not existing_db:
                    to_create.append(("DATABASE", "general", "Глобальная аналитика базы"))
                    
        except Exception as e:
            logger.error(f"SmartDetector error: {e}", token="ai-det")
        
        return to_create
    
    @staticmethod
    def create_missing_chunks(memory_manager, chunk_manager):
        missing = SmartChunkDetector.detect_new_chunks(memory_manager)
        created = 0
        for chunk_type_str, key, title in missing:
            from app.core.ai.chunk_cultivation import ChunkType
            ctype = ChunkType.PRODUCT if chunk_type_str == "PRODUCT" else ChunkType.DATABASE
            try:
                chunk_manager.create_pending_chunk(ctype, key, title)
                created += 1
            except:
                pass
        
        if created:
            logger.info(f"Создано {created} новых чанков...", token="ai-det")