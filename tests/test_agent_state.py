"""Tests for scripts/core/agent_state.py — state management, event bus, HITL.

No external services or API calls required.
"""

import threading
import time
import uuid

import pytest

from scripts.core.agent_state import (
    AgentState,
    AgentStateManager,
    AgentStatus,
    CostRecord,
    Event,
    EventBus,
    EventType,
    ErrorType,
    HITLRequest,
)


# ── AgentStatus ────────────────────────────────────────────────────────────────


class TestAgentStatus:
    def test_all_statuses_exist(self):
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.WAITING.value == "waiting"
        assert AgentStatus.SUCCEEDED.value == "succeeded"
        assert AgentStatus.FAILED.value == "failed"
        assert AgentStatus.RETRYING.value == "retrying"

    def test_status_count(self):
        assert len(AgentStatus) == 6


# ── EventType ─────────────────────────────────────────────────────────────────


class TestEventType:
    def test_all_event_types_exist(self):
        assert EventType.AGENT_START.value == "agent_start"
        assert EventType.AGENT_END.value == "agent_end"
        assert EventType.AGENT_ERROR.value == "agent_error"
        assert EventType.AGENT_RETRY.value == "agent_retry"
        assert EventType.TASK_CREATE.value == "task_create"
        assert EventType.TASK_COMPLETE.value == "task_complete"
        assert EventType.HITL_REQUEST.value == "hitl_request"
        assert EventType.HITL_APPROVE.value == "hitl_approve"
        assert EventType.HITL_REJECT.value == "hitl_reject"
        assert EventType.COST_UPDATE.value == "cost_update"
        assert EventType.STATE_CHANGE.value == "state_change"


# ── ErrorType ─────────────────────────────────────────────────────────────────


class TestErrorType:
    def test_all_error_types_exist(self):
        assert ErrorType.API_ERROR.value == "api_error"
        assert ErrorType.TIMEOUT.value == "timeout"
        assert ErrorType.RATE_LIMIT.value == "rate_limit"
        assert ErrorType.AUTH_ERROR.value == "auth_error"
        assert ErrorType.PARSE_ERROR.value == "parse_error"
        assert ErrorType.VALIDATION_ERROR.value == "validation_error"
        assert ErrorType.UNKNOWN.value == "unknown"


# ── AgentState dataclass ───────────────────────────────────────────────────────


class TestAgentState:
    def test_create_with_required_fields(self):
        state = AgentState(
            agent_id="agent_001",
            name="test_agent",
            status=AgentStatus.IDLE,
        )
        assert state.agent_id == "agent_001"
        assert state.name == "test_agent"
        assert state.status == AgentStatus.IDLE
        assert state.current_task is None
        assert state.error_count == 0
        assert state.metadata == {}

    def test_create_with_all_fields(self):
        now = time.time()
        state = AgentState(
            agent_id="agent_002",
            name="full_agent",
            status=AgentStatus.RUNNING,
            current_task="running_task",
            start_time=now,
            end_time=now + 100,
            error_count=2,
            last_error="some error",
            metadata={"key": "value"},
        )
        assert state.current_task == "running_task"
        assert state.start_time == now
        assert state.end_time == now + 100
        assert state.error_count == 2
        assert state.last_error == "some error"
        assert state.metadata == {"key": "value"}


# ── Event dataclass ────────────────────────────────────────────────────────────


class TestEvent:
    def test_create_event(self):
        event = Event(
            event_id="evt_001",
            event_type=EventType.AGENT_START,
            agent_id="agent_001",
            timestamp=time.time(),
            data={"task": "test_task"},
        )
        assert event.event_id == "evt_001"
        assert event.event_type == EventType.AGENT_START
        assert event.agent_id == "agent_001"
        assert event.data == {"task": "test_task"}
        assert event.duration_ms is None

    def test_event_with_duration(self):
        event = Event(
            event_id="evt_002",
            event_type=EventType.AGENT_END,
            agent_id="agent_001",
            timestamp=time.time(),
            data={},
            duration_ms=1500.5,
        )
        assert event.duration_ms == 1500.5


# ── CostRecord dataclass ──────────────────────────────────────────────────────


class TestCostRecord:
    def test_create_cost_record(self):
        record = CostRecord(
            record_id="cost_001",
            agent_id="agent_001",
            timestamp=time.time(),
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
            model="deepseek-chat",
        )
        assert record.input_tokens == 1000
        assert record.output_tokens == 500
        assert record.cost_usd == 0.05
        assert record.task_id is None

    def test_cost_record_with_task(self):
        record = CostRecord(
            record_id="cost_002",
            agent_id="agent_001",
            timestamp=time.time(),
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.10,
            model="gpt-4o",
            task_id="task_001",
        )
        assert record.task_id == "task_001"


# ── HITLRequest dataclass ─────────────────────────────────────────────────────


class TestHITLRequest:
    def test_create_hitl_request(self):
        request = HITLRequest(
            request_id="hitl_001",
            agent_id="agent_001",
            task_id="task_001",
            decision_point="approve_output",
            context={"output": "generated_text"},
            created_at=time.time(),
        )
        assert request.status == "pending"
        assert request.reviewed_at is None
        assert request.reviewer_comment is None

    def test_hitl_request_approved(self):
        now = time.time()
        request = HITLRequest(
            request_id="hitl_002",
            agent_id="agent_001",
            task_id="task_001",
            decision_point="approve_output",
            context={},
            created_at=now,
            status="approved",
            reviewed_at=now + 60,
            reviewer_comment="Looks good",
        )
        assert request.status == "approved"
        assert request.reviewer_comment == "Looks good"


# ── EventBus ──────────────────────────────────────────────────────────────────


class TestEventBus:
    def test_singleton(self):
        bus1 = EventBus()
        bus2 = EventBus()
        assert bus1 is bus2

    def test_subscribe_and_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.AGENT_START, handler)
        # publish without starting the bus — event goes to queue but not processed
        event = Event(
            event_id="evt_test",
            event_type=EventType.AGENT_START,
            agent_id="test",
            timestamp=time.time(),
            data={},
        )
        bus.publish(event)
        assert len(received) == 0  # not started yet

        bus.start()
        time.sleep(0.3)  # let processing thread drain the queue
        assert len(received) == 1
        assert received[0].event_id == "evt_test"
        bus.stop()

        # unsubscribe
        bus.unsubscribe(EventType.AGENT_START, handler)
        event2 = Event(
            event_id="evt_test2",
            event_type=EventType.AGENT_START,
            agent_id="test",
            timestamp=time.time(),
            data={},
        )
        bus.publish(event2)
        time.sleep(0.3)
        assert len(received) == 1  # no new events received


# ── AgentStateManager ─────────────────────────────────────────────────────────


class TestAgentStateManager:
    def test_singleton(self):
        # Use unique session_id to avoid state from other tests
        AgentStateManager._instance = None
        manager1 = AgentStateManager()
        manager2 = AgentStateManager()
        assert manager1 is manager2

    def test_register_and_get_agent(self):
        # Reset singleton for isolation
        AgentStateManager._instance = None
        manager = AgentStateManager()

        manager.register_agent("agent_test_001", "TestAgent")
        state = manager.get_agent("agent_test_001")
        assert state is not None
        assert state.agent_id == "agent_test_001"
        assert state.name == "TestAgent"
        assert state.status == AgentStatus.IDLE

    def test_get_nonexistent_agent(self):
        AgentStateManager._instance = None
        manager = AgentStateManager()
        state = manager.get_agent("nonexistent")
        assert state is None

    def test_start_agent(self):
        AgentStateManager._instance = None
        manager = AgentStateManager()

        manager.register_agent("agent_test_002", "TestAgent2")
        ok = manager.start_agent("agent_test_002", task="task_a")
        assert ok is True
        state = manager.get_agent("agent_test_002")
        assert state.status == AgentStatus.RUNNING
        assert state.current_task == "task_a"
        assert state.start_time is not None

    def test_end_agent_success(self):
        AgentStateManager._instance = None
        manager = AgentStateManager()

        manager.register_agent("agent_test_003", "TestAgent3")
        manager.start_agent("agent_test_003")
        ok = manager.end_agent("agent_test_003", success=True)
        assert ok is True
        state = manager.get_agent("agent_test_003")
        assert state.status == AgentStatus.SUCCEEDED
        assert state.end_time is not None
