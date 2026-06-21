"""HITLGate: Human-in-the-Loop approval gate for agent pipelines.

Sentinel HITL design:
    - Pipeline pauses at designated checkpoints
    - Analyst reviews intermediate output
    - Approve to continue, Reject to rollback with feedback

Reference: https://github.com/mollendorff-ai/sentinel
"""

from __future__ import annotations

__all__ = [
    "GateState",
    "ApprovalRecord",
    "HITLGate",
]

import json
import logging
import sqlite3
import threading
import time

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ─── Gate State ───────────────────────────────────────────────────────────────


class GateState(Enum):
    PENDING = "pending"    # Waiting for human review
    APPROVED = "approved"   # Human approved, pipeline continues
    REJECTED = "rejected"  # Human rejected, pipeline rolls back


# ─── Approval Record ─────────────────────────────────────────────────────────


@dataclass
class ApprovalRecord:
    """
    A single approval gate record.

    Attributes
    ----------
    gate_id : str
        Unique identifier for this gate instance.
    stage : str
        Pipeline stage that triggered this gate.
    state : GateState
        Current gate state.
    content : dict
        Content shown to the human reviewer.
    question : str
        Specific question or instruction for the reviewer.
    feedback : str
        Human reviewer's feedback (provided on approve/reject).
    held_at : float
        Unix timestamp when the gate was created.
    decided_at : float | None
        Unix timestamp when the human made a decision.
    approved_by : str | None
        Identifier of who approved (if known).
    """
    gate_id: str
    stage: str
    state: GateState = GateState.PENDING
    content: dict = field(default_factory=dict)
    question: str = ""
    feedback: str = ""
    held_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    approved_by: str | None = None
    rejected_by: str | None = None


# ─── HITL Gate ────────────────────────────────────────────────────────────────


class HITLGate:
    """
    Human-in-the-Loop approval gate for critical pipeline checkpoints.

    Sentinel-style design:
        - Gates pause the pipeline at key stages (outline, draft, final)
        - Human reviewer can approve or reject with feedback
        - Rejected stages rollback to the previous agent with feedback
        - All decisions are logged for audit trail

    Standard approval points:
        1. Outline approval: After OutlineAgent → user confirms structure
        2. Literature approval: After LiteratureReviewAgent → user confirms references
        3. Draft approval: After SectionWritingAgent → user confirms content
        4. Final approval: After ContentRefinementAgent → user confirms quality

    Usage:
        gate = HITLGate()

        # Pipeline reaches checkpoint
        gate.hold(
            stage="outline",
            content={"outline": outline_json, "chapters": 7},
            question="请确认论文大纲结构是否正确？",
        )

        # In a separate thread / web UI, reviewer calls:
        gate.approve(gate_id, feedback="结构OK，继续")
        # or
        gate.reject(gate_id, feedback="需要增加方法论章节")

        # Pipeline resumes:
        decision = gate.get_decision(gate_id)
        if decision.state == GateState.APPROVED:
            continue_pipeline()
        else:
            rollback_and_revise(decision.feedback)
    """

    _write_lock = threading.Lock()
    _pending_lock = threading.Lock()

    def __init__(self, db_path: str = ".cache/hitl_gates.db"):
        self._pending: dict[str, ApprovalRecord] = {}
        self._history: list[ApprovalRecord] = []
        self._listeners: list = []
        self._db_path = db_path
        self._init_db()

        # ── Auto-register HITLManager as listener ──────────────────────────
        # 双向同步：HITLGate 的每个操作事件都同步到全局 HITLManager，
        # 保证 Dashboard / orchestrator / AgentPipeline 读取同一份数据
        try:
            from scripts.core.agent_state import HITLManager
            _hm = HITLManager()
            if _hm not in self._listeners:
                self.register_listener(_hm._on_gate_event)
        except Exception as exc:
            logger.debug("[HITLGate] HITLManager auto-registration skipped: %s", exc)

    # ── Database ───────────────────────────────────────────────────────────────

    def _init_db(self):
        """Initialize SQLite DB for persistence."""
        from pathlib import Path

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS approval_records ("
            "  gate_id TEXT PRIMARY KEY,"
            "  stage TEXT,"
            "  state TEXT,"
            "  content TEXT,"
            "  question TEXT,"
            "  feedback TEXT,"
            "  held_at REAL,"
            "  decided_at REAL,"
            "  approved_by TEXT,"
            "  rejected_by TEXT"
            ")"
        )
        self._db.commit()

        # Load pending records from DB on startup
        with self._write_lock:
            cur = self._db.execute(
            "SELECT gate_id,stage,state,content,question,feedback,"
            "       held_at,decided_at,approved_by,rejected_by "
            "FROM approval_records WHERE state=?",
            (GateState.PENDING.value,),
        )
        for row in cur.fetchall():
                try:
                    content_val = json.loads(row[3]) if row[3] else {}
                except (json.JSONDecodeError, ValueError, TypeError):
                    _log.warning(
                        "HITLGate[%s]: corrupted content in approval_records at row %d: %s ...",
                        gate_id, row[0], repr(row[3][:100]) if row[3] else "empty"
                    )
                    content_val = {}
                rec = ApprovalRecord(
                    gate_id=row[0],
                    stage=row[1],
                    state=GateState[row[2]],
                    content=content_val,
                    question=row[4] or "",
                    feedback=row[5] or "",
                    held_at=row[6],
                    decided_at=row[7],
                    approved_by=row[8],
                    rejected_by=row[9],
                )
                self._pending[rec.gate_id] = rec

    # ── Gate Operations ─────────────────────────────────────────────────

    def hold(
        self,
        stage: str,
        content: dict,
        question: str = "请审核以下内容并决定是否继续：",
        gate_id: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """
        Create a pending approval gate.

        Parameters
        ----------
        stage : str
            Name of the pipeline stage (e.g. "outline", "literature", "draft").
        content : dict
            Content to present to the reviewer (outline, citations, draft, etc.).
        question : str
            Specific question or instruction for the reviewer.
        gate_id : str | None
            Optional explicit gate ID. If None, auto-generates one.
        timeout : int | None
            Seconds to wait for a decision. If None, waits indefinitely.
            When timeout expires, the gate remains open and returns the gate_id.
            Use wait_for_decision() separately for timeout handling.

        Returns
        -------
        str
            The gate_id that can be used to approve/reject later.
        """
        gid = gate_id or f"hitl_{stage}_{int(time.time() * 1000)}"

        record = ApprovalRecord(
            gate_id=gid,
            stage=stage,
            state=GateState.PENDING,
            content=content,
            question=question,
            held_at=time.time(),
        )

        with self._pending_lock:
            self._pending[gid] = record

        # Persist to SQLite
        with self._write_lock:
            self._db.execute(
                "INSERT OR REPLACE INTO approval_records VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    gid,
                    stage,
                    GateState.PENDING.value,
                    json.dumps(content),
                    question,
                    "",
                    time.time(),
                    None,
                    None,
                    None,
                ],
            )
            self._db.commit()

        # Notify listeners
        self._notify("hold", record)

        return gid

    def approve(
        self,
        gate_id: str,
        feedback: str = "",
        approved_by: str | None = None,
    ) -> ApprovalRecord:
        """
        Approve a pending gate, allowing the pipeline to continue.

        Parameters
        ----------
        gate_id : str
            The gate ID returned by hold().
        feedback : str
            Optional feedback from the reviewer.
        approved_by : str | None
            Identifier of who approved.

        Returns
        -------
        ApprovalRecord
            The completed approval record.
        """
        with self._pending_lock:
            record = self._pending.pop(gate_id, None)
        if record is None:
            raise ValueError(f"Gate '{gate_id}' not found or already decided")

        record.state = GateState.APPROVED
        record.feedback = feedback
        record.decided_at = time.time()
        record.approved_by = approved_by

        with self._write_lock:
            self._db.execute(
                "UPDATE approval_records SET state=?, feedback=?, decided_at=?, approved_by=? "
                "WHERE gate_id=?",
                [GateState.APPROVED.value, feedback, record.decided_at, approved_by, gate_id],
            )
            self._db.commit()

        with self._pending_lock:
            self._history.append(record)
        self._notify("approve", record)

        return record

    def reject(
        self,
        gate_id: str,
        feedback: str,
        rejected_by: str | None = None,
    ) -> ApprovalRecord:
        """
        Reject a pending gate, triggering pipeline rollback.

        Parameters
        ----------
        gate_id : str
            The gate ID returned by hold().
        feedback : str
            **Required.** Feedback explaining why the content was rejected.
        rejected_by : str | None
            Identifier of who rejected.

        Returns
        -------
        ApprovalRecord
            The completed rejection record.
        """
        if not feedback:
            raise ValueError("feedback is required for rejection")

        with self._pending_lock:
            record = self._pending.pop(gate_id, None)
        if record is None:
            raise ValueError(f"Gate '{gate_id}' not found or already decided")

        record.state = GateState.REJECTED
        record.feedback = feedback
        record.decided_at = time.time()
        record.rejected_by = rejected_by

        with self._write_lock:
            self._db.execute(
                "UPDATE approval_records SET state=?, feedback=?, decided_at=?, rejected_by=? "
                "WHERE gate_id=?",
                [GateState.REJECTED.value, feedback, record.decided_at, rejected_by, gate_id],
            )
            self._db.commit()

        with self._pending_lock:
            self._history.append(record)
        self._notify("reject", record)

        return record

    # ── Query Methods ─────────────────────────────────────────────────

    def get_record(self, gate_id: str) -> ApprovalRecord | None:
        """Get the current state of a gate (pending or historical)."""
        with self._pending_lock:
            if gate_id in self._pending:
                return self._pending[gate_id]
            for record in self._history:
                if record.gate_id == gate_id:
                    return record
        return None

    def get_pending(self) -> list[ApprovalRecord]:
        """Return a copy of all pending gates (prevents external mutation)."""
        with self._pending_lock:
            return [ApprovalRecord(**vars(r)) for r in self._pending.values()]

    def wait_for_decision(
        self,
        gate_id: str,
        timeout: int | None = None,
    ) -> ApprovalRecord | None:
        """
        Block until a gate receives a human decision (approve or reject).

        This replaces direct polling of _pending dict with a thread-safe
        polling loop that uses the public get_record() API.

        Parameters
        ----------
        gate_id : str
            The gate ID returned by hold().
        timeout : int | None
            Maximum seconds to wait. If None, waits indefinitely.

        Returns
        -------
        ApprovalRecord | None
            The final record after decision, or None if timeout expired.
        """
        deadline = (time.time() + timeout) if timeout else None
        poll_interval = 0.5

        while True:
            rec = self.get_record(gate_id)
            if rec is None:
                # Gate was decided and removed from pending
                return rec
            if rec.state != GateState.PENDING:
                # State changed (approved/rejected)
                return rec

            if deadline is not None and time.time() >= deadline:
                return None  # Timeout

            time.sleep(poll_interval)

    def get_history(
        self,
        stage: str | None = None,
        state: GateState | None = None,
        limit: int = 50,
    ) -> list[ApprovalRecord]:
        """
        Return gate history, optionally filtered.

        Parameters
        ----------
        stage : str | None
            Filter by pipeline stage name.
        state : GateState | None
            Filter by approval state.
        limit : int
            Maximum number of records to return.

        Returns
        -------
        list[ApprovalRecord]
            Filtered approval history.
        """
        results = self._history

        if stage:
            results = [r for r in results if r.stage == stage]
        if state:
            results = [r for r in results if r.state == state]

        return results[-limit:]

    def is_approved(self, gate_id: str) -> bool:
        """Check if a gate has been approved."""
        record = self.get_record(gate_id)
        return record is not None and record.state == GateState.APPROVED

    def is_rejected(self, gate_id: str) -> bool:
        """Check if a gate has been rejected."""
        record = self.get_record(gate_id)
        return record is not None and record.state == GateState.REJECTED

    def is_pending(self, gate_id: str) -> bool:
        """Check if a gate is still pending."""
        return gate_id in self._pending

    # ── Statistics ────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return approval gate statistics."""
        total = len(self._history)
        approved = sum(1 for r in self._history if r.state == GateState.APPROVED)
        rejected = sum(1 for r in self._history if r.state == GateState.REJECTED)
        pending = len(self._pending)

        avg_decision_time: float | None = None
        decided = [r for r in self._history if r.decided_at is not None]
        if decided:
            total_time = sum(r.decided_at - r.held_at for r in decided)
            avg_decision_time = total_time / len(decided)

        return {
            "total_decisions": total,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "approval_rate": approved / total if total > 0 else 0.0,
            "avg_decision_time_seconds": avg_decision_time,
        }

    # ── Listener Hooks ────────────────────────────────────────────────

    def add_listener(self, callback) -> None:
        """
        Register a callback for gate state changes.

        Callback signature: callback(event_type: str, record: ApprovalRecord)

        Idempotent — registering the same callback twice has no effect.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def _notify(self, event: str, record: ApprovalRecord) -> None:
        """Notify all listeners of a gate state change."""
        for listener in self._listeners:
            try:
                listener(event, record)
            except Exception as exc:
                print(f"[HITLGate] Listener error in '{event}': {exc}", flush=True)

    def get_state(self) -> dict[str, Any]:
        """
        Serialise the complete gate state for checkpoint persistence.

        Returns a dict with pending records, history, and statistics that can be
        stored by CheckpointManager and used to reconstruct the gate via
        HITLGate.from_state().
        """
        return {
            "pending": [
                {
                    "gate_id": r.gate_id,
                    "stage": r.stage,
                    "state": r.state.value,
                    "content": r.content,
                    "question": r.question,
                    "feedback": r.feedback,
                    "held_at": r.held_at,
                    "decided_at": r.decided_at,
                    "approved_by": r.approved_by,
                    "rejected_by": r.rejected_by,
                }
                for r in self._pending.values()
            ],
            "history_count": len(self._history),
            "stats": self.stats(),
        }

    @classmethod
    def from_state(cls, state: dict, db_path: str = ".cache/hitl_gates.db") -> HITLGate:
        """
        Reconstruct a HITLGate from a serialised state dict.

        Restores pending approval records and gate statistics from a checkpoint.
        """
        gate = cls(db_path)

        # Rebuild pending records
        for entry in state.get("pending", []):
            rec = ApprovalRecord(
                gate_id=entry["gate_id"],
                stage=entry["stage"],
                state=GateState(entry["state"]),
                content=entry.get("content", {}),
                question=entry.get("question", ""),
                feedback=entry.get("feedback", ""),
                held_at=entry.get("held_at", time.time()),
                decided_at=entry.get("decided_at"),
                approved_by=entry.get("approved_by"),
                rejected_by=entry.get("rejected_by"),
            )
            gate._pending[rec.gate_id] = rec

        return gate

    def __repr__(self) -> str:
        pending = len(self._pending)
        decided = len(self._history)
        return f"HITLGate(pending={pending}, decided={decided})"
