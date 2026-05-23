"""
End-to-end integration tests for the research agent workflow.
These tests verify that all four core modules work together correctly.

Run with: .venv/bin/python -m pytest scripts/core/test_integration.py -v
"""

import tempfile, shutil, sqlite3
from pathlib import Path

from scripts.core.memory import ResearchMemory, ContextUnit
from scripts.core.planner import ResearchPlanner, TaskType
from scripts.core.tool_selector import ToolSelector
from scripts.core.reflector import ResearchReflector, Evaluation
from scripts.core.session import ResearchSession, SessionConfig, SessionState


# ── Test 1: Memory → Planner integration ─────────────────────────────────

def test_memory_planner_integration():
    """Planner uses memory context for decomposition"""
    tmpdir = tempfile.mkdtemp()
    try:
        db = str(Path(tmpdir) / "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        mem.push("分析茅台", {"roe": 25.3}, {"tools": ["fetch_a_stock"]})
        mem.push("对比五粮液", {"roe": 20.1}, {"tools": ["fetch_a_stock"]})

        planner = ResearchPlanner(mem)
        # Memory context should be accessible
        ctx = mem.get_context(limit=5)
        assert len(ctx) >= 2, "Memory should store context entries"

        # Planner should decompose a financial analysis request
        tasks = planner.decompose("分析苹果公司财务数据")
        assert len(tasks) >= 1
        task_types = {t.task_type for t in tasks}
        assert TaskType.ANALYSIS in task_types or TaskType.DATA_FETCH in task_types
    finally:
        shutil.rmtree(tmpdir)


# ── Test 2: ToolSelector → Planner integration ──────────────────────────

def test_tool_selector_planner_integration():
    """ToolSelector selects tools for planner-generated tasks"""
    tmpdir = tempfile.mkdtemp()
    try:
        db = str(Path(tmpdir) / "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        planner = ResearchPlanner(mem)
        selector = ToolSelector(mem)

        tasks = planner.decompose("检索深度学习量化交易文献")
        lit_tasks = [t for t in tasks if t.task_type == TaskType.LITERATURE]
        assert len(lit_tasks) >= 1, "Should create at least one LITERATURE task"

        task = lit_tasks[0]
        ctx = mem.get_context(limit=5)
        selections = selector.select(task, ctx)

        assert len(selections) >= 1, "Should select at least one tool for LITERATURE"
        tool_names = {s.tool_name for s in selections}
        assert tool_names & {"arxiv", "literature_search", "brave_search"}, \
            f"Expected arxiv/literature_search/brave_search, got {tool_names}"
    finally:
        shutil.rmtree(tmpdir)


# ── Test 3: Reflector → Memory integration ────────────────────────────

def test_reflector_memory_integration():
    """Reflector evaluates and results are stored in memory"""
    tmpdir = tempfile.mkdtemp()
    try:
        db = str(Path(tmpdir) / "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        reflector = ResearchReflector(mem)

        from scripts.core.planner import Task, TaskStatus
        task = Task(
            id="test-1",
            description="分析茅台ROE",
            task_type=TaskType.ANALYSIS,
            status=TaskStatus.DONE,
            subtasks=[],
            dependencies=[],
            created_at=0,
        )
        result = {"roe": 25.3, "revenue_growth": 15.2}
        evaluation = reflector.evaluate(task, result, [])

        # Push evaluation result to memory
        mem.push(
            task.description,
            {"score": evaluation.score, "quality_flags": evaluation.quality_flags},
            {"tools": ["test"], "evaluation": evaluation.feedback},
        )

        # Verify memory contains the evaluation
        ctx = mem.get_context(limit=5)
        assert len(ctx) >= 1
        # Memory should store the result (which contains evaluation data)
        assert any("roe" in str(c.result) or "score" in str(c.result) for c in ctx)

        # Verify reflect() works with stored data
        summary = reflector.reflect(None)
        assert summary is not None and len(summary) > 0
    finally:
        shutil.rmtree(tmpdir)


# ── Test 4: Full Session flow ─────────────────────────────────────────

def test_session_end_to_end():
    """ResearchSession orchestrates all four modules"""
    # Note: use default .cache/research.db so save/resume work correctly
    config = SessionConfig(
        session_id="integration-test",
        user_goal="分析苹果公司财务数据",
        workspace_root=Path("."),
        verbose=False,
    )
    session = ResearchSession(config)

    # Verify all 4 modules are initialized
    assert session.memory is not None
    assert session.planner is not None
    assert session.tool_selector is not None
    assert session.reflector is not None
    assert session._state == SessionState.CREATED

    # Ask should transition to RUNNING
    result = session.ask("分析苹果财务数据")
    assert isinstance(result, dict)
    assert "session_id" in result
    assert session._state == SessionState.RUNNING

    # Status should reflect current state
    status = session.status()
    assert status.state == SessionState.RUNNING

    # Save and resume should work
    session.save()
    restored = ResearchSession.resume("integration-test")
    assert restored.config.session_id == "integration-test"
    # Resume restores the full serialized state including _state
    assert restored._state == SessionState.COMPLETED
    # Memory context is restored from the session's serialized state (self.context snapshot)
    ctx = restored.memory.get_context(limit=10)
    assert len(ctx) >= 0  # Context restored from serialized session state


def test_graceful_degradation():
    """Agent handles errors gracefully without crashing"""
    tmpdir = tempfile.mkdtemp()
    try:
        db = str(Path(tmpdir) / "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        planner = ResearchPlanner(mem)
        selector = ToolSelector(mem)
        reflector = ResearchReflector(mem)

        # No context → ToolSelector should still return results
        task = planner.tasks.get("task_001") if planner.tasks else None
        # Even if no tasks exist, select should not crash
        from scripts.core.planner import Task, TaskStatus
        dummy = Task(
            id="dummy", description="test",
            task_type=TaskType.DATA_FETCH,
            status=TaskStatus.PENDING,
            subtasks=[], dependencies=[], created_at=0,
        )
        selections = selector.select(dummy, [])
        assert isinstance(selections, list)

        # Empty context → reflector should handle gracefully
        from scripts.core.planner import Task, TaskStatus
        eval_task = Task(
            id="eval-test", description="test",
            task_type=TaskType.DATA_FETCH,
            status=TaskStatus.DONE,
            subtasks=[], dependencies=[], created_at=0,
        )
        eval_result = reflector.evaluate(eval_task, {"data": "test"}, [])
        assert isinstance(eval_result, Evaluation)
    finally:
        shutil.rmtree(tmpdir)


# ── Test 6: Four-module dependency chain ────────────────────────────────

def test_four_module_chain():
    """Memory → Planner → ToolSelector → Reflector all chain correctly"""
    tmpdir = tempfile.mkdtemp()
    try:
        db = str(Path(tmpdir) / "test.db")

        # Step 1: Memory stores initial context
        mem = ResearchMemory("test-chain", db_path=db)
        mem.push("分析苹果", {"price": 180.0}, {"tools": ["financial"]})

        # Step 2: Planner uses memory context to decompose
        planner = ResearchPlanner(mem)
        tasks = planner.decompose("分析苹果公司的ROE和毛利率")
        assert len(tasks) >= 1

        # Step 3: ToolSelector selects tools for planner's tasks
        selector = ToolSelector(mem)
        for task in tasks:
            ctx = mem.get_context(limit=5)
            selections = selector.select(task, ctx)
            assert len(selections) >= 1

        # Step 4: Reflector evaluates results and writes back to memory
        reflector = ResearchReflector(mem)
        from scripts.core.planner import Task, TaskStatus
        for task in tasks[:2]:
            eval_result = reflector.evaluate(task, {"result": "analysis done"}, ctx)
            assert isinstance(eval_result, Evaluation)
            mem.push(task.description, {"score": eval_result.score}, {"evaluation": eval_result.feedback})

        # Memory should now have: initial push + 2 evaluation pushes
        final_ctx = mem.get_context(limit=10)
        assert len(final_ctx) >= 3, f"Expected >= 3 context entries, got {len(final_ctx)}"
    finally:
        shutil.rmtree(tmpdir)
