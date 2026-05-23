"""Tests for ToolSelector.

Run with: pytest scripts/core/test_tool_selector.py -v
"""

from __future__ import annotations

from scripts.core.memory import ResearchMemory
from scripts.core.planner import Task, TaskStatus, TaskType
from scripts.core.tool_selector import (
    CostTier,
    ToolCapability,
    ToolSelection,
    ToolSelector,
)


# ── Helpers ──────────────────────────────────────────────────────────────────────


def _make_task(task_id: str, description: str, task_type: TaskType) -> Task:
    """Factory: create a minimal Task for testing."""
    return Task(
        id=task_id,
        description=description,
        task_type=task_type,
        status=TaskStatus.PENDING,
        subtasks=[],
        dependencies=[],
        created_at=0.0,
    )


# ── Test Cases ───────────────────────────────────────────────────────────────────


def test_select_for_data_fetch():
    """DATA_FETCH task should return at least one matching tool."""
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    task = _make_task("t1", "获取苹果股价", TaskType.DATA_FETCH)

    selections = selector.select(task, [])

    assert len(selections) >= 1
    assert all(
        s.tool_name in ("financial", "finviz_sec", "fetch_a_stock",
                        "arxiv", "brave_search", "fetch", "eastmoney_reports")
        for s in selections
    ), f"Unexpected tool names: {[s.tool_name for s in selections]}"


def test_select_for_literature():
    """LITERATURE task should return arxiv, literature_search, brave_search, eastmoney_reports."""
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    task = _make_task("t2", "检索深度学习量化交易文献", TaskType.LITERATURE)

    selections = selector.select(task, [])

    assert len(selections) >= 1
    assert all(
        s.tool_name in ("arxiv", "literature_search", "brave_search", "eastmoney_reports")
        for s in selections
    ), f"Unexpected tool names: {[s.tool_name for s in selections]}"


def test_select_for_writing():
    """WRITING task should return paper_write or report_generator."""
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    task = _make_task("t3", "写论文", TaskType.WRITING)

    selections = selector.select(task, [])

    assert len(selections) >= 1
    assert all(
        s.tool_name in ("paper_write", "report_generator")
        for s in selections
    ), f"Unexpected tool names: {[s.tool_name for s in selections]}"


def test_tool_registry_complete():
    """
    Verify all 13 tools are registered in TOOL_REGISTRY.
    """
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)

    expected = {
        # MCP tools
        "arxiv",
        "financial",
        "finviz_sec",
        "brave_search",
        "fetch",
        "eastmoney_reports",
        "context7",
        # Python script tools
        "fetch_a_stock",
        "econometrics_regression",
        "literature_search",
        "paper_write",
        "report_generator",
        "llm_sentiment",
    }

    actual = set(selector.TOOL_REGISTRY.keys())
    assert actual == expected, (
        f"Registry mismatch.\n"
        f"  Expected: {expected}\n"
        f"  Missing:  {expected - actual}\n"
        f"  Extra:    {actual - expected}"
    )


def test_cost_tier_ordering():
    """
    For ANALYSIS tasks (FREE: finviz_sec, econometrics_regression; LOW: llm_sentiment),
    all FREE tools must appear before any LOW-cost tool in the selection list.
    """
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    task = _make_task("t4", "数据分析", TaskType.ANALYSIS)

    selections = selector.select(task, [])

    assert len(selections) >= 2, (
        f"Need at least 2 candidates to test ordering, got {len(selections)}"
    )

    free_indices = [i for i, s in enumerate(selections) if s.estimated_cost == "free"]
    low_indices  = [i for i, s in enumerate(selections) if s.estimated_cost == "low"]

    if free_indices and low_indices:
        assert max(free_indices) < min(low_indices), (
            f"FREE tools must come before LOW-cost tools in selection order.\n"
            f"  FREE indices:  {free_indices}\n"
            f"  LOW  indices:  {low_indices}\n"
            f"  Full list:    {[(s.tool_name, s.estimated_cost) for s in selections]}"
        )


def test_tool_selection_confidence():
    """First-ranked tool should have confidence=1.0; others should have confidence=0.8."""
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    task = _make_task("t5", "获取财务数据", TaskType.DATA_FETCH)

    selections = selector.select(task, [])

    if len(selections) >= 2:
        assert selections[0].confidence == 1.0
        assert all(s.confidence == 0.8 for s in selections[1:]), (
            "All non-first selections should have confidence=0.8"
        )
    elif len(selections) == 1:
        assert selections[0].confidence == 1.0


def test_tool_capability_dataclass():
    """ToolCapability fields are accessible and correct."""
    cap = ToolCapability(
        name="test_tool",
        task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
        inputs=["query"],
        outputs=["result"],
        priority=1,
        cost=CostTier.FREE,
        requires_vpn=False,
        description="A test tool",
    )

    assert cap.name == "test_tool"
    assert TaskType.DATA_FETCH in cap.task_types
    assert cap.cost == CostTier.FREE
    assert cap.requires_vpn is False
    assert cap.callable is None


def test_tool_selection_dataclass():
    """ToolSelection fields are accessible."""
    sel = ToolSelection(
        tool_name="arxiv",
        confidence=0.8,
        reason="Best match for LITERATURE",
        estimated_cost="free",
        requires_vpn=False,
    )

    assert sel.tool_name == "arxiv"
    assert sel.confidence == 0.8
    assert sel.estimated_cost == "free"


def test_execute_returns_tool_result():
    """execute() should return a ToolResult, not raise (failure returns failed ToolResult)."""
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)

    # Build a selection for a tool that does not exist
    sel = ToolSelection(
        tool_name="nonexistent_tool",
        confidence=1.0,
        reason="testing",
        estimated_cost="free",
        requires_vpn=False,
    )

    result = selector.execute(sel, {})

    # Should return a ToolResult, not raise
    assert hasattr(result, "success")
    assert hasattr(result, "output")
    assert hasattr(result, "tool_name")
    assert hasattr(result, "error")
    # Nonexistent tool should fail gracefully
    assert result.success is False
    assert result.tool_name == "nonexistent_tool"
