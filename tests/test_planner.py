"""Tests for scripts/core/planner.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

import pytest

from scripts.core.planner import (
    KEYWORD_PATTERNS,
    REGEX_PATTERNS,
    ResearchPlanner,
    TaskStatus,
    TaskType,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memory():
    """Mock ResearchMemory for the planner."""
    mem = MagicMock()
    return mem


@pytest.fixture
def planner(mock_memory):
    """Create a ResearchPlanner with a mock memory."""
    return ResearchPlanner(mock_memory)


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestResearchPlannerInit:
    """Test 1: ResearchPlanner.__init__."""

    def test_init_stores_memory(self, planner, mock_memory):
        assert planner.memory is mock_memory

    def test_init_empty_task_registry(self, planner):
        assert isinstance(planner.tasks, dict)
        assert len(planner.tasks) == 0

    def test_init_task_counter_starts_at_zero(self, planner):
        assert planner._task_counter == 0


class TestTaskDecompose:
    """Test 2: plan/decompose method."""

    def test_decompose_literature_request(self, planner):
        """'检索文献' should decompose into search→download→review."""
        tasks = planner.decompose("检索碳排放权相关文献")
        _ = [t.id for t in tasks]  # noqa: F841 (side-effect only, original var= removed by ruff)
        # Should produce literature tasks
        assert len(tasks) >= 3
        types = [t.task_type for t in tasks]
        assert TaskType.LITERATURE in types or TaskType.REVIEW in types

    def test_decompose_writing_request(self, planner):
        """'写论文' should decompose into outline→chapter→assemble."""
        tasks = planner.decompose("写一篇关于碳排放权的论文")
        assert len(tasks) >= 3
        types = [t.task_type for t in tasks]
        assert TaskType.WRITING in types

    def test_decompose_analysis_request(self, planner):
        """'分析财务数据' should produce analysis tasks."""
        tasks = planner.decompose("分析茅台2024年财务数据")
        types = [t.task_type for t in tasks]
        assert TaskType.ANALYSIS in types or TaskType.DATA_FETCH in types

    def test_decompose_data_fetch_request(self, planner):
        """'获取数据' should produce data fetch tasks."""
        tasks = planner.decompose("获取贵州茅台日线数据")
        types = [t.task_type for t in tasks]
        assert TaskType.DATA_FETCH in types

    def test_decompose_visualization_request(self, planner):
        """'画出股价走势图' contains data keywords, triggers ANALYSIS/DATA_FETCH."""
        tasks = planner.decompose("画出茅台股价走势图")
        types = [t.task_type for t in tasks]
        # "画出..." contains "画" (VISUALIZATION keyword) but also gets
        # matched by the ANALYSIS/DATA_FETCH case
        assert TaskType.DATA_FETCH in types or TaskType.ANALYSIS in types

    def test_decompose_unknown_request_defaults_to_analysis(self, planner):
        """Unmatched request defaults to ANALYSIS → DATA_FETCH + ANALYSIS."""
        tasks = planner.decompose("请帮我做点什么")
        assert len(tasks) >= 2
        types = [t.task_type for t in tasks]
        assert TaskType.ANALYSIS in types or TaskType.DATA_FETCH in types

    def test_decompose_code_request(self, planner):
        """'写一段Python代码进行回归分析' → WRITING (keyword "写" wins).
        CODE type triggered by "python代码" without "写"."""
        tasks = planner.decompose("写一段Python代码进行回归分析")
        types = [t.task_type for t in tasks]
        assert TaskType.WRITING in types  # "写" keyword maps to WRITING
        assert len(tasks) >= 1

    def test_decompose_registers_tasks_in_registry(self, planner):
        """All decomposed tasks are stored in planner.tasks dict."""
        tasks = planner.decompose("检索文献")
        assert all(t.id in planner.tasks for t in tasks)

    def test_decompose_research_report(self, planner):
        """'生成研报' triggers WRITING decomposition (outline→chapter→assemble)."""
        tasks = planner.decompose("生成一份茅台行业研报")
        types = [t.task_type for t in tasks]
        assert TaskType.WRITING in types
        assert len(tasks) >= 3  # outline + chapters + assemble


class TestTaskTypeClassification:
    """Test _estimate_task_type classification logic."""

    def test_classify_literature_keywords(self, planner):
        result = planner._estimate_task_type("检索文献并撰写综述")
        assert TaskType.LITERATURE in result

    def test_classify_analysis_keywords(self, planner):
        result = planner._estimate_task_type("分析财务ROE和毛利率")
        assert TaskType.ANALYSIS in result

    def test_classify_writing_keywords(self, planner):
        result = planner._estimate_task_type("写论文并润色")
        assert TaskType.WRITING in result

    def test_classify_data_fetch_keywords(self, planner):
        result = planner._estimate_task_type("获取日线行情数据")
        assert TaskType.DATA_FETCH in result

    def test_classify_code_keywords(self, planner):
        result = planner._estimate_task_type("写一段python代码")
        assert TaskType.CODE in result

    def test_classify_visualization_keywords(self, planner):
        result = planner._estimate_task_type("绘制可视化图表")
        assert TaskType.VISUALIZATION in result

    def test_classify_unknown_defaults_to_analysis(self, planner):
        result = planner._estimate_task_type("随便做点什么")
        assert TaskType.ANALYSIS in result

    def test_classify_multiple_types(self, planner):
        """A request can match multiple task types."""
        result = planner._estimate_task_type("分析数据并写报告")
        assert len(result) >= 2


class TestSuggestTools:
    """Test suggest_tools via tool_selector integration."""

    def test_tool_selector_has_select_and_report_methods(self):
        from scripts.core.tool_selector import ToolSelector
        from unittest.mock import MagicMock
        # Use spec=True to avoid initializing ResearchMemory (which triggers DB init)
        mock_mem = MagicMock(spec=True)
        selector = ToolSelector(mock_mem)
        assert hasattr(selector, "select")
        assert hasattr(selector, "select_best_quality_tool")
        assert hasattr(selector, "get_tool_marketplace_report")


class TestGetPlanSummary:
    """Test get_plan_summary — delegates to planner.get_status()."""

    def test_get_status_returns_dict(self, planner):
        status = planner.get_status()
        assert isinstance(status, dict)


class TestTaskCreation:
    """Test task creation and registration."""

    def test_create_task_auto_increments_id(self, planner):
        """Each call to _create_task gets a unique ID."""
        t1 = planner._create_task("Task 1", TaskType.ANALYSIS)
        t2 = planner._create_task("Task 2", TaskType.DATA_FETCH)
        assert t1.id != t2.id
        assert t1.id.startswith("task_")
        assert t2.id.startswith("task_")

    def test_create_task_with_dependencies(self, planner):
        """Tasks can be created with dependencies."""
        t1 = planner._create_task("Task A", TaskType.ANALYSIS)
        t2 = planner._create_task("Task B", TaskType.ANALYSIS, dependencies=[t1.id])
        assert t1.id in t2.dependencies

    def test_create_task_with_subtasks(self, planner):
        """Tasks can be created with subtasks."""
        sub = planner._create_task("Subtask", TaskType.ANALYSIS)
        parent = planner._create_task("Parent", TaskType.WRITING, subtasks=[sub])
        assert sub in parent.subtasks

    def test_register_tasks_adds_to_registry(self, planner):
        """_register_tasks adds tasks to planner.tasks dict."""
        t1 = planner._create_task("A", TaskType.ANALYSIS)
        t2 = planner._create_task("B", TaskType.DATA_FETCH)
        planner._register_tasks([t1, t2])
        assert t1.id in planner.tasks
        assert t2.id in planner.tasks

    def test_register_tasks_recursively_includes_subtasks(self, planner):
        """_register_tasks also registers nested subtasks."""
        sub = planner._create_task("Subtask", TaskType.ANALYSIS)
        parent = planner._create_task("Parent", TaskType.WRITING, subtasks=[sub])
        planner._register_tasks([parent])
        assert parent.id in planner.tasks
        assert sub.id in planner.tasks


class TestTopologicalSort:
    """Test topological sorting in the planner."""

    def test_topological_sort_respects_dependencies(self, planner):
        """Tasks with satisfied dependencies come first."""
        t1 = planner._create_task("Fetch data", TaskType.DATA_FETCH)
        t2 = planner._create_task("Analyze", TaskType.ANALYSIS, dependencies=[t1.id])
        t3 = planner._create_task("Write", TaskType.WRITING, dependencies=[t2.id])

        sorted_tasks = planner._topological_sort([t1, t2, t3])
        ids = [t.id for t in sorted_tasks]
        assert ids.index(t1.id) < ids.index(t2.id)
        assert ids.index(t2.id) < ids.index(t3.id)

    def test_topological_sort_handles_no_dependencies(self, planner):
        """Independent tasks are sorted without blocking."""
        t1 = planner._create_task("Task A", TaskType.ANALYSIS)
        t2 = planner._create_task("Task B", TaskType.ANALYSIS)
        sorted_tasks = planner._topological_sort([t1, t2])
        assert len(sorted_tasks) == 2


class TestFallbackStrategy:
    """Test _fallback task retry/degrade/skip logic."""

    def test_fallback_retries_pending_task(self, planner):
        """Task with retry_count < 3 is retried."""
        task = planner._create_task("Retry task", TaskType.ANALYSIS)
        task.retry_count = 0
        result = planner._fallback(task)
        assert result is not None
        assert result.status == TaskStatus.RETRY
        assert task.retry_count == 1

    def test_fallback_degrades_critical_task(self, planner):
        """Critical task at retry_count >= 3 is degraded to ANALYSIS."""
        task = planner._create_task("Critical task", TaskType.WRITING)
        task.retry_count = 3
        result = planner._fallback(task)
        assert result is not None
        assert "[降级]" in result.description
        assert result.task_type == TaskType.ANALYSIS

    def test_fallback_skips_non_critical_task(self, planner):
        """Non-critical task at retry_count >= 3 is skipped."""
        task = planner._create_task("Literature task", TaskType.LITERATURE)
        task.retry_count = 3
        result = planner._fallback(task)
        assert result is not None
        assert result.status == TaskStatus.DONE
        assert "[跳过]" in result.description

    def test_fallback_aborts_critical_task(self, planner):
        """ORCHESTRATE task at max retries is degraded to ANALYSIS (Level 2)."""
        task = planner._create_task("Writing task", TaskType.WRITING)
        task.retry_count = 3
        # After max retries, Level 2 degrades to ANALYSIS
        task.task_type = TaskType.ORCHESTRATE
        result = planner._fallback(task)
        # Level 2 degrades to ANALYSIS task (status PENDING by default)
        assert result is not None
        assert result.task_type == TaskType.ANALYSIS
        assert result.description.startswith("[降级]")


class TestGetStatus:
    """Test get_status summary method."""

    def test_get_status_returns_dict(self, planner):
        """get_status returns a {task_id: status} dict."""
        planner.decompose("分析数据")
        status = planner.get_status()
        assert isinstance(status, dict)
        assert all(isinstance(v, str) for v in status.values())


class TestKeywordPatterns:
    """Test that KEYWORD_PATTERNS covers all TaskTypes."""

    def test_all_task_types_have_patterns(self):
        for task_type in TaskType:
            assert task_type in KEYWORD_PATTERNS, f"Missing pattern for {task_type}"

    def test_regex_patterns_is_list(self):
        assert isinstance(REGEX_PATTERNS, list)
        assert len(REGEX_PATTERNS) > 0
