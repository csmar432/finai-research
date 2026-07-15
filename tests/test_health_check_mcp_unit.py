"""Unit tests for scripts/health_check_mcp.py (pure data structures + logic)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def hcm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    import health_check_mcp as h
    yield h
    if _p in sys.path:
        sys.path.remove(_p)


class TestPriorityServers:
    def test_priority_servers_is_list(self, hcm):
        assert isinstance(hcm.PRIORITY_SERVERS, list)
        assert len(hcm.PRIORITY_SERVERS) > 0

    def test_contains_key_servers(self, hcm):
        for name in ("user-yfinance", "user-openalex", "user-financial", "user-tushare"):
            assert name in hcm.PRIORITY_SERVERS

    def test_all_start_with_user(self, hcm):
        for s in hcm.PRIORITY_SERVERS:
            assert s.startswith("user-")

    def test_priority_servers_count(self, hcm):
        assert len(hcm.PRIORITY_SERVERS) == 22

    def test_no_duplicates(self, hcm):
        assert len(hcm.PRIORITY_SERVERS) == len(set(hcm.PRIORITY_SERVERS))


class TestProjectRoot:
    def test_default_resolved(self, hcm):
        assert hcm.PROJECT_ROOT_DEFAULT.is_absolute()
        assert hcm.PROJECT_ROOT_DEFAULT.exists()


class TestHelperFunctions:
    def test_get_priority_servers_function(self, hcm):
        if hasattr(hcm, "get_priority_servers"):
            result = hcm.get_priority_servers()
            assert isinstance(result, list)
            assert len(result) > 0

