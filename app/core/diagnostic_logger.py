import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional
from app.config import BASE_APP_DIR, ENABLE_RAW_DATA_DIAGNOSTICS
from app.core.log_manager import logger

class DiagnosticLogger:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __init__(self, enabled: Optional[bool] = None):
        if not DiagnosticLogger._initialized:
            self.enabled = ENABLE_RAW_DATA_DIAGNOSTICS if enabled is None else enabled
            self.session_data = []
            self.session_start = datetime.now()
            self.log_dir = os.path.join(BASE_APP_DIR, "diagnostic_logs")
            os.makedirs(self.log_dir, exist_ok=True)
            timestamp = self.session_start.strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(self.log_dir, f"diagnostic_{timestamp}.json")
            self.readable_file = os.path.join(self.log_dir, f"diagnostic_{timestamp}.txt")
            DiagnosticLogger._initialized = True
        elif enabled is not None:
            self.enabled = enabled
    
    def log_item_processing(self,
                           original_item: Dict,
                           semantic_data: Dict,
                           db_result: Optional[Dict] = None,
                           intermediate_data: Optional[Dict] = None):

        if not self.enabled:
            return

        # 1. ОПРЕДЕЛЕНИЕ ВАЖНОСТИ: Логируем подробно, если это начало, ошибка или неизвестная категория
        is_error = db_result and db_result.get('status') == 'error'
        is_misc = semantic_data.get('category') == 'MISC' or semantic_data.get('product_key', '').startswith('misc')
        is_start_of_batch = len(self.session_data) < 10
        
        is_verbose = is_error or is_misc or is_start_of_batch

        # 2. АГРЕССИВНОЕ СОКРАЩЕНИЕ ДЛЯ ВСЕХ
        desc = original_item.get('description', '')
        short_desc = (desc[:50] + '... [TRUNCATED]') if desc and len(desc) > 50 else desc
        
        # 3. ПОДГОТОВКА ДАННЫХ
        entry = {
            'timestamp': datetime.now().isoformat(),
            'input': {
                'title': original_item.get('title', ''),
                'description': short_desc, 
                'price': original_item.get('price', 0),
                # Убираем city и link для экономии, если они не критичны для логики парсинга
                # 'city': original_item.get('city', ''), 
                # 'link': original_item.get('link', '') 
            },
            'semantic_analysis': {
                'category': semantic_data.get('category', 'UNKNOWN'),
                'product_key': semantic_data.get('product_key', ''),
                'cluster_key': semantic_data.get('cluster_key', ''),
                'clean_name': semantic_data.get('clean_name', ''),
                'brand': semantic_data.get('brand', ''),
                'model': semantic_data.get('model', ''),
                'entity_type': semantic_data.get('entity_type', ''),
                # features оставляем, они маленькие и важны
                'features': semantic_data.get('features', {}), 
            },
            'database': db_result or {}
        }

        # 4. УСЛОВНОЕ ДОБАВЛЕНИЕ ТЯЖЕЛЫХ ДАННЫХ
        if is_verbose:
            entry['semantic_analysis']['raw_tokens'] = semantic_data.get('raw_tokens', [])[:15]
            entry['intermediate'] = intermediate_data or {}
            entry['debug_note'] = "FULL_LOG"
        else:
            # Для успешных стандартных элементов убираем шум
            entry['semantic_analysis']['raw_tokens'] = [] 
            entry['intermediate'] = "OK (Hidden to save space)"

        self.session_data.append(entry)
    
    def save_session(self):
        """
        Сохраняет накопленные данные в файлы.
        """
        if not self.enabled or not self.session_data:
            return
        
        # === JSON версия (полные данные) ===
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump({
                'session_start': self.session_start.isoformat(),
                'session_end': datetime.now().isoformat(),
                'total_items': len(self.session_data),
                'items': self.session_data
            }, f, ensure_ascii=False, indent=2)
        
        # === Readable версия (для быстрого просмотра) ===
        with open(self.readable_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"DIAGNOSTIC LOG - {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total items: {len(self.session_data)}\n")
            f.write("=" * 80 + "\n\n")
            
            # Группируем по категориям
            by_category = {}
            for entry in self.session_data:
                cat = entry['semantic_analysis']['category']
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(entry)
            
            # Пишем по категориям
            for cat, items in sorted(by_category.items()):
                f.write(f"\n{'=' * 80}\n")
                f.write(f"CATEGORY: {cat} ({len(items)} items)\n")
                f.write(f"{'=' * 80}\n\n")
                
                for i, entry in enumerate(items, 1):
                    f.write(f"{i}. {'-' * 75}\n")
                    f.write(f"   TITLE: {entry['input']['title']}\n")
                    f.write(f"   PRICE: {entry['input']['price']} ₽\n")
                    
                    if entry['input']['description']:
                        f.write(f"   DESC:  {entry['input']['description'][:100]}...\n")
                    
                    sem = entry['semantic_analysis']
                    f.write(f"\n   → PRODUCT KEY: {sem['product_key']}\n")
                    f.write(f"   → CLEAN NAME:  {sem['clean_name']}\n")
                    f.write(f"   → BRAND:       {sem['brand']}\n")
                    f.write(f"   → MODEL:       {sem['model']}\n")
                    
                    # Промежуточные данные если есть
                    if entry['intermediate']:
                        inter = entry['intermediate']
                        if 'category_scores' in inter:
                            f.write(f"\n   CATEGORY SCORES:\n")
                            for c, score in sorted(inter['category_scores'].items(), key=lambda x: x[1], reverse=True)[:5]:
                                f.write(f"      {c}: {score:.2f}\n")
                        
                        if 'matched_keywords' in inter:
                            f.write(f"   MATCHED KEYWORDS: {', '.join(inter['matched_keywords'][:10])}\n")
                        
                        if 'components' in inter:
                            f.write(f"   COMPONENTS: {inter['components']}\n")
                    
                    # БД результат
                    if entry['database']:
                        db = entry['database']
                        f.write(f"\n   DB STATUS: {db.get('status', 'unknown')}\n")
                        f.write(f"   DB ID:     {db.get('item_id', 'N/A')}\n")
                        if db.get('product_id'):
                            f.write(f"   PRODUCT_ID: {db['product_id']}\n")
                    
                    f.write("\n")
        
        logger.success(f"Diagnostic log saved to: {self.log_file}")
        logger.success(f"Readable log saved to: {self.readable_file}")
    
    def clear_session(self):
        """Очищает накопленные данные."""
        self.session_data = []
        self.session_start = datetime.now()


_diagnostic_logger = None

def get_diagnostic_logger(enabled: bool = True) -> DiagnosticLogger:
    global _diagnostic_logger
    if _diagnostic_logger is None:
        _diagnostic_logger = DiagnosticLogger(enabled=enabled)
    return _diagnostic_logger

def enable_diagnostics():
    logger = get_diagnostic_logger()
    logger.enabled = True
    logger.clear_session()
    return logger

def disable_diagnostics():
    logger = get_diagnostic_logger()
    logger.enabled = False

def save_diagnostics():
    logger = get_diagnostic_logger()
    logger.save_session()