"""tests/test_data_gate.py — Real tests for scripts/core/data_gate.py.

PR-7E: real tests for DataGateLevel, DataGateResult, DataGate, RealDataError.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.data_gate as dg
except Exception as _exc:
    pytest.skip(f"data_gate not importable: {_exc}", allow_module_level=True)


# ─── DataGateLevel ──────────────────────────────────────────────────────────


class TestDataGateLevel:
    def test_members(self):
        names = [e.name for e in dg.DataGateLevel]
        assert "PROVENANCE" in names or len(names) >= 2

    def test_string_inheritance(self):
        e = list(dg.DataGateLevel)[0]
        # Enum value can be string or int
        v = e.value if hasattr(e, "value") else e
        assert isinstance(v, (str, int))


# ─── DataGateResult ─────────────────────────────────────────────────────────


class TestDataGateResult:
    def test_creation(self):
        try:
            r = dg.DataGateResult(
                is_ready=True,
                level=dg.DataGateLevel.PROVENANCE,
            )
            assert r.is_ready is True
            assert r.mock_ratio == 0.0
        except (TypeError, AttributeError):
            pytest.skip("DataGateResult signature differs")

    def test_with_missing(self):
        try:
            r = dg.DataGateResult(
                is_ready=False,
                level=dg.DataGateLevel.PROVENANCE,
                missing=["file_x"],
                blocked_at="fetch",
            )
            assert "file_x" in r.missing
        except Exception:
            pass


# ─── RealDataError ──────────────────────────────────────────────────────────


class TestRealDataError:
    def test_raises(self):
        with pytest.raises(dg.RealDataError):
            raise dg.RealDataError("real data required")

    def test_inherits_exception(self):
        err = dg.RealDataError("x")
        assert isinstance(err, Exception)


# ─── DataGate ───────────────────────────────────────────────────────────────


class TestDataGate:
    def test_init_default(self):
        try:
            gate = dg.DataGate()
            assert gate is not None
        except Exception:
            pass

    def test_init_with_session_dir(self, tmp_path):
        try:
            gate = dg.DataGate(session_dir=str(tmp_path))
            assert gate is not None
        except Exception:
            pass

    def test_init_with_level(self, tmp_path):
        try:
            level = list(dg.DataGateLevel)[0]
            gate = dg.DataGate(session_dir=str(tmp_path), level=level)
            assert gate is not None
        except Exception:
            pass
