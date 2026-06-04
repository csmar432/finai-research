"""Tests for ResearchReflector — four-dimensional result evaluation."""

from scripts.core.memory import ResearchMemory
from scripts.core.planner import Task, TaskStatus, TaskType
from scripts.core.reflector import ResearchReflector


def test_evaluate_financial_data():
    """Valid financial metrics should produce a passing score."""
    mem = ResearchMemory("test", db_path=":memory:")
    reflector = ResearchReflector(mem)
    task = Task(
        id="t1",
        description="分析茅台ROE",
        task_type=TaskType.ANALYSIS,
        status=TaskStatus.DONE,
        subtasks=[],
        dependencies=[],
        created_at=0,
    )
    result = {"roe": 25.3, "revenue_growth": 15.2, "data_source": "akshare"}
    eval_result = reflector.evaluate(task, result, [])
    assert eval_result.success is True, f"Expected success=True, got {eval_result.success} (score={eval_result.score})"
    assert eval_result.score >= 0.7, f"Expected score >= 0.7, got {eval_result.score}"


def test_evaluate_incomplete_result():
    """Result missing required fields should be flagged as missing_data."""
    mem = ResearchMemory("test", db_path=":memory:")
    reflector = ResearchReflector(mem)
    task = Task(
        id="t2",
        description="获取财报",
        task_type=TaskType.DATA_FETCH,
        status=TaskStatus.DONE,
        subtasks=[],
        dependencies=[],
        created_at=0,
    )
    result = {"revenue": None}
    eval_result = reflector.evaluate(task, result, [])
    assert "missing_data" in eval_result.quality_flags, (
        f"Expected 'missing_data' in quality_flags, got {eval_result.quality_flags}"
    )
    assert eval_result.success is False, f"Expected success=False, got {eval_result.success}"


def test_quality_flag_inconsistency():
    """A result that contradicts a historical one should be flagged inconsistent."""
    mem = ResearchMemory("test", db_path=":memory:")
    mem.push("分析苹果PE", {"pe": 25.0}, {"tools": ["financial"]})
    reflector = ResearchReflector(mem)
    task = Task(
        id="t3",
        description="再次分析苹果PE",
        task_type=TaskType.ANALYSIS,
        status=TaskStatus.DONE,
        subtasks=[],
        dependencies=[],
        created_at=0,
    )
    result = {"pe": 150.0}
    eval_result = reflector.evaluate(task, result, mem.get_context())
    assert "inconsistent" in eval_result.quality_flags, (
        f"Expected 'inconsistent' in quality_flags, got {eval_result.quality_flags}"
    )


def test_accuracy_check():
    """Out-of-range financial values should trigger needs_verification flag."""
    mem = ResearchMemory("test", db_path=":memory:")
    reflector = ResearchReflector(mem)
    task = Task(
        id="t4",
        description="分析财务指标",
        task_type=TaskType.ANALYSIS,
        status=TaskStatus.DONE,
        subtasks=[],
        dependencies=[],
        created_at=0,
    )
    result = {"roe": 999.0, "pe": -5.0}
    eval_result = reflector.evaluate(task, result, [])
    assert "needs_verification" in eval_result.quality_flags, (
        f"Expected 'needs_verification' in quality_flags, got {eval_result.quality_flags}"
    )
    assert eval_result.score < 0.7, f"Expected score < 0.7, got {eval_result.score}"


def test_reflect():
    """reflect() should return a non-empty string summarizing the session."""
    mem = ResearchMemory("test", db_path=":memory:")
    reflector = ResearchReflector(mem)
    task1 = Task(
        id="t1",
        description="分析茅台",
        task_type=TaskType.ANALYSIS,
        status=TaskStatus.DONE,
        subtasks=[],
        dependencies=[],
        created_at=0,
    )
    eval1 = reflector.evaluate(task1, {"roe": 25.3}, [])
    mem.push("分析茅台", eval1.feedback, {"evaluation": eval1.feedback})
    summary = reflector.reflect(None)
    assert summary is not None
    assert len(summary) > 0
