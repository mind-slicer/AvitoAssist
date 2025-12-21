# app/core/memory.py
import sqlite3
import os
import threading
import re
import statistics
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from datetime import timedelta

from app.config import BASE_APP_DIR
from app.core.ai.chunk_compression import ChunkCompressor
from app.core.text_utils import FeatureExtractor, TextMatcher
from app.core.log_manager import logger


class MemoryManager:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = os.path.join(BASE_APP_DIR, "data", "memory.db")
        else:
            self.db_path = db_path

        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        self._init_db()
        self._stats_cache = {}

    def __del__(self):
        try:
            if hasattr(self, '_conn'):
                self._conn.close()
        except:
            pass
    
    def _execute(
        self,
        query,
        params=(),
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False,
        return_lastrowid: bool = False,
    ):
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(query, params)

                result = None
                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()

                if commit:
                    self._conn.commit()
                    if return_lastrowid:
                        return cursor.lastrowid

                return result
            except Exception as e:
                logger.error(f"DB Error: {e} | Query: {query}")
                return None

    # ==================== SQLite ====================

    def _init_db(self):
        with self._lock:
            c = self._conn.cursor()
            self._conn.execute("PRAGMA journal_mode=WAL;")

            # --- Таблица сырых товаров (Операционная память) ---
            c.execute("""CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY, avito_id TEXT UNIQUE, title TEXT, price INTEGER, 
                description TEXT, url TEXT, seller TEXT, address TEXT, published_date TEXT, 
                added_at TEXT, verdict TEXT, reason TEXT, market_position TEXT, defects BOOLEAN
            )""")
            
            # --- Статистика (Кэш) ---
            c.execute("""CREATE TABLE IF NOT EXISTS statistics (
                product_key TEXT PRIMARY KEY, avg_price INTEGER, median_price INTEGER, 
                min_price INTEGER, max_price INTEGER, sample_count INTEGER, 
                trend TEXT, trend_percent REAL, last_updated TEXT
            )""")
            
            # --- История трендов ---
            c.execute("""CREATE TABLE IF NOT EXISTS trend_history (
                id INTEGER PRIMARY KEY, product_key TEXT, date TEXT, avg_price INTEGER, sample_count INTEGER
            )""")
            
            # --- Чат ---
            c.execute("""CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
            
            # --- Концептуальная память (Legacy) ---
            c.execute("""CREATE TABLE IF NOT EXISTS ai_knowledge (
                product_key TEXT PRIMARY KEY,
                summary TEXT,
                risk_factors TEXT,
                price_range_notes TEXT,
                last_updated TEXT
            )""")

            # --- ТИПИЗИРОВАННЫЕ ЧАНКИ ПАМЯТИ v2 ---
            # Исправлено: UNIQUE constraint перенесен в конец
            c.execute("""
                CREATE TABLE IF NOT EXISTS aiknowledge_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    chunk_type TEXT NOT NULL,
                    chunk_key TEXT NOT NULL,
                    
                    status TEXT DEFAULT 'PENDING',
                    progress_percent INTEGER DEFAULT 0,
                    title TEXT,

                    content TEXT,
                    summary TEXT,
                    compressed_content TEXT,

                    content_hash TEXT,
                    original_size INTEGER,
                    compressed_size INTEGER,

                    created_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    last_cultivation_attempt TEXT,

                    data_added_since_attempt TEXT,
                    new_data_items_count INTEGER DEFAULT 0,
                    llm_confidence REAL,

                    user_locked BOOLEAN DEFAULT 0,
                    system_critical BOOLEAN DEFAULT 0,

                    depends_on_chunks TEXT,
                    version INTEGER DEFAULT 1,
                    
                    UNIQUE(chunk_type, chunk_key)
                )
            """)

            # --- История версий чанков ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS aiknowledge_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER NOT NULL,
                    version INTEGER,
                    content TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chunk_id) REFERENCES aiknowledge_v2(id)
                )
            """)

            # --- Лог попыток культивации ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS cultivation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER NOT NULL,
                    attempt_time TEXT NOT NULL,
                    status TEXT,
                    items_processed INTEGER,
                    data_points_analyzed INTEGER,
                    llm_time_ms INTEGER,
                    error_msg TEXT,
                    FOREIGN KEY(chunk_id) REFERENCES aiknowledge_v2(id)
                )
            """)

            # --- Отслеживание изменений исходных данных ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS data_change_tracker (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT,
                    category_key TEXT,
                    change_type TEXT,
                    changed_at TEXT NOT NULL,
                    processed_in_chunk_id INTEGER,
                    FOREIGN KEY(processed_in_chunk_id) REFERENCES aiknowledge_v2(id)
                )
            """)

            c.execute("ALTER TABLE aiknowledge_v2 ADD COLUMN retry_count INTEGER DEFAULT 0")

            self._conn.commit()

    # --- Knowledge Methods (Legacy + v2) ---

    def add_knowledge(self, product_key: str, summary: str, risks: str, prices: str):
        now = datetime.now().isoformat()
        self._execute("""
            INSERT OR REPLACE INTO ai_knowledge (product_key, summary, risk_factors, price_range_notes, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (product_key, summary, risks, prices, now), commit=True)

    def get_knowledge(self, product_key: str) -> Optional[Dict]:
        row = self._execute("SELECT * FROM ai_knowledge WHERE product_key = ?", (product_key,), fetch_one=True)
        return dict(row) if row else None
    
    def get_all_knowledge_summaries(self) -> List[Dict]:
        rows = self._execute("SELECT product_key, summary, last_updated FROM ai_knowledge ORDER BY last_updated DESC", fetch_all=True)
        return [dict(r) for r in rows] if rows else []

    def delete_knowledge(self, product_key: str):
        self._execute("DELETE FROM ai_knowledge WHERE product_key = ?", (product_key,), commit=True)
        self._execute("DELETE FROM statistics WHERE product_key = ?", (product_key,), commit=True)

    # --- v2 Methods ---

    def add_knowledge_v2(
        self,
        chunk_type: str,
        chunk_key: str,
        title: str,
        status: str = "PENDING",
        content: Optional[dict] = None,
    ) -> int:
        now = datetime.now().isoformat()
        content_str = None
        content_hash = None
        original_size = None

        if content is not None:
            content_str = json.dumps(content, ensure_ascii=False)
            content_hash = hashlib.md5(content_str.encode()).hexdigest()
            original_size = len(content_str.encode())

        chunk_id = self._execute(
            """
            INSERT INTO aiknowledge_v2
                (chunk_type, chunk_key, title, status,
                 content, content_hash, original_size,
                 created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_type, chunk_key, title, status,
             content_str, content_hash, original_size,
             now, now),
            commit=True,
            return_lastrowid=True,
        )
        return int(chunk_id) if chunk_id is not None else -1

    def get_chunk_by_id(self, chunk_id: int) -> Optional[Dict]:
        row = self._execute(
            "SELECT * FROM aiknowledge_v2 WHERE id = ?",
            (chunk_id,),
            fetch_one=True,
        )
        return dict(row) if row else None

    def get_chunk_by_key(self, chunk_type: str, chunk_key: str) -> Optional[Dict]:
        row = self._execute(
            "SELECT * FROM aiknowledge_v2 WHERE chunk_type = ? AND chunk_key = ?",
            (chunk_type, chunk_key),
            fetch_one=True,
        )
        return dict(row) if row else None

    def get_all_chunks(self) -> List[Dict]:
        rows = self._execute(
            "SELECT * FROM aiknowledge_v2 ORDER BY created_at DESC",
            fetch_all=True,
        )
        return [dict(r) for r in rows] if rows else []

    def get_pending_chunks(self) -> List[Dict]:
        rows = self._execute(
            """
            SELECT * FROM aiknowledge_v2
            WHERE status = 'PENDING'
            ORDER BY created_at ASC
            """,
            fetch_all=True,
        )
        return [dict(r) for r in rows] if rows else []

    def update_chunk_status(self, chunk_id: int, new_status: str, progress: Optional[int] = None):
        now = datetime.now().isoformat()
        if progress is not None:
            self._execute(
                """
                UPDATE aiknowledge_v2
                SET status = ?, progress_percent = ?, last_updated = ?
                WHERE id = ?
                """,
                (new_status, int(progress), now, chunk_id),
                commit=True,
            )
        else:
            self._execute(
                """
                UPDATE aiknowledge_v2
                SET status = ?, last_updated = ?
                WHERE id = ?
                """,
                (new_status, now, chunk_id),
                commit=True,
            )

    def update_chunk_content(self, chunk_id: int, content: dict, summary: Optional[str] = None):
        content_str = json.dumps(content, ensure_ascii=False)
        content_hash = hashlib.md5(content_str.encode()).hexdigest()
        original_size = len(content_str.encode())
        now = datetime.now().isoformat()

        self._execute(
            """
            UPDATE aiknowledge_v2
            SET content = ?, content_hash = ?, original_size = ?,
                summary = COALESCE(?, summary),
                last_updated = ?, status = 'READY', progress_percent = 100
            WHERE id = ?
            """,
            (content_str, content_hash, original_size,
             summary, now, chunk_id),
            commit=True,
        )

    def delete_chunk(self, chunk_id: int):
        self._execute(
            "DELETE FROM aiknowledge_v2 WHERE id = ?",
            (chunk_id,),
            commit=True,
        )

    # ==================== Items & Stats ====================

    def add_item(self, item: dict):
        if self._execute("SELECT 1 FROM items WHERE avito_id = ?", (str(item.get('id')),), fetch_one=True):
            return False
        self._execute("""
            INSERT INTO items (avito_id, title, price, description, url, seller, address, published_date, added_at, verdict, reason, market_position, defects)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(item.get('id')), item.get('title'), item.get('price'), item.get('description'), item.get('link'), item.get('seller'), 
              item.get('address'), item.get('date'), datetime.now().isoformat(), item.get('verdict'), item.get('reason'), 
              item.get('market_position'), item.get('defects')), commit=True)
        return True

    def find_similar_items(self, title: str, limit: int = 20) -> List[Dict]:
        clean = re.sub(r'\b(продам|куплю|торг|новый|бу|цена)\b', '', title.lower(), flags=re.I)
        kws = [w for w in clean.split() if len(w) > 2][:4]
        if not kws: return []
        q = " OR ".join(["title LIKE ?"] * len(kws))
        p = [f"%{k}%" for k in kws]
        p.append(limit)
        rows = self._execute(f"SELECT * FROM items WHERE ({q}) ORDER BY added_at DESC LIMIT ?", tuple(p), fetch_all=True)
        return [dict(r) for r in rows] if rows else []

    def get_rag_context_for_item(self, title: str, days_back: int = 30) -> Optional[Dict]:
        # 1. Сначала ищем сырую статистику
        stats = None
        items = self.find_similar_items(title, 30)
        if items:
            prices = [i['price'] for i in items if i['price']]
            if prices:
                stats = {
                    'median_price': int(statistics.median(prices)),
                    'avg_price': int(statistics.mean(prices)),
                    'min_price': min(prices),
                    'max_price': max(prices),
                    'trend': 'stable', 
                    'sample_count': len(prices)
                }
        
        if not stats: return None
        
        # 2. Теперь ищем УМНЫЙ чанк в новой таблице aiknowledge_v2
        # Генерируем ключ так же, как SmartChunkDetector
        key = self._generate_product_key(title) 
        
        # Ищем готовый PRODUCT чанк
        chunk = self.get_chunk_by_key('PRODUCT', key)
        knowledge_text = ""
        
        if chunk and chunk.get('status') == 'READY':
            # Чанк найден! Извлекаем summary
            if chunk.get('summary'):
                knowledge_text = chunk['summary']
            elif chunk.get('content'):
                try:
                    data = json.loads(chunk['content'])
                    knowledge_text = data.get('summary') or data.get('analysis', {}).get('summary', '')
                except: pass
        
        context = stats.copy()
        if knowledge_text:
            context['knowledge'] = knowledge_text
        else:
            context['knowledge'] = "Нет детального AI-анализа в памяти."
            
        return context

    def _calculate_trend(self, items: List[Dict]) -> tuple[str, float]:
        if len(items) < 3:
            return ("stable", 0.0)
        try:
            sorted_items = sorted(items, key=lambda x: x.get('added_at', ''))
            third = len(sorted_items) // 3
            early = sorted_items[:third]
            late = sorted_items[-third:]
            early_prices = [i['price'] for i in early if i.get('price')]
            late_prices = [i['price'] for i in late if i.get('price')]
            if not early_prices or not late_prices: return ("stable", 0.0)
            avg_early = statistics.mean(early_prices)
            avg_late = statistics.mean(late_prices)
            percent_change = ((avg_late - avg_early) / avg_early) * 100
            if avg_late > avg_early * 1.1: return ("up", percent_change)
            elif avg_late < avg_early * 0.9: return ("down", percent_change)
            else: return ("stable", percent_change)
        except:
            return ("stable", 0.0)

    def _generate_product_key(self, title: str) -> str:
        clean = re.sub(r'\b(продам|куплю|торг)\b', '', title.lower(), flags=re.I)
        return " ".join(clean.split()[:3])

    def _get_cached_stats(self, key):
        row = self._execute("SELECT * FROM statistics WHERE product_key=?", (key,), fetch_one=True)
        return dict(row) if row else None

    def _cache_stats(self, product_key: str, context: Dict):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO statistics
                    (product_key, avg_price, median_price, min_price, max_price,
                     sample_count, trend, trend_percent, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_key,
                    context['avg_price'],
                    context['median_price'],
                    context['min_price'],
                    context['max_price'],
                    context['sample_count'],
                    context['trend'],
                    context.get('trend_percent', 0.0),
                    now_str
                ))
                cursor.execute("""
                    INSERT OR REPLACE INTO trend_history
                    (product_key, date, avg_price, sample_count)
                    VALUES (?, ?, ?, ?)
                """, (product_key, date_str, context['avg_price'], context['sample_count']))
                self._conn.commit()
            except Exception as e:
                logger.error(f"Cache write error: {e}")

    def rebuild_statistics_cache(self) -> int:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute("SELECT DISTINCT title FROM items")
            titles = [row['title'] for row in c.fetchall()]
            conn.close()
            
            if not titles:
                return 0
            
            product_keys = set()
            for title in titles:
                pk = self._generate_product_key(title)
                if pk:
                    product_keys.add(pk)
            
            rebuilt = 0
            for pk in product_keys:
                keywords = pk.split()
                if not keywords: continue
                
                temp_title = " ".join(keywords)
                similar = self.find_similar_items(temp_title, limit=100)
                
                if len(similar) < 2: continue
                
                prices = [item['price'] for item in similar if item.get('price')]
                if not prices: continue
                
                trend, trend_percent = self._calculate_trend(similar)
                
                context = {
                    'avg_price': int(statistics.mean(prices)),
                    'median_price': int(statistics.median(prices)),
                    'min_price': int(min(prices)),
                    'max_price': int(max(prices)),
                    'sample_count': len(similar),
                    'trend': trend,
                    'trend_percent': round(trend_percent, 1)
                }
                
                self._cache_stats(pk, context)
                rebuilt += 1
            
            return rebuilt
        except Exception as e:
            logger.error(f"Rebuild error: {e}")
            return 0

    def get_all_statistics(self, limit: int = 100) -> List[Dict]:
        rows = self._execute("SELECT * FROM statistics ORDER BY last_updated DESC LIMIT ?", (limit,), fetch_all=True)
        return [dict(r) for r in rows] if rows else []

    def get_stats_for_product_key(self, product_key: str) -> Optional[Dict]:
        row = self._execute("SELECT * FROM statistics WHERE product_key = ?", (product_key,), fetch_one=True)
        return dict(row) if row else None

    def get_stats_for_title(self, title: str) -> Optional[Dict]:
        if not title: return None
        ignore = {'продам', 'куплю', 'новый', 'состояние', 'торг', 'original', 'оригинал', 'комплект', 'полный', 'идеальное', 'отличное'}
        clean_words = [w for w in title.lower().split() if len(w) > 3 and w not in ignore]
        if not clean_words: return None
        keyword = max(clean_words, key=len)

        rows = self._execute("SELECT price FROM items WHERE title LIKE ? AND price > 100", (f"%{keyword}%",), fetch_all=True)
        if not rows: return None
        
        raw_prices = [r['price'] for r in rows if r['price'] is not None]
        if len(raw_prices) < 3: return None

        sorted_prices = sorted(raw_prices)
        return {
            "keyword": keyword,
            "sample_count": len(raw_prices),
            "avg_price": int(statistics.mean(sorted_prices)),
            "median_price": int(statistics.median(sorted_prices)),
            "min_price": sorted_prices[0],
            "max_price": sorted_prices[-1],
            "trend": "stable"
        }

    def get_rag_status(self):
        i = self._execute("SELECT COUNT(*) FROM items", fetch_one=True)
        k = self._execute("SELECT COUNT(*) FROM ai_knowledge", fetch_one=True)
        last = self._execute("SELECT last_updated FROM ai_knowledge ORDER BY last_updated DESC LIMIT 1", fetch_one=True)
        
        return {
            'total_items': i[0] if i else 0, 
            'total_categories': k[0] if k else 0, 
            'status': 'ok' if i and i[0] > 0 else 'empty',
            'last_rebuild': last['last_updated'] if last else "Никогда"
        }

    def get_all_items(self, limit=100) -> List[Dict]:
        rows = self._execute("SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,), fetch_all=True)
        return [dict(row) for row in rows] if rows else []

    def delete_item(self, avito_id: str):
        self._execute("DELETE FROM items WHERE avito_id = ?", (str(avito_id),), commit=True)
        return True

    def clear_all(self):
        self._execute("DELETE FROM items", commit=True)

    def get_stats(self) -> Dict:
        try:
            total = self._execute("SELECT COUNT(*) FROM items", fetch_one=True)[0]
            great = self._execute("SELECT COUNT(*) FROM items WHERE verdict='GREAT_DEAL'", fetch_one=True)[0]
            return {"total": total, "great": great}
        except:
            return {"total": 0, "great": 0}

    # ==================== Compression (v2) ====================

    def compress_chunk(self, chunk_id: int) -> bool:
        chunk = self._execute(
            "SELECT id, chunk_type, content, status, original_size FROM aiknowledge_v2 WHERE id = ?",
            (chunk_id,),
            fetch_one=True
        )
        
        if not chunk or chunk['status'] != 'READY':
            return False
        
        try:
            content_str = chunk['content']
            if not content_str:
                return False
                
            content = json.loads(content_str)
            chunk_type = chunk['chunk_type']
            
            if chunk_type == 'PRODUCT':
                compressed_str, size = ChunkCompressor.compress_product_chunk(content)
            elif chunk_type == 'CATEGORY':
                compressed_str, size = ChunkCompressor.compress_category_chunk(content)
            elif chunk_type == 'DATABASE':
                compressed_str, size = ChunkCompressor.compress_database_chunk(content)
            else:
                compressed_str, size = ChunkCompressor.compress_generic(content)
            
            if not compressed_str or size == 0:
                return False

            self._execute(
                """
                UPDATE aiknowledge_v2 
                SET compressed_content = ?, compressed_size = ?, status = 'COMPRESSED'
                WHERE id = ?
                """,
                (compressed_str, size, chunk_id),
                commit=True
            )
            
            ratio = round((size / chunk['original_size']) * 100, 1) if chunk['original_size'] else 0
            logger.info(f"Compressed chunk {chunk_id}: {chunk['original_size']} -> {size} bytes ({ratio}%)")
            return True
            
        except Exception as e:
            logger.error(f"Compression failed for chunk {chunk_id}: {e}")
            return False
    
    def auto_compress_old_chunks(self, days_old: int = 7):
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        old_chunks = self._execute(
            """
            SELECT id FROM aiknowledge_v2 
            WHERE status = 'READY' AND last_updated < ?
            """,
            (cutoff_date,),
            fetch_all=True
        )
        
        if not old_chunks: return

        count = 0
        for chunk in old_chunks:
            if self.compress_chunk(chunk['id']):
                count += 1
        
        if count > 0:
            logger.info(f"Auto-compressed {count} old chunks")

    def cleanup_old_data(self, days_to_keep=90):
        cutoff = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
        self._execute("DELETE FROM items WHERE added_at < ?", (cutoff,), commit=True)