"""Comprehensive tests for scripts/core/agent_state.py.

Covers AgentStateManager, CostTracker, ErrorClassifier, HITLManager, and related
function-level helpers.  No external services or API calls.

Test conventions:
  - Reset singletons before each test to ensure isolation.
  - Synthetic data only — no network calls.
  - Every test completes in under 1 second.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest

# Import from agent_state — add project root to path so tests run from repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.agent_state import (
    AgentState,
    AgentStateManager,
    AgentStatus,
    CostRecord,
    ErrorClassifier,
    ErrorType,
    Event,
    EventBus,
    EventType,
    HITLManager,
    HITLRequest,
    CostTracker,
    agent_state_manager,
    cost_tracker,
    get_fleet_status,
    get_total_cost,
    hitl_manager,
    record_api_call,
    _get_shared_eventbus,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons before every test for full isolation."""
    # AgentStateManager
    AgentStateManager._instance = None
    # CostTracker
    CostTracker._instance = None
    # HITLManager
    HITLManager._instance = None
    # EventBus — shared singleton
    # The shared bus is referenced via module-level variables; we reset
    # _shared_eventbus by re-importing the module-level objects.
    # Reset the module-level shared bus so each test starts clean.
    import scripts.core.agent_state as _mod

    _mod._shared_eventbus = None
    # Make sure all three singletons re-create their EventBus reference
    yield
    # Teardown: stop the bus so background threads don't leak between tests.
    if _mod._shared_eventbus is not None:
        _mod._shared_eventbus.stop()


@pytest.fixture
def fresh_manager() -> AgentStateManager:
    """Return a freshly-initialised AgentStateManager."""
    AgentStateManager._instance = None
    import scripts.core.agent_state as _mod

    _mod._shared_eventbus = None
    return AgentStateManager()


@pytest.fixture
def fresh_cost_tracker() -> CostTracker:
    """Return a freshly-initialised CostTracker."""
    CostTracker._instance = None
    import scripts.core.agent_state as _mod

    _mod._shared_eventbus = None
    return CostTracker()


@pytest.fixture
def fresh_hitl() -> HITLManager:
    """Return a freshly-initialised HITLManager."""
    HITLManager._instance = None
    import scripts.core.agent_state as _mod

    _mod._shared_eventbus = None
    return HITLManager()


# ═══════════════════════════════════════════════════════════════════════════
# AgentStateManager — register_agent / get_agent
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentStateManagerBasics:
    def test_register_agent_returns_state(self, fresh_manager):
        state = fresh_manager.register_agent("agent_a", "Agent Alpha")
        assert isinstance(state, AgentState)
        assert state.agent_id == "agent_a"
        assert state.name == "Agent Alpha"
        assert state.status == AgentStatus.IDLE
        assert state.metadata == {}

    def test_register_agent_with_metadata(self, fresh_manager):
        meta = {"role": "researcher", "priority": 3}
        state = fresh_manager.register_agent("agent_b", "Agent Beta", metadata=meta)
        assert state.metadata == meta

    def test_get_agent_returns_state(self, fresh_manager):
        fresh_manager.register_agent("agent_c", "Agent Gamma")
        state = fresh_manager.get_agent("agent_c")
        assert state is not None
        assert state.name == "Agent Gamma"

    def test_get_nonexistent_returns_none(self, fresh_manager):
        assert fresh_manager.get_agent("does_not_exist") is None

    def test_get_all_agents(self, fresh_manager):
        fresh_manager.register_agent("a1", "One")
        fresh_manager.register_agent("a2", "Two")
        agents = fresh_manager.get_all_agents()
        assert len(agents) == 2
        ids = {s.agent_id for s in agents}
        assert ids == {"a1", "a2"}

    def test_idempotent_initialisation(self, fresh_manager):
        """Second __init__ call must not reset state."""
        fresh_manager.register_agent("idempotent", "Test")
        m2 = AgentStateManager()
        assert m2 is fresh_manager
        assert m2.get_agent("idempotent") is not None


# ═══════════════════════════════════════════════════════════════════════════
# AgentStateManager — start / end / retry / wait
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentStateManagerLifecycle:
    def test_start_agent_transitions_to_running(self, fresh_manager):
        fresh_manager.register_agent("run1", "Runner")
        ok = fresh_manager.start_agent("run1", task="step_one")
        assert ok is True
        state = fresh_manager.get_agent("run1")
        assert state.status == AgentStatus.RUNNING
        assert state.current_task == "step_one"
        assert state.start_time is not None
        assert state.end_time is None

    def test_start_nonexistent_returns_false(self, fresh_manager):
        assert fresh_manager.start_agent("ghost") is False

    def test_end_agent_success(self, fresh_manager):
        fresh_manager.register_agent("end1", "Ender")
        fresh_manager.start_agent("end1")
        ok = fresh_manager.end_agent("end1", success=True)
        assert ok is True
        state = fresh_manager.get_agent("end1")
        assert state.status == AgentStatus.SUCCEEDED
        assert state.end_time is not None

    def test_end_agent_failure_records_error(self, fresh_manager):
        fresh_manager.register_agent("end2", "Failer")
        fresh_manager.start_agent("end2")
        ok = fresh_manager.end_agent("end2", success=False, error="timeout")
        assert ok is True
        state = fresh_manager.get_agent("end2")
        assert state.status == AgentStatus.FAILED
        assert state.last_error == "timeout"
        assert state.error_count == 1

    def test_end_agent_calculates_duration_ms(self, fresh_manager):
        fresh_manager.register_agent("dur", "Dur")
        fresh_manager.start_agent("dur")
        time.sleep(0.05)
        ok = fresh_manager.end_agent("dur")
        assert ok is True
        state = fresh_manager.get_agent("dur")
        # duration_ms is stored in the event; verify end_time - start_time > 0
        assert state.end_time is not None
        assert state.start_time is not None
        assert (state.end_time - state.start_time) > 0

    def test_end_nonexistent_returns_false(self, fresh_manager):
        assert fresh_manager.end_agent("phantom") is False

    def test_set_waiting_transitions_to_waiting(self, fresh_manager):
        fresh_manager.register_agent("wait1", "Waiter")
        fresh_manager.start_agent("wait1")
        ok = fresh_manager.set_waiting("wait1", reason="needs_approval")
        assert ok is True
        state = fresh_manager.get_agent("wait1")
        assert state.status == AgentStatus.WAITING

    def test_set_waiting_nonexistent_returns_false(self, fresh_manager):
        assert fresh_manager.set_waiting("ghost") is False

    def test_retry_agent_transitions_to_retrying(self, fresh_manager):
        fresh_manager.register_agent("retry1", "Retryer")
        fresh_manager.start_agent("retry1")
        fresh_manager.end_agent("retry1", success=False, error="boom")
        ok = fresh_manager.retry_agent("retry1")
        assert ok is True
        state = fresh_manager.get_agent("retry1")
        assert state.status == AgentStatus.RETRYING

    def test_retry_nonexistent_returns_false(self, fresh_manager):
        assert fresh_manager.retry_agent("no_such_agent") is False


# ═══════════════════════════════════════════════════════════════════════════
# AgentStateManager — history & fleet status
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentStateManagerHistory:
    def test_history_empty_initially(self, fresh_manager):
        assert fresh_manager.get_history() == []

    def test_history_records_agent_start(self, fresh_manager):
        fresh_manager.register_agent("hist1", "Historian")
        fresh_manager.start_agent("hist1")
        history = fresh_manager.get_history()
        assert len(history) >= 1
        assert any(e.event_type == EventType.AGENT_START for e in history)

    def test_history_respects_limit(self, fresh_manager):
        # register_agent emits STATE_CHANGE; start emits AGENT_START + appends to history
        fresh_manager.register_agent("lim1", "Lim")
        fresh_manager.start_agent("lim1")
        # end emits AGENT_END and appends to history
        fresh_manager.end_agent("lim1")
        history = fresh_manager.get_history(limit=1)
        assert len(history) == 1

    def test_history_order_is_chronological(self, fresh_manager):
        fresh_manager.register_agent("ord", "Order")
        fresh_manager.start_agent("ord")
        fresh_manager.end_agent("ord")
        history = fresh_manager.get_history()
        timestamps = [e.timestamp for e in history]
        assert timestamps == sorted(timestamps)


class TestFleetStatus:
    def test_fleet_status_empty(self, fresh_manager):
        status = fresh_manager.get_fleet_status()
        assert status["total_agents"] == 0
        assert status["running_count"] == 0
        assert status["failed_count"] == 0
        assert status["idle_count"] == 0
        assert status["waiting_count"] == 0

    def test_fleet_status_counts_running(self, fresh_manager):
        fresh_manager.register_agent("f1", "Fleet1")
        fresh_manager.start_agent("f1")
        status = fresh_manager.get_fleet_status()
        assert status["total_agents"] == 1
        assert status["running_count"] == 1

    def test_fleet_status_counts_failed(self, fresh_manager):
        fresh_manager.register_agent("f2", "Fleet2")
        fresh_manager.start_agent("f2")
        fresh_manager.end_agent("f2", success=False)
        status = fresh_manager.get_fleet_status()
        assert status["failed_count"] == 1

    def test_fleet_status_mixed(self, fresh_manager):
        fresh_manager.register_agent("f3", "Fleet3")
        fresh_manager.start_agent("f3")  # running
        fresh_manager.register_agent("f4", "Fleet4")  # idle
        fresh_manager.register_agent("f5", "Fleet5")
        fresh_manager.start_agent("f5")
        fresh_manager.end_agent("f5", success=True)  # succeeded
        status = fresh_manager.get_fleet_status()
        assert status["total_agents"] == 3
        assert status["running_count"] == 1
        assert status["idle_count"] == 1
        assert status["status_breakdown"]["succeeded"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Module-level convenience functions
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleLevelHelpers:
    def test_get_fleet_status_delegates(self):
        # Override the module-level reference to a fresh manager with 1 agent.
        import scripts.core.agent_state as _mod

        mgr = AgentStateManager()
        mgr.register_agent("a1", "researcher", metadata={})
        _mod.agent_state_manager = mgr
        status = get_fleet_status()
        assert status["total_agents"] == 1

    def test_get_total_cost_default_zero(self):
        import scripts.core.agent_state as _mod

        ct = CostTracker()
        _mod.cost_tracker = ct
        assert get_total_cost()["total_cost_usd"] == 0.0

    def test_record_api_call_shortcut(self, fresh_cost_tracker):
        import scripts.core.agent_state as _mod

        _mod.cost_tracker = fresh_cost_tracker
        record = record_api_call("call1", 1000, 500, "deepseek-chat")
        assert record.agent_id == "call1"
        assert record.input_tokens == 1000
        assert record.output_tokens == 500


# ═══════════════════════════════════════════════════════════════════════════
# CostTracker
# ═══════════════════════════════════════════════════════════════════════════


class TestCostTracker:
    def test_record_single_call(self, fresh_cost_tracker):
        record = fresh_cost_tracker.record("c1", 1_000_000, 500_000, "deepseek-chat")
        assert record.cost_usd > 0
        assert record.model == "deepseek-chat"

    def test_record_multiple_calls_accumulate(self, fresh_cost_tracker):
        fresh_cost_tracker.record("c2", 1_000_000, 0, "deepseek-chat")
        fresh_cost_tracker.record("c2", 2_000_000, 0, "deepseek-chat")
        stats = fresh_cost_tracker.get_agent_cost("c2")
        assert stats["total_input_tokens"] == 3_000_000
        assert stats["call_count"] == 2

    def test_get_total_cost(self, fresh_cost_tracker):
        fresh_cost_tracker.record("c3", 1_000_000, 0, "deepseek-chat")
        fresh_cost_tracker.record("c4", 2_000_000, 0, "deepseek-chat")
        total = fresh_cost_tracker.get_total_cost()
        assert total["total_calls"] == 2
        assert total["total_cost_usd"] > 0
        assert total["cost_per_call"] > 0

    def test_get_cost_by_agent(self, fresh_cost_tracker):
        fresh_cost_tracker.record("c5", 100, 50, "deepseek-chat")
        fresh_cost_tracker.record("c6", 200, 100, "deepseek-chat")
        by_agent = fresh_cost_tracker.get_cost_by_agent()
        assert "c5" in by_agent
        assert "c6" in by_agent
        assert by_agent["c5"]["call_count"] == 1
        assert by_agent["c6"]["call_count"] == 1

    def test_get_cost_timeline_filters_by_hours(self, fresh_cost_tracker):
        fresh_cost_tracker.record("tl1", 100, 50, "deepseek-chat")
        timeline = fresh_cost_tracker.get_cost_timeline(hours=1)
        assert len(timeline) == 1
        assert timeline[0]["agent_id"] == "tl1"

    def test_get_recent_records(self, fresh_cost_tracker):
        for i in range(10):
            fresh_cost_tracker.record(f"r{i}", 100, 50, "deepseek-chat")
        recent = fresh_cost_tracker.get_recent_records(limit=5)
        assert len(recent) == 5

    def test_unknown_model_uses_fallback_pricing(self, fresh_cost_tracker):
        record = fresh_cost_tracker.record("unk", 1_000_000, 1_000_000, "unknown-model-xyz")
        # Should use fallback: input=1.0, output=2.0 per 1M tokens
        expected = (1.0 * 1.0) + (2.0 * 1.0)  # $3.0 per 1M tokens
        assert abs(record.cost_usd - expected) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
# ErrorClassifier
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorClassifier:
    @pytest.mark.parametrize(
        "msg,expected",
        [
            ("api error occurred", ErrorType.API_ERROR),
            ("internal server error", ErrorType.API_ERROR),
            ("connection timeout", ErrorType.TIMEOUT),
            ("request timed out", ErrorType.TIMEOUT),
            ("rate limit exceeded", ErrorType.RATE_LIMIT),
            ("too many requests", ErrorType.RATE_LIMIT),
            ("401 unauthorized", ErrorType.AUTH_ERROR),
            ("invalid api key", ErrorType.AUTH_ERROR),
            ("json decode error", ErrorType.PARSE_ERROR),
            ("unexpected token", ErrorType.PARSE_ERROR),
            ("validation failed", ErrorType.VALIDATION_ERROR),
            ("missing required field", ErrorType.VALIDATION_ERROR),
            ("something went wrong", ErrorType.UNKNOWN),
            ("", ErrorType.UNKNOWN),
        ],
    )
    def test_classify_returns_expected_type(self, msg, expected):
        assert ErrorClassifier.classify(msg) == expected

    @pytest.mark.parametrize(
        "error_type,max_retries",
        [
            (ErrorType.API_ERROR, 3),
            (ErrorType.TIMEOUT, 2),
            (ErrorType.RATE_LIMIT, 5),
            (ErrorType.AUTH_ERROR, 0),
            (ErrorType.PARSE_ERROR, 1),
            (ErrorType.VALIDATION_ERROR, 0),
            (ErrorType.UNKNOWN, 2),
        ],
    )
    def test_retry_strategy_max_retries(self, error_type, max_retries):
        strategy = ErrorClassifier.get_retry_strategy(error_type)
        assert strategy["max_retries"] == max_retries

    def test_retry_strategy_backoff_for_rate_limit(self):
        strategy = ErrorClassifier.get_retry_strategy(ErrorType.RATE_LIMIT)
        assert strategy["backoff"] == "exponential"
        assert strategy["wait"] == 60


# ═══════════════════════════════════════════════════════════════════════════
# HITLManager
# ═══════════════════════════════════════════════════════════════════════════


class TestHITLManager:
    def test_create_request(self, fresh_hitl):
        req = fresh_hitl.create_request(
            agent_id="hitl1",
            task_id="task_x",
            decision_point="approve_output",
            context={"text": "hello"},
        )
        assert req.agent_id == "hitl1"
        assert req.status == "pending"
        assert req.request_id is not None

    def test_approve_request(self, fresh_hitl):
        req = fresh_hitl.create_request("hitl2", "task_y", "decision", {})
        ok = fresh_hitl.approve(req.request_id, comment="looks good")
        assert ok is True
        updated = fresh_hitl.get_request(req.request_id)
        assert updated.status == "approved"
        assert updated.reviewer_comment == "looks good"
        assert updated.reviewed_at is not None

    def test_reject_request(self, fresh_hitl):
        req = fresh_hitl.create_request("hitl3", "task_z", "decision", {})
        ok = fresh_hitl.reject(req.request_id, comment="not ready")
        assert ok is True
        updated = fresh_hitl.get_request(req.request_id)
        assert updated.status == "rejected"

    def test_approve_nonexistent_returns_false(self, fresh_hitl):
        assert fresh_hitl.approve("no-such-id") is False

    def test_reject_nonexistent_returns_false(self, fresh_hitl):
        assert fresh_hitl.reject("no-such-id") is False

    def test_get_pending(self, fresh_hitl):
        r1 = fresh_hitl.create_request("h1", "t1", "d1", {})
        r2 = fresh_hitl.create_request("h2", "t2", "d2", {})
        fresh_hitl.approve(r1.request_id)
        pending = fresh_hitl.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id == r2.request_id

    def test_get_pending_with_elapsed(self, fresh_hitl):
        req = fresh_hitl.create_request("h3", "t3", "d3", {})
        elapsed_list = fresh_hitl.get_pending_with_elapsed()
        assert len(elapsed_list) == 1
        assert "elapsed_seconds" in elapsed_list[0]
        assert "timeout_warning" in elapsed_list[0]

    def test_get_all_requests(self, fresh_hitl):
        fresh_hitl.create_request("h4", "t4", "d4", {})
        fresh_hitl.create_request("h5", "t5", "d5", {})
        all_req = fresh_hitl.get_all()
        assert len(all_req) == 2

    def test_check_timeouts_auto_rejects(self, fresh_hitl):
        req = fresh_hitl.create_request("h6", "t6", "d6", {})
        expired = fresh_hitl.check_timeouts(timeout_seconds=0.0)
        assert len(expired) == 1
        assert expired[0].request_id == req.request_id
        updated = fresh_hitl.get_request(req.request_id)
        assert updated.status == "rejected"

    def test_check_timeouts_no_expired(self, fresh_hitl):
        fresh_hitl.create_request("h7", "t7", "d7", {})
        expired = fresh_hitl.check_timeouts(timeout_seconds=3600)
        assert len(expired) == 0

    def test_check_timeouts_none_timeout_returns_empty(self, fresh_hitl):
        fresh_hitl.default_timeout_seconds = None
        expired = fresh_hitl.check_timeouts()
        assert expired == []

    def test_restore_from_checkpoint_empty(self, fresh_hitl):
        restored = fresh_hitl.restore_from_checkpoint(None)
        assert restored == 0
        restored = fresh_hitl.restore_from_checkpoint({})
        assert restored == 0
        restored = fresh_hitl.restore_from_checkpoint({"pending_requests": []})
        assert restored == 0

    def test_restore_from_checkpoint_restores_pending(self, fresh_hitl):
        checkpoint = {
            "pending_requests": [
                {
                    "request_id": "old-1",
                    "agent_name": "restored_agent",
                    "task_id": "restored_task",
                    "step_name": "review_step",
                    "created_at": time.time() - 100,
                    "context": {"restored": True},
                }
            ]
        }
        restored = fresh_hitl.restore_from_checkpoint(checkpoint)
        assert restored == 1
        pending = fresh_hitl.get_pending()
        assert len(pending) == 1

    def test_restore_skips_existing_requests(self, fresh_hitl):
        existing = fresh_hitl.create_request("exist", "et", "ed", {})
        checkpoint = {
            "pending_requests": [
                {
                    "request_id": existing.request_id,
                    "agent_name": "old",
                    "task_id": "old_task",
                    "step_name": "old_step",
                    "created_at": time.time(),
                }
            ]
        }
        restored = fresh_hitl.restore_from_checkpoint(checkpoint)
        assert restored == 0


# ═══════════════════════════════════════════════════════════════════════════
# EventBus — publish / subscribe / subscribe_all
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBusPublishSubscribe:
    def test_publish_without_start_does_not_deliver(self):
        # Reset shared bus
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        bus = EventBus()
        received: list[Event] = []

        def handler(e: Event):
            received.append(e)

        bus.subscribe(EventType.AGENT_START, handler)
        bus.publish(Event(event_id="x", event_type=EventType.AGENT_START, agent_id="a", timestamp=0.0, data={}))
        assert len(received) == 0  # not started
        bus.stop()

    def test_publish_delivers_after_start(self):
        bus = EventBus()
        received: list[Event] = []

        def handler(e: Event):
            received.append(e)

        bus.subscribe(EventType.AGENT_START, handler)
        bus.start()
        try:
            bus.publish(Event(event_id="y", event_type=EventType.AGENT_START, agent_id="b", timestamp=0.0, data={}))
            time.sleep(0.3)
            assert any(e.event_id == "y" for e in received)
        finally:
            bus.stop()

    def test_subscribe_all_receives_all_event_types(self):
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        bus = EventBus()
        received: list[Event] = []

        def handler(e: Event):
            received.append(e)

        bus.subscribe_all(handler)
        bus.start()
        bus.publish(Event(event_id="e1", event_type=EventType.AGENT_START, agent_id="x", timestamp=0.0, data={}))
        bus.publish(Event(event_id="e2", event_type=EventType.AGENT_END, agent_id="x", timestamp=0.0, data={}))
        time.sleep(0.3)
        assert len(received) == 2
        bus.stop()

    def test_unsubscribe_stops_delivery(self):
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        bus = EventBus()
        received: list[Event] = []

        def handler(e: Event):
            received.append(e)

        bus.subscribe(EventType.AGENT_START, handler)
        bus.start()
        bus.publish(Event(event_id="orig", event_type=EventType.AGENT_START, agent_id="x", timestamp=0.0, data={}))
        time.sleep(0.3)
        assert len(received) == 1
        bus.unsubscribe(EventType.AGENT_START, handler)
        bus.publish(Event(event_id="after", event_type=EventType.AGENT_START, agent_id="x", timestamp=0.0, data={}))
        time.sleep(0.3)
        assert len(received) == 1  # no new event
        bus.stop()

    def test_deduplication_all_subscribers_does_not_double_notify(self):
        """A callback registered for both type-specific and subscribe_all
        should only be called once per event."""
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        bus = EventBus()
        call_count = [0]

        def handler(e: Event):
            call_count[0] += 1

        bus.subscribe(EventType.AGENT_START, handler)
        bus.subscribe_all(handler)
        bus.start()
        bus.publish(Event(event_id="dedup", event_type=EventType.AGENT_START, agent_id="x", timestamp=0.0, data={}))
        time.sleep(0.3)
        assert call_count[0] == 1  # deduplicated
        bus.stop()


# ═══════════════════════════════════════════════════════════════════════════
# Session cleanup / reset
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionCleanup:
    def test_reset_manager_clears_agents(self, fresh_manager):
        fresh_manager.register_agent("reset1", "R1")
        AgentStateManager._instance = None
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        new_mgr = AgentStateManager()
        assert new_mgr.get_agent("reset1") is None

    def test_reset_cost_tracker_clears_records(self, fresh_cost_tracker):
        fresh_cost_tracker.record("rc1", 100, 50, "deepseek-chat")
        CostTracker._instance = None
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        new_ct = CostTracker()
        assert new_ct.get_total_cost()["total_calls"] == 0

    def test_reset_hitl_clears_requests(self, fresh_hitl):
        fresh_hitl.create_request("hc1", "ht1", "hd1", {})
        HITLManager._instance = None
        import scripts.core.agent_state as _mod

        _mod._shared_eventbus = None
        new_hitl = HITLManager()
        assert len(new_hitl.get_all()) == 0

    def test_concurrent_register_and_start_is_safe(self, fresh_manager):
        errors = []

        def register_and_start(agent_id: str):
            try:
                fresh_manager.register_agent(agent_id, f"Concurrent {agent_id}")
                fresh_manager.start_agent(agent_id, task=f"task_{agent_id}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_and_start, args=(f"c{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert fresh_manager.get_fleet_status()["total_agents"] == 20
        assert fresh_manager.get_fleet_status()["running_count"] == 20

    def test_concurrent_cost_recording_is_safe(self, fresh_cost_tracker):
        errors = []

        def record_tokens(i: int):
            try:
                fresh_cost_tracker.record(f"ct{i}", 100, 50, "deepseek-chat")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_tokens, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        total = fresh_cost_tracker.get_total_cost()
        assert total["total_calls"] == 50
