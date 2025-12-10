import json
import os
from typing import List, Optional
from datetime import datetime
from app.config import BASE_APP_DIR
from app.core.log_manager import logger


class BlacklistEntry:
    """Одна запись в черном списке: seller_id + имя"""

    def __init__(self, seller_id: str, custom_name: str = ""):
        self.seller_id = str(seller_id).strip().lower()
        if not self.seller_id:
            raise ValueError("Seller ID cannot be empty")
            
        self.custom_name = custom_name.strip() or f"Seller_{self.seller_id}"
        self.added_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "seller_id": self.seller_id,
            "custom_name": self.custom_name,
            "added_at": self.added_at
        }

    @staticmethod
    def from_dict(data: dict) -> 'BlacklistEntry':
        entry = BlacklistEntry(data["seller_id"], data.get("custom_name", ""))
        entry.added_at = data.get("added_at", datetime.now().isoformat())
        return entry


class BlacklistSet:
    """Один набор черного списка"""

    def __init__(self, name: str):
        self.name = name
        self.entries: List[BlacklistEntry] = []
        self.created_at = datetime.now().isoformat()
        self.is_active = False

    def add_entry(self, seller_id: str, custom_name: str = "") -> BlacklistEntry:
        """Добавить запись в набор"""
        # Проверка на дубликаты
        for entry in self.entries:
            if entry.seller_id == seller_id:
                return entry

        new_entry = BlacklistEntry(seller_id, custom_name)
        self.entries.append(new_entry)
        return new_entry

    def remove_entry(self, seller_id: str) -> bool:
        """Удалить запись из набора"""
        for i, entry in enumerate(self.entries):
            if entry.seller_id == seller_id:
                self.entries.pop(i)
                return True
        return False

    def update_entry_name(self, seller_id: str, new_name: str):
        """Обновить имя записи"""
        for entry in self.entries:
            if entry.seller_id == seller_id:
                entry.custom_name = new_name.strip() or f"Seller_{seller_id}"
                return True
        return False

    def get_seller_ids(self) -> set:
        """Получить множество всех seller_id в наборе"""
        return {entry.seller_id for entry in self.entries}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "entries": [e.to_dict() for e in self.entries],
            "created_at": self.created_at,
            "is_active": self.is_active
        }

    @staticmethod
    def from_dict(data: dict) -> 'BlacklistSet':
        bl_set = BlacklistSet(data["name"])
        bl_set.entries = [BlacklistEntry.from_dict(e) for e in data.get("entries", [])]
        bl_set.created_at = data.get("created_at", datetime.now().isoformat())
        bl_set.is_active = data.get("is_active", False)
        return bl_set


class BlacklistManager:
    """Менеджер всех наборов черного списка"""

    SAVE_FILE = "blacklist_sets.json"

    def __init__(self):
        self.sets: List[BlacklistSet] = []
        self.active_set_index: Optional[int] = None
        self._ensure_default_set()

    def _ensure_default_set(self):
        """Создает набор по умолчанию если нет наборов"""
        if not self.sets:
            default_set = BlacklistSet("Основной набор")
            default_set.is_active = True
            self.sets.append(default_set)
            self.active_set_index = 0

    def create_set(self, name: str) -> BlacklistSet:
        """Создать новый набор"""
        new_set = BlacklistSet(name)
        self.sets.append(new_set)
        return new_set

    def delete_set(self, index: int) -> bool:
        """Удалить набор (если не единственный)"""
        if len(self.sets) <= 1:
            return False

        if 0 <= index < len(self.sets):
            self.sets.pop(index)

            # Корректируем активный индекс
            if self.active_set_index == index:
                self.active_set_index = 0
                self.sets[0].is_active = True
            elif self.active_set_index and self.active_set_index > index:
                self.active_set_index -= 1

            return True
        return False

    def rename_set(self, index: int, new_name: str) -> bool:
        """Переименовать набор"""
        if 0 <= index < len(self.sets):
            self.sets[index].name = new_name.strip()
            return True
        return False

    def activate_set(self, index: int):
        """Активировать набор"""
        if 0 <= index < len(self.sets):
            # Деактивировать все
            for s in self.sets:
                s.is_active = False

            # Активировать выбранный
            self.sets[index].is_active = True
            self.active_set_index = index

    def get_active_set(self) -> Optional[BlacklistSet]:
        """Получить активный набор"""
        if self.active_set_index is not None and 0 <= self.active_set_index < len(self.sets):
            return self.sets[self.active_set_index]
        return None

    def get_active_seller_ids(self) -> set:
        """Получить все seller_id из активного набора"""
        active = self.get_active_set()
        return active.get_seller_ids() if active else set()

    def save(self):
        """Сохранить все наборы в файл"""
        filepath = os.path.join(BASE_APP_DIR, self.SAVE_FILE)
        data = {
            "sets": [s.to_dict() for s in self.sets],
            "active_index": self.active_set_index
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.dev(f"Blacklist save error: {e}", level="ERROR")

    def load(self):
        """Загрузить наборы из файла"""
        filepath = os.path.join(BASE_APP_DIR, self.SAVE_FILE)

        if not os.path.exists(filepath):
            self._ensure_default_set()
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.sets = [BlacklistSet.from_dict(s) for s in data.get("sets", [])]
            self.active_set_index = data.get("active_index")

            if not self.sets:
                self._ensure_default_set()

        except Exception as e:
            logger.dev(f"Blacklist load error: {e}", level="ERROR")
            self._ensure_default_set()


# Глобальный экземпляр
_blacklist_manager = None


def get_blacklist_manager() -> BlacklistManager:
    """Получить глобальный экземпляр менеджера"""
    global _blacklist_manager
    if _blacklist_manager is None:
        _blacklist_manager = BlacklistManager()
        _blacklist_manager.load()
    return _blacklist_manager
