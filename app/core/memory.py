import sqlite3
import os
import threading
import re
import statistics
from datetime import datetime
from typing import List, Dict, Optional
from datetime import timedelta

from app.config import BASE_APP_DIR
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
    
    def _execute(self, query, params=(), fetch_one=False, fetch_all=False, commit=False):
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
                
                return result
            except Exception as e:
                logger.dev(f"DB Error: {e} | Query: {query}", level="ERROR")
                return None

    # ==================== SQLite ====================

    def _init_db(self):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    avito_id TEXT UNIQUE,
                    title TEXT,
                    price INTEGER,
                    description TEXT,
                    url TEXT,
                    seller TEXT,
                    address TEXT,
                    published_date TEXT,
                    added_at TEXT,
                    verdict TEXT,
                    reason TEXT,
                    market_position TEXT,
                    defects BOOLEAN,
                    category TEXT,
                    tags TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS statistics (
                    product_key TEXT PRIMARY KEY,
                    avg_price INTEGER,
                    median_price INTEGER,
                    min_price INTEGER,
                    max_price INTEGER,
                    sample_count INTEGER,
                    trend TEXT,
                    trend_percent REAL,
                    last_updated TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trend_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT,
                    date TEXT,
                    avg_price INTEGER,
                    sample_count INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._conn.commit()

    # ==================== Добавление товаров ====================

    def add_item(self, item: dict):
        row = self._execute("SELECT id FROM items WHERE avito_id = ?", (str(item.get('id')),), fetch_one=True)
        if row:
            return False

        self._execute("""
            INSERT INTO items (
                avito_id, title, price, description, url, seller, address, 
                published_date, added_at, verdict, reason, market_position, defects
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(item.get('id')),
            item.get('title'),
            item.get('price'),
            item.get('description'),
            item.get('link'),
            item.get('seller'),
            item.get('address'),
            item.get('date'),
            datetime.now().isoformat(),
            item.get('verdict'),
            item.get('reason'),
            item.get('market_position'),
            item.get('defects')
        ), commit=True)
        return True

    # ==================== Поиск похожих товаров ====================

    def find_similar_items(self, query_text: str, limit: int = 20) -> List[Dict]:
        return self._find_similar_by_keywords(query_text, limit)

    def _find_similar_by_keywords(self, title: str, limit: int = 20) -> List[Dict]:
        try:
            keywords = self._extract_keywords(title)
            if not keywords:
                return []

            query_parts = []
            params = []
            for kw in keywords:
                query_parts.append("title LIKE ?")
                params.append(f"%{kw}%")

            query = " OR ".join(query_parts)
            sql = f"SELECT * FROM items WHERE ({query}) ORDER BY added_at DESC LIMIT ?"
            params.append(limit)

            rows = self._execute(sql, tuple(params), fetch_all=True)
            if not rows:
                return []
                
            return [dict(row) for row in rows]

        except Exception as e:
            logger.dev(f"Memory keyword search error: {e}", level="ERROR")
            return []

    def _extract_keywords(self, title: str) -> List[str]:
        noise_pattern = r'\b(новый|б/у|срочно|обмен|торг|продам|куплю|цена|руб|рублей)\b'
        clean_title = re.sub(noise_pattern, '', title.lower(), flags=re.IGNORECASE)
        words = clean_title.split()
        keywords = [w for w in words if len(w) > 2][:5]
        return keywords

    # ==================== RAG Контекст ====================

    def get_rag_context_for_item(self, title: str, days_back: int = 30) -> Optional[Dict]:
        query_features = FeatureExtractor.extract_features(title)
        
        # Кэш
        product_key = self._generate_product_key(title) 
        cached_stats = self._get_cached_stats(product_key)
        if cached_stats:
            logger.dev(f"Memory using cached stats for {title[:30]}", level="INFO")
            return cached_stats

        # 1. Сначала грубая выборка по ключевым словам (SQL)
        candidates = self.find_similar_items(title, limit=100) 
        if not candidates:
            return None

        # 2. Подготовка к фильтрации
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        candidate_titles = []
        candidate_objs = []

        # Предварительная фильтрация (цена, дата, features)
        for item in candidates:
            if item.get('added_at', '') < cutoff_date: continue
            if not item.get('price') or item['price'] < 100: continue

            item_features = FeatureExtractor.extract_features(item.get('title', ''))
            mismatch = False
            critical_keys = ['storage', 'ram', 'model_suffix'] 
            for key in critical_keys:
                if key in query_features and key in item_features:
                    if query_features[key] != item_features[key]:
                        mismatch = True
                        break
            if mismatch: continue
            
            candidate_titles.append(item.get('title', ''))
            candidate_objs.append(item)

        if not candidate_titles:
            return None

        # 3. Применяем TF-IDF
        scores = TextMatcher.calculate_similarity(title, candidate_titles)
        
        # Порог сходства (эмпирический)
        THRESHOLD = 0.3 
        
        final_items = []
        for idx, score in enumerate(scores):
            if score >= THRESHOLD:
                final_items.append(candidate_objs[idx])

        if len(final_items) < 2:
            return None

        # 4. Расчет статистики
        prices = [item['price'] for item in final_items]
        trend, trend_percent = self._calculate_trend(final_items)

        context = {
            'avg_price': int(statistics.mean(prices)),
            'median_price': int(statistics.median(prices)),
            'min_price': int(min(prices)),
            'max_price': int(max(prices)),
            'sample_count': len(final_items),
            'trend': trend,
            'trend_percent': round(trend_percent, 1)
        }

        self._cache_stats(product_key, context)
        logger.dev(f"RAG (TF-IDF): {len(final_items)} items matched query '{title[:20]}...'", level="INFO")
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

    # ==================== Кэширование статистики ====================

    def _generate_product_key(self, title: str) -> str:
        keywords = self._extract_keywords(title)
        return ' '.join(keywords[:3])

    def _get_cached_stats(self, product_key: str) -> Optional[Dict]:
        row = self._execute("""
            SELECT * FROM statistics
            WHERE product_key = ?
            AND last_updated >= datetime('now', '-1 hour')
        """, (product_key,), fetch_one=True)
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
                logger.dev(f"Cache write error: {e}", level="ERROR")

    def _invalidate_stats_cache(self, title: str):
        try:
            product_key = self._generate_product_key(title)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM statistics WHERE product_key = ?", (product_key,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    def rebuild_statistics_cache(self) -> int:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute("SELECT DISTINCT title FROM items")
            titles = [row['title'] for row in c.fetchall()]
            conn.close()
            
            if not titles:
                logger.dev(f"No titles found, database might be empty", level="DEBUG")
                return 0
            
            product_keys = set()
            for title in titles:
                pk = self._generate_product_key(title)
                if pk:
                    product_keys.add(pk)
            
            logger.dev(f"Rebuilding stats for {len(product_keys)} categories", level="INFO")
            
            rebuilt = 0
            for pk in product_keys:
                keywords = pk.split()
                if not keywords:
                    continue
                
                temp_title = " ".join(keywords)
                similar = self.find_similar_items(temp_title, limit=100)
                
                if len(similar) < 2:
                    logger.dev(f"Category '{pk}': too few items ({len(similar)})", level="DEBUG")
                    continue
                
                cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                filtered = [item for item in similar if item.get('added_at', '') >= cutoff_date]
                
                if len(filtered) < 2:
                    logger.dev(f"Category '{pk}': too few recent items ({len(filtered)})", level="DEBUG")
                    continue
                
                prices = [item['price'] for item in filtered if item.get('price')]
                if not prices:
                    continue
                
                trend, trend_percent = self._calculate_trend(filtered)
                
                context = {
                    'avg_price': int(statistics.mean(prices)),
                    'median_price': int(statistics.median(prices)),
                    'min_price': int(min(prices)),
                    'max_price': int(max(prices)),
                    'sample_count': len(filtered),
                    'trend': trend,
                    'trend_percent': round(trend_percent, 1)
                }
                
                self._cache_stats(pk, context)
                rebuilt += 1
                logger.dev(f"Category '{pk}': avg={context['avg_price']}, trend={trend}", level="INFO")
            
            logger.dev(f"Rebuild complete: {rebuilt}/{len(product_keys)} categories", level="INFO")
            return rebuilt
            
        except Exception as e:
            logger.dev(f"Rebuild error: {e}", level="ERROR")
            import traceback
            traceback.print_exc()
            return 0

    def get_all_statistics(self, limit: int = 100) -> List[Dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            c.execute("""
                SELECT * FROM statistics
                ORDER BY last_updated DESC
                LIMIT ?
            """, (limit,))

            rows = [dict(row) for row in c.fetchall()]
            conn.close()
            return rows

        except Exception as e:
            logger.dev(f"Get statistics error: {e}", level="ERROR")
            return []

    def get_stats_for_product_key(self, product_key: str) -> Optional[Dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT * FROM statistics
                WHERE product_key = ?
            """, (product_key,))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.dev(f"Get stats by key error: {e}", level="ERROR")
            return None

    def get_stats_for_title(self, title: str) -> Optional[Dict]:
        if not title: return None
        ignore = {'продам', 'куплю', 'новый', 'состояние', 'торг', 'original', 'оригинал', 'комплект', 'полный', 'идеальное', 'отличное'}
        clean_words = [w for w in title.lower().split() if len(w) > 3 and w not in ignore]
        if not clean_words: return None
        keyword = max(clean_words, key=len)

        # Безопасный запрос
        rows = self._execute("SELECT price FROM items WHERE title LIKE ? AND price > 100", (f"%{keyword}%",), fetch_all=True)
        if not rows: return None
        
        raw_prices = [r['price'] for r in rows if r['price'] is not None]
        if len(raw_prices) < 3: return None

        sorted_prices = sorted(raw_prices)
        q1 = sorted_prices[len(sorted_prices)//4]
        q3 = sorted_prices[3*len(sorted_prices)//4]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        filtered_prices = [p for p in sorted_prices if lower_bound <= p <= upper_bound]
        if not filtered_prices: filtered_prices = sorted_prices

        try:
            return {
                "keyword": keyword,
                "sample_count": len(raw_prices),
                "clean_count": len(filtered_prices),
                "avg_price": int(statistics.mean(filtered_prices)),
                "median_price": int(statistics.median(filtered_prices)),
                "min_price": filtered_prices[0],
                "max_price": filtered_prices[-1],
                "trend": "stable"
            }
        except: return None

    def get_rag_context_for_product_key(self, product_key: str) -> Optional[Dict]:
        stats = self.get_stats_for_product_key(product_key)
        if not stats:
            return None
        return {
            "product_key": product_key,
            "avg_price": stats.get("avg_price"),
            "median_price": stats.get("median_price"),
            "min_price": stats.get("min_price"),
            "max_price": stats.get("max_price"),
            "sample_count": stats.get("sample_count"),
            "trend": stats.get("trend"),
            "trend_percent": stats.get("trend_percent", 0.0),
        }

    # ==================== Утилиты ====================

    def get_rag_status(self) -> Dict:
        with self._lock:
            try:
                c = self._conn.cursor()
                c.execute("SELECT COUNT(*) FROM items")
                total_items = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM statistics")
                total_categories = c.fetchone()[0]
                c.execute("SELECT MAX(last_updated) FROM statistics")
                last_updated = c.fetchone()[0]
                
                status = 'empty' if total_items == 0 else 'ok'
                if last_updated:
                    last_dt = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() - last_dt > timedelta(hours=1):
                        status = 'outdated'
                elif total_items > 0:
                    status = 'outdated'
                    
                return {
                    'total_items': total_items,
                    'total_categories': total_categories,
                    'last_rebuild': last_updated or 'Never',
                    'status': status
                }
            except Exception:
                return {'total_items': 0, 'total_categories': 0, 'last_rebuild': 'Error', 'status': 'empty'}

    # TODO Почему здесь лимит?
    def get_all_items(self, limit=100) -> List[Dict]:
        rows = self._execute("SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,), fetch_all=True)
        return [dict(row) for row in rows] if rows else []

    def delete_item(self, avito_id: str):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM items WHERE avito_id = ?", (str(avito_id),))
            self._conn.commit()
            return cursor.rowcount > 0

    def clear_all(self):
        self._execute("DELETE FROM items", commit=True)

    def get_stats(self) -> Dict:
        with self._lock:
            try:
                c = self._conn.cursor()
                c.execute("SELECT COUNT(*) FROM items")
                total = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM items WHERE verdict='GREAT_DEAL'")
                great = c.fetchone()[0]
                return {"total": total, "great": great}
            except:
                return {"total": 0, "great": 0}

    def get_context_as_text(self, limit=50) -> str:
        items = self.get_all_items(limit)
        if not items:
            return "База знаний пуста."

        items.sort(key=lambda x: x['price'] if x['price'] is not None else float('inf'))

        text_parts = [f"В базе данных всего {len(items)} товаров. Список (отсортирован по цене):"]
        for idx, i in enumerate(items, 1):
            verdict = i['verdict'] or "N/A"
            price = i['price'] or 0
            title = i['title'] or "No Title"
            title = " ".join(title.split())
            city = i['city'] or "Unknown"
            line = f"{idx}. [{verdict}] {price} руб. | {title} | {city}"
            text_parts.append(line)

        return "\n".join(text_parts)
    
    def get_category_summary_text(self, top_n: int = 10) -> str:
        try:
            stats = self.get_all_statistics(limit=top_n)
        except Exception:
            return "Нет данных статистики."

        if not stats:
            return "База знаний пуста."

        lines = ["Краткая сводка по рынку (товар: средняя цена (медиана, кол-во) тренд):"]
        for st in stats:
            name = st.get('product_key') or "N/A"
            avg = st.get('avg_price') or 0
            med = st.get('median_price') or 0
            count = st.get('sample_count') or 0
            trend = st.get('trend') or 'stable'
            tp = st.get('trend_percent') or 0.0

            avg_fmt = f"{avg//1000}к" if avg > 1000 else str(avg)
            med_fmt = f"{med//1000}к" if med > 1000 else str(med)
            trend_icon = "↗️" if trend == 'up' else "↘️" if trend == 'down' else "➡️"
            
            line = f"- {name}: {avg_fmt} (med:{med_fmt}, n={count}) {trend_icon}{tp:+.0f}%"
            lines.append(line)
        
        return "\n".join(lines)

    def cleanup_old_data(self, days_to_keep=90):
        try:
            cutoff = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
            with self._lock:
                c = self._conn.cursor()
                c.execute("DELETE FROM items WHERE added_at < ?", (cutoff,))
                self._conn.commit()
                logger.dev(f"Memory cleanup: {c.rowcount} items deleted", level="INFO")
        except Exception as e:
            logger.dev(f"Memory cleanup error: {e}", level="ERROR")