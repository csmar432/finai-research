"""Unit tests for scripts/empirical_agent.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ea():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import empirical_agent as e
    yield e
    if _p in sys.path:
        sys.path.remove(_p)


class TestAdjustmentAction:
    def test_init(self, ea):
        a = ea.AdjustmentAction(
            level="LEVEL_1_CONTROL_VARS",
            action_type="add_controls",
            description="Add firm size",
            specific_changes=["+firm_size"],
            expected_impact="Reduce omitted variable bias",
            priority=1,
        )
        assert a.action_type == "add_controls"
        assert a.priority == 1


class TestDiagnosticResult:
    def test_init(self, ea):
        d = ea.DiagnosticResult(
            cause="Omitted variable bias",
            confidence=0.85,
            evidence=["R² jumps with controls"],
            recommendation="Add firm-level controls",
            suggested_adjustment="LEVEL_1_CONTROL_VARS",
        )
        assert d.cause == "Omitted variable bias"
        assert d.suggested_model_switch is None


class TestEvaluationResult:
    def test_init(self, ea):
        r = ea.EvaluationResult(
            is_significant=True,
            best_significance_level="1%",
            core_variable_result={"coef": 0.15, "pval": 0.005},
            diagnostics={},
            adjustment_plan=[],
            model_switch_recommendation=None,
            recommendation="Continue",
            action_plan=["Re-estimate with controls"],
            research_note="Strong effect",
        )
        assert r.is_significant is True
        assert r.max_attempts == 3


class TestRegressionRun:
    def test_init(self, ea):
        r = ea.RegressionRun(
            stage="baseline",
            model_type="OLS",
            description="Baseline regression",
            formula="y ~ x",
            controls=["firm_size"],
            fixed_effects=["firm_id"],
            se_type="cluster",
        )
        assert r.model_type == "OLS"
        assert r.is_significant is False
        assert r.pval == 1.0
