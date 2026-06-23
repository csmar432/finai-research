"""Tests for scripts/core/multi_agent.py — MultiAgentOrchestrator, WorkflowTemplates."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from scripts.core.multi_agent import (
    MultiAgentOrchestrator,
    WorkflowTemplates,
    TaskStatus,
    ExecutionMode,
    Agent,
    Task,
    Workflow,
    DefaultAgentExecutor,
    create_default,
)


# ── TaskStatus ────────────────────────────────────────────────────────────────


class TestTaskStatus:
    def test_all_task_statuses_exist(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


# ── ExecutionMode ────────────────────────────────────────────────────────────


class TestExecutionMode:
    def test_all_execution_modes_exist(self):
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"
        assert ExecutionMode.PIPELINE.value == "pipeline"


# ── Agent Dataclass ───────────────────────────────────────────────────────────


class TestAgentDataclass:
    def test_agent_creation(self):
        agent = Agent(
            agent_id="research_designer",
            name="研究设计专家",
            role="负责研究设计",
            capabilities=["research_design", "hypothesis"],
            system_prompt="You are a research designer.",
        )
        assert agent.agent_id == "research_designer"
        assert agent.max_concurrent == 1  # default


# ── Task Dataclass ────────────────────────────────────────────────────────────


class TestTaskDataclass:
    def test_task_creation(self):
        task = Task(
            task_id="task_001",
            name="文献检索",
            description="检索碳排放相关文献",
            required_capabilities=["literature_search"],
            input_data={"query": "carbon trading"},
        )
        assert task.task_id == "task_001"
        assert task.status == TaskStatus.PENDING
        assert task.assigned_agent_id is None
        assert task.result is None

    def test_task_with_defaults(self):
        task = Task(
            task_id="task_002",
            name="数据分析",
            description="分析数据",
            required_capabilities=["statistics"],
            input_data={},
        )
        assert task.input_data == {}


# ── Workflow Dataclass ────────────────────────────────────────────────────────


class TestWorkflowDataclass:
    def test_workflow_creation(self):
        wf = Workflow(
            workflow_id="wf_001",
            name="论文写作流程",
            description="端到端论文写作",
            agents=[],
            tasks=[],
            execution_mode=ExecutionMode.SEQUENTIAL,
            dependencies={},
        )
        assert wf.workflow_id == "wf_001"
        assert wf.execution_mode == ExecutionMode.SEQUENTIAL


# ── DefaultAgentExecutor ──────────────────────────────────────────────────────


class TestDefaultAgentExecutor:
    def test_executor_initializes_without_llm(self):
        executor = DefaultAgentExecutor()
        assert executor.llm_provider is None

    def test_executor_initializes_with_llm(self):
        mock_llm = MagicMock()
        executor = DefaultAgentExecutor(llm_provider=mock_llm)
        assert executor.llm_provider is mock_llm

    def test_execute_without_llm_returns_mock_result(self):
        executor = DefaultAgentExecutor()
        mock_agent = MagicMock()
        mock_agent.agent_id = "agent_001"
        mock_agent.system_prompt = "You are a test agent."
        mock_task = MagicMock()
        mock_task.task_id = "task_001"
        mock_task.name = "Test task"
        mock_task.description = "A test task"
        mock_task.input_data = {}

        result = executor.execute(mock_agent, mock_task)
        assert isinstance(result, dict)
        assert result["agent_id"] == "agent_001"
        assert result["task_id"] == "task_001"

    def test_execute_with_llm_calls_provider(self):
        mock_llm = MagicMock(return_value={"llm_response": "done"})
        executor = DefaultAgentExecutor(llm_provider=mock_llm)

        mock_agent = MagicMock()
        mock_agent.agent_id = "agent_001"
        mock_agent.system_prompt = "You are a test agent."
        mock_task = MagicMock()
        mock_task.task_id = "task_001"
        mock_task.name = "Test task"
        mock_task.description = "A test task"
        mock_task.input_data = {}

        result = executor.execute(mock_agent, mock_task)
        mock_llm.assert_called_once()
        assert result == {"llm_response": "done"}

    def test_async_execute_returns_awaitable(self):
        """async_execute returns a coroutine (do not await in sync test)."""
        executor = DefaultAgentExecutor()

        mock_agent = MagicMock()
        mock_agent.agent_id = "agent_001"
        mock_agent.system_prompt = "You are a test agent."
        mock_task = MagicMock()
        mock_task.task_id = "task_001"
        mock_task.name = "Test task"
        mock_task.description = "A test task"
        mock_task.input_data = {}

        result = executor.async_execute(mock_agent, mock_task)
        # It must be a coroutine (awaitable)
        import asyncio

        assert asyncio.iscoroutine(result)
        # Clean up without awaiting
        result.close()


# ── MultiAgentOrchestrator Init ───────────────────────────────────────────────


class TestMultiAgentOrchestratorInit:
    def test_orchestrator_initializes(self):
        orch = MultiAgentOrchestrator()
        assert orch is not None

    def test_orchestrator_with_custom_executor(self):
        executor = DefaultAgentExecutor()
        orch = MultiAgentOrchestrator(executor=executor)
        assert orch.executor is executor

    def test_agents_dict_initializes(self):
        orch = MultiAgentOrchestrator()
        assert hasattr(orch, "_agents")
        assert isinstance(orch._agents, dict)

    def test_tasks_dict_initializes(self):
        orch = MultiAgentOrchestrator()
        assert hasattr(orch, "_tasks")
        assert isinstance(orch._tasks, dict)

    def test_workflows_dict_initializes(self):
        orch = MultiAgentOrchestrator()
        assert hasattr(orch, "_workflows")
        assert isinstance(orch._workflows, dict)

    def test_results_dict_initializes(self):
        orch = MultiAgentOrchestrator()
        assert hasattr(orch, "_results")
        assert isinstance(orch._results, dict)

    def test_active_tokens_initializes_empty(self):
        orch = MultiAgentOrchestrator()
        assert hasattr(orch, "_active_tokens")
        assert orch._active_tokens == {}

    def test_registers_default_agents(self):
        orch = MultiAgentOrchestrator()
        # Should have 5 default agents registered
        assert len(orch._agents) == 5
        expected_ids = {
            "research_designer",
            "literature_reviewer",
            "data_analyst",
            "paper_writer",
            "reviewer",
        }
        assert set(orch._agents.keys()) == expected_ids

    def test_create_default_helper(self):
        instance = create_default()
        assert isinstance(instance, MultiAgentOrchestrator)
        assert len(instance._agents) == 5


# ── Agent Registry ────────────────────────────────────────────────────────────


class TestAgentRegistry:
    def test_register_agent(self):
        orch = MultiAgentOrchestrator()
        initial_count = len(orch._agents)

        new_agent = Agent(
            agent_id="custom_agent",
            name="Custom Agent",
            role="Custom role",
            capabilities=["custom"],
            system_prompt="Custom prompt",
        )
        result = orch.register_agent(new_agent)
        assert result is True
        assert "custom_agent" in orch._agents
        assert len(orch._agents) == initial_count + 1

    def test_register_duplicate_returns_false(self):
        orch = MultiAgentOrchestrator()
        agent = Agent(
            agent_id="research_designer",  # Already exists as default
            name="Duplicate",
            role="Role",
            capabilities=["x"],
            system_prompt="Prompt",
        )
        result = orch.register_agent(agent)
        assert result is False

    def test_unregister_agent(self):
        orch = MultiAgentOrchestrator()
        ok = orch.unregister_agent("research_designer")
        assert ok is True
        assert "research_designer" not in orch._agents

    def test_unregister_nonexistent_returns_false(self):
        orch = MultiAgentOrchestrator()
        ok = orch.unregister_agent("ghost_agent")
        assert ok is False

    def test_get_agent(self):
        orch = MultiAgentOrchestrator()
        agent = orch.get_agent("paper_writer")
        assert agent is not None
        assert agent.agent_id == "paper_writer"

    def test_get_nonexistent_agent(self):
        orch = MultiAgentOrchestrator()
        assert orch.get_agent("nonexistent") is None

    def test_list_agents(self):
        orch = MultiAgentOrchestrator()
        agents = orch.list_agents()
        assert len(agents) == 5
        assert all(isinstance(a, Agent) for a in agents)


# ── Agent Selection ───────────────────────────────────────────────────────────


class TestAgentSelection:
    def test_find_best_agent_exact_match(self):
        orch = MultiAgentOrchestrator()
        agent = orch.find_best_agent(["literature_search", "analysis"])
        # literature_reviewer has literature_search in capabilities
        assert agent is not None
        assert agent.agent_id == "literature_reviewer"

    def test_find_best_agent_partial_match(self):
        orch = MultiAgentOrchestrator()
        agent = orch.find_best_agent(["academic_writing"])
        assert agent is not None
        assert agent.agent_id == "paper_writer"

    def test_find_best_agent_no_match(self):
        orch = MultiAgentOrchestrator()
        agent = orch.find_best_agent(["nonexistent_capability"])
        assert agent is None


# ── Task Creation ─────────────────────────────────────────────────────────────


class TestTaskCreation:
    def test_create_task(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="文献检索",
            description="检索碳排放相关文献",
            required_capabilities=["literature_search"],
            input_data={"query": "carbon"},
        )
        assert task.task_id is not None
        assert task.name == "文献检索"
        assert task.status == TaskStatus.PENDING
        assert task.task_id in orch._tasks

    def test_create_task_with_defaults(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="分析",
            description="分析数据",
            required_capabilities=["statistics"],
        )
        assert task.input_data == {}

    def test_get_task(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="分析",
            description="分析",
            required_capabilities=["statistics"],
        )
        retrieved = orch.get_task(task.task_id)
        assert retrieved is task

    def test_get_nonexistent_task(self):
        orch = MultiAgentOrchestrator()
        assert orch.get_task("ghost") is None


# ── Task Assignment ───────────────────────────────────────────────────────────


class TestTaskAssignment:
    def test_assign_task_success(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="写作",
            description="撰写论文",
            required_capabilities=["academic_writing"],
        )
        ok = orch.assign_task(task.task_id, "paper_writer")
        assert ok is True
        assert task.assigned_agent_id == "paper_writer"

    def test_assign_task_invalid_task(self):
        orch = MultiAgentOrchestrator()
        ok = orch.assign_task("ghost_task", "paper_writer")
        assert ok is False

    def test_assign_task_invalid_agent(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="写作",
            description="撰写",
            required_capabilities=["academic_writing"],
        )
        ok = orch.assign_task(task.task_id, "ghost_agent")
        assert ok is False


# ── Task Execution ────────────────────────────────────────────────────────────


class TestTaskExecution:
    def test_execute_task_success(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="写作",
            description="撰写论文",
            required_capabilities=["academic_writing"],
        )

        result = orch.execute_task(task.task_id)
        assert result is not None
        assert isinstance(result, dict)

        # Task should be completed
        updated_task = orch.get_task(task.task_id)
        assert updated_task.status == TaskStatus.COMPLETED
        assert updated_task.result is not None

    def test_execute_task_auto_assigns_agent(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="数据分析",
            description="分析数据",
            required_capabilities=["data_processing", "statistics"],
        )

        result = orch.execute_task(task.task_id)
        assert task.assigned_agent_id is not None

    def test_execute_task_unknown_id_raises(self):
        orch = MultiAgentOrchestrator()
        with pytest.raises(ValueError, match="不存在"):
            orch.execute_task("ghost_task_id")

    def test_execute_task_no_capable_agent_raises(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="Impossible task",
            description="Impossible",
            required_capabilities=["nonexistent_superpower"],
        )
        with pytest.raises(ValueError, match="没有找到合适的"):
            orch.execute_task(task.task_id)

    def test_execute_task_failure_sets_status(self):
        orch = MultiAgentOrchestrator()

        # Give the executor a callable that raises
        def failing_execute(agent, task):
            raise RuntimeError("Intentional failure")

        orch.executor.execute = failing_execute

        # Task must have capabilities matching an existing agent so executor runs
        task = orch.create_task(
            name="Failing task",
            description="This will fail",
            required_capabilities=["research_design"],
        )

        with pytest.raises(RuntimeError, match="Intentional failure"):
            orch.execute_task(task.task_id)

        updated_task = orch.get_task(task.task_id)
        assert updated_task.status == TaskStatus.FAILED


# ── Parallel Execution ─────────────────────────────────────────────────────────


class TestParallelExecution:
    def test_execute_parallel_returns_results_and_errors(self):
        orch = MultiAgentOrchestrator()

        task1 = orch.create_task(
            name="Task 1",
            description="First task",
            required_capabilities=["research_design"],
        )
        task2 = orch.create_task(
            name="Task 2",
            description="Second task",
            required_capabilities=["literature_search"],
        )

        result = orch.execute_parallel([task1.task_id, task2.task_id])
        assert "results" in result
        assert "errors" in result
        assert task1.task_id in result["results"]
        assert task2.task_id in result["results"]


# ── Sequential Execution ──────────────────────────────────────────────────────


class TestSequentialExecution:
    def test_execute_sequential_returns_results_and_errors(self):
        orch = MultiAgentOrchestrator()

        task1 = orch.create_task(
            name="Seq Task 1",
            description="First",
            required_capabilities=["research_design"],
        )
        task2 = orch.create_task(
            name="Seq Task 2",
            description="Second",
            required_capabilities=["literature_search"],
        )

        result = orch.execute_sequential([task1.task_id, task2.task_id])
        assert "results" in result
        assert "errors" in result
        assert task1.task_id in result["results"]
        assert task2.task_id in result["results"]


# ── Pipeline Execution ────────────────────────────────────────────────────────


class TestPipelineExecution:
    def test_execute_pipeline_simple_chain(self):
        orch = MultiAgentOrchestrator()

        task1 = orch.create_task(
            name="Step 1",
            description="First step",
            required_capabilities=["research_design"],
        )
        task2 = orch.create_task(
            name="Step 2",
            description="Second step",
            required_capabilities=["literature_search"],
        )
        task3 = orch.create_task(
            name="Step 3",
            description="Third step",
            required_capabilities=["data_processing"],
        )

        # task3 depends on task2, task2 depends on task1
        dependencies = {
            task2.task_id: [task1.task_id],
            task3.task_id: [task2.task_id],
        }

        result = orch.execute_pipeline(
            task_ids=[task1.task_id, task2.task_id, task3.task_id],
            dependencies=dependencies,
        )

        assert "results" in result
        assert "errors" in result
        assert task1.task_id in result["results"]
        assert task2.task_id in result["results"]
        assert task3.task_id in result["results"]

    def test_execute_pipeline_with_parallel_batches(self):
        orch = MultiAgentOrchestrator()

        t1 = orch.create_task("T1", "Step 1", ["research_design"])
        t2 = orch.create_task("T2", "Step 2", ["literature_search"])
        t3 = orch.create_task("T3", "Step 3", ["data_processing"])

        # t2 and t3 both depend on t1, can run in parallel after t1
        dependencies = {
            t2.task_id: [t1.task_id],
            t3.task_id: [t1.task_id],
        }

        result = orch.execute_pipeline(
            task_ids=[t1.task_id, t2.task_id, t3.task_id],
            dependencies=dependencies,
        )
        assert t1.task_id in result["results"]
        assert t2.task_id in result["results"]
        assert t3.task_id in result["results"]


# ── Results ────────────────────────────────────────────────────────────────────


class TestResults:
    def test_get_results_returns_all(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="Result test",
            description="Test",
            required_capabilities=["research_design"],
        )
        orch.execute_task(task.task_id)

        results = orch.get_results()
        assert task.task_id in results

    def test_get_result_returns_single(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="Single result",
            description="Test",
            required_capabilities=["research_design"],
        )
        orch.execute_task(task.task_id)

        result = orch.get_result(task.task_id)
        assert result is not None

    def test_get_result_nonexistent(self):
        orch = MultiAgentOrchestrator()
        assert orch.get_result("ghost") is None


# ── Cancellation ──────────────────────────────────────────────────────────────


class TestCancellation:
    def test_cancel_task_returns_false_when_not_active(self):
        orch = MultiAgentOrchestrator()
        ok = orch.cancel_task("ghost_task")
        assert ok is False

    def test_is_task_active_false_initially(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="Test",
            description="Test",
            required_capabilities=["research_design"],
        )
        assert orch.is_task_active(task.task_id) is False

    def test_get_task_status(self):
        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="Status test",
            description="Test",
            required_capabilities=["research_design"],
        )
        status = orch.get_task_status(task.task_id)
        assert status == TaskStatus.PENDING


# ── WorkflowTemplates ─────────────────────────────────────────────────────────


class TestWorkflowTemplates:
    def test_paper_writing_workflow_returns_tasks(self):
        orch = MultiAgentOrchestrator()
        tasks = WorkflowTemplates.paper_writing_workflow(orch)

        assert isinstance(tasks, list)
        assert len(tasks) == 5

        task_names = {t.name for t in tasks}
        expected = {"研究设计", "文献综述", "数据分析", "论文写作", "论文审核"}
        assert task_names == expected

    def test_paper_writing_tasks_have_correct_capabilities(self):
        orch = MultiAgentOrchestrator()
        tasks = WorkflowTemplates.paper_writing_workflow(orch)

        for task in tasks:
            assert len(task.required_capabilities) >= 1
            assert task.status == TaskStatus.PENDING
            assert task.task_id is not None

    def test_workflow_tasks_registered_in_orchestrator(self):
        orch = MultiAgentOrchestrator()
        tasks = WorkflowTemplates.paper_writing_workflow(orch)

        for task in tasks:
            assert task.task_id in orch._tasks


# ── Async Execution ───────────────────────────────────────────────────────────


class TestAsyncExecution:
    def test_async_execute_task_success(self):
        import asyncio

        orch = MultiAgentOrchestrator()
        task = orch.create_task(
            name="Async test",
            description="Async task",
            required_capabilities=["research_design"],
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(orch.async_execute_task(task.task_id))
            assert result is not None
        finally:
            loop.close()

        updated_task = orch.get_task(task.task_id)
        assert updated_task.status == TaskStatus.COMPLETED

    def test_async_execute_task_unknown_id_raises(self):
        import asyncio

        orch = MultiAgentOrchestrator()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(ValueError, match="不存在"):
                loop.run_until_complete(orch.async_execute_task("ghost"))
        finally:
            loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
