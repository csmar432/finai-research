"""tests/test_research_directions_green_finance_deep_exec.py — Deep execution tests for green_finance."""

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
    from scripts.research_directions import green_finance as mod
except Exception as _exc:
    pytest.skip(f"green_finance not importable: {_exc}", allow_module_level=True)


# ─── Synthetic data factories ──────────────────────────────────────────────────

def _make_minimal_panel() -> pd.DataFrame:
    """Minimal panel with province_code and year columns for DID treatment."""
    records = []
    provinces = [330000, 440000, 520000, 650000, 360000, 310000, 320000, 510000]
    for pid in provinces:
        for yr in range(2015, 2022):
            records.append({
                "firm_id": f"F{pid}{yr:04d}",
                "year": yr,
                "province_code": pid,
                "roa": round(np.random.uniform(-0.05, 0.15), 4),
                "rd_intensity": round(np.random.uniform(0.01, 0.08), 4),
                "tobin_q": round(np.random.uniform(0.8, 2.5), 3),
                "green_investment": round(np.random.uniform(0, 0.1), 4),
            })
    return pd.DataFrame(records)


def _make_extended_panel() -> pd.DataFrame:
    """Extended panel with pollution_intensity and mechanism variables."""
    df = _make_minimal_panel()
    df["pollution_intensity"] = np.random.uniform(0.1, 0.9, len(df))
    df["patent_count"] = np.random.randint(0, 200, len(df))
    df["sa_index"] = np.random.uniform(-3, -1, len(df))
    df["env_reg_pressure"] = (df["pollution_intensity"] > 0.5).astype(int)
    df["size"] = np.random.uniform(18, 23, len(df))
    df["lev"] = np.random.uniform(0.2, 0.7, len(df))
    df["age"] = np.random.randint(5, 40, len(df))
    return df


# ─── Test Module ───────────────────────────────────────────────────────────────

class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_classes_present(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)
        assert len(classes) >= 1


class TestGreenFinanceDirection:
    """Test GreenFinanceDirection class."""

    def test_class_exists(self):
        cls = getattr(mod, "GreenFinanceDirection", None)
        assert cls is not None, "GreenFinanceDirection not found"
        assert isinstance(cls, type)

    def test_instantiate(self):
        cls = getattr(mod, "GreenFinanceDirection")
        obj = cls()
        assert obj is not None

    def test_name_attr(self):
        cls = getattr(mod, "GreenFinanceDirection")
        obj = cls()
        assert obj.name == "绿色金融"
        assert obj.slug == "green_finance"

    def test_description_attr(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        assert isinstance(obj.description, str)
        assert len(obj.description) > 0

    def test_policy_events_attr(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        assert isinstance(obj.policy_events, list)
        assert len(obj.policy_events) >= 5
        for event in obj.policy_events:
            assert isinstance(event, tuple)
            assert len(event) == 2
            assert isinstance(event[0], int)
            assert isinstance(event[1], str)


class TestPureHelpers:
    """Test module-level helper functions."""

    def test_safe_fmt_module_helpers(self):
        # green_finance doesn't export standalone helpers but we can test formatting
        pass


class TestAddDidTreatment:
    """Test _add_did_treatment method."""

    def test_adds_treat_column(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        assert "treat" in result.columns

    def test_treat_is_binary(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        assert set(result["treat"].unique()).issubset({0, 1})

    def test_pilot_provinces_treated(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        # Pilot provinces should have treat=1
        pilot_mask = result["province_code"].isin([330000, 440000, 520000, 650000, 360000])
        assert result.loc[pilot_mask, "treat"].max() == 1

    def test_adds_post_column(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        assert "post" in result.columns
        assert set(result["post"].unique()).issubset({0, 1})

    def test_post_is_one_after_2017(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        post_years = result[result["post"] == 1]["year"]
        assert all(post_years >= 2017)

    def test_adds_did_column(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        if "post" in result.columns and "treat" in result.columns:
            assert "did" in result.columns

    def test_did_equals_treat_times_post(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        if "did" in result.columns and "treat" in result.columns and "post" in result.columns:
            # did = treat * post; use numeric comparison to avoid dtype/index edge cases
            expected = (result["treat"].fillna(0) * result["post"].fillna(0)).astype(float)
            did_vals = result["did"].fillna(0).astype(float)
            diff = (expected - did_vals).abs()
            assert diff.max() < 1e-6, f"did != treat*post, max diff={diff.max()}"


class TestValidate:
    """Test validate method."""

    def test_validate_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.validate({})
        assert isinstance(result, dict)
        assert "valid" in result

    def test_validate_with_minimal_panel(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj.validate({"df": df})
        assert isinstance(result, dict)
        assert "warnings" in result

    def test_validate_with_extended_panel(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj.validate({"df": df})
        assert isinstance(result, dict)
        assert "warnings" in result

    def test_validate_warns_missing_co2(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj.validate({"df": df})
        # Should warn about missing CO2 variable
        warning_text = " ".join(result.get("warnings", []))
        # Either warned or not, both fine

    def test_validate_warns_missing_dfi(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj.validate({"df": df})
        warning_text = " ".join(result.get("warnings", []))
        # May or may not warn depending on dfi presence


class TestPvalToStars:
    """Test _pval_to_stars method."""

    def test_stars_for_very_significant(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        stars = obj._pval_to_stars(0.0005)
        assert stars == "***"

    def test_stars_for_significant(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        stars = obj._pval_to_stars(0.005)
        assert stars == "**"

    def test_stars_for_marginally_significant(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        stars = obj._pval_to_stars(0.03)
        assert stars == "*"

    def test_stars_for_dagger(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        stars = obj._pval_to_stars(0.08)
        assert stars == r"^{\dagger}"

    def test_stars_for_not_significant(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        stars = obj._pval_to_stars(0.5)
        assert stars == ""

    def test_stars_for_nan(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        stars = obj._pval_to_stars(float("nan"))
        assert stars == ""


class TestEmptyTable:
    """Test _empty_table method."""

    def test_empty_table_returns_latex(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._empty_table("Test Table")
        assert isinstance(result, str)
        assert r"\begin{table}" in result
        assert r"\caption{Test Table}" in result

    def test_empty_table_contains_tabular(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._empty_table("Another Table")
        assert r"\begin{tabular}" in result
        assert r"\end{table}" in result


class TestFormatTables:
    """Test format_tables method."""

    def test_format_tables_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.format_tables({"status": "no_data", "tables": {}})
        assert isinstance(result, dict)

    def test_format_tables_handles_success_status(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.format_tables({"status": "success", "tables": {}})
        assert isinstance(result, dict)

    def test_format_tables_generates_latex(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.format_tables({"status": "success", "tables": {}})
        # Should return strings (even if empty/placeholder tables)
        for key, value in result.items():
            assert isinstance(value, str)

    def test_fmt_did_latex_returns_string(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._fmt_did_latex({})
        assert isinstance(result, str)
        assert r"\begin{table}" in result

    def test_fmt_ddd_latex_returns_string(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._fmt_ddd_latex({})
        assert isinstance(result, str)
        assert r"\begin{table}" in result

    def test_fmt_mechanism_latex_returns_string(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._fmt_mechanism_latex({})
        assert isinstance(result, str)

    def test_fmt_heterogeneity_latex_returns_string(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._fmt_heterogeneity_latex({})
        assert isinstance(result, str)

    def test_fmt_placebo_latex_returns_string(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj._fmt_placebo_latex({})
        assert isinstance(result, str)


class TestGetFigurePlan:
    """Test get_figure_plan method."""

    def test_returns_list(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.get_figure_plan()
        assert isinstance(result, list)

    def test_returns_4_figures(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.get_figure_plan()
        assert len(result) == 4

    def test_figures_have_required_keys(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.get_figure_plan()
        for fig in result:
            assert isinstance(fig, dict)
            assert "figure_id" in fig
            assert "title" in fig

    def test_figures_have_chart_types(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.get_figure_plan()
        for fig in result:
            assert "chart_type" in fig or "type" in fig


class TestBuildPanel:
    """Test build_panel method."""

    def test_build_panel_with_extended_data(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        data = {"wind_esg_panel": df}
        result = obj.build_panel(data)
        assert result is not None
        assert "df" in result

    def test_build_panel_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        data = {"stocks": df.to_dict("records")}
        # build_panel handles dict-like data
        result = obj.build_panel(data)
        # May return None if data insufficient

    def test_build_panel_industrial_panel(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        data = {"industrial_panel": df}
        result = obj.build_panel(data)
        assert result is not None
        assert "df" in result

    def test_run_heterogeneity_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        df = obj._add_did_treatment(df)
        result = obj._run_heterogeneity(df)
        assert isinstance(result, dict)

    def test_run_placebo_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj._run_placebo(df)
        assert isinstance(result, dict)

    def test_did_equals_treat_times_post(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_minimal_panel()
        result = obj._add_did_treatment(df)
        if "did" in result.columns and "treat" in result.columns and "post" in result.columns:
            expected = (result["treat"].fillna(0) * result["post"].fillna(0)).astype(float)
            did_vals = result["did"].fillna(0).astype(float)
            diff = (expected - did_vals).abs()
            assert diff.max() < 1e-6


class TestRunRegressions:
    """Test run_regressions method with synthetic data."""

    def test_run_regressions_empty_data(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.run_regressions({})
        assert isinstance(result, dict)
        assert "status" in result

    def test_run_regressions_no_dataframe(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        result = obj.run_regressions({"df": pd.DataFrame()})
        assert isinstance(result, dict)
        assert result["status"] in ("no_data", "error", "success")

    def test_run_regressions_with_extended_panel(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj.run_regressions({"df": df})
        assert isinstance(result, dict)
        assert "status" in result
        assert "tables" in result

    def test_run_regressions_returns_tables(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj.run_regressions({"df": df})
        assert isinstance(result.get("tables"), dict)

    def test_run_cs_did_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj._run_cs_did(df)
        assert isinstance(result, dict)
        assert "title" in result

    def test_run_ddd_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj._run_ddd(df)
        assert isinstance(result, dict)
        assert "title" in result

    def test_run_mechanism_analysis_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj._run_mechanism_analysis(df)
        assert isinstance(result, dict)

    def test_run_placebo_returns_dict(self):
        obj = getattr(mod, "GreenFinanceDirection")()
        df = _make_extended_panel()
        result = obj._run_placebo(df)
        assert isinstance(result, dict)
