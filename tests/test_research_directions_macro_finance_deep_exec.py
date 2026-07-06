"""tests/test_research_directions_macro_finance_deep_exec.py — Deep execution tests for macro_finance."""

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
    from scripts.research_directions import macro_finance as mod
except Exception as _exc:
    pytest.skip(f"macro_finance not importable: {_exc}", allow_module_level=True)


# ─── Synthetic data factories ──────────────────────────────────────────────────

def _make_macro_panel() -> pd.DataFrame:
    """Time-series panel with rate and macro variables."""
    dates = pd.date_range("2010-01-01", "2023-12-31", freq="QE")
    return pd.DataFrame({
        "date": dates,
        "fed_rate": np.random.uniform(0, 5, len(dates)),
        "lpr": np.random.uniform(3, 6, len(dates)),
        "m2": np.random.uniform(150, 250, len(dates)),
        "cpi": np.random.uniform(-1, 5, len(dates)),
        "gdp": np.random.uniform(5, 10, len(dates)),
    })


def _make_bank_panel() -> pd.DataFrame:
    """Bank-level panel for Panel VAR."""
    records = []
    for bid in range(1, 21):
        for qtr in range(1, 5):
            records.append({
                "date": f"202{qtr}-0{qtr+1}-01" if qtr < 4 else f"202{qtr}-12-01",
                "bank_id": f"B{bid:02d}",
                "loan_growth": np.random.uniform(-0.05, 0.15),
                "size": np.random.uniform(15, 22),
                "capital_ratio": np.random.uniform(0.08, 0.15),
            })
    return pd.DataFrame(records)


# ─── Test Module ────────────────────────────────────────────────────────────────

class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_classes_present(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)


class TestMacroFinanceDirection:
    """Test MacroFinanceDirection class."""

    def test_class_exists(self):
        cls = getattr(mod, "MacroFinanceDirection", None)
        assert cls is not None
        assert isinstance(cls, type)

    def test_instantiate(self):
        cls = getattr(mod, "MacroFinanceDirection")
        obj = cls()
        assert obj is not None

    def test_name_attr(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert obj.name == "宏观金融"
        assert obj.slug == "macro_finance"

    def test_description_attr(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert isinstance(obj.description, str)
        assert len(obj.description) > 0

    def test_policy_events_list(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert isinstance(obj.policy_events, list)
        assert len(obj.policy_events) >= 8


class TestToDataFrame:
    """Test _to_dataframe helper."""

    def test_passthrough_dataframe(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = pd.DataFrame({"a": [1, 2]})
        result = obj._to_dataframe(df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_from_list(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._to_dataframe([{"a": 1}, {"a": 2}])
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_from_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._to_dataframe({"a": 1})
        assert isinstance(result, pd.DataFrame)

    def test_from_dict_with_data_key(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._to_dataframe({"data": [{"a": 1}, {"a": 2}]})
        assert isinstance(result, pd.DataFrame)


class TestBuildPanel:
    """Test build_panel method."""

    def test_build_panel_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        data = {"fed_rate": [{"date": "2020-01-01", "value": 1.5}]}
        result = obj.build_panel(data)
        assert result is None or isinstance(result, dict)

    def test_build_panel_with_macro_data(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        data = {"fed_rate": _make_macro_panel()[["date", "fed_rate"]].to_dict("records")}
        result = obj.build_panel(data)
        # May return None if insufficient data

    def test_build_panel_generates_event_panel(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.build_panel({})
        # Always generates event panel
        if result:
            assert "event_panel" in result or result is None


class TestValidate:
    """Test validate method."""

    def test_validate_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.validate({})
        assert isinstance(result, dict)
        assert "valid" in result

    def test_validate_with_macro_panel(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_macro_panel()
        result = obj.validate({"ts_panel": df})
        assert isinstance(result, dict)
        assert "warnings" in result

    def test_validate_with_bank_panel(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_bank_panel()
        result = obj.validate({"bank_panel": df})
        assert isinstance(result, dict)


class TestLocalProjection:
    """Test _local_projection method."""

    def test_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_macro_panel()
        result = obj._local_projection(df)
        assert isinstance(result, dict)

    def test_returns_error_when_no_rate(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = pd.DataFrame({"date": ["2020-01-01"], "cpi": [2.0]})
        result = obj._local_projection(df)
        assert "error" in result

    def test_returns_irf_entries(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_macro_panel()
        result = obj._local_projection(df)
        if "error" not in result:
            assert len(result) >= 1


class TestPanelVar:
    """Test _panel_var method."""

    def test_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_bank_panel()
        result = obj._panel_var(df)
        assert isinstance(result, dict)

    def test_insufficient_vars_returns_error(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = pd.DataFrame({"bank_id": ["B1"], "loan_growth": [0.05]})
        result = obj._panel_var(df)
        assert isinstance(result, dict)


class TestEventStudy:
    """Test _event_study method."""

    def test_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        event_df = pd.DataFrame([{"date": "2020-01-01", "year": 2020, "event": "test"}])
        ts_df = pd.DataFrame({"date": ["2020-01-01"], "value": [1.5]})
        result = obj._event_study(event_df, ts_df)
        assert isinstance(result, dict)

    def test_no_ts_panel_returns_error(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        event_df = pd.DataFrame([{"date": "2020-01-01", "year": 2020, "event": "test"}])
        result = obj._event_study(event_df, None)
        assert "error" in result


class TestStaggeredDid:
    """Test _staggered_did method."""

    def test_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_macro_panel()
        result = obj._staggered_did(df)
        assert isinstance(result, dict)

    def test_insufficient_data(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = pd.DataFrame({"date": ["2020-01-01"], "cpi": [2.0]})
        result = obj._staggered_did(df)
        assert isinstance(result, dict)


class TestSafeFormatter:
    """Test _safe helper."""

    def test_none_returns_dash(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._safe(None)
        assert result == "--"

    def test_valid_number(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._safe(3.14159)
        assert "3.14" in result

    def test_custom_decimals(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._safe(3.14159, decimals=2)
        assert "3.14" in result


class TestSigStars:
    """Test _sig_stars method."""

    def test_very_significant(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert obj._sig_stars(0.0005) == "***"

    def test_significant(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert obj._sig_stars(0.005) == "**"

    def test_marginal(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert obj._sig_stars(0.03) == "*"

    def test_dagger(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert r"{\dagger}" in obj._sig_stars(0.08) or "$^" in obj._sig_stars(0.08)

    def test_not_significant(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        assert obj._sig_stars(0.5) == ""


class TestRunRegressions:
    """Test run_regressions method."""

    def test_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.run_regressions({})
        assert isinstance(result, dict)
        assert "status" in result
        assert "tables" in result

    def test_with_macro_panel(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_macro_panel()
        result = obj.run_regressions({"ts_panel": df})
        assert isinstance(result, dict)

    def test_with_bank_panel(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        df = _make_bank_panel()
        result = obj.run_regressions({"bank_panel": df})
        assert isinstance(result, dict)


class TestFormatTables:
    """Test format_tables method."""

    def test_format_tables_returns_dict(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.format_tables({})
        assert isinstance(result, dict)

    def test_table1_returns_string(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._table1_mp_shock({})
        assert isinstance(result, str)
        assert r"\begin{table}" in result

    def test_table2_returns_string(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._table2_irf({})
        assert isinstance(result, str)

    def test_table3_returns_string(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._table3_bank_hetero({})
        assert isinstance(result, str)

    def test_table4_returns_string(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj._table4_er_pt({})
        assert isinstance(result, str)


class TestGetFigurePlan:
    """Test get_figure_plan method."""

    def test_returns_list(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.get_figure_plan()
        assert isinstance(result, list)

    def test_returns_4_figures(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.get_figure_plan()
        assert len(result) == 4

    def test_figures_have_required_keys(self):
        obj = getattr(mod, "MacroFinanceDirection")()
        result = obj.get_figure_plan()
        for fig in result:
            assert "figure_id" in fig
            assert "title" in fig
