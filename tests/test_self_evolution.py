"""Tests for scripts/core/self_evolution.py"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.core.self_evolution import (
    EvolutionEvent, SelfEvolutionEngine,
    SelfEvolutionAutoTrigger, SessionEvolutionIntegration,
)


class TestEvolutionEvent:
    def test_evolution_event_creation(self):
        event = EvolutionEvent(
            timestamp=1234567890.0,
            agent_name="test_agent",
            proposal={"target": "prompt", "suggestion": "improve"},
            assessment={"score": 0.8},
            committed=True,
            commit_message="Applied improvement",
        )
        assert event.agent_name == "test_agent"
        assert event.committed is True
        assert event.commit_message == "Applied improvement"

    def test_evolution_event_defaults(self):
        event = EvolutionEvent(
            timestamp=100.0,
            agent_name="agent",
            proposal={},
            assessment={},
            committed=False,
        )
        assert event.commit_message == ""


class TestSelfEvolutionEngine:
    def test_engine_initialization(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        assert engine._is_active is False

    def test_is_active_returns_bool(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        assert isinstance(engine.is_active(), bool)
        assert engine.is_active() is False

    def test_register_agent_single(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config = {"temperature": 0.7}
        engine.register_agent("test_agent", mock_agent)
        assert "test_agent" in engine._agents
        assert engine._agents["test_agent"] is mock_agent

    def test_register_multiple_agents(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        mock_agent1 = MagicMock()
        mock_agent1.config = {"temperature": 0.7}
        mock_agent2 = MagicMock()
        mock_agent2.config = {"temperature": 0.5}

        engine.register_agent("agent1", mock_agent1)
        engine.register_agent("agent2", mock_agent2)

        assert len(engine._agents) == 2

    def test_activate_deactivate(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config = {"temperature": 0.7}
        engine.register_agent("test_agent", mock_agent)

        result = engine.activate()
        assert engine.is_active() is True
        assert result["status"] == "activated"
        assert "test_agent" in engine._golden_config

        result2 = engine.deactivate()
        assert engine.is_active() is False
        assert result2["status"] == "deactivated"

    def test_activate_idempotent(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config = {"temperature": 0.7}
        engine.register_agent("agent", mock_agent)

        engine.activate()
        result = engine.activate()
        assert result["status"] == "already_active"

    def test_deactivate_when_not_active(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        result = engine.deactivate()
        assert result["status"] == "not_active"

    def test_record_and_assess_returns_none_when_inactive(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        # Provide a mock result with a score attribute so _extract_quality works
        mock_result = MagicMock()
        mock_result.score = 0.8  # above baseline

        result = engine.record_and_assess(
            agent_name="test_agent",
            result=mock_result,
            context={},
        )
        # Inactive engine skips the quality check logic path
        # The engine just checks _is_active is False and returns None
        assert result is None

    def test_record_and_assess_triggers_proposal_when_low_quality(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._quality_baseline = 0.8

        mock_agent = MagicMock()
        mock_agent.config = MagicMock()
        mock_agent.config.temperature = 0.7
        mock_agent.config.max_iterations = 3
        mock_agent.config.max_time_seconds = 60
        mock_agent.config.output_format = "json"
        engine.register_agent("test_agent", mock_agent)

        engine.activate()

        # Mock low quality result
        mock_result = MagicMock()
        mock_result.score = 0.5  # below baseline

        with patch.object(engine, "_propose", return_value={"proposals": [{"target": "temperature", "suggestion": "increase"}]}):
            with patch.object(engine, "_assess_lightweight", return_value={"commit": False, "severity": 0.5}):
                result = engine.record_and_assess("test_agent", mock_result, {})

        assert result is not None
        assert "proposal" in result
        assert "assessment" in result

    def test_record_and_assess_skips_when_above_baseline(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._quality_baseline = 0.5

        mock_result = MagicMock()
        mock_result.score = 0.8  # above baseline

        result = engine.record_and_assess("test_agent", mock_result, {})
        assert result is None

    def test_proposals_persistence_save_and_load(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._proposals.append({"proposal": "test", "timestamp": 123.0})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "proposals.jsonl"
            saved_path = engine.save_proposals(path)
            assert saved_path == path
            assert path.exists()

            # Load into new engine
            engine2 = SelfEvolutionEngine(mock_memory, mock_gateway)
            loaded = engine2.load_proposals(path)
            assert loaded == 1
            assert len(engine2._proposals) == 1

    def test_save_proposals_to_default_path(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._agent_name = "test_engine"

        with patch("builtins.open", side_effect=OSError("disk full")):
            with patch("pathlib.Path.mkdir"):
                with pytest.raises(OSError):
                    engine.save_proposals()

    def test_load_proposals_nonexistent_file(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        loaded = engine.load_proposals(Path("/nonexistent/file.jsonl"))
        assert loaded == 0

    def test_evolution_hooks_no_exception(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        r1 = engine.on_feedback_received("test_agent", "Improve clarity")
        r2 = engine.on_checkpoint_restored("test_agent", "cp_001")
        assert r1 is None, "Hook should return None"
        assert r2 is None, "Hook should return None"
        assert len(engine._history) == 0, "Hooks must not mutate history"

    def test_stream_events(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._history.append(EvolutionEvent(
            timestamp=1.0, agent_name="a", proposal={}, assessment={}, committed=False
        ))
        events = list(engine.stream_events())
        assert len(events) == 1
        assert events[0].agent_name == "a"

    def test_get_history_filtered_by_agent(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._history.append(EvolutionEvent(
            timestamp=1.0, agent_name="agent_a", proposal={}, assessment={}, committed=True
        ))
        engine._history.append(EvolutionEvent(
            timestamp=2.0, agent_name="agent_b", proposal={}, assessment={}, committed=False
        ))

        history_a = engine.get_history(agent_name="agent_a")
        assert len(history_a) == 1
        assert history_a[0]["agent_name"] == "agent_a"

        history_b = engine.get_history(agent_name="agent_b")
        assert len(history_b) == 1

        history_all = engine.get_history()
        assert len(history_all) == 2

    def test_get_stats(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        trigger = SelfEvolutionAutoTrigger(engine)
        stats = trigger.get_stats()

        assert "total_agents" in stats
        assert "consecutive_fails" in stats
        assert "history_count" in stats

    def test_commit_requires_approved_assessment(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        result = engine.commit(
            proposal={"agent_name": "test"},
            assessment={"commit": False},  # Not approved
        )
        assert "error" in result

    def test_commit_unregistered_agent(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        result = engine.commit(
            proposal={"agent_name": "nonexistent_agent", "suggestion": "change"},
            assessment={"commit": True},
        )
        assert "error" in result

    def test_rollback_no_golden_config(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        result = engine.rollback("unknown_agent")
        assert "error" in result

    def test_rollback_with_golden_config(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        mock_agent = MagicMock()
        mock_agent.config = MagicMock()
        mock_agent.config.temperature = 0.9
        mock_agent.config.max_iterations = 5
        mock_agent.config.max_time_seconds = 120
        mock_agent.config.output_format = "json"
        engine.register_agent("test_agent", mock_agent)
        engine.activate()

        # Manually set golden config to a proper dict (simulating what _get_agent_config_snapshot returns)
        engine._golden_config["test_agent"] = {
            "temperature": 0.9,
            "max_iterations": 5,
            "output_format": "json",
        }

        # Change the config
        mock_agent.config.temperature = 0.1

        result = engine.rollback("test_agent")
        assert result["rolled_back"] is True
        assert mock_agent.config.temperature == 0.9  # Restored to golden

    def test_propose_improvements(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        mock_gateway.generate.return_value = MagicMock(
            response='{"proposals": [{"agent_name": "test", "target": "temperature", "suggestion": "increase", "issue": "low", "expected_impact": "medium"}], "overall_assessment": "ok", "priority_order": []}'
        )

        result = engine.propose_improvements(context={})
        assert "proposals" in result
        assert len(result["proposals"]) >= 1

    def test_assess_on_tests(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        engine._quality_baseline = 0.5

        mock_agent = MagicMock()
        mock_agent.config = MagicMock()
        mock_agent.config.temperature = 0.7
        mock_agent.config.max_iterations = 3
        mock_agent.config.max_time_seconds = 60
        mock_agent.config.output_format = "json"
        mock_agent.run.return_value = MagicMock(score=0.8)
        engine.register_agent("test_agent", mock_agent)

        result = engine.assess_on_tests(
            proposal={"agent_name": "test_agent", "suggestion": "increase"},
            test_data=[{}, {}],
        )
        assert "quality_delta" in result
        assert "commit" in result


class TestSelfEvolutionAutoTrigger:
    def test_auto_trigger_initialization(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        trigger = SelfEvolutionAutoTrigger(engine)
        assert trigger.engine is engine
        assert trigger.quality_threshold == 0.7
        assert trigger.consecutive_fail_threshold == 3
        assert trigger.auto_rollback_threshold == 5

    def test_on_task_complete_success_resets_counter(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        trigger = SelfEvolutionAutoTrigger(engine, quality_threshold=0.7)

        # Simulate a failure first
        mock_result_fail = MagicMock()
        mock_result_fail.score = 0.5
        trigger.on_task_complete("agent1", mock_result_fail, {})

        # Then success
        mock_result_ok = MagicMock()
        mock_result_ok.score = 0.8
        result = trigger.on_task_complete("agent1", mock_result_ok, {})

        assert result is None  # No evolution event on success

    def test_on_task_complete_no_agent_registered(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        trigger = SelfEvolutionAutoTrigger(engine, quality_threshold=0.7)

        mock_result = MagicMock()
        mock_result.score = 0.5
        result = trigger.on_task_complete("unregistered_agent", mock_result, {})
        assert result is None

    def test_get_stats(self):
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)

        trigger = SelfEvolutionAutoTrigger(engine)
        stats = trigger.get_stats()

        assert "total_agents" in stats
        assert "consecutive_fails" in stats
        assert "history_count" in stats


class TestSessionEvolutionIntegration:
    def test_integration_initializes(self):
        mock_session = MagicMock()
        mock_session.memory = MagicMock()
        mock_engine = MagicMock()

        integration = SessionEvolutionIntegration(mock_session, mock_engine)
        assert integration.session is mock_session
        assert integration.engine is mock_engine

    def test_wrap_execute_task_returns_wrapper(self):
        mock_session = MagicMock()
        mock_session.memory = MagicMock()
        mock_engine = MagicMock()
        mock_engine._extract_quality.return_value = 0.8
        mock_engine.record_and_assess.return_value = None

        integration = SessionEvolutionIntegration(mock_session, mock_engine)

        mock_result = MagicMock()
        mock_result.output = "test"
        mock_result.iterations = 5
        mock_result.score = 0.8

        original_fn = MagicMock(return_value=mock_result)

        wrapped = integration.wrap_execute_task(original_fn)
        assert callable(wrapped)

        result = wrapped(agent_name="test_agent")
        original_fn.assert_called_once()
        assert result is mock_result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
