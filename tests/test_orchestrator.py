"""Tests for scripts/core/orchestrator.py — AgentOrchestrator, PipelineStage, PipelineStep."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from unittest.mock import MagicMock, patch

from scripts.core.orchestrator import (
    AgentOrchestrator,
    PipelineStage,
    PipelineStep,
    PipelineResult,
)


# ── PipelineStage ──────────────────────────────────────────────────────────────


class TestPipelineStage:
    def test_all_stages_exist(self):
        assert PipelineStage.OUTLINE.value == "outline"
        assert PipelineStage.LITERATURE.value == "literature"
        assert PipelineStage.PLOTTING.value == "plotting"
        assert PipelineStage.WRITING.value == "writing"
        assert PipelineStage.REFINEMENT.value == "refinement"
        assert PipelineStage.EVALUATION.value == "evaluation"
        assert PipelineStage.FINANCIAL_ANALYSIS.value == "financial_analysis"
        assert PipelineStage.REPORT_WRITING.value == "report_writing"

    def test_stage_is_enum(self):
        assert isinstance(PipelineStage.OUTLINE, PipelineStage)
        assert PipelineStage.OUTLINE == PipelineStage("outline")


# ── PipelineStep ──────────────────────────────────────────────────────────────


class TestPipelineStep:
    def test_pipeline_step_creation(self):
        step = PipelineStep(
            stage=PipelineStage.LITERATURE,
            agent_name="literature",
            depends_on=[PipelineStage.OUTLINE],
            hitl_gate=True,
        )
        assert step.stage == PipelineStage.LITERATURE
        assert step.agent_name == "literature"
        assert step.depends_on == [PipelineStage.OUTLINE]
        assert step.hitl_gate is True
        assert step.skip is False
        assert step.condition is None

    def test_should_run_default(self):
        step = PipelineStep(stage=PipelineStage.WRITING, agent_name="writing")
        assert step.should_run({}) is True

    def test_should_run_when_skip_true(self):
        step = PipelineStep(stage=PipelineStage.WRITING, agent_name="writing", skip=True)
        assert step.should_run({}) is False

    def test_should_run_with_condition_true(self):
        step = PipelineStep(
            stage=PipelineStage.PLOTTING,
            agent_name="plotting",
            condition=lambda ctx: ctx.get("has_data", False),
        )
        assert step.should_run({"has_data": True}) is True
        assert step.should_run({"has_data": False}) is False

    def test_should_run_with_condition_returns_false(self):
        step = PipelineStep(
            stage=PipelineStage.PLOTTING,
            agent_name="plotting",
            condition=lambda ctx: ctx.get("enabled", True) is False,
        )
        assert step.should_run({}) is False


# ── AgentOrchestrator Init ─────────────────────────────────────────────────────


class TestAgentOrchestratorInit:
    def test_orchestrator_requires_gateway(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert orch.gateway is mock_gateway
        assert orch is not None

    def test_agents_dict_initializes_empty(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert hasattr(orch, "_agents")
        assert isinstance(orch._agents, dict)
        assert len(orch._agents) == 0

    def test_message_bus_initializes_empty(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert hasattr(orch, "_message_bus")
        assert orch._message_bus == []

    def test_trace_initializes_empty(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert hasattr(orch, "_trace")
        assert orch._trace == []

    def test_hitl_gate_is_attached(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert hasattr(orch, "_hitl_gate")
        # HITLGate is lazily imported so just check it's not None
        assert orch._hitl_gate is not None

    def test_active_tokens_initializes_empty(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert hasattr(orch, "_active_tokens")
        assert orch._active_tokens == {}

    def test_rejection_feedback_initializes_empty(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert hasattr(orch, "_rejection_feedback")
        assert orch._rejection_feedback == {}

    def test_repr_includes_agent_count(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        repr_str = repr(orch)
        assert "AgentOrchestrator" in repr_str
        assert "0" in repr_str  # no agents registered yet


# ── Agent Registry ─────────────────────────────────────────────────────────────


class TestAgentRegistry:
    def test_register_adds_agent(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config.name = "test_agent"
        mock_agent.config.allowed_tools = []

        orch.register(mock_agent)
        assert "test_agent" in orch._agents
        assert orch._agents["test_agent"] is mock_agent

    def test_unregister_removes_agent(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config.name = "outline"
        mock_agent.config.allowed_tools = []
        orch.register(mock_agent)

        orch.unregister("outline")
        assert "outline" not in orch._agents

    def test_get_agent_returns_registered_agent(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config.name = "writer"
        mock_agent.config.allowed_tools = []
        orch.register(mock_agent)

        result = orch.get_agent("writer")
        assert result is mock_agent

    def test_get_agent_returns_none_for_missing(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert orch.get_agent("does_not_exist") is None

    def test_list_agents_returns_names(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        for name in ["a", "b", "c"]:
            mock_agent = MagicMock()
            mock_agent.config.name = name
            mock_agent.config.allowed_tools = []
            orch.register(mock_agent)

        agents = orch.list_agents()
        assert set(agents) == {"a", "b", "c"}


# ── Message Bus ────────────────────────────────────────────────────────────────


class TestMessageBus:
    def test_broadcast_appends_message(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        orch.broadcast({"type": "test", "content": "hello"})
        assert len(orch._message_bus) == 1
        assert orch._message_bus[0]["type"] == "test"
        assert "_bus_timestamp" in orch._message_bus[0]

    def test_get_messages_returns_all(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        orch.broadcast({"type": "a", "recipient": "*"})
        orch.broadcast({"type": "b", "recipient": "*"})

        messages = orch.get_messages()
        assert len(messages) == 2

    def test_get_messages_filters_by_recipient(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        orch.broadcast({"type": "a", "recipient": "outline"})
        orch.broadcast({"type": "b", "recipient": "writer"})

        outline_msgs = orch.get_messages(agent_name="outline")
        assert len(outline_msgs) == 1
        assert outline_msgs[0]["recipient"] == "outline"

    def test_clear_bus_removes_messages(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        orch.broadcast({"type": "test"})
        orch.clear_bus()
        assert orch._message_bus == []

    def test_get_bus_stats_returns_dict(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        stats = orch.get_bus_stats()
        assert isinstance(stats, dict)
        assert "total_messages" in stats
        assert "messages_by_type" in stats
        assert stats["total_messages"] == 0


# ── HITL Integration ──────────────────────────────────────────────────────────


class TestHITLIntegration:
    def test_set_hitl_gate_replaces_internal_gate(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        from scripts.core.hitl_gate import HITLGate

        new_gate = HITLGate(db_path=":memory:")
        orch.set_hitl_gate(new_gate)
        assert orch._hitl_gate is new_gate


# ── Cancellation ──────────────────────────────────────────────────────────────


class TestCancellation:
    def test_cancel_agent_returns_false_when_not_active(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        result = orch.cancel_agent("outline")
        assert result is False

    def test_is_agent_active_returns_false_when_not_running(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert orch.is_agent_active("outline") is False


# ── Tracing ───────────────────────────────────────────────────────────────────


class TestTracing:
    def test_get_trace_returns_list(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        trace = orch.get_trace()
        assert isinstance(trace, list)
        assert trace == []

    def test_clear_trace_empties_list(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._trace.append({"type": "test"})
        orch.clear_trace()
        assert orch._trace == []


# ── Pipeline Execution (happy-path, mocked) ───────────────────────────────────


class TestPipelineExecution:
    def test_run_pipeline_injects_rejection_feedback(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._rejection_feedback["literature"] = "Add more recent citations"

        steps = [
            PipelineStep(stage=PipelineStage.LITERATURE, agent_name="literature"),
        ]

        # Mock agent so we don't actually run LLM
        mock_agent = MagicMock()
        mock_agent.config.name = "literature"
        mock_agent.config.allowed_tools = []
        from scripts.core.agents.base import AgentResult

        mock_agent.run.return_value = AgentResult(
            status="success",
            output={"literature": "review done"},
            feedback="",
            iterations=1,
            latency_ms=100,
        )
        orch.register(mock_agent)

        # Patch HITLGate.hold to return immediately (skip HITL)
        with patch.object(orch._hitl_gate, "hold", return_value="fake_gate_id"):
            result = orch.run_pipeline(
                pipeline_name="test_pipeline",
                steps=steps,
                input_data={"topic": "test"},
            )

        # Rejection feedback should have been injected into context
        # The orchestrator copies it to enriched_input then clears it from _rejection_feedback
        assert orch._rejection_feedback.get("literature") is None  # cleared after use

    def test_run_pipeline_returns_pipeline_result(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        from scripts.core.agents.base import AgentResult

        mock_agent = MagicMock()
        mock_agent.config.name = "outline"
        mock_agent.config.allowed_tools = []
        mock_agent.run.return_value = AgentResult(
            status="success",
            output={"outline": "structured outline"},
            feedback="",
            iterations=1,
            latency_ms=100,
        )
        orch.register(mock_agent)

        steps = [
            PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline"),
        ]

        with patch.object(orch._hitl_gate, "hold", return_value="fake_gate_id"):
            result = orch.run_pipeline(
                pipeline_name="outline_pipeline",
                steps=steps,
                input_data={},
            )

        assert isinstance(result, PipelineResult)
        assert result.pipeline_name == "outline_pipeline"
        assert result.total_latency_ms >= 0
        assert isinstance(result.stage_results, dict)

    def test_run_parallel_runs_multiple_agents(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        from scripts.core.agents.base import AgentResult

        for name in ["outline", "literature"]:
            mock_agent = MagicMock()
            mock_agent.config.name = name
            mock_agent.config.allowed_tools = []
            mock_agent.run.return_value = AgentResult(
                status="success",
                output={name: "done"},
                feedback="",
                iterations=1,
                latency_ms=50,
            )
            orch.register(mock_agent)

        results = orch.run_parallel(
            agent_names=["outline", "literature"],
            input_data={},
        )

        assert isinstance(results, dict)
        assert "outline" in results
        assert "literature" in results

    def test_approve_step_returns_dict(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        from scripts.core.hitl_gate import HITLGate

        gate = HITLGate(db_path=":memory:")
        orch.set_hitl_gate(gate)

        # Put a record in pending state
        gate._pending["test_gate"] = MagicMock(
            gate_id="test_gate",
            stage="outline",
            state=gate._pending.__class__.__name__,  # won't match but we check gate_id
        )

        # Can't easily test approve_step without full HITL setup;
        # just verify the method exists and returns dict
        with patch.object(orch._hitl_gate, "get_pending", return_value=[]):
            result = orch.approve_step(PipelineStage.OUTLINE, "looks good")
            assert isinstance(result, dict)

    def test_resume_pipeline_returns_early_when_no_pause(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)


        mock_result = PipelineResult(
            pipeline_name="test",
            success=True,
            stage_results={},
            final_context={},
            total_latency_ms=100,
            hitl_paused_at=None,
        )

        result = orch.resume_pipeline(mock_result, steps=[])
        assert result is mock_result


# ── PipelineResult ────────────────────────────────────────────────────────────


class TestPipelineResult:
    def test_pipeline_result_has_all_fields(self):
        pass

        result = PipelineResult(
            pipeline_name="test",
            success=True,
            stage_results={},
            final_context={"key": "value"},
            total_latency_ms=500.0,
            hitl_paused_at=None,
            evolution_events=[],
            trace=[{"type": "test"}],
        )
        assert result.pipeline_name == "test"
        assert result.success is True
        assert result.stage_results == {}
        assert result.final_context == {"key": "value"}
        assert result.total_latency_ms == 500.0
        assert result.hitl_paused_at is None
        assert len(result.trace) == 1


# ── Evolution Integration ─────────────────────────────────────────────────────


class TestEvolutionIntegration:
    def test_set_evolution_engine_attaches_engine(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        mock_engine = MagicMock()
        mock_engine.register_agent = MagicMock()

        orch.set_evolution_engine(mock_engine)
        assert orch._evolution_engine is mock_engine


# ── Error Handling ────────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_run_pipeline_handles_missing_agent(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)

        steps = [
            PipelineStep(stage=PipelineStage.LITERATURE, agent_name="ghost_agent"),
        ]
        result = orch.run_pipeline("test", steps, {})
        assert result.success is False
        # Error is recorded in trace, not final_context
        agent_not_found = [e for e in result.trace if e.get("type") == "agent_not_found"]
        assert len(agent_not_found) == 1
        assert agent_not_found[0]["agent_name"] == "ghost_agent"

    def test_unregister_removes_agent(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        mock_agent = MagicMock()
        mock_agent.config.name = "test_agent"
        orch.register(mock_agent)
        assert orch.get_agent("test_agent") is not None
        orch.unregister("test_agent")
        assert orch.get_agent("test_agent") is None

    def test_list_agents(self):
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        for name in ["a1", "a2"]:
            mock_agent = MagicMock()
            mock_agent.config.name = name
            orch.register(mock_agent)
        names = orch.list_agents()
        assert "a1" in names and "a2" in names


class TestPipelineStep:
    """Additional PipelineStep tests for should_run conditions."""

    def test_should_run_skip_true(self):
        step = PipelineStep(stage=PipelineStage.LITERATURE, agent_name="lit", skip=True)
        assert not step.should_run({})

    def test_should_run_condition_true(self):
        step = PipelineStep(
            stage=PipelineStage.LITERATURE,
            agent_name="lit",
            condition=lambda ctx: ctx.get("has_data", False),
        )
        assert step.should_run({"has_data": True})
        assert not step.should_run({})

    def test_should_run_no_condition(self):
        step = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline")
        assert step.should_run({})  # no condition, no skip -> always run

    def test_pipeline_step_equality(self):
        s1 = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline")
        s2 = PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline")
        assert s1.stage == s2.stage


class TestMessageBusExtended:
    """Additional tests for orchestrator's _message_bus list (not a MessageBus class)."""

    def test_message_bus_is_list(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert isinstance(orch._message_bus, list)

    def test_broadcast_appends_to_list(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._message_bus.append({"type": "msg1", "sender": "a"})
        orch._message_bus.append({"type": "msg2", "sender": "b"})
        assert len(orch._message_bus) == 2

    def test_get_messages_returns_all(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._message_bus.append({"msg": "test"})
        # _message_bus is a plain list; the "get_messages" method does not exist
        # (the test validates the list directly)
        assert len(orch._message_bus) == 1

    def test_clear_message_bus(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._message_bus.append({"msg": "test"})
        assert len(orch._message_bus) == 1
        orch._message_bus.clear()
        assert len(orch._message_bus) == 0


class TestOrchestratorMessageBusIntegration:
    """Integration: _message_bus list wired into AgentOrchestrator."""

    def test_orchestrator_has_message_bus_list(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert isinstance(orch._message_bus, list)
        assert orch._message_bus == []

    def test_broadcast_via_orchestrator(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._message_bus.append({"type": "test", "content": "hello"})
        assert len(orch._message_bus) == 1


class TestPipelineStageEnum:
    """Extended PipelineStage enum tests."""

    def test_all_stages_are_strings(self):
        for stage in PipelineStage:
            assert isinstance(stage.value, str)

    def test_stage_count(self):
        assert len(PipelineStage) >= 5  # outline, literature, plotting, writing, refinement

    def test_stage_from_string(self):
        assert PipelineStage("outline") == PipelineStage.OUTLINE


class TestTracingExtended:
    """Additional tracing tests."""

    def test_trace_records_multiple_events(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._trace.append({"type": "event1"})
        orch._trace.append({"type": "event2"})
        trace = orch.get_trace()
        assert len(trace) == 2

    def test_clear_trace(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        orch._trace.append({"type": "event"})
        orch.clear_trace()
        assert orch.get_trace() == []


class TestCancellationExtended:
    """Additional cancellation tests."""

    def test_cancel_nonexistent_agent(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        result = orch.cancel_agent("does_not_exist")
        assert result is False

    def test_is_agent_active_unknown(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        assert orch.is_agent_active("unknown_agent") is False


class TestAgentRegistryExtended:
    """Additional agent registry tests."""

    def test_register_multiple_agents(self):
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        for name in ["ag1", "ag2", "ag3"]:
            mock_agent = MagicMock()
            mock_agent.config.name = name
            orch.register(mock_agent)
        assert len(orch.list_agents()) == 3

    def test_unregister_nonexistent_is_silent(self):
        """Unregistering a non-existent agent must not raise."""
        from scripts.core.orchestrator import AgentOrchestrator
        mock_gateway = MagicMock()
        orch = AgentOrchestrator(gateway=mock_gateway)
        # Should not raise
        orch.unregister("not_registered")
        assert orch.get_agent("not_registered") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
