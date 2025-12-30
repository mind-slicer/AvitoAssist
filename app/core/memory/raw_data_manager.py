import sqlite3
import json
import os
import re
import hashlib
import time
from typing import List, Dict, Optional
from datetime import datetime
from collections import Counter
from dataclasses import dataclass

from app.config import BASE_APP_DIR
from app.core.log_manager import logger


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
    SCHEMA_VERSION = 5
    DB_FILENAME = "memory_raw_data.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(BASE_APP_DIR, self.DB_FILENAME)
        self._stats_cache = StatisticsCache(ttl_seconds=60)
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
        return conn

    def _ensure_db_exists(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            if cursor.fetchone() is None:
                logger.info("Creating fresh PURE v5 database schema")
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
        # Performance Indexes v5
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_price_city ON raw_items(price, city_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_analyzed_price ON raw_items(analyzed_at, price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_product_id ON raw_items(product_id)")

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int, to_version: int):
        if from_version < 2:
            self._create_all_tables(cursor)
        if from_version < 3:
            cursor.execute("CREATE TABLE IF NOT EXISTS user_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, action_type TEXT, details TEXT, created_at TEXT)")
        if from_version < 4:
            self._create_all_tables(cursor)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='product_keys'")
            if cursor.fetchone():
                cursor.execute("ALTER TABLE product_keys RENAME TO products")
                try: cursor.execute("ALTER TABLE products ADD COLUMN brand TEXT")
                except: pass
                try: cursor.execute("ALTER TABLE products ADD COLUMN model TEXT")
                except: pass
            try: cursor.execute("ALTER TABLE raw_items ADD COLUMN city_id INTEGER REFERENCES cities(id)")
            except: pass
            try: cursor.execute("ALTER TABLE raw_items ADD COLUMN seller_table_id INTEGER REFERENCES sellers(id)")
            except: pass
            try: cursor.execute("ALTER TABLE raw_items ADD COLUMN product_id INTEGER REFERENCES products(id)")
            except: pass
            try:
                cursor.execute("INSERT OR IGNORE INTO cities (name) SELECT DISTINCT city FROM raw_items WHERE city IS NOT NULL AND city != ''")
                cursor.execute("UPDATE raw_items SET city_id = (SELECT id FROM cities WHERE cities.name = raw_items.city) WHERE city_id IS NULL")
                cursor.execute("INSERT OR IGNORE INTO sellers (seller_link_id) SELECT DISTINCT seller_id FROM raw_items WHERE seller_id IS NOT NULL AND seller_id != ''")
                cursor.execute("UPDATE raw_items SET seller_table_id = (SELECT id FROM sellers WHERE sellers.seller_link_id = raw_items.seller_id) WHERE seller_table_id IS NULL")
            except Exception: pass
        if from_version < 5:
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_price_city ON raw_items(price, city_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_analyzed_price ON raw_items(analyzed_at, price)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_product_id ON raw_items(product_id)")
            except Exception: pass

    def get_or_create_city(self, name: str, cursor: sqlite3.Cursor) -> int:
        if not name: return None
        clean_name = name.strip()
        cursor.execute("SELECT id FROM cities WHERE name = ?", (clean_name,))
        row = cursor.fetchone()
        if row: return row[0]
        cursor.execute("INSERT INTO cities (name) VALUES (?)", (clean_name,))
        return cursor.lastrowid

    def get_or_create_seller(self, seller_id_str: str, cursor: sqlite3.Cursor) -> int:
        if not seller_id_str: return None
        clean_id = seller_id_str.strip()
        cursor.execute("SELECT id FROM sellers WHERE seller_link_id = ?", (clean_id,))
        row = cursor.fetchone()
        if row: return row[0]
        cursor.execute("INSERT INTO sellers (seller_link_id) VALUES (?)", (clean_id,))
        return cursor.lastrowid

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

    def add_raw_item(self, item: Dict, categories: Optional[List[str]] = None,
                     product_keys: Optional[List[str]] = None,
                     external_cursor: sqlite3.Cursor = None) -> AddItemResult:
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

            city_id = self.get_or_create_city(city_str, cursor)
            seller_db_id = self.get_or_create_seller(seller_str, cursor)
            product_id = None

            # Resolve Product & Category
            semantic = item.get('semantic_data')
            if semantic and semantic.get('product_key'):
                p_key = semantic['product_key']
                cat_name = semantic.get('category', 'MISC')
                brand = semantic.get('brand')
                model = semantic.get('model')
                clean_name = semantic.get('clean_name')

                cursor.execute("SELECT id FROM products WHERE key = ?", (p_key,))
                p_row = cursor.fetchone()
                if p_row:
                    product_id = p_row[0]
                else:
                    cat_id = self.get_or_create_category(cat_name, cursor)
                    cursor.execute("""
                        INSERT INTO products (key, display_name, brand, model, category_id)
                        VALUES (?, ?, ?, ?, ?)
                    """, (p_key, clean_name, brand, model, cat_id))
                    product_id = cursor.lastrowid

            elif product_keys and len(product_keys) > 0:
                p_key = product_keys[0]
                cat_name = categories[0] if categories else 'MISC'
                cursor.execute("SELECT id FROM products WHERE key = ?", (p_key,))
                p_row = cursor.fetchone()
                if p_row:
                    product_id = p_row[0]
                else:
                    cat_id = self.get_or_create_category(cat_name, cursor)
                    cursor.execute("INSERT INTO products (key, category_id) VALUES (?, ?)", (p_key, cat_id))
                    product_id = cursor.lastrowid

            # Check existing item
            cursor.execute("""
                SELECT id, price, views, title, description, condition, city_id, product_id 
                FROM raw_items WHERE ad_id = ?
            """, (ad_id,))
            existing = cursor.fetchone()

            raw_data_json = json.dumps(item, ensure_ascii=False)
            current_time = datetime.now().isoformat()

            if existing:
                raw_item_id = existing[0]
                old_price = existing[1]
                
                # Check what changed
                old_views = existing[2] or 0
                new_views = item.get('views', 0)
                
                # Loose check for content changes to avoid unnecessary writes
                has_content_change = (
                    existing[3] != title or
                    existing[5] != item.get('condition') or
                    existing[6] != city_id or
                    existing[7] != product_id
                )
                
                price_changed = (old_price != price and price > 0)
                
                # Update if significant changes found
                if price_changed or new_views != old_views or has_content_change:
                    if price_changed:
                        cursor.execute("""
                            INSERT INTO price_history (raw_item_id, price, recorded_at)
                            VALUES (?, ?, ?)
                        """, (raw_item_id, old_price, current_time))

                    cursor.execute("""
                        UPDATE raw_items SET
                            price = ?, views = ?, raw_data = ?, analyzed_at = ?,
                            city_id = ?, seller_table_id = ?, product_id = ?,
                            title = ?, description = ?, condition = ?, date_text = ?, link = ?
                        WHERE id = ?
                    """, (
                        price, new_views, raw_data_json, current_time,
                        city_id, seller_db_id, product_id,
                        title, item.get('description'), item.get('condition'), 
                        item.get('date_text'), item.get('link'),
                        raw_item_id
                    ))
                    
                    status = "updated"
                else:
                    status = "skipped"
                    
                result = AddItemResult(raw_item_id, status, price_changed)

            else:
                cursor.execute("""
                    INSERT INTO raw_items (
                        ad_id, title, price, description, condition,
                        views, date_text, link, raw_data, analyzed_at,
                        city_id, seller_table_id, product_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ad_id, title, price, item.get('description'), item.get('condition'),
                    item.get('views'), item.get('date_text'), item.get('link'),
                    raw_data_json, current_time,
                    city_id, seller_db_id, product_id
                ))
                raw_item_id = cursor.lastrowid
                
                if price > 0:
                    cursor.execute("""
                        INSERT INTO price_history (raw_item_id, price, recorded_at)
                        VALUES (?, ?, ?)
                    """, (raw_item_id, price, current_time))
                
                result = AddItemResult(raw_item_id, "created", False)

            if own_connection:
                conn.commit()

            if result.status in ("created", "updated"):
                self._stats_cache.invalidate()

            return result

        except Exception as e:
            logger.error(f"DB Error in add_raw_item: {e}")
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
                    ri.analyzed_at, ri.created_at,
                    prod.key as clean_product_key,
                    prod.brand,
                    prod.model,
                    c.name as category_name

                FROM raw_items ri
                LEFT JOIN cities cit ON ri.city_id = cit.id
                LEFT JOIN sellers sel ON ri.seller_table_id = sel.id
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
                LEFT JOIN raw_items ri ON p.id = ri.product_id
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

    def calculate_data_signature(self, category_key: Optional[str] = None, product_key: Optional[str] = None) -> str:
        """
        Calculates a hash based on CONTENT of items, not just count.
        Using MD5 of (id + price + title + analyzed_at) for items.
        """
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
            
            # Aggregate string for hashing
            content_str = ""
            for r in rows:
                # Basic string concatenation of critical fields
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
                       c.name as category_name
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
                    item.get('categories'), 
                    item.get('product_keys'),
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