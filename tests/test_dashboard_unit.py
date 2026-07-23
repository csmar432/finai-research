"""Unit tests for scripts/dashboard.py.

Covers: STREAMLIT_AVAILABLE flag, page render functions, sidebar, set_page_config,
add_custom_css, data fetch helpers (_get_sessions, _get_papers, _get_tasks_count,
_get_task_status_counts, _get_recent_tasks, _get_mcp_tools, _search_memory,
_rag_query), main, run_cli.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def d():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import dashboard as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


# ═══════════════════════════════════════════════════════════════════════════
# Module structure
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleStructure:
    def test_module_loads(self, d):
        assert d is not None

    def test_streamlit_flag_is_bool(self, d):
        # Flag should exist and be bool (True if streamlit installed, False otherwise)
        assert isinstance(d.STREAMLIT_AVAILABLE, bool)

    def test_main_callable(self, d):
        assert callable(d.main)

    def test_run_cli_callable(self, d):
        assert callable(d.run_cli)


class TestPublicRenderFunctions:
    """All public render_* functions should exist and be callable."""

    @pytest.mark.parametrize("name", [
        "set_page_config",
        "add_custom_css",
        "render_sidebar",
        "render_overview",
        "render_sessions",
        "render_tasks",
        "render_memory",
        "render_papers",
        "render_rag",
        "render_data",
        "render_settings",
        "render_advanced_view",
        "render_trace_viewer",
    ])
    def test_render_function_exists(self, d, name):
        assert hasattr(d, name)
        assert callable(getattr(d, name))


# ═══════════════════════════════════════════════════════════════════════════
# Data fetch helpers (return safe defaults without crashing)
# ═══════════════════════════════════════════════════════════════════════════


class TestGetPapers:
    def test_get_papers_callable(self, d):
        assert callable(d._get_papers)

    def test_get_papers_returns_list(self, d):
        # Without a real knowledge/outlines directory, returns []
        result = d._get_papers()
        assert isinstance(result, list)


class TestGetSessions:
    def test_get_sessions_callable(self, d):
        assert callable(d._get_sessions)

    def test_get_sessions_returns_list(self, d):
        result = d._get_sessions()
        assert isinstance(result, list)


class TestGetTasksCount:
    def test_get_tasks_count_callable(self, d):
        assert callable(d._get_tasks_count)

    def test_get_tasks_count_returns_int(self, d):
        result = d._get_tasks_count()
        assert isinstance(result, int)


class TestGetTaskStatusCounts:
    def test_get_task_status_counts_callable(self, d):
        assert callable(d._get_task_status_counts)

    def test_get_task_status_counts_returns_dict(self, d):
        result = d._get_task_status_counts()
        assert isinstance(result, dict)
        # Should contain standard statuses
        for status in ["pending", "running", "done", "failed"]:
            assert status in result


class TestGetRecentTasks:
    def test_get_recent_tasks_callable(self, d):
        assert callable(d._get_recent_tasks)

    def test_get_recent_tasks_returns_list(self, d):
        result = d._get_recent_tasks()
        assert isinstance(result, list)


class TestSearchMemory:
    def test_search_memory_callable(self, d):
        assert callable(d._search_memory)

    def test_search_memory_returns_list(self, d):
        # Should not crash when DB doesn't exist
        result = d._search_memory("test query", ["paper"], 10)
        assert isinstance(result, list)


class TestRagQuery:
    def test_rag_query_callable(self, d):
        assert callable(d._rag_query)

    def test_rag_query_returns_tuple(self, d):
        # Without real RAG, returns (error_message, []) tuple
        answer, sources = d._rag_query("test", 5, "deepseek")
        assert isinstance(answer, str)
        assert isinstance(sources, list)


class TestGetMcpTools:
    def test_get_mcp_tools_callable(self, d):
        assert callable(d._get_mcp_tools)

    def test_get_mcp_tools_returns_list(self, d):
        result = d._get_mcp_tools()
        assert isinstance(result, list)
        assert len(result) >= 1
        # Each entry has expected keys
        for tool in result:
            assert "name" in tool
            assert "status" in tool


# ═══════════════════════════════════════════════════════════════════════════
# Signatures
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionSignatures:
    def test_render_advanced_view_signature(self, d):
        sig = inspect.signature(d.render_advanced_view)
        assert "view_type" in sig.parameters

    def test_search_memory_signature(self, d):
        sig = inspect.signature(d._search_memory)
        assert "query" in sig.parameters
        assert "tags" in sig.parameters
        assert "limit" in sig.parameters

    def test_rag_query_signature(self, d):
        sig = inspect.signature(d._rag_query)
        assert "query" in sig.parameters
        assert "top_k" in sig.parameters
        assert "model" in sig.parameters
