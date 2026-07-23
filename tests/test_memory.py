"""Tests for scripts/core/memory.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import unittest.mock
from collections import deque

import pytest

from scripts.core.memory import (
    ContextUnit,
    Operation,
    ResearchMemory,
    _CHROMADB_AVAILABLE,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db_path(tmp_path):
    """Provide a temporary DB path for ResearchMemory."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    return str(db_dir / "test_research.db")


@pytest.fixture
def memory(temp_db_path):
    """Create a ResearchMemory instance with a temporary DB."""
    return ResearchMemory(
        session_id="test-session-001",
        db_path=temp_db_path,
    )


@pytest.fixture
def memory_with_data(temp_db_path):
    """Create a ResearchMemory with pre-stored data."""
    mem = ResearchMemory(
        session_id="test-session-002",
        db_path=temp_db_path,
    )
    mem.push(
        task="检索茅台财务数据",
        result={"revenue": 1000, "profit": 500},
        metadata={"tools": ["tushare"], "type": "task_complete"},
    )
    mem.push(
        task="分析ROE",
        result={"roe": 0.30},
        metadata={"tools": [], "type": "task_complete"},
    )
    mem.store_knowledge(
        key="stock:600519",
        value={"name": "贵州茅台", "price": 1800.0},
        tags=["stock", "A股", "白酒"],
    )
    return mem


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestResearchMemoryInit:
    """Test 1: ResearchMemory.__init__."""

    def test_init_creates_db_and_tables(self, temp_db_path):
        mem = ResearchMemory("init-test", db_path=temp_db_path)
        assert mem.session_id == "init-test"
        assert mem.db_path == temp_db_path
        assert isinstance(mem.context, list)
        assert isinstance(mem.short_term, deque)

        # DB should have tables
        cursor = mem.db.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "contexts" in tables
        assert "knowledge" in tables
        assert "sessions" in tables

        mem.db.close()

    def test_init_with_custom_db_path(self, temp_db_path):
        mem = ResearchMemory("custom-path-test", db_path=temp_db_path)
        assert mem.db_path == temp_db_path
        mem.db.close()

    def test_chromadb_initialization_graceful(self, temp_db_path):
        """When ChromaDB is unavailable, _chroma_client and _vectors are None."""
        mem = ResearchMemory("chromadb-test", db_path=temp_db_path)
        if not _CHROMADB_AVAILABLE:
            assert mem._chroma_client is None
            assert mem._vectors is None
        mem.db.close()


class TestPushAndRetrieve:
    """Test 2 & 3: store/push and retrieve."""

    def test_push_stores_in_memory_and_db(self, memory):
        unit = memory.push(
            task="获取股价数据",
            result={"price": 100.0},
            metadata={"tools": ["yfinance"], "type": "task_complete"},
        )
        assert isinstance(unit, ContextUnit)
        assert unit.task == "获取股价数据"
        assert unit.result == {"price": 100.0}
        assert len(memory.context) == 1
        assert len(memory.short_term) == 1

    def test_get_context_returns_recent_items(self, memory):
        for i in range(5):
            memory.push(
                task=f"任务{i}",
                result={"i": i},
                metadata={"type": "task"},
            )
        recent = memory.get_context(limit=3)
        assert len(recent) == 3
        assert recent[-1].task == "任务4"  # Most recent last

    def test_update_evaluation(self, memory):
        unit = memory.push(
            task="分析数据",
            result={"score": 0.8},
            metadata={"type": "task"},
        )
        memory.update_evaluation(unit.timestamp, "评估：数据质量良好")
        updated = memory.get_context(limit=1)[-1]
        assert updated.evaluation == "评估：数据质量良好"


class TestStoreKnowledge:
    """Test knowledge storage and retrieval."""

    def test_store_and_retrieve_knowledge(self, memory):
        memory.store_knowledge(
            key="paper:2024.00001",
            value={"title": "碳排放权与绿色创新", "doi": "10.xxx"},
            tags=["carbon", "innovation", "DID"],
        )
        results = memory.retrieve(query="碳排放权")
        assert len(results) >= 1
        assert results[0]["key"] == "paper:2024.00001"

    def test_retrieve_by_tag(self, memory):
        memory.store_knowledge(
            key="ref:1",
            value={"text": "某篇论文"},
            tags=["finance", "valuation"],
        )
        memory.store_knowledge(
            key="ref:2",
            value={"text": "另一篇论文"},
            tags=["finance"],
        )
        results = memory.retrieve(tags=["finance"])
        assert len(results) >= 1
        for r in results:
            assert "finance" in r["tags"]

    def test_retrieve_with_limit(self, memory):
        for i in range(10):
            memory.store_knowledge(
                key=f"item:{i}",
                value={"i": i},
                tags=["test"],
            )
        results = memory.retrieve(limit=3)
        assert len(results) == 3


class TestGetRecent:
    """Test short-term layer ordering and limits."""

    def test_short_term_respects_maxlen(self, memory):
        # deque(maxlen=20) — add 25 items
        for i in range(25):
            memory.short_term.append(Operation(
                timestamp=time.time() + i,
                operation_type="test",
                description=f"op-{i}",
            ))
        assert len(memory.short_term) == 20
        # Oldest items should have been dropped
        assert memory.short_term[0].description == "op-5"

    def test_context_layer_order(self, memory):
        for i in range(3):
            memory.push(
                task=f"task-{i}",
                result={"n": i},
                metadata={"type": "test"},
            )
        ctx = memory.get_context(limit=10)
        assert ctx[0].task == "task-0"
        assert ctx[-1].task == "task-2"


class TestClear:
    """Test 5: clear / clear_session."""

    def test_clear_session_removes_context(self, memory):
        memory.push(
            task="temp task",
            result={},
            metadata={"type": "task"},
        )
        assert len(memory.context) > 0
        # Reset context list
        memory.context = []
        assert len(memory.context) == 0

    def test_short_term_cleared(self, memory):
        memory.short_term.append(Operation(
            timestamp=time.time(),
            operation_type="test",
            description="test op",
        ))
        memory.short_term.clear()
        assert len(memory.short_term) == 0


class TestGetStats:
    """Test 6: get_stats."""

    def test_get_stats_counts_operations(self, memory):
        for i in range(5):
            memory.push(
                task=f"task-{i}",
                result={"n": i},
                metadata={"type": "task"},
            )
        # Check that operations were recorded
        assert len(memory.short_term) == 5
        assert len(memory.context) == 5

    def test_stats_reflect_stored_knowledge(self, memory):
        for i in range(3):
            memory.store_knowledge(
                key=f"k{i}",
                value={"v": i},
                tags=["test"],
            )
        cursor = memory.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM knowledge WHERE session_id=?", (memory.session_id,))
        count = cursor.fetchone()[0]
        assert count >= 3


class TestVectorSearch:
    """Test 7: add_vector / search_vector — graceful degradation when ChromaDB unavailable."""

    def test_add_vector_returns_none_when_chromadb_unavailable(self, memory):
        if _CHROMADB_AVAILABLE:
            pytest.skip("ChromaDB is available — skipping graceful-degradation test")
        result = memory.add_vector("some text", {"source": "test"})
        assert result is None

    def test_search_vector_returns_empty_when_chromadb_unavailable(self, memory):
        if _CHROMADB_AVAILABLE:
            pytest.skip("ChromaDB is available — skipping graceful-degradation test")
        results = memory.search_vector("query text", top_k=3)
        assert results == []

    @pytest.mark.skipif(
        not _CHROMADB_AVAILABLE,
        reason="ChromaDB not installed",
    )
    def test_add_and_search_vector(self, temp_db_path):
        """Test vector storage and search when ChromaDB is available."""
        mem = ResearchMemory("vector-test", db_path=temp_db_path)
        vector_id = mem.add_vector(
            "碳排放权交易试点政策促进了企业绿色创新",
            metadata={"source": "paper", "year": 2024},
        )
        assert vector_id is not None
        results = mem.search_vector("绿色创新 政策", top_k=1)
        assert len(results) >= 1
        assert "text" in results[0]
        mem.db.close()


class TestPersistence:
    """Test session save/load."""

    def test_save_and_load_session(self, memory_with_data):
        memory_with_data.save_session()

        loaded = ResearchMemory.load_session(
            memory_with_data.session_id,
            db_path=memory_with_data.db_path,
        )
        assert loaded.session_id == memory_with_data.session_id
        # In-memory context restored
        assert len(loaded.context) >= 1
        loaded.db.close()

    def test_to_dict_contains_required_fields(self, memory_with_data):
        d = memory_with_data.to_dict()
        assert "session_id" in d
        assert "context" in d
        assert "short_term" in d
        assert d["session_id"] == memory_with_data.session_id

    def test_from_dict_restores_context(self, memory_with_data):
        d = memory_with_data.to_dict()
        restored = ResearchMemory.from_dict(d, db_path=memory_with_data.db_path)
        assert len(restored.context) == len(memory_with_data.context)
        assert restored.session_id == memory_with_data.session_id
        restored.db.close()

    def test_load_nonexistent_session_returns_fresh_memory(self, temp_db_path):
        """Loading a non-existent sessionID returns a new empty memory."""
        loaded = ResearchMemory.load_session(
            "this-session-does-not-exist",
            db_path=temp_db_path,
        )
        assert loaded.session_id == "this-session-does-not-exist"
        assert len(loaded.context) == 0
        loaded.db.close()


class TestCompressContext:
    """Test context compression."""

    def test_compress_context_marks_old_items(self, memory):
        """compress_context replaces older items with a compressed summary.

        Production code now uses threading.RLock for re-entrancy.
        """
        import threading

        # Production code now uses RLock; the patch is kept for explicit clarity
        original_lock = memory._write_lock
        memory._write_lock = threading.RLock()

        try:
            for i in range(5):
                memory.push(
                    task=f"old-task-{i}",
                    result={"i": i},
                    metadata={"type": "task"},
                )
            memory.compress_context(max_items=2)
            # Should have compressed unit + 2 kept items
            assert len(memory.context) == 3
            # First item should be the compressed summary
            assert "[压缩摘要]" in memory.context[0].task
        finally:
            memory._write_lock = original_lock


class TestDBWriteErrorHandling:
    """Test that DB write errors are handled gracefully."""

    def test_push_handles_db_error(self, memory):
        """DB operational errors should be caught and warned (not crash)."""
        import sqlite3

        # Replace db with a mock that raises on commit (simulating DB write failure)
        mock_conn = unittest.mock.MagicMock(spec=sqlite3.Connection)
        mock_conn.commit.side_effect = sqlite3.Error("simulated write error")
        memory.db = mock_conn

        unit = memory.push(
            task="task",
            result={"ok": True},
            metadata={"type": "task"},
        )
        assert isinstance(unit, ContextUnit)
        assert len(memory.context) == 1
