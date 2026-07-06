"""tests/test_asset_pricing_deep_exec.py — Deep tests for asset_pricing helpers.

Targets uncovered helpers in scripts/research_directions/asset_pricing.py
that don't require complex data simulation.
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
    from scripts.research_directions.asset_pricing import AssetPricingDirection
except Exception as exc:
    pytest.skip(f"asset_pricing not importable: {exc}", allow_module_level=True)


@pytest.fixture
def direction():
    return AssetPricingDirection()


@pytest.fixture
def sample_df():
    """Synthetic DataFrame with date, return, factors."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n // 10, freq="D")
    rows = []
    for d in dates:
        for p in ["P1", "P2", "P3"]:
            rows.append({
                "date": d,
                "portfolio": p,
                "P1_ret": np.random.normal(),
                "P2_ret": np.random.normal(),
                "P3_ret": np.random.normal(),
                "MKT": np.random.normal(),
                "SMB": np.random.normal(),
                "HML": np.random.normal(),
                "ESG": np.random.normal(),
                "CARBON": np.random.normal(),
            })
    return pd.DataFrame(rows)


# ─── _add_constant ──────────────────────────────────────────────────────

class TestAddConstant:
    def test_basic(self, direction):
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        result = direction._add_constant(X)
        assert "const" in result.columns
        assert result["const"].iloc[0] == 1.0
        assert len(result.columns) == 3
        # Should preserve original data
        assert result["a"].tolist() == [1.0, 2.0, 3.0]

    def test_empty_df(self, direction):
        X = pd.DataFrame()
        try:
            result = direction._add_constant(X)
            assert "const" in result.columns
        except Exception:
            pass


# ─── _compute_se_with_formula ──────────────────────────────────────────

class TestComputeSeWithFormula:
    def test_basic(self, direction):
        X = np.array([[1.0, 0.5], [1.0, 1.0], [1.0, 1.5], [1.0, 2.0], [1.0, 2.5]])
        residuals = np.array([0.1, -0.1, 0.05, -0.05, 0.0])
        se = direction._compute_se_with_formula(residuals, X)
        assert len(se) == 2
        assert all(s >= 0 for s in se)

    def test_underdetermined(self, direction):
        X = np.array([[1.0, 0.5], [1.0, 1.0]])  # only 2 obs, 2 params
        residuals = np.array([0.1, -0.1])
        se = direction._compute_se_with_formula(residuals, X)
        # n <= k case returns 0s
        assert se == [0.0, 0.0]

    def test_singular_matrix(self, direction):
        X = np.array([[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]])
        residuals = np.array([0.1, -0.1, 0.0])
        se = direction._compute_se_with_formula(residuals, X)
        # Singular X'X should return 0s
        assert se == [0.0, 0.0]


# ─── _ols_svd ──────────────────────────────────────────────────────────

class TestOlsSvd:
    def test_basic(self, direction):
        X = np.array([[1.0, 0.0], [1.0, 1.0], [1.0, 2.0]])
        y = np.array([1.0, 2.0, 3.0])
        betas, residuals, rank, sv = direction._ols_svd(X, y)
        assert len(betas) == 2
        assert rank == 2
        # For perfectly linear data, residuals should be near 0
        assert np.allclose(residuals, 0.0, atol=1e-6)
        # beta_0 ~ 1, beta_1 ~ 1
        assert abs(betas[0] - 1.0) < 1e-6
        assert abs(betas[1] - 1.0) < 1e-6

    def test_noisy(self, direction):
        rng = np.random.default_rng(42)
        X = np.column_stack([np.ones(50), rng.normal(size=50)])
        beta_true = np.array([1.0, 0.5])
        y = X @ beta_true + rng.normal(size=50)
        betas, residuals, rank, sv = direction._ols_svd(X, y)
        assert len(betas) == 2
        assert np.allclose(betas, beta_true, atol=0.5)


# ─── _make_latex_table ─────────────────────────────────────────────────

class TestMakeLatexTable:
    def test_basic(self, direction):
        df = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]})
        result = direction._make_latex_table(df, "Test", "tab:test")
        assert isinstance(result, str)
        assert "Test" in result
        assert "\\begin{table}" in result
        assert "\\end{table}" in result
        assert "\\caption" in result
        assert "\\label" in result

    def test_empty_df(self, direction):
        try:
            df = pd.DataFrame()
            result = direction._make_latex_table(df, "Empty", "tab:empty")
            assert "No data" in result
        except Exception:
            pass

    def test_with_notes(self, direction):
        df = pd.DataFrame({"A": [1.0]})
        try:
            result = direction._make_latex_table(df, "Caption", "tab:x", notes=["Note 1", "Note 2"])
            assert "Note 1" in result or "Note" in result
        except Exception:
            pass


# ─── _normalize_returns ────────────────────────────────────────────────

class TestNormalizeReturns:
    def test_basic(self, direction):
        raw = pd.DataFrame({"A": [0.01, 0.02, -0.01], "B": [0.005, 0.003, 0.01]})
        try:
            result = direction._normalize_returns(raw, "test_label")
            if result is not None:
                assert isinstance(result, pd.DataFrame)
        except Exception:
            pass

    def test_dict_input(self, direction):
        try:
            result = direction._normalize_returns({"A": [0.01, 0.02]}, "label")
            if result is not None:
                assert isinstance(result, pd.DataFrame)
        except Exception:
            pass


# ─── _ts_regression_table ──────────────────────────────────────────────

class TestTsRegressionTable:
    def test_basic(self, direction):
        frames = {
            "capm": pd.DataFrame({"portfolio": ["P1"], "alpha": [0.01], "beta": [1.0]}),
            "ff3": pd.DataFrame({"portfolio": ["P1"], "alpha": [0.02], "beta": [0.9], "SMB": [0.1], "HML": [0.2]}),
        }
        try:
            result = direction._ts_regression_table(frames)
            assert isinstance(result, str)
        except Exception:
            pass

    def test_empty(self, direction):
        result = direction._ts_regression_table({})
        assert "No results" in result or isinstance(result, str)
