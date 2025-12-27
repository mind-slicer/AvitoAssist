import sqlite3
import json
import os
import sys
from typing import List, Dict, Optional
from datetime import datetime

# Add workspace root to path for config imports
_workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from app.config import BASE_APP_DIR
from app.core.log_manager import logger


class KnowledgeManager:
    """
    Manages AI knowledge chunks with persistent storage.
    Supports chunk types: PRODUCT, CATEGORY, DATABASE, AI_BEHAVIOR, CUSTOM.
    """

    SCHEMA_VERSION = 2
    DB_FILENAME = "memory_knowledge.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(BASE_APP_DIR, self.DB_FILENAME)
        self._ensure_db_exists()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
        """Create all data tables."""
        # Create the main knowledge table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_type TEXT NOT NULL,
                chunk_key TEXT NOT NULL,
                title TEXT,
                content TEXT,
                summary TEXT,
                status TEXT DEFAULT 'PENDING',
                priority INTEGER DEFAULT 1,
                new_data_items_count INTEGER DEFAULT 0,
                last_cultivation_attempt TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chunk_type, chunk_key)
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_status ON ai_knowledge(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_chunk_key ON ai_knowledge(chunk_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_type ON ai_knowledge(chunk_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_knowledge_priority ON ai_knowledge(priority)")

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int, to_version: int):
        """Execute schema migrations."""
        if from_version < 2:
            # Create all tables for version 2
            self._create_all_tables(cursor)

    # === Basic CRUD ===

    def add_knowledge(self, chunk_type: str, chunk_key: str, title: str,
                      content: Optional[Dict] = None, status: str = 'PENDING',
                      priority: int = 1) -> int:
        """
        Add or update knowledge chunk.
        Returns the chunk id.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            content_json = json.dumps(content, ensure_ascii=False) if content else None

            # Check if exists
            cursor.execute(
                "SELECT id FROM ai_knowledge WHERE chunk_type = ? AND chunk_key = ?",
                (chunk_type, chunk_key)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing
                cursor.execute("""
                    UPDATE ai_knowledge SET
                        title = ?, content = ?, summary = NULL,
                        status = ?, priority = ?, new_data_items_count = 0,
                        last_updated = ?
                    WHERE id = ?
                """, (title, content_json, status, priority, datetime.now().isoformat(), existing[0]))
                return existing[0]
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO ai_knowledge (
                        chunk_type, chunk_key, title, content, status, priority, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (chunk_type, chunk_key, title, content_json, status, priority, datetime.now().isoformat()))
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def get_knowledge(self, chunk_id: Optional[int] = None,
                      chunk_key: Optional[str] = None,
                      chunk_type: Optional[str] = None,
                      status: Optional[str] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[Dict]:
        """Get knowledge chunks with filters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM ai_knowledge WHERE 1=1"
            params = []

            if chunk_id:
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

            query += " ORDER BY priority DESC, last_updated DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [self._chunk_from_row(row) for row in cursor.fetchall()]
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
        """Delete chunk by id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ai_knowledge WHERE id = ?", (chunk_id,))
            conn.commit()
            return cursor.rowcount > 0
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

    def update_chunk_content(self, chunk_id: int, content: Dict, summary: Optional[str] = None):
        """Update chunk content and summary."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            content_json = json.dumps(content, ensure_ascii=False)
            if summary is None:
                # Try to extract summary from content
                summary = content.get('summary') or content.get('analysis', {}).get('summary', '')
            cursor.execute("""
                UPDATE ai_knowledge SET
                    content = ?, summary = ?, status = 'READY',
                    new_data_items_count = 0, last_updated = ?
                WHERE id = ?
            """, (content_json, summary, datetime.now().isoformat(), chunk_id))
            conn.commit()
        finally:
            conn.close()

    def update_chunk_status(self, chunk_id: int, status: str, progress: Optional[int] = None):
        """Update chunk status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE ai_knowledge SET status = ?, last_cultivation_attempt = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), chunk_id))
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
        """Get all chunks with PENDING status."""
        return self.get_knowledge(status='PENDING', limit=9999)

    def get_ready_chunks(self) -> List[Dict]:
        """Get all chunks with READY status."""
        return self.get_knowledge(status='READY', limit=9999)

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
        """Get overall statistics."""
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

            return {
                'total_chunks': total,
                'by_status': status_summary,
                'product_chunks': product_count,
                'category_chunks': category_count
            }
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

    def get_rag_status(self) -> Dict:
        """Get RAG system status."""
        stats = self.get_statistics()
        status_summary = stats.get('by_status', {})
        return {
            'total_items': stats.get('total_chunks', 0),
            'total_categories': stats.get('category_chunks', 0),
            'ready_chunks': status_summary.get('READY', 0),
            'pending_chunks': status_summary.get('PENDING', 0),
            'failed_chunks': status_summary.get('FAILED', 0)
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