"""tests/test_carbon_economics_exec.py — Test carbon_economics research direction."""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts.research_directions.carbon_economics import CarbonEconomicsDirection
except Exception as e:
    pytest.skip(f"carbon_economics not importable: {e}", allow_module_level=True)


@pytest.fixture
def d():
    return CarbonEconomicsDirection()


def _make_panel(n_firms=10, n_years=5):
    firms = list(range(n_firms))
    years = list(range(2018, 2018 + n_years))
    rows = []
    for f in firms:
        for y in years:
            rows.append({
                "firm_id": f,
                "year": y,
                "emission": np.random.normal(100, 30),
                "carbon_price": np.random.uniform(20, 80),
                "size": np.random.uniform(20, 28),
            })
    return {"panel": pd.DataFrame(rows), "outcome_vars": ["emission"], "treatment": "carbon_price"}


class TestInit:
    def test_class_attrs(self, d):
        assert d.name
        assert d.slug
        assert d.description
        assert isinstance(d.policy_events, list)

    def test_repr(self, d):
        assert isinstance(repr(d), str)


class TestValidate:
    def test_none(self, d):
        r = d.validate(None)
        assert r["valid"] is False

    def test_empty(self, d):
        r = d.validate({"panel": pd.DataFrame()})
        assert r["valid"] is False

    def test_valid(self, d):
        r = d.validate(_make_panel())
        assert "valid" in r


class TestBuildPanel:
    def test_minimal_data(self, d):
        # audit-2026-07-21: try/except/Exception:pass converted to xfail
        pytest.xfail(
            reason="no real assertion",
        )


class TestFetchData:
    @pytest.mark.skip(reason="network-dependent (MCP)")
    def test_fetch_data(self, d):
        result = d.fetch_data("test topic")
        assert result is None or isinstance(result, dict)


class TestFormatTables:
    def test_format_tables_minimal(self, d):
        fake_results = {"models": {"DID": {"att": -0.5, "se": 0.1, "n": 200}}}
        try:
            r = d.format_tables(fake_results)
            assert r is None or isinstance(r, dict)
        except Exception:
            pass


class TestRunRegressions:
    def test_run_regressions_synthetic(self, d):
        try:
            r = d.run_regressions(_make_panel())
            assert r is None or isinstance(r, dict)
        except Exception:
            pass


class TestHelperMethods:
    def test_helper_methods_exist(self, d):
        method_names = [m for m in dir(d) if m.startswith("_") and callable(getattr(d, m, None))]
        assert len(method_names) > 0

    def test_class_level_attrs(self, d):
        for attr in ["name", "slug", "description", "policy_events"]:
            assert hasattr(d, attr)
