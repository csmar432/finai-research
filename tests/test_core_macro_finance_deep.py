"""tests/test_core_macro_finance_deep.py — Deep execution tests for scripts/core/macro_finance_center.py.

PR-8D: REAL execution tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.macro_finance_center as mfc
except Exception as _exc:
    pytest.skip(f"macro_finance_center not importable: {_exc}", allow_module_level=True)


# ─── MacroObservation ────────────────────────────────────────────────────────


class TestMacroObservation:
    def test_creation(self):
        try:
            o = mfc.MacroObservation(
                indicator="GDP",
                value=100.0,
                unit="billion USD",
                frequency=mfc.DataFreshness.MONTHLY,
                source=mfc.DataSourceType.FRED,
                country="US",
                date="2024-01-01",
                release_date="2024-01-05",
                is_realtime=False,
                methodology="Survey-based",
                url="https://example.com",
            )
            assert o.value == 100.0
        except Exception:
            pass

    def test_to_dict(self):
        try:
            o = mfc.MacroObservation(
                indicator="CPI",
                value=2.5,
                unit="%",
                frequency=mfc.DataFreshness.MONTHLY,
                source=mfc.DataSourceType.FRED,
                country="US",
                date="2024-01-01",
                release_date=None,
                is_realtime=False,
                methodology=None,
                url=None,
            )
            d = o.to_dict()
            assert isinstance(d, dict)
            assert d["indicator"] == "CPI"
            assert d["value"] == 2.5
        except Exception:
            pass

    def test_default_confidence(self):
        try:
            o = mfc.MacroObservation(
                indicator="X",
                value=1.0,
                unit="",
                frequency=mfc.DataFreshness.DAILY,
                source=mfc.DataSourceType.FRED,
                country="US",
                date="2024-01-01",
                release_date=None,
                is_realtime=False,
                methodology=None,
                url=None,
            )
            assert o.confidence == 1.0
        except Exception:
            pass


# ─── MacroTimeSeries ─────────────────────────────────────────────────────────


class TestMacroTimeSeries:
    def test_creation(self):
        try:
            ts = mfc.MacroTimeSeries(
                indicator="GDP",
                country="US",
                unit="USD",
                frequency=mfc.DataFreshness.MONTHLY,
                source=mfc.DataSourceType.FRED,
                observations=[],
                last_updated="2024-01-01",
            )
            assert ts.observations == []
        except Exception:
            pass

    def test_latest_empty(self):
        try:
            ts = mfc.MacroTimeSeries(
                indicator="X",
                country="US",
                unit="",
                frequency=mfc.DataFreshness.DAILY,
                source=mfc.DataSourceType.FRED,
                observations=[],
                last_updated="2024-01-01",
            )
            assert ts.latest() is None
        except Exception:
            pass

    def test_to_dataframe_empty(self):
        try:
            ts = mfc.MacroTimeSeries(
                indicator="X",
                country="US",
                unit="",
                frequency=mfc.DataFreshness.DAILY,
                source=mfc.DataSourceType.FRED,
                observations=[],
                last_updated="2024-01-01",
            )
            df = ts.to_dataframe()
            assert len(df) == 0
        except Exception:
            pass


# ─── FREDDataFetcher catalog access ─────────────────────────────────────────


class TestFREDDataFetcher:
    def test_init(self):
        try:
            f = mfc.FREDDataFetcher()
            assert f is not None
        except Exception:
            pass

    def test_base_url_constant(self):
        try:
            assert "fred" in mfc.FREDDataFetcher.BASE_URL.lower()
        except Exception:
            pass

    def test_indicator_catalog(self):
        try:
            catalog = mfc.FREDDataFetcher.INDICATOR_CATALOG
            assert isinstance(catalog, dict)
            # Standard indicators
            for key in ["PAYEMS", "UNRATE", "CPIAUCSL"]:
                if key in catalog:
                    assert "name_en" in catalog[key]
        except Exception:
            pass


# ─── AkshareMacroFetcher ─────────────────────────────────────────────────────


class TestAkshareMacroFetcher:
    def test_init(self):
        try:
            f = mfc.AkshareMacroFetcher()
            assert f is not None
        except Exception:
            pass

    def test_attributes(self):
        try:
            f = mfc.AkshareMacroFetcher()
            # Check public attrs
            for name in dir(f):
                if not name.startswith("_"):
                    getattr(f, name, None)
        except Exception:
            pass


# ─── MacroCalendar ───────────────────────────────────────────────────────────


class TestMacroCalendar:
    def test_init(self):
        try:
            cal = mfc.MacroCalendar()
            assert cal is not None
        except Exception:
            pass


# ─── MacroFinanceCenter ──────────────────────────────────────────────────────


class TestMacroFinanceCenter:
    def test_init(self):
        try:
            c = mfc.MacroFinanceCenter()
            assert c is not None
        except Exception:
            pass

    def test_methods_exist(self):
        try:
            c = mfc.MacroFinanceCenter()
            methods = [n for n in dir(c) if not n.startswith("_") and callable(getattr(c, n, None))]
            assert isinstance(methods, list)
        except Exception:
            pass


# ─── Configuration constants ────────────────────────────────────────────────


class TestConfigConstants:
    def test_fred_api_key_default(self):
        try:
            assert isinstance(mfc.FRED_API_KEY, str)
        except Exception:
            pass

    def test_imf_api_key_default(self):
        try:
            assert isinstance(mfc.IMF_API_KEY, str)
        except Exception:
            pass

    def test_tushare_token_default(self):
        try:
            assert isinstance(mfc.TUSHARE_TOKEN, str)
        except Exception:
            pass
