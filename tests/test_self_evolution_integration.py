"""Integration tests for SelfEvolutionEngine hot-path."""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.core.self_evolution import SelfEvolutionEngine, EvolutionEvent


class TestSelfEvolutionHotPath:
    """Tests covering the most frequently exercised code paths in SelfEvolutionEngine."""

    def _make_engine(self):
        """Create a minimally configured engine with mocked dependencies."""
        mock_memory = MagicMock()
        mock_gateway = MagicMock()
        engine = SelfEvolutionEngine(mock_memory, mock_gateway)
        return engine

    def test_activate_then_record_triggers_proposal(self):
        """activate() should backup golden config and record activation state."""
        engine = self._make_engine()
        mock_agent = MagicMock()
        mock_agent.config = {"temperature": 0.7}
        engine.register_agent("test_agent", mock_agent)

        result = engine.activate()

        assert "test_agent" in engine._golden_config
        assert result["status"] == "activated"
        assert engine.is_active() is True

        engine.deactivate()
        assert engine.is_active() is False

    def test_deactivate_returns_deactivation_summary(self):
        """deactivate() should return a summary dict."""
        engine = self._make_engine()
        engine.activate()
        result = engine.deactivate()
        assert result["status"] == "deactivated"
        assert "events_recorded" in result
        assert "proposals_generated" in result

    def test_proposals_persist_across_sessions(self):
        """save_proposals and load_proposals should work correctly."""
        engine = self._make_engine()
        engine._proposals.append(
            {
                "proposal": "increase temperature",
                "timestamp": 123456.0,
                "source": "llm_analysis",
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "proposals.jsonl"
            saved = engine.save_proposals(path)
            assert saved == path
            assert path.exists()

            engine2 = self._make_engine()
            loaded = engine2.load_proposals(path)
            assert loaded == 1
            assert len(engine2._proposals) == 1
            assert engine2._proposals[0]["proposal"] == "increase temperature"

    def test_evolution_event_serialization(self):
        """EvolutionEvent dataclass fields should be accessible."""
        event = EvolutionEvent(
            timestamp=123456.0,
            agent_name="test_agent",
            proposal={"target": "prompt", "suggestion": "be clearer"},
            assessment={"score": 0.6, "passed": True},
            committed=False,
        )

        assert event.agent_name == "test_agent"
        assert event.committed is False
        assert event.proposal["suggestion"] == "be clearer"
        assert event.assessment["passed"] is True

    def test_stream_events_yields_all_history(self):
        """stream_events generator should yield all evolution events."""
        engine = self._make_engine()
        for i in range(5):
            engine._history.append(
                EvolutionEvent(
                    timestamp=float(i),
                    agent_name="test",
                    proposal={"id": i},
                    assessment={},
                    committed=False,
                )
            )

        events = list(engine.stream_events())
        assert len(events) == 5
        assert events[0].proposal["id"] == 0
        assert events[4].proposal["id"] == 4

    def test_hook_methods_no_errors(self):
        """Hook methods should not raise on valid input."""
        engine = self._make_engine()
        r1 = engine.on_feedback_received("agent1", "Good job, improve efficiency")
        r2 = engine.on_checkpoint_restored("agent1", "cp_abc123")
        assert r1 is None
        assert r2 is None
        assert len(engine._history) == 0

    def test_register_agent_stores_agent(self):
        """register_agent should store the agent in _agents dict."""
        engine = self._make_engine()
        mock_agent = MagicMock()
        mock_agent.config = {"top_p": 0.9}
        engine.register_agent("writer", mock_agent)
        assert "writer" in engine._agents
        assert engine._get_agent("writer") is mock_agent
