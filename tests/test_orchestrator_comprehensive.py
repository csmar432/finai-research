"""Comprehensive tests for scripts/core/orchestrator.py

Tests AgentOrchestrator, PipelineStage, PipelineStep, PipelineResult,
message bus, HITL integration, evolution engine, and tracing.
All tests use extensive mocking — no real API keys or LLM access needed.
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure the scripts package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPipelineStageEnum:
    """Test PipelineStage enum and constants."""

    def test_pipeline_stage_enum_exists(self):
        """PipelineStage enum can be imported."""
        from scripts.core.orchestrator import PipelineStage
        assert PipelineStage is not None

    def test_pipeline_stage_has_outline(self):
        """PipelineStage.OUTLINE exists."""
        from scripts.core.orchestrator import PipelineStage
        assert PipelineStage.OUTLINE.value == "outline"

    def test_pipeline_stage_has_literature(self):
        """PipelineStage.LITERATURE exists."""
        from scripts.core.orchestrator import PipelineStage
        assert PipelineStage.LITERATURE.value == "literature"

    def test_pipeline_stage_has_plotting(self):
        """PipelineStage.PLOTTING exists."""
        from scripts.core.orchestrator import PipelineStage
        assert PipelineStage.PLOTTING.value == "plotting"

    def test_pipeline_stage_has_writing(self):
        """PipelineStage.WRITING exists."""
        from scripts.core.orchestrator import PipelineStage
        assert PipelineStage.WRITING.value == "writing"

    def test_pipeline_stage_has_refinement(self):
        """PipelineStage.REFINEMENT exists."""
        from scripts.core.orchestrator import PipelineStage
        assert PipelineStage.REFINEMENT.value == "refinement"

    def test_pipeline_stage_values_are_strings(self):
        """All stage values are lowercase strings."""
        from scripts.core.orchestrator import PipelineStage
        for stage in PipelineStage:
            assert isinstance(stage.value, str)
            assert stage.value == stage.value.lower()

    def test_pipeline_stage_count(self):
        """Expected number of pipeline stages are defined."""
        from scripts.core.orchestrator import PipelineStage
        stages = list(PipelineStage)
        # Should have at least the core 5 stages
        assert len(stages) >= 5


class TestPipelineStep:
    """Test PipelineStep dataclass."""

    def test_pipeline_step_creation(self):
        """PipelineStep can be created with required fields."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline_agent")
        assert step.stage == PipelineStage.OUTLINE
        assert step.agent_name == "outline_agent"
        assert step.depends_on == []
        assert step.hitl_gate is False
        assert step.skip is False

    def test_pipeline_step_with_hitl_gate(self):
        """PipelineStep supports hitl_gate flag."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(stage=PipelineStage.WRITING, agent_name="writing", hitl_gate=True)
        assert step.hitl_gate is True

    def test_pipeline_step_with_depends_on(self):
        """PipelineStep supports depends_on list."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(
            stage=PipelineStage.WRITING,
            agent_name="writing",
            depends_on=[PipelineStage.OUTLINE, PipelineStage.LITERATURE],
        )
        assert len(step.depends_on) == 2

    def test_pipeline_step_should_run_default(self):
        """should_run returns True by default."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline")
        assert step.should_run({}) is True

    def test_pipeline_step_should_run_when_skipped(self):
        """should_run returns False when skip=True."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline", skip=True)
        assert step.should_run({}) is False

    def test_pipeline_step_should_run_with_condition(self):
        """should_run evaluates condition callback."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(
            stage=PipelineStage.WRITING,
            agent_name="writing",
            condition=lambda ctx: ctx.get("approved", False),
        )
        assert step.should_run({"approved": True}) is True
        assert step.should_run({"approved": False}) is False


class TestPipelineResult:
    """Test PipelineResult dataclass."""

    def test_pipeline_result_creation(self):
        """PipelineResult can be created."""
        from scripts.core.orchestrator import PipelineResult

        result = PipelineResult(
            pipeline_name="test_pipeline",
            success=True,
            stage_results={},
            final_context={"key": "value"},
            total_latency_ms=1234.5,
        )
        assert result.pipeline_name == "test_pipeline"
        assert result.success is True
        assert result.stage_results == {}
        assert result.final_context == {"key": "value"}
        assert result.total_latency_ms == 1234.5
        assert result.hitl_paused_at is None

    def test_pipeline_result_with_hitl_pause(self):
        """PipelineResult tracks HITL pause stage."""
        from scripts.core.orchestrator import PipelineResult, PipelineStage
        result = PipelineResult(
            pipeline_name="test",
            success=False,
            stage_results={},
            final_context={},
            total_latency_ms=100,
            hitl_paused_at=PipelineStage.WRITING,
        )
        assert result.hitl_paused_at == PipelineStage.WRITING

    def test_pipeline_result_has_trace(self):
        """PipelineResult includes execution trace."""
        from scripts.core.orchestrator import PipelineResult
        result = PipelineResult(
            pipeline_name="test",
            success=True,
            stage_results={},
            final_context={},
            total_latency_ms=100,
            trace=[{"type": "step_start", "stage": "outline"}],
        )
        assert len(result.trace) == 1
        assert result.trace[0]["type"] == "step_start"

    def test_pipeline_result_has_timestamp(self):
        """PipelineResult includes timestamp."""
        from scripts.core.orchestrator import PipelineResult
        result = PipelineResult(
            pipeline_name="test",
            success=True,
            stage_results={},
            final_context={},
            total_latency_ms=100,
        )
        assert result.timestamp > 0


class TestAgentOrchestratorInit:
    """Test AgentOrchestrator initialization."""

    def test_requires_gateway_argument(self):
        """AgentOrchestrator requires a gateway argument."""
        from scripts.core.orchestrator import AgentOrchestrator
        # Passing None as gateway should still create the object
        # (actual gateway usage happens at runtime)
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert orch is not None

    def test_initializes_with_empty_agents(self):
        """Orchestrator starts with empty agent registry."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert orch._agents == {}
            assert orch.list_agents() == []

    def test_initializes_message_bus(self):
        """Orchestrator initializes message bus as empty list."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert isinstance(orch._message_bus, list)
            assert len(orch._message_bus) == 0

    def test_initializes_trace(self):
        """Orchestrator initializes execution trace."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert isinstance(orch._trace, list)
            assert len(orch._trace) == 0

    def test_initializes_hitl_gate(self):
        """Orchestrator initializes HITL gate."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert hasattr(orch, "_hitl_gate")

    def test_initializes_active_tokens(self):
        """Orchestrator initializes cancellation token registry."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert isinstance(orch._active_tokens, dict)

    def test_initializes_rejection_feedback(self):
        """Orchestrator initializes rejection feedback dict."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert isinstance(orch._rejection_feedback, dict)


class TestAgentRegistry:
    """Test agent registration and management."""

    def test_register_adds_agent(self):
        """register() adds agent to registry."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agents.base import AgentConfig, BaseAgent

        mock_agent = MagicMock(spec=BaseAgent)
        mock_agent.config = AgentConfig(name="test_agent", role="tester", goal="test", backstory="A test agent")
        mock_gateway = MagicMock()
        mock_gateway.register_agent = MagicMock()

        with patch("scripts.core.orchestrator.LLMGateway", return_value=mock_gateway):
            orch = AgentOrchestrator(gateway=mock_gateway)
            orch.register(mock_agent)
            assert "test_agent" in orch._agents

    def test_unregister_removes_agent(self):
        """unregister() removes agent from registry."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agents.base import AgentConfig, BaseAgent

        mock_agent = MagicMock(spec=BaseAgent)
        mock_agent.config = AgentConfig(name="temp_agent", role="tester", goal="test", backstory="A test agent")
        mock_gateway = MagicMock()
        mock_gateway.register_agent = MagicMock()

        with patch("scripts.core.orchestrator.LLMGateway", return_value=mock_gateway):
            orch = AgentOrchestrator(gateway=mock_gateway)
            orch.register(mock_agent)
            assert "temp_agent" in orch._agents
            orch.unregister("temp_agent")
            assert "temp_agent" not in orch._agents

    def test_get_agent_returns_registered_agent(self):
        """get_agent() retrieves registered agent."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agents.base import AgentConfig, BaseAgent

        mock_agent = MagicMock(spec=BaseAgent)
        mock_agent.config = AgentConfig(name="found_agent", role="tester", goal="test", backstory="A test agent")
        mock_gateway = MagicMock()
        mock_gateway.register_agent = MagicMock()

        with patch("scripts.core.orchestrator.LLMGateway", return_value=mock_gateway):
            orch = AgentOrchestrator(gateway=mock_gateway)
            orch.register(mock_agent)
            retrieved = orch.get_agent("found_agent")
            assert retrieved is not None

    def test_get_agent_returns_none_for_missing(self):
        """get_agent() returns None for unregistered name."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert orch.get_agent("nonexistent") is None

    def test_list_agents_returns_names(self):
        """list_agents() returns all registered agent names."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agents.base import AgentConfig, BaseAgent

        mock_gateway = MagicMock()
        mock_gateway.register_agent = MagicMock()

        with patch("scripts.core.orchestrator.LLMGateway", return_value=mock_gateway):
            orch = AgentOrchestrator(gateway=mock_gateway)
            agents = [
                MagicMock(spec=BaseAgent, config=AgentConfig(name=n, role="t", goal="g", backstory="agent"))
                for n in ["agent_a", "agent_b", "agent_c"]
            ]
            for a in agents:
                orch.register(a)
            names = orch.list_agents()
            assert len(names) == 3
            assert "agent_a" in names
            assert "agent_b" in names
            assert "agent_c" in names


class TestMessageBus:
    """Test message bus functionality."""

    def test_broadcast_adds_message(self):
        """broadcast() adds message to message bus."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "test_message", "data": 123})
            assert len(orch._message_bus) == 1
            assert orch._message_bus[0]["type"] == "test_message"

    def test_broadcast_adds_timestamp(self):
        """broadcast() adds _bus_timestamp to message."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "test"})
            assert "_bus_timestamp" in orch._message_bus[0]

    def test_get_messages_returns_all(self):
        """get_messages() with no filter returns all messages."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "msg1"})
            orch.broadcast({"type": "msg2"})
            messages = orch.get_messages()
            assert len(messages) == 2

    def test_get_messages_filters_by_recipient(self):
        """get_messages(agent_name) filters by recipient."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "msg1", "recipient": "agent_a"})
            orch.broadcast({"type": "msg2", "recipient": "agent_b"})
            orch.broadcast({"type": "msg3", "recipient": "*"})
            msgs = orch.get_messages("agent_a")
            assert len(msgs) == 2  # agent_a's + broadcast to *

    def test_clear_bus_removes_all(self):
        """clear_bus() removes all messages."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "msg"})
            orch.broadcast({"type": "msg2"})
            assert len(orch._message_bus) == 2
            orch.clear_bus()
            assert len(orch._message_bus) == 0

    def test_get_bus_stats_returns_dict(self):
        """get_bus_stats() returns statistics dict."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "test_message"})
            stats = orch.get_bus_stats()
            assert isinstance(stats, dict)
            assert "total_messages" in stats
            assert stats["total_messages"] >= 1

    def test_get_snapshot_returns_newest_first(self):
        """get_snapshot() returns newest messages first."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"order": 1})
            orch.broadcast({"order": 2})
            orch.broadcast({"order": 3})
            snapshot = orch.get_snapshot(limit=2)
            assert len(snapshot) == 2
            assert snapshot[0]["order"] == 3  # newest first
            assert snapshot[1]["order"] == 2

    def test_export_to_json_writes_file(self, tmp_path):
        """export_to_json() writes bus to JSON file."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch.broadcast({"type": "test"})
            out_path = tmp_path / "bus.json"
            orch.export_to_json(str(out_path))
            assert out_path.exists()


class TestCancellation:
    """Test cancellation token support."""

    def test_cancel_agent_returns_true_when_active(self):
        """cancel_agent() returns True for active agent."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agents.base import CancellationToken

        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            token = CancellationToken()
            orch._active_tokens["running_agent"] = token
            result = orch.cancel_agent("running_agent")
            assert result is True

    def test_cancel_agent_returns_false_when_not_active(self):
        """cancel_agent() returns False for unknown agent."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            result = orch.cancel_agent("ghost_agent")
            assert result is False

    def test_is_agent_active_true(self):
        """is_agent_active() returns True for running agent."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.agents.base import CancellationToken
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch._active_tokens["busy_agent"] = CancellationToken()
            assert orch.is_agent_active("busy_agent") is True

    def test_is_agent_active_false(self):
        """is_agent_active() returns False for idle agent."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert orch.is_agent_active("idle_agent") is False


class TestHITLIntegration:
    """Test HITL gate integration in orchestrator."""

    def test_has_hitl_gate_attribute(self):
        """Orchestrator has _hitl_gate attribute."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            assert hasattr(orch, "_hitl_gate")

    def test_set_hitl_gate_replaces_gate(self):
        """set_hitl_gate() replaces internal gate."""
        from scripts.core.orchestrator import AgentOrchestrator
        from scripts.core.hitl_gate import HITLGate
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            original_gate = orch._hitl_gate
            new_gate = HITLGate(db_path=":memory:")
            orch.set_hitl_gate(new_gate)
            assert orch._hitl_gate is new_gate
            assert orch._hitl_gate is not original_gate


class TestEvolutionEngine:
    """Test self-evolution engine integration."""

    def test_set_evolution_engine_attaches_engine(self):
        """set_evolution_engine() attaches evolution engine."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            mock_engine = MagicMock()
            mock_engine.register_agent = MagicMock()
            orch.set_evolution_engine(mock_engine)
            assert orch._evolution_engine is mock_engine


class TestTracing:
    """Test execution trace functionality."""

    def test_get_trace_returns_list(self):
        """get_trace() returns trace list."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            trace = orch.get_trace()
            assert isinstance(trace, list)

    def test_clear_trace_clears_list(self):
        """clear_trace() clears the trace."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch._trace.append({"type": "test"})
            orch.clear_trace()
            assert len(orch._trace) == 0

    def test_save_trace_writes_json(self, tmp_path):
        """save_trace() writes trace to JSON file."""
        from scripts.core.orchestrator import AgentOrchestrator
        with patch("scripts.core.orchestrator.LLMGateway"):
            orch = AgentOrchestrator(gateway=None)
            orch._trace.append({"type": "agent_start", "stage": "outline"})
            out_path = tmp_path / "trace.json"
            orch.save_trace(str(out_path))
            assert out_path.exists()


class TestRepr:
    """Test __repr__ method."""

    def test_repr_shows_agent_count(self):
        """__repr__ includes agent count."""
        from scripts.core.orchestrator import AgentOrchestrator

        mock_gateway = MagicMock()
        mock_gateway.register_agent = MagicMock()

        with patch("scripts.core.orchestrator.LLMGateway", return_value=mock_gateway):
            orch = AgentOrchestrator(gateway=mock_gateway)
            r = repr(orch)
            assert "AgentOrchestrator" in r
            assert "agents=" in r


class TestPipelineSteps:
    """Test pipeline step definitions."""

    def test_pipeline_step_default_skip(self):
        """PipelineStep.skip defaults to False."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline")
        assert step.skip is False

    def test_pipeline_step_default_hitl_gate(self):
        """PipelineStep.hitl_gate defaults to False."""
        from scripts.core.orchestrator import PipelineStep, PipelineStage
        step = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline")
        assert step.hitl_gate is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
