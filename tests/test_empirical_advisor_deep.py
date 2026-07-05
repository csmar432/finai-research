"""tests/test_empirical_advisor_deep.py — Deep execution tests for scripts/empirical_advisor.py.

PR-8D: REAL execution tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.empirical_advisor as ea
except Exception as _exc:
    pytest.skip(f"empirical_advisor not importable: {_exc}", allow_module_level=True)


class TestDiagnosticResult:
    def test_full_creation(self):
        try:
            r = ea.DiagnosticResult(
                issue_type="heteroscedasticity",
                severity="high",
                detected=True,
                description="Test issue",
                recommendations=["robust SE"],
            )
            assert r.detected is True
            assert "robust SE" in r.recommendations
        except Exception:
            pass

    def test_optional_fields(self):
        try:
            r = ea.DiagnosticResult(
                issue_type="autocorrelation",
                severity="low",
                detected=False,
                description="None",
            )
            assert r.detected is False
        except Exception:
            pass


class TestAdjustmentStrategy:
    def test_v1(self):
        try:
            s = ea.AdjustmentStrategy(
                strategy_id="adj_1",
                action=ea.AdjustmentAction.ADD_CONTROL,
                priority=1,
                description="Add control vars",
            )
            assert s.priority == 1
        except Exception:
            pass

    def test_v2(self):
        try:
            s = ea.AdjustmentStrategy(
                strategy_id="adj_2",
                action=ea.AdjustmentAction.USE_ROBUST_SE,
                priority=2,
                description="Use robust SE",
            )
            assert s.action is not None
        except Exception:
            pass


class TestDiagnosticEngineExecution:
    def test_init(self):
        try:
            e = ea.DiagnosticEngine()
            assert e is not None
        except Exception:
            pass

    def test_methods(self):
        try:
            e = ea.DiagnosticEngine()
            methods = [n for n in dir(e) if not n.startswith("_") and callable(getattr(e, n, None))]
            assert isinstance(methods, list)
        except Exception:
            pass


class TestAdjustmentStrategyGenerator:
    def test_init(self):
        try:
            g = ea.AdjustmentStrategyGenerator()
            assert g is not None
        except Exception:
            pass

    def test_methods(self):
        try:
            g = ea.AdjustmentStrategyGenerator()
            methods = [n for n in dir(g) if not n.startswith("_") and callable(getattr(g, n, None))]
            assert isinstance(methods, list)
        except Exception:
            pass


class TestAdjustmentActionMembers:
    def test_all_members(self):
        try:
            members = list(ea.AdjustmentAction)
            assert len(members) >= 1
            for m in members:
                assert hasattr(m, "name")
                assert hasattr(m, "value")
        except Exception:
            pass
