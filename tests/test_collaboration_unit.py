"""Unit tests for scripts/core/collaboration.py."""

from __future__ import annotations

from scripts.core.collaboration import (
    ConflictResolution,
    Operation,
    OperationType,
    OperationalTransform,
    PaperSnapshot,
    UserPresence,
)


class TestOperationType:
    """Enum values."""

    def test_values(self):
        assert OperationType.INSERT.value == "insert"
        assert OperationType.DELETE.value == "delete"
        assert OperationType.RETAIN.value == "retain"
        assert OperationType.FORMAT.value == "format"
        assert OperationType.SECTION_ADD.value == "section_add"
        assert OperationType.SECTION_REMOVE.value == "section_remove"
        assert OperationType.SECTION_RENAME.value == "section_rename"
        assert OperationType.METADATA_UPDATE.value == "metadata_update"


class TestOperationDataclass:
    """Operation dataclass fields and to_dict."""

    def _op(self, **kwargs):
        defaults = dict(
            op_id="op-1",
            user_id="alice",
            paper_id="p1",
            section="intro",
            op_type=OperationType.INSERT,
            position=0,
        )
        defaults.update(kwargs)
        return Operation(**defaults)

    def test_required_fields(self):
        op = self._op()
        assert op.op_id == "op-1"
        assert op.user_id == "alice"
        assert op.op_type == OperationType.INSERT

    def test_default_content_length(self):
        op = self._op()
        assert op.content == ""
        assert op.length == 0

    def test_default_parent_op_id(self):
        op = self._op()
        assert op.parent_op_id is None

    def test_default_version_zero(self):
        op = self._op()
        assert op.version == 0

    def test_timestamp_set(self):
        op = self._op()
        assert isinstance(op.timestamp, float)

    def test_to_dict(self):
        op = self._op(content="hello", length=5, position=10)
        d = op.to_dict()
        assert d["op_id"] == "op-1"
        assert d["type"] == "insert"
        assert d["content"] == "hello"
        assert d["length"] == 5
        assert d["position"] == 10


class TestUserPresence:
    """UserPresence dataclass."""

    def test_required_fields(self):
        p = UserPresence(user_id="alice", paper_id="p1", section="intro")
        assert p.user_id == "alice"
        assert p.cursor_position == 0

    def test_default_color(self):
        p = UserPresence(user_id="alice", paper_id="p1", section="intro")
        assert p.color.startswith("#")

    def test_default_active(self):
        p = UserPresence(user_id="alice", paper_id="p1", section="intro")
        assert p.is_active is True

    def test_to_dict(self):
        p = UserPresence(user_id="alice", paper_id="p1", section="intro")
        d = p.to_dict()
        assert d["user_id"] == "alice"
        assert d["paper_id"] == "p1"
        assert d["section"] == "intro"


class TestPaperSnapshot:
    """PaperSnapshot dataclass."""

    def test_required_fields(self):
        s = PaperSnapshot(
            version=1,
            paper_id="p1",
            content={"intro": "hello"},
            author_id="alice",
            timestamp=1000.0,
        )
        assert s.version == 1
        assert s.content["intro"] == "hello"
        assert s.message == ""

    def test_to_dict(self):
        s = PaperSnapshot(
            version=2,
            paper_id="p1",
            content={"intro": "hello", "body": "world"},
            author_id="alice",
            timestamp=1000.0,
            message="Initial draft",
        )
        d = s.to_dict()
        assert d["version"] == 2
        assert d["author_id"] == "alice"
        assert "intro" in d["content_keys"]
        assert "body" in d["content_keys"]


class TestConflictResolution:
    """ConflictResolution dataclass."""

    def test_required_fields(self):
        c = ConflictResolution(
            resolved=True,
            winning_version=2,
            losing_version=1,
            resolution_type="last_write_wins",
        )
        assert c.resolved is True
        assert c.resolution_type == "last_write_wins"

    def test_default_collections(self):
        c = ConflictResolution(
            resolved=True, winning_version=1, losing_version=0,
            resolution_type="auto_merge",
        )
        assert c.merged_content is None
        assert c.conflict_regions == []
        assert c.suggestion == ""


class TestOperationalTransformBasic:
    """OT transform on non-overlapping operations."""

    def test_no_overlap_returns_unchanged(self):
        op1 = Operation(
            op_id="1", user_id="a", paper_id="p", section="s",
            op_type=OperationType.INSERT, position=10, content="X",
        )
        op2 = Operation(
            op_id="2", user_id="b", paper_id="p", section="s",
            op_type=OperationType.INSERT, position=20, content="Y",
        )
        o1, o2 = OperationalTransform.transform(op1, op2)
        # Non-overlapping — positions unchanged
        assert o1.position == op1.position
        assert o2.position == op2.position

    def test_two_inserts_at_same_position(self):
        """Both inserts at same position — one shifts."""
        op1 = Operation(
            op_id="1", user_id="a", paper_id="p", section="s",
            op_type=OperationType.INSERT, position=5, content="ABC",
        )
        op2 = Operation(
            op_id="2", user_id="b", paper_id="p", section="s",
            op_type=OperationType.INSERT, position=5, content="XY",
        )
        o1, o2 = OperationalTransform.transform(op1, op2)
        # op1 stays at 5, op2 shifts right by len(op1.content)=3
        assert o1.position == 5
        assert o2.position == 8


class TestOperationalTransformVersions:
    """Transform should bump version numbers."""

    def test_versions_incremented(self):
        op1 = Operation(
            op_id="1", user_id="a", paper_id="p", section="s",
            op_type=OperationType.INSERT, position=5, content="ABC",
        )
        op2 = Operation(
            op_id="2", user_id="b", paper_id="p", section="s",
            op_type=OperationType.INSERT, position=5, content="XY",
        )
        o1, o2 = OperationalTransform.transform(op1, op2)
        assert o1.version == op1.version + 1
        assert o2.version == op2.version + 1


class TestOperationalTransformReturnsTuple:
    """Transform returns tuple of (op1', op2')."""

    def test_returns_tuple(self):
        op1 = Operation(
            op_id="1", user_id="a", paper_id="p", section="s",
            op_type=OperationType.RETAIN, position=0, length=5,
        )
        op2 = Operation(
            op_id="2", user_id="b", paper_id="p", section="s",
            op_type=OperationType.RETAIN, position=0, length=5,
        )
        result = OperationalTransform.transform(op1, op2)
        assert isinstance(result, tuple)
        assert len(result) == 2
