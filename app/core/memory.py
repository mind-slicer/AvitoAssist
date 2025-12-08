import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from datetime import timedelta
import re
import statistics
from app.config import BASE_APP_DIR
from app.core.text_utils import SimHash, FeatureExtractor


class MemoryManager:
    """
    Менеджер памяти с RAG (Retrieval-Augmented Generation)
    - SQLite для данных и статистики
    - Keyword search для поиска похожих товаров
    """

    def __init__(self, db_path=None):
        if db_path is None:
            # Формируем полный путь к файлу внутри BASE_APP_DIR
            self.db_path = os.path.join(BASE_APP_DIR, "data", "memory.db")
        else:
            self.db_path = db_path

        # Создаем директорию, если её нет (важно, чтобы папка 'data' существовала)
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()
        self._stats_cache = {}

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    # ==================== SQLite ====================

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Таблица товаров
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
                    added_at TEXT,  -- ИСПРАВЛЕНО: было parsed_date, стало added_at
                    
                    -- AI поля
                    verdict TEXT,
                    reason TEXT,
                    market_position TEXT,
                    defects BOOLEAN,
                    
                    -- Мета
                    category TEXT,
                    tags TEXT
                )
            """)
            
            # Таблица статистики (Кэш RAG)
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

            # Таблица истории трендов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trend_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT,
                    date TEXT,
                    avg_price INTEGER,
                    sample_count INTEGER
                )
            """)
            
            # Таблица истории чата
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ==================== Добавление товаров ====================

    def add_item(self, item: dict):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                # Проверяем дубликаты
                cursor.execute("SELECT id FROM items WHERE avito_id = ?", (str(item.get('id')),))
                if cursor.fetchone():
                    return False # Уже есть

                # ИСПРАВЛЕНО: используем added_at вместо parsed_date
                cursor.execute("""
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
                    datetime.now().isoformat(), # Это значение пойдет в added_at
                    # AI Results
                    item.get('verdict'),
                    item.get('reason'),
                    item.get('market_position'),
                    item.get('defects')
                ))
                conn.commit()
                return True
            except Exception as e:
                print(f"DB Error: {e}")
                return False

    # ==================== Поиск похожих товаров ====================

    def find_similar_items(self, query_text: str, limit: int = 20) -> List[Dict]:
        """
        Поиск похожих товаров по ключевым словам (SQL LIKE)

        Args:
            query_text: Название товара для поиска
            limit: Максимум результатов

        Returns:
            Список похожих товаров из SQLite
        """
        return self._find_similar_by_keywords(query_text, limit)

    def _find_similar_by_keywords(self, title: str, limit: int = 20) -> List[Dict]:
        """Поиск похожих товаров по ключевым словам (SQL LIKE)"""
        try:
            keywords = self._extract_keywords(title)
            if not keywords:
                return []

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            # Параметризованный запрос (защита от SQL injection)
            query_parts = []
            params = []
            for kw in keywords:
                query_parts.append("title LIKE ?")
                params.append(f"%{kw}%")

            query = " OR ".join(query_parts)
            params.append(limit)

            c.execute(f"""
                SELECT * FROM items
                WHERE ({query})
                ORDER BY added_at DESC
                LIMIT ?
            """, params)

            rows = [dict(row) for row in c.fetchall()]
            conn.close()

            print(f"[Memory] 🔍 Keyword search: {len(rows)} results for '{title[:30]}'")
            return rows

        except Exception as e:
            print(f"[Memory] Keyword search error: {e}")
            return []

    def _extract_keywords(self, title: str) -> List[str]:
        """Извлечение ключевых слов из названия товара"""
        # Убираем шум
        noise_pattern = r'\b(новый|б/у|срочно|обмен|торг|продам|куплю|цена|руб|рублей)\b'
        clean_title = re.sub(noise_pattern, '', title.lower(), flags=re.IGNORECASE)

        # Разбиваем на слова и берем значимые (длина > 2)
        words = clean_title.split()
        keywords = [w for w in words if len(w) > 2][:5]  # Первые 5 значимых слов
        return keywords

    # ==================== RAG Контекст ====================

    def get_rag_context_for_item(self, title: str, days_back: int = 30) -> Optional[Dict]:
        """
        Получить RAG-контекст для товара (статистика по похожим)
        Args:
            title: Название товара
            days_back: Сколько дней назад учитывать
        Returns:
            Словарь с avg_price, median_price, trend, trend_percent, sample_count или None
        """
        
        # --- NEW: Сразу генерируем фичи для запроса ---
        # Это нужно для product_key и для последующей фильтрации
        query_features = FeatureExtractor.extract_features(title)
        query_hash = SimHash.get_hash(title)

        # Проверяем кеш статистики
        # Используем старый метод _generate_product_key, чтобы не ломать старую статистику
        # (или можно переделать его на основе query_features, но пока оставим как есть)
        product_key = self._generate_product_key(title) 
        cached_stats = self._get_cached_stats(product_key)

        if cached_stats:
            print(f"[Memory] 📊 Using cached stats for '{title[:30]}'")
            return cached_stats

        # Ищем похожие товары
        # --- CHANGE: Увеличиваем limit, так как будем жестко фильтровать ---
        similar_items = self.find_similar_items(title, limit=150) 
        if not similar_items:
            return None

        # Фильтруем по дате (последние N дней)
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        # --- NEW: Продвинутая фильтрация ---
        filtered_items = []
        for item in similar_items:
            # 1. Проверка даты
            if item.get('added_at', '') < cutoff_date:
                continue

            # 2. Проверка цены (защита от мусора)
            if not item.get('price') or item['price'] < 100:
                continue

            # 3. Фильтрация по характеристикам (Features)
            # Извлекаем фичи товара (из БД или на лету)
            item_features = {}
            if item.get('features'):
                try:
                    item_features = json.loads(item['features'])
                except: 
                    # Фолбэк, если JSON битый
                    item_features = FeatureExtractor.extract_features(item.get('title', ''))
            else:
                # Если товар старый и поля features еще нет
                item_features = FeatureExtractor.extract_features(item.get('title', ''))

            # Сравниваем критические характеристики
            mismatch = False
            # Список ключей, несовпадение которых недопустимо
            critical_keys = ['storage', 'ram', 'model_suffix'] 
            
            for key in critical_keys:
                if key in query_features and key in item_features:
                    # Если у нас iPhone 13 Pro, а нашли iPhone 13 (без Pro) -> mismatch
                    # Но тут нюанс: если в запросе "Pro", а в товаре нет суффикса - это mismatch.
                    # А если наоборот? Обычно тоже. Поэтому строгое равенство.
                    if query_features[key] != item_features[key]:
                        mismatch = True
                        break
            
            if mismatch:
                continue

            # 4. Фильтрация по SimHash (семантическая близость)
            item_hash = item.get('simhash')
            if not item_hash:
                # Если хеша нет в БД, считаем на лету
                item_hash = SimHash.get_hash(item.get('title', ''))
            
            dist = SimHash.distance(query_hash, item_hash)
            
            # Порог 25 бит подобран эмпирически для коротких заголовков.
            # Можно ужесточить до 15-20 для большей точности.
            if dist > 25:
                continue

            filtered_items.append(item)

        # --- END NEW ---

        if len(filtered_items) < 2:
            return None

        # Собираем цены
        prices = [item['price'] for item in filtered_items] # проверка if item.get('price') уже была выше
        
        # Расчет тренда (теперь возвращает tuple)
        trend, trend_percent = self._calculate_trend(filtered_items)

        # Формируем контекст
        context = {
            'avg_price': int(statistics.mean(prices)),
            'median_price': int(statistics.median(prices)),
            'min_price': int(min(prices)),
            'max_price': int(max(prices)),
            'sample_count': len(filtered_items),
            'trend': trend,
            'trend_percent': round(trend_percent, 1)
        }

        # Кешируем статистику
        self._cache_stats(product_key, context)

        print(f"[Memory] 📊 RAG context: {len(filtered_items)} items (filtered from {len(similar_items)}), avg={context['avg_price']}, trend={trend} ({trend_percent:+.1f}%)")
        return context

    def _calculate_trend(self, items: List[Dict]) -> tuple[str, float]:
        """
        Расчет тренда цен (up/down/stable) + процент изменения
        Args:
            items: Список товаров (с added_at и price)
        Returns:
            ("up"/"down"/"stable", процент_изменения)
        """
        if len(items) < 3:
            return ("stable", 0.0)

        try:
            # Сортируем по дате
            sorted_items = sorted(items, key=lambda x: x.get('added_at', ''))

            # Берем первую и последнюю треть
            third = len(sorted_items) // 3
            early = sorted_items[:third]
            late = sorted_items[-third:]

            early_prices = [i['price'] for i in early if i.get('price')]
            late_prices = [i['price'] for i in late if i.get('price')]

            if not early_prices or not late_prices:
                return ("stable", 0.0)

            avg_early = statistics.mean(early_prices)
            avg_late = statistics.mean(late_prices)

            # Процент изменения
            percent_change = ((avg_late - avg_early) / avg_early) * 100

            # Порог изменения: 10%
            if avg_late > avg_early * 1.1:
                return ("up", percent_change)
            elif avg_late < avg_early * 0.9:
                return ("down", percent_change)
            else:
                return ("stable", percent_change)
        except Exception as e:
            print(f"[Memory] Trend calculation error: {e}")
            return ("stable", 0.0)

    # ==================== Кеширование статистики ====================

    def _generate_product_key(self, title: str) -> str:
        """Генерация ключа продукта для кеширования"""
        keywords = self._extract_keywords(title)
        return ' '.join(keywords[:3])  # Первые 3 ключевых слова

    def _get_cached_stats(self, product_key: str) -> Optional[Dict]:
        """Получить статистику из кеша (если не устарела)"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            c.execute("""
                SELECT * FROM statistics
                WHERE product_key = ?
                AND last_updated >= datetime('now', '-1 hour')
            """, (product_key,))

            row = c.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            print(f"[Memory] Cache read error: {e}")
            return None

    def _cache_stats(self, product_key: str, context: Dict):
        """Сохранить статистику в кеш"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            c.execute("""
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

            # Сохраняем в историю трендов
            date_str = datetime.now().strftime("%Y-%m-%d")
            c.execute("""
                INSERT OR REPLACE INTO trend_history
                (product_key, date, avg_price, sample_count)
                VALUES (?, ?, ?, ?)
            """, (product_key, date_str, context['avg_price'], context['sample_count']))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Memory] Cache write error: {e}")

    def _invalidate_stats_cache(self, title: str):
        """Инвалидация кеша статистики при добавлении нового товара"""
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
        """
        Пересчитать все агрегаты статистики
        Returns:
            Количество пересчитанных категорий
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Получаем все уникальные product_key из items
            c.execute("SELECT DISTINCT title FROM items")
            titles = [row['title'] for row in c.fetchall()]
            conn.close()
            
            print(f"[Memory] 🔍 Found {len(titles)} unique titles")  # DEBUG
            
            if not titles:
                print("[Memory] ⚠️ No titles found, database might be empty")
                return 0
            
            # Генерируем product_key и собираем уникальные
            product_keys = set()
            for title in titles:
                pk = self._generate_product_key(title)
                if pk:
                    product_keys.add(pk)
            
            print(f"[Memory] 🔄 Rebuilding stats for {len(product_keys)} categories...")
            
            rebuilt = 0
            for pk in product_keys:
                # Ищем товары по ключевым словам
                keywords = pk.split()
                if not keywords:
                    continue
                
                # Строим временный title для поиска
                temp_title = " ".join(keywords)
                similar = self.find_similar_items(temp_title, limit=100)
                
                if len(similar) < 2:
                    print(f"[Memory] ⚠️ Category '{pk}': too few items ({len(similar)})")
                    continue
                
                # Фильтруем по дате (последние 30 дней)
                cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                filtered = [item for item in similar if item.get('added_at', '') >= cutoff_date]
                
                if len(filtered) < 2:
                    print(f"[Memory] ⚠️ Category '{pk}': too few recent items ({len(filtered)})")
                    continue
                
                # Считаем статистику
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
                print(f"[Memory] ✅ Category '{pk}': avg={context['avg_price']}, trend={trend}")
            
            print(f"[Memory] ✅ Rebuild complete: {rebuilt}/{len(product_keys)} categories")
            return rebuilt
            
        except Exception as e:
            print(f"[Memory] ❌ Rebuild error: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def get_all_statistics(self, limit: int = 100) -> List[Dict]:
        """
        Получить все агрегированные статистики
        Returns:
            Список словарей с полями: product_key, avg_price, trend, trend_percent, sample_count, last_updated
        """
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
            print(f"[Memory] Get statistics error: {e}")
            return []

    def get_stats_for_product_key(self, product_key: str) -> Optional[Dict]:
        """Получить агрегаты по конкретному product_key из таблицы statistics"""
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
            print(f"[Memory] Get stats by key error: {e}")
            return None

    def get_stats_for_title(self, title: str) -> Optional[Dict]:
        """
        RAG ENGINE: Ищет похожие товары и возвращает статистику рынка.
        Использует IQR для фильтрации выбросов (чехлов, коробок, ошибок).
        """
        if not title:
            return None
            
        # 1. Выделяем ключевое слово (самое длинное из значимых)
        ignore = {'продам', 'куплю', 'новый', 'состояние', 'торг', 'original', 'оригинал', 'комплект', 'полный', 'идеальное', 'отличное'}
        clean_words = [w for w in title.lower().split() if len(w) > 3 and w not in ignore]
        if not clean_words:
            return None
            
        keyword = max(clean_words, key=len) # Самое длинное слово - лучший кандидат (напр. 'macbook', 'playstation')

        # 2. Ищем цены в базе
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Ищем совпадение по ключевому слову
            cursor.execute("SELECT price FROM items WHERE title LIKE ? AND price > 100", (f"%{keyword}%",))
            rows = cursor.fetchall()
            
        raw_prices = [r[0] for r in rows if r[0] is not None]
        
        if len(raw_prices) < 3: # Мало данных для статистики
            return None

        # 3. Фильтрация выбросов (IQR метод)
        sorted_prices = sorted(raw_prices)
        q1 = sorted_prices[len(sorted_prices)//4]
        q3 = sorted_prices[3*len(sorted_prices)//4]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        filtered_prices = [p for p in sorted_prices if lower_bound <= p <= upper_bound]
        
        if not filtered_prices: # Если все отфильтровалось (странно), берем сырые
            filtered_prices = sorted_prices

        # 4. Расчет статистики
        try:
            avg_price = int(statistics.mean(filtered_prices))
            median_price = int(statistics.median(filtered_prices))
            min_price = filtered_prices[0]
            max_price = filtered_prices[-1]
            
            # Оценка тренда (грубая: сравниваем последние 3 добавленных с общей средней)
            # Тут мы не знаем порядок добавления в raw_prices, но допустим. 
            # Для простоты вернем "stable"
            trend = "stable" 
            
            return {
                "keyword": keyword,
                "sample_count": len(raw_prices), # Общее кол-во найденных
                "clean_count": len(filtered_prices), # Кол-во использованных для расчета
                "avg_price": avg_price,
                "median_price": median_price,
                "min_price": min_price,
                "max_price": max_price,
                "trend": trend
            }
        except Exception as e:
            print(f"RAG Error calculation: {e}")
            return None

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
        """
        Получить статус RAG-системы для UI
        Returns:
            {
                'total_items': int,
                'total_categories': int,
                'last_rebuild': str (timestamp),
                'status': 'ok' | 'outdated' | 'empty'
            }
        """
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Количество товаров
            c.execute("SELECT COUNT(*) FROM items")
            total_items = c.fetchone()[0]
            
            # Количество категорий
            c.execute("SELECT COUNT(*) FROM statistics")
            total_categories = c.fetchone()[0]
            
            # Последнее обновление
            c.execute("SELECT MAX(last_updated) FROM statistics")
            last_updated = c.fetchone()[0]
            
            conn.close()
            
            # Определяем статус
            if total_items == 0:
                status = 'empty'
            elif last_updated:
                # Проверяем, не устарело ли (более 1 часа)
                last_dt = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - last_dt > timedelta(hours=1):
                    status = 'outdated'
                else:
                    status = 'ok'
            else:
                status = 'outdated'
            
            return {
                'total_items': total_items,
                'total_categories': total_categories,
                'last_rebuild': last_updated or 'Never',
                'status': status
            }
            
        except Exception as e:
            print(f"[Memory] Get RAG status error: {e}")
            return {
                'total_items': 0,
                'total_categories': 0,
                'last_rebuild': 'Error',
                'status': 'empty'
            }

    def get_all_items(self, limit=100) -> List[Dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM items ORDER BY added_at DESC LIMIT ?", (limit,))
            rows = [dict(row) for row in c.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            print(f"[Memory] Get Error: {e}")
            return []

    def delete_item(self, avito_id: str):
       with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM items WHERE avito_id = ?", (str(avito_id),))
            conn.commit()
            return cursor.rowcount > 0

    def clear_all(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM items")
            conn.commit()

    def get_stats(self) -> Dict:
        """Статистика по памяти"""
        if not hasattr(self, 'db_path'):
            return {"total": 0, "great": 0}

        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM items")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM items WHERE verdict='GREAT_DEAL'")
            great = c.fetchone()[0]
            conn.close()

            return {"total": total, "great": great}
        except:
            return {"total": 0, "great": 0}

    def get_context_as_text(self, limit=50) -> str:
        """Текстовое представление памяти для чата"""
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
        """
        Краткая сводка по топ-N категориям из таблицы statistics
        для использования в чат-промпте аналитики.
        """
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
        """Удаление записей старше N дней"""
        if not hasattr(self, 'db_path'):
            return

        try:
            cutoff = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            c.execute("DELETE FROM items WHERE added_at < ?", (cutoff,))
            deleted = c.rowcount
            conn.commit()
            conn.close()

            print(f"[Memory] 🗑️ Cleanup: {deleted} items older than {days_to_keep} days")
        except Exception as e:
            print(f"[Memory] Cleanup error: {e}")