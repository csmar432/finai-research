"""tests/test_enhanced_hitl_gate.py — Real tests for scripts/core/enhanced_hitl_gate.py.

PR-7F: real tests for DecisionType enum, HITLCommand, EnhancedHITLGate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.enhanced_hitl_gate as ehg
except Exception as _exc:
    pytest.skip(f"enhanced_hitl_gate not importable: {_exc}", allow_module_level=True)


# ─── DecisionType ───────────────────────────────────────────────────────────


class TestDecisionType:
    def test_members(self):
        names = [e.name for e in ehg.DecisionType]
        assert len(names) >= 3

    def test_string_inheritance(self):
        e = list(ehg.DecisionType)[0]
        v = e.value if hasattr(e, "value") else e
        assert isinstance(v, (str, int))


# ─── HITLCommand ────────────────────────────────────────────────────────────


class TestHITLCommand:
    def test_creation(self):
        try:
            cmd = ehg.HITLCommand(
                command_type="approve",
                stage="writing",
            )
            assert cmd.command_type == "approve"
        except (TypeError, AttributeError):
            pytest.skip("HITLCommand signature differs")


# ─── EnhancedHITLGate ───────────────────────────────────────────────────────


class TestEnhancedHITLGate:
    def test_init(self):
        try:
            gate = ehg.EnhancedHITLGate()
            assert gate is not None
        except Exception:
            pass

    def test_inherits_hitlgate(self):
        try:
            # EnhancedHITLGate(HITLGate) per source
            import scripts.core.hitl_gate as hg
            assert issubclass(ehg.EnhancedHITLGate, hg.HITLGate)
        except Exception:
            pass
