"""Unit tests for scripts/run_research.py (pure functions)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def rr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    import run_research as r
    yield r
    if _p in sys.path:
        sys.path.remove(_p)


class TestConstants:
    def test_project_root_resolved(self, rr):
        assert rr.PROJECT_ROOT.is_absolute()

    def test_queue_file_defined(self, rr):
        assert isinstance(rr.QUEUE_FILE, Path)

    def test_server_url(self, rr):
        assert rr.SERVER_URL == "http://localhost:8502"

    def test_poll_interval_positive(self, rr):
        assert rr.POLL_INTERVAL > 0


class TestHttpPost:
    def test_returns_none_on_network_error(self, rr):
        result = rr._http_post("http://localhost:99999/nonexistent", {})
        assert result is None

    def test_returns_none_on_invalid_url(self, rr):
        result = rr._http_post("not-a-url", {})
        assert result is None


class TestLoadQueue:
    def test_missing_file_returns_empty(self, rr, tmp_path, monkeypatch):
        monkeypatch.setattr(rr, "QUEUE_FILE", tmp_path / "nonexistent.json")
        result = rr._load_queue()
        assert result == []


class TestHelperFunctions:
    def test_push_wf_state_exists(self, rr):
        assert callable(rr._push_wf_state)

    def test_load_queue_exists(self, rr):
        assert callable(rr._load_queue)


class TestDataclasses:
    def test_wf_node_fields(self, rr):
        if hasattr(rr, "WFNode"):
            n = rr.WFNode(id="test", label="Test", status="running")
            assert n.id == "test"
            assert n.status == "running"

