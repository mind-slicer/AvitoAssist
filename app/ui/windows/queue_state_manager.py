import os
import json
from typing import Dict, List, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal

from app.config import BASE_APP_DIR


class QueueStateManager(QObject):
    state_loaded = pyqtSignal(int, dict)
    state_saved = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.queues_data: Dict[int, Dict[str, Any]] = {}
        self.current_queue_index: int = 0
        
        self._load_all_queues()
    
    def get_current_index(self) -> int:
        return self.current_queue_index
    
    def set_current_index(self, index: int):
        self.current_queue_index = index
        self._ensure_queue_exists(index)
    
    def get_state(self, queue_index: Optional[int] = None) -> Dict[str, Any]:
        if queue_index is None:
            queue_index = self.current_queue_index
        
        self._ensure_queue_exists(queue_index)
        return self.queues_data[queue_index]
    
    def set_state(self, state: Dict[str, Any], queue_index: Optional[int] = None):
        if queue_index is None:
            queue_index = self.current_queue_index
    
        base = self._create_default_state()
    
        if queue_index in self.queues_data:
            base.update(self.queues_data[queue_index])
    
        base.update(state)
    
        self.queues_data[queue_index] = base
        self.state_saved.emit(queue_index)
    
    def update_state(self, updates: Dict[str, Any], queue_index: Optional[int] = None):
        if queue_index is None:
            queue_index = self.current_queue_index
        
        self._ensure_queue_exists(queue_index)
        self.queues_data[queue_index].update(updates)
        self.state_saved.emit(queue_index)
    
    def _ensure_queue_exists(self, queue_index: int):
        if queue_index not in self.queues_data:
            self.queues_data[queue_index] = self._create_default_state()
    
    def _create_default_state(self) -> Dict[str, Any]:
        return {
            "name": "",
            "search_tags": [],
            "ignore_tags": [],
            "min_price": 0,
            "max_price": 0,
            "search_mode": "full",
            "ai_criteria": "",
            "include_ai": False,
            "store_in_memory": False,
            "max_pages": 0,
            "max_items": 0,
            "all_regions": False,
            "filter_defects": False,
            "forced_categories": [],
            "scanned_categories": [],
            "split_ads_count": 0,
            "use_queue_manager": False,
            "use_blacklist": False,
            "sort_type": "default",
            "queue_enabled": True, 
            "rewrite_duplicates": False,
            "skip_duplicates": False,
            "allow_rewrite_duplicates": False,
            "split_results": False
        }
    
    def get_all_queue_indices(self) -> List[int]:
        return sorted(self.queues_data.keys())
    
    def delete_queue(self, queue_index: int):
        if queue_index in self.queues_data:
            del self.queues_data[queue_index]
    
        new_data: Dict[int, Dict[str, Any]] = {}
        for old_idx in sorted(self.queues_data.keys()):
            new_idx = old_idx if old_idx < queue_index else old_idx - 1
            new_data[new_idx] = self.queues_data[old_idx]
    
        self.queues_data = new_data
        self._save_all_queues()

    def clear_all_queues(self):
        self.queues_data.clear()
        self._ensure_queue_exists(0)
        self._save_all_queues()
    
    def copy_queue(self, from_index: int, to_index: int):
        if from_index in self.queues_data:
            self.queues_data[to_index] = self.queues_data[from_index].copy()
            self.queues_data[to_index]["name"] = "" 
            self.state_saved.emit(to_index)
    
    def clear_scanned_categories_bulk(self):
        changed = False
        for idx, state in self.queues_data.items():
            if state.get("scanned_categories"):
                state["scanned_categories"] = []
                changed = True
        
        if changed:
            self._save_all_queues()
            if self.current_queue_index in self.queues_data:
                pass
    
    def _queues_file_path(self) -> str:
        return os.path.join(BASE_APP_DIR, "queues_state.json")
    
    def _load_all_queues(self):
        path = self._queues_file_path()
        
        if not os.path.exists(path):
            self.queues_data[0] = self._create_default_state()
            return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            loaded = {}
            if isinstance(data, dict):
                for key, value in data.items():
                    try:
                        index = int(key)
                        if isinstance(value, dict):
                            state = self._create_default_state()
                            state.update(value)
                            state["forced_categories"] = []
                            loaded[index] = state
                    except (ValueError, TypeError):
                        continue
            
            if loaded:
                self.queues_data = loaded
            else:
                self.queues_data[0] = self._create_default_state()
        
        except Exception as e:
            self.queues_data[0] = self._create_default_state()
    
    def _save_all_queues(self):
        path = self._queues_file_path()
        
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            save_data = {str(k): v for k, v in self.queues_data.items()}
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            pass
    
    def save_current_state(self):
        self._save_all_queues()
        self.state_saved.emit(self.current_queue_index)
    
    def load_queue_state(self, queue_index: int):
        self.current_queue_index = queue_index
        state = self.get_state(queue_index)
        self.state_loaded.emit(queue_index, state)
    
    def export_queue(self, queue_index: int) -> str:
        state = self.get_state(queue_index)
        return json.dumps(state, ensure_ascii=False, indent=2)
    
    def import_queue(self, json_string: str, queue_index: int) -> bool:
        try:
            data = json.loads(json_string)
            if not isinstance(data, dict):
                return False
            
            state = self._create_default_state()
            state.update(data)
            
            self.set_state(state, queue_index)
            self._save_all_queues()
            return True
        
        except Exception as e:
            return False
    
    def validate_state(self, state: Dict[str, Any]) -> bool:
        required_fields = [
            "search_tags", "ignore_tags", "min_price", "max_price",
            "search_mode", "max_pages", "max_items"
        ]
        
        for field in required_fields:
            if field not in state:
                return False
        
        if not isinstance(state["search_tags"], list):
            return False
        if not isinstance(state["ignore_tags"], list):
            return False
        if state["search_mode"] not in ["primary", "full", "neuro"]:
            return False
        
        return True
    
    def get_queue_count(self) -> int:
        return len(self.queues_data)
    
    def get_non_empty_queues(self) -> List[int]:
        result = []
        for index, state in self.queues_data.items():
            if state.get("search_tags"):
                result.append(index)
        return sorted(result)
    
    def get_queue_summary(self, queue_index: int) -> str:
        state = self.get_state(queue_index)
        
        custom_name = state.get("name", "")
        if custom_name:
             return f"Queue {queue_index}: {custom_name}"

        tags = state.get("search_tags", [])
        if not tags:
            return f"Queue {queue_index}: Empty"
        
        tags_preview = ", ".join(tags[:3])
        if len(tags) > 3:
            tags_preview += "..."
        
        return f"Queue {queue_index}: {tags_preview} ({len(tags)} tags)"