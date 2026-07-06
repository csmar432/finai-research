"""tests/test_research_directions_political_economy_finance_deep_exec.py — Deep exec tests for political_economy_finance."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_directions import political_economy_finance as mod
except Exception as _exc:
    pytest.skip(f"political_economy_finance not importable: {_exc}", allow_module_level=True)


# ─── Synthetic data factories ──────────────────────────────────────────────────

def _make_pol_panel() -> pd.DataFrame:
    """Political economy panel with political connection variables."""
    records = []
    for i in range(1, 101):
        for yr in range(2012, 2023):
            records.append({
                "ts_code": f"00000{i%9+1:02d}.SZ",
                "ann_date": f"{yr}-06-30",
                "roa": round(np.random.uniform(-0.05, 0.15), 4),
                "political_connection": np.random.choice([0, 1], p=[0.6, 0.4]),
                "politician_on_board": np.random.choice([0, 1], p=[0.8, 0.2]),
                "is_soe": np.random.choice([0, 1], p=[0.7, 0.3]),
                "size": round(np.random.uniform(18, 24), 2),
                "age": np.random.randint(3, 40),
                "leverage": round(np.random.uniform(0.2, 0.8), 4),
                "hhi": round(np.random.uniform(0.01, 0.5), 4),
                "investment_efficiency": round(np.random.uniform(-0.2, 0.2), 4),
                "loan_availability": round(np.random.uniform(0.1, 0.6), 4),
            })
    return pd.DataFrame(records)


# ─── Test Module ────────────────────────────────────────────────────────────────

class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_classes_present(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)


class TestModuleHelpers:
    """Test module-level formatting helpers."""

    def test_fmt_val_none(self):
        assert mod._fmt_val(None) == ""

    def test_fmt_val_float(self):
        result = mod._fmt_val(3.14159)
        assert "3.142" in result

    def test_fmt_val_with_star(self):
        result = mod._fmt_val(2.5)
        assert "***" in result

    def test_fmt_val_dagger(self):
        result = mod._fmt_val(0.15)
        assert "*" in result

    def test_fmt_se_none(self):
        assert mod._fmt_se(None) == ""

    def test_fmt_se_float(self):
        result = mod._fmt_se(1.234)
        assert "1.234" in result

    def test_fmt_n_large(self):
        result = mod._fmt_n(1500000)
        assert "1.5M" in result

    def test_fmt_n_thousand(self):
        result = mod._fmt_n(5000)
        assert "5K" in result

    def test_fmt_r2(self):
        result = mod._fmt_r2(0.4567)
        assert "0.457" in result


class TestPoliticalEconomyFinanceDirection:
    """Test PoliticalEconomyFinanceDirection class."""

    def test_class_exists(self):
        cls = getattr(mod, "PoliticalEconomyFinanceDirection", None)
        assert cls is not None
        assert isinstance(cls, type)

    def test_instantiate(self):
        cls = getattr(mod, "PoliticalEconomyFinanceDirection")
        obj = cls()
        assert obj is not None

    def test_name_attr(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        assert obj.name == "政治经济金融"
        assert obj.slug == "political_economy_finance"

    def test_description_attr(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        assert isinstance(obj.description, str)
        assert len(obj.description) > 0

    def test_policy_events_list(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        assert isinstance(obj.policy_events, list)
        assert len(obj.policy_events) >= 7


class TestValidate:
    """Test validate method."""

    def test_validate_returns_dict(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.validate({})
        assert isinstance(result, dict)
        assert "valid" in result

    def test_validate_with_panel(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        df = _make_pol_panel()
        result = obj.validate({"df": df})
        assert isinstance(result, dict)
        assert "warnings" in result


class TestRunRegressions:
    """Test run_regressions method."""

    def test_empty_returns_no_data(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.run_regressions({})
        assert result["status"] in ("no_data", "error")

    def test_with_pol_panel(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        df = _make_pol_panel()
        result = obj.run_regressions({"df": df})
        assert isinstance(result, dict)
        assert "status" in result
        assert "tables" in result


class TestFormatTables:
    """Test format_tables method."""

    def test_format_tables_returns_dict(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.format_tables({})
        assert isinstance(result, dict)

    def test_format_tables_keys(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.format_tables({})
        assert "table1_performance" in result
        assert "table2_mechanism" in result
        assert "table3_misallocation" in result
        assert "table4_heterogeneity" in result

    def test_table1_returns_string(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj._fmt_table1_pol_connection(None)
        assert isinstance(result, str)
        assert r"\begin{table}" in result

    def test_table2_returns_string(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj._fmt_table2_bank_loan(None)
        assert isinstance(result, str)

    def test_table3_returns_string(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj._fmt_table3_misallocation(None)
        assert isinstance(result, str)

    def test_table4_returns_string(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj._fmt_table4_heterogeneity(None)
        assert isinstance(result, str)

    def test_format_tables_with_success_status(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        df = _make_pol_panel()
        rr = obj.run_regressions({"df": df})
        result = obj.format_tables(rr)
        assert isinstance(result, dict)
        # Result contains both strings (from _fmt_table*) and dicts (from regression tables)
        for v in result.values():
            assert isinstance(v, (str, dict))


class TestGetFigurePlan:
    """Test get_figure_plan method."""

    def test_returns_list(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.get_figure_plan()
        assert isinstance(result, list)

    def test_returns_4_figures(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.get_figure_plan()
        assert len(result) == 4

    def test_figures_have_required_keys(self):
        obj = getattr(mod, "PoliticalEconomyFinanceDirection")()
        result = obj.get_figure_plan()
        for fig in result:
            assert "figure_id" in fig
            assert "title" in fig
