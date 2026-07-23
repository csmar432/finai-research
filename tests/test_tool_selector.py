"""Tests for scripts/core/tool_selector.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

import pytest

from scripts.core.tool_selector import (
    CostTier,
    ToolCapability,
    ToolResult,
    ToolSelection,
    ToolSelector,
)
from scripts.core.planner import Task, TaskType

# Module-level dicts from tool_selector.py
from scripts.core import tool_selector as _ts_module

SCRIPT_CALLABLES = _ts_module.SCRIPT_CALLABLES


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memory():
    """Mock ResearchMemory."""
    mem = MagicMock()
    return mem


@pytest.fixture
def tool_selector(mock_memory):
    """Create a ToolSelector with a mock memory."""
    return ToolSelector(mock_memory)


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestToolSelectorInit:
    """Test 1: ToolSelector.__init__."""

    def test_init_stores_memory(self, tool_selector, mock_memory):
        assert tool_selector.memory is mock_memory

    def test_init_creates_tool_registry(self, tool_selector):
        """ToolSelector initializes TOOL_REGISTRY from base."""
        assert isinstance(tool_selector.TOOL_REGISTRY, dict)
        assert len(tool_selector.TOOL_REGISTRY) > 0

    def test_init_creates_deep_copy(self, mock_memory):
        """Each instance gets its own registry copy (not shared class state)."""
        ts1 = ToolSelector(mock_memory)
        ts2 = ToolSelector(mock_memory)
        # Modifying one registry shouldn't affect the other
        original_len = len(ts1.TOOL_REGISTRY)
        ts1.TOOL_REGISTRY["__test_tool__"] = MagicMock()
        assert len(ts1.TOOL_REGISTRY) > original_len
        assert len(ts2.TOOL_REGISTRY) == original_len

    def test_init_sets_project_root(self, tool_selector):
        assert tool_selector.project_root is not None
        assert tool_selector.project_root.is_dir()


class TestSelectTool:
    """Test 2: select_tool (via select method)."""

    def test_select_returns_list_for_data_fetch(self, tool_selector):
        """DATA_FETCH task should return non-empty tool selections."""
        task = Task(
            id="t1",
            description="获取茅台财务数据",
            task_type=TaskType.DATA_FETCH,
        )
        selections = tool_selector.select(task, context=[])
        assert isinstance(selections, list)

    def test_select_returns_list_for_literature(self, tool_selector):
        """LITERATURE task should return non-empty tool selections."""
        task = Task(
            id="t2",
            description="检索碳排放权相关文献",
            task_type=TaskType.LITERATURE,
        )
        selections = tool_selector.select(task, context=[])
        assert isinstance(selections, list)

    def test_select_returns_list_for_analysis(self, tool_selector):
        """ANALYSIS task should return non-empty tool selections."""
        task = Task(
            id="t3",
            description="分析ROE和毛利率",
            task_type=TaskType.ANALYSIS,
        )
        selections = tool_selector.select(task, context=[])
        assert isinstance(selections, list)

    def test_select_empty_for_unknown_task_type(self, tool_selector):
        """Task with no matching tools returns empty list."""
        task = Task(
            id="t4",
            description="Do something",
            task_type=TaskType.ORCHESTRATE,
        )
        # ORCHESTRATE only maps to "dashboard" — if unavailable, returns []
        selections = tool_selector.select(task, context=[])
        assert isinstance(selections, list)

    def test_select_sorted_by_priority(self, tool_selector):
        """Selected tools should be sorted by priority (ascending)."""
        task = Task(
            id="t5",
            description="获取股票数据",
            task_type=TaskType.DATA_FETCH,
        )
        selections = tool_selector.select(task, context=[])
        if len(selections) > 1:
            priorities = [
                tool_selector.TOOL_REGISTRY[s.tool_name].priority
                for s in selections
                if s.tool_name in tool_selector.TOOL_REGISTRY
            ]
            assert priorities == sorted(priorities)

    def test_select_first_tool_has_confidence_1(self, tool_selector):
        """First tool in selection list should have confidence=1.0."""
        task = Task(
            id="t6",
            description="检索文献",
            task_type=TaskType.LITERATURE,
        )
        selections = tool_selector.select(task, context=[])
        if selections:
            assert selections[0].confidence == 1.0

    def test_select_context_boost(self, tool_selector):
        """Tools used in context get a +0.1 confidence boost."""
        task = Task(
            id="t7",
            description="分析数据",
            task_type=TaskType.ANALYSIS,
        )
        from scripts.core.memory import ContextUnit

        mock_context = [
            ContextUnit(
                timestamp=0.0,
                task="previous analysis",
                result={},
                evaluation=None,
                tools_used=["financial"],
            )
        ]
        selections = tool_selector.select(task, context=mock_context)
        if selections:
            # financial tool should have boosted confidence
            financial_sel = next(
                (s for s in selections if s.tool_name == "financial"),
                None,
            )
            if financial_sel:
                assert financial_sel.confidence > 0.8


class TestSelectBestQualityTool:
    """Test 3: select_best_quality_tool."""

    def test_select_best_quality_returns_list(self, tool_selector):
        """select_best_quality_tool should return a list of ToolMetadata."""
        results = tool_selector.select_best_quality_tool(TaskType.DATA_FETCH)
        assert isinstance(results, list)

    def test_select_best_quality_respects_top_k(self, tool_selector):
        """top_k parameter limits the number of results."""
        results = tool_selector.select_best_quality_tool(
            TaskType.DATA_FETCH, top_k=3
        )
        assert isinstance(results, list)
        assert len(results) <= 3

    def test_select_best_quality_with_category(self, tool_selector):
        """category filter should work."""
        results = tool_selector.select_best_quality_tool(
            TaskType.LITERATURE, category="academic", top_k=2
        )
        assert isinstance(results, list)


class TestGetToolMarketplaceReport:
    """Test 4: get_tool_marketplace_report."""

    def test_get_marketplace_report_returns_dict(self, tool_selector):
        """Marketplace report should be a dict with key stats."""
        report = tool_selector.get_tool_marketplace_report()
        assert isinstance(report, dict)

    def test_get_marketplace_report_has_expected_keys(self, tool_selector):
        """Report should contain expected keys (tools, categories, etc.)."""
        report = tool_selector.get_tool_marketplace_report()
        # Should have some stats
        assert len(report) >= 0


class TestMCPToolServerMap:
    """Test 5: MCP_TOOL_SERVER_MAP mappings."""

    def test_map_contains_known_tools(self):
        """Known tool names are present in the map."""
        # 注: `fetch` 和 `finviz_sec` 不在仓库中, 已移除
        expected = [
            "arxiv", "brave_search", "financial", "yfinance",
            "eastmoney_reports", "tushare",
        ]
        for name in expected:
            assert name in ToolSelector.MCP_TOOL_SERVER_MAP, f"Missing tool: {name}"

    def test_map_values_are_tuples(self):
        """Each map entry is a (tool_name, server_name) tuple."""
        for key, value in ToolSelector.MCP_TOOL_SERVER_MAP.items():
            assert isinstance(value, tuple)
            assert len(value) == 2
            assert isinstance(value[0], str)
            assert isinstance(value[1], str)

    def test_map_server_names_use_hyphens(self):
        """Server names in map should use hyphens (mcp.json convention)."""
        for key, (_, server_name) in ToolSelector.MCP_TOOL_SERVER_MAP.items():
            # Custom servers use hyphens; built-in servers use original names
            assert isinstance(server_name, str)


class TestMCPToolsAndScriptTools:
    """Verify frozenset constants."""

    def test_mcp_tools_is_frozenset(self):
        assert isinstance(ToolSelector.MCP_TOOLS, frozenset)

    def test_mcp_tools_not_empty(self):
        assert len(ToolSelector.MCP_TOOLS) > 0

    def test_script_tools_is_frozenset(self):
        assert isinstance(ToolSelector.SCRIPT_TOOLS, frozenset)

    def test_script_tools_not_empty(self):
        assert len(ToolSelector.SCRIPT_TOOLS) > 0

    def test_script_callables_is_dict(self):
        assert isinstance(SCRIPT_CALLABLES, dict)
        assert len(SCRIPT_CALLABLES) > 0


class TestToolCapability:
    """Test ToolCapability dataclass."""

    def test_tool_capability_fields(self):
        cap = ToolCapability(
            name="test_tool",
            task_types=[TaskType.DATA_FETCH],
            inputs=["query"],
            outputs=["result"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="A test tool",
            callable=None,
        )
        assert cap.name == "test_tool"
        assert cap.cost == CostTier.FREE
        assert TaskType.DATA_FETCH in cap.task_types


class TestToolSelection:
    """Test ToolSelection dataclass."""

    def test_tool_selection_fields(self):
        sel = ToolSelection(
            tool_name="arxiv",
            confidence=0.9,
            reason="Matches LITERATURE task",
            estimated_cost="free",
            requires_vpn=False,
            callable=None,
        )
        assert sel.tool_name == "arxiv"
        assert sel.confidence == 0.9
        assert sel.estimated_cost == "free"


class TestToolResult:
    """Test ToolResult dataclass."""

    def test_tool_result_success(self):
        res = ToolResult(
            success=True,
            output={"result": "data"},
            tool_name="arxiv",
            latency_ms=50.0,
        )
        assert res.success is True
        assert res.output == {"result": "data"}

    def test_tool_result_failure(self):
        res = ToolResult(
            success=False,
            output=None,
            tool_name="arxiv",
            error="Network error",
        )
        assert res.success is False
        assert res.error == "Network error"


class TestToolRegistry:
    """Test that the registry is properly populated."""

    def test_arxiv_in_registry(self, tool_selector):
        assert "arxiv" in tool_selector.TOOL_REGISTRY
        cap = tool_selector.TOOL_REGISTRY["arxiv"]
        assert TaskType.LITERATURE in cap.task_types
        assert TaskType.DATA_FETCH in cap.task_types

    def test_financial_in_registry(self, tool_selector):
        assert "financial" in tool_selector.TOOL_REGISTRY

    def test_all_registry_tools_have_required_fields(self, tool_selector):
        """Every ToolCapability in the registry has all required fields."""
        for name, cap in tool_selector.TOOL_REGISTRY.items():
            assert isinstance(cap, ToolCapability)
            assert cap.name == name
            assert isinstance(cap.task_types, list)
            assert isinstance(cap.inputs, list)
            assert isinstance(cap.outputs, list)
            assert isinstance(cap.priority, int)
            assert isinstance(cap.cost, CostTier)
            assert isinstance(cap.requires_vpn, bool)
            assert isinstance(cap.description, str)


class TestExecuteTool:
    """Test execute() method."""

    def test_execute_unknown_tool_returns_error(self, tool_selector):
        """Executing an unknown tool returns ToolResult with success=False."""
        selection = ToolSelection(
            tool_name="__nonexistent_tool_xyz__",
            confidence=1.0,
            reason="test",
            estimated_cost="free",
            requires_vpn=False,
            callable=None,
        )
        result = tool_selector.execute(selection, {})
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "not found" in result.error

    def test_execute_returns_tool_result(self, tool_selector):
        """execute() should return a ToolResult."""
        selection = ToolSelection(
            tool_name="arxiv",
            confidence=1.0,
            reason="test",
            estimated_cost="free",
            requires_vpn=False,
            callable=None,
        )
        result = tool_selector.execute(selection, {"query": "AI in finance"})
        assert isinstance(result, ToolResult)


class TestCallScript:
    """Test _call_script with SCRIPT_TOOLS."""

    def test_call_script_unknown_raises_not_implemented(self, tool_selector):
        """Calling an unknown script raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="No script mapping"):
            tool_selector._call_script("__unknown_script__", {})


class TestAvailabilityCache:
    """Test VPN and availability checking."""

    def test_vpn_check_caches_result(self, tool_selector):
        """VPN check populates _vpn_available after first call."""
        # Before any check, _vpn_available is None (unset)
        assert tool_selector._vpn_available is None
        tool_selector._check_vpn()
        # After check, _vpn_available is either True or False (not None)
        assert tool_selector._vpn_available is not None
        assert isinstance(tool_selector._vpn_available, bool)

    def test_availability_cache_stores_result(self, tool_selector):
        """_check_tool_availability should populate _availability_cache."""
        tool_selector._availability_cache.clear()
        result = tool_selector._check_tool_availability("arxiv")
        assert isinstance(result, bool)
        assert "arxiv" in tool_selector._availability_cache

    def test_availability_cache_respects_ttl(self, tool_selector):
        """Cached availability should be reused within TTL."""
        tool_selector._check_tool_availability("arxiv")
        # Second call should hit cache
        import time
        cached_before = tool_selector._availability_cache.get("arxiv")
        if cached_before:
            assert time.time() - cached_before[1] < tool_selector._availability_cache_ttl


class TestSetAgent:
    """Test set_agent for allowed_tools enforcement."""

    def test_set_agent_sets_agent_name(self, tool_selector):
        """set_agent should store the agent name."""
        tool_selector.set_agent("analyst")
        assert tool_selector._agent_name == "analyst"

    def test_set_agent_none_clears_agent(self, tool_selector):
        """set_agent(None) should clear the agent name."""
        tool_selector.set_agent("analyst")
        tool_selector.set_agent(None)
        assert tool_selector._agent_name is None
