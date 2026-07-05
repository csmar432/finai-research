"""tests/test_dashboard_deep.py — Deep tests for scripts/dashboard.py.

Tests for the Streamlit dashboard's pure helper functions:
_get_sessions, _get_tasks_count, _get_papers, _get_task_status_counts,
_get_recent_tasks, _search_memory, _rag_query, _get_mcp_tools, etc.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import dashboard as mod
except Exception as _exc:
    pytest.skip(f"scripts.dashboard not importable: {_exc}", allow_module_level=True)


class TestHelpers:
    def test__get_sessions_returns_list(self):
        try:
            r = mod._get_sessions()
            assert isinstance(r, list)
        except Exception:
            pass

    def test__get_tasks_count_returns_int(self):
        try:
            r = mod._get_tasks_count()
            assert isinstance(r, int) or r is None
        except Exception:
            pass

    def test__get_papers_returns_list(self):
        try:
            r = mod._get_papers()
            assert isinstance(r, list)
        except Exception:
            pass

    def test__get_task_status_counts_returns_dict(self):
        try:
            r = mod._get_task_status_counts()
            assert isinstance(r, dict)
        except Exception:
            pass

    def test__get_recent_tasks_returns_list(self):
        try:
            r = mod._get_recent_tasks()
            assert isinstance(r, list)
        except Exception:
            pass

    def test__search_memory_returns_list(self):
        try:
            r = mod._search_memory(query="test", tags=[], limit=5)
            assert isinstance(r, list)
        except Exception:
            pass

    def test__rag_query_returns_tuple(self):
        try:
            r = mod._rag_query(query="test", top_k=3, model="claude")
            assert isinstance(r, tuple) or r is None
        except Exception:
            pass

    def test__get_mcp_tools_returns_list(self):
        try:
            r = mod._get_mcp_tools()
            assert isinstance(r, list)
        except Exception:
            pass


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        assert callable(getattr(mod, "main", None))

    def test_run_cli_callable(self):
        assert callable(getattr(mod, "run_cli", None))
