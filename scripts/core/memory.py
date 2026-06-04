"""ResearchMemory: Three-layer memory system for economic research agent.

Layers:
- Context layer (self.context): current session context, for filling prompts
- Short-term layer (self.short_term): last 20 operations, session-only
- Long-term layer (SQLite research.db): permanent knowledge store
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

# ─── Optional Dependencies ─────────────────────────────────────────────────────

try:
    import chromadb

    _CHROMADB_AVAILABLE = True
except ImportError:
    _CHROMADB_AVAILABLE = False
    chromadb = None

# ─── Data Types ────────────────────────────────────────────────────────────────


class ContextUnit(NamedTuple):
    """A single unit of context in the current session."""
    timestamp: float
    task: str
    result: Any          # Can be dict/list/str
    evaluation: str | None  # Filled by Reflection
    tools_used: list[str]


@dataclass
class Operation:
    """A single operation record in the short-term layer."""
    timestamp: float
    operation_type: str   # e.g. "tool_call", "task_complete", "user_input"
    description: str
    metadata: dict = field(default_factory=dict)


# ─── ResearchMemory ───────────────────────────────────────────────────────────


class ResearchMemory:
    """
    Three-layer memory system:
    - Context layer: self.context list[ContextUnit] — current session context
    - Short-term layer: self.short_term deque[Operation] — last 20 operations
    - Long-term layer: SQLite research.db — permanent knowledge store
    """

    _write_lock = threading.RLock()
    DEFAULT_DB_PATH = ".cache/research.db"

    def __init__(self, session_id: str, db_path: str | None = None):
        self.session_id = session_id
        self.db_path = db_path or self.DEFAULT_DB_PATH

        # In-memory layers
        self.context: list[ContextUnit] = []
        self.short_term: deque[Operation] = deque(maxlen=20)

        # SQLite layer
        self.db = self._connect_db()
        self._init_db()
        self._migrate_if_needed()

        # ChromaDB vector layer
        if _CHROMADB_AVAILABLE:
            chroma_path = Path(self.db_path).parent / "chromadb"
            self._chroma_client = chromadb.PersistentClient(path=str(chroma_path))
            self._vectors = self._chroma_client.get_or_create_collection("research_vectors")
        else:
            self._chroma_client = None
            self._vectors = None

    # ── SQLite helpers ────────────────────────────────────────────────────────

    def _connect_db(self) -> sqlite3.Connection:
        """Connect to SQLite, creating directories if needed."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they don't exist."""
        cursor = self.db.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contexts (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                timestamp REAL,
                task TEXT,
                result TEXT,
                evaluation TEXT,
                tools_used TEXT,
                is_compressed INTEGER DEFAULT 0,
                UNIQUE(session_id, timestamp)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                key TEXT,
                value TEXT,
                tags TEXT,
                timestamp REAL,
                UNIQUE(session_id, key)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at REAL,
                updated_at REAL,
                state TEXT,
                summary TEXT
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_tags ON knowledge(tags)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_contexts_session ON contexts(session_id)"
        )

        # Track ChromaDB vector entries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                chroma_id TEXT,
                metadata TEXT,
                timestamp REAL,
                UNIQUE(session_id, chroma_id)
            )
        """)

        with self._write_lock:
            self.db.commit()

    def _migrate_if_needed(self):
        """Add is_compressed column to contexts if missing (v1 -> v2 migration)."""
        cursor = self.db.cursor()
        try:
            cursor.execute("SELECT is_compressed FROM contexts LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE contexts ADD COLUMN is_compressed INTEGER DEFAULT 0")
            with self._write_lock:
                self.db.commit()

    # ── Core operations ───────────────────────────────────────────────────────

    def push(self, task: str, result: Any, metadata: dict) -> ContextUnit:
        """
        Record task execution result to all layers.
        Writes to context layer and short-term layer.
        Optionally writes to long-term layer if metadata indicates persistence.
        """
        timestamp = time.time()
        tools_used = metadata.get("tools", [])

        # Build ContextUnit
        unit = ContextUnit(
            timestamp=timestamp,
            task=task,
            result=result,
            evaluation=None,
            tools_used=tools_used,
        )

        # Context layer
        self.context.append(unit)

        # Short-term layer
        self.short_term.append(Operation(
            timestamp=timestamp,
            operation_type=metadata.get("type", "task_complete"),
            description=task,
            metadata={"result": result, **metadata},
        ))

        # Long-term layer (always write to SQLite for persistence)
        self._write_context_to_db(unit)

        # Auto-compress if too many items — caller should invoke compress_context() explicitly
        # if len(self.context) > 20:
        #     self.compress_context()

        return unit

    def _write_context_to_db(self, unit: ContextUnit):
        """Write a single ContextUnit to SQLite."""
        is_compressed = 1 if unit.task.startswith("[压缩摘要]") else 0
        with self._write_lock:
            cursor = self.db.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO contexts
                        (session_id, timestamp, task, result, evaluation, tools_used, is_compressed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.session_id,
                        unit.timestamp,
                        unit.task,
                        json.dumps(unit.result, ensure_ascii=False),
                        unit.evaluation,
                        json.dumps(unit.tools_used, ensure_ascii=False),
                        is_compressed,
                    ),
                )
                self.db.commit()
            except sqlite3.Error as exc:
                self.db.rollback()
                warnings.warn(
                    f"[ResearchMemory] DB write failed: {exc}. Data may not persist.",
                    stacklevel=2,
                )

    def get_context(self, limit: int = 10) -> list[ContextUnit]:
        """
        Get recent context units for prompt filling.
        Returns the most recent `limit` items from in-memory context.
        """
        return self.context[-limit:]

    def update_evaluation(self, timestamp: float, evaluation: str):
        """
        Update the evaluation field of a ContextUnit.
        Called by Reflection after evaluating a task result.
        """
        # Update in-memory context
        for i, unit in enumerate(self.context):
            if abs(unit.timestamp - timestamp) < 1e-6:
                self.context[i] = ContextUnit(
                    timestamp=unit.timestamp,
                    task=unit.task,
                    result=unit.result,
                    evaluation=evaluation,
                    tools_used=unit.tools_used,
                )
                break

        # Update in SQLite
        with self._write_lock:
            cursor = self.db.cursor()
            try:
                cursor.execute(
                    "UPDATE contexts SET evaluation = ? "
                    "WHERE session_id = ? AND is_compressed = 0 AND ABS(timestamp - ?) < 1e-6",
                    (evaluation, self.session_id, timestamp),
                )
                self.db.commit()
            except sqlite3.Error:
                self.db.rollback()

    # ── Long-term knowledge ───────────────────────────────────────────────────

    def store_knowledge(
        self,
        key: str,
        value: Any,
        tags: list[str],
        ttl: float | None = None,
    ):
        """
        Store knowledge to the long-term SQLite knowledge base.

        Args:
            key: Unique identifier (e.g. "paper:2312.00001")
            value: Serializable value to store
            tags: List of tag strings for retrieval
            ttl: Optional time-to-live in seconds (None = permanent).
                 Note: `ttl` parameter is accepted for future implementation.
                 Currently TTL is not enforced on retrieval.

        Returns:
            None
        """
        timestamp = time.time()

        with self._write_lock:
            cursor = self.db.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO knowledge
                        (session_id, key, value, tags, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.session_id,
                        key,
                        json.dumps(value, ensure_ascii=False),
                        json.dumps(tags, ensure_ascii=False),
                        timestamp,
                    ),
                )
                self.db.commit()
            except sqlite3.Error as e:
                self.db.rollback()
                raise RuntimeError(f"Failed to store knowledge: {e}") from e

    def retrieve(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Semantic retrieval of long-term knowledge.

        Args:
            query: Text query to match against key and value (SQL LIKE)
            tags: Filter by tags (all tags must match)
            limit: Maximum number of results

        Returns:
            List of matching knowledge entries as dicts.
        """
        cursor = self.db.cursor()

        conditions = ["session_id = ?"]
        params: list[Any] = [self.session_id]

        if query:
            conditions.append("(key LIKE ? OR value LIKE ?)")
            like_pattern = f"%{query}%"
            params.extend([like_pattern, like_pattern])

        if tags:
            # All specified tags must be present in the entry's tags
            for tag in tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT key, value, tags, timestamp
            FROM knowledge
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to retrieve knowledge: {e}") from e

        results = []
        for row in rows:
            results.append({
                "key": row["key"],
                "value": json.loads(row["value"]),
                "tags": json.loads(row["tags"]),
                "timestamp": row["timestamp"],
            })

        return results

    # ── Context compression ──────────────────────────────────────────────────

    def compress_context(self, max_items: int = 2):
        """
        Compress context when it exceeds 20 items.

        Replaces older items with a single "compressed" ContextUnit that
        contains the count and a brief text summary. Uses LOGICAL compression
        (is_compressed flag) instead of DELETE+INSERT to avoid data loss on crash.

        After compression, total items in DB = compressed record + max_items kept.
        """
        if len(self.context) <= max_items:
            return

        keep = self.context[-max_items:]
        to_summarize = self.context[:-max_items]

        # Build a summary string from older items
        summary_parts = []
        for unit in to_summarize:
            result_str = str(unit.result)[:200]
            summary_parts.append(
                f"[{time.strftime('%H:%M:%S', time.localtime(unit.timestamp))}] "
                f"{unit.task}: {result_str}"
            )
        summary_text = " | ".join(summary_parts)

        # Create compressed unit (stored as is_compressed=1 in DB)
        compressed = ContextUnit(
            timestamp=time.time(),
            task=f"[压缩摘要] {len(to_summarize)} 个历史任务",
            result={"summary": summary_text, "count": len(to_summarize)},
            evaluation=None,
            tools_used=[],
        )

        # Logical compression: mark old records as compressed instead of deleting them
        with self._write_lock:
            cursor = self.db.cursor()
            try:
                cursor.execute(
                    "UPDATE contexts SET is_compressed = 1 "
                    "WHERE session_id = ? AND is_compressed = 0",
                    (self.session_id,),
                )
                # Write compressed unit and keep items as non-compressed
                self._write_context_to_db(compressed)
                for unit in keep:
                    self._write_context_to_db(unit)
                self.db.commit()
            except sqlite3.Error:
                self.db.rollback()
                # Fallback: keep in-memory state, DB will be inconsistent
                # but no data is lost

        self.context = [compressed] + keep

    # ── Session persistence ───────────────────────────────────────────────────

    def save_session(self):
        """
        Serialize the full session state to SQLite.
        Stores context + short_term + metadata in the sessions table.
        """
        state = self.to_dict()
        now = time.time()

        with self._write_lock:
            cursor = self.db.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO sessions
                        (session_id, created_at, updated_at, state, summary)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.session_id,
                        state.get("created_at", now),
                        now,
                        json.dumps(state, ensure_ascii=False),
                        state.get("summary", ""),
                    ),
                )
                self.db.commit()
            except sqlite3.Error as e:
                self.db.rollback()
                raise RuntimeError(f"Failed to save session: {e}") from e

    @staticmethod
    def load_session(
        session_id: str,
        db_path: str | None = None,
    ) -> ResearchMemory:
        """
        Restore a historical session from SQLite.

        Returns a new ResearchMemory instance populated with
        the saved session's context and state.
        """
        path = db_path or ResearchMemory.DEFAULT_DB_PATH

        # If the DB doesn't exist, return empty memory
        if not os.path.exists(path):
            return ResearchMemory(session_id, db_path=path)

        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT state FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            # Session not found — return fresh memory
            return ResearchMemory(session_id, db_path=path)

        state = json.loads(row["state"])
        return ResearchMemory.from_dict(state, db_path=path)

    def to_dict(self) -> dict:
        """
        Serialize the full memory state to a dict.
        Used for session persistence.
        """
        return {
            "session_id": self.session_id,
            "db_path": self.db_path,
            "context": [
                {
                    "timestamp": u.timestamp,
                    "task": u.task,
                    "result": u.result,
                    "evaluation": u.evaluation,
                    "tools_used": u.tools_used,
                    "is_compressed": u.task.startswith("[压缩摘要]"),
                }
                for u in self.context
            ],
            "short_term": [
                {
                    "timestamp": o.timestamp,
                    "operation_type": o.operation_type,
                    "description": o.description,
                    "metadata": o.metadata,
                }
                for o in self.short_term
            ],
            "created_at": getattr(self, "_created_at", time.time()),
            "summary": self._generate_summary(),
        }

    def _generate_summary(self) -> str:
        """Generate a brief summary of the session."""
        if not self.context:
            return "Empty session"
        tasks = [u.task for u in self.context[-5:]]
        return f"Recent tasks: {'; '.join(tasks)}"

    @staticmethod
    def from_dict(data: dict, db_path: str | None = None) -> ResearchMemory:
        """
        Deserialize from a dict and restore in-memory state.
        Note: In-memory layers are restored, but SQLite is NOT re-written
        (session is assumed to already be in the DB).
        """
        session_id = data["session_id"]
        path = db_path or data.get("db_path", ResearchMemory.DEFAULT_DB_PATH)

        mem = ResearchMemory(session_id, db_path=path)

        # Restore context
        mem.context = []
        for item in data.get("context", []):
            mem.context.append(ContextUnit(
                timestamp=item["timestamp"],
                task=item["task"],
                result=item["result"],
                evaluation=item.get("evaluation"),
                tools_used=item.get("tools_used", []),
            ))

        # Restore short_term
        mem.short_term = deque(maxlen=20)
        for item in data.get("short_term", []):
            mem.short_term.append(Operation(
                timestamp=item["timestamp"],
                operation_type=item["operation_type"],
                description=item["description"],
                metadata=item.get("metadata", {}),
            ))

        mem._created_at = data.get("created_at", time.time())

        return mem

    # ── Vector search (ChromaDB) ────────────────────────────────────────────────

    def add_vector(self, text: str, metadata: dict) -> str | None:
        """
        Add a text entry to the ChromaDB vector store.

        Args:
            text: The text content to embed and store.
            metadata: Metadata dict to store alongside the text.

        Returns:
            The ChromaDB entry ID if successful, None if ChromaDB unavailable.
        """
        if not _CHROMADB_AVAILABLE or self._vectors is None:
            warnings.warn(
                "[ResearchMemory] ChromaDB not available. "
                "Install with: pip install chromadb",
                stacklevel=2,
            )
            return None

        # Include session_id in metadata
        enriched_metadata = {**metadata, "session_id": self.session_id}

        try:
            # Generate unique ID for the entry
            chroma_id = f"{self.session_id}_{int(time.time() * 1000)}"
            # ChromaDB auto-embeds using default all-MiniLM-L6-v2 model
            self._vectors.add(
                documents=[text],
                metadatas=[enriched_metadata],
                ids=[chroma_id],
            )
            with self._write_lock:
                cursor = self.db.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO vectors (session_id, chroma_id, metadata, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (self.session_id, chroma_id, json.dumps(enriched_metadata, ensure_ascii=False), time.time()),
                )
                self.db.commit()

            return chroma_id
        except Exception as exc:
            warnings.warn(f"[ResearchMemory] Vector add failed: {exc}", stacklevel=2)
            return None

    def search_vector(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Search the ChromaDB vector store for similar entries.

        Args:
            query: The text query to search for.
            top_k: Maximum number of results to return.

        Returns:
            List of dicts with {"text", "metadata", "distance"} keys,
            filtered to current session_id.
        """
        if not _CHROMADB_AVAILABLE or self._vectors is None:
            warnings.warn(
                "[ResearchMemory] ChromaDB not available. "
                "Install with: pip install chromadb",
                stacklevel=2,
            )
            return []

        try:
            results = self._vectors.query(
                query_texts=[query],
                n_results=top_k,
                where={"session_id": self.session_id},
            )

            output = []
            for i, doc in enumerate(results.get("documents", [[]])[0]):
                output.append({
                    "text": doc,
                    "metadata": results.get("metadatas", [[{}]])[0][i] if results.get("metadatas") else {},
                    "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None,
                })
            return output
        except Exception as exc:
            warnings.warn(f"[ResearchMemory] Vector search failed: {exc}", stacklevel=2)
            return []

    def __del__(self):
        """Close database connection on cleanup."""
        try:
            if hasattr(self, "db") and self.db:
                self.db.close()
        except Exception:
            pass
