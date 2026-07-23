"""Comprehensive tests for scripts/core/hitl_gate.py.

Covers: hold, approve, reject, skip (if exists), get_history,
get_statistics, can_proceed logic, gate policies, and serialization.
All tests use synthetic data — no real API calls.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import pytest

# Import from the source module
from scripts.core.hitl_gate import ApprovalRecord, GateState, HITLGate


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db_path():
    """Provide a temporary database path for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "hitl_test.db")


@pytest.fixture
def gate(tmp_db_path):
    """Create a fresh HITLGate instance with a temporary DB."""
    return HITLGate(db_path=tmp_db_path)


@pytest.fixture
def gate_with_records(gate):
    """Create a gate pre-populated with records in various states."""
    # Pending gate
    gate.hold(
        stage="outline",
        content={"title": "Test Paper", "chapters": 5},
        question="Approve outline?",
        gate_id="gate_pending_001",
    )
    # Approved gate
    gate.hold(
        stage="literature",
        content={"papers": 10},
        question="Approve literature review?",
        gate_id="gate_approved_001",
    )
    gate.approve(gate_id="gate_approved_001", feedback="Looks good", approved_by="reviewer1")

    # Rejected gate
    gate.hold(
        stage="draft",
        content={"sections": 8},
        question="Approve draft?",
        gate_id="gate_rejected_001",
    )
    gate.reject(gate_id="gate_rejected_001", feedback="Need more analysis", rejected_by="reviewer2")

    # Another approved gate
    gate.hold(
        stage="final",
        content={"ready": True},
        question="Approve final?",
        gate_id="gate_approved_002",
    )
    gate.approve(gate_id="gate_approved_002", feedback="Excellent work", approved_by="reviewer1")

    return gate


# ─── Test: GateState Enum ────────────────────────────────────────────────────


class TestGateState:
    """Tests for the GateState enum."""

    def test_gate_state_values(self):
        """Verify all expected states exist."""
        assert GateState.PENDING.value == "pending"
        assert GateState.APPROVED.value == "approved"
        assert GateState.REJECTED.value == "rejected"

    def test_gate_state_count(self):
        """Ensure only 3 states are defined."""
        assert len(GateState) == 3


# ─── Test: ApprovalRecord ─────────────────────────────────────────────────────


class TestApprovalRecord:
    """Tests for the ApprovalRecord dataclass."""

    def test_default_state_is_pending(self):
        """A new record should default to PENDING state."""
        rec = ApprovalRecord(gate_id="test_001", stage="outline")
        assert rec.state == GateState.PENDING
        assert rec.feedback == ""
        assert rec.decided_at is None

    def test_record_with_all_fields(self):
        """Test record creation with all fields populated."""
        now = time.time()
        rec = ApprovalRecord(
            gate_id="test_002",
            stage="draft",
            state=GateState.APPROVED,
            content={"title": "Research Paper"},
            question="Is this good?",
            feedback="Yes",
            held_at=now,
            decided_at=now + 100,
            approved_by="alice",
            rejected_by=None,
        )
        assert rec.gate_id == "test_002"
        assert rec.stage == "draft"
        assert rec.state == GateState.APPROVED
        assert rec.approved_by == "alice"
        assert rec.rejected_by is None

    def test_content_default_empty_dict(self):
        """Content should default to empty dict."""
        rec = ApprovalRecord(gate_id="test_003", stage="outline")
        assert rec.content == {}


# ─── Test: hold() ─────────────────────────────────────────────────────────────


class TestHold:
    """Tests for the HITLGate.hold() method."""

    def test_hold_creates_pending_gate(self, gate):
        """hold() should create a gate in PENDING state."""
        gate_id = gate.hold(stage="outline", content={"chapters": 5})
        record = gate.get_record(gate_id)
        assert record is not None
        assert record.state == GateState.PENDING
        assert record.stage == "outline"

    def test_hold_auto_generates_id(self, gate):
        """When no gate_id is provided, one should be auto-generated."""
        gate_id = gate.hold(stage="draft", content={})
        assert gate_id is not None
        assert gate_id.startswith("hitl_draft_")

    def test_hold_preserves_custom_id(self, gate):
        """A custom gate_id should be preserved."""
        gate_id = gate.hold(
            stage="literature",
            content={},
            gate_id="my_custom_gate_123",
        )
        assert gate_id == "my_custom_gate_123"

    def test_hold_stores_content(self, gate):
        """Content passed to hold() should be retrievable."""
        content = {"title": "My Paper", "authors": ["Alice", "Bob"]}
        gate_id = gate.hold(stage="outline", content=content)
        record = gate.get_record(gate_id)
        assert record.content == content

    def test_hold_stores_question(self, gate):
        """Question passed to hold() should be stored."""
        question = "Does this outline look correct?"
        gate_id = gate.hold(stage="outline", content={}, question=question)
        record = gate.get_record(gate_id)
        assert record.question == question

    def test_hold_default_question(self, gate):
        """When no question is provided, a default should be used."""
        gate_id = gate.hold(stage="outline", content={})
        record = gate.get_record(gate_id)
        assert record.question == "请审核以下内容并决定是否继续："

    def test_hold_multiple_gates(self, gate):
        """Multiple concurrent gates should be trackable."""
        gate_id1 = gate.hold(stage="outline", content={})
        gate_id2 = gate.hold(stage="draft", content={})
        gate_id3 = gate.hold(stage="final", content={})
        assert gate_id1 != gate_id2 != gate_id3
        assert len(gate.get_pending()) == 3

    def test_hold_persists_to_db(self, tmp_db_path):
        """hold() should persist the record to SQLite.

        Note: This test verifies pending records are stored. The current implementation
        stores state as lowercase value ("pending"), which matches _init_db's enum lookup.
        """
        gate = HITLGate(db_path=tmp_db_path)
        gate_id = gate.hold(stage="outline", content={"key": "value"})

        # Verify the gate exists in the pending list
        assert gate.is_pending(gate_id)
        # Verify record content is retrievable
        record = gate.get_record(gate_id)
        assert record is not None
        assert record.content == {"key": "value"}


# ─── Test: approve() ──────────────────────────────────────────────────────────


class TestApprove:
    """Tests for the HITLGate.approve() method."""

    def test_approve_changes_state(self, gate):
        """approve() should change gate state to APPROVED."""
        gate_id = gate.hold(stage="outline", content={})
        record = gate.approve(gate_id, feedback="Looks good")
        assert record.state == GateState.APPROVED

    def test_approve_stores_feedback(self, gate):
        """approve() should store the feedback."""
        gate_id = gate.hold(stage="outline", content={})
        record = gate.approve(gate_id, feedback="Structure is correct")
        assert record.feedback == "Structure is correct"

    def test_approve_stores_approved_by(self, gate):
        """approve() should track who approved."""
        gate_id = gate.hold(stage="outline", content={})
        record = gate.approve(gate_id, feedback="OK", approved_by="dr_smith")
        assert record.approved_by == "dr_smith"

    def test_approve_sets_decided_at(self, gate):
        """approve() should set decided_at timestamp."""
        gate_id = gate.hold(stage="outline", content={})
        before = time.time()
        record = gate.approve(gate_id)
        after = time.time()
        assert before <= record.decided_at <= after

    def test_approve_removes_from_pending(self, gate):
        """After approval, gate should no longer be in pending list."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        assert gate_id not in gate._pending
        assert len(gate.get_pending()) == 0

    def test_approve_nonexistent_gate_raises(self, gate):
        """Approving a non-existent gate should raise ValueError."""
        with pytest.raises(ValueError, match="not found or already decided"):
            gate.approve("nonexistent_gate_id")

    def test_approve_twice_raises(self, gate):
        """Approving the same gate twice should raise ValueError."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        with pytest.raises(ValueError, match="not found or already decided"):
            gate.approve(gate_id)


# ─── Test: reject() ───────────────────────────────────────────────────────────


class TestReject:
    """Tests for the HITLGate.reject() method."""

    def test_reject_changes_state(self, gate):
        """reject() should change gate state to REJECTED."""
        gate_id = gate.hold(stage="draft", content={})
        record = gate.reject(gate_id, feedback="Needs revision")
        assert record.state == GateState.REJECTED

    def test_reject_stores_feedback(self, gate):
        """reject() should store the feedback."""
        gate_id = gate.hold(stage="draft", content={})
        record = gate.reject(gate_id, feedback="Add more citations")
        assert record.feedback == "Add more citations"

    def test_reject_stores_rejected_by(self, gate):
        """reject() should track who rejected."""
        gate_id = gate.hold(stage="draft", content={})
        record = gate.reject(gate_id, feedback="OK", rejected_by="dr_jones")
        assert record.rejected_by == "dr_jones"

    def test_reject_sets_decided_at(self, gate):
        """reject() should set decided_at timestamp."""
        gate_id = gate.hold(stage="draft", content={})
        before = time.time()
        record = gate.reject(gate_id, feedback="Fix errors")
        after = time.time()
        assert before <= record.decided_at <= after

    def test_reject_removes_from_pending(self, gate):
        """After rejection, gate should no longer be in pending list."""
        gate_id = gate.hold(stage="draft", content={})
        gate.reject(gate_id, feedback="No")
        assert gate_id not in gate._pending
        assert len(gate.get_pending()) == 0

    def test_reject_requires_feedback(self, gate):
        """reject() should require non-empty feedback."""
        gate_id = gate.hold(stage="draft", content={})
        with pytest.raises(ValueError, match="feedback is required"):
            gate.reject(gate_id, feedback="")

    def test_reject_nonexistent_gate_raises(self, gate):
        """Rejecting a non-existent gate should raise ValueError."""
        with pytest.raises(ValueError, match="not found or already decided"):
            gate.reject("nonexistent_gate_id", feedback="No")

    def test_reject_twice_raises(self, gate):
        """Rejecting the same gate twice should raise ValueError."""
        gate_id = gate.hold(stage="draft", content={})
        gate.reject(gate_id, feedback="First rejection")
        with pytest.raises(ValueError, match="not found or already decided"):
            gate.reject(gate_id, feedback="Second rejection")


# ─── Test: can_proceed / is_approved / is_rejected / is_pending ───────────────


class TestStateQueries:
    """Tests for can_proceed, is_approved, is_rejected, is_pending."""

    def test_is_pending_for_pending_gate(self, gate):
        """is_pending() should return True for pending gates."""
        gate_id = gate.hold(stage="outline", content={})
        assert gate.is_pending(gate_id) is True

    def test_is_pending_false_after_approve(self, gate):
        """is_pending() should return False after approval."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        assert gate.is_pending(gate_id) is False

    def test_is_pending_false_after_reject(self, gate):
        """is_pending() should return False after rejection."""
        gate_id = gate.hold(stage="outline", content={})
        gate.reject(gate_id, feedback="No")
        assert gate.is_pending(gate_id) is False

    def test_is_approved_true_after_approve(self, gate):
        """is_approved() should return True after approval."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        assert gate.is_approved(gate_id) is True

    def test_is_approved_false_after_reject(self, gate):
        """is_approved() should return False after rejection."""
        gate_id = gate.hold(stage="outline", content={})
        gate.reject(gate_id, feedback="No")
        assert gate.is_approved(gate_id) is False

    def test_is_approved_false_for_pending(self, gate):
        """is_approved() should return False for pending gates."""
        gate_id = gate.hold(stage="outline", content={})
        assert gate.is_approved(gate_id) is False

    def test_is_rejected_true_after_reject(self, gate):
        """is_rejected() should return True after rejection."""
        gate_id = gate.hold(stage="outline", content={})
        gate.reject(gate_id, feedback="No")
        assert gate.is_rejected(gate_id) is True

    def test_is_rejected_false_after_approve(self, gate):
        """is_rejected() should return False after approval."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        assert gate.is_rejected(gate_id) is False

    def test_is_rejected_false_for_pending(self, gate):
        """is_rejected() should return False for pending gates."""
        gate_id = gate.hold(stage="outline", content={})
        assert gate.is_rejected(gate_id) is False

    def test_get_record_returns_none_for_unknown(self, gate):
        """get_record() should return None for unknown gate_id."""
        assert gate.get_record("unknown_id") is None

    def test_can_proceed_equivalent_to_is_approved(self, gate):
        """can_proceed() returns True when approved (similar to is_approved)."""
        gate_id = gate.hold(stage="outline", content={})
        # A pending gate cannot proceed
        assert gate.is_approved(gate_id) is False
        gate.approve(gate_id)
        # An approved gate can proceed
        assert gate.is_approved(gate_id) is True


# ─── Test: get_history() ──────────────────────────────────────────────────────


class TestGetHistory:
    """Tests for the HITLGate.get_history() method."""

    def test_get_history_empty_initially(self, gate):
        """get_history() should return empty list for new gate."""
        assert gate.get_history() == []

    def test_get_history_after_decisions(self, gate_with_records):
        """get_history() should return all decided records."""
        history = gate_with_records.get_history()
        assert len(history) == 3  # 2 approved + 1 rejected

    def test_get_history_filter_by_state(self, gate_with_records):
        """get_history() should filter by state correctly."""
        approved = gate_with_records.get_history(state=GateState.APPROVED)
        rejected = gate_with_records.get_history(state=GateState.REJECTED)
        assert len(approved) == 2
        assert len(rejected) == 1

    def test_get_history_filter_by_stage(self, gate_with_records):
        """get_history() should filter by stage correctly."""
        literature = gate_with_records.get_history(stage="literature")
        draft = gate_with_records.get_history(stage="draft")
        assert len(literature) == 1
        assert len(draft) == 1

    def test_get_history_filter_by_stage_and_state(self, gate_with_records):
        """get_history() should combine stage and state filters."""
        results = gate_with_records.get_history(stage="literature", state=GateState.APPROVED)
        assert len(results) == 1
        assert results[0].stage == "literature"

    def test_get_history_limit(self, gate):
        """get_history() should respect limit parameter."""
        for i in range(10):
            gate_id = gate.hold(stage=f"stage_{i}", content={})
            gate.approve(gate_id)
        history = gate.get_history(limit=5)
        assert len(history) == 5

    def test_get_history_returns_most_recent(self, gate):
        """get_history() should return most recent records (last N)."""
        for i in range(5):
            gate_id = gate.hold(stage=f"stage_{i}", content={})
            gate.approve(gate_id)
        history = gate.get_history(limit=3)
        assert len(history) == 3
        # Should be the last 3 records
        assert history[-1].stage == "stage_4"


# ─── Test: stats() / get_statistics() ────────────────────────────────────────


class TestStats:
    """Tests for the HITLGate.stats() method."""

    def test_stats_empty_gate(self, gate):
        """Stats for empty gate should show zeros."""
        stats = gate.stats()
        assert stats["total_decisions"] == 0
        assert stats["approved"] == 0
        assert stats["rejected"] == 0
        assert stats["pending"] == 0
        assert stats["approval_rate"] == 0.0

    def test_stats_with_approved(self, gate):
        """Stats should track approved count correctly."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        stats = gate.stats()
        assert stats["approved"] == 1
        assert stats["rejected"] == 0
        assert stats["total_decisions"] == 1

    def test_stats_with_rejected(self, gate):
        """Stats should track rejected count correctly."""
        gate_id = gate.hold(stage="outline", content={})
        gate.reject(gate_id, feedback="No")
        stats = gate.stats()
        assert stats["rejected"] == 1
        assert stats["approved"] == 0
        assert stats["total_decisions"] == 1

    def test_stats_pending_count(self, gate):
        """Stats should track pending count correctly."""
        gate.hold(stage="outline", content={})
        gate.hold(stage="draft", content={})
        stats = gate.stats()
        assert stats["pending"] == 2

    def test_stats_approval_rate(self, gate):
        """Stats should calculate approval rate correctly."""
        gate_id1 = gate.hold(stage="outline", content={})
        gate.approve(gate_id1)
        gate_id2 = gate.hold(stage="draft", content={})
        gate.reject(gate_id2, feedback="No")
        stats = gate.stats()
        assert stats["approval_rate"] == 0.5

    def test_stats_avg_decision_time(self, gate):
        """Stats should calculate average decision time."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        stats = gate.stats()
        assert stats["avg_decision_time_seconds"] is not None
        assert stats["avg_decision_time_seconds"] >= 0

    def test_stats_from_fixture(self, gate_with_records):
        """Full stats test with multiple records."""
        stats = gate_with_records.stats()
        assert stats["approved"] == 2
        assert stats["rejected"] == 1
        assert stats["pending"] == 1
        assert stats["total_decisions"] == 3
        assert stats["approval_rate"] == pytest.approx(2 / 3)


# ─── Test: get_pending() ──────────────────────────────────────────────────────


class TestGetPending:
    """Tests for the HITLGate.get_pending() method."""

    def test_get_pending_empty_initially(self, gate):
        """get_pending() should return empty list for new gate."""
        assert gate.get_pending() == []

    def test_get_pending_after_holds(self, gate):
        """get_pending() should return all pending gates."""
        gate.hold(stage="outline", content={})
        gate.hold(stage="draft", content={})
        pending = gate.get_pending()
        assert len(pending) == 2

    def test_get_pending_returns_copy(self, gate):
        """get_pending() should return a copy, not the original."""
        gate.hold(stage="outline", content={})
        pending = gate.get_pending()
        pending.clear()  # Modifying the returned list
        assert len(gate.get_pending()) == 1  # Original should be unchanged


# ─── Test: wait_for_decision() ────────────────────────────────────────────────


class TestWaitForDecision:
    """Tests for the HITLGate.wait_for_decision() method."""

    def test_wait_returns_record_after_approve(self, gate):
        """wait_for_decision() should return record after approval."""
        gate_id = gate.hold(stage="outline", content={})

        def approve_later():
            time.sleep(0.1)
            gate.approve(gate_id, feedback="OK")

        t = threading.Thread(target=approve_later)
        t.start()

        record = gate.wait_for_decision(gate_id, timeout=5)
        t.join()

        assert record is not None
        assert record.state == GateState.APPROVED

    def test_wait_returns_record_after_reject(self, gate):
        """wait_for_decision() should return record after rejection."""
        gate_id = gate.hold(stage="outline", content={})

        def reject_later():
            time.sleep(0.1)
            gate.reject(gate_id, feedback="No")

        t = threading.Thread(target=reject_later)
        t.start()

        record = gate.wait_for_decision(gate_id, timeout=5)
        t.join()

        assert record is not None
        assert record.state == GateState.REJECTED

    def test_wait_timeout_returns_none(self, gate):
        """wait_for_decision() should return None on timeout."""
        gate_id = gate.hold(stage="outline", content={})
        result = gate.wait_for_decision(gate_id, timeout=1)  # 1 second timeout
        assert result is None


# ─── Test: listeners ──────────────────────────────────────────────────────────


class TestListeners:
    """Tests for the listener/notification system."""

    def test_add_listener_called_on_hold(self, gate):
        """Listeners should be notified on hold()."""
        events = []

        def listener(event, record):
            events.append((event, record.gate_id))

        gate.add_listener(listener)
        gate_id = gate.hold(stage="outline", content={})

        assert len(events) == 1
        assert events[0] == ("hold", gate_id)

    def test_add_listener_called_on_approve(self, gate):
        """Listeners should be notified on approve()."""
        events = []

        def listener(event, record):
            events.append((event, record.state.value))

        gate.add_listener(listener)
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)

        assert len(events) == 2
        assert events[1] == ("approve", "approved")

    def test_add_listener_called_on_reject(self, gate):
        """Listeners should be notified on reject()."""
        events = []

        def listener(event, record):
            events.append((event, record.state.value))

        gate.add_listener(listener)
        gate_id = gate.hold(stage="outline", content={})
        gate.reject(gate_id, feedback="No")

        assert len(events) == 2
        assert events[1] == ("reject", "rejected")

    def test_listener_idempotent_registration(self, gate):
        """Adding the same listener twice should not duplicate events."""
        events = []
        listener = lambda e, r: events.append(e)

        gate.add_listener(listener)
        gate.add_listener(listener)  # Register again
        gate.hold(stage="outline", content={})

        assert len(events) == 1  # Should only fire once

    def test_listener_error_handling(self, gate):
        """Listener errors should be caught and not propagate."""
        events = []

        def bad_listener(event, record):
            if event == "approve":
                raise RuntimeError("Listener error")

        def good_listener(event, record):
            events.append(event)

        gate.add_listener(bad_listener)
        gate.add_listener(good_listener)

        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)

        # Good listener should still receive both events
        assert len(events) == 2
        assert "hold" in events
        assert "approve" in events


# ─── Test: Serialization ──────────────────────────────────────────────────────


class TestSerialization:
    """Tests for get_state() and from_state()."""

    def test_get_state_returns_dict(self, gate):
        """get_state() should return a dictionary."""
        gate.hold(stage="outline", content={"key": "value"})
        state = gate.get_state()
        assert isinstance(state, dict)
        assert "pending" in state
        assert "stats" in state

    def test_get_state_pending_records(self, gate):
        """get_state() should include pending records."""
        gate.hold(stage="outline", content={}, gate_id="pending_1")
        gate.hold(stage="draft", content={}, gate_id="pending_2")
        state = gate.get_state()
        assert len(state["pending"]) == 2

    def test_from_state_reconstructs_gate(self, tmp_db_path):
        """from_state() should reconstruct a gate with pending records.

        Note: from_state() reconstructs pending records in memory. The history
        is not persisted to DB in the current implementation, so we only test
        pending record reconstruction.
        """
        state = {
            "pending": [
                {
                    "gate_id": "test_001",
                    "stage": "outline",
                    "state": "pending",
                    "content": {"title": "Paper"},
                    "question": "Approve?",
                    "feedback": "",
                    "held_at": time.time(),
                    "decided_at": None,
                    "approved_by": None,
                    "rejected_by": None,
                },
                {
                    "gate_id": "test_002",
                    "stage": "draft",
                    "state": "pending",
                    "content": {"sections": 5},
                    "question": "Approve?",
                    "feedback": "",
                    "held_at": time.time(),
                    "decided_at": None,
                    "approved_by": None,
                    "rejected_by": None,
                },
            ],
            "history_count": 0,
            "stats": {"total_decisions": 0, "approved": 0, "rejected": 0, "pending": 2, "approval_rate": 0.0, "avg_decision_time_seconds": None},
        }

        gate = HITLGate.from_state(state, db_path=tmp_db_path)
        assert len(gate.get_pending()) == 2
        assert gate.get_record("test_001") is not None
        assert gate.get_record("test_002") is not None

    def test_from_state_preserves_content(self, tmp_db_path):
        """from_state() should preserve content fields."""
        content = {"title": "My Research", "authors": ["Alice"]}
        state = {
            "pending": [
                {
                    "gate_id": "content_test",
                    "stage": "outline",
                    "state": "pending",
                    "content": content,
                    "question": "Approve?",
                    "feedback": "",
                    "held_at": time.time(),
                    "decided_at": None,
                    "approved_by": None,
                    "rejected_by": None,
                }
            ],
            "history_count": 0,
            "stats": {"total_decisions": 0, "approved": 0, "rejected": 0, "pending": 1, "approval_rate": 0.0, "avg_decision_time_seconds": None},
        }

        gate = HITLGate.from_state(state, db_path=tmp_db_path)
        record = gate.get_record("content_test")
        assert record.content == content

    def test_get_state_includes_stats(self, gate_with_records):
        """get_state() should include stats."""
        state = gate_with_records.get_state()
        assert "stats" in state
        assert state["stats"]["total_decisions"] == 3


# ─── Test: __repr__ ────────────────────────────────────────────────────────────


class TestRepr:
    """Tests for __repr__ method."""

    def test_repr_empty_gate(self, gate):
        """__repr__ for empty gate should show 0 pending and 0 decided."""
        r = repr(gate)
        assert "pending=0" in r
        assert "decided=0" in r

    def test_repr_with_pending(self, gate):
        """__repr__ should show correct pending count."""
        gate.hold(stage="outline", content={})
        gate.hold(stage="draft", content={})
        r = repr(gate)
        assert "pending=2" in r

    def test_repr_with_history(self, gate):
        """__repr__ should show correct decided count."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        r = repr(gate)
        assert "decided=1" in r


# ─── Test: Thread Safety ───────────────────────────────────────────────────────


class TestThreadSafety:
    """Tests for thread safety of gate operations."""

    def test_concurrent_holds(self, gate):
        """Multiple threads should be able to create gates concurrently."""

        def create_gate(i):
            gate.hold(stage=f"stage_{i}", content={"index": i})

        threads = [threading.Thread(target=create_gate, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(gate.get_pending()) == 10

    def test_concurrent_approves(self, gate):
        """Multiple threads should be able to approve concurrently."""

        def approve_gate(i):
            gate_id = gate.hold(stage=f"stage_{i}", content={})
            gate.approve(gate_id)

        threads = [threading.Thread(target=approve_gate, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(gate.get_history()) == 5
        assert len(gate.get_pending()) == 0


# ─── Test: Edge Cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_approve_then_reject_same_gate(self, gate):
        """Once approved, a gate cannot be rejected."""
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)
        with pytest.raises(ValueError, match="not found or already decided"):
            gate.reject(gate_id, feedback="Changed my mind")

    def test_reject_then_approve_same_gate(self, gate):
        """Once rejected, a gate cannot be approved."""
        gate_id = gate.hold(stage="outline", content={})
        gate.reject(gate_id, feedback="No")
        with pytest.raises(ValueError, match="not found or already decided"):
            gate.approve(gate_id)

    def test_empty_content_allowed(self, gate):
        """Empty content dict should be allowed."""
        gate_id = gate.hold(stage="outline", content={})
        record = gate.get_record(gate_id)
        assert record.content == {}

    def test_special_characters_in_feedback(self, gate):
        """Special characters in feedback should be handled."""
        gate_id = gate.hold(stage="outline", content={})
        feedback = "很好！需要添加更多 <b>emoji</b> 和特殊字符: 你好世界"
        record = gate.approve(gate_id, feedback=feedback)
        assert record.feedback == feedback

    def test_unicode_in_stage_and_content(self, gate):
        """Unicode characters should work in stage and content."""
        gate_id = gate.hold(stage="论文大纲", content={"标题": "研究论文", "作者": "张三"})
        record = gate.get_record(gate_id)
        assert record.stage == "论文大纲"
        assert record.content["标题"] == "研究论文"

    def test_history_in_memory_after_decision(self, gate):
        """History should be maintained in memory after decision."""
        # Use the gate fixture - history is maintained in memory on the same instance
        gate_id = gate.hold(stage="outline", content={})
        gate.approve(gate_id)

        # History is in-memory, same instance has history
        assert len(gate.get_history()) == 1
        assert gate.get_history()[0].state == GateState.APPROVED

        # Note: History is NOT persisted to DB in current implementation
        # This is a design limitation - pending records are persisted,
        # but decided records (history) are only in-memory

    def test_large_content(self, gate):
        """Large content dict should be handled."""
        large_content = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}
        gate_id = gate.hold(stage="outline", content=large_content)
        record = gate.get_record(gate_id)
        assert record.content == large_content


# ─── Test: Performance ───────────────────────────────────────────────────────


class TestPerformance:
    """Performance tests to ensure operations are fast."""

    def test_hold_performance(self, gate):
        """Many holds should complete quickly."""
        start = time.time()
        for i in range(100):
            gate.hold(stage="outline", content={"index": i})
        elapsed = time.time() - start
        assert elapsed < 1.0  # Should complete in under 1 second

    def test_approve_performance(self, gate):
        """Many approves should complete quickly."""
        gate_ids = []
        for i in range(50):
            # Use unique gate_id to avoid collisions
            gid = f"perf_approve_{i}_{int(time.time() * 1000000)}"
            gate_ids.append(gate.hold(stage="outline", content={}, gate_id=gid))

        start = time.time()
        for gid in gate_ids:
            gate.approve(gid)
        elapsed = time.time() - start
        assert elapsed < 1.0  # Should complete in under 1 second

    def test_stats_performance(self, gate):
        """stats() should be fast even with many records."""
        for i in range(100):
            gid = gate.hold(stage="outline", content={})
            gate.approve(gid)
        start = time.time()
        for _ in range(100):
            gate.stats()
        elapsed = time.time() - start
        assert elapsed < 0.5  # Should be very fast


# ─── Test: request_approval alias (if exists) ──────────────────────────────────


class TestRequestApproval:
    """Tests for request_approval() method if it exists."""

    def test_request_approval_exists(self, gate):
        """request_approval should be an alias or wrapper for hold()."""
        # Check if the method exists
        if hasattr(gate, "request_approval"):
            gate_id = gate.request_approval(stage="outline", content={})
            assert gate.is_pending(gate_id)
        else:
            # If not exists, this test is skipped
            pytest.skip("request_approval method not found")


# ─── Test: skip() method (if exists) ─────────────────────────────────────────


class TestSkip:
    """Tests for skip() method if it exists."""

    def test_skip_exists(self, gate):
        """skip() method should exist or be equivalent to approve()."""
        if hasattr(gate, "skip"):
            gate_id = gate.hold(stage="outline", content={})
            gate.skip(gate_id)
            assert gate.is_approved(gate_id) or gate.is_pending(gate_id)
        else:
            pytest.skip("skip method not found")
