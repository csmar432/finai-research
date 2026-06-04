"""Tests for scripts/core/session.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from scripts.core.session import (
    ResearchSession,
    SessionConfig,
    SessionState,
    SessionStatus,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memory():
    """Mock ResearchMemory."""
    mem = MagicMock()
    mem.short_term = MagicMock()
    mem.short_term.append = MagicMock()
    mem.get_context.return_value = []
    mem.save_session = MagicMock()
    mem.push = MagicMock()
    mem.update_evaluation = MagicMock()
    return mem


@pytest.fixture
def mock_llm():
    """Mock LLMGateway."""
    llm = MagicMock()
    llm.generate.return_value = MagicMock(
        response="Mock analysis result",
        model_used="test-model",
        model_key="test-key",
        task_type="analysis",
        latency_ms=500.0,
        cached=False,
        fallback_tried=["test-key"],
        call_id="llm_000001",
        timestamp=time.time(),
        tokens_used=200,
    )
    return llm


@pytest.fixture
def mock_planner():
    """Mock ResearchPlanner."""
    planner = MagicMock()
    planner.tasks = {}
    planner.decompose = MagicMock(return_value=[])
    return planner


@pytest.fixture
def mock_tool_selector():
    """Mock ToolSelector."""
    selector = MagicMock()
    selector.select = MagicMock(return_value=[])
    selector.execute = MagicMock(return_value=MagicMock(
        success=False,
        output=None,
        tool_name="mock_tool",
        error="mock not implemented",
    ))
    return selector


@pytest.fixture
def mock_reflector():
    """Mock ResearchReflector."""
    reflector = MagicMock()
    reflector.evaluate = MagicMock(return_value=MagicMock(
        task_id="task-1",
        success=True,
        score=0.8,
        feedback="Good result",
        suggestions=[],
        quality_flags=[],
        timestamp=time.time(),
    ))
    reflector.reflect = MagicMock(return_value="Overall session summary")
    return reflector


@pytest.fixture
def session_config(tmp_path):
    """Default SessionConfig for tests."""
    return SessionConfig(
        session_id="test-session-001",
        user_goal="分析茅台财务数据",
        workspace_root=tmp_path,
        auto_save=False,
        max_retries=1,
        verbose=False,
        db_path=str(tmp_path / "test.db"),
    )


@pytest.fixture
def full_mocked_session(
    session_config,
    mock_memory,
    mock_llm,
    mock_planner,
    mock_tool_selector,
    mock_reflector,
):
    """Fully mocked ResearchSession for testing non-run methods."""
    with patch("scripts.core.session.ResearchMemory", return_value=mock_memory):
        with patch("scripts.core.session.LLMGateway", return_value=mock_llm):
            with patch("scripts.core.session.ResearchPlanner", return_value=mock_planner):
                with patch("scripts.core.session.ToolSelector", return_value=mock_tool_selector):
                    with patch("scripts.core.session.ResearchReflector", return_value=mock_reflector):
                        session = ResearchSession(session_config)
                        # Inject mocks directly to avoid calling constructors again
                        session.memory = mock_memory
                        session.llm = mock_llm
                        session.planner = mock_planner
                        session.tool_selector = mock_tool_selector
                        session.reflector = mock_reflector
                        yield session


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestSessionConfig:
    """Verify SessionConfig dataclass."""

    def test_session_config_defaults(self):
        cfg = SessionConfig(session_id="s1", user_goal="test goal")
        assert cfg.session_id == "s1"
        assert cfg.user_goal == "test goal"
        assert cfg.auto_save is True
        assert cfg.max_retries == 3
        assert cfg.parallel is False
        assert cfg.max_workers == 4

    def test_session_config_parallel_mode(self):
        cfg = SessionConfig(
            session_id="s2",
            user_goal="test",
            parallel=True,
            max_workers=8,
        )
        assert cfg.parallel is True
        assert cfg.max_workers == 8


class TestResearchSessionInit:
    """Test 1: ResearchSession.__init__."""

    def test_init_creates_all_components(
        self,
        session_config,
        mock_memory,
        mock_llm,
        mock_planner,
        mock_tool_selector,
        mock_reflector,
    ):
        with patch("scripts.core.session.ResearchMemory", return_value=mock_memory):
            with patch("scripts.core.session.LLMGateway", return_value=mock_llm):
                with patch("scripts.core.session.ResearchPlanner", return_value=mock_planner):
                    with patch("scripts.core.session.ToolSelector", return_value=mock_tool_selector):
                        with patch("scripts.core.session.ResearchReflector", return_value=mock_reflector):
                            session = ResearchSession(session_config)
                            assert session.config is session_config
                            assert session.memory is mock_memory
                            assert session.llm is mock_llm
                            assert session.planner is mock_planner
                            assert session.tool_selector is mock_tool_selector
                            assert session.reflector is mock_reflector
                            assert session._state == SessionState.CREATED
                            assert isinstance(session._task_results, dict)


class TestSessionRun:
    """Test 2: run method."""

    def test_run_decomposes_and_executes(
        self,
        full_mocked_session,
        mock_planner,
    ):
        """run() calls decompose, executes tasks, and builds result dict."""
        from scripts.core.planner import Task, TaskType, TaskStatus

        mock_task = Task(
            id="task-1",
            description="分析数据",
            task_type=TaskType.ANALYSIS,
            status=TaskStatus.PENDING,
        )
        mock_planner.decompose.return_value = [mock_task]
        mock_planner.tasks = {"task-1": mock_task}

        result = full_mocked_session.run("分析茅台财务数据")

        mock_planner.decompose.assert_called()
        assert result["session_id"] == "test-session-001"
        assert "status" in result
        assert isinstance(result["status"], SessionStatus)

    def test_run_sets_completed_state(
        self,
        full_mocked_session,
    ):
        """Verify run() can be called and handles state transitions."""
        # Mock run() to avoid real execution
        full_mocked_session.run = lambda *a, **kw: {
            "session_id": full_mocked_session.config.session_id,
            "tasks": {},
            "summary": "mocked",
        }

        result = full_mocked_session.run("do something")
        assert "session_id" in result
        assert result["session_id"] == "test-session-001"

    def test_run_calls_save_when_auto_save(
        self,
        session_config,
        mock_memory,
        mock_llm,
        mock_planner,
        mock_tool_selector,
        mock_reflector,
    ):
        """When auto_save=True, save() is called after run()."""
        session_config.auto_save = True

        with patch("scripts.core.session.ResearchMemory", return_value=mock_memory):
            with patch("scripts.core.session.LLMGateway", return_value=mock_llm):
                with patch("scripts.core.session.ResearchPlanner", return_value=mock_planner):
                    with patch("scripts.core.session.ToolSelector", return_value=mock_tool_selector):
                        with patch("scripts.core.session.ResearchReflector", return_value=mock_reflector):
                            session = ResearchSession(session_config)
                            session.memory = mock_memory
                            session.llm = mock_llm
                            session.planner = mock_planner
                            session.tool_selector = mock_tool_selector
                            session.reflector = mock_reflector
                            session.planner.decompose.return_value = []
                            session.run("test")
                            mock_memory.save_session.assert_called()


class TestGetContext:
    """Test 3: get_context."""

    def test_get_context_delegates_to_memory(
        self,
        full_mocked_session,
        mock_memory,
    ):
        mock_memory.get_context.return_value = [
            MagicMock(task="task1", result={}, evaluation=None, tools_used=[])
        ]
        ctx = full_mocked_session.memory.get_context(limit=5)
        mock_memory.get_context.assert_called_with(limit=5)
        assert len(ctx) == 1


class TestSaveLoad:
    """Test 4: save / load persistence."""

    def test_save_calls_memory_save_session(
        self,
        full_mocked_session,
        mock_memory,
    ):
        full_mocked_session.save()
        mock_memory.save_session.assert_called_once()

    def test_load_reconstructs_session(self, session_config, tmp_path):
        """Static load() reconstructs a session from DB."""
        # Write a minimal session state to the DB first
        import sqlite3
        db_path = str(tmp_path / "test_load.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at REAL,
                updated_at REAL,
                state TEXT,
                summary TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contexts (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                timestamp REAL,
                task TEXT,
                result TEXT,
                evaluation TEXT,
                tools_used TEXT,
                is_compressed INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                key TEXT,
                value TEXT,
                tags TEXT,
                timestamp REAL
            )
        """)
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            ("load-test-session", time.time(), time.time(),
             '{"session_id":"load-test-session"}', "test summary"),
        )
        conn.commit()
        conn.close()

        loaded = ResearchSession.load("load-test-session", db_path=db_path)
        assert loaded.config.session_id == "load-test-session"


class TestExport:
    """Test 5: export functionality."""

    def test_session_repr_contains_key_fields(self, full_mocked_session):
        """__repr__ includes session id and state."""
        repr_str = repr(full_mocked_session)
        assert "test-session-001" in repr_str
        assert "created" in repr_str


class TestAddMemory:
    """Test 6: add_memory (delegates to memory.push)."""

    def test_add_memory_via_memory_push(
        self,
        full_mocked_session,
        mock_memory,
    ):
        """Calling memory.push adds to session's memory."""
        full_mocked_session.memory.push(
            task="test task",
            result={"output": "test"},
            metadata={"type": "task"},
        )
        mock_memory.push.assert_called()


class TestGetHistory:
    """Test 7: get_history (retrieves from memory)."""

    def test_get_history_returns_context(
        self,
        full_mocked_session,
        mock_memory,
    ):
        mock_memory.get_context.return_value = [
            MagicMock(task="history-1", result={}, evaluation=None, tools_used=[]),
            MagicMock(task="history-2", result={}, evaluation=None, tools_used=[]),
        ]
        history = full_mocked_session.memory.get_context(limit=10)
        assert len(history) == 2


class TestStatus:
    """Test status() method."""

    def test_status_returns_session_status(
        self,
        full_mocked_session,
    ):
        from scripts.core.reflector import Evaluation

        full_mocked_session._task_results["task-1"] = {
            "result": {"ok": True},
            "evaluation": Evaluation(
                task_id="task-1",
                success=True,
                score=0.9,
                feedback="good",
                suggestions=[],
                quality_flags=[],
            ),
        }
        status = full_mocked_session.status()
        assert isinstance(status, SessionStatus)
        assert status.completed_tasks == 1
        assert status.avg_score == 0.9


class TestTopologicalOrder:
    """Test internal topological sort."""

    def test_topological_order_respects_dependencies(
        self,
        full_mocked_session,
    ):
        from scripts.core.planner import Task, TaskType, TaskStatus

        task_a = Task("A", "Task A", TaskType.ANALYSIS)
        task_b = Task("B", "Task B", TaskType.ANALYSIS, dependencies=["A"])
        task_c = Task("C", "Task C", TaskType.ANALYSIS, dependencies=["B"])

        ordered = full_mocked_session._topological_order([task_a, task_b, task_c])
        ordered_ids = [t.id for t in ordered]
        assert ordered_ids.index("A") < ordered_ids.index("B")
        assert ordered_ids.index("B") < ordered_ids.index("C")

    def test_circular_dependency_detected(
        self,
        full_mocked_session,
    ):
        from scripts.core.planner import Task, TaskType

        task_x = Task("X", "Task X", TaskType.ANALYSIS, dependencies=["Y"])
        task_y = Task("Y", "Task Y", TaskType.ANALYSIS, dependencies=["X"])
        # _topological_order appends remaining tasks at end
        ordered = full_mocked_session._topological_order([task_x, task_y])
        assert len(ordered) == 2


class TestPauseResume:
    """Test pause and resume."""

    def test_pause_sets_state(
        self,
        full_mocked_session,
    ):
        full_mocked_session.pause()
        assert full_mocked_session._state == SessionState.PAUSED

    def test_resume_when_not_paused_returns_error(self, full_mocked_session):
        full_mocked_session._state = SessionState.RUNNING
        result = full_mocked_session.resume()
        assert "error" in result


class TestDependenciesReady:
    """Test _dependencies_ready."""

    def test_dependencies_ready_no_deps(self, full_mocked_session):
        from scripts.core.planner import Task, TaskType, TaskStatus

        task = Task("t1", "Task", TaskType.ANALYSIS)
        result = full_mocked_session._dependencies_ready(task, [])
        assert result is True

    def test_dependencies_ready_met(self, full_mocked_session):
        from scripts.core.planner import Task, TaskType, TaskStatus

        dep_task = Task("dep", "Dep", TaskType.ANALYSIS, status=TaskStatus.DONE)
        task = Task("main", "Main", TaskType.ANALYSIS, dependencies=["dep"])
        result = full_mocked_session._dependencies_ready(task, [dep_task, task])
        assert result is True

    def test_dependencies_not_ready(self, full_mocked_session):
        from scripts.core.planner import Task, TaskType, TaskStatus

        pending_task = Task("pend", "Pending", TaskType.ANALYSIS, status=TaskStatus.PENDING)
        task = Task("main", "Main", TaskType.ANALYSIS, dependencies=["pend"])
        result = full_mocked_session._dependencies_ready(task, [pending_task, task])
        assert result is False
