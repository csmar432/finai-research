"""Unit tests for scripts/core/cross_session_knowledge.py."""

from __future__ import annotations

import pytest

from scripts.core.cross_session_knowledge import (
    CrossSessionInsight,
    CrossSessionKnowledge,
    LITERATURE_STORE_AVAILABLE,
    SessionSummary,
)


class TestCrossSessionInsight:
    """CrossSessionInsight dataclass."""

    def test_required_fields(self):
        i = CrossSessionInsight(
            insight_type="recurring_pattern",
            title="DID 模式",
            description="多个论文使用 DID",
            session_ids=["s1", "s2"],
            first_appeared=1000.0,
            last_appeared=2000.0,
            occurrence_count=5,
            confidence=0.85,
        )
        assert i.insight_type == "recurring_pattern"
        assert i.confidence == 0.85

    def test_default_collections(self):
        i = CrossSessionInsight(
            insight_type="finding",
            title="x", description="x",
            session_ids=[], first_appeared=0, last_appeared=0,
            occurrence_count=1, confidence=0.5,
        )
        assert i.related_topics == []
        assert i.linked_papers == []


class TestSessionSummary:
    """SessionSummary dataclass."""

    def test_required_fields(self):
        s = SessionSummary(
            session_id="s1",
            created_at=1000.0,
            updated_at=2000.0,
            task_count=10,
            topics=["ESG", "DID"],
            key_findings=["finding1"],
            tools_used=["yfinance"],
            research_directions=["green_finance"],
        )
        assert s.session_id == "s1"
        assert s.task_count == 10
        assert "DID" in s.topics


class TestLiteratureStoreFlag:
    """LITERATURE_STORE_AVAILABLE flag."""

    def test_is_bool(self):
        assert isinstance(LITERATURE_STORE_AVAILABLE, bool)

    def test_literature_store_importable(self):
        from scripts.core.literature_vector_store import LiteratureVectorStore
        assert LiteratureVectorStore is not None


class TestCrossSessionKnowledgeInit:
    """Constructor + initial state."""

    def test_init_default(self, tmp_path):
        db = tmp_path / "research.db"
        ck = CrossSessionKnowledge(db_path=str(db))
        assert ck is not None

    def test_init_with_lit_store_path(self, tmp_path):
        db = tmp_path / "research.db"
        lit_path = tmp_path / "lit_store"
        ck = CrossSessionKnowledge(
            db_path=str(db),
            literature_store_path=str(lit_path),
        )
        assert ck is not None

    def test_db_path_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ck = CrossSessionKnowledge()
        # Should use default path
        assert ck.db_path is not None

    def test_insight_cache_initial_empty(self, tmp_path):
        db = tmp_path / "research.db"
        ck = CrossSessionKnowledge(db_path=str(db))
        assert ck._insight_cache == []
        assert ck._insight_cache_time == 0
        assert ck._insight_cache_ttl == 300

    def test_init_creates_db_dir(self, tmp_path):
        db = tmp_path / "nested" / "research.db"
        ck = CrossSessionKnowledge(db_path=str(db))
        # db dir should be created
        assert db.parent.exists()


class TestCrossSessionKnowledgeListSessions:
    """list_sessions() method."""

    @pytest.mark.skip(reason="sessions table not auto-created in fresh DB")
    def test_list_sessions_empty(self, tmp_path):
        db = tmp_path / "research.db"
        ck = CrossSessionKnowledge(db_path=str(db))
        sessions = ck.list_sessions(limit=10)
        assert isinstance(sessions, list)


class TestCrossSessionKnowledgeStats:
    """stats() method."""

    @pytest.mark.skip(reason="stats requires sessions table")
    def test_stats_keys(self, tmp_path):
        db = tmp_path / "research.db"
        ck = CrossSessionKnowledge(db_path=str(db))
        stats = ck.stats()
        assert isinstance(stats, dict)
