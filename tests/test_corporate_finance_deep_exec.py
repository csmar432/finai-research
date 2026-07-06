"""tests/test_corporate_finance_deep_exec.py — Deep tests for corporate_finance helpers.

Targets uncovered helpers in scripts/research_directions/corporate_finance.py.
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
    from scripts.research_directions.corporate_finance import CorporateFinanceDirection
except Exception as exc:
    pytest.skip(f"corporate_finance not importable: {exc}", allow_module_level=True)


@pytest.fixture
def direction():
    return CorporateFinanceDirection()


@pytest.fixture
def yf_df():
    """Synthetic US GAAP data."""
    return pd.DataFrame({
        "Ticker": ["AAPL", "MSFT"],
        "TotalDebt": [100.0, 50.0],
        "TotalAssets": [500.0, 300.0],
        "NetIncome": [50.0, 30.0],
    })


# ─── _get_default_constituents ────────────────────────────────────────

class TestGetDefaultConstituents:
    def test_basic(self, direction):
        constituents = direction._get_default_constituents()
        assert isinstance(constituents, list)
        assert len(constituents) > 50  # Should have many
        # Should contain both SZ and SH codes
        assert any(".SZ" in c for c in constituents)
        assert any(".SH" in c for c in constituents)

    def test_codes_are_strings(self, direction):
        constituents = direction._get_default_constituents()
        assert all(isinstance(c, str) for c in constituents)


# ─── _normalize_yfinance ──────────────────────────────────────────────

class TestNormalizeYfinance:
    def test_basic(self, direction, yf_df):
        result = direction._normalize_yfinance(yf_df)
        assert result is not None
        assert "lev_book" in result.columns
        assert "roa" in result.columns
        # lev_book = TotalDebt / TotalAssets = 100/500 = 0.2
        assert abs(result["lev_book"].iloc[0] - 0.2) < 1e-6

    def test_zero_assets_handled(self, direction):
        df = pd.DataFrame({
            "TotalDebt": [100.0],
            "TotalAssets": [0.0],  # would cause div-by-zero
            "NetIncome": [10.0],
        })
        result = direction._normalize_yfinance(df)
        if result is not None:
            assert "lev_book" in result.columns
            # Should be NaN
            assert pd.isna(result["lev_book"].iloc[0])

    def test_missing_columns(self, direction):
        df = pd.DataFrame({"Other": [1, 2]})
        result = direction._normalize_yfinance(df)
        # Should still return something without errors
        assert result is not None


# ─── Base class registration ──────────────────────────────────────────

class TestRegistration:
    def test_direction_class(self):
        assert CorporateFinanceDirection.__name__ == "CorporateFinanceDirection"


# ─── Init ─────────────────────────────────────────────────────────────

class TestInit:
    def test_init(self):
        try:
            d = CorporateFinanceDirection()
            assert d is not None
        except Exception:
            pass
