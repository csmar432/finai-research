"""Unit tests for scripts/core/agent_state.py.

Covers: enums, dataclasses, module-level helpers, and EventBus basics.
For singleton-heavy classes (AgentStateManager, CostTracker, HITLManager) see
test_agent_state.py which tests them with proper isolation fixtures.

Test conventions:
  - Synthetic data only — no network calls.
  - Every test completes in under 1 second.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.agent_state import (
    AgentStatus,
    EventType,
    ErrorType,
    AgentState,
    Event,
    CostRecord,
    HITLRequest,
)


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentStatusEnum:
    def test_all_status_values_exist(self):
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.WAITING.value == "waiting"
        assert AgentStatus.SUCCEEDED.value == "succeeded"
        assert AgentStatus.FAILED.value == "failed"
        assert AgentStatus.RETRYING.value == "retrying"

    def test_status_count(self):
        assert len(AgentStatus) == 6

    def test_status_from_value(self):
        assert AgentStatus("running") == AgentStatus.RUNNING
        assert AgentStatus("idle") == AgentStatus.IDLE


class TestEventTypeEnum:
    def test_all_event_values_exist(self):
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

    def test_event_type_count(self):
        assert len(EventType) == 11

    def test_event_type_from_value(self):
        assert EventType("agent_start") == EventType.AGENT_START
        assert EventType("hitl_request") == EventType.HITL_REQUEST


class TestErrorTypeEnum:
    def test_all_error_values_exist(self):
        assert ErrorType.API_ERROR.value == "api_error"
        assert ErrorType.TIMEOUT.value == "timeout"
        assert ErrorType.RATE_LIMIT.value == "rate_limit"
        assert ErrorType.AUTH_ERROR.value == "auth_error"
        assert ErrorType.PARSE_ERROR.value == "parse_error"
        assert ErrorType.VALIDATION_ERROR.value == "validation_error"
        assert ErrorType.UNKNOWN.value == "unknown"

    def test_error_type_count(self):
        assert len(ErrorType) == 7

    def test_error_type_from_value(self):
        assert ErrorType("timeout") == ErrorType.TIMEOUT
        assert ErrorType("unknown") == ErrorType.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses — AgentState
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentStateDataclass:
    def test_init_with_required_fields(self):
        state = AgentState(
            agent_id="test_agent",
            name="Test Agent",
            status=AgentStatus.IDLE,
        )
        assert state.agent_id == "test_agent"
        assert state.name == "Test Agent"
        assert state.status == AgentStatus.IDLE
        assert state.current_task is None
        assert state.start_time is None
        assert state.end_time is None
        assert state.error_count == 0
        assert state.last_error is None
        assert state.metadata == {}

    def test_init_with_all_fields(self):
        now = time.time()
        meta = {"key": "value"}
        state = AgentState(
            agent_id="full_agent",
            name="Full Agent",
            status=AgentStatus.RUNNING,
            current_task="testing",
            start_time=now,
            end_time=now + 100,
            error_count=3,
            last_error="some error",
            metadata=meta,
        )
        assert state.agent_id == "full_agent"
        assert state.status == AgentStatus.RUNNING
        assert state.current_task == "testing"
        assert state.start_time == now
        assert state.end_time == now + 100
        assert state.error_count == 3
        assert state.last_error == "some error"
        assert state.metadata == meta

    def test_agent_state_is_dataclass(self):
        s1 = AgentState("a", "A", AgentStatus.IDLE)
        s2 = AgentState("a", "A", AgentStatus.IDLE)
        assert s1 == s2  # dataclass equality

    def test_agent_state_repr(self):
        state = AgentState("id", "Name", AgentStatus.IDLE)
        r = repr(state)
        assert "id" in r
        assert "Name" in r


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses — Event
# ═══════════════════════════════════════════════════════════════════════════


class TestEventDataclass:
    def test_init_with_required_fields(self):
        event = Event(
            event_id="evt_001",
            event_type=EventType.AGENT_START,
            agent_id="agent_x",
            timestamp=1234567890.0,
            data={},
        )
        assert event.event_id == "evt_001"
        assert event.event_type == EventType.AGENT_START
        assert event.agent_id == "agent_x"
        assert event.timestamp == 1234567890.0
        assert event.data == {}
        assert event.duration_ms is None

    def test_init_with_all_fields(self):
        event = Event(
            event_id="evt_002",
            event_type=EventType.AGENT_END,
            agent_id="agent_y",
            timestamp=1234567890.0,
            data={"success": True},
            duration_ms=500.5,
        )
        assert event.duration_ms == 500.5
        assert event.data == {"success": True}

    def test_event_repr(self):
        event = Event(
            event_id="evt_003",
            event_type=EventType.TASK_COMPLETE,
            agent_id="a",
            timestamp=0.0,
            data={},
        )
        r = repr(event)
        assert "evt_003" in r


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses — CostRecord
# ═══════════════════════════════════════════════════════════════════════════


class TestCostRecordDataclass:
    def test_init_with_required_fields(self):
        record = CostRecord(
            record_id="rec_001",
            agent_id="cost_agent",
            timestamp=1234567890.0,
            input_tokens=1_000_000,
            output_tokens=500_000,
            cost_usd=0.50,
            model="deepseek-chat",
        )
        assert record.record_id == "rec_001"
        assert record.agent_id == "cost_agent"
        assert record.input_tokens == 1_000_000
        assert record.output_tokens == 500_000
        assert record.cost_usd == 0.50
        assert record.model == "deepseek-chat"
        assert record.task_id is None

    def test_init_with_task_id(self):
        record = CostRecord(
            record_id="rec_002",
            agent_id="a",
            timestamp=0.0,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            model="test",
            task_id="task_abc",
        )
        assert record.task_id == "task_abc"

    def test_cost_record_is_dataclass(self):
        r1 = CostRecord("r", "a", 0.0, 100, 50, 0.01, "m")
        r2 = CostRecord("r", "a", 0.0, 100, 50, 0.01, "m")
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses — HITLRequest
# ═══════════════════════════════════════════════════════════════════════════


class TestHITLRequestDataclass:
    def test_init_with_required_fields(self):
        req = HITLRequest(
            request_id="hitl_req_001",
            agent_id="agent_h",
            task_id="task_h",
            decision_point="approve_text",
            context={"text": "hello"},
            created_at=1234567890.0,
        )
        assert req.request_id == "hitl_req_001"
        assert req.agent_id == "agent_h"
        assert req.task_id == "task_h"
        assert req.decision_point == "approve_text"
        assert req.context == {"text": "hello"}
        assert req.created_at == 1234567890.0
        assert req.status == "pending"
        assert req.reviewed_at is None
        assert req.reviewer_comment is None

    def test_init_with_all_fields(self):
        now = 1234567890.0
        req = HITLRequest(
            request_id="hitl_req_002",
            agent_id="agent_full",
            task_id="task_full",
            decision_point="final_review",
            context={"final": True},
            created_at=now,
            status="approved",
            reviewed_at=now + 60,
            reviewer_comment="looks good",
        )
        assert req.status == "approved"
        assert req.reviewed_at == now + 60
        assert req.reviewer_comment == "looks good"

    def test_hitl_request_repr(self):
        req = HITLRequest(
            request_id="hitl_003",
            agent_id="a",
            task_id="t",
            decision_point="d",
            context={},
            created_at=0.0,
        )
        r = repr(req)
        assert "hitl_003" in r


# ═══════════════════════════════════════════════════════════════════════════
# Module-level convenience functions
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleLevelFunctions:
    def test_get_fleet_status_returns_dict(self):
        from scripts.core.agent_state import get_fleet_status
        result = get_fleet_status()
        assert isinstance(result, dict)
        assert "total_agents" in result
        assert "status_breakdown" in result

    def test_get_total_cost_returns_dict(self):
        from scripts.core.agent_state import get_total_cost
        result = get_total_cost()
        assert isinstance(result, dict)
        assert "total_cost_usd" in result
        assert "total_calls" in result

    def test_record_api_call_returns_cost_record(self):
        from scripts.core.agent_state import record_api_call
        record = record_api_call(
            agent_id="helper_test",
            input_tokens=1000,
            output_tokens=500,
            model="test-model",
            task_id="helper_task",
        )
        assert isinstance(record, CostRecord)
        assert record.agent_id == "helper_test"
        assert record.input_tokens == 1000
        assert record.output_tokens == 500

    def test_record_api_call_without_task_id(self):
        from scripts.core.agent_state import record_api_call
        record = record_api_call(
            agent_id="no_task",
            input_tokens=100,
            output_tokens=50,
            model="test",
        )
        assert record.task_id is None


# ═══════════════════════════════════════════════════════════════════════════
# ErrorClassifier
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorClassifierUnit:
    """ErrorClassifier is a pure class with static methods — no fixtures needed."""

    @pytest.mark.parametrize(
        "msg,expected",
        [
            ("API error occurred", ErrorType.API_ERROR),
            ("internal server error", ErrorType.API_ERROR),
            ("Invalid Request", ErrorType.API_ERROR),
            ("connection timeout", ErrorType.TIMEOUT),
            ("request timed out", ErrorType.TIMEOUT),
            ("Timeout during call", ErrorType.TIMEOUT),
            ("rate limit exceeded", ErrorType.RATE_LIMIT),
            ("too many requests", ErrorType.RATE_LIMIT),
            ("429 rate limit", ErrorType.RATE_LIMIT),
            ("401 unauthorized", ErrorType.AUTH_ERROR),
            ("invalid api key", ErrorType.AUTH_ERROR),
            ("authentication failed", ErrorType.AUTH_ERROR),
            ("json decode error", ErrorType.PARSE_ERROR),
            ("unexpected token", ErrorType.PARSE_ERROR),
            ("invalid json", ErrorType.PARSE_ERROR),
            ("validation failed", ErrorType.VALIDATION_ERROR),
            ("missing required field", ErrorType.VALIDATION_ERROR),
            ("some unexpected error", ErrorType.UNKNOWN),
            ("", ErrorType.UNKNOWN),
        ],
    )
    def test_classify_parity_with_test_agent_state(self, msg, expected):
        """Mirror the same cases tested in test_agent_state.py."""
        from scripts.core.agent_state import ErrorClassifier
        assert ErrorClassifier.classify(msg) == expected

    def test_classify_all_error_types_returns_error_type(self):
        """Every error_type.value should classify to SOME ErrorType (never crash)."""
        from scripts.core.agent_state import ErrorClassifier
        for et in ErrorType:
            result = ErrorClassifier.classify(et.value)
            assert isinstance(result, ErrorType)

    def test_get_retry_strategy_all_types(self):
        from scripts.core.agent_state import ErrorClassifier
        for et in ErrorType:
            strategy = ErrorClassifier.get_retry_strategy(et)
            assert isinstance(strategy, dict)
            assert "max_retries" in strategy
            assert "backoff" in strategy
            assert isinstance(strategy["max_retries"], int)

    def test_get_retry_strategy_rate_limit_has_wait(self):
        from scripts.core.agent_state import ErrorClassifier
        strategy = ErrorClassifier.get_retry_strategy(ErrorType.RATE_LIMIT)
        assert "wait" in strategy
        assert strategy["wait"] == 60

    def test_get_retry_strategy_auth_error_no_retries(self):
        from scripts.core.agent_state import ErrorClassifier
        strategy = ErrorClassifier.get_retry_strategy(ErrorType.AUTH_ERROR)
        assert strategy["max_retries"] == 0
        assert strategy["backoff"] is None
