import sqlite3
import json
import os
import sys
import hashlib
from typing import List, Dict, Optional
from datetime import datetime

# Add workspace root to path for config imports
_workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from app.config import BASE_APP_DIR
from app.core.log_manager import logger


class RawDataManager:
    """
    Manages raw items data with persistent storage.
    Supports categories, product keys, and many-to-many relationships.
    """

    SCHEMA_VERSION = 2
    DB_FILENAME = "memory_raw_data.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(BASE_APP_DIR, self.DB_FILENAME)
        self._ensure_db_exists()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_db_exists(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Check if schema_version table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            if cursor.fetchone() is None:
                # Fresh database - create schema_version and all tables
                logger.info("Creating fresh database schema")
                cursor.execute("""
                    CREATE TABLE schema_version (
                        version INTEGER PRIMARY KEY DEFAULT 1
                    )
                """)
                cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
                # Create all data tables
                self._create_all_tables(cursor)
                conn.commit()
                return

            # Check version and migrate if needed
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            if current_version < self.SCHEMA_VERSION:
                logger.info(f"Migrating raw_data schema from {current_version} to {self.SCHEMA_VERSION}")
                self._migrate_schema(cursor, current_version, self.SCHEMA_VERSION)
                cursor.execute("UPDATE schema_version SET version = ?", (self.SCHEMA_VERSION,))
            elif current_version == self.SCHEMA_VERSION:
                # Ensure tables exist even at current version
                self._ensure_tables_exist(cursor)

            conn.commit()
        finally:
            conn.close()

    def _ensure_tables_exist(self, cursor: sqlite3.Cursor):
        """Ensure all data tables exist."""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='categories'")
        if cursor.fetchone() is None:
            self._create_all_tables(cursor)

    def _create_all_tables(self, cursor: sqlite3.Cursor):
        """Create all data tables."""
        # Categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Product keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                display_name TEXT,
                category_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)

        # Raw items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id TEXT UNIQUE NOT NULL,
                title TEXT,
                price INTEGER,
                description TEXT,
                city TEXT,
                condition TEXT,
                seller_id TEXT,
                views INTEGER,
                date_text TEXT,
                link TEXT,
                raw_data TEXT,
                analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Items-Categories junction
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_items_categories (
                raw_item_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY (raw_item_id, category_id),
                FOREIGN KEY (raw_item_id) REFERENCES raw_items(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)

        # Items-Products junction
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_items_products (
                raw_item_id INTEGER NOT NULL,
                product_key_id INTEGER NOT NULL,
                PRIMARY KEY (raw_item_id, product_key_id),
                FOREIGN KEY (raw_item_id) REFERENCES raw_items(id) ON DELETE CASCADE,
                FOREIGN KEY (product_key_id) REFERENCES product_keys(id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_ad_id ON raw_items(ad_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_price ON raw_items(price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_analyzed ON raw_items(analyzed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_keys_key ON product_keys(key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name)")

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int, to_version: int):
        """Execute schema migrations."""
        if from_version < 2:
            # Create all tables for version 2
            self._create_all_tables(cursor)

    # === Categories ===

    def get_or_create_category(self, name: str, cursor: sqlite3.Cursor = None) -> int:
        """Get category id by name, creating if doesn't exist."""
        own_cursor = cursor is None
        conn = None
        try:
            if own_cursor:
                conn = self._get_connection()
                cursor = conn.cursor()
            cursor.execute("SELECT id FROM categories WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row[0]
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            if own_cursor:
                conn.commit()
            return cursor.lastrowid
        finally:
            if own_cursor and conn:
                conn.close()

    def get_all_categories(self) -> List[Dict]:
        """Get all categories with counts."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    c.id,
                    c.name,
                    c.created_at,
                    COUNT(DISTINCT rip.raw_item_id) as item_count
                FROM categories c
                LEFT JOIN raw_items_categories ric ON c.id = ric.category_id
                LEFT JOIN raw_items_products rip ON ric.raw_item_id = rip.raw_item_id
                GROUP BY c.id
                ORDER BY c.name
            """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_category(self, category_id: int) -> bool:
        """Delete category by id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # === Product Keys ===

    def get_or_create_product_key(self, key: str, display_name: Optional[str] = None,
                                   category_id: Optional[int] = None,
                                   cursor: sqlite3.Cursor = None) -> int:
        """Get product key id, creating if doesn't exist."""
        own_cursor = cursor is None
        conn = None
        try:
            if own_cursor:
                conn = self._get_connection()
                cursor = conn.cursor()
            cursor.execute("SELECT id, display_name, category_id FROM product_keys WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                # Update display_name or category if provided
                if display_name or category_id:
                    update_fields = []
                    params = []
                    if display_name is not None:
                        update_fields.append("display_name = ?")
                        params.append(display_name)
                    if category_id is not None:
                        update_fields.append("category_id = ?")
                        params.append(category_id)
                    params.append(row[0])
                    cursor.execute(f"UPDATE product_keys SET {', '.join(update_fields)} WHERE id = ?", params)
                    if own_cursor:
                        conn.commit()
                return row[0]
            cursor.execute(
                "INSERT INTO product_keys (key, display_name, category_id) VALUES (?, ?, ?)",
                (key, display_name, category_id)
            )
            if own_cursor:
                conn.commit()
            return cursor.lastrowid
        finally:
            if own_cursor and conn:
                conn.close()

    def get_all_product_keys(self, category_id: Optional[int] = None) -> List[Dict]:
        """Get all product keys with optional category filter."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if category_id:
                cursor.execute("""
                    SELECT
                        pk.id,
                        pk.key,
                        pk.display_name,
                        pk.category_id,
                        c.name as category_name,
                        pk.created_at,
                        COUNT(DISTINCT rip.raw_item_id) as item_count
                    FROM product_keys pk
                    LEFT JOIN categories c ON pk.category_id = c.id
                    LEFT JOIN raw_items_products rip ON pk.id = rip.product_key_id
                    WHERE pk.category_id = ?
                    GROUP BY pk.id
                    ORDER BY pk.key
                """, (category_id,))
            else:
                cursor.execute("""
                    SELECT
                        pk.id,
                        pk.key,
                        pk.display_name,
                        pk.category_id,
                        c.name as category_name,
                        pk.created_at,
                        COUNT(DISTINCT rip.raw_item_id) as item_count
                    FROM product_keys pk
                    LEFT JOIN categories c ON pk.category_id = c.id
                    LEFT JOIN raw_items_products rip ON pk.id = rip.product_key_id
                    GROUP BY pk.id
                    ORDER BY pk.key
                """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_product_key(self, product_key_id: int) -> bool:
        """Delete product key by id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM product_keys WHERE id = ?", (product_key_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # === Raw Items ===

    def add_raw_item(self, item: Dict, categories: Optional[List[str]] = None,
                     product_keys: Optional[List[str]] = None) -> str:
        """
        Возвращает статус операции: 'created', 'updated', 'skipped'
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 1. Мягкая генерация ID (Hash fallback)
            ad_id = str(item.get('id') or item.get('ad_id') or self._extract_ad_id(item.get('link', '')) or "")
            
            if not ad_id:
                # Генерируем ID из заголовка и продавца, если нет явного ID
                unique_str = f"{item.get('title')}_{item.get('seller_id')}_{item.get('city')}"
                ad_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()

            # 2. Проверка существования
            cursor.execute("SELECT id, price, views FROM raw_items WHERE ad_id = ?", (ad_id,))
            existing = cursor.fetchone()
            
            current_price = item.get('price', 0)
            current_views = item.get('views', 0)
            
            raw_item_id = None
            status = "skipped"

            if existing:
                # LOGIC: Обновляем только если изменилась цена или просмотры, или прошло время
                raw_item_id = existing[0]
                old_price = existing[1]
                
                # Обновляем, если есть новые данные
                if (current_price > 0 and current_price != old_price) or (current_views > 0):
                    raw_data_json = json.dumps(item, ensure_ascii=False)
                    cursor.execute("""
                        UPDATE raw_items SET
                            price = ?, views = ?, raw_data = ?, analyzed_at = ?
                        WHERE id = ?
                    """, (
                        current_price,
                        current_views,
                        raw_data_json,
                        datetime.now().isoformat(),
                        raw_item_id
                    ))
                    status = "updated"
            else:
                # INSERT
                raw_data_json = json.dumps(item, ensure_ascii=False)
                cursor.execute("""
                    INSERT INTO raw_items (
                        ad_id, title, price, description, city, condition,
                        seller_id, views, date_text, link, raw_data, analyzed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ad_id,
                    item.get('title'),
                    item.get('price'),
                    item.get('description'),
                    item.get('city'),
                    item.get('condition'),
                    item.get('seller_id'),
                    item.get('views'),
                    item.get('date_text'),
                    item.get('link'),
                    raw_data_json,
                    datetime.now().isoformat()
                ))
                raw_item_id = cursor.lastrowid
                status = "created"

            # 3. Обновление связей (Categories / Product Keys)
            if raw_item_id:
                if categories:
                    for cat_name in categories:
                        cat_id = self.get_or_create_category(cat_name, cursor)
                        cursor.execute("INSERT OR IGNORE INTO raw_items_categories (raw_item_id, category_id) VALUES (?, ?)", (raw_item_id, cat_id))

                if product_keys:
                    for pk in product_keys:
                        pk_id = self.get_or_create_product_key(pk, cursor=cursor)
                        cursor.execute("INSERT OR IGNORE INTO raw_items_products (raw_item_id, product_key_id) VALUES (?, ?)", (raw_item_id, pk_id))

            conn.commit()
            return status # Возвращаем статус вместо ID, чтобы понимать результат
        except Exception as e:
            logger.error(f"DB Error in add_raw_item: {e}")
            return "error"
        finally:
            conn.close()

    def _extract_ad_id(self, link: str) -> Optional[str]:
        """Extract ad_id from Avito URL."""
        if not link:
            return None
        import re
        match = re.search(r'/(\d+)(?:\?|$)', link)
        return match.group(1) if match else None

    def _update_raw_item(self, cursor: sqlite3.Cursor, item_id: int, item: Dict):
        """Update existing raw item."""
        raw_data_json = json.dumps(item, ensure_ascii=False)
        cursor.execute("""
            UPDATE raw_items SET
                title = ?, price = ?, description = ?, city = ?, condition = ?,
                seller_id = ?, views = ?, date_text = ?, link = ?, raw_data = ?,
                analyzed_at = ?
            WHERE id = ?
        """, (
            item.get('title'),
            item.get('price'),
            item.get('description'),
            item.get('city'),
            item.get('condition'),
            item.get('seller_id'),
            item.get('views'),
            item.get('date_text'),
            item.get('link'),
            raw_data_json,
            datetime.now().isoformat(),
            item_id
        ))

    def get_items(self, limit: int = 100000) -> List[Dict]:
        """Get all raw items with optional limit."""
        return self.get_raw_items(limit=limit)

    def get_raw_items(self, category: Optional[str] = None,
                      product_key: Optional[str] = None,
                      search_query: Optional[str] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[Dict]:
        """Get raw items with filtering and pagination."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = """
                SELECT DISTINCT
                    ri.id, ri.ad_id, ri.title, ri.price, ri.description, ri.city,
                    ri.condition, ri.seller_id, ri.views, ri.date_text, ri.link,
                    ri.analyzed_at, ri.created_at
                FROM raw_items ri
                LEFT JOIN raw_items_categories ric ON ri.id = ric.raw_item_id
                LEFT JOIN categories c ON ric.category_id = c.id
                LEFT JOIN raw_items_products rip ON ri.id = rip.raw_item_id
                LEFT JOIN product_keys pk ON rip.product_key_id = pk.id
                WHERE 1=1
            """
            params = []

            if category:
                query += " AND c.name = ?"
                params.append(category)

            if product_key:
                query += " AND pk.key = ?"
                params.append(product_key)

            if search_query:
                query += " AND (ri.title LIKE ? OR ri.description LIKE ? OR ri.city LIKE ?)"
                search_term = f"%{search_query}%"
                params.extend([search_term, search_term, search_term])

            query += " ORDER BY ri.analyzed_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [self._item_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _item_from_row(self, row: sqlite3.Row) -> Dict:
        """Convert row to item dict."""
        item = dict(row)
        # Parse categories
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.name FROM categories c
                JOIN raw_items_categories ric ON c.id = ric.category_id
                WHERE ric.raw_item_id = ?
            """, (item['id'],))
            item['categories'] = [r[0] for r in cursor.fetchall()]
            # Parse product keys
            cursor.execute("""
                SELECT pk.key FROM product_keys pk
                JOIN raw_items_products rip ON pk.id = rip.product_key_id
                WHERE rip.raw_item_id = ?
            """, (item['id'],))
            item['product_keys'] = [r[0] for r in cursor.fetchall()]
        finally:
            conn.close()
        return item

    def get_raw_items_count(self, category: Optional[str] = None,
                            product_key: Optional[str] = None) -> int:
        """Get count of raw items with filters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = """
                SELECT COUNT(DISTINCT ri.id)
                FROM raw_items ri
                LEFT JOIN raw_items_categories ric ON ri.id = ric.raw_item_id
                LEFT JOIN categories c ON ric.category_id = c.id
                LEFT JOIN raw_items_products rip ON ri.id = rip.raw_item_id
                LEFT JOIN product_keys pk ON rip.product_key_id = pk.id
                WHERE 1=1
            """
            params = []

            if category:
                query += " AND c.name = ?"
                params.append(category)

            if product_key:
                query += " AND pk.key = ?"
                params.append(product_key)

            cursor.execute(query, params)
            return cursor.fetchone()[0] or 0
        finally:
            conn.close()

    def get_raw_item_by_id(self, item_id: int) -> Optional[Dict]:
        """Get single raw item by id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return self._item_from_row(row) if row else None
        finally:
            conn.close()

    def delete_raw_items(self, item_ids: List[int]) -> int:
        """Delete items by ids. Returns count of deleted items."""
        if not item_ids:
            return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            cursor.execute(f"DELETE FROM raw_items WHERE id IN ({placeholders})", item_ids)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def clear_all_raw_items(self) -> int:
        """Clear all raw items. Returns count of deleted items."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_items")
            count = cursor.fetchone()[0] or 0
            cursor.execute("DELETE FROM raw_items")
            conn.commit()
            return count
        finally:
            conn.close()

    # === Product Key Relations ===

    def get_items_for_product_key(self, product_key: str) -> List[Dict]:
        """Get all items for a specific product key."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT
                    ri.id, ri.ad_id, ri.title, ri.price, ri.description, ri.city,
                    ri.condition, ri.seller_id, ri.views, ri.date_text, ri.link,
                    ri.analyzed_at, ri.created_at
                FROM raw_items ri
                JOIN raw_items_products rip ON ri.id = rip.raw_item_id
                JOIN product_keys pk ON rip.product_key_id = pk.id
                WHERE pk.key = ?
                ORDER BY ri.analyzed_at DESC
            """, (product_key,))
            return [self._item_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # === Statistics ===

    def get_statistics(self) -> Dict:
        """Get overall statistics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM raw_items")
            total_items = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM categories")
            total_categories = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM product_keys")
            total_product_keys = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(price) FROM raw_items WHERE price > 0")
            avg_price = cursor.fetchone()[0] or 0

            return {
                'total_items': total_items,
                'total_categories': total_categories,
                'total_product_keys': total_product_keys,
                'avg_price': round(avg_price, 2) if avg_price else 0
            }
        finally:
            conn.close()

    # === Export/Import ===

    def export_to_json(self, filepath: str):
        """Export entire database to JSON."""
        data = {
            'exported_at': datetime.now().isoformat(),
            'schema_version': self.SCHEMA_VERSION,
            'categories': self.get_all_categories(),
            'product_keys': self.get_all_product_keys(),
            'items': self.get_raw_items(limit=999999)
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.success(f"Exported {data['items']} items to {filepath}")

    def import_from_json(self, filepath: str, clear_first: bool = False):
        """Import database from JSON."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if clear_first:
                cursor.execute("DELETE FROM raw_items_categories")
                cursor.execute("DELETE FROM raw_items_products")
                cursor.execute("DELETE FROM raw_items")
                cursor.execute("DELETE FROM product_keys")
                cursor.execute("DELETE FROM categories")

            # Import categories
            for cat in data.get('categories', []):
                cursor.execute(
                    "INSERT OR IGNORE INTO categories (id, name, created_at) VALUES (?, ?, ?)",
                    (cat['id'], cat['name'], cat.get('created_at'))
                )

            # Import product keys
            for pk in data.get('product_keys', []):
                cursor.execute(
                    "INSERT OR IGNORE INTO product_keys (id, key, display_name, category_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (pk['id'], pk['key'], pk.get('display_name'), pk.get('category_id'), pk.get('created_at'))
                )

            # Import items
            for item in data.get('items', []):
                ad_id = item.get('ad_id')
                if not ad_id:
                    continue
                raw_data = json.dumps(item, ensure_ascii=False)
                cursor.execute("""
                    INSERT OR IGNORE INTO raw_items (
                        id, ad_id, title, price, description, city, condition,
                        seller_id, views, date_text, link, raw_data, analyzed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get('id'), ad_id, item.get('title'), item.get('price'),
                    item.get('description'), item.get('city'), item.get('condition'),
                    item.get('seller_id'), item.get('views'), item.get('date_text'),
                    item.get('link'), raw_data, item.get('analyzed_at'), item.get('created_at')
                ))

            conn.commit()
            logger.success(f"Imported {len(data.get('items', []))} items from {filepath}")
        finally:
            conn.close()

    # === Reset ===

    def reset_database(self):
        """Completely reset the database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._ensure_db_exists()
        logger.info("Raw data database reset complete")