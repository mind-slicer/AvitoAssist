import sqlite3
import json
import os
import re
import hashlib
import time
import threading
from typing import List, Dict, Optional
from datetime import datetime
from collections import Counter
from dataclasses import dataclass
import numpy as np
from app.config import BASE_APP_DIR
from app.core.log_manager import logger


def evaluate_item_placement(
    title: str,
    description: str,
    product_key: str,
    category: str,
    brand: str = "",
    model: str = ""
) -> bool:
    """
    Evaluate if an item is correctly placed in its category/product.
    
    Args:
        title: Item title
        description: Item description
        product_key: Product key from semantic_data
        category: Category name (GPU, CPU, LAPTOP, etc.)
        brand: Brand from semantic_data
        model: Model from semantic_data
    
    Returns:
        True if placement is reliable, False if suspicious
    """
    if not title:
        return False

    title_lower = title.lower()
    desc_lower = (description or "").lower()
    combined_text = f"{title_lower} {desc_lower}"
    category = category.upper()

    # --- 1. GLOBAL DEFECT CHECK ---
    # Слова, указывающие на то, что это мусор/запчасти, а не полноценный товар
    # (кроме категорий, где это нормально)
    if category not in ["MISC", "ACCESSORY", "SERVICE", "COOLING", "CASE"]:
        defect_markers = [
            "на запчасти", "на разбор", "донор", "труп", "не включается", 
            "не рабочий", "под восстановление", "запчасти", "разборка"
        ]
        # Если в ЗАГОЛОВКЕ есть маркер дефекта -> ненадежно
        if any(m in title_lower for m in defect_markers):
            return False

    # --- 2. CATEGORY RULES ---
    
    # REQUIRED: Слова, хотя бы одно из которых ОБЯЗАНО быть (Positive)
    # BANNED: Слова, наличие которых сразу делает товар ненадежным (Negative)
    # ALLOWED_CONFLICTS: Категории, ключевые слова которых допустимы внутри текущей (для систем)
    
    rules = {
        "LAPTOP": {
            "required": ["ноутбук", "laptop", "ultrabook", "macbook", "нетбук", "notebook"],
            "banned": [
                "матрица", "клавиатура", "аккумулятор", "батарея", "зарядка", "блок питания", 
                "петли", "шлейф", "корпус", "топкейс", "поддон", "разбор", "кулер", 
                "вентилятор", "видеокарта для", "плата для", "разъем", "кнопки", "запчасти"
            ],
            "allowed_conflicts": ["GPU", "CPU", "RAM", "STORAGE", "MONITOR"] # Ноутбук содержит это внутри
        },
        "PC_BUILD": {
            "required": ["системный", "блок", "пк", "компьютер", "сборка", "desktop", "station", "server", "моноблок", "imac", "mac mini"],
            "banned": [
                "корпус без", "пустой корпус", "коробка", "вентилятор", "кулер", 
                "видеокарта", "майнинг ферма", "риг", "райзер"
            ],
            "allowed_conflicts": ["GPU", "CPU", "RAM", "STORAGE", "MOTHERBOARD", "PSU", "CASE", "COOLING"]
        },
        "GPU": {
            "required": ["видеокарта", "gpu", "rtx", "gtx", "rx", "radeon", "geforce", "arc", "quadro", "tesla", "titan", "gt", "видеоадаптер"],
            "banned": [
                "ноутбук", "laptop", "райзер", "riser", "кабель", "переходник", 
                "кулер", "охлаждение", "коробка", "держатель", "подставка", "доставка", "скупка"
            ],
            "allowed_conflicts": []
        },
        "CPU": {
            "required": ["процессор", "cpu", "ryzen", "core", "intel", "amd", "xeon", "pentium", "celeron", "athlon", "phenom"],
            "banned": [
                "ноутбук", "laptop", "системный", "компьютер", "сборка", "материнская", "плата", "комплект", "кулер"
            ],
            "allowed_conflicts": []
        },
        "MOTHERBOARD": {
            "required": ["материнская", "плата", "motherboard", "mainboard", "mb", "мать", "сокет", "socket", "lga", "am4", "am5"],
            "banned": [
                "ноутбук", "laptop", "системный", "компьютер"
            ],
            "allowed_conflicts": ["CPU", "RAM"] # Часто продают комплекты "Мать + Проц"
        },
        "MONITOR": {
            "required": ["монитор", "monitor", "дисплей", "экран"],
            "banned": [
                "ноутбук", "laptop", "разбит", "матрица", "кронштейн", "кабель", "системный", "пк", "моноблок"
            ],
            "allowed_conflicts": []
        }
    }

    # Если категории нет в правилах (например RAM, SSD), используем базовую проверку
    if category not in rules:
        # Для мелочевки (ACCESSORY, MISC) считаем надежным по умолчанию, если нет явного треша
        if category in ["ACCESSORY", "MISC", "SERVICE", "COOLING", "CASE"]:
            return True
        # Для других (RAM, PSU) - нужна минимальная проверка
        if category == "RAM" and not any(k in combined_text for k in ["память", "ram", "ddr", "озу"]): return False
        if category == "PSU" and not any(k in combined_text for k in ["блок", "питания", "psu", "power"]): return False
        if category == "STORAGE" and not any(k in combined_text for k in ["ssd", "hdd", "диск", "накопитель"]): return False
        return True

    rule = rules[category]

    # 1. Check BANNED (Immediate Fail)
    # Проверяем только TITLE для строгости, описание может содержать "подойдет для..."
    for ban in rule["banned"]:
        if ban in title_lower:
             # Исключение: "Не ноутбук" (редкий кейс, но все же)
             return False

    # 2. Check REQUIRED (Must have one)
    has_required = False
    for req in rule["required"]:
        # Проверяем слово целиком или вхождение
        if req in title_lower:
            has_required = True
            break
    
    if not has_required:
        # Если нет ключевого слова в заголовке, проверяем начало описания (первые 100 символов)
        if any(req in desc_lower[:100] for req in rule["required"]):
            has_required = True
        else:
            return False

    # 3. Conflict Check (Cross-contamination)
    # Проверяем, не упоминается ли другая "сильная" категория в заголовке
    strong_categories = ["LAPTOP", "PC_BUILD", "GPU", "MONITOR"]
    
    for other_cat in strong_categories:
        if other_cat == category: continue
        if other_cat in rule["allowed_conflicts"]: continue
        
        other_rule = rules.get(other_cat)
        if not other_rule: continue
        
        # Если в заголовке найдено ключевое слово ЧУЖОЙ категории
        # Пример: Category=GPU, Title="Ноутбук Asus RTX 3060" -> Нашли "Ноутбук" -> Fail
        for other_req in other_rule["required"]:
            if other_req in title_lower:
                # Особый случай: "Видеокарта для ноутбука" -> Category=GPU. 
                # Нашли "ноутбук". Но это запчасть.
                # Если текущая категория GPU, а нашли "ноутбук" - это плохо, так как GPU для ноутов это обычно мусор/запчасти
                # Если текущая категория PC_BUILD, а нашли "монитор" - это ОК ("ПК с монитором")
                return False

    # 4. Brand Consistency (Soft Check)
    if brand and brand != "NO_BRAND":
        brand_clean = brand.lower().replace(" ", "")
        # Если бренд явно указан, он должен быть в тексте (хотя бы похоже)
        # Но делаем скидку на длину: короткие бренды (HP, LG) часто теряются или пишутся кириллицей
        if len(brand_clean) > 2:
            if brand_clean not in combined_text.replace(" ", ""):
                # Попробуем кириллицу (очень примитивно)
                # Если бренда нет нигде - это подозрительно для дорогих товаров
                if category in ["LAPTOP", "GPU", "MONITOR"]:
                    # Допускаем отсутствие бренда в тексте, если есть ОЧЕНЬ сильное совпадение по модели
                    if model and len(model) > 3 and model.lower().replace(" ", "") in combined_text.replace(" ", ""):
                        pass
                    else:
                        # Штрафуем, но не баним сразу (может быть опечатка)
                        # Но для строгости - вернем False
                        return False

    return True


class StatisticsCache:
    def __init__(self, ttl_seconds=60):
        self.ttl = ttl_seconds
        self._data = None
        self._last_update = 0

    def get(self):
        if self._data and (time.time() - self._last_update < self.ttl):
            return self._data
        return None

    def set(self, data):
        self._data = data
        self._last_update = time.time()

    def invalidate(self):
        self._data = None

@dataclass
class AddItemResult:
    item_id: int
    status: str
    price_changed: bool = False
    
    def __eq__(self, other):
        if isinstance(other, str):
            return self.status == other
        return super().__eq__(other)

    def __str__(self):
        return self.status

class RawDataManager:
    SCHEMA_VERSION = 10
    DB_FILENAME = "memory_raw_data.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(BASE_APP_DIR, self.DB_FILENAME)
        self._stats_cache = StatisticsCache(ttl_seconds=60)
        self._city_cache = {}
        self._seller_cache = {}
        self._cache_lock = threading.Lock()
        self._ensure_db_exists()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -64000;")
        conn.execute("PRAGMA mmap_size = 268435456;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        return conn

    def _ensure_db_exists(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            if cursor.fetchone() is None:
                logger.info("Creating fresh PURE database schema")
                cursor.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY DEFAULT 1)")
                cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
                self._create_all_tables(cursor)
                conn.commit()
                return

            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0
            
            if current_version < self.SCHEMA_VERSION:
                logger.info(f"Migrating raw_data schema from {current_version} to {self.SCHEMA_VERSION}")
                self._migrate_schema(cursor, current_version, self.SCHEMA_VERSION)
                cursor.execute("UPDATE schema_version SET version = ?", (self.SCHEMA_VERSION,))
                self._ensure_tables_exist(cursor)
                conn.commit()
        finally:
            conn.close()

    def _ensure_tables_exist(self, cursor: sqlite3.Cursor):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_items'")
        if cursor.fetchone() is None:
            self._create_all_tables(cursor)

    def _create_all_tables(self, cursor: sqlite3.Cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sellers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_link_id TEXT UNIQUE NOT NULL,
                rating REAL DEFAULT 0.0,
                status TEXT DEFAULT 'active'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                display_name TEXT,
                brand TEXT,
                model TEXT,
                category_id INTEGER,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT,
                original_category_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)
        
        # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id TEXT UNIQUE NOT NULL,
                title TEXT,
                price INTEGER,
                description TEXT,
                condition TEXT,
                views INTEGER,
                date_text TEXT,
                link TEXT,
                raw_data TEXT,
                city_id INTEGER REFERENCES cities(id),
                seller_table_id INTEGER REFERENCES sellers(id),
                product_id INTEGER REFERENCES products(id),
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT,
                original_product_id INTEGER,
                placement_confidence INTEGER DEFAULT 1,
                
                is_outlier INTEGER DEFAULT 0,  -- <--- ДОБАВЛЕНО
                embedding BLOB,                -- <--- ДОБАВЛЕНО
                
                analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # -------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_item_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (raw_item_id) REFERENCES raw_items(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_key TEXT UNIQUE NOT NULL,
                target_product_key TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_ad_id ON raw_items(ad_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_price ON raw_items(price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item ON price_history(raw_item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_key ON products(key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_price_city ON raw_items(price, city_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_analyzed_price ON raw_items(analyzed_at, price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_product_id ON raw_items(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_date ON price_history(raw_item_id, recorded_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category_brand ON products(category_id, brand, display_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_valid_prices ON raw_items(price, city_id) WHERE price > 0")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_ad_id_analyzed ON raw_items(ad_id, analyzed_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_deleted ON raw_items(is_deleted, deleted_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_deleted ON products(is_deleted)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_deleted ON categories(is_deleted)")
        
        # Новые индексы тоже полезно добавить сразу
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aliases_key ON product_aliases(alias_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_outlier ON raw_items(is_outlier)")

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int, to_version: int):
        if from_version < 2:
            self._create_all_tables(cursor)
        if from_version < 3:
            cursor.execute("CREATE TABLE IF NOT EXISTS user_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, action_type TEXT, details TEXT, created_at TEXT)")
        if from_version < 4:
            self._create_all_tables(cursor)
        if from_version < 5:
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_price_city ON raw_items(price, city_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_analyzed_price ON raw_items(analyzed_at, price)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_product_id ON raw_items(product_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_date ON price_history(raw_item_id, recorded_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category_brand ON products(category_id, brand, display_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_valid_prices ON raw_items(price, city_id) WHERE price > 0")
            except Exception: pass
        if from_version < 6:
            pass
        if from_version < 7:
             try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_ad_id_analyzed ON raw_items(ad_id, analyzed_at DESC)")
                logger.info("Миграция v7: добавлен composite index на (ad_id, analyzed_at)")
             except Exception as e:
                logger.error(f"Migration to v7 failed: {e}")
        if from_version < 8:
            try:
                cursor.execute("ALTER TABLE raw_items ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE raw_items ADD COLUMN deleted_at TEXT")
                cursor.execute("ALTER TABLE raw_items ADD COLUMN original_product_id INTEGER")
                
                cursor.execute("ALTER TABLE products ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE products ADD COLUMN deleted_at TEXT")
                cursor.execute("ALTER TABLE products ADD COLUMN original_category_id INTEGER")

                cursor.execute("ALTER TABLE categories ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE categories ADD COLUMN deleted_at TEXT")
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_deleted ON raw_items(is_deleted, deleted_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_deleted ON products(is_deleted)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_deleted ON categories(is_deleted)")
                logger.info("Миграция v8: добавлена поддержка мягкого удаления (корзина)")
            except Exception as e:
                logger.error(f"Migration to v8 failed: {e}")
        if from_version < 9:
            try:
                cursor.execute("ALTER TABLE raw_items ADD COLUMN placement_confidence INTEGER DEFAULT 1")
                logger.info("✅ v9: Added placement_confidence column to raw_items")
            except Exception as e:
                logger.error(f"Migration to v9 failed: {e}")
        if from_version < 10:
            try:
                # 1. Таблица алиасов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS product_aliases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alias_key TEXT UNIQUE NOT NULL,
                        target_product_key TEXT NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 2. Поля для аналитики и векторов
                cursor.execute("ALTER TABLE raw_items ADD COLUMN is_outlier INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE raw_items ADD COLUMN embedding BLOB")
                
                # 3. Индексы
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_aliases_key ON product_aliases(alias_key)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_outlier ON raw_items(is_outlier)")
                
                logger.info("✅ v10: Added aliases, embeddings, and outlier detection columns")
            except Exception as e:
                logger.error(f"Migration to v10 failed: {e}")

    def resolve_product_key(self, raw_key: str) -> str:
        """Проверяет, есть ли для ключа алиас. Если нет - возвращает исходный."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT target_product_key FROM product_aliases WHERE alias_key = ?", (raw_key,))
            row = cursor.fetchone()
            return row[0] if row else raw_key
        finally:
            conn.close()

    # Проверка на выброс (Hard Math)
    def _check_is_outlier(self, price: int, category: str, cursor: sqlite3.Cursor) -> bool:
        if price <= 100: return True # Мусорные цены
        
        try:
            cursor.execute("""
                SELECT AVG(ri.price) 
                FROM raw_items ri
                JOIN products p ON ri.product_id = p.id
                JOIN categories c ON p.category_id = c.id
                WHERE c.name = ? AND ri.price > 100 AND ri.is_deleted = 0
                ORDER BY ri.analyzed_at DESC LIMIT 100
            """, (category,))
            row = cursor.fetchone()
            if not row or not row[0]: return False
            
            avg_price = row[0]
            
            if price < avg_price * 0.2 or price > avg_price * 10.0:
                return True
                
        except Exception:
            return False
        return False

    def get_or_create_city(self, name: str, cursor: sqlite3.Cursor) -> int:
        with self._cache_lock:
            if name in self._city_cache:
                return self._city_cache[name]
        
        cursor.execute("SELECT id FROM cities WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            res = row[0]
        else:
            cursor.execute("INSERT INTO cities (name) VALUES (?)", (name,))
            res = cursor.lastrowid
            
        with self._cache_lock:
            self._city_cache[name] = res
        return res

    def get_or_create_seller(self, seller_id_str: str, cursor: sqlite3.Cursor) -> int:
        with self._cache_lock:
            if seller_id_str in self._seller_cache:
                return self._seller_cache[seller_id_str]

        cursor.execute("SELECT id FROM sellers WHERE seller_link_id = ?", (seller_id_str,))
        row = cursor.fetchone()
        if row:
            res = row[0]
        else:
            cursor.execute("INSERT INTO sellers (seller_link_id) VALUES (?)", (seller_id_str,))
            res = cursor.lastrowid
            
        with self._cache_lock:
            self._seller_cache[seller_id_str] = res
        return res

    def get_or_create_category(self, name: str, cursor: sqlite3.Cursor = None) -> int:
        own_cursor = cursor is None
        conn = None
        try:
            if own_cursor:
                conn = self._get_connection()
                cursor = conn.cursor()

            clean_name = name.strip().upper()
            cursor.execute("SELECT id FROM categories WHERE name = ?", (clean_name,))
            row = cursor.fetchone()
            if row:
                cat_id = row[0]
            else:
                cursor.execute("INSERT INTO categories (name) VALUES (?)", (clean_name,))
                cat_id = cursor.lastrowid
                if own_cursor: conn.commit()
            return cat_id
        finally:
            if own_cursor and conn: conn.close()

    def add_raw_items_bulk(self, items_with_meta: List[Dict]) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        count = 0
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            with self._cache_lock:
                city_cache = self._city_cache.copy()
                seller_cache = self._seller_cache.copy()

            cursor.execute("SELECT name, id FROM cities")
            for name, city_id in cursor.fetchall():
                city_cache[name] = city_id

            cursor.execute("SELECT seller_link_id, id FROM sellers")
            for link_id, seller_id in cursor.fetchall():
                seller_cache[link_id] = seller_id

            new_cities = set()
            new_sellers = set()
            
            seen_ad_ids = set()
            unique_items = []

            for entry in items_with_meta:
                item = entry['item']
                ad_id = str(item.get('id') or item.get('ad_id') or self._extract_ad_id(item.get('link', '')) or "")
                if not ad_id:
                    unique_str = f"{item.get('title')}_{item.get('seller_id')}_{item.get('city')}"
                    ad_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
                
                if ad_id in seen_ad_ids:
                    continue
                seen_ad_ids.add(ad_id)
                unique_items.append(entry)

                city_str = item.get('city', '').strip()
                seller_str = item.get('seller_id', '').strip()

                if city_str and city_str not in city_cache:
                    new_cities.add(city_str)
                if seller_str and seller_str not in seller_cache:
                    new_sellers.add(seller_str)

            if new_cities:
                cursor.executemany(
                    "INSERT OR IGNORE INTO cities (name) VALUES (?)",
                    [(c,) for c in new_cities]
                )
                cursor.execute("SELECT name, id FROM cities WHERE name IN ({})".format(
                    ','.join('?' * len(new_cities))
                ), list(new_cities))
                for name, city_id in cursor.fetchall():
                    city_cache[name] = city_id

            if new_sellers:
                cursor.executemany(
                    "INSERT OR IGNORE INTO sellers (seller_link_id) VALUES (?)",
                    [(s,) for s in new_sellers]
                )
                cursor.execute("SELECT seller_link_id, id FROM sellers WHERE seller_link_id IN ({})".format(
                    ','.join('?' * len(new_sellers))
                ), list(new_sellers))
                for link_id, seller_id in cursor.fetchall():
                    seller_cache[link_id] = seller_id

            with self._cache_lock:
                self._city_cache.update(city_cache)
                self._seller_cache.update(seller_cache)

            for entry in unique_items:
                item = entry['item']
                item['_city_id_cached'] = city_cache.get(item.get('city', '').strip())
                item['_seller_id_cached'] = seller_cache.get(item.get('seller_id', '').strip())
                
                result = self.add_raw_item(item, external_cursor=cursor)
                if result.status in ('created', 'updated'):
                    count += 1

            conn.commit()
            self._stats_cache.invalidate()
            logger.success(f"Bulk insert: добавлено {count}/{len(unique_items)} уникальных элементов")

        except Exception as e:
            logger.error(f"Bulk insert failed: {e}", exc_info=True)
            conn.rollback()
            count = 0
        finally:
            conn.close()
        return count

    def add_raw_item(self, item: Dict, external_cursor: sqlite3.Cursor = None) -> AddItemResult:
        own_connection = external_cursor is None
        conn = None
        try:
            if own_connection:
                conn = self._get_connection()
                cursor = conn.cursor()
            else:
                cursor = external_cursor

            # 1. Генерация AD ID
            ad_id = str(item.get('id') or item.get('ad_id') or self._extract_ad_id(item.get('link', '')) or "")
            if not ad_id:
                unique_str = f"{item.get('title')}_{item.get('seller_id')}_{item.get('city')}"
                ad_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()

            # 2. Извлечение базовых полей
            title = item.get('title', '')
            price = item.get('price', 0)
            city_str = item.get('city', 'Неизвестно')
            seller_str = item.get('seller_id', '')

            # 3. Кеширование внешних ключей (City/Seller)
            if '_city_id_cached' in item:
                city_id = item.pop('_city_id_cached')
            else:
                city_id = self.get_or_create_city(city_str, cursor)

            if '_seller_id_cached' in item:
                seller_db_id = item.pop('_seller_id_cached')
            else:
                seller_db_id = self.get_or_create_seller(seller_str, cursor)

            # 4. Обработка семантики (NLP)
            product_id = None
            semantic = item.get('semantic_data')
            
            if not semantic:
                logger.error(f"Элемент '{title}' ({ad_id}) добавлен БЕЗ 'semantic_data'! БЛОКИРОВАН.")
                return AddItemResult(-1, "error", False)

            # --- [NEW] Векторизация (Embeddings) ---
            embedding_blob = None
            if 'embedding_vector' in semantic and semantic['embedding_vector'] is not None:
                try:
                    # Конвертируем numpy array в bytes для BLOB
                    embedding_blob = semantic['embedding_vector'].astype(np.float32).tobytes()
                except Exception as e:
                    logger.warning(f"Embedding conversion failed for {ad_id}: {e}")

            # --- [NEW] Алиасы (Product Key Resolution) ---
            raw_p_key = semantic.get('product_key', 'misc_unknown')
            p_key = self.resolve_product_key(raw_p_key) # Приводим к каноническому виду

            cat_name = semantic.get('category', 'MISC')
            brand = semantic.get('brand')
            model = semantic.get('model')
            clean_name = semantic.get('clean_name')

            # 5. Привязка к Product/Category
            cat_id = self.get_or_create_category(cat_name, cursor)
            
            # Ищем продукт по УЖЕ нормализованному ключу
            cursor.execute("SELECT id FROM products WHERE key = ?", (p_key,))
            p_row = cursor.fetchone()
            if p_row:
                product_id = p_row[0]
            else:
                cursor.execute("""
                    INSERT INTO products (key, display_name, brand, model, category_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (p_key, clean_name, brand, model, cat_id))
                product_id = cursor.lastrowid

            # --- [NEW] Детекция выбросов (Outlier Detection) ---
            is_outlier = 0
            if price > 0:
                if self._check_is_outlier(price, cat_name, cursor):
                    is_outlier = 1

            # 6. Проверка существования записи (Upsert Logic)
            cursor.execute("""
                SELECT id, price, analyzed_at FROM raw_items WHERE ad_id = ?
                ORDER BY analyzed_at DESC LIMIT 1
            """, (ad_id,))
            existing = cursor.fetchone()

            from datetime import datetime, timedelta
            current_time = datetime.now().isoformat()

            if existing:
                # --- UPDATE SCENARIO ---
                raw_item_id = existing[0]
                old_price = existing[1]
                last_analyzed = existing[2]
                
                # Троттлинг обновлений (не чаще раза в минуту)
                if last_analyzed:
                    try:
                        last_dt = datetime.fromisoformat(last_analyzed)
                        if datetime.now() - last_dt < timedelta(seconds=60):
                            return AddItemResult(raw_item_id, "skipped_recent", False)
                    except:
                        pass

                price_diff_percent = abs(old_price - price) / old_price if old_price > 0 else 0
                price_changed = (price_diff_percent >= 0.01 and price > 0)

                if price_changed:
                    # Записываем историю цен
                    cursor.execute("""
                        INSERT INTO price_history (raw_item_id, price, recorded_at)
                        VALUES (?, ?, ?)
                    """, (raw_item_id, old_price, current_time))
                    
                    # Полное обновление, включая embedding и is_outlier
                    cursor.execute("""
                        UPDATE raw_items SET
                        title = ?, price = ?, description = ?, condition = ?,
                        views = ?, date_text = ?, link = ?, analyzed_at = ?,
                        city_id = ?, seller_table_id = ?, product_id = ?,
                        embedding = ?, is_outlier = ?
                        WHERE id = ?
                    """, (
                        title, price, item.get('description'), item.get('condition'),
                        item.get('views', 0), item.get('date_text'), item.get('link'),
                        current_time,
                        city_id, seller_db_id, product_id,
                        embedding_blob, is_outlier,
                        raw_item_id
                    ))
                    status = "updated"
                else:
                    # Легкое обновление (только метаданные)
                    cursor.execute("""
                        UPDATE raw_items SET
                        analyzed_at = ?, views = ?,
                        city_id = ?, seller_table_id = ?, product_id = ?,
                        embedding = ?, is_outlier = ?
                        WHERE id = ?
                    """, (
                        current_time, item.get('views', 0),
                        city_id, seller_db_id, product_id,
                        embedding_blob, is_outlier,
                        raw_item_id
                    ))
                    status = "skipped"
                
                result = AddItemResult(raw_item_id, status, price_changed)
            else:
                # --- INSERT SCENARIO ---
                cursor.execute("""
                    INSERT INTO raw_items (
                        ad_id, title, price, description, condition,
                        views, date_text, link, analyzed_at, created_at,
                        city_id, seller_table_id, product_id,
                        embedding, is_outlier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ad_id, title, price, item.get('description'), item.get('condition'),
                    item.get('views'), item.get('date_text'), item.get('link'),
                    current_time, current_time,
                    city_id, seller_db_id, product_id,
                    embedding_blob, is_outlier
                ))
                raw_item_id = cursor.lastrowid
                
                if price > 0:
                    cursor.execute("""
                        INSERT INTO price_history (raw_item_id, price, recorded_at)
                        VALUES (?, ?, ?)
                    """, (raw_item_id, price, current_time))
                
                result = AddItemResult(raw_item_id, "created", False)

            # 7. Расчет Placement Confidence (Smart Placement)
            if result.status in ("created", "updated"):
                try:
                    # Используем внешнюю функцию оценки (она должна быть импортирована)
                    is_reliable = evaluate_item_placement(
                        title=title,
                        description=item.get("description", ""),
                        product_key=p_key,
                        category=cat_name,
                        brand=brand or "",
                        model=model or ""
                    )

                    cursor.execute("""
                        UPDATE raw_items 
                        SET placement_confidence = ? 
                        WHERE id = ?
                    """, (1 if is_reliable else 0, raw_item_id))

                except Exception as e:
                    logger.warning(f"Could not calculate placement_confidence: {e}")

            if own_connection:
                conn.commit()

            if result.status in ("created", "updated"):
                self._stats_cache.invalidate()
            
            return result

        except Exception as e:
            logger.error(f"DB Error in add_raw_item: {e}", exc_info=True)
            if own_connection and conn:
                conn.rollback()
            return AddItemResult(-1, "error", False)
        finally:
            if own_connection and conn:
                conn.close()

    def get_raw_items(self, category: Optional[str] = None,
                      product_key: Optional[str] = None,
                      search_query: Optional[str] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT DISTINCT
                    ri.id, ri.ad_id, ri.title, ri.price, ri.description,
                    cit.name as city,
                    ri.condition,
                    sel.seller_link_id as seller_id,
                    ri.views, ri.date_text, ri.link,
                    ri.analyzed_at, ri.created_at, ri.product_id,
                    prod.key as clean_product_key,
                    prod.brand,
                    prod.model,
                    c.name as category_name,
                    ri.placement_confidence, ri.is_deleted, ri.deleted_at
                FROM raw_items ri
                LEFT JOIN cities cit ON ri.city_id = cit.id
                LEFT JOIN sellers sel ON ri.seller_table_id = sel.id
                LEFT JOIN products prod ON ri.product_id = prod.id
                LEFT JOIN categories c ON prod.category_id = c.id
                WHERE ri.is_deleted = 0
            """
            params = []
            
            if category:
                query += " AND c.name = ?"
                params.append(category)
            if product_key:
                query += " AND prod.key = ?"
                params.append(product_key)
            if search_query:
                query += " AND (ri.title LIKE ? OR ri.description LIKE ? OR cit.name LIKE ?)"
                search_term = f"%{search_query}%"
                params.extend([search_term, search_term, search_term])
            
            query += " ORDER BY ri.analyzed_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [self._item_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_raw_items_count(self, category: Optional[str] = None,
                            product_key: Optional[str] = None) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(ri.id)
                FROM raw_items ri
                LEFT JOIN products prod ON ri.product_id = prod.id
                LEFT JOIN categories c ON prod.category_id = c.id
                WHERE 1=1
            """
            params = []
            
            if category:
                query += " AND c.name = ?"
                params.append(category)
            if product_key:
                query += " AND prod.key = ?"
                params.append(product_key)
                
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            return count if count is not None else 0
        except Exception as e:
            logger.error(f"Error getting raw items count: {e}", exc_info=True)
            return 0
        finally:
            conn.close()

    def _item_from_row(self, row: sqlite3.Row) -> Dict:
        item = dict(row)
        if item.get('clean_product_key'):
            item['product_keys'] = [item['clean_product_key']]
        else:
            item['product_keys'] = []
        
        cat_name = item.get('category_name')
        item['categories'] = [cat_name] if cat_name else []
        
        if 'category_name' in item:
            del item['category_name']
            
        return item

    def get_hierarchy_data(self) -> Dict:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT 
                    c.name as category_name,
                    COALESCE(p.brand, 'NO_BRAND') as brand,
                    COALESCE(p.display_name, p.key) as display_name,
                    p.key as product_key,
                    p.id as product_id,
                    COUNT(ri.id) as item_count
                FROM products p
                JOIN categories c ON p.category_id = c.id
                LEFT JOIN raw_items ri ON p.id = ri.product_id AND ri.is_deleted = 0
                WHERE p.is_deleted = 0 AND c.is_deleted = 0
                GROUP BY c.name, p.brand, p.display_name, p.key, p.id
                ORDER BY c.name, p.brand, p.display_name
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            tree = {}
            for row in rows:
                cat = row['category_name']
                brand = row['brand']
                if not brand: brand = 'NO_BRAND'
                brand = brand.upper()
                
                if cat not in tree: tree[cat] = {}
                if brand not in tree[cat]: tree[cat][brand] = []
                
                tree[cat][brand].append({
                    'id': row['product_id'],
                    'key': row['product_key'],
                    'name': row['display_name'],
                    'count': row['item_count']
                })
            return tree
        finally:
            conn.close()

    def _extract_ad_id(self, link: str) -> Optional[str]:
        if not link: return None
        match = re.search(r'/(\d+)(?:\?|$)', link)
        return match.group(1) if match else None

    def get_database_vocabulary(self, limit: int = 60) -> List[str]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM raw_items ORDER BY id DESC LIMIT 1000")
            titles = [r[0] for r in cursor.fetchall()]
            
            word_counter = Counter()
            stop_words = {'продам', 'куплю', 'цена', 'торг', 'обмен', 'новый', 'бу', 'состояние', 'комплект', 'гарантия', 'для', 'на', 'с', 'по', 'от', 'и', 'в'}
            
            for t in titles:
                words = re.findall(r'\b[a-zA-Zа-яА-Я]{3,}\b', t.lower())
                for w in words:
                    if w not in stop_words:
                        word_counter[w] += 1
            
            return [w for w, count in word_counter.most_common(limit)]
        finally:
            conn.close()

    def cleanup_old_data(self, days=180):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM price_history WHERE recorded_at < date('now', ?)",
                (f'-{days} days',)
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_categories(self) -> List[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.id, c.name, COUNT(ri.id) as item_count
                FROM categories c
                LEFT JOIN products p ON c.id = p.category_id
                LEFT JOIN raw_items ri ON p.id = ri.product_id
                GROUP BY c.id
                ORDER BY c.name
            """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_all_product_keys(self, category_id: Optional[int] = None) -> List[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT p.id, p.key, p.display_name, p.category_id, c.name as category_name,
                       COUNT(ri.id) as item_count
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                LEFT JOIN raw_items ri ON p.id = ri.product_id
                WHERE 1=1
            """
            params = []
            if category_id:
                query += " AND p.category_id = ?"
                params.append(category_id)
            
            query += " GROUP BY p.id ORDER BY p.key"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_or_create_product_key(self, key: str, display_name: Optional[str] = None, category_id: Optional[int] = None) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM products WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row: return row[0]
            
            cursor.execute("INSERT INTO products (key, display_name, category_id) VALUES (?, ?, ?)", (key, display_name, category_id))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_items_for_product_key(self, product_key: str) -> List[Dict]:
        return self.get_raw_items(product_key=product_key)

    def get_raw_item_by_id(self, item_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT ri.*, cit.name as city, sel.seller_link_id as seller_id, prod.key as clean_product_key,
                       c.name as category_name, ri.placement_confidence
                FROM raw_items ri
                LEFT JOIN cities cit ON ri.city_id = cit.id
                LEFT JOIN sellers sel ON ri.seller_table_id = sel.id
                LEFT JOIN products prod ON ri.product_id = prod.id
                LEFT JOIN categories c ON prod.category_id = c.id
                WHERE ri.id = ?
            """
            cursor.execute(query, (item_id,))
            row = cursor.fetchone()
            return self._item_from_row(row) if row else None
        finally:
            conn.close()

    def delete_raw_items(self, item_ids: List[int]) -> int:
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            cursor.execute(f"DELETE FROM raw_items WHERE id IN ({placeholders})", item_ids)
            conn.commit()
            self._stats_cache.invalidate()
            return cursor.rowcount
        finally:
            conn.close()

    def delete_category(self, category_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def clear_all_raw_items(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_items")
            count = cursor.fetchone()[0] or 0
            
            cursor.execute("DELETE FROM raw_items")
            cursor.execute("DELETE FROM price_history")
            conn.commit()
            self._stats_cache.invalidate()
            return count
        finally:
            conn.close()

    def get_statistics(self) -> Dict:
        cached = self._stats_cache.get()
        if cached:
            return cached

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_items")
            total_items = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM categories")
            total_cats = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM products")
            total_prods = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(price) FROM raw_items WHERE price > 0")
            avg_price = cursor.fetchone()[0] or 0

            result = {
                'total_items': total_items,
                'total_categories': total_cats,
                'total_product_keys': total_prods,
                'avg_price': round(avg_price, 2) if avg_price else 0
            }
            self._stats_cache.set(result)
            return result
        finally:
            conn.close()

    def log_user_action(self, action_type: str, details: str):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO user_actions (action_type, details) VALUES (?, ?)", (action_type, str(details)[:500]))
            conn.commit()
        except Exception as e:
            logger.dev(f"Action log error: {e}", level="ERROR")
        finally:
            conn.close()

    def get_recent_actions(self, limit: int = 50) -> List[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_actions ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def cleanup_old_actions(self, keep_last: int = 1000):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user_actions ORDER BY id DESC LIMIT 1 OFFSET ?", (keep_last,))
            row = cursor.fetchone()
            if row:
                cutoff_id = row[0]
                cursor.execute("DELETE FROM user_actions WHERE id < ?", (cutoff_id,))
                conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def reset_database(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._stats_cache.invalidate()
        self._ensure_db_exists()
        logger.info("Raw data database reset complete")

    def calculate_data_signature(self, product_key: Optional[str] = None, category_name: Optional[str] = None, category_key: Optional[str] = None) -> str:
        """
        Рассчитывает хеш-сигнатуру данных для проверки изменений.
        Поддерживает алиас category_key для совместимости с системой чанков.
        """
        import hashlib

        # Алиас для совместимости
        if category_key and not category_name:
            category_name = category_key

        try:
            query = "SELECT title, price, date_text FROM raw_items WHERE 1=1"
            params = []

            if product_key:
                query += " AND product_id = (SELECT id FROM products WHERE key = ?)"
                params.append(product_key)

            if category_name:
                query += " AND product_id IN (SELECT id FROM products WHERE category_id = (SELECT id FROM categories WHERE name = ?))"
                params.append(category_name)

            query += " ORDER BY id LIMIT 1000"

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return "empty"

            data_str = ""
            for row in rows:
                # Простая конкатенация ключевых полей
                data_str += f"{row[0]}|{row[1]}|{row[2]}#"

            if not data_str:
                return "empty"

            signature = hashlib.sha256(data_str.encode()).hexdigest()
            return signature

        except Exception as e:
            logger.error(f"Error calculating signature: {e}")
            return "error"
    
    def save_history_snapshot(self, product_key: Optional[str] = None, stats_snapshot: Optional[Dict] = None):
        """Сохраняет снепшот истории для анализа изменений (в JSON файл)"""
        try:
            import os
            from datetime import datetime
            
            if not product_key or not stats_snapshot:
                return
            
            # Создаём директорию для истории
            history_dir = os.path.join(BASE_APP_DIR, "chunk_history")
            os.makedirs(history_dir, exist_ok=True)
            
            # Генерируем безопасное имя файла
            safe_key = product_key.replace('/', '_').replace('\\', '_')
            history_file = os.path.join(history_dir, f"{safe_key}_history.json")
            
            # Читаем существующую историю
            history = []
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except:
                    history = []
            
            # Добавляем новый снепшот
            snapshot = {
                'recorded_at': datetime.utcnow().isoformat(),
                **stats_snapshot
            }
            history.append(snapshot)
            
            # Сохраняем обратно (только последние 50 снепшотов)
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history[-50:], f, ensure_ascii=False, indent=2)
            
            logger.dev(f"History snapshot saved for {product_key}", level="DEBUG")
        
        except Exception as e:
            logger.dev(f"Error saving history snapshot: {e}", level="DEBUG")
    
    
    def get_chunk_history(self, product_key: str, limit: int = 10) -> List[Dict]:
        """Получает историю изменений чанка"""
        try:
            import os
            
            history_dir = os.path.join(BASE_APP_DIR, "chunk_history")
            safe_key = product_key.replace('/', '_').replace('\\', '_')
            history_file = os.path.join(history_dir, f"{safe_key}_history.json")
            
            if not os.path.exists(history_file):
                return []
            
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            return history[-limit:] if history else []
        
        except Exception as e:
            logger.dev(f"Error getting chunk history: {e}", level="DEBUG")
            return []

    def export_to_json(self, filepath: str):
        data = {
            'exported_at': datetime.now().isoformat(),
            'schema_version': self.SCHEMA_VERSION,
            'categories': self.get_all_categories(),
            'product_keys': self.get_all_product_keys(),
            'items': self.get_raw_items(limit=999999)
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.success(f"Exported {len(data['items'])} items to {filepath}")

    def import_from_json(self, filepath: str, clear_first: bool = False):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            
            if clear_first:
                self.clear_all_raw_items()

            items = data.get('items', [])
            count = 0
            
            for item in items:
                self.add_raw_item(
                    item, 
                    external_cursor=cursor
                )
                count += 1
                if count % 1000 == 0:
                    conn.commit()
                    cursor.execute("BEGIN TRANSACTION")

            conn.commit()
            logger.success(f"Imported {count} items from {filepath}")
        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"Import error: {e}")
            raise
        finally:
            conn.close()

    def soft_delete_items(self, item_ids: List[int]) -> int:
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            placeholders = ','.join('?' * len(item_ids))
            
            query = f"""
                UPDATE raw_items
                SET is_deleted = 1, deleted_at = ?, original_product_id = product_id
                WHERE id IN ({placeholders}) AND is_deleted = 0
            """
            params = [now] + item_ids
            
            cursor.execute(query, params)
            count = cursor.rowcount
            
            conn.commit()
            self._stats_cache.invalidate()
            return count
        except Exception as e:
            logger.error(f"Bulk delete error: {e}")
            return 0
        finally:
            conn.close()

    def soft_delete_product(self, product_id: int) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("SELECT category_id FROM products WHERE id = ?", (product_id,))
            row = cursor.fetchone()
            if not row: return 0
            
            cursor.execute("""
                UPDATE raw_items
                SET is_deleted = 1, deleted_at = ?, original_product_id = product_id
                WHERE product_id = ? AND is_deleted = 0
            """, (now, product_id))
            items_count = cursor.rowcount
            
            cursor.execute("""
                UPDATE products
                SET is_deleted = 1, deleted_at = ?, original_category_id = category_id
                WHERE id = ?
            """, (now, product_id))
            
            conn.commit()
            self._stats_cache.invalidate()
            return items_count
        finally:
            conn.close()

    def soft_delete_category(self, category_id: int) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("SELECT id FROM products WHERE category_id = ? AND is_deleted = 0", (category_id,))
            product_ids = [row[0] for row in cursor.fetchall()]
            
            total_items = 0
            for pid in product_ids:
                cursor.execute("""
                    UPDATE raw_items
                    SET is_deleted = 1, deleted_at = ?, original_product_id = product_id
                    WHERE product_id = ? AND is_deleted = 0
                """, (now, pid))
                total_items += cursor.rowcount
                
            cursor.execute("""
                UPDATE products
                SET is_deleted = 1, deleted_at = ?, original_category_id = category_id
                WHERE category_id = ? AND is_deleted = 0
            """, (now, category_id))
            
            cursor.execute("""
                UPDATE categories
                SET is_deleted = 1, deleted_at = ?
                WHERE id = ?
            """, (now, category_id))
            
            conn.commit()
            self._stats_cache.invalidate()
            return total_items
        finally:
            conn.close()

    def restore_item(self, item_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE raw_items
                SET is_deleted = 0, deleted_at = NULL, product_id = original_product_id
                WHERE id = ? AND is_deleted = 1
            """, (item_id,))
            conn.commit()
            self._stats_cache.invalidate()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def restore_items(self, item_ids: List[int]) -> int:
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            query = f"""
                UPDATE raw_items
                SET is_deleted = 0, deleted_at = NULL, product_id = original_product_id
                WHERE id IN ({placeholders}) AND is_deleted = 1
            """
            cursor.execute(query, item_ids)
            count = cursor.rowcount
            conn.commit()
            self._stats_cache.invalidate()
            return count
        except Exception as e:
            logger.error(f"Bulk restore error: {e}")
            return 0
        finally:
            conn.close()

    def permanent_delete_item(self, item_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM raw_items WHERE id = ? AND is_deleted = 1", (item_id,))
            conn.commit()
            self._stats_cache.invalidate()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def permanent_delete_items(self, item_ids: List[int]) -> int:
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            cursor.execute(f"DELETE FROM raw_items WHERE id IN ({placeholders}) AND is_deleted = 1", item_ids)
            conn.commit()
            self._stats_cache.invalidate()
            return cursor.rowcount
        finally:
            conn.close()

    def get_trash_items(self, limit: int = 1000) -> List[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT DISTINCT
                    ri.id, ri.ad_id, ri.title, ri.price, ri.description,
                    cit.name as city,
                    ri.condition,
                    sel.seller_link_id as seller_id,
                    ri.views, ri.date_text, ri.link,
                    ri.analyzed_at, ri.created_at, ri.deleted_at, ri.original_product_id,
                    prod.key as clean_product_key,
                    prod.brand,
                    prod.model,
                    c.name as category_name,
                    ri.placement_confidence, ri.is_deleted
                FROM raw_items ri
                LEFT JOIN cities cit ON ri.city_id = cit.id
                LEFT JOIN sellers sel ON ri.seller_table_id = sel.id
                LEFT JOIN products prod ON ri.original_product_id = prod.id
                LEFT JOIN categories c ON prod.category_id = c.id
                WHERE ri.is_deleted = 1
                ORDER BY ri.deleted_at DESC LIMIT ?
            """
            cursor.execute(query, (limit,))
            return [self._item_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def move_item_to_product(self, item_id: int, target_product_id: int) -> bool:
        return self.move_items_to_product([item_id], target_product_id) > 0

    def move_items_to_product(self, item_ids: List[int], target_product_id: int) -> int:
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            
            cursor.execute("SELECT id FROM products WHERE id = ?", (target_product_id,))
            if not cursor.fetchone():
                return 0
            
            query = f"""
                UPDATE raw_items
                SET product_id = ?, is_deleted = 0, deleted_at = NULL
                WHERE id IN ({placeholders})
            """
            params = [target_product_id] + item_ids
            cursor.execute(query, params)
            count = cursor.rowcount

            logger.info(f"Recalculating placement_confidence for {count} moved items...")
            recalculated = 0
            for item_id in item_ids:
                if self.recalculate_placement_confidence(item_id):
                    recalculated += 1
            logger.success(f"✓ {recalculated}/{count} items recalculated")

            conn.commit()
            self._stats_cache.invalidate()
            return count
        except Exception as e:
            logger.error(f"Bulk move error: {e}")
            return 0
        finally:
            conn.close()

    def update_item_confidence(self, item_id: int, is_reliable: bool) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE raw_items 
                SET placement_confidence = ? 
                WHERE id = ?
            """, (1 if is_reliable else 0, item_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating confidence for item {item_id}: {e}")
            return False
        finally:
            conn.close()

    def recalculate_placement_confidence(self, item_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT ri.title, ri.description, ri.price, 
                       p.key as product_key, c.name as category_name,
                       p.brand, p.model
                FROM raw_items ri
                LEFT JOIN products p ON ri.product_id = p.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE ri.id = ?
            """, (item_id,))

            row = cursor.fetchone()
            if not row:
                return False

            title = row[0] or ""
            description = row[1] or ""
            product_key = row[3] or ""
            category = row[4] or "MISC"
            brand = row[5] or ""
            model = row[6] or ""

            try:
                is_reliable = evaluate_item_placement(
                    title=title,
                    description=description,
                    product_key=product_key,
                    category=category,
                    brand=brand,
                    model=model
                )
            except ImportError:
                logger.warning("evaluate_item_placement not found, defaulting to reliable")
                is_reliable = True

            cursor.execute("""
                UPDATE raw_items 
                SET placement_confidence = ? 
                WHERE id = ?
            """, (1 if is_reliable else 0, item_id))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error recalculating confidence for item {item_id}: {e}")
            return False
        finally:
            conn.close()

    def bulk_recalculate_confidence(self, item_ids: List[int]) -> int:
        count = 0
        for item_id in item_ids:
            if self.recalculate_placement_confidence(item_id):
                count += 1
        return count

    def empty_trash(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM raw_items WHERE is_deleted = 1")
            items_deleted = cursor.rowcount
            
            cursor.execute("DELETE FROM products WHERE is_deleted = 1")
            cursor.execute("DELETE FROM categories WHERE is_deleted = 1")
            
            conn.commit()
            self._stats_cache.invalidate()
            return items_deleted
        finally:
            conn.close()