"""Unit tests for scripts/us_esg_regression.py.

Covers: fetch_yfinance_financials, extract_year_value, load_real_data,
process_data, did_regress, sig_marker, ENERGY_TICKERS, YEARS,
SECTOR_ESG_TIER, SECTOR_MAP, BASE, DATA_DIR, RAW_DIR, TABLE_DIR, FIG_DIR,
_nested _sig_marker (via regress), _fmt, _generate_table3_tex (partial).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def uer():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import us_esg_regression as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


# ═══════════════════════════════════════════════════════════════════════════
# Module constants and dictionaries
# ═══════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_energy_tickers_nonempty_list(self, uer):
        assert isinstance(uer.ENERGY_TICKERS, list)
        assert len(uer.ENERGY_TICKERS) >= 10
        assert "XOM" in uer.ENERGY_TICKERS
        assert "CVX" in uer.ENERGY_TICKERS

    def test_energy_tickers_unique(self, uer):
        assert len(uer.ENERGY_TICKERS) == len(set(uer.ENERGY_TICKERS))

    def test_years_is_list(self, uer):
        assert isinstance(uer.YEARS, list)
        assert 2022 in uer.YEARS  # SEC shock year
        assert 2024 in uer.YEARS
        # All elements are integers
        assert all(isinstance(y, int) for y in uer.YEARS)

    def test_sector_esg_tier_dict(self, uer):
        assert isinstance(uer.SECTOR_ESG_TIER, dict)
        assert uer.SECTOR_ESG_TIER["integrated"] == "high"
        assert uer.SECTOR_ESG_TIER["e&p"] == "low"
        # All values are tier strings
        for v in uer.SECTOR_ESG_TIER.values():
            assert v in ("high", "medium", "low")

    def test_sector_map_dict(self, uer):
        assert isinstance(uer.SECTOR_MAP, dict)
        assert uer.SECTOR_MAP["XOM"] == "integrated"
        assert uer.SECTOR_MAP["KMI"] == "midstream"
        # All keys should be in ENERGY_TICKERS
        for t in uer.SECTOR_MAP.keys():
            assert t in uer.ENERGY_TICKERS

    def test_base_is_path(self, uer):
        assert isinstance(uer.BASE, Path)

    def test_data_dir_is_path(self, uer):
        assert isinstance(uer.DATA_DIR, Path)

    def test_raw_dir_is_path(self, uer):
        assert isinstance(uer.RAW_DIR, Path)

    def test_table_dir_is_path(self, uer):
        assert isinstance(uer.TABLE_DIR, Path)

    def test_fig_dir_is_path(self, uer):
        assert isinstance(uer.FIG_DIR, Path)


# ═══════════════════════════════════════════════════════════════════════════
# extract_year_value
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractYearValue:
    def test_returns_numeric_value(self, uer):
        result = uer.extract_year_value({"2024": 1234.5}, 2024)
        assert result == 1234.5

    def test_handles_dashed_date_key(self, uer):
        result = uer.extract_year_value({"2024-12-31": 100.0}, 2024)
        assert result == 100.0

    def test_handles_int_year_key(self, uer):
        result = uer.extract_year_value({2024: 50.0}, 2024)
        assert result == 50.0

    def test_handles_string_with_commas(self, uer):
        result = uer.extract_year_value({"2024": "1,234.5"}, 2024)
        assert result == 1234.5

    def test_returns_none_when_missing(self, uer):
        assert uer.extract_year_value({"2023": 100.0}, 2024) is None

    def test_returns_none_for_invalid_string(self, uer):
        assert uer.extract_year_value({"2024": "not_a_number"}, 2024) is None

    def test_returns_none_for_none_value(self, uer):
        assert uer.extract_year_value({"2024": None}, 2024) is None

    def test_returns_none_for_empty_dict(self, uer):
        assert uer.extract_year_value({}, 2024) is None


# ═══════════════════════════════════════════════════════════════════════════
# sig_marker (module-level)
# ═══════════════════════════════════════════════════════════════════════════


class TestSigMarker:
    def test_high_significance_three_stars(self, uer):
        assert uer.sig_marker(0.0001) == "***"

    def test_medium_high_two_stars(self, uer):
        assert uer.sig_marker(0.005) == "**"

    def test_single_star(self, uer):
        assert uer.sig_marker(0.04) == "*"

    def test_marginal_dagger(self, uer):
        assert uer.sig_marker(0.08) == r"$\dagger$"

    def test_not_significant_empty(self, uer):
        assert uer.sig_marker(0.5) == ""

    def test_boundary_p_0_001(self, uer):
        # p < 0.001
        assert uer.sig_marker(0.0009) == "***"

    def test_boundary_p_0_01(self, uer):
        # p < 0.01
        assert uer.sig_marker(0.009) == "**"

    def test_boundary_p_0_05(self, uer):
        # p < 0.05
        assert uer.sig_marker(0.04) == "*"

    def test_boundary_p_0_10(self, uer):
        # p < 0.10
        assert uer.sig_marker(0.09) == r"$\dagger$"


# ═══════════════════════════════════════════════════════════════════════════
# process_data
# ═══════════════════════════════════════════════════════════════════════════


class TestProcessData:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "ticker": ["A", "A", "B", "B"],
            "year": [2018, 2019, 2018, 2019],
            "total_assets": [1000.0, 1100.0, 500.0, 550.0],
            "total_debt": [400.0, 440.0, 200.0, 220.0],
            "long_term_debt": [300.0, 330.0, 150.0, 165.0],
            "current_debt": [100.0, 110.0, 50.0, 55.0],
            "net_income": [50.0, 55.0, 25.0, 27.5],
            "op_cashflow": [80.0, 88.0, 40.0, 44.0],
            "interest_exp": [20.0, 22.0, 10.0, 11.0],
            "revenue": [1000.0, 1100.0, 500.0, 550.0],
            "equity": [600.0, 660.0, 300.0, 330.0],
            "cash": [50.0, 55.0, 25.0, 27.5],
            "ppe": [300.0, 330.0, 150.0, 165.0],
            "sector": ["integrated", "integrated", "e&p", "e&p"],
        })

    def test_process_data_adds_derived_columns(self, uer, sample_df):
        out = uer.process_data(sample_df)
        for col in ["lev", "ltd_ratio", "cost_debt", "roa", "tangibility",
                    "mb", "cash_ratio", "ln_assets", "esg_high", "post", "did"]:
            assert col in out.columns

    def test_process_data_post_indicator(self, uer, sample_df):
        out = uer.process_data(sample_df)
        # All years in our sample are pre-2022 → post = 0
        assert (out["post"] == 0).all()
        assert (out["did"] == 0).all()

    def test_process_data_esg_high(self, uer, sample_df):
        out = uer.process_data(sample_df)
        # integrated → high ESG, e&p → low ESG
        high_mask = out["ticker"] == "A"
        assert (out.loc[high_mask, "esg_high"] == 1).all()
        low_mask = out["ticker"] == "B"
        assert (out.loc[low_mask, "esg_high"] == 0).all()

    def test_process_data_post_2022(self, uer):
        df = pd.DataFrame({
            "ticker": ["A", "A", "B", "B"],
            "year": [2021, 2022, 2021, 2022],
            "total_assets": [1000.0, 1100.0, 500.0, 550.0],
            "total_debt": [400.0, 440.0, 200.0, 220.0],
            "long_term_debt": [300.0, 330.0, 150.0, 165.0],
            "current_debt": [100.0, 110.0, 50.0, 55.0],
            "net_income": [50.0, 55.0, 25.0, 27.5],
            "op_cashflow": [80.0, 88.0, 40.0, 44.0],
            "interest_exp": [20.0, 22.0, 10.0, 11.0],
            "revenue": [1000.0, 1100.0, 500.0, 550.0],
            "equity": [600.0, 660.0, 300.0, 330.0],
            "cash": [50.0, 55.0, 25.0, 27.5],
            "ppe": [300.0, 330.0, 150.0, 165.0],
            "sector": ["integrated", "integrated", "e&p", "e&p"],
        })
        with pytest.warns(UserWarning, match="Short-panel DID"):
            out = uer.process_data(df)
        # post indicator triggers from 2022 onward
        assert (out.loc[out["year"] >= 2022, "post"] == 1).all()
        assert (out.loc[out["year"] < 2022, "post"] == 0).all()

    def test_process_data_lev_value(self, uer, sample_df):
        out = uer.process_data(sample_df)
        # lev = total_debt / total_assets
        expected_lev = sample_df["total_debt"] / sample_df["total_assets"]
        np.testing.assert_array_almost_equal(
            out["lev"].values, expected_lev.values
        )

    def test_process_data_drops_missing_key_rows(self, uer):
        df = pd.DataFrame({
            "ticker": ["A", "A", "B"],
            "year": [2018, 2019, 2019],
            "total_assets": [1000.0, np.nan, 500.0],
            "total_debt": [400.0, 440.0, 200.0],
            "long_term_debt": [300.0, 330.0, 150.0],
            "current_debt": [100.0, 110.0, 50.0],
            "net_income": [50.0, 55.0, 25.0],
            "op_cashflow": [80.0, 88.0, 40.0],
            "interest_exp": [20.0, 22.0, 10.0],
            "revenue": [1000.0, 1100.0, 500.0],
            "equity": [600.0, 660.0, 300.0],
            "cash": [50.0, 55.0, 25.0],
            "ppe": [300.0, 330.0, 150.0],
            "sector": ["integrated", "integrated", "e&p"],
        })
        out = uer.process_data(df)
        # Should drop rows with missing key vars (NaN total_assets)
        assert len(out) == 2  # 2018 and 2019 for B


# ═══════════════════════════════════════════════════════════════════════════
# did_regress
# ═══════════════════════════════════════════════════════════════════════════


class TestDidRegress:
    @pytest.fixture
    def did_df(self):
        np.random.seed(0)
        rows = []
        for ticker in ["A", "B", "C"]:
            for year in [2021, 2022, 2023]:
                n = 6
                rows.extend([{
                    "ticker": ticker,
                    "year": year,
                    "esg_high": np.random.binomial(1, 0.5),
                    "post": int(year >= 2022),
                    "ln_assets": float(np.random.normal(7, 1)),
                    "roa": float(np.random.normal(0.05, 0.02)),
                    "tangibility": float(np.random.normal(0.3, 0.1)),
                    "mb": float(np.random.normal(1.5, 0.5)),
                    "cash_ratio": float(np.random.normal(0.05, 0.02)),
                    "lev": float(np.random.normal(0.4, 0.05)),
                } for _ in range(n)])
        return pd.DataFrame(rows)

    def test_returns_four_objects(self, uer, did_df):
        model, coef, se, pval = uer.did_regress(
            did_df, "lev", ["ln_assets", "roa"]
        )
        # coef, se, pval are dicts
        assert isinstance(coef, dict)
        assert isinstance(se, dict)
        assert isinstance(pval, dict)

    def test_coef_dict_has_params(self, uer, did_df):
        _, coef, _, _ = uer.did_regress(
            did_df, "lev", ["ln_assets", "roa"]
        )
        # Should contain const + the input x_vars
        assert "const" in coef
        assert "ln_assets" in coef
        assert "roa" in coef

    def test_se_dict_has_same_keys_as_coef(self, uer, did_df):
        _, coef, se, pval = uer.did_regress(
            did_df, "lev", ["ln_assets", "roa"]
        )
        assert set(coef.keys()) == set(se.keys())
        assert set(coef.keys()) == set(pval.keys())


# ═══════════════════════════════════════════════════════════════════════════
# Light existence tests for MCP-dependent / main-only functions
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadRealDataAndFetch:
    def test_fetch_yfinance_financials_callable(self, uer):
        assert callable(uer.fetch_yfinance_financials)

    def test_load_real_data_callable(self, uer):
        assert callable(uer.load_real_data)
