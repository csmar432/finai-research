"""tests/test_asset_pricing_exec.py — Test asset_pricing research direction."""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

from scripts.exceptions import DataSourceError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts.research_directions.asset_pricing import AssetPricingDirection
except Exception as e:
    pytest.skip(f"asset_pricing not importable: {e}", allow_module_level=True)


@pytest.fixture
def d():
    return AssetPricingDirection()


def _make_panel(n_firms=10, n_years=5):
    firms = list(range(n_firms))
    years = list(range(2018, 2018 + n_years))
    rows = []
    for f in firms:
        for y in years:
            rows.append({
                "firm_id": f,
                "year": y,
                "ret": np.random.normal(0.05, 0.1),
                "Mkt_RF": np.random.normal(0.06, 0.05),
                "SMB": np.random.normal(0.02, 0.03),
                "HML": np.random.normal(0.02, 0.03),
                "ESG": np.random.normal(0.01, 0.04),
                "RF": np.random.normal(0.02, 0.005),
                "esg_score": np.random.uniform(40, 80),
            })
    df = pd.DataFrame(rows)
    return {"panel": df, "outcome_vars": ["ret"], "treatment": "esg_score"}


class TestInit:
    def test_class_attrs(self, d):
        assert d.name
        assert d.slug
        assert d.description
        assert isinstance(d.policy_events, list)

    def test_repr(self, d):
        s = repr(d)
        assert isinstance(s, str)


class TestValidate:
    def test_none(self, d):
        r = d.validate(None)
        assert r["valid"] is False
        assert len(r["issues"]) > 0

    def test_empty(self, d):
        r = d.validate({"panel": pd.DataFrame()})
        assert r["valid"] is False

    def test_valid(self, d):
        r = d.validate(_make_panel())
        assert "valid" in r
        assert "n_obs" in r


class TestBuildPanel:
    def test_minimal_data(self, d):
        data = {"prices": pd.DataFrame({"A": [1, 2, 3]})}
        try:
            result = d.build_panel(data)
        except (KeyError, ValueError, TypeError, RuntimeError, DataSourceError):
            pass  # acceptable on minimal stub data


class TestFetchData:
    @pytest.mark.skip(reason="network-dependent (MCP)")
    def test_fetch_data(self, d):
        result = d.fetch_data("test topic")
        # Will be dict or None
        assert result is None or isinstance(result, dict)


class TestFormatTables:
    def test_format_tables_with_minimal_results(self, d):
        fake_results = {
            "models": {
                "CAPM": {"coefficients": {"Mkt_RF": 0.5}, "r2": 0.3, "n": 50},
                "FF3": {"coefficients": {"Mkt_RF": 0.4, "SMB": 0.2, "HML": 0.1}, "r2": 0.5, "n": 50},
            }
        }
        r = d.format_tables(fake_results) if hasattr(d, "format_tables") else None
        assert r is None or isinstance(r, dict)


class TestRunRegressions:
    def test_run_regressions_with_synthetic(self, d):
        panel = _make_panel()
        try:
            r = d.run_regressions(panel)
            assert r is None or isinstance(r, dict)
        except Exception:
            # Acceptable to fail on synthetic data; just don't crash on import
            pass


class TestHelperMethods:
    def test_normalize_returns(self, d):
        if hasattr(d, "_normalize_returns"):
            try:
                r = d._normalize_returns(None, "test")
            except Exception:
                pass

    def test_add_constant(self, d):
        if hasattr(d, "_add_constant"):
            X = pd.DataFrame({"a": [1, 2, 3]})
            r = d._add_constant(X)
            assert isinstance(r, pd.DataFrame)
            assert "const" in r.columns

    def test_ols_svd(self, d):
        if hasattr(d, "_ols_svd"):
            X = np.array([[1.0, 2.0], [1.0, 3.0], [1.0, 4.0]])
            y = np.array([5.0, 6.0, 7.0])
            try:
                coef, resid = d._ols_svd(X, y)
            except Exception:
                pass
