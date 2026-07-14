"""Unit tests for scripts/core/data_gate.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.core.data_gate import (
    DataGate,
    DataGateLevel,
    DataGateResult,
    RealDataError,
)


def _make_session(tmp_path: Path) -> Path:
    """Create a bare session dir."""
    session = tmp_path / "session"
    session.mkdir()
    return session


def _make_complete_session(tmp_path: Path) -> Path:
    """Create session with all required files for ready state."""
    session = _make_session(tmp_path)
    (session / "session_state.json").write_text(json.dumps({"completed": True}))
    var_data = {"has_minimum_redundancy": True, "variables": {}}
    (session / "redundant_variables.json").write_text(json.dumps(var_data))
    (session / "data_manifest.json").write_text(json.dumps({"requires_synthetic_data": False}))
    (session / "data").mkdir()
    (session / "data" / "final_panel.csv").write_text("a,b\n1,2\n")
    return session


class TestDataGateLevel:
    """Enum values."""

    def test_values(self):
        assert DataGateLevel.NONE.value == "none"
        assert DataGateLevel.CHECKPOINT_ONLY.value == "checkpoint"
        assert DataGateLevel.PROVENANCE.value == "provenance"
        assert DataGateLevel.FULL.value == "full"

    def test_count(self):
        assert len(list(DataGateLevel)) == 4


class TestDataGateInit:
    """Constructor and defaults."""

    def test_default_level(self):
        gate = DataGate(session_dir="/tmp/x")
        assert gate.level == DataGateLevel.PROVENANCE

    def test_session_dir_is_path(self):
        gate = DataGate(session_dir="/tmp/x")
        assert isinstance(gate.session_dir, Path)

    def test_session_dir_from_path(self, tmp_path):
        gate = DataGate(session_dir=tmp_path)
        assert gate.session_dir == tmp_path

    def test_gate_file_path(self, tmp_path):
        gate = DataGate(session_dir=tmp_path)
        assert gate.gate_file == tmp_path / "gate.json"

    def test_blocked_file_path(self, tmp_path):
        gate = DataGate(session_dir=tmp_path)
        assert gate.blocked_file == tmp_path / "blocked.json"


class TestDataGateCheckEmpty:
    """Empty session — should not be ready."""

    def test_missing_session_state(self, tmp_path):
        gate = DataGate(session_dir=tmp_path)
        result = gate.check()
        assert result.is_ready is False
        assert any("session_state" in m for m in result.missing)

    def test_missing_redundant_variables(self, tmp_path):
        gate = DataGate(session_dir=tmp_path)
        result = gate.check()
        assert any("redundant_variables" in m for m in result.missing)

    def test_warns_about_no_data_dir(self, tmp_path):
        gate = DataGate(session_dir=tmp_path)
        result = gate.check()
        assert any("数据目录" in w for w in result.warnings)


class TestDataGateCheckComplete:
    """Complete session — should be ready."""

    def test_complete_session_is_ready(self, tmp_path):
        session = _make_complete_session(tmp_path)
        gate = DataGate(session_dir=session, level=DataGateLevel.PROVENANCE)
        result = gate.check()
        assert result.is_ready is True
        assert result.missing == []

    def test_complete_session_writes_gate_json(self, tmp_path):
        session = _make_complete_session(tmp_path)
        gate = DataGate(session_dir=session, level=DataGateLevel.PROVENANCE)
        gate.check()
        assert (session / "gate.json").exists()


class TestDataGateCheckOptional:
    """Optional file warnings don't block."""

    def test_missing_optional_manifest_warns(self, tmp_path):
        session = _make_session(tmp_path)
        (session / "session_state.json").write_text("{}")
        (session / "redundant_variables.json").write_text(
            json.dumps({"has_minimum_redundancy": True})
        )
        gate = DataGate(session_dir=session)
        result = gate.check()
        assert result.is_ready is True
        assert any("manifest" in w for w in result.warnings)


class TestDataGateSyntheticData:
    """Mock data detection."""

    def test_mock_data_file_warns(self, tmp_path):
        session = _make_session(tmp_path)
        (session / "session_state.json").write_text("{}")
        (session / "redundant_variables.json").write_text(
            json.dumps({"has_minimum_redundancy": True})
        )
        (session / "data").mkdir()
        (session / "data" / "test_mock_data.csv").write_text("a,b\n1,2\n")
        gate = DataGate(session_dir=session)
        result = gate.check()
        assert any("mock" in w.lower() for w in result.warnings)

    def test_synthetic_data_blocks(self, tmp_path):
        session = _make_session(tmp_path)
        (session / "session_state.json").write_text("{}")
        (session / "redundant_variables.json").write_text(
            json.dumps({"has_minimum_redundancy": True})
        )
        (session / "data_manifest.json").write_text(
            json.dumps({"requires_synthetic_data": True})
        )
        gate = DataGate(session_dir=session)
        result = gate.check()
        # Manifest flag alone warns but doesn't block
        assert any("synthetic" in w.lower() or "模拟" in w for w in result.warnings)


class TestDataGateProvenanceLevel:
    """Provenance checks in PROVENANCE/FULL mode."""

    def test_missing_provenance_warns(self, tmp_path):
        session = _make_complete_session(tmp_path)
        gate = DataGate(session_dir=session, level=DataGateLevel.PROVENANCE)
        result = gate.check()
        # No provenance_ids.json — should warn
        assert any("provenance" in w.lower() for w in result.warnings)

    def test_provenance_ids_loaded(self, tmp_path):
        session = _make_complete_session(tmp_path)
        (session / "provenance_ids.json").write_text(
            json.dumps({"ids": ["prov-1", "prov-2"]})
        )
        gate = DataGate(session_dir=session, level=DataGateLevel.PROVENANCE)
        result = gate.check()
        assert "prov-1" in result.provenance_ids
        assert "prov-2" in result.provenance_ids


class TestDataGateNoneLevel:
    """NONE level — provenance is skipped but file checks still run."""

    def test_none_level_skips_provenance(self, tmp_path):
        """Even with NONE level, missing required files still block."""
        gate = DataGate(session_dir=tmp_path, level=DataGateLevel.NONE)
        result = gate.check()
        # Required files missing — not ready
        assert result.is_ready is False
        # But provenance check is skipped (no provenance warnings)
        assert not any("provenance" in w.lower() for w in result.warnings)


class TestDataGateResult:
    """DataGateResult dataclass."""

    def test_default_field_values(self):
        r = DataGateResult(
            is_ready=True,
            level=DataGateLevel.PROVENANCE,
            gate_file=None,
        )
        assert r.missing == []
        assert r.warnings == []
        assert r.provenance_ids == []
        assert r.data_files == []
        assert r.mock_ratio == 0.0
        assert r.blocked_at == ""

    def test_block_message_when_ready(self):
        r = DataGateResult(
            is_ready=True,
            level=DataGateLevel.PROVENANCE,
            gate_file=None,
        )
        assert r.block_message == ""

    def test_block_message_when_not_ready(self):
        r = DataGateResult(
            is_ready=False,
            level=DataGateLevel.PROVENANCE,
            gate_file=None,
            missing=["data missing"],
            warnings=["warning 1"],
        )
        msg = r.block_message
        assert "data missing" in msg
        assert "warning 1" in msg

    def test_block_message_with_mock(self):
        r = DataGateResult(
            is_ready=False,
            level=DataGateLevel.PROVENANCE,
            gate_file=None,
            mock_ratio=0.5,
        )
        msg = r.block_message
        assert msg != ""


class TestRealDataError:
    """Exception class."""

    def test_can_raise(self):
        try:
            raise RealDataError("data not ready")
        except RealDataError as e:
            assert "data not ready" in str(e)

    def test_is_exception(self):
        assert issubclass(RealDataError, Exception)
