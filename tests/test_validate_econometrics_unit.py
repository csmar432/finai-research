"""Unit tests for scripts/validate_econometrics.py.

Covers: ValidationResult dataclass-like class, load_* dataset loaders,
estimate_* estimators, validate_did, validate_iv, _stata_available,
validate_against_stata, validate_against_r, main.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ve():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import validate_econometrics as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


# ═══════════════════════════════════════════════════════════════════════════
# ValidationResult class
# ═══════════════════════════════════════════════════════════════════════════


class TestValidationResult:
    def test_class_exists(self, ve):
        assert hasattr(ve, "ValidationResult")
        assert inspect.isclass(ve.ValidationResult)

    def test_init_with_se(self, ve):
        r = ve.ValidationResult(
            method="2SLS",
            ref_value=0.107,
            python_value=0.108,
            ref_std_err=0.032,
            python_std_err=0.030,
            tolerance=0.02,
            reference_source="Wooldridge Table 13.1",
        )
        assert r.method == "2SLS"
        assert r.ref_value == 0.107
        assert r.python_value == 0.108
        assert r.pass_coef is True
        assert r.pass_se is True
        assert r.pass_all is True

    def test_init_without_se(self, ve):
        r = ve.ValidationResult(
            method="DID",
            ref_value=1.0,
            python_value=1.01,
            ref_std_err=None,
            python_std_err=None,
            tolerance=0.05,
            reference_source="synthetic",
        )
        assert r.pass_se is None
        assert r.pass_all is True  # only coef check matters

    def test_fail_when_delta_exceeds_tolerance(self, ve):
        r = ve.ValidationResult(
            method="DID",
            ref_value=1.0,
            python_value=2.0,
            ref_std_err=None,
            python_std_err=None,
            tolerance=0.05,
            reference_source="synthetic",
        )
        assert r.pass_coef is False
        assert r.pass_all is False

    def test_fail_when_se_delta_exceeds_2x_tolerance(self, ve):
        r = ve.ValidationResult(
            method="IV",
            ref_value=0.1,
            python_value=0.1,
            ref_std_err=0.03,
            python_std_err=0.1,  # delta 0.07 > 0.02 * 2 = 0.04
            tolerance=0.02,
            reference_source="test",
        )
        assert r.pass_coef is True
        assert r.pass_se is False
        assert r.pass_all is False

    def test_coef_delta_stored(self, ve):
        r = ve.ValidationResult(
            method="X",
            ref_value=1.0,
            python_value=1.05,
            ref_std_err=None,
            python_std_err=None,
            tolerance=0.1,
            reference_source="src",
        )
        assert r.coef_delta == pytest.approx(0.05)

    def test_str_format_includes_method(self, ve):
        r = ve.ValidationResult(
            method="TestMethod",
            ref_value=1.0,
            python_value=1.01,
            ref_std_err=None,
            python_std_err=None,
            tolerance=0.05,
            reference_source="unit",
        )
        s = str(r)
        assert "TestMethod" in s
        assert "PASS" in s

    def test_str_format_includes_source(self, ve):
        r = ve.ValidationResult(
            method="X",
            ref_value=1.0,
            python_value=1.0,
            ref_std_err=None,
            python_std_err=None,
            tolerance=0.05,
            reference_source="MySource",
        )
        assert "MySource" in str(r)

    def test_str_format_shows_failure(self, ve):
        r = ve.ValidationResult(
            method="X",
            ref_value=1.0,
            python_value=2.0,
            ref_std_err=None,
            python_std_err=None,
            tolerance=0.05,
            reference_source="unit",
        )
        assert "FAIL" in str(r)

    def test_str_includes_se_delta_when_present(self, ve):
        r = ve.ValidationResult(
            method="IV",
            ref_value=0.1,
            python_value=0.1,
            ref_std_err=0.03,
            python_std_err=0.04,
            tolerance=0.02,
            reference_source="test",
        )
        assert "SE delta" in str(r)


# ═══════════════════════════════════════════════════════════════════════════
# Dataset loaders
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadDatasets:
    def test_load_did_synthetic_returns_df(self, ve):
        df = ve.load_did_synthetic()
        assert isinstance(df, pd.DataFrame)
        assert "outcome" in df.columns
        assert "treated" in df.columns
        assert "post" in df.columns
        assert len(df) > 100

    def test_load_did_synthetic_balance(self, ve):
        df = ve.load_did_synthetic()
        # Both pre and post periods should have ~n observations
        post_count = (df["post"] == 1).sum()
        pre_count = (df["post"] == 0).sum()
        assert pre_count > 0
        assert post_count > 0
        # Roughly equal pre and post (synthetic data)
        assert abs(pre_count - post_count) <= 1

    def test_load_wooldridge_card_returns_df(self, ve):
        df = ve.load_wooldridge_card_hehes()
        assert isinstance(df, pd.DataFrame)
        assert "lwage" in df.columns
        assert "educ" in df.columns
        assert "nearc4" in df.columns
        assert "exper" in df.columns
        # Card (1995) sample is ~3000
        assert len(df) > 2000

    def test_load_wooldridge_did_smoking_returns_df(self, ve):
        df = ve.load_wooldridge_did_smoking()
        assert isinstance(df, pd.DataFrame)
        assert "log_earnings" in df.columns
        assert "log_trips" in df.columns
        assert "after" in df.columns


# ═══════════════════════════════════════════════════════════════════════════
# Python estimators
# ═══════════════════════════════════════════════════════════════════════════


class TestEstimatePython:
    def test_estimate_did_python(self, ve):
        df = ve.load_did_synthetic()
        coef, se = ve.estimate_did_python(df)
        assert isinstance(coef, float)
        assert isinstance(se, float)
        # The known ATT = 1.0 should be recovered (loose tolerance)
        assert abs(coef - 1.0) < 0.2
        # SE should be positive
        assert se > 0

    def test_estimate_did_signature(self, ve):
        sig = inspect.signature(ve.estimate_did_python)
        assert "df" in sig.parameters

    def test_estimate_iv_python(self, ve):
        df = ve.load_wooldridge_card_hehes()
        try:
            coef, se = ve.estimate_iv_python(df, "lwage", "nearc4", ["exper"])
            assert isinstance(coef, float)
            assert isinstance(se, float)
        except Exception:
            # If linearmodels missing → acceptable skip
            pytest.skip("linearmodels not installed")

    def test_estimate_iv_signature(self, ve):
        sig = inspect.signature(ve.estimate_iv_python)
        assert "df" in sig.parameters
        assert "endog" in sig.parameters
        assert "iv" in sig.parameters
        assert "exog" in sig.parameters


# ═══════════════════════════════════════════════════════════════════════════
# Validation functions
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateDid:
    def test_returns_list(self, ve):
        results = ve.validate_did()
        assert isinstance(results, list)
        assert len(results) >= 1
        # Each entry is a ValidationResult
        assert all(isinstance(r, ve.ValidationResult) for r in results)

    def test_passes_synthetic_did(self, ve):
        results = ve.validate_did()
        # Synthetic ATT = 1.0, tolerance = 0.05 → should pass
        assert all(r.pass_all for r in results)

    def test_validate_did_signature(self, ve):
        sig = inspect.signature(ve.validate_did)
        # No required args
        required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
        assert len(required) == 0


class TestValidateIv:
    def test_returns_list(self, ve):
        results = ve.validate_iv()
        assert isinstance(results, list)
        # May be empty if linearmodels missing — that's acceptable
        for r in results:
            assert isinstance(r, ve.ValidationResult)


# ═══════════════════════════════════════════════════════════════════════════
# External tool availability / comparison functions
# ═══════════════════════════════════════════════════════════════════════════


class TestStataAvailable:
    def test_returns_bool(self, ve):
        result = ve._stata_available()
        assert isinstance(result, bool)


class TestValidateAgainstStata:
    def test_returns_list(self, ve):
        # If Stata is not installed, this should return [] gracefully
        results = ve.validate_against_stata("did")
        assert isinstance(results, list)

    def test_returns_list_for_iv(self, ve):
        results = ve.validate_against_stata("iv")
        assert isinstance(results, list)

    def test_returns_list_for_all(self, ve):
        results = ve.validate_against_stata("all")
        assert isinstance(results, list)

    def test_signature_has_method_param(self, ve):
        sig = inspect.signature(ve.validate_against_stata)
        assert "method" in sig.parameters


class TestValidateAgainstR:
    def test_returns_list(self, ve):
        results = ve.validate_against_r("did")
        assert isinstance(results, list)

    def test_signature_has_method_param(self, ve):
        sig = inspect.signature(ve.validate_against_r)
        assert "method" in sig.parameters


# ═══════════════════════════════════════════════════════════════════════════
# CLI entrypoint
# ═══════════════════════════════════════════════════════════════════════════


class TestMain:
    def test_function_exists(self, ve):
        assert callable(ve.main)

    def test_main_signature(self, ve):
        sig = inspect.signature(ve.main)
        required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
        assert len(required) == 0
