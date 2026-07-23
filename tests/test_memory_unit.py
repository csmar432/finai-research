"""Unit tests for scripts/core/memory.py"""

import os
import tempfile
import time
from collections import deque

import pytest

from scripts.core.memory import ContextUnit, Operation, ResearchMemory


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path for tests."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    return str(db_dir / "test_research.db")


@pytest.fixture
def memory(temp_db_path):
    """Create a fresh ResearchMemory instance for each test."""
    mem = ResearchMemory(session_id="test_session", db_path=temp_db_path)
    yield mem
    mem.db.close()


@pytest.fixture
def memory_with_data(memory):
    """Create memory with some initial data."""
    memory.push(
        task="First task",
        result={"output": "result1"},
        metadata={"type": "tool_call", "tools": ["tool_a"]},
    )
    memory.push(
        task="Second task",
        result={"output": "result2"},
        metadata={"type": "tool_call", "tools": ["tool_b"]},
    )
    return memory


# ─── ContextUnit NamedTuple Tests ──────────────────────────────────────────


class TestContextUnit:
    """Tests for the ContextUnit NamedTuple."""

    def test_context_unit_creation(self):
        """Test ContextUnit creation with all fields."""
        unit = ContextUnit(
            timestamp=1234567890.0,
            task="Test task",
            result={"key": "value"},
            evaluation="success",
            tools_used=["tool1", "tool2"],
        )
        assert unit.timestamp == 1234567890.0
        assert unit.task == "Test task"
        assert unit.result == {"key": "value"}
        assert unit.evaluation == "success"
        assert unit.tools_used == ["tool1", "tool2"]

    def test_context_unit_defaults(self):
        """Test ContextUnit with minimal fields (no defaults available in NamedTuple)."""
        unit = ContextUnit(
            timestamp=1234567890.0,
            task="Minimal task",
            result="simple result",
            evaluation=None,
            tools_used=[],
        )
        assert unit.evaluation is None
        assert unit.tools_used == []

    def test_context_unit_immutable(self):
        """Test that ContextUnit is immutable."""
        unit = ContextUnit(
            timestamp=1234567890.0,
            task="Immutable task",
            result="data",
            evaluation=None,
            tools_used=[],
        )
        with pytest.raises(AttributeError):
            unit.timestamp = 9999999999.0

    def test_context_unit_indexing(self):
        """Test ContextUnit field access via index."""
        unit = ContextUnit(
            timestamp=1000.0,
            task="Indexed task",
            result="result_data",
            evaluation="good",
            tools_used=["t1"],
        )
        assert unit[0] == 1000.0
        assert unit[1] == "Indexed task"
        assert unit[2] == "result_data"

    def test_context_unit_fields(self):
        """Test ContextUnit _fields attribute."""
        assert ContextUnit._fields == (
            "timestamp",
            "task",
            "result",
            "evaluation",
            "tools_used",
        )


# ─── Operation Dataclass Tests ─────────────────────────────────────────────


class TestOperation:
    """Tests for the Operation dataclass."""

    def test_operation_required_fields(self):
        """Test Operation with all required fields."""
        op = Operation(
            timestamp=1234567890.0,
            operation_type="tool_call",
            description="Called tool X",
        )
        assert op.timestamp == 1234567890.0
        assert op.operation_type == "tool_call"
        assert op.description == "Called tool X"
        assert op.metadata == {}

    def test_operation_all_fields(self):
        """Test Operation with all fields including optional metadata."""
        op = Operation(
            timestamp=1234567890.0,
            operation_type="task_complete",
            description="Task finished",
            metadata={"duration": 5.0, "status": "success"},
        )
        assert op.metadata == {"duration": 5.0, "status": "success"}

    def test_operation_defaults(self):
        """Test Operation default values for metadata."""
        op = Operation(
            timestamp=1234567890.0,
            operation_type="user_input",
            description="User typed something",
        )
        assert op.metadata == {}

    def test_operation_mutable(self):
        """Test that Operation metadata is mutable dict."""
        op = Operation(
            timestamp=1234567890.0,
            operation_type="test",
            description="Test operation",
        )
        op.metadata["new_key"] = "new_value"
        assert op.metadata == {"new_key": "new_value"}


# ─── ResearchMemory Init Tests ─────────────────────────────────────────────


class TestResearchMemoryInit:
    """Tests for ResearchMemory initialization."""

    def test_init_creates_session_id(self, temp_db_path):
        """Test that init sets session_id correctly."""
        mem = ResearchMemory(session_id="my_session", db_path=temp_db_path)
        assert mem.session_id == "my_session"

    def test_init_default_db_path(self):
        """Test that init uses default DB path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = ResearchMemory(session_id="test", db_path=os.path.join(tmpdir, "test.db"))
            assert mem.db_path == os.path.join(tmpdir, "test.db")

    def test_init_creates_db_directory(self, tmp_path):
        """Test that init creates DB directory if it doesn't exist."""
        db_path = tmp_path / "nested" / "dir" / "test.db"
        assert not db_path.parent.exists()
        mem = ResearchMemory(session_id="test", db_path=str(db_path))
        assert db_path.parent.exists()

    def test_init_context_empty(self, memory):
        """Test that context layer starts empty."""
        assert memory.context == []

    def test_init_short_term_empty(self, memory):
        """Test that short_term layer starts as empty deque."""
        assert len(memory.short_term) == 0
        assert isinstance(memory.short_term, deque)

    def test_init_creates_tables(self, memory):
        """Test that _init_db creates required tables."""
        cursor = memory.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "contexts" in tables
        assert "knowledge" in tables
        assert "sessions" in tables
        assert "vectors" in tables

    def test_init_creates_indexes(self, memory):
        """Test that _init_db creates indexes."""
        cursor = memory.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_knowledge_tags" in indexes
        assert "idx_contexts_session" in indexes


# ─── ResearchMemory.push Tests ──────────────────────────────────────────────


class TestResearchMemoryPush:
    """Tests for ResearchMemory.push method."""

    def test_push_basic(self, memory):
        """Test basic push to all layers."""
        unit = memory.push(
            task="Process data",
            result={"processed": True},
            metadata={"type": "tool_call", "tools": ["pandas"]},
        )

        assert isinstance(unit, ContextUnit)
        assert unit.task == "Process data"
        assert unit.result == {"processed": True}
        assert unit.tools_used == ["pandas"]

    def test_push_updates_context_layer(self, memory):
        """Test that push adds to context layer."""
        memory.push(task="Task 1", result="R1", metadata={})
        memory.push(task="Task 2", result="R2", metadata={})

        assert len(memory.context) == 2
        assert memory.context[0].task == "Task 1"
        assert memory.context[1].task == "Task 2"

    def test_push_updates_short_term_layer(self, memory):
        """Test that push adds to short_term layer."""
        memory.push(
            task="Operation 1",
            result="R1",
            metadata={"type": "task_complete", "extra": "data"},
        )
        memory.push(
            task="Operation 2",
            result="R2",
            metadata={"type": "tool_call"},
        )

        assert len(memory.short_term) == 2
        assert memory.short_term[0].operation_type == "task_complete"
        assert memory.short_term[1].operation_type == "tool_call"

    def test_push_writes_to_db(self, memory, temp_db_path):
        """Test that push writes to SQLite."""
        memory.push(task="DB Test", result={"value": 42}, metadata={})

        conn = memory.db
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM contexts WHERE task = ?", ("DB Test",))
        count = cursor.fetchone()[0]
        assert count == 1

    def test_push_without_tools(self, memory):
        """Test push with metadata without tools key."""
        unit = memory.push(task="No tools", result="result", metadata={})
        assert unit.tools_used == []

    def test_push_with_complex_result(self, memory):
        """Test push with complex nested result."""
        complex_result = {
            "regression": {
                "coefficients": [0.5, -0.3, 0.1],
                "p_values": [0.01, 0.05, 0.2],
            },
            "n_obs": 1000,
        }
        unit = memory.push(
            task="Run regression",
            result=complex_result,
            metadata={"tools": ["statsmodels"]},
        )
        assert unit.result == complex_result
        assert unit.result["n_obs"] == 1000


# ─── ResearchMemory.get_context Tests ───────────────────────────────────────


class TestResearchMemoryGetContext:
    """Tests for ResearchMemory.get_context method."""

    def test_get_context_default_limit(self, memory_with_data):
        """Test get_context with default limit."""
        result = memory_with_data.get_context()
        assert len(result) == 2

    def test_get_context_custom_limit(self, memory_with_data):
        """Test get_context with custom limit."""
        result = memory_with_data.get_context(limit=1)
        assert len(result) == 1
        assert result[0].task == "Second task"

    def test_get_context_limit_exceeds_data(self, memory_with_data):
        """Test get_context when limit exceeds available data."""
        result = memory_with_data.get_context(limit=100)
        assert len(result) == 2

    def test_get_context_empty_memory(self, memory):
        """Test get_context on empty memory."""
        result = memory.get_context()
        assert result == []


# ─── ResearchMemory.update_evaluation Tests ────────────────────────────────


class TestResearchMemoryUpdateEvaluation:
    """Tests for ResearchMemory.update_evaluation method."""

    def test_update_evaluation_in_memory(self, memory):
        """Test update_evaluation modifies in-memory context."""
        unit = memory.push(task="Eval test", result="data", metadata={})
        timestamp = unit.timestamp

        memory.update_evaluation(timestamp, "Task completed successfully")

        # Check in-memory
        updated = memory.context[-1]
        assert updated.evaluation == "Task completed successfully"

    def test_update_evaluation_in_db(self, memory):
        """Test update_evaluation modifies SQLite."""
        unit = memory.push(task="DB eval test", result="data", metadata={})
        timestamp = unit.timestamp

        memory.update_evaluation(timestamp, "Saved to DB")

        # Check in DB
        cursor = memory.db.cursor()
        cursor.execute(
            "SELECT evaluation FROM contexts WHERE ABS(timestamp - ?) < 1e-6",
            (timestamp,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Saved to DB"

    def test_update_evaluation_nonexistent_timestamp(self, memory):
        """Test update_evaluation with non-matching timestamp."""
        # Should not raise
        memory.update_evaluation(9999999999.999, "No match")


# ─── ResearchMemory.store_knowledge Tests ───────────────────────────────────


class TestResearchMemoryStoreKnowledge:
    """Tests for ResearchMemory.store_knowledge method."""

    def test_store_knowledge_basic(self, memory):
        """Test basic knowledge storage."""
        memory.store_knowledge(
            key="paper:2024.00001",
            value={"title": "Test Paper", "authors": ["A", "B"]},
            tags=["finance", "empirical"],
        )

        result = memory.retrieve(query="paper")
        assert len(result) == 1
        assert result[0]["key"] == "paper:2024.00001"
        assert result[0]["value"]["title"] == "Test Paper"

    def test_store_knowledge_with_ttl(self, memory):
        """Test knowledge storage with TTL (parameter accepted, not enforced)."""
        # TTL is accepted but not currently enforced
        memory.store_knowledge(
            key="temp:data",
            value={"ephemeral": True},
            tags=["temp"],
            ttl=3600,  # 1 hour
        )

        # Should still store successfully
        result = memory.retrieve(query="ephemeral")
        assert len(result) == 1

    def test_store_knowledge_replaces_existing(self, memory):
        """Test that storing same key replaces existing value."""
        memory.store_knowledge(
            key="update:test",
            value={"version": 1},
            tags=["test"],
        )
        memory.store_knowledge(
            key="update:test",
            value={"version": 2},
            tags=["test"],
        )

        result = memory.retrieve(query="update")
        assert len(result) == 1
        assert result[0]["value"]["version"] == 2

    def test_store_knowledge_multiple_tags(self, memory):
        """Test storing with multiple tags."""
        memory.store_knowledge(
            key="multi:tag",
            value={"data": "test"},
            tags=["tag1", "tag2", "tag3"],
        )

        result = memory.retrieve(tags=["tag1", "tag2"])
        assert len(result) == 1


# ─── ResearchMemory.retrieve Tests ─────────────────────────────────────────


class TestResearchMemoryRetrieve:
    """Tests for ResearchMemory.retrieve method."""

    def test_retrieve_by_query(self, memory):
        """Test retrieve with text query."""
        memory.store_knowledge(
            key="carbon:trading",
            value={"topic": "carbon emissions"},
            tags=["environmental"],
        )
        memory.store_knowledge(
            key="equity:pricing",
            value={"topic": "stock valuation"},
            tags=["finance"],
        )

        result = memory.retrieve(query="carbon")
        assert len(result) == 1
        assert result[0]["key"] == "carbon:trading"

    def test_retrieve_by_tags(self, memory):
        """Test retrieve with tag filter."""
        memory.store_knowledge(key="k1", value={"v": 1}, tags=["finance", "empirical"])
        memory.store_knowledge(key="k2", value={"v": 2}, tags=["finance", "theory"])
        memory.store_knowledge(key="k3", value={"v": 3}, tags=["marketing"])

        result = memory.retrieve(tags=["finance"])
        assert len(result) == 2

    def test_retrieve_query_and_tags(self, memory):
        """Test retrieve with both query and tags."""
        memory.store_knowledge(key="k1", value={"data": "test1"}, tags=["finance"])
        memory.store_knowledge(key="k2", value={"data": "test2"}, tags=["finance"])
        memory.store_knowledge(key="k3", value={"data": "nomatch"}, tags=["finance"])

        result = memory.retrieve(query="test1", tags=["finance"])
        assert len(result) == 1

    def test_retrieve_limit(self, memory):
        """Test retrieve respects limit."""
        for i in range(10):
            memory.store_knowledge(
                key=f"limit:test:{i}",
                value={"index": i},
                tags=["test"],
            )

        result = memory.retrieve(tags=["test"], limit=3)
        assert len(result) == 3

    def test_retrieve_no_match(self, memory):
        """Test retrieve with no matching results."""
        memory.store_knowledge(key="a", value={"v": 1}, tags=["x"])
        result = memory.retrieve(query="nonexistent")
        assert len(result) == 0

    def test_retrieve_returns_dicts(self, memory):
        """Test retrieve returns properly formatted dicts."""
        memory.store_knowledge(
            key="format:test",
            value={"nested": {"key": "value"}},
            tags=["test"],
        )

        result = memory.retrieve(tags=["test"])
        assert len(result) == 1
        entry = result[0]
        assert "key" in entry
        assert "value" in entry
        assert "tags" in entry
        assert "timestamp" in entry
        assert isinstance(entry["value"], dict)


# ─── ResearchMemory.compress_context Tests ──────────────────────────────────


class TestResearchMemoryCompressContext:
    """Tests for ResearchMemory.compress_context method."""

    def test_compress_context_no_op_when_small(self, memory):
        """Test compress_context does nothing when context is small."""
        memory.push(task="Small 1", result={}, metadata={})
        memory.push(task="Small 2", result={}, metadata={})

        memory.compress_context(max_items=5)
        assert len(memory.context) == 2

    def test_compress_context_merges_old_items(self, memory):
        """Test compress_context merges older items."""
        for i in range(5):
            memory.push(task=f"Task {i}", result={"n": i}, metadata={})

        memory.compress_context(max_items=2)
        assert len(memory.context) == 3  # 1 compressed + 2 kept

    def test_compress_context_creates_compressed_unit(self, memory):
        """Test compress_context creates unit with [压缩摘要] prefix."""
        for i in range(4):
            memory.push(task=f"Compress Test {i}", result={}, metadata={})

        memory.compress_context(max_items=2)

        compressed = memory.context[0]
        assert compressed.task.startswith("[压缩摘要]")
        # max_items=2, so 4-2=2 items are compressed
        assert compressed.result["count"] == 2

    def test_compress_context_keeps_recent_items(self, memory):
        """Test compress_context keeps the most recent items."""
        for i in range(5):
            memory.push(task=f"Keep {i}", result={"idx": i}, metadata={})

        memory.compress_context(max_items=2)

        # Check that recent items are preserved
        recent = memory.context[-1]
        assert "Keep 4" in recent.task


# ─── ResearchMemory.save_session / load_session Tests ───────────────────────


class TestResearchMemorySessionPersistence:
    """Tests for session persistence methods."""

    def test_save_and_load_session(self, temp_db_path):
        """Test save_session and load_session roundtrip."""
        # Create and populate memory
        mem1 = ResearchMemory(session_id="persist_session", db_path=temp_db_path)
        mem1.push(task="Session Task 1", result={"r": 1}, metadata={})
        mem1.push(task="Session Task 2", result={"r": 2}, metadata={})
        mem1.save_session()
        mem1.db.close()

        # Load session
        mem2 = ResearchMemory.load_session(session_id="persist_session", db_path=temp_db_path)

        assert mem2.session_id == "persist_session"
        assert len(mem2.context) == 2
        assert mem2.context[0].task == "Session Task 1"
        assert mem2.context[1].task == "Session Task 2"

    def test_load_session_nonexistent(self, temp_db_path):
        """Test load_session returns new memory for nonexistent session."""
        mem = ResearchMemory.load_session(
            session_id="nonexistent_session",
            db_path=temp_db_path,
        )
        assert mem.session_id == "nonexistent_session"
        assert len(mem.context) == 0

    def test_load_session_nonexistent_db_file(self, temp_db_path):
        """Test load_session with non-existent DB file."""
        nonexistent_path = os.path.join(os.path.dirname(temp_db_path), "nonexistent.db")
        mem = ResearchMemory.load_session(
            session_id="new_session",
            db_path=nonexistent_path,
        )
        assert mem.session_id == "new_session"


# ─── ResearchMemory.to_dict / from_dict Tests ───────────────────────────────


class TestResearchMemorySerialization:
    """Tests for to_dict and from_dict serialization methods."""

    def test_to_dict_basic(self, memory_with_data):
        """Test to_dict produces correct structure."""
        d = memory_with_data.to_dict()

        assert "session_id" in d
        assert "db_path" in d
        assert "context" in d
        assert "short_term" in d
        assert "created_at" in d
        assert "summary" in d

    def test_to_dict_context_items(self, memory_with_data):
        """Test to_dict includes context items."""
        d = memory_with_data.to_dict()

        assert len(d["context"]) == 2
        assert d["context"][0]["task"] == "First task"
        assert d["context"][0]["result"] == {"output": "result1"}

    def test_to_dict_short_term_items(self, memory_with_data):
        """Test to_dict includes short_term items."""
        d = memory_with_data.to_dict()

        assert len(d["short_term"]) == 2
        assert d["short_term"][0]["operation_type"] == "tool_call"

    def test_to_dict_summary(self, memory_with_data):
        """Test to_dict generates summary."""
        d = memory_with_data.to_dict()
        assert isinstance(d["summary"], str)
        assert len(d["summary"]) > 0

    def test_to_dict_empty_session(self, memory):
        """Test to_dict on empty memory."""
        d = memory.to_dict()
        assert d["context"] == []
        assert d["short_term"] == []
        assert d["summary"] == "Empty session"

    def test_from_dict_basic(self, temp_db_path):
        """Test from_dict restores memory state."""
        data = {
            "session_id": "restored_session",
            "db_path": temp_db_path,
            "context": [
                {
                    "timestamp": 1000.0,
                    "task": "Restored Task",
                    "result": {"restored": True},
                    "evaluation": None,
                    "tools_used": ["tool_x"],
                }
            ],
            "short_term": [
                {
                    "timestamp": 1000.0,
                    "operation_type": "restored_op",
                    "description": "Restored operation",
                    "metadata": {},
                }
            ],
            "created_at": 1000.0,
        }

        mem = ResearchMemory.from_dict(data, db_path=temp_db_path)

        assert mem.session_id == "restored_session"
        assert len(mem.context) == 1
        assert mem.context[0].task == "Restored Task"
        assert len(mem.short_term) == 1
        assert mem.short_term[0].operation_type == "restored_op"

    def test_from_dict_empty_context(self, temp_db_path):
        """Test from_dict with empty context."""
        data = {
            "session_id": "empty_session",
            "db_path": temp_db_path,
            "context": [],
            "short_term": [],
            "created_at": time.time(),
        }

        mem = ResearchMemory.from_dict(data, db_path=temp_db_path)
        assert mem.context == []
        assert len(mem.short_term) == 0

    def test_roundtrip_to_from(self, memory_with_data, temp_db_path):
        """Test roundtrip: to_dict -> from_dict."""
        d = memory_with_data.to_dict()
        mem2 = ResearchMemory.from_dict(d, db_path=temp_db_path)

        assert mem2.session_id == memory_with_data.session_id
        assert len(mem2.context) == len(memory_with_data.context)


# ─── ResearchMemory._generate_summary Tests ─────────────────────────────────


class TestResearchMemorySummary:
    """Tests for _generate_summary method."""

    def test_generate_summary_empty(self, memory):
        """Test summary generation for empty memory."""
        summary = memory._generate_summary()
        assert summary == "Empty session"

    def test_generate_summary_with_tasks(self, memory_with_data):
        """Test summary generation includes recent tasks."""
        summary = memory_with_data._generate_summary()
        assert "First task" in summary
        assert "Second task" in summary
        assert "Recent tasks:" in summary


# ─── ResearchMemory.Vector Tests ─────────────────────────────────────────────


class TestResearchMemoryVector:
    """Tests for ChromaDB vector operations."""

    def test_add_vector_chromadb_unavailable(self, memory, monkeypatch):
        """Test add_vector when ChromaDB is not available."""
        # Mock _CHROMADB_AVAILABLE to False
        import scripts.core.memory as memory_module

        monkeypatch.setattr(memory_module, "_CHROMADB_AVAILABLE", False)

        result = memory.add_vector(text="test content", metadata={"source": "test"})
        assert result is None

    def test_search_vector_chromadb_unavailable(self, memory, monkeypatch):
        """Test search_vector when ChromaDB is not available."""
        import scripts.core.memory as memory_module

        monkeypatch.setattr(memory_module, "_CHROMADB_AVAILABLE", False)

        result = memory.search_vector(query="test query", top_k=5)
        assert result == []

    def test_add_vector_no_vectors_attribute(self, memory):
        """Test add_vector when _vectors is None."""
        memory._vectors = None

        result = memory.add_vector(text="test", metadata={})
        assert result is None

    def test_search_vector_no_vectors_attribute(self, memory):
        """Test search_vector when _vectors is None."""
        memory._vectors = None

        result = memory.search_vector(query="test", top_k=5)
        assert result == []


# ─── ResearchMemory._write_context_to_db Tests ──────────────────────────────


class TestResearchMemoryDBWrite:
    """Tests for _write_context_to_db method."""

    def test_write_context_to_db_basic(self, memory):
        """Test _write_context_to_db inserts correctly."""
        unit = ContextUnit(
            timestamp=time.time(),
            task="DB write test",
            result={"key": "value"},
            evaluation=None,
            tools_used=["tool_a"],
        )

        memory._write_context_to_db(unit)

        cursor = memory.db.cursor()
        cursor.execute("SELECT task, result, tools_used FROM contexts WHERE task = ?", ("DB write test",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "DB write test"
        assert "tool_a" in row[2]

    def test_write_context_marks_compressed(self, memory):
        """Test that _write_context_to_db marks compressed tasks."""
        unit = ContextUnit(
            timestamp=time.time(),
            task="[压缩摘要] 5 old tasks",
            result={},
            evaluation=None,
            tools_used=[],
        )

        memory._write_context_to_db(unit)

        cursor = memory.db.cursor()
        cursor.execute(
            "SELECT is_compressed FROM contexts WHERE task = ?",
            ("[压缩摘要] 5 old tasks",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1


# ─── ResearchMemory._migrate_if_needed Tests ─────────────────────────────────


class TestResearchMemoryMigration:
    """Tests for _migrate_if_needed method."""

    def test_migrate_adds_is_compressed_column(self, temp_db_path):
        """Test migration adds is_compressed column to contexts."""
        # Create a DB manually without is_compressed column (simulate v1 schema)
        conn = __import__("sqlite3").connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE contexts (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                timestamp REAL,
                task TEXT,
                result TEXT,
                evaluation TEXT,
                tools_used TEXT
            )
        """
        )
        conn.close()

        # Now create ResearchMemory which should trigger migration
        mem = ResearchMemory(session_id="migration_test", db_path=temp_db_path)

        cursor = mem.db.cursor()
        cursor.execute("PRAGMA table_info(contexts)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "is_compressed" in columns


# ─── ResearchMemory.__del__ Tests ──────────────────────────────────────────


class TestResearchMemoryCleanup:
    """Tests for __del__ cleanup method."""

    def test_del_closes_db(self, temp_db_path):
        """Test that __del__ closes database connection."""
        mem = ResearchMemory(session_id="cleanup_test", db_path=temp_db_path)
        db_conn = mem.db

        mem.__del__()

        # Connection should be closed (can't verify directly, but no exception should be raised)
        # The db object should no longer be usable
        with pytest.raises(__import__("sqlite3").ProgrammingError):
            db_conn.execute("SELECT 1")


# ─── ResearchMemory Constants ────────────────────────────────────────────────


class TestResearchMemoryConstants:
    """Tests for ResearchMemory class constants."""

    def test_default_db_path(self):
        """Test DEFAULT_DB_PATH is correctly defined."""
        assert ResearchMemory.DEFAULT_DB_PATH == ".cache/research.db"

    def test_write_lock_exists(self):
        """Test _write_lock is an RLock."""
        mem = ResearchMemory(session_id="lock_test", db_path=":memory:")
        assert hasattr(mem, "_write_lock")

        assert type(mem._write_lock).__name__ == "RLock"


# ─── Integration Tests ──────────────────────────────────────────────────────


class TestResearchMemoryIntegration:
    """Integration tests for complete workflows."""

    def test_full_research_workflow(self, memory):
        """Test complete research memory workflow."""
        # Push multiple research tasks
        memory.push(
            task="Literature search",
            result={"papers_found": 50},
            metadata={"type": "research", "tools": ["openalex"]},
        )
        memory.push(
            task="Data collection",
            result={"n_obs": 10000},
            metadata={"type": "data", "tools": ["tushare"]},
        )
        memory.push(
            task="Run regression",
            result={"coef": 0.023, "se": 0.005},
            metadata={"type": "analysis", "tools": ["statsmodels"]},
        )

        # Store key findings
        memory.store_knowledge(
            key="finding:coef_significant",
            value={"coefficient": 0.023, "p_value": 0.001},
            tags=["empirical", "significant"],
        )

        # Update evaluation
        last_unit = memory.context[-1]
        memory.update_evaluation(last_unit.timestamp, "Regression looks good")

        # Verify state
        assert len(memory.context) == 3
        assert memory.get_context(limit=2)[-1].evaluation == "Regression looks good"

        # Retrieve knowledge
        findings = memory.retrieve(tags=["significant"])
        assert len(findings) == 1

        # Compress context
        memory.push(task="Task 4", result={}, metadata={})
        memory.push(task="Task 5", result={}, metadata={})
        memory.compress_context(max_items=2)

        assert len(memory.context) <= 4

    def test_session_save_and_restore(self, temp_db_path):
        """Test complete session save and restore workflow."""
        # Create session
        mem1 = ResearchMemory(session_id="workflow_session", db_path=temp_db_path)

        mem1.push(
            task="Initial research",
            result={"phase": 1},
            metadata={"tools": ["search"]},
        )
        mem1.store_knowledge(
            key="preliminary:result",
            value={"status": "pending"},
            tags=["preliminary"],
        )

        mem1.save_session()
        mem1.db.close()

        # Restore and continue
        mem2 = ResearchMemory.load_session(session_id="workflow_session", db_path=temp_db_path)

        assert len(mem2.context) == 1
        findings = mem2.retrieve(tags=["preliminary"])
        assert len(findings) == 1

        # Continue work
        mem2.push(
            task="Continue research",
            result={"phase": 2},
            metadata={"tools": ["analysis"]},
        )

        mem2.save_session()
        mem2.db.close()

        # Load again
        mem3 = ResearchMemory.load_session(session_id="workflow_session", db_path=temp_db_path)
        assert len(mem3.context) == 2
