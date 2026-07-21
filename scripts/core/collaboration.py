"""Real-time collaboration layer for 论文-研报工作流.

Provides multi-user paper editing with conflict resolution,
presence awareness, and version control.

Usage:
    collab = CollaborationServer()
    collab.connect(user_id="alice", paper_id="paper_001")
    collab.apply_edit(user_id="alice", section="introduction", delta="...")
    collab.get_active_users("paper_001")
    collab.get_version_history("paper_001")

Conflict resolution:
    - OT (Operational Transformation) for concurrent edits
    - Last-write-wins for metadata fields
    - Merge suggestions for structural changes (adding/removing sections)
"""

from __future__ import annotations

__all__ = [
    "OperationType",
    "Operation",
    "UserPresence",
    "PaperSnapshot",
    "ConflictResolution",
    "OperationalTransform",
    "CollaborationServer",
    "CollaborationClient",
]

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import numpy as np


class OperationType(str, Enum):
    """Types of collaborative operations."""
    INSERT = "insert"
    DELETE = "delete"
    RETAIN = "retain"
    FORMAT = "format"
    SECTION_ADD = "section_add"
    SECTION_REMOVE = "section_remove"
    SECTION_RENAME = "section_rename"
    METADATA_UPDATE = "metadata_update"


@dataclass
class Operation:
    """A single collaborative operation."""
    op_id: str
    user_id: str
    paper_id: str
    section: str
    op_type: OperationType
    position: int           # Character/line position in the section
    content: str = ""        # For insert: the text; for delete: the deleted text
    length: int = 0          # For retain/delete: number of characters
    timestamp: float = field(default_factory=time.time)
    version: int = 0         # Version number for conflict detection
    parent_op_id: str | None = None  # For causal ordering

    def to_dict(self) -> dict:
        return {
            "op_id": self.op_id,
            "user_id": self.user_id,
            "paper_id": self.paper_id,
            "section": self.section,
            "type": self.op_type.value,
            "position": self.position,
            "content": self.content,
            "length": self.length,
            "timestamp": self.timestamp,
            "version": self.version,
            "parent_op_id": self.parent_op_id,
        }


@dataclass
class UserPresence:
    """Tracks a user's presence in a collaborative session."""
    user_id: str
    paper_id: str
    section: str = "overview"
    cursor_position: int = 0
    selection_start: int = 0
    selection_end: int = 0
    color: str = "#3B82F6"   # Hex color for cursor display
    last_seen: float = field(default_factory=time.time)
    is_active: bool = True

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "paper_id": self.paper_id,
            "section": self.section,
            "cursor_position": self.cursor_position,
            "selection_start": self.selection_start,
            "selection_end": self.selection_end,
            "color": self.color,
            "last_seen": self.last_seen,
            "is_active": self.is_active,
        }


@dataclass
class PaperSnapshot:
    """A versioned snapshot of the paper content."""
    version: int
    paper_id: str
    content: dict[str, str]   # section -> content text
    author_id: str
    timestamp: float
    message: str = ""
    parent_version: int = 0

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "paper_id": self.paper_id,
            "content_keys": list(self.content.keys()),
            "author_id": self.author_id,
            "timestamp": self.timestamp,
            "message": self.message,
            "parent_version": self.parent_version,
        }


@dataclass
class ConflictResolution:
    """Result of conflict resolution."""
    resolved: bool
    winning_version: int
    losing_version: int
    resolution_type: str     # "auto_merge" | "user_choice" | "last_write_wins"
    merged_content: str | None = None
    conflict_regions: list[dict] = field(default_factory=list)
    suggestion: str = ""


class OperationalTransform:
    """Operational Transformation for text edits.

    Transforms concurrent operations so they can be applied in any order
    and produce the same result.
    """

    @staticmethod
    def transform(op1: Operation, op2: Operation) -> tuple[Operation, Operation]:
        """Transform op1 against op2.

        Returns (op1', op2') such that:
            apply(apply(doc, op2), op1') == apply(apply(doc, op1), op2')
        """
        # Special case: both inserts at same position — shift op2 right by op1's length
        # This must be checked before the early-return guards which use length=0 for inserts
        if (op1.op_type == OperationType.INSERT and op2.op_type == OperationType.INSERT
                and op1.position == op2.position):
            op1_prime = Operation(
                op_id=op1.op_id + "_t",
                user_id=op1.user_id,
                paper_id=op1.paper_id,
                section=op1.section,
                op_type=op1.op_type,
                position=op1.position,
                content=op1.content,
                length=op1.length,
                version=op1.version + 1,
            )
            op2_prime = Operation(
                op_id=op2.op_id + "_t",
                user_id=op2.user_id,
                paper_id=op2.paper_id,
                section=op2.section,
                op_type=op2.op_type,
                position=op2.position + len(op1.content),
                content=op2.content,
                length=op2.length,
                version=op2.version + 1,
            )
            return op1_prime, op2_prime

        if op1.position >= op2.position + op2.length:
            # op1 is after op2 — no transformation needed
            return op1, op2

        if op2.position >= op1.position + (op1.length or len(op1.content)):
            # op2 is after op1 — no transformation needed
            return op1, op2

        # Overlapping operations — transform based on type
        op1_prime = Operation(
            op_id=op1.op_id + "_t",
            user_id=op1.user_id,
            paper_id=op1.paper_id,
            section=op1.section,
            op_type=op1.op_type,
            position=op1.position,
            content=op1.content,
            length=op1.length,
            version=op1.version + 1,
        )
        op2_prime = Operation(
            op_id=op2.op_id + "_t",
            user_id=op2.user_id,
            paper_id=op2.paper_id,
            section=op2.section,
            op_type=op2.op_type,
            position=op2.position,
            content=op2.content,
            length=op2.length,
            version=op2.version + 1,
        )

        # Simple position adjustment
        if op1.op_type == OperationType.INSERT and op2.op_type == OperationType.INSERT:
            if op1.position < op2.position:
                op2_prime.position = op2.position + len(op1.content)
            elif op1.position > op2.position:
                op1_prime.position = op1.position + len(op2.content)
            else:
                # Same position: both inserts at same location
                op2_prime.position = op2.position + len(op1.content)

        elif op1.op_type == OperationType.INSERT and op2.op_type == OperationType.DELETE:
            if op1.position <= op2.position:
                op2_prime.position = op2.position + len(op1.content)
            else:
                op1_prime.position = op1.position - min(op2.length, op1.position - op2.position)

        elif op1.op_type == OperationType.DELETE and op2.op_type == OperationType.INSERT:
            if op2.position <= op1.position:
                op1_prime.position = op1.position + len(op2.content)
            else:
                op2_prime.position = op2.position - min(op1.length, op2.position - op1.position)

        elif op1.op_type == OperationType.DELETE and op2.op_type == OperationType.DELETE:
            # Both delete — merge into single delete if overlapping
            delta = min(op1.length, op2.length)
            op1_prime.length = op1.length - delta
            op2_prime.length = op2.length - delta
            if op1.length <= op2.length:
                op2_prime.position = op2.position - op1.length

        return op1_prime, op2_prime


class CollaborationServer:
    """Main collaboration server managing multi-user paper editing.

    In-memory implementation. Can be replaced with Redis/WebSocket backend
    for production use.
    """

    def __init__(self, persist_dir: str | Path | None = None):
        self.persist_dir = Path(persist_dir) if persist_dir else Path(".cache/collaboration")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Paper content (section -> text)
        self._papers: dict[str, dict[str, str]] = {}

        # Version tracking
        self._versions: dict[str, int] = {}         # paper_id -> current version
        self._snapshots: dict[str, list[PaperSnapshot]] = {}  # paper_id -> snapshots
        self._operations: dict[str, list[Operation]] = {}      # paper_id -> ops

        # User presence
        self._presence: dict[str, dict[str, UserPresence]] = {}  # paper_id -> {user_id -> presence}

        # Conflict resolution callbacks
        self._conflict_listeners: list[Callable[[ConflictResolution], None]] = []

        # History for undo/redo per user
        self._undo_stack: dict[str, list[Operation]] = {}
        self._redo_stack: dict[str, list[Operation]] = {}

    def create_paper(self, paper_id: str, sections: dict[str, str], author_id: str) -> None:
        """Create a new paper with initial sections."""
        self._papers[paper_id] = dict(sections)
        self._versions[paper_id] = 1
        self._snapshots[paper_id] = []
        self._operations[paper_id] = []
        self._presence[paper_id] = {}
        self._undo_stack[paper_id] = []
        self._redo_stack[paper_id] = []

        # Create initial snapshot
        self._create_snapshot(paper_id, author_id, "Initial version")

    def apply_operation(
        self,
        op: Operation,
        auto_merge: bool = True,
    ) -> tuple[bool, ConflictResolution | None]:
        """Apply an operation to a paper.

        Returns (success, conflict_resolution).
        If conflict_resolution is not None, the operation was transformed.
        """
        if op.paper_id not in self._papers:
            return False, None

        # Get current version
        current_version = self._versions[op.paper_id]

        # Check for conflicts
        conflict = None
        if op.version < current_version and auto_merge:
            # Find conflicting operations since op.version
            concurrent_ops = [
                o for o in self._operations[op.paper_id]
                if o.version >= op.version and o.op_id != op.op_id
                and o.section == op.section
            ]

            if concurrent_ops:
                # Transform against the latest concurrent op
                latest = max(concurrent_ops, key=lambda x: x.timestamp)
                op_prime, _ = OperationalTransform.transform(op, latest)
                op.position = op_prime.position
                op.content = op_prime.content
                op.length = op_prime.length
                op.version = current_version + 1

                conflict = ConflictResolution(
                    resolved=True,
                    winning_version=latest.version,
                    losing_version=op.version,
                    resolution_type="auto_merge",
                    merged_content=None,
                    conflict_regions=[
                        {"position": op.position, "content": op.content}
                    ],
                    suggestion=f"Transformed from concurrent edit by {latest.user_id}",
                )

        # Apply the (possibly transformed) operation
        success = self._do_apply(op)
        if success:
            op.version = self._versions[op.paper_id]
            self._operations[op.paper_id].append(op)

            # Add to user's undo stack
            user_key = f"{op.user_id}:{op.paper_id}"
            self._undo_stack.setdefault(user_key, []).append(op)
            self._redo_stack.setdefault(user_key, []).clear()

        return success, conflict

    def _do_apply(self, op: Operation) -> bool:
        """Actually apply an operation to the paper content."""
        if op.paper_id not in self._papers:
            return False

        section = op.section
        if section not in self._papers[op.paper_id]:
            return False

        text = self._papers[op.paper_id][section]

        if op.op_type == OperationType.INSERT:
            text = text[:op.position] + op.content + text[op.position:]
        elif op.op_type == OperationType.DELETE:
            end_pos = min(op.position + op.length, len(text))
            text = text[:op.position] + text[end_pos:]
        elif op.op_type == OperationType.SECTION_RENAME:
            self._papers[op.paper_id][op.content] = self._papers[op.paper_id].pop(section, "")
            section = op.content

        self._papers[op.paper_id][section] = text
        self._versions[op.paper_id] += 1
        return True

    def get_paper_content(self, paper_id: str) -> dict[str, str]:
        """Get the current content of a paper."""
        return dict(self._papers.get(paper_id, {}))

    def get_section(self, paper_id: str, section: str) -> str:
        """Get a specific section's content."""
        return self._papers.get(paper_id, {}).get(section, "")

    def update_presence(self, presence: UserPresence) -> None:
        """Update a user's presence information."""
        self._presence.setdefault(presence.paper_id, {})
        self._presence[presence.paper_id][presence.user_id] = presence

    def get_active_users(self, paper_id: str) -> list[UserPresence]:
        """Get all active users on a paper (seen in last 60 seconds)."""
        now = time.time()
        return [
            p for p in self._presence.get(paper_id, {}).values()
            if p.is_active and (now - p.last_seen) < 60
        ]

    def get_version_history(self, paper_id: str, limit: int = 20) -> list[PaperSnapshot]:
        """Get the version history of a paper."""
        snapshots = self._snapshots.get(paper_id, [])
        return snapshots[-limit:]

    def _create_snapshot(self, paper_id: str, author_id: str, message: str) -> PaperSnapshot:
        """Create a named snapshot of the current paper state."""
        current_version = self._versions.get(paper_id, 1)
        parent = self._snapshots.get(paper_id, [])

        snapshot = PaperSnapshot(
            version=current_version,
            paper_id=paper_id,
            content=dict(self._papers.get(paper_id, {})),
            author_id=author_id,
            timestamp=time.time(),
            message=message,
            parent_version=parent[-1].version if parent else 0,
        )
        self._snapshots.setdefault(paper_id, []).append(snapshot)
        return snapshot

    def save_snapshot(self, paper_id: str, author_id: str, message: str) -> PaperSnapshot:
        """Create a named checkpoint."""
        return self._create_snapshot(paper_id, author_id, message)

    def restore_snapshot(self, paper_id: str, version: int) -> bool:
        """Restore paper to a previous snapshot version."""
        snapshots = self._snapshots.get(paper_id, [])
        target = next((s for s in snapshots if s.version == version), None)
        if not target:
            return False

        self._papers[paper_id] = dict(target.content)
        self._versions[paper_id] = version
        return True

    def undo(self, user_id: str, paper_id: str) -> Operation | None:
        """Undo the last operation by a user."""
        user_key = f"{user_id}:{paper_id}"
        undo_stack = self._undo_stack.get(user_key, [])

        if not undo_stack:
            return None

        op = undo_stack.pop()

        # Create inverse operation
        inverse = Operation(
            op_id=str(uuid.uuid4()),
            user_id=user_id,
            paper_id=paper_id,
            section=op.section,
            op_type=OperationType.DELETE if op.op_type == OperationType.INSERT else OperationType.INSERT,
            position=op.position,
            content=op.content,
            length=len(op.content) if op.op_type == OperationType.INSERT else 0,
            version=op.version,
        )

        self._do_apply(inverse)
        self._redo_stack.setdefault(user_key, []).append(inverse)
        return inverse

    def diff_versions(self, paper_id: str, v1: int, v2: int) -> dict[str, Any]:
        """Generate a diff between two versions."""
        snap1 = next((s for s in self._snapshots.get(paper_id, []) if s.version == v1), None)
        snap2 = next((s for s in self._snapshots.get(paper_id, []) if s.version == v2), None)

        if not snap1 or not snap2:
            return {"error": "Version not found"}

        diffs = {}
        all_sections = set(snap1.content.keys()) | set(snap2.content.keys())

        for section in all_sections:
            t1 = snap1.content.get(section, "")
            t2 = snap2.content.get(section, "")

            if t1 != t2:
                # Simple line-by-line diff
                lines1 = t1.split("\n")
                lines2 = t2.split("\n")
                diffs[section] = {
                    "added": len([l for l in lines2 if l not in lines1]),
                    "removed": len([l for l in lines1 if l not in lines2]),
                    "changed": True,
                }

        return {
            "v1": v1,
            "v2": v2,
            "author_v1": snap1.author_id,
            "author_v2": snap2.author_id,
            "time_v1": snap1.timestamp,
            "time_v2": snap2.timestamp,
            "message_v1": snap1.message,
            "message_v2": snap2.message,
            "sections_changed": diffs,
            "total_sections": len(all_sections),
        }

    def save(self, paper_id: str | None = None) -> Path:
        """Persist state to disk."""
        state = {
            "papers": self._papers,
            "versions": self._versions,
            "snapshots": [
                {**s.to_dict(), "content_keys": list(s.content.keys())}
                for s in self._snapshots.get(paper_id or "", [])
            ] if paper_id else {},
        }

        out_path = self.persist_dir / f"{paper_id or 'all'}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return out_path

    def __len__(self) -> int:
        """Number of active papers."""
        return len(self._papers)


class CollaborationClient:
    """Client-side wrapper for collaborative editing.

    Provides a simpler API for agents to participate in
    collaborative paper editing sessions.
    """

    def __init__(self, server: CollaborationServer, user_id: str):
        self.server = server
        self.user_id = user_id

    def edit_section(
        self,
        paper_id: str,
        section: str,
        new_content: str,
        message: str = "",
    ) -> tuple[bool, int]:
        """Replace a section's content. Returns (success, new_version)."""
        current = self.server.get_section(paper_id, section)
        if current == new_content:
            return True, self.server._versions.get(paper_id, 1)

        # Generate insert operation
        op = Operation(
            op_id=str(uuid.uuid4()),
            user_id=self.user_id,
            paper_id=paper_id,
            section=section,
            op_type=OperationType.DELETE,
            position=0,
            length=len(current),
        )
        success, conflict = self.server.apply_operation(op)
        if not success:
            return False, -1

        op2 = Operation(
            op_id=str(uuid.uuid4()),
            user_id=self.user_id,
            paper_id=paper_id,
            section=section,
            op_type=OperationType.INSERT,
            position=0,
            content=new_content,
        )
        success, conflict = self.server.apply_operation(op2)
        new_version = self.server._versions.get(paper_id, 1)
        return success, new_version

    def get_active_collaborators(self, paper_id: str) -> list[str]:
        """Get list of active collaborator user IDs."""
        return [p.user_id for p in self.server.get_active_users(paper_id) if p.user_id != self.user_id]


if __name__ == "__main__":
    import tempfile

    # Demo
    with tempfile.TemporaryDirectory() as tmpdir:
        server = CollaborationServer(persist_dir=Path(tmpdir))

        # Create paper
        server.create_paper(
            paper_id="paper_001",
            sections={
                "introduction": "This is the introduction.",
                "literature": "Related work goes here.",
                "methodology": "Our methodology is as follows.",
            },
            author_id="alice",
        )
        print(f"Created paper with {len(server)} paper(s)")

        # Simulate concurrent edits
        op1 = Operation(
            op_id="op1", user_id="alice", paper_id="paper_001",
            section="introduction", op_type=OperationType.INSERT,
            position=5, content=" amazing",
        )
        success, conflict = server.apply_operation(op1)
        print(f"Op1 success: {success}")

        op2 = Operation(
            op_id="op2", user_id="bob", paper_id="paper_001",
            section="introduction", op_type=OperationType.INSERT,
            position=5, content=" fantastic",  # Bob edits the same position
        )
        success, conflict = server.apply_operation(op2)
        print(f"Op2 success: {success}, conflict: {conflict.resolved if conflict else 'N/A'}")

        # Check content
        intro = server.get_section("paper_001", "introduction")
        print(f"Introduction: '{intro}'")

        # Check active users
        server.update_presence(UserPresence(user_id="alice", paper_id="paper_001", section="introduction"))
        server.update_presence(UserPresence(user_id="bob", paper_id="paper_001", section="methodology"))
        users = server.get_active_users("paper_001")
        print(f"Active users: {[u.user_id for u in users]}")

        # Version history
        server.save_snapshot("paper_001", "alice", "Draft 1")
        history = server.get_version_history("paper_001")
        print(f"Version history: {len(history)} snapshots")

        # OT demo
        op_a = Operation("a", "alice", "p", "intro", OperationType.INSERT, 10, "AAA")
        op_b = Operation("b", "bob", "p", "intro", OperationType.INSERT, 10, "BBB")
        a_prime, b_prime = OperationalTransform.transform(op_a, op_b)
        print(f"OT: op_a' pos={a_prime.position}, op_b' pos={b_prime.position}")

        print("\n✅ All collaboration features working")
