"""Comprehensive tests for scripts/core/hitl_gate.py

Tests HITLGate, GateState, ApprovalRecord — the full approval lifecycle:
hold, approve, reject, timeout, stats, listener callbacks, serialization.
All tests use a temporary DB path — no real files created.
"""
import pytest
import time
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── GateState Tests ────────────────────────────────────────────────────────────


class TestGateStateEnum:
    """Test GateState enum values."""

    def test_gate_state_pending_exists(self):
        """GateState.PENDING exists and has correct value."""
        from scripts.core.hitl_gate import GateState
        assert GateState.PENDING.value == "pending"

    def test_gate_state_approved_exists(self):
        """GateState.APPROVED exists and has correct value."""
        from scripts.core.hitl_gate import GateState
        assert GateState.APPROVED.value == "approved"

    def test_gate_state_rejected_exists(self):
        """GateState.REJECTED exists and has correct value."""
        from scripts.core.hitl_gate import GateState
        assert GateState.REJECTED.value == "rejected"

    def test_gate_state_all_values(self):
        """GateState has exactly 3 states."""
        from scripts.core.hitl_gate import GateState
        states = list(GateState)
        assert len(states) == 3

    def test_gate_state_from_string(self):
        """GateState can be accessed by string key."""
        from scripts.core.hitl_gate import GateState
        assert GateState["PENDING"] == GateState.PENDING
        assert GateState["APPROVED"] == GateState.APPROVED
        assert GateState["REJECTED"] == GateState.REJECTED


# ─── ApprovalRecord Tests ───────────────────────────────────────────────────────


class TestApprovalRecord:
    """Test ApprovalRecord dataclass."""

    def test_approval_record_creation(self):
        """ApprovalRecord can be created with gate_id and stage."""
        from scripts.core.hitl_gate import ApprovalRecord, GateState
        rec = ApprovalRecord(gate_id="test_001", stage="outline")
        assert rec.gate_id == "test_001"
        assert rec.stage == "outline"
        assert rec.state == GateState.PENDING
        assert rec.feedback == ""
        assert rec.held_at > 0

    def test_approval_record_with_content(self):
        """ApprovalRecord stores content dict."""
        from scripts.core.hitl_gate import ApprovalRecord
        content = {"outline": {"chapters": 7}, "metadata": {"author": "test"}}
        rec = ApprovalRecord(gate_id="test_002", stage="writing", content=content)
        assert rec.content == content
        assert rec.content["outline"]["chapters"] == 7

    def test_approval_record_with_question(self):
        """ApprovalRecord stores review question."""
        from scripts.core.hitl_gate import ApprovalRecord
        rec = ApprovalRecord(
            gate_id="test_003",
            stage="literature",
            question="Is the literature coverage adequate?",
        )
        assert "literature" in rec.question

    def test_approval_record_defaults(self):
        """ApprovalRecord has sensible defaults."""
        from scripts.core.hitl_gate import ApprovalRecord, GateState
        rec = ApprovalRecord(gate_id="test_004", stage="outline")
        assert rec.decided_at is None
        assert rec.approved_by is None
        assert rec.rejected_by is None
        assert rec.state == GateState.PENDING


# ─── HITLGate Core Tests ───────────────────────────────────────────────────────


class TestHITLGateInit:
    """Test HITLGate initialization."""

    def test_initializes_with_memory_db(self):
        """HITLGate can use in-memory SQLite DB."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        assert gate is not None
        assert gate._db_path == ":memory:"

    def test_pending_dict_starts_empty(self):
        """_pending dict is empty after init."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        assert gate._pending == {}
        assert len(gate._pending) == 0

    def test_history_list_starts_empty(self):
        """_history list is empty after init."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        assert gate._history == []
        assert isinstance(gate._history, list)

    def test_listeners_list_starts_empty(self):
        """_listeners list is initialized."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        assert isinstance(gate._listeners, list)

    def test_repr_shows_pending_and_decided(self):
        """__repr__ shows pending and decided counts."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        r = repr(gate)
        assert "HITLGate" in r
        assert "pending=" in r
        assert "decided=" in r


# ─── hold() Tests ──────────────────────────────────────────────────────────────


class TestHoldMethod:
    """Test gate.hold() method."""

    def test_hold_returns_gate_id(self):
        """hold() returns a gate_id string."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        assert isinstance(gid, str)
        assert len(gid) > 0

    def test_hold_returns_string_gate_id(self):
        """hold() gate_id starts with 'hitl_' or is explicit."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        # Should be auto-generated with stage prefix
        assert "outline" in gid

    def test_hold_with_explicit_gate_id(self):
        """hold() accepts explicit gate_id."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="writing", content={}, gate_id="my_custom_id")
        assert gid == "my_custom_id"

    def test_hold_with_question(self):
        """hold() stores the question."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        q = "Please review the outline structure."
        gid = gate.hold(stage="outline", content={}, question=q)
        rec = gate.get_record(gid)
        assert rec.question == q

    def test_hold_stores_content(self):
        """hold() stores content dict in record."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        content = {"outline": {"title": "Test", "chapters": 5}}
        gid = gate.hold(stage="outline", content=content)
        rec = gate.get_record(gid)
        assert rec.content == content

    def test_hold_creates_pending_record(self):
        """hold() creates PENDING record."""
        from scripts.core.hitl_gate import HITLGate, GateState
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        rec = gate.get_record(gid)
        assert rec is not None
        assert rec.state == GateState.PENDING

    def test_hold_is_pending(self):
        """is_pending() returns True for new hold."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        assert gate.is_pending(gid) is True

    def test_multiple_holds_create_multiple_pending(self):
        """Multiple hold() calls create multiple pending records."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="outline", content={})
        gate.hold(stage="literature", content={})
        gate.hold(stage="writing", content={})
        pending = gate.get_pending()
        assert len(pending) == 3

    def test_hold_stores_stage(self):
        """hold() stores the stage name in record."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="financial_analysis", content={})
        rec = gate.get_record(gid)
        assert rec.stage == "financial_analysis"


# ─── approve() Tests ───────────────────────────────────────────────────────────


class TestApproveMethod:
    """Test gate.approve() method."""

    def test_approve_returns_record(self):
        """approve() returns the ApprovalRecord."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        rec = gate.approve(gid, feedback="Looks good")
        assert rec is not None
        assert rec.gate_id == gid

    def test_approve_sets_state_approved(self):
        """approve() sets state to APPROVED."""
        from scripts.core.hitl_gate import HITLGate, GateState
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid, feedback="ok")
        rec = gate.get_record(gid)
        assert rec.state == GateState.APPROVED

    def test_approve_stores_feedback(self):
        """approve() stores reviewer feedback."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid, feedback="结构完整，继续")
        rec = gate.get_record(gid)
        assert "结构完整" in rec.feedback

    def test_approve_sets_decided_at(self):
        """approve() sets decided_at timestamp."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        before = time.time()
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid)
        after = time.time()
        rec = gate.get_record(gid)
        assert rec.decided_at is not None
        assert before <= rec.decided_at <= after

    def test_approve_sets_approved_by(self):
        """approve() records who approved."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid, approved_by="reviewer_001")
        rec = gate.get_record(gid)
        assert rec.approved_by == "reviewer_001"

    def test_approve_removes_from_pending(self):
        """approve() removes gate from pending list."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        assert gate.is_pending(gid) is True
        gate.approve(gid)
        assert gate.is_pending(gid) is False

    def test_approve_nonexistent_raises(self):
        """approve() raises ValueError for unknown gate_id."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        with pytest.raises(ValueError):
            gate.approve("ghost_id_123", feedback="test")

    def test_approve_is_approved_true(self):
        """is_approved() returns True after approve()."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid)
        assert gate.is_approved(gid) is True

    def test_approve_double_approve_raises(self):
        """Approving twice raises ValueError."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid)
        with pytest.raises(ValueError):
            gate.approve(gid)


# ─── reject() Tests ───────────────────────────────────────────────────────────


class TestRejectMethod:
    """Test gate.reject() method."""

    def test_reject_returns_record(self):
        """reject() returns the ApprovalRecord."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        rec = gate.reject(gid, feedback="Needs more detail")
        assert rec is not None
        assert rec.gate_id == gid

    def test_reject_sets_state_rejected(self):
        """reject() sets state to REJECTED."""
        from scripts.core.hitl_gate import HITLGate, GateState
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.reject(gid, feedback="incomplete")
        rec = gate.get_record(gid)
        assert rec.state == GateState.REJECTED

    def test_reject_requires_feedback(self):
        """reject() requires non-empty feedback."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        with pytest.raises(ValueError, match="feedback"):
            gate.reject(gid, feedback="")

    def test_reject_requires_feedback_none(self):
        """reject() with None feedback raises ValueError."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        with pytest.raises(ValueError):
            gate.reject(gid, feedback=None)

    def test_reject_sets_rejected_by(self):
        """reject() records who rejected."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.reject(gid, feedback="bad", rejected_by="senior_reviewer")
        rec = gate.get_record(gid)
        assert rec.rejected_by == "senior_reviewer"

    def test_reject_removes_from_pending(self):
        """reject() removes gate from pending."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.reject(gid, feedback="no")
        assert gate.is_pending(gid) is False

    def test_reject_nonexistent_raises(self):
        """reject() raises ValueError for unknown gate_id."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        with pytest.raises(ValueError):
            gate.reject("ghost_id", feedback="not found")

    def test_reject_is_rejected_true(self):
        """is_rejected() returns True after reject()."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.reject(gid, feedback="failed")
        assert gate.is_rejected(gid) is True


# ─── Query Methods Tests ───────────────────────────────────────────────────────


class TestQueryMethods:
    """Test get_record, get_pending, get_history."""

    def test_get_pending_returns_list(self):
        """get_pending() returns a list."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="a", content={})
        gate.hold(stage="b", content={})
        pending = gate.get_pending()
        assert isinstance(pending, list)
        assert len(pending) == 2

    def test_get_pending_returns_copy(self):
        """get_pending() returns a copy (not the internal dict)."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="outline", content={})
        pending = gate.get_pending()
        pending.clear()  # Mutating the copy should not affect internal state
        assert len(gate._pending) == 1

    def test_get_history_returns_list(self):
        """get_history() returns a list."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid1 = gate.hold(stage="outline", content={})
        gate.approve(gid1)
        history = gate.get_history()
        assert isinstance(history, list)
        assert len(history) == 1

    def test_get_history_filter_by_stage(self):
        """get_history() can filter by stage."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="outline", content={})
        gate.hold(stage="writing", content={})
        gid1 = list(gate._pending.keys())[0]
        gate.approve(gid1)
        outline_history = gate.get_history(stage="outline")
        assert len(outline_history) >= 1

    def test_get_record_returns_record(self):
        """get_record() returns ApprovalRecord or None."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        rec = gate.get_record(gid)
        assert rec is not None
        assert rec.gate_id == gid

    def test_get_record_returns_none_for_unknown(self):
        """get_record() returns None for unknown gate_id."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        rec = gate.get_record("unknown_gate")
        assert rec is None


# ─── wait_for_decision Tests ───────────────────────────────────────────────────


class TestWaitForDecision:
    """Test wait_for_decision() method."""

    def test_wait_for_decision_returns_on_approve(self):
        """wait_for_decision() returns record after approve()."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})

        def delayed_approve():
            time.sleep(0.05)
            gate.approve(gid, feedback="ok")

        t = threading.Thread(target=delayed_approve)
        t.start()

        rec = gate.wait_for_decision(gid, timeout=5)
        t.join()

        assert rec is not None
        assert rec.gate_id == gid

    def test_wait_for_decision_returns_none_on_timeout(self):
        """wait_for_decision() returns None after timeout."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        rec = gate.wait_for_decision(gid, timeout=1)
        assert rec is None

    def test_wait_for_decision_returns_immediately_if_decided(self):
        """wait_for_decision() returns immediately if already decided."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid)
        rec = gate.wait_for_decision(gid, timeout=1)
        assert rec is not None


# ─── Statistics Tests ──────────────────────────────────────────────────────────


class TestStats:
    """Test stats() method."""

    def test_stats_returns_dict(self):
        """stats() returns a dict."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        s = gate.stats()
        assert isinstance(s, dict)

    def test_stats_contains_total_decisions(self):
        """stats() includes total_decisions key."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        s = gate.stats()
        assert "total_decisions" in s

    def test_stats_contains_approved_count(self):
        """stats() includes approved count."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid1 = gate.hold(stage="a", content={})
        gate.approve(gid1)
        s = gate.stats()
        assert "approved" in s
        assert s["approved"] == 1

    def test_stats_contains_rejected_count(self):
        """stats() includes rejected count."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid1 = gate.hold(stage="a", content={})
        gate.reject(gid1, feedback="bad")
        s = gate.stats()
        assert "rejected" in s
        assert s["rejected"] == 1

    def test_stats_contains_pending_count(self):
        """stats() includes pending count."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="a", content={})
        s = gate.stats()
        assert "pending" in s
        assert s["pending"] == 1

    def test_stats_contains_approval_rate(self):
        """stats() includes approval_rate."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid1 = gate.hold(stage="a", content={})
        gate.approve(gid1)
        gid2 = gate.hold(stage="b", content={})
        gate.reject(gid2, feedback="no")
        s = gate.stats()
        assert "approval_rate" in s
        assert s["approval_rate"] == 0.5


# ─── Listener Tests ────────────────────────────────────────────────────────────


class TestListenerPattern:
    """Test add_listener and notification system."""

    def test_add_listener_appends_callback(self):
        """add_listener() adds callback to _listeners."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")

        def cb(event, record):
            pass

        gate.add_listener(cb)
        assert cb in gate._listeners

    def test_add_listener_idempotent(self):
        """add_listener() is idempotent (no duplicate)."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")

        def cb(event, record):
            pass

        gate.add_listener(cb)
        gate.add_listener(cb)
        count = sum(1 for l in gate._listeners if l == cb)
        assert count == 1

    def test_listener_called_on_approve(self):
        """Listener is called when request is approved."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")

        called = []

        def my_listener(event, record):
            called.append((event, record.gate_id))

        gate.add_listener(my_listener)
        gid = gate.hold(stage="outline", content={})
        gate.approve(gid, feedback="ok")

        assert len(called) >= 1
        events = [e[0] for e in called]
        assert "approve" in events

    def test_listener_called_on_reject(self):
        """Listener is called when request is rejected."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")

        called = []

        def my_listener(event, record):
            called.append((event, record.gate_id))

        gate.add_listener(my_listener)
        gid = gate.hold(stage="outline", content={})
        gate.reject(gid, feedback="bad")

        assert len(called) >= 1
        events = [e[0] for e in called]
        assert "reject" in events

    def test_listener_called_on_hold(self):
        """Listener is called when hold() is called."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")

        called = []

        def my_listener(event, record):
            called.append(event)

        gate.add_listener(my_listener)
        gate.hold(stage="outline", content={})

        assert "hold" in called

    def test_listener_error_does_not_crash(self):
        """Listener exception is caught and doesn't crash gate."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")

        def bad_listener(event, record):
            raise RuntimeError("intentional error in listener")

        gate.add_listener(bad_listener)
        gid = gate.hold(stage="outline", content={})
        # Should not raise
        gate.approve(gid, feedback="ok")


# ─── State Serialization Tests ─────────────────────────────────────────────────


class TestStateSerialization:
    """Test get_state() and from_state()."""

    def test_get_state_returns_dict(self):
        """get_state() returns a dict."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="outline", content={"key": "value"})
        state = gate.get_state()
        assert isinstance(state, dict)

    def test_get_state_contains_pending(self):
        """get_state() includes pending records."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="outline", content={})
        gate.hold(stage="writing", content={})
        state = gate.get_state()
        assert "pending" in state
        assert len(state["pending"]) == 2

    def test_get_state_pending_has_required_fields(self):
        """Pending state entries have required fields."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gate.hold(stage="test_stage", content={"data": 123}, question="test?")
        state = gate.get_state()
        pending = state["pending"][0]
        assert "gate_id" in pending
        assert "stage" in pending
        assert "state" in pending
        assert "content" in pending
        assert "question" in pending

    def test_get_state_contains_stats(self):
        """get_state() includes stats."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        state = gate.get_state()
        assert "stats" in state

    def test_from_state_reconstructs_pending(self):
        """from_state() reconstructs pending records."""
        from scripts.core.hitl_gate import HITLGate
        gate1 = HITLGate(db_path=":memory:")
        gate1.hold(stage="outline", content={"outline": "test"}, question="ok?")
        gate1.hold(stage="writing", content={"draft": "v1"})

        state = gate1.get_state()

        # Create new gate from state
        gate2 = HITLGate.from_state(state, db_path=":memory:")
        pending2 = gate2.get_pending()
        assert len(pending2) == 2

    def test_from_state_restores_content(self):
        """from_state() restores content correctly."""
        from scripts.core.hitl_gate import HITLGate
        gate1 = HITLGate(db_path=":memory:")
        gate1.hold(stage="outline", content={"title": "My Paper", "chapters": 8})
        state = gate1.get_state()

        gate2 = HITLGate.from_state(state, db_path=":memory:")
        rec = gate2.get_pending()[0]
        assert rec.content["title"] == "My Paper"
        assert rec.content["chapters"] == 8


# ─── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_hold_multiple_same_stage(self):
        """Multiple holds for the same stage are allowed."""
        from scripts.core.hitl_gate import HITLGate
        import time
        gate = HITLGate(db_path=":memory:")
        # Add small delay between holds so IDs are distinct (ms precision)
        gid1 = gate.hold(stage="outline", content={"v": 1})
        time.sleep(0.002)  # 2ms > typical clock resolution
        gid2 = gate.hold(stage="outline", content={"v": 2})
        assert gid1 != gid2
        assert len(gate.get_pending()) == 2

    def test_approve_without_hold_raises(self):
        """Approve on never-held gate raises ValueError."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        with pytest.raises(ValueError):
            gate.approve("never_created")

    def test_reject_without_hold_raises(self):
        """Reject on never-held gate raises ValueError."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        with pytest.raises(ValueError):
            gate.reject("never_created", feedback="test")

    def test_get_history_respects_limit(self):
        """get_history() respects limit parameter."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        for i in range(10):
            gid = gate.hold(stage=f"stage_{i}", content={})
            gate.approve(gid)

        history = gate.get_history(limit=3)
        assert len(history) == 3

    def test_approve_with_empty_feedback(self):
        """approve() allows empty feedback."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        rec = gate.approve(gid, feedback="")
        assert rec is not None

    def test_hold_then_immediate_get_pending(self):
        """get_pending() immediately after hold() includes the new record."""
        from scripts.core.hitl_gate import HITLGate
        gate = HITLGate(db_path=":memory:")
        gid = gate.hold(stage="outline", content={})
        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0].gate_id == gid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
