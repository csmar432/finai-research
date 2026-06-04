"""
Tests for econometrics_rules.py and its integration with halt_rules_registry.py.
"""

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from scripts.core.econometrics_rules import (
    ValidationResult,
    DIDValidator,
    WeakInstrumentTest,
    BalanceTestValidator,
    HeteroskedasticityTest,
    EconometricsRuleEngine,
)
from scripts.core.halt_rules_registry import HaltRulesRegistry


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def np_rng():
    """Seeded numpy random state for reproducibility."""
    return np.random.default_rng(seed=42)


@pytest.fixture
def registry():
    """HaltRulesRegistry pointing to the project's config dir."""
    return HaltRulesRegistry(rules_dir=PROJECT_ROOT / "config" / "halt_rules")


# ═══════════════════════════════════════════════════════════════════
# Test 1: ValidationResult
# ═══════════════════════════════════════════════════════════════════


def test_validation_result():
    """Create ValidationResult, add warnings/errors, verify summary()."""
    vr = ValidationResult(passed=True)

    assert vr.passed is True
    assert vr.warnings == []
    assert vr.errors == []

    vr.add_warning("Sample size is small (n=50)")
    assert len(vr.warnings) == 1
    assert "small" in vr.warnings[0]

    vr.add_error("Parallel trend test failed (p=0.03)")
    assert vr.passed is False
    assert len(vr.errors) == 1
    assert "failed" in vr.errors[0]

    summary = vr.summary()
    assert "FAIL" in summary
    assert "WARN" in summary
    assert "small" in summary


# ═══════════════════════════════════════════════════════════════════
# Test 2: DIDValidator — parallel trend PASS
# ═══════════════════════════════════════════════════════════════════


def test_did_validator_parallel_trend_pass(np_rng):
    """
    Synthetic data where pre-treatment coefficients are close to zero
    and not jointly significant → should PASS.
    """
    # Periods: -3, -2, -1, 0, 1, 2, 3
    periods = [-3, -2, -1, 0, 1, 2, 3]
    # Pre-treatment: coefficients ≈ 0, standard errors relatively large → not significant
    coefs = [0.01, 0.02, 0.005, 0.12, 0.15, 0.13, 0.11]
    ses = [0.08, 0.07, 0.06, 0.05, 0.06, 0.07, 0.08]

    event_df = pd.DataFrame({"period": periods, "coef": coefs, "se": ses})

    validator = DIDValidator()
    result = validator.check_parallel_trend(event_df, pre_periods=3, alpha=0.1)

    assert result["passed"] is True
    assert result["p_value"] > 0.1
    assert not result["joint_reject_null"]
    assert "平行趋势" in result["issues"][0] or "passed" in str(result["issues"])


# ═══════════════════════════════════════════════════════════════════
# Test 3: DIDValidator — parallel trend FAIL
# ═══════════════════════════════════════════════════════════════════


def test_did_validator_parallel_trend_fail(np_rng):
    """
    Synthetic data where a pre-treatment coefficient is significantly
    negative → should FAIL parallel trend test.
    """
    periods = [-3, -2, -1, 0, 1, 2, 3]
    # Period -1 is significantly negative: coef = -0.15, se = 0.05 → t = -3
    coefs = [0.01, 0.02, -0.15, 0.12, 0.15, 0.13, 0.11]
    ses = [0.08, 0.07, 0.05, 0.05, 0.06, 0.07, 0.08]

    event_df = pd.DataFrame({"period": periods, "coef": coefs, "se": ses})

    validator = DIDValidator()
    result = validator.check_parallel_trend(event_df, pre_periods=3, alpha=0.1)

    assert result["passed"] == False
    assert result["p_value"] < 0.1 or result["joint_reject_null"]


# ═══════════════════════════════════════════════════════════════════
# Test 4: WeakInstrumentTest — strong instrument
# ═══════════════════════════════════════════════════════════════════


def test_weak_instrument_strong(np_rng):
    """
    Strong instrument: F-stat > 19.93 (Stock-Yogo 5% bias) → should PASS.
    """
    n = 500
    # Two instruments that strongly predict X
    Z = np.column_stack([
        np_rng.normal(0, 1, n),
        np_rng.normal(0, 1, n),
    ])
    X = 1.5 * Z[:, 0] + 0.8 * Z[:, 1] + np_rng.normal(0, 0.3, n)

    tester = WeakInstrumentTest()
    result = tester.first_stage_f_stat(X, Z)

    assert result["f_stat"] > 19.93, f"F-stat={result['f_stat']:.2f} should be > 19.93"
    assert result["is_weak"] is False
    assert result["is_weak_by_sy"] is False
    assert "强工具变量" in result["interpretation"]


# ═══════════════════════════════════════════════════════════════════
# Test 5: WeakInstrumentTest — weak instrument
# ═══════════════════════════════════════════════════════════════════


def test_weak_instrument_weak(np_rng):
    """
    Weak instrument: F-stat < 10.38 → should FAIL.
    """
    n = 300
    # Instruments barely related to X → weak first stage
    Z = np.column_stack([
        np_rng.normal(0, 1, n),
        np_rng.normal(0, 1, n),
    ])
    X = 0.2 * Z[:, 0] + 0.1 * Z[:, 1] + np_rng.normal(0, 2.0, n)

    tester = WeakInstrumentTest()
    result = tester.first_stage_f_stat(X, Z)

    assert result["is_weak"] is True
    assert result["f_stat"] < 10.38


# ═══════════════════════════════════════════════════════════════════
# Test 6: BalanceTestValidator — PASS
# ═══════════════════════════════════════════════════════════════════


def test_balance_test_pass(np_rng):
    """
    Matched data where SMD < 0.1 for all covariates → should PASS.
    """
    n_treat = 200
    n_ctrl = 300

    treat_df = pd.DataFrame({
        "treatment": [1] * n_treat,
        "size": np_rng.normal(22.0, 1.5, n_treat),
        "lev": np_rng.normal(0.50, 0.15, n_treat),
        "roe": np_rng.normal(0.10, 0.04, n_treat),
    })
    ctrl_df = pd.DataFrame({
        "treatment": [0] * n_ctrl,
        "size": np_rng.normal(22.0, 1.5, n_ctrl),
        "lev": np_rng.normal(0.50, 0.15, n_ctrl),
        "roe": np_rng.normal(0.10, 0.04, n_ctrl),
    })
    matched = pd.concat([treat_df, ctrl_df], ignore_index=True)

    validator = BalanceTestValidator()
    result = validator.check_balance(
        matched,
        variables=["size", "lev", "roe"],
        treatment_col="treatment",
        threshold=0.1,
    )

    assert result["passed"] == True
    assert result["max_abs_bias"] < 0.1
    assert result["imbalance_vars"] == []


# ═══════════════════════════════════════════════════════════════════
# Test 7: BalanceTestValidator — FAIL
# ═══════════════════════════════════════════════════════════════════


def test_balance_test_fail(np_rng):
    """
    Matched data where at least one SMD > 0.2 → should FAIL.
    """
    n_treat = 200
    n_ctrl = 300

    # 'size' has large imbalance: treated mean ≈ 23.5, control mean ≈ 21.5
    treat_df = pd.DataFrame({
        "treatment": [1] * n_treat,
        "size": np_rng.normal(23.5, 1.5, n_treat),  # intentionally higher
        "lev": np_rng.normal(0.50, 0.15, n_treat),
        "roe": np_rng.normal(0.10, 0.04, n_treat),
    })
    ctrl_df = pd.DataFrame({
        "treatment": [0] * n_ctrl,
        "size": np_rng.normal(21.5, 1.5, n_ctrl),
        "lev": np_rng.normal(0.50, 0.15, n_ctrl),
        "roe": np_rng.normal(0.10, 0.04, n_ctrl),
    })
    matched = pd.concat([treat_df, ctrl_df], ignore_index=True)

    validator = BalanceTestValidator()
    result = validator.check_balance(
        matched,
        variables=["size", "lev", "roe"],
        treatment_col="treatment",
        threshold=0.1,
    )

    assert result["passed"] == False
    assert result["max_abs_bias"] > 0.2
    assert "size" in result["imbalance_vars"]


# ═══════════════════════════════════════════════════════════════════
# Test 8: HeteroskedasticityTest — Breusch-Pagan
# ═══════════════════════════════════════════════════════════════════


def test_heteroskedasticity_bp(np_rng):
    """
    Run Breusch-Pagan test and verify it returns a result dict
    with the expected keys.
    """
    n = 500
    X = np.column_stack([
        np_rng.normal(0, 1, n),
        np_rng.normal(0, 1, n),
        np_rng.normal(0, 1, n),
    ])
    # Heteroskedastic residuals: variance increases with X[:, 0]
    residuals = np_rng.normal(0, 1, n) * (1.0 + 0.5 * X[:, 0])

    tester = HeteroskedasticityTest()
    result = tester.breusch_pagan(residuals, X)

    assert "bp_stat" in result
    assert "p_value" in result
    assert "has_heteroskedasticity" in result
    assert result["bp_stat"] is not None
    assert result["p_value"] is not None
    assert isinstance(result["has_heteroskedasticity"], bool)


# ═══════════════════════════════════════════════════════════════════
# Test 9: EconometricsRuleEngine — validate DID
# ═══════════════════════════════════════════════════════════════════


def test_rule_engine_validate_did(np_rng):
    """
    EconometricsRuleEngine.validate('did', ...) with synthetic
    event-study data should return a ValidationResult.
    """
    engine = EconometricsRuleEngine()

    # Passing DID data: pre-periods ≈ 0, post-periods significant
    event_df = pd.DataFrame({
        "period": [-3, -2, -1, 0, 1, 2, 3],
        "coef": [0.01, 0.02, 0.005, 0.12, 0.15, 0.13, 0.11],
        "se": [0.08, 0.07, 0.06, 0.05, 0.06, 0.07, 0.08],
    })

    result = engine.validate("did", {"event_study_df": event_df, "pre_periods": 3})

    assert isinstance(result, ValidationResult)
    assert hasattr(result, "passed")
    assert hasattr(result, "warnings")
    assert hasattr(result, "errors")
    assert hasattr(result, "details")
    assert result.passed is True


# ═══════════════════════════════════════════════════════════════════
# Test 10: EconometricsRuleEngine — validate IV
# ═══════════════════════════════════════════════════════════════════


def test_rule_engine_validate_iv(np_rng):
    """
    EconometricsRuleEngine.validate('iv', ...) with strong instrument
    should return passed=True.
    """
    engine = EconometricsRuleEngine()

    n = 500
    Z = np.column_stack([
        np_rng.normal(0, 1, n),
        np_rng.normal(0, 1, n),
    ])
    X = 1.5 * Z[:, 0] + 0.8 * Z[:, 1] + np_rng.normal(0, 0.3, n)

    result = engine.validate("iv", {"X": X, "Z": Z})

    assert isinstance(result, ValidationResult)
    assert result.passed is True
    assert result.errors == []


# ═══════════════════════════════════════════════════════════════════
# Test 11: HaltRulesRegistry — econometric_quality_check PASS
# ═══════════════════════════════════════════════════════════════════


def test_halt_rules_registry_econometric_check_pass(registry, np_rng):
    """
    HaltRulesRegistry.validate() with econometric_quality_check rule
    and passing DID data should return all_passed=True.
    """
    # Build content with a passing DID event study
    event_df = {
        "period": [-3, -2, -1, 0, 1, 2, 3],
        "coef": [0.01, 0.02, 0.005, 0.12, 0.15, 0.13, 0.11],
        "se": [0.08, 0.07, 0.06, 0.05, 0.06, 0.07, 0.08],
    }
    content = {
        "method": "did",
        "event_study_df": event_df,
        "pre_periods": 3,
    }

    result = registry.validate("empirical_paper", content)

    # The econometric_quality rule should have passed
    econ_violations = [
        v for v in result.violations
        if v.rule_id == "econometric_quality"
    ]
    assert len(econ_violations) == 0, f"Unexpected violations: {[v.message for v in econ_violations]}"


# ═══════════════════════════════════════════════════════════════════
# Test 12: HaltRulesRegistry — econometric_quality_check FAIL
# ═══════════════════════════════════════════════════════════════════


def test_halt_rules_registry_econometric_check_fail(registry, np_rng):
    """
    HaltRulesRegistry.validate() with failing DID data (significant
    pre-treatment coefficients) should produce a violation.
    """
    # Failing DID data: period -1 is significantly negative
    event_df = {
        "period": [-3, -2, -1, 0, 1, 2, 3],
        "coef": [0.01, 0.02, -0.15, 0.12, 0.15, 0.13, 0.11],
        "se": [0.08, 0.07, 0.05, 0.05, 0.06, 0.07, 0.08],
    }
    content = {
        "method": "did",
        "event_study_df": event_df,
        "pre_periods": 3,
    }

    result = registry.validate("empirical_paper", content)

    # The econometric_quality rule should have produced a violation
    econ_violations = [
        v for v in result.violations
        if v.rule_id == "econometric_quality"
    ]
    assert len(econ_violations) >= 1, "Expected at least one violation for failing DID data"
    assert any(
        "平行趋势" in v.message or "failed" in v.message.lower()
        for v in econ_violations
    ), f"Expected parallel trend error message, got: {[v.message for v in econ_violations]}"


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
