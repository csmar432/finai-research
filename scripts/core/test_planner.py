"""Tests for scripts/core/planner.py — ResearchPlanner decomposition and fallback."""


from scripts.core.memory import ResearchMemory
from scripts.core.planner import ResearchPlanner, TaskStatus, TaskType


def test_decompose_paper():
    """Test that writing a paper decomposes into outline + chapter + assemble tasks."""
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("帮我写一篇深度学习量化交易的论文，目标NeurIPS")
    assert len(tasks) >= 3, f"Expected >=3 tasks, got {len(tasks)}"
    assert any(t.task_type == TaskType.WRITING for t in tasks), "Should have WRITING task"


def test_decompose_analysis():
    """Test that financial analysis decomposes into DATA_FETCH + ANALYSIS tasks."""
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("分析苹果公司2024年的ROE和毛利率")
    assert any(t.task_type == TaskType.DATA_FETCH for t in tasks), "Should have DATA_FETCH task"
    assert any(t.task_type == TaskType.ANALYSIS for t in tasks), "Should have ANALYSIS task"


def test_topological_order():
    """Test that literature search + review creates proper task graph with dependencies."""
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("检索文献并写综述")

    lit_task = next((t for t in tasks if t.task_type == TaskType.LITERATURE), None)
    assert lit_task is not None, "Should have a LITERATURE task"

    # All dependencies must reference valid task IDs
    all_ids = {t.id for t in tasks}
    for t in tasks:
        for dep in t.dependencies:
            assert dep in all_ids, f"Dependency '{dep}' not found in task graph"


def test_fallback_retry():
    """Test that failed non-critical tasks are retried (retry_count < 3)."""
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("分析苹果公司财务数据")
    task = tasks[0]
    task.status = TaskStatus.FAILED
    task.retry_count = 0
    fallback = planner._fallback(task)
    # Should return a RETRY task since retry_count < 3
    assert fallback is not None
    assert fallback.retry_count == 1

    # After 3 retries exhausted → Level 3: non-critical tasks get skipped (DATA_FETCH not in CRITICAL_TYPES)
    task.retry_count = 3
    fallback2 = planner._fallback(task)
    assert fallback2 is not None
    # Level 3 skips non-critical tasks with status DONE
    assert fallback2.status == TaskStatus.DONE and "[跳过]" in fallback2.description


def test_get_status():
    """Test that get_status returns status for all registered tasks."""
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("分析苹果公司财务数据")
    status = planner.get_status()
    # All registered tasks (root + subtasks) should appear in status
    assert len(status) == len(planner.tasks), f"Expected {len(planner.tasks)} tasks in status, got {len(status)}"
    valid_statuses = [s.value for s in TaskStatus]
    assert all(s in valid_statuses for s in status.values()), "All statuses should be valid TaskStatus values"
