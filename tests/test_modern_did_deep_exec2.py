"""tests/test_modern_did_deep_exec2.py — Additional deep tests for modern_did.

Targets _honest_did_simplified, _build_honest_did_interpretation,
EstimatorUnavailableError (additional), ModernDiDEngine helpers.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import pandas as pd
    from scripts.research_framework.modern_did import (
        ModernDiDEngine, EstimatorUnavailableError,
        _honest_did_simplified, _build_honest_did_interpretation,
    )
except Exception as exc:
    pytest.skip(f"modern_did not importable: {exc}", allow_module_level=True)


# ─── _honest_did_simplified ──────────────────────────────────────────

class TestHonestDidSimplified:
    def test_basic(self):
        coef = 0.5
        se = 0.1
        m = 0.5
        delta_grid = np.array([0.0, 0.1, 0.2])
        # audit-2026-07-21: try/except/Exception:pass converted to xfail
        pytest.xfail(
            reason="no real assertion",
        )

    def test_zero_coef(self):
        # audit-2026-07-21: try/except/Exception:pass converted to xfail
        pytest.xfail(
            reason="no real assertion",
        )

    def test_warns(self):
        with pytest.warns(UserWarning):
            result = _honest_did_simplified(0.5, 0.1, 0.5, np.array([0.0, 0.1]))


# ─── _build_honest_did_interpretation ────────────────────────────────

class TestBuildInterpretation:
    def test_basic(self):
        interp = _build_honest_did_interpretation(
            coef=0.5, ci_lower=0.1, ci_upper=0.9,
            breakdown_value=0.5, m=0.3, m_pre=0.5,
        )
        assert isinstance(interp, str)
        assert "0.5" in interp or "0.1" in interp
        assert "Honest DiD" in interp or "Honest" in interp

    def test_no_breakdown(self):
        interp = _build_honest_did_interpretation(
            coef=0.3, ci_lower=-0.1, ci_upper=0.7,
            breakdown_value=None, m=0.3, m_pre=None,
        )
        assert isinstance(interp, str)

    def test_with_m_pre(self):
        interp = _build_honest_did_interpretation(
            coef=0.3, ci_lower=0.0, ci_upper=0.6,
            breakdown_value=0.7, m=0.3, m_pre=0.5,
        )
        # Should mention "robust"
        assert "robust" in interp.lower() or "Pre-treatment" in interp


# ─── EstimatorUnavailableError ───────────────────────────────────────

class TestEstimatorUnavailableErrorExtended:
    def test_with_install_hint(self):
        e = EstimatorUnavailableError(
            estimator="cs",
            package="csdid",
            install_hint="pip install csdid",
        )
        assert "csdid" in str(e) or "cs" in str(e)
        assert "pip install csdid" in str(e)

    def test_default_hint(self):
        e = EstimatorUnavailableError(
            estimator="some_est",
            package="some_pkg",
        )
        # Default hint should be "pip install some_pkg"
        assert "some_pkg" in str(e)

    def test_attributes(self):
        e = EstimatorUnavailableError(estimator="x", package="y")
        assert e.estimator == "x"
        assert e.package == "y"
        assert e.install_hint == "pip install y"


# ─── ModernDiDEngine ────────────────────────────────────────────────

class TestModernDiDEngine:
    @pytest.fixture
    def sample_df(self):
        np.random.seed(42)
        n = 200
        df = pd.DataFrame({
            "y": np.random.normal(size=n),
            "did": np.random.binomial(1, 0.5, n),
            "post": np.random.binomial(1, 0.5, n),
            "ticker": np.repeat(np.arange(50), 4),
            "year": np.tile(np.arange(4), 50),
        })
        return df

    def test_init_basic(self, sample_df):
        engine = ModernDiDEngine(
            df=sample_df, y_var="y", treat_var="did",
            time_var="post", unit_var="ticker",
        )
        assert engine.n_obs == 200
        assert engine.n_periods == 2

    def test_init_with_covariates(self, sample_df):
        sample_df["x1"] = np.random.normal(size=len(sample_df))
        engine = ModernDiDEngine(
            df=sample_df, y_var="y", treat_var="did",
            time_var="post", unit_var="ticker",
            x_vars=["x1"],
        )
        assert "x1" in engine.x_vars

    def test_init_with_cluster(self, sample_df):
        engine = ModernDiDEngine(
            df=sample_df, y_var="y", treat_var="did",
            time_var="post", unit_var="ticker",
            cluster_var="ticker",
        )
        assert engine.cluster_var == "ticker"

    def test_init_missing_columns(self):
        df = pd.DataFrame({"a": [1, 2]})
        with pytest.raises(ValueError):
            ModernDiDEngine(
                df=df, y_var="missing", treat_var="x",
                time_var="t", unit_var="u",
            )
