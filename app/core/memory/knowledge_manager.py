import sqlite3
import json
import os
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone

from app.core.text_utils import FeatureExtractor

from app.config import BASE_APP_DIR
from app.core.log_manager import logger


class KnowledgeManager:
    SCHEMA_VERSION = 5
    DB_FILENAME = "memory_knowledge.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(BASE_APP_DIR, self.DB_FILENAME)
        self._stats_cache = None
        self._stats_cache_time = 0
        self._ensure_db_exists()

    def _get_connection(self) -> sqlite3.Connection:

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -32000;")
        conn.execute("PRAGMA mmap_size = 134217728;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        
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
                logger.info("Creating fresh knowledge database schema")
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
                logger.info(f"Migrating knowledge schema from {current_version} to {self.SCHEMA_VERSION}")
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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_knowledge'")
        if cursor.fetchone() is None:
            self._create_all_tables(cursor)

    def _create_all_tables(self, cursor: sqlite3.Cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_type TEXT NOT NULL,
                chunk_key TEXT NOT NULL,
                parent_chunk_id INTEGER REFERENCES ai_knowledge(id),
                title TEXT,
                content TEXT,
                summary TEXT,
                status TEXT DEFAULT 'PENDING',
                priority INTEGER DEFAULT 1,
                new_data_items_count INTEGER DEFAULT 0,
                last_cultivation_attempt TEXT,
                retry_count INTEGER DEFAULT 0,
                source_hash TEXT,
                dependency_hash TEXT,
                embedding BLOB,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chunk_type, chunk_key)
            )
        """)
        
        # Исправлена опечатка AUTOINCREMENT
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id INTEGER,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                avg_price INTEGER,
                data_sufficiency TEXT,
                market_phase TEXT
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_status ON ai_knowledge(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunk_key ON ai_knowledge(chunk_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_type ON ai_knowledge(chunk_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_priority ON ai_knowledge(priority)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_history_id ON chunk_history(chunk_id)")

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int, to_version: int):
        if from_version < 2:
            self._create_all_tables(cursor)
        
        if from_version < 3:
            try:
                cursor.execute("ALTER TABLE ai_knowledge ADD COLUMN source_hash TEXT")
            except sqlite3.OperationalError:
                pass

        if from_version < 4:
            logger.info("Migrating Knowledge DB to v4: Translating Enums to English")
            try:
                # 1. Перевод статусов
                status_map = {
                    'В ОЖИДАНИИ': 'PENDING', 'ИНИЦИАЛИЗАЦИЯ': 'INITIALIZING',
                    'НАКОПЛЕНИЕ': 'ACCUMULATING', 'ГОТОВ': 'READY',
                    'СЖАТ': 'COMPRESSED', 'ОШИБКА': 'FAILED'
                }
                for rus, eng in status_map.items():
                    cursor.execute("UPDATE ai_knowledge SET status = ? WHERE status = ?", (eng, rus))
                # Страховка регистра
                cursor.execute("UPDATE ai_knowledge SET status = 'PENDING' WHERE status LIKE 'В ожидании'")

                # 2. Перевод типов чанков
                type_map = {
                    'ПРОДУКТ': 'PRODUCT', 'КАТЕГОРИЯ': 'CATEGORY',
                    'БАЗА ДАННЫХ': 'DATABASE', 'ПОВЕДЕНИЕ ИИ': 'AI_BEHAVIOR',
                    'ПОЛЬЗОВАТЕЛЬСКИЙ': 'CUSTOM'
                }
                for rus, eng in type_map.items():
                    cursor.execute("UPDATE ai_knowledge SET chunk_type = ? WHERE chunk_type = ?", (eng, rus))
                
            except Exception as e:
                logger.error(f"Migration v4 error: {e}")

        # --- МИГРАЦИЯ V5 ---
        if from_version < 5:
            logger.info("Migrating Knowledge DB to v5: Graph, History & Embeddings")
            try:
                # Граф
                cursor.execute("ALTER TABLE ai_knowledge ADD COLUMN parent_chunk_id INTEGER REFERENCES ai_knowledge(id)")
                cursor.execute("ALTER TABLE ai_knowledge ADD COLUMN dependency_hash TEXT")
                
                # Вектора (RAG)
                cursor.execute("ALTER TABLE ai_knowledge ADD COLUMN embedding BLOB")
                
                # История
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chunk_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chunk_id INTEGER,
                        recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        avg_price INTEGER,
                        data_sufficiency TEXT,
                        market_phase TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_history_id ON chunk_history(chunk_id)")
            except Exception as e:
                logger.error(f"Migration v5 error: {e}")

    # === Basic CRUD ===

    def add_knowledge(self, chunk_type: str, chunk_key: str, title: str,
                      content: Optional[Dict] = None, status: str = 'PENDING',
                      priority: int = 1, source_hash: str = None, parent_chunk_id: int = None) -> int:

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            content_json = json.dumps(content, ensure_ascii=False) if content else None
            
            now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

            cursor.execute(
                "SELECT id FROM ai_knowledge WHERE chunk_type = ? AND chunk_key = ?",
                (chunk_type, chunk_key)
            )
            existing = cursor.fetchone()

            if existing:
                sql = """
                    UPDATE ai_knowledge SET
                        title = ?, content = ?,
                        status = ?, priority = ?, new_data_items_count = 0,
                        last_updated = ?
                """
                params = [title, content_json, status, priority, now_utc]
                
                if source_hash:
                    sql += ", source_hash = ?"
                    params.append(source_hash)
                
                if parent_chunk_id is not None:
                    sql += ", parent_chunk_id = ?"
                    params.append(parent_chunk_id)
                
                sql += " WHERE id = ?"
                params.append(existing[0])
                
                cursor.execute(sql, tuple(params))
                conn.commit()
                return existing[0]
            else:
                cursor.execute("""
                    INSERT INTO ai_knowledge (
                        chunk_type, chunk_key, title, content, status, priority, 
                        last_updated, source_hash, parent_chunk_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (chunk_type, chunk_key, title, content_json, status, priority, 
                      now_utc, source_hash, parent_chunk_id, now_utc))
                
                conn.commit()
                self._stats_cache = None
                return cursor.lastrowid
        finally:
            conn.close()

    def get_knowledge(
        self,
        chunk_id: Optional[int] = None,
        chunk_key: Optional[str] = None,
        chunk_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Получает знания из БД с полной поддержкой фильтрации и правильной сортировкой статусов.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Базовый запрос
            query = "SELECT * FROM ai_knowledge WHERE 1=1"
            params = []

            if chunk_id is not None:
                query += " AND id = ?"
                params.append(chunk_id)

            if chunk_key:
                query += " AND chunk_key = ?"
                params.append(chunk_key)

            if chunk_type:
                query += " AND chunk_type = ?"
                params.append(chunk_type)

            if status:
                query += " AND status = ?"
                params.append(status)

            # Сортировка: Сначала активные процессы, потом требующие обновления, потом новые, потом готовые
            query += """
                ORDER BY
                CASE 
                    WHEN status = 'INITIALIZING' THEN 0 
                    WHEN status = 'NEED_REFRESH' THEN 1
                    WHEN status = 'PENDING' THEN 2
                    ELSE 3 
                END,
                priority DESC,
                last_updated DESC
                LIMIT ? OFFSET ?
            """
            
            # Добавляем лимиты в параметры (ОНИ ДОЛЖНЫ СООТВЕТСТВОВАТЬ ? В SQL)
            params.extend([limit, offset])

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            return [self._chunk_from_row(row) for row in rows]

        except Exception as e:
            logger.error(f"Ошибка при получении знаний: {e}")
            return []
        finally:
            conn.close()

    def get_chunk_by_id(self, chunk_id: int) -> Optional[Dict]:
        """Get single chunk by id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ai_knowledge WHERE id = ?", (chunk_id,))
            row = cursor.fetchone()
            return self._chunk_from_row(row) if row else None
        finally:
            conn.close()

    def _chunk_from_row(self, row: sqlite3.Row) -> Dict:
        """Convert row to chunk dict."""
        chunk = dict(row)
        # Parse content JSON
        if chunk.get('content'):
            try:
                chunk['content'] = json.loads(chunk['content'])
            except json.JSONDecodeError:
                chunk['content'] = None
        return chunk

    def delete_knowledge(self, chunk_id: int) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Получаем инфо о удаляемом чанке
            cursor.execute("SELECT * FROM ai_knowledge WHERE id = ?", (chunk_id,))
            row = cursor.fetchone()
            if not row: return False
            
            target_chunk = dict(row)
            target_key = target_chunk['chunk_key']
            target_type = target_chunk['chunk_type']
            
            # 2. Удаляем
            cursor.execute("DELETE FROM ai_knowledge WHERE id = ?", (chunk_id,))
            deleted = cursor.rowcount > 0
            
            if deleted:
                logger.info(f"🧠 ИИ забыл концепцию: [{target_type}] {target_key}", token="ai-mem")
                
                # 3. Обработка зависимостей (Cascade Invalidate)
                dependents_reset = 0
                
                # Если удалили КАТЕГОРИЮ -> Сбрасываем ПРОДУКТЫ, которые в нее входили
                if target_type == 'CATEGORY':
                    # Ищем продукты (эффективнее было бы хранить parent_id, но мы используем ключи)
                    # Перебираем все продукты и проверяем их cluster_key
                    # (Это может быть медленно на огромных базах, но для <1000 чанков приемлемо)
                    cursor.execute("SELECT id, chunk_key, title FROM ai_knowledge WHERE chunk_type = 'PRODUCT'")
                    products = cursor.fetchall()
                    
                    ids_to_reset = []
                    for p_row in products:
                        # Используем ту же логику определения родителя, что и при создании
                        sem = FeatureExtractor.extract_semantic_data(p_row['title'] or p_row['chunk_key'])
                        if sem.get('cluster_key') == target_key:
                            ids_to_reset.append(p_row['id'])
                    
                    if ids_to_reset:
                        placeholders = ','.join('?' * len(ids_to_reset))
                        cursor.execute(f"UPDATE ai_knowledge SET status = 'PENDING' WHERE id IN ({placeholders})", tuple(ids_to_reset))
                        dependents_reset = len(ids_to_reset)

                # Если удалили БАЗУ ДАННЫХ -> Сбрасываем ПОВЕДЕНИЕ (оно опирается на базу)
                elif target_type == 'DATABASE':
                    cursor.execute("UPDATE ai_knowledge SET status = 'PENDING' WHERE chunk_type = 'AI_BEHAVIOR'")
                    dependents_reset = cursor.rowcount

                if dependents_reset > 0:
                    logger.warning(f"⚠️ Сброшен статус у {dependents_reset} зависимых чанков (требуется перегенерация).", token="ai-mem")

            conn.commit()
            if deleted:
                self._stats_cache = None
            return deleted
        finally:
            conn.close()

    def delete_knowledge_by_key(self, chunk_key: str, chunk_type: Optional[str] = None) -> int:
        """Delete chunks by key. Returns count."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if chunk_type:
                cursor.execute(
                    "DELETE FROM ai_knowledge WHERE chunk_key = ? AND chunk_type = ?",
                    (chunk_key, chunk_type)
                )
            else:
                cursor.execute("DELETE FROM ai_knowledge WHERE chunk_key = ?", (chunk_key,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def clear_all_knowledge(self) -> int:
        """Clear all knowledge. Returns count of deleted."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ai_knowledge")
            count = cursor.fetchone()[0] or 0
            cursor.execute("DELETE FROM ai_knowledge")
            conn.commit()
            return count
        finally:
            conn.close()

    # === Updates ===

    def update_chunk_content(self, chunk_id: int, content: Dict, summary: Optional[str] = None, source_hash: str = None, embedding_blob: bytes = None):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            content_json = json.dumps(content, ensure_ascii=False)
            if summary is None:
                summary = content.get('summary') or content.get('analysis', {}).get('summary', '')
            
            now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            
            sql = """
                UPDATE ai_knowledge SET
                    content = ?, summary = ?, status = 'READY',
                    new_data_items_count = 0, last_updated = ?
            """
            params = [content_json, summary, now_utc]
            
            if source_hash:
                sql += ", source_hash = ?"
                params.append(source_hash)
            
            if embedding_blob:
                sql += ", embedding = ?"
                params.append(embedding_blob)
                
            sql += " WHERE id = ?"
            params.append(chunk_id)
            
            cursor.execute(sql, tuple(params))
            conn.commit()
            self._stats_cache = None
        finally:
            conn.close()

    def update_chunk_status(self, chunk_id: int, status: str, progress: Optional[int] = None):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                UPDATE ai_knowledge SET status = ?, last_cultivation_attempt = ?
                WHERE id = ?
            """, (status, now_utc, chunk_id))
            conn.commit()
        finally:
            conn.close()

    def update_chunk_with_retry(self, chunk_id: int, status: str, retry_count: int):
        """Update chunk status with retry count."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE ai_knowledge SET
                    status = ?, retry_count = ?, last_cultivation_attempt = ?
                WHERE id = ?
            """, (status, retry_count, datetime.now().isoformat(), chunk_id))
            conn.commit()
        finally:
            conn.close()

    def increment_data_count(self, chunk_id: int, count: int = 1):
        """Increment new data items count."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE ai_knowledge SET new_data_items_count = new_data_items_count + ?
                WHERE id = ?
            """, (count, chunk_id))
            conn.commit()
        finally:
            conn.close()

    # === Queries ===

    def get_pending_chunks(self) -> List[Dict]:
        """
        Возвращает чанки, ожидающие обработки.
        Поддерживает как английский 'PENDING', так и русский 'В ОЖИДАНИИ' статусы.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT * FROM ai_knowledge 
                WHERE status IN ('PENDING', 'В ОЖИДАНИИ') 
                ORDER BY priority DESC, last_updated DESC
            """
            cursor.execute(query)
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_ready_chunks(self) -> List[Dict]:
        """
        Возвращает готовые чанки.
        Поддерживает как английский 'READY', так и русский 'ГОТОВ'.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT * FROM ai_knowledge 
                WHERE status IN ('READY', 'ГОТОВ', 'COMPRESSED', 'СЖАТ')
                ORDER BY priority DESC, last_updated DESC
            """
            cursor.execute(query)
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_chunks_by_type(self, chunk_type: str) -> List[Dict]:
        """Get all chunks of a specific type."""
        return self.get_knowledge(chunk_type=chunk_type, limit=9999)

    def get_chunk_by_key_and_type(self, chunk_key: str, chunk_type: str) -> Optional[Dict]:
        """Get chunk by key and type."""
        chunks = self.get_knowledge(chunk_key=chunk_key, chunk_type=chunk_type, limit=1)
        return chunks[0] if chunks else None

    # === Statistics ===

    def get_status_summary(self) -> Dict:
        """Get summary of chunks by status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM ai_knowledge
                GROUP BY status
            """)
            result = {}
            for row in cursor.fetchall():
                result[row[0]] = row[1]
            return result
        finally:
            conn.close()

    def get_recent_knowledge(self, limit: int = 10) -> List[Dict]:
        """Get recently updated chunks."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_knowledge
                ORDER BY last_updated DESC
                LIMIT ?
            """, (limit,))
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_statistics(self) -> Dict:
        if self._stats_cache and (time.time() - self._stats_cache_time < 60):
            return self._stats_cache

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM ai_knowledge")
            total = cursor.fetchone()[0] or 0

            status_summary = self.get_status_summary()

            cursor.execute("SELECT COUNT(*) FROM ai_knowledge WHERE chunk_type = 'PRODUCT'")
            product_count = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM ai_knowledge WHERE chunk_type = 'CATEGORY'")
            category_count = cursor.fetchone()[0] or 0

            result = {
                'total_chunks': total,
                'by_status': status_summary,
                'product_chunks': product_count,
                'category_chunks': category_count
            }
            self._stats_cache = result
            self._stats_cache_time = time.time()
            return result
        finally:
            conn.close()

    # === RAG Context ===

    def get_rag_context_for_item(self, title: str) -> Optional[Dict]:
        """Get RAG context for a given item title."""
        # Find best matching chunk based on title
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_knowledge
                WHERE status = 'READY'
                ORDER BY
                    CASE WHEN title LIKE ? THEN 1 ELSE 0 END DESC,
                    CASE WHEN title LIKE ? THEN 1 ELSE 0 END DESC,
                    priority DESC
                LIMIT 1
            """, (f'%{title}%', f'%{title.lower()}%'))
            row = cursor.fetchone()
            if row:
                chunk = self._chunk_from_row(row)
                # Extract price stats from content
                content = chunk.get('content') or {}
                analysis = content.get('analysis') or {}
                price_analysis = analysis.get('price_analysis') or {}
                return {
                    'knowledge': chunk.get('summary', ''),
                    'chunk_id': chunk['id'],
                    'median_price': price_analysis.get('median', 0) or price_analysis.get('avg', 0),
                    'avg_price': price_analysis.get('avg', 0),
                    'q25_price': price_analysis.get('q25', 0),
                    'sample_count': analysis.get('sample_count', 0)
                }
            return None
        finally:
            conn.close()

    def find_relevant_chunks(self, query_text: str, limit: int = 3, min_similarity: float = 0.6) -> List[Dict]:
        """
        Ищет чанки по смыслу (векторам) с использованием Cosine Similarity.
        Если векторов нет, откатывается на LIKE.
        """
        from app.core.text_utils import FeatureExtractor
        import numpy as np
        
        # 1. Получаем вектор запроса
        query_vec = FeatureExtractor.get_string_vector(query_text)
        
        # Если модель не загружена или вектора нет -> Fallback на LIKE
        if query_vec is None:
            return self._fallback_text_search(query_text, limit)
            
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 2. Выгружаем ID и Embeddings всех готовых чанков
            # (Для базы < 10,000 чанков это очень быстро, < 100ms)
            cursor.execute("SELECT id, embedding FROM ai_knowledge WHERE status = 'READY' AND embedding IS NOT NULL")
            rows = cursor.fetchall()
            
            if not rows:
                return self._fallback_text_search(query_text, limit)
            
            # 3. Считаем Cosine Similarity через Numpy (векторизованно)
            # Формируем матрицу векторов базы
            db_vectors = []
            ids = []
            
            for r in rows:
                if r[1]: # Если blob не пустой
                    vec = np.frombuffer(r[1], dtype=np.float32)
                    if vec.shape == query_vec.shape:
                        db_vectors.append(vec)
                        ids.append(r[0])
            
            if not db_vectors:
                return self._fallback_text_search(query_text, limit)

            db_matrix = np.array(db_vectors)
            
            # Cosine Sim = (A . B) / (|A| * |B|)
            # Spacy вектора обычно уже нормализованы, но для надежности посчитаем нормы
            norm_query = np.linalg.norm(query_vec)
            norm_db = np.linalg.norm(db_matrix, axis=1)
            
            dot_products = np.dot(db_matrix, query_vec)
            similarities = dot_products / (norm_db * norm_query)
            
            # 4. Сортировка и фильтрация
            # Получаем индексы топ-N результатов
            top_indices = np.argsort(similarities)[::-1][:limit]
            
            results = []
            for idx in top_indices:
                score = similarities[idx]
                if score >= min_similarity:
                    chunk_id = ids[idx]
                    # Загружаем полный чанк
                    chunk = self.get_chunk_by_id(chunk_id)
                    if chunk:
                        chunk['_similarity'] = float(score) # Для дебага
                        results.append(chunk)
            
            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._fallback_text_search(query_text, limit)
        finally:
            conn.close()

    def _fallback_text_search(self, query_text: str, limit: int) -> List[Dict]:
        """Старый добрый SQL LIKE для подстраховки"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_knowledge 
                WHERE status = 'READY' AND (
                    title LIKE ? OR summary LIKE ?
                ) ORDER BY priority DESC LIMIT ?
            """, (f"%{query_text}%", f"%{query_text}%", limit))
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # --- НОВЫЕ МЕТОДЫ: ГРАФ ---
    def get_child_chunks(self, parent_id: int) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_knowledge WHERE parent_chunk_id = ?", (parent_id,))
        return [self._chunk_from_row(r) for r in cursor.fetchall()]

    def set_parent(self, child_id: int, parent_id: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ai_knowledge SET parent_chunk_id = ? WHERE id = ?", (parent_id, child_id))
        conn.commit()

    # --- НОВЫЕ МЕТОДЫ: ИСТОРИЯ ---
    def save_history_snapshot(self, chunk_id: int, stats: Dict):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chunk_history (chunk_id, avg_price, data_sufficiency, market_phase)
            VALUES (?, ?, ?, ?)
        """, (chunk_id, stats.get('avg'), stats.get('sufficiency'), stats.get('phase')))
        conn.commit()
        
    def get_chunk_history(self, chunk_id: int, limit: int = 5) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chunk_history WHERE chunk_id = ? ORDER BY recorded_at DESC LIMIT ?", (chunk_id, limit))
        return [dict(r) for r in cursor.fetchall()]

    def get_chunks_by_priority(self, limit: int = 10) -> List[Dict]:
        """Получает чанки, отсортированные по приоритету (только PENDING)"""
        return self.get_knowledge(status='PENDING', limit=limit)
    
    
    def get_chunk_children(self, parent_chunk_id: int) -> List[Dict]:
        """Получает все дочерние чанки для заданного родителя"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM ai_knowledge WHERE parent_chunk_id = ? ORDER BY priority DESC",
                (parent_chunk_id,)
            )
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    
    def get_chunk_parent(self, chunk_id: int) -> Optional[Dict]:
        """Получает родительский чанк"""
        chunk = self.get_chunk_by_id(chunk_id)
        if not chunk or not chunk.get('parent_chunk_id'):
            return None
        return self.get_chunk_by_id(chunk.get('parent_chunk_id'))
    
    
    def get_chunk_by_key_and_type(self, chunk_key: str, chunk_type: str) -> Optional[Dict]:
        """Получает чанк по ключу и типу"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM ai_knowledge WHERE chunk_key = ? AND chunk_type = ?",
                (chunk_key, chunk_type)
            )
            row = cursor.fetchone()
            return self._chunk_from_row(row) if row else None
        finally:
            conn.close()
    
    
    def get_pending_chunks(self) -> List[Dict]:
        """Получает все PENDING чанки"""
        return self.get_knowledge(status='PENDING', limit=999999)
    
    
    def get_ready_chunks(self) -> List[Dict]:
        """Получает все READY чанки"""
        return self.get_knowledge(status='READY', limit=999999)
    
    
    def get_recent_knowledge(self, limit: int = 10) -> List[Dict]:
        """Получает недавно обновлённые чанки"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM ai_knowledge ORDER BY last_updated DESC LIMIT ?",
                (limit,)
            )
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    
    def get_statistics(self) -> Dict:
        """Получает статистику БД знаний"""
        if self._stats_cache and time.time() - self._stats_cache_time < 60:
            return self._stats_cache
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM ai_knowledge")
            total = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM ai_knowledge WHERE status = 'READY'")
            ready = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM ai_knowledge WHERE status = 'PENDING'")
            pending = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM ai_knowledge WHERE chunk_type = 'PRODUCT'")
            products = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM ai_knowledge WHERE chunk_type = 'CATEGORY'")
            categories = cursor.fetchone()[0] or 0
            
            stats = {
                'total_chunks': total,
                'ready_chunks': ready,
                'pending_chunks': pending,
                'products': products,
                'categories': categories,
                'completion_rate': round(ready / total * 100, 1) if total > 0 else 0
            }
            
            self._stats_cache = stats
            self._stats_cache_time = time.time()
            
            return stats
        finally:
            conn.close()
    
    
    def get_status_summary(self) -> Dict:
        """Получает сводку статусов всех чанков"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM ai_knowledge
                GROUP BY status
            """)
            
            summary = {}
            for row in cursor.fetchall():
                summary[row[0]] = row[1]
            
            return summary
        finally:
            conn.close()
    
    
    def get_rag_context_for_item(self, item_title: str) -> Optional[Dict]:
        """Получает RAG контекст для товара (поиск по семантике)"""
        try:
            # Извлекаем семантику товара
            semantic = FeatureExtractor.extract_semantic_data(item_title)
            product_key = semantic.get('product_key')
            
            if not product_key:
                return None
            
            # Ищем соответствующий PRODUCT чанк
            chunk = self.get_chunk_by_key_and_type(product_key, 'PRODUCT')
            
            if not chunk or chunk.get('status') != 'READY':
                return None
            
            content = chunk.get('content', {})
            
            return {
                'chunk_id': chunk['id'],
                'chunk_key': chunk['chunk_key'],
                'knowledge': content.get('main_description', ''),
                'summary': chunk.get('summary', ''),
                'confidence': content.get('confidence', 0.5)
            }
        
        except Exception as e:
            logger.error(f"RAG context error: {e}")
            return None
    
    def get_rag_status(self) -> Dict:
        """Получает статус RAG (сколько чанков готово для RAG)"""
        stats = self.get_statistics()
        ready = stats.get('ready_chunks', 0)
        total = stats.get('total_chunks', 0)

        # FIX: Защита от деления на ноль
        if total > 0:
            coverage = round(ready / total * 100, 1)
            if ready / total > 0.7:
                status_str = 'GOOD'
            elif ready > 0:
                status_str = 'NEEDS_WORK'
            else:
                status_str = 'EMPTY'
        else:
            coverage = 0
            status_str = 'EMPTY'

        return {
            'rag_ready_chunks': ready,
            'total_chunks': total,
            'rag_coverage': coverage,
            'status': status_str
        }

    # === Export/Import ===

    def export_to_json(self, filepath: str):
        """Export knowledge to JSON."""
        chunks = self.get_knowledge(limit=999999)
        data = {
            'exported_at': datetime.now().isoformat(),
            'schema_version': self.SCHEMA_VERSION,
            'chunks': chunks
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.success(f"Exported {len(chunks)} knowledge chunks to {filepath}")

    def import_from_json(self, filepath: str, clear_first: bool = False):
        """Import knowledge from JSON."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if clear_first:
                cursor.execute("DELETE FROM ai_knowledge")

            for chunk in data.get('chunks', []):
                try:
                    self.add_knowledge(
                        chunk_type=chunk['chunk_type'],
                        chunk_key=chunk['chunk_key'],
                        title=chunk.get('title', ''),
                        content=chunk.get('content'),
                        status=chunk.get('status', 'PENDING'),
                        priority=chunk.get('priority', 1)
                    )
                except Exception as e:
                    logger.warning(f"Failed to import chunk {chunk.get('chunk_key')}: {e}")

            conn.commit()
            logger.success(f"Imported knowledge chunks from {filepath}")
        finally:
            conn.close()

    # === Reset ===

    def reset_database(self):
        """Completely reset the database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._ensure_db_exists()
        logger.info("Knowledge database reset complete")