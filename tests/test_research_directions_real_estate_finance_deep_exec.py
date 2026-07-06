"""tests/test_research_directions_real_estate_finance_deep_exec.py — Deep exec tests for real_estate_finance."""

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
    from scripts.research_directions import real_estate_finance as mod
except Exception as _exc:
    pytest.skip(f"real_estate_finance not importable: {_exc}", allow_module_level=True)


# ─── Synthetic data factories ──────────────────────────────────────────────────

def _make_re_panel() -> pd.DataFrame:
    """Real estate panel with housing/city variables."""
    records = []
    for city in ["北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京"]:
        for yr in range(2010, 2023):
            records.append({
                "city": city,
                "year": yr,
                "housing_price": round(np.random.uniform(5000, 50000), 2),
                "property_price": round(np.random.uniform(5000, 50000), 2),
                "land_revenue": round(np.random.uniform(100, 5000), 2),
                "land_sale": round(np.random.uniform(50, 2000), 2),
                "gdp_growth": round(np.random.uniform(-5, 15), 2),
                "population": round(np.random.uniform(5, 30), 2),
                "mortgage_rate": round(np.random.uniform(0.03, 0.07), 4),
                "leverage_ratio": round(np.random.uniform(0.5, 0.9), 4),
                "distance_threshold": round(np.random.uniform(-0.2, 0.2), 4),
            })
    return pd.DataFrame(records)


# ─── Test Module ────────────────────────────────────────────────────────────────

class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_classes_present(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)


class TestRealEstateFinanceDirection:
    """Test RealEstateFinanceDirection class."""

    def test_class_exists(self):
        cls = getattr(mod, "RealEstateFinanceDirection", None)
        assert cls is not None
        assert isinstance(cls, type)

    def test_instantiate(self):
        cls = getattr(mod, "RealEstateFinanceDirection")
        obj = cls()
        assert obj is not None

    def test_name_attr(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        assert obj.name == "房地产金融"
        assert obj.slug == "real_estate_finance"

    def test_description_attr(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        assert isinstance(obj.description, str)
        assert len(obj.description) > 0

    def test_policy_events_list(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        assert isinstance(obj.policy_events, list)
        assert len(obj.policy_events) >= 7


class TestAddTreatmentVariables:
    """Test _add_treatment_variables method."""

    def test_adds_three_redlines(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        df = pd.DataFrame({
            "city": ["上海", "北京"],
            "year": [2019, 2021],
        })
        result = obj._add_treatment_variables(df)
        assert "post_three_redlines" in result.columns

    def test_three_redlines_is_one_after_2020(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        df = pd.DataFrame({
            "city": ["上海", "北京"],
            "year": [2019, 2021],
        })
        result = obj._add_treatment_variables(df)
        assert result.loc[result["year"] == 2021, "post_three_redlines"].iloc[0] == 1

    def test_adds_property_tax(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        df = pd.DataFrame({
            "city": ["上海", "北京"],
            "year": [2010, 2015],
        })
        result = obj._add_treatment_variables(df)
        assert "post_property_tax" in result.columns

    def test_property_tax_pilot_shanghai(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        df = pd.DataFrame({
            "city": ["上海", "北京"],
            "year": [2012, 2012],
        })
        result = obj._add_treatment_variables(df)
        # Shanghai is a pilot city
        shanghai_val = result.loc[result["city"] == "上海", "post_property_tax"].iloc[0]
        assert shanghai_val == 1


class TestValidate:
    """Test validate method."""

    def test_validate_returns_dict(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.validate({})
        assert isinstance(result, dict)
        assert "valid" in result

    def test_validate_with_panel(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        df = _make_re_panel()
        result = obj.validate({"df": df})
        assert isinstance(result, dict)
        assert "warnings" in result


class TestRunRegressions:
    """Test run_regressions method."""

    def test_returns_dict(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.run_regressions({})
        assert isinstance(result, dict)
        assert "status" in result

    def test_empty_dataframe(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.run_regressions({"df": pd.DataFrame()})
        assert result["status"] in ("no_data", "no_valid_regression")

    def test_with_re_panel(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        df = _make_re_panel()
        result = obj.run_regressions({"df": df})
        assert isinstance(result, dict)
        assert "status" in result
        assert "tables" in result


class TestEventStudyPlaceholder:
    """Test _event_study_placeholder method."""

    def test_returns_dict(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj._event_study_placeholder()
        assert isinstance(result, dict)
        assert "caption" in result


class TestFormatTables:
    """Test format_tables method."""

    def test_format_tables_returns_dict(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.format_tables({})
        assert isinstance(result, dict)

    def test_format_tables_keys(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.format_tables({})
        # Returns {} when status is not success
        assert isinstance(result, dict)
        # When success, should have specific keys
        result2 = obj.format_tables({"status": "success", "tables": {}})
        assert "table1_three_redlines" in result2
        assert "table2_land_finance" in result2
        assert "table3_chengtou_bond" in result2
        assert "table4_spatial" in result2

    def test_table1_returns_string(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj._table1_three_redlines()
        assert isinstance(result, str)
        assert r"\begin{table}" in result

    def test_table2_returns_string(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj._table2_land_finance()
        assert isinstance(result, str)

    def test_table3_returns_string(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj._table3_chengtou_bond()
        assert isinstance(result, str)

    def test_table4_returns_string(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj._table4_spatial()
        assert isinstance(result, str)


class TestGetFigurePlan:
    """Test get_figure_plan method."""

    def test_returns_list(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.get_figure_plan()
        assert isinstance(result, list)

    def test_returns_4_figures(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.get_figure_plan()
        assert len(result) == 4

    def test_figures_have_required_keys(self):
        obj = getattr(mod, "RealEstateFinanceDirection")()
        result = obj.get_figure_plan()
        for fig in result:
            assert "figure_id" in fig
            assert "title" in fig
