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
    
    This function checks if the item's title and description match
    the expected category and product key without using neural networks.
    
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
    
    # 1. Basic validation
    if not title or not product_key or not category:
        return False
    
    title_lower = title.lower()
    desc_lower = (description or "").lower()
    combined_text = f"{title_lower} {desc_lower}"
    
    # 2. Category keyword mapping
    category_keywords = {
        "GPU": ["видеокарта", "видеокарт", "gpu", "rtx", "gtx", "radeon", "geforce", "rx ", "arc "],
        "CPU": ["процессор", "cpu", "ryzen", "core i", "intel", "amd", "xeon", "pentium", "celeron"],
        "RAM": ["память", "ram", "озу", "ddr", "оперативн"],
        "STORAGE": ["ssd", "hdd", "накопитель", "жесткий", "nvme", "m.2", "диск"],
        "LAPTOP": ["ноутбук", "laptop", "lenovo", "asus", "hp", "dell", "acer", "macbook"],
        "MOTHERBOARD": ["материнская", "мат. плата", "материнка", "motherboard", "сокет", "socket"],
        "PSU": ["блок питания", "psu", "power supply", "бп ", "watts"],
        "MONITOR": ["монитор", "display", "экран", "дисплей"],
        "COOLING": ["кулер", "охлаждение", "вентилятор", "cooling", "cooler"],
        "CASE": ["корпус", "case"],
        "ACCESSORY": ["кабель", "cable", "мышь", "mouse", "клавиатур"],
        "PCBUILD": ["сборка", "системный блок", "компьютер", "pc build"],
    }
    
    # Check if current category keywords are present
    current_keywords = category_keywords.get(category, [])
    has_category_match = any(kw in combined_text for kw in current_keywords)
    
    # Check for conflicts with other categories
    conflicting_categories = 0
    conflicting_cats = []
    for cat, keywords in category_keywords.items():
        if cat != category:
            if any(kw in combined_text for kw in keywords):
                conflicting_categories += 1
                conflicting_cats.append(cat)
    
    # 3. Critical category rules
    if category in ["GPU", "CPU", "LAPTOP", "MOTHERBOARD"]:
        # Laptop in GPU category = unreliable
        if category == "GPU" and any(kw in combined_text for kw in ["ноутбук", "laptop"]):
            return False
        
        # GPU mentioned separately in LAPTOP = unreliable
        if category == "LAPTOP" and "видеокарта" in combined_text and "ноутбук" not in combined_text:
            return False
        
        # Critical categories must have explicit match
        if not has_category_match:
            return False
    
    # 4. Product key validation
    if "unknown" in product_key.lower() and category not in ["ACCESSORY", "MISC", "SERVICE"]:
        # Unknown product keys are suspicious for hardware
        return False
    
    if product_key.startswith(category.lower() + "-") and len(product_key) < 10:
        # Very short product keys are suspicious
        return False
    
    # 5. Brand/Model consistency check
    if brand and len(brand) > 2:
        if brand.lower() not in combined_text:
            # Brand not found in text - suspicious for critical categories
            if category in ["GPU", "CPU", "LAPTOP"]:
                return False
    
    if model and len(model) > 2:
        model_clean = model.replace("-", "").replace(" ", "").lower()
        text_clean = combined_text.replace("-", "").replace(" ", "")
        if model_clean not in text_clean:
            # Model not found - suspicious for GPU/CPU
            if category in ["GPU", "CPU"]:
                return False
    
    # 6. Final decision logic
    result = None
    if has_category_match and conflicting_categories <= 1:
        result = True
    elif conflicting_categories >= 2:
        result = False
    elif category in ["ACCESSORY", "MISC", "SERVICE", "COOLING", "CASE"]:
        result = True
    else:
        result = has_category_match
    
    # Debug logging for first few items
    if title:  # Simple check to avoid spam
        from app.core.log_manager import logger
        logger.dev(
            f"Confidence eval: '{title[:30]}...' -> {category} -> "
            f"{'RELIABLE' if result else 'UNRELIABLE'} "
            f"(match={has_category_match}, conflicts={conflicting_categories})"
        )
    
    return result


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
    SCHEMA_VERSION = 9
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
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -64000")
        conn.execute("PRAGMA mmap_size = 268435456")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _ensure_db_exists(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            if cursor.fetchone() is None:
                logger.info("Creating fresh PURE v7 database schema")
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
                analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
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

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int, to_version: int):
        if from_version < 2:
            self._create_all_tables(cursor)
        if from_version < 3:
            cursor.execute("CREATE TABLE IF NOT EXISTS user_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, action_type TEXT, details TEXT, created_at TEXT)")
        if from_version < 4:
            self._create_all_tables(cursor)
            # Migration logic for v4 omitted for brevity as in original
            pass
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
            # v6 specific migration
            pass
        if from_version < 7:
             try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_ad_id_analyzed ON raw_items(ad_id, analyzed_at DESC)")
                logger.info("Миграция v7: добавлен composite index на (ad_id, analyzed_at)")
             except Exception as e:
                logger.error(f"Migration to v7 failed: {e}")
        if from_version < 8:
            try:
                # Добавляем поля для мягкого удаления
                cursor.execute("ALTER TABLE raw_items ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE raw_items ADD COLUMN deleted_at TEXT")
                cursor.execute("ALTER TABLE raw_items ADD COLUMN original_product_id INTEGER")
                
                cursor.execute("ALTER TABLE products ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE products ADD COLUMN deleted_at TEXT")
                cursor.execute("ALTER TABLE products ADD COLUMN original_category_id INTEGER")

                cursor.execute("ALTER TABLE categories ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE categories ADD COLUMN deleted_at TEXT")
                
                # Индексы для корзины
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_deleted ON raw_items(is_deleted, deleted_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_deleted ON products(is_deleted)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_deleted ON categories(is_deleted)")
                logger.info("Миграция v8: добавлена поддержка мягкого удаления (корзина)")
            except Exception as e:
                logger.error(f"Migration to v8 failed: {e}")
        if from_version < 9:
            try:
                # Add placement_confidence column (1=reliable, 0=unreliable)
                cursor.execute("ALTER TABLE raw_items ADD COLUMN placement_confidence INTEGER DEFAULT 1")
                logger.info("✅ v9: Added placement_confidence column to raw_items")
            except Exception as e:
                logger.error(f"Migration to v9 failed: {e}")

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
            
            # Загружаем кэши с блокировкой
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
            
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Проверка дублей внутри батча
            seen_ad_ids = set()
            unique_items = []

            for entry in items_with_meta:
                item = entry['item']
                ad_id = str(item.get('id') or item.get('ad_id') or self._extract_ad_id(item.get('link', '')) or "")
                if not ad_id:
                    unique_str = f"{item.get('title')}_{item.get('seller_id')}_{item.get('city')}"
                    ad_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
                
                # Пропускаем дубли в батче
                if ad_id in seen_ad_ids:
                    logger.warning(f"Дубль в батче (ad_id={ad_id[:8]}...), пропущен")
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

            # Обновляем глобальные кэши
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

            ad_id = str(item.get('id') or item.get('ad_id') or self._extract_ad_id(item.get('link', '')) or "")
            if not ad_id:
                unique_str = f"{item.get('title')}_{item.get('seller_id')}_{item.get('city')}"
                ad_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()

            title = item.get('title', '')
            price = item.get('price', 0)
            city_str = item.get('city', 'Неизвестно')
            seller_str = item.get('seller_id', '')

            if '_city_id_cached' in item:
                city_id = item.pop('_city_id_cached')
            else:
                city_id = self.get_or_create_city(city_str, cursor)

            if '_seller_id_cached' in item:
                seller_db_id = item.pop('_seller_id_cached')
            else:
                seller_db_id = self.get_or_create_seller(seller_str, cursor)

            product_id = None
            semantic = item.get('semantic_data')
            
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Блокируем элементы без semantic_data
            if not semantic:
                logger.error(f"Элемент '{title}' ({ad_id}) добавлен БЕЗ 'semantic_data'! БЛОКИРОВАН.")
                return AddItemResult(-1, "error", False)

            p_key = semantic.get('product_key', 'misc_unknown')
            cat_name = semantic.get('category', 'MISC')
            brand = semantic.get('brand')
            model = semantic.get('model')
            clean_name = semantic.get('clean_name')

            cat_id = self.get_or_create_category(cat_name, cursor)
            
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

            # Используем новый composite index
            cursor.execute("""
                SELECT id, price, analyzed_at FROM raw_items WHERE ad_id = ?
                ORDER BY analyzed_at DESC LIMIT 1
            """, (ad_id,))
            existing = cursor.fetchone()

            from datetime import datetime, timedelta
            current_time = datetime.now().isoformat()

            if existing:
                raw_item_id = existing[0]
                old_price = existing[1]
                last_analyzed = existing[2]
                
                # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Не обновляем, если обновлялось менее 60 секунд назад
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
                    cursor.execute("""
                        INSERT INTO price_history (raw_item_id, price, recorded_at)
                        VALUES (?, ?, ?)
                    """, (raw_item_id, old_price, current_time))
                    
                    cursor.execute("""
                        UPDATE raw_items SET
                        title = ?, price = ?, description = ?, condition = ?,
                        views = ?, date_text = ?, link = ?, analyzed_at = ?,
                        city_id = ?, seller_table_id = ?, product_id = ?
                        WHERE id = ?
                    """, (
                        title, price, item.get('description'), item.get('condition'),
                        item.get('views', 0), item.get('date_text'), item.get('link'),
                        current_time,
                        city_id, seller_db_id, product_id,
                        raw_item_id
                    ))
                    status = "updated"
                else:
                    cursor.execute("""
                        UPDATE raw_items SET
                        analyzed_at = ?, views = ?,
                        city_id = ?, seller_table_id = ?, product_id = ?
                        WHERE id = ?
                    """, (
                        current_time, item.get('views', 0),
                        city_id, seller_db_id, product_id,
                        raw_item_id
                    ))
                    status = "skipped"
                
                result = AddItemResult(raw_item_id, status, price_changed)
            else:
                cursor.execute("""
                    INSERT INTO raw_items (
                        ad_id, title, price, description, condition,
                        views, date_text, link, analyzed_at, created_at,
                        city_id, seller_table_id, product_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ad_id, title, price, item.get('description'), item.get('condition'),
                    item.get('views'), item.get('date_text'), item.get('link'),
                    current_time, current_time,
                    city_id, seller_db_id, product_id
                ))
                raw_item_id = cursor.lastrowid
                
                if price > 0:
                    cursor.execute("""
                        INSERT INTO price_history (raw_item_id, price, recorded_at)
                        VALUES (?, ?, ?)
                    """, (raw_item_id, price, current_time))
                
                result = AddItemResult(raw_item_id, "created", False)

            if result.status in ("created", "updated"):
                try:
                    # Вызываем пересчет ДО коммита, чтобы сохранить в той же транзакции
                    title = item.get("title", "")
                    description = item.get("description", "")

                    is_reliable = evaluate_item_placement(
                        title=title,
                        description=description,
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
        
        # Optimization: Use fetched category_name instead of N+1 query
        cat_name = item.get('category_name')
        item['categories'] = [cat_name] if cat_name else []
        
        # Clean up internal field if not needed in final dict
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

    def calculate_data_signature(self, category_key: Optional[str] = None, product_key: Optional[str] = None) -> str:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            base_query = """
                SELECT ri.id, ri.price, ri.title, ri.analyzed_at
                FROM raw_items ri
                LEFT JOIN products p ON ri.product_id = p.id
                WHERE 1=1
            """
            params = []
            if product_key:
                base_query += " AND p.key = ?"
                params.append(product_key)
            elif category_key:
                base_query += " AND p.key LIKE ?"
                params.append(f"{category_key}%")
            
            base_query += " ORDER BY ri.id"
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            
            if not rows: return "empty"
            
            content_str = ""
            for r in rows:
                content_str += f"{r[0]}:{r[1]}:{r[2]}:{r[3]}|"
            
            return hashlib.md5(content_str.encode('utf-8')).hexdigest()
        except Exception:
            return "error"
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
            # Start explicit transaction
            cursor.execute("BEGIN TRANSACTION")
            
            if clear_first:
                self.clear_all_raw_items()

            items = data.get('items', [])
            count = 0
            
            # Batch inserts using external cursor
            for item in items:
                self.add_raw_item(
                    item, 
                    external_cursor=cursor
                )
                count += 1
                # Commit every 1000 items to keep transaction log small
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
        """Мягкое массовое удаление элементов."""
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
        """Мягкое удаление продукта и всех его элементов."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Получаем category_id продукта
            cursor.execute("SELECT category_id FROM products WHERE id = ?", (product_id,))
            row = cursor.fetchone()
            if not row: return 0
            
            # Удаляем все элементы этого продукта
            cursor.execute("""
                UPDATE raw_items
                SET is_deleted = 1, deleted_at = ?, original_product_id = product_id
                WHERE product_id = ? AND is_deleted = 0
            """, (now, product_id))
            items_count = cursor.rowcount
            
            # Удаляем сам продукт
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
        """Мягкое удаление категории и всех её продуктов/элементов."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Получаем все продукты категории
            cursor.execute("SELECT id FROM products WHERE category_id = ? AND is_deleted = 0", (category_id,))
            product_ids = [row[0] for row in cursor.fetchall()]
            
            total_items = 0
            for pid in product_ids:
                # Удаляем элементы каждого продукта
                cursor.execute("""
                    UPDATE raw_items
                    SET is_deleted = 1, deleted_at = ?, original_product_id = product_id
                    WHERE product_id = ? AND is_deleted = 0
                """, (now, pid))
                total_items += cursor.rowcount
                
            # Удаляем все продукты категории
            cursor.execute("""
                UPDATE products
                SET is_deleted = 1, deleted_at = ?, original_category_id = category_id
                WHERE category_id = ? AND is_deleted = 0
            """, (now, category_id))
            
            # Удаляем саму категорию
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
        """Восстановление элемента из корзины."""
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
        """Массовое восстановление элементов из корзины."""
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            # Восстанавливаем и возвращаем привязку к оригинальному продукту
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

    #def restore_product(self, product_id: int) -> int:
    #    """Восстановление продукта и всех его элементов."""
    #    conn = self._get_connection()
    #    try:
    #        cursor = conn.cursor()
    #        # Восстанавливаем продукт
    #        cursor.execute("""
    #            UPDATE products
    #            SET is_deleted = 0, deleted_at = NULL, category_id = original_category_id
    #            WHERE id = ? AND is_deleted = 1
    #        """, (product_id,))
    #        
    #        # Восстанавливаем все элементы этого продукта
    #        cursor.execute("""
    #            UPDATE raw_items
    #            SET is_deleted = 0, deleted_at = NULL, product_id = original_product_id
    #            WHERE original_product_id = ? AND is_deleted = 1
    #        """, (product_id,))
    #        
    #        items_count = cursor.rowcount
    #        conn.commit()
    #        self._stats_cache.invalidate()
    #        return items_count
    #    finally:
    #        conn.close()
#
    #def restore_category(self, category_id: int) -> int:
    #    """Восстановление категории и всех её продуктов/элементов."""
    #    conn = self._get_connection()
    #    try:
    #        cursor = conn.cursor()
    #        # Восстанавливаем категорию
    #        cursor.execute("""
    #            UPDATE categories
    #            SET is_deleted = 0, deleted_at = NULL
    #            WHERE id = ? AND is_deleted = 1
    #        """, (category_id,))
    #        
    #        # Получаем все удаленные продукты этой категории
    #        cursor.execute("""
    #            SELECT id FROM products
    #            WHERE original_category_id = ? AND is_deleted = 1
    #        """, (category_id,))
    #        product_ids = [row[0] for row in cursor.fetchall()]
    #        
    #        total_items = 0
    #        for pid in product_ids:
    #            # Восстанавливаем продукт
    #            cursor.execute("""
    #                UPDATE products
    #                SET is_deleted = 0, deleted_at = NULL, category_id = original_category_id
    #                WHERE id = ?
    #            """, (pid,))
    #            
    #            # Восстанавливаем элементы
    #            cursor.execute("""
    #                UPDATE raw_items
    #                SET is_deleted = 0, deleted_at = NULL, product_id = original_product_id
    #                WHERE original_product_id = ? AND is_deleted = 1
    #            """, (pid,))
    #            total_items += cursor.rowcount
    #            
    #        conn.commit()
    #        self._stats_cache.invalidate()
    #        return total_items
    #    finally:
    #        conn.close()

    def permanent_delete_item(self, item_id: int) -> bool:
        """Окончательное удаление элемента."""
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
        """Окончательное массовое удаление элементов из корзины."""
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
        """Получить все элементы из корзины."""
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
        """Переместить один элемент."""
        return self.move_items_to_product([item_id], target_product_id) > 0

    def move_items_to_product(self, item_ids: List[int], target_product_id: int) -> int:
        """Массовое перемещение элементов (автоматически восстанавливает из корзины)."""
        if not item_ids: return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            
            cursor.execute("SELECT id FROM products WHERE id = ?", (target_product_id,))
            if not cursor.fetchone():
                return 0
            
            # Обновляем product_id И сбрасываем флаг удаления
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
        """
        Manually update placement_confidence flag for a single item.

        Args:
            item_id: Item ID
            is_reliable: True for reliable, False for unreliable

        Returns:
            True if updated successfully
        """
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
        """
        Recalculate placement_confidence for an item based on its semantic data.

        Uses evaluate_item_placement() function from memory.py to determine
        if the item is correctly placed in its current category/product.

        Args:
            item_id: Item ID to recalculate

        Returns:
            True if recalculation succeeded
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Fetch item data with product and category info
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

            # Update database
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
        """
        Bulk recalculate placement_confidence for multiple items.

        Args:
            item_ids: List of item IDs

        Returns:
            Number of successfully recalculated items
        """
        count = 0
        for item_id in item_ids:
            if self.recalculate_placement_confidence(item_id):
                count += 1
        return count

    def empty_trash(self) -> int:
        """Полная очистка корзины."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Удаляем элементы
            cursor.execute("DELETE FROM raw_items WHERE is_deleted = 1")
            items_deleted = cursor.rowcount
            
            # Удаляем продукты
            cursor.execute("DELETE FROM products WHERE is_deleted = 1")
            
            # Удаляем категории
            cursor.execute("DELETE FROM categories WHERE is_deleted = 1")
            
            conn.commit()
            self._stats_cache.invalidate()
            return items_deleted
        finally:
            conn.close()