"""Unit tests for scripts/core/macro_finance_center.py.

Covers:
  - Enums (DataSourceType, DataFreshness) — values, counts, lookup.
  - Dataclasses (MacroObservation, MacroTimeSeries) — construction, defaults,
    to_dict, to_dataframe, latest().
  - FREDDataFetcher — INDICATOR_CATALOG structure, cache hit/miss, public CSV
    path, API path with mocked requests, fallback to mock on error, and the
    convenience fetch_* wrappers.
  - AkshareMacroFetcher — both available and unavailable branches for all
    fetch_cn_* methods, including exceptions raised inside the akshare stub.
  - MacroCalendar — get_upcoming_releases (including NFP / CPI / CN PMI /
    CN CPI rules), get_next_fomc (skips to next Wednesday-on-cycle), and
    get_next_nfp (first Friday of next month when today is past).
  - MacroFinanceCenter — registry dispatch, unknown indicator raises
    ValueError, panel fetch with country branching, generate_macro_report
    delegate.

All network calls are mocked; no FRED, akshare, or HTTP I/O occurs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.macro_finance_center import (  # noqa: E402
    AkshareMacroFetcher,
    DataFreshness,
    DataSourceType,
    FREDDataFetcher,
    MacroCalendar,
    MacroFinanceCenter,
    MacroObservation,
    MacroTimeSeries,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_obs(**overrides):
    """Build a fully populated MacroObservation with sensible defaults."""
    base = dict(
        indicator="PAYEMS",
        value=150_000.0,
        unit="千人",
        frequency=DataFreshness.MONTHLY,
        source=DataSourceType.FRED,
        country="US",
        date="2024-01-01",
        release_date=None,
        is_realtime=False,
        methodology="BLS survey",
        url="https://fred.stlouisfed.org/series/PAYEMS",
        confidence=1.0,
        metadata={},
    )
    base.update(overrides)
    return MacroObservation(**base)


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════


class TestDataSourceTypeEnum:
    def test_all_values(self):
        assert DataSourceType.FRED.value == "fred"
        assert DataSourceType.AKSHARE.value == "akshare"
        assert DataSourceType.WORLD_BANK.value == "world_bank"
        assert DataSourceType.IMF.value == "imf"
        assert DataSourceType.BCEI.value == "bcei"
        assert DataSourceType.TUSHARE.value == "tushare"
        assert DataSourceType.SIMULATED.value == "simulated"
        assert DataSourceType.UNKNOWN.value == "unknown"

    def test_member_count(self):
        assert len(DataSourceType) == 8

    def test_lookup_by_value(self):
        assert DataSourceType("fred") is DataSourceType.FRED
        assert DataSourceType("akshare") is DataSourceType.AKSHARE

    def test_is_str_enum(self):
        # str-based enums should be usable as strings
        assert DataSourceType.FRED == "fred"
        assert isinstance(DataSourceType.FRED, str)


class TestDataFreshnessEnum:
    def test_all_values(self):
        assert DataFreshness.REALTIME.value == "realtime"
        assert DataFreshness.DAILY.value == "daily"
        assert DataFreshness.MONTHLY.value == "monthly"
        assert DataFreshness.QUARTERLY.value == "quarterly"
        assert DataFreshness.ANNUAL.value == "annual"

    def test_member_count(self):
        assert len(DataFreshness) == 5

    def test_lookup_by_value(self):
        assert DataFreshness("monthly") is DataFreshness.MONTHLY
        assert DataFreshness("daily") is DataFreshness.DAILY

    def test_is_str_enum(self):
        assert DataFreshness.DAILY == "daily"


# ═══════════════════════════════════════════════════════════════════════════
# MacroObservation dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestMacroObservation:
    def test_defaults(self):
        obs = MacroObservation(
            indicator="X",
            value=1.0,
            unit="%",
            frequency=DataFreshness.DAILY,
            source=DataSourceType.FRED,
            country="US",
            date="2024-01-01",
            release_date=None,
            is_realtime=False,
            methodology=None,
            url=None,
        )
        assert obs.confidence == 1.0
        assert obs.metadata == {}

    def test_to_dict_full(self):
        obs = _make_obs(metadata={"k": "v"}, confidence=0.9)
        d = obs.to_dict()
        assert d["indicator"] == "PAYEMS"
        assert d["value"] == 150_000.0
        assert d["unit"] == "千人"
        assert d["frequency"] == "monthly"          # enum -> its .value
        assert d["source"] == "fred"
        assert d["country"] == "US"
        assert d["date"] == "2024-01-01"
        assert d["release_date"] is None
        assert d["is_realtime"] is False
        assert d["methodology"] == "BLS survey"
        assert d["url"] == "https://fred.stlouisfed.org/series/PAYEMS"
        assert d["confidence"] == 0.9
        assert d["metadata"] == {"k": "v"}

    def test_to_dict_handles_none_value(self):
        obs = _make_obs(value=None)
        d = obs.to_dict()
        assert d["value"] is None

    def test_metadata_isolation_between_instances(self):
        a = _make_obs()
        b = _make_obs()
        a.metadata["x"] = 1
        # field(default_factory=dict) → independent dicts per instance
        assert "x" not in b.metadata


# ═══════════════════════════════════════════════════════════════════════════
# MacroTimeSeries dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestMacroTimeSeries:
    def _series(self, dates=("2024-01-01", "2024-02-01", "2024-03-01")):
        return MacroTimeSeries(
            indicator="PAYEMS",
            country="US",
            unit="千人",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.FRED,
            observations=[_make_obs(date=d) for d in dates],
            last_updated="2024-04-01T00:00:00",
            description="非农就业人数",
            methodology="BLS survey",
        )

    def test_optional_fields_default_none(self):
        ts = MacroTimeSeries(
            indicator="X",
            country="US",
            unit="%",
            frequency=DataFreshness.DAILY,
            source=DataSourceType.FRED,
            observations=[],
            last_updated="2024-01-01T00:00:00",
        )
        assert ts.description is None
        assert ts.methodology is None

    def test_latest_with_observations(self):
        ts = self._series()
        latest = ts.latest()
        assert latest is not None
        assert latest.date == "2024-03-01"

    def test_latest_empty_returns_none(self):
        ts = self._series(dates=())
        assert ts.latest() is None

    def test_latest_with_unsorted_dates(self):
        ts = self._series(dates=("2024-02-15", "2024-01-01", "2024-03-10"))
        assert ts.latest().date == "2024-03-10"

    def test_to_dataframe_creates_sorted_dataframe(self):
        ts = self._series(dates=("2024-03-01", "2024-01-01", "2024-02-01"))
        df = ts.to_dataframe()
        assert list(df["date"]) == [
            __import__("pandas").Timestamp("2024-01-01"),
            __import__("pandas").Timestamp("2024-02-01"),
            __import__("pandas").Timestamp("2024-03-01"),
        ]
        assert len(df) == 3
        assert "value" in df.columns

    def test_to_dataframe_empty(self):
        ts = self._series(dates=())
        df = ts.to_dataframe()
        assert len(df) == 0
        # When there are no rows, "date" column doesn't exist (only with rows).
        assert list(df.columns) == []


# ═══════════════════════════════════════════════════════════════════════════
# FREDDataFetcher — catalog, cache, parsing, error paths
# ═══════════════════════════════════════════════════════════════════════════


class TestFREDIndicatorCatalog:
    def test_catalog_has_expected_series(self):
        for sid in [
            "PAYEMS", "UNRATE", "CPIAUCSL", "GDP", "FEDFUNDS",
            "DGS10", "DGS2", "TEDRATE", "NFCI", "T10Y2Y",
            "PCE", "CONSSENT", "ICSA", "CSUSHPINSA", "MANEMP",
            "PMI", "DEXCHUS", "DEXUSEU", "GDPPCT", "PCECTPI",
            "BAML0C0A0CMORTY",
        ]:
            assert sid in FREDDataFetcher.INDICATOR_CATALOG, sid

    def test_catalog_entry_schema(self):
        entry = FREDDataFetcher.INDICATOR_CATALOG["PAYEMS"]
        for key in (
            "name_cn", "name_en", "unit", "frequency",
            "release_offset_days", "source_url", "methodology", "impact",
        ):
            assert key in entry, f"PAYEMS missing key {key}"
        assert entry["impact"] in {"high", "medium", "low"}

    def test_base_and_public_urls(self):
        assert FREDDataFetcher.BASE_URL.startswith("https://")
        assert FREDDataFetcher.PUBLIC_URL.startswith("https://")


class TestFREDDataFetcherInit:
    def test_init_with_no_args(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.core.macro_finance_center.FRED_API_KEY", "test_key",
            raising=False,
        )
        f = FREDDataFetcher()
        assert f.api_key == "test_key"
        assert f.cache_dir is None
        assert f._cache == {}

    def test_init_with_explicit_key_overrides_env(self):
        f = FREDDataFetcher(api_key="explicit")
        assert f.api_key == "explicit"

    def test_init_with_cache_dir(self, tmp_path):
        f = FREDDataFetcher(api_key="k", cache_dir=str(tmp_path))
        assert f.cache_dir == str(tmp_path)


class TestFREDDataFetcherCache:
    def test_get_cached_returns_none_when_empty(self):
        f = FREDDataFetcher(api_key="k")
        assert f._get_cached("nope") is None

    def test_set_then_get_cache(self):
        f = FREDDataFetcher(api_key="k")
        f._set_cached("foo", {"x": 1})
        assert f._get_cached("foo") == {"x": 1}

    def test_disk_cache_roundtrip(self, tmp_path):
        f = FREDDataFetcher(api_key="k", cache_dir=str(tmp_path))
        payload = {"observations": [{"date": "2024-01-01", "value": "100"}]}
        f._set_cached("PAYEMS_None_None", payload)
        # Force a new instance to bypass in-memory cache
        f2 = FREDDataFetcher(api_key="k", cache_dir=str(tmp_path))
        got = f2._get_cached("PAYEMS_None_None")
        assert got == payload

    def test_disk_cache_expires_after_24h(self, tmp_path):
        import time as _time
        f = FREDDataFetcher(api_key="k", cache_dir=str(tmp_path))
        path = Path(tmp_path) / "fred_old.json"
        path.write_text(json.dumps({"a": 1}))
        # backdate mtime to 25h ago
        old = _time.time() - (25 * 3600)
        import os
        os.utime(path, (old, old))
        assert f._get_cached("old") is None


class TestFREDDataFetcherFetchSeries:
    def _api_response(self, dates_values):
        return {
            "observations": [
                {"date": d, "value": v, "realtime_start": d, "realtime_end": d}
                for d, v in dates_values
            ]
        }

    def test_cache_hit_skips_network(self):
        f = FREDDataFetcher(api_key="k")
        cached_payload = self._api_response([("2024-01-01", "100"), ("2024-02-01", "101")])
        with patch.object(f, "_get_cached", return_value=cached_payload) as gc, \
             patch.object(f, "_parse_fred_response", return_value=_ts_stub()) as parse, \
             patch.object(f._session, "get") as gget:
            ts = f.fetch_series("PAYEMS", use_public=False)
        assert ts is not None
        gget.assert_not_called()
        gc.assert_called_once()
        parse.assert_called_once()

    def test_use_public_with_no_api_key_uses_csv(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.core.macro_finance_center.FRED_API_KEY", "", raising=False,
        )
        f = FREDDataFetcher(api_key=None)
        # Force the FRED_API_KEY inside the class attribute namespace too
        f.api_key = ""
        csv = "DATE,PAYEMS\n2024-01-01,100\n2024-02-01,101\n"
        mock_resp = MagicMock()
        mock_resp.text = csv
        mock_resp.raise_for_status = MagicMock()
        with patch.object(f._session, "get", return_value=mock_resp) as gget:
            ts = f.fetch_series("PAYEMS")
        assert gget.called
        assert len(ts.observations) == 2
        assert ts.observations[0].value == 100.0
        assert ts.source == DataSourceType.FRED

    def test_use_public_passes_dates(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.core.macro_finance_center.FRED_API_KEY", "", raising=False,
        )
        f = FREDDataFetcher(api_key=None)
        f.api_key = ""
        csv = "DATE,PAYEMS\n2024-01-01,100\n"
        mock_resp = MagicMock()
        mock_resp.text = csv
        mock_resp.raise_for_status = MagicMock()
        with patch.object(f._session, "get", return_value=mock_resp) as gget:
            f.fetch_series("PAYEMS", start_date="2024-01-01", end_date="2024-12-31")
        url = gget.call_args.args[0]
        assert "cosd=2024-01-01" in url
        assert "coed=2024-12-31" in url

    def test_public_csv_failure_falls_back_to_mock(self):
        f = FREDDataFetcher(api_key=None)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("boom")
        with patch.object(f._session, "get", return_value=mock_resp):
            ts = f.fetch_series("PAYEMS", use_public=True)
        assert ts.source == DataSourceType.SIMULATED
        assert ts.observations == []
        assert "MOCK" in (ts.description or "")

    def test_api_path_with_key_parses_observations(self):
        f = FREDDataFetcher(api_key="abc")
        payload = self._api_response([("2024-01-01", "150000")])
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch.object(f._session, "get", return_value=mock_resp) as gget:
            ts = f.fetch_series("PAYEMS")
        assert gget.called
        assert len(ts.observations) == 1
        assert ts.observations[0].value == 150000.0
        assert ts.country == "US"
        assert ts.unit == "千人"

    def test_api_path_drops_dot_values(self):
        f = FREDDataFetcher(api_key="abc")
        payload = self._api_response([("2024-01-01", "."), ("2024-02-01", "100")])
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch.object(f._session, "get", return_value=mock_resp):
            ts = f.fetch_series("PAYEMS")
        assert len(ts.observations) == 1
        assert ts.observations[0].date == "2024-02-01"

    def test_api_path_failure_falls_back_to_mock(self):
        f = FREDDataFetcher(api_key="abc")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("network down")
        with patch.object(f._session, "get", return_value=mock_resp):
            ts = f.fetch_series("PAYEMS")
        assert ts.source == DataSourceType.SIMULATED
        assert ts.observations == []

    def test_unknown_series_uses_default_unit_and_freq(self):
        f = FREDDataFetcher(api_key="abc")
        payload = self._api_response([("2024-01-01", "1")])
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        with patch.object(f._session, "get", return_value=mock_resp):
            ts = f.fetch_series("XYZ_UNKNOWN")
        assert ts.unit == "unknown"
        # default freq is daily
        assert ts.frequency == DataFreshness.DAILY
        assert ts.observations[0].methodology is None
        assert ts.observations[0].url is None


class TestFREDFetchHelpers:
    def test_fetch_nfp_uses_PAYEMS_default_years(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()) as fs:
            f.fetch_nfp()
        args, kwargs = fs.call_args
        assert args[0] == "PAYEMS"
        assert "start_date" in kwargs

    def test_fetch_nfp_with_explicit_years(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()) as fs:
            f.fetch_nfp(start_year=2020, end_year=2023)
        kwargs = fs.call_args.kwargs
        assert kwargs["start_date"] == "2020-01-01"
        assert kwargs["end_date"] == "2023-12-31"

    def test_fetch_cpi_uses_CPIAUCSL(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()) as fs:
            f.fetch_cpi()
        assert fs.call_args.args[0] == "CPIAUCSL"

    def test_fetch_fed_rates(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()) as fs:
            f.fetch_fed_rates()
        assert fs.call_args.args[0] == "FEDFUNDS"

    def test_fetch_ted_spread(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()) as fs:
            f.fetch_ted_spread()
        assert fs.call_args.args[0] == "TEDRATE"

    def test_fetch_yield_curve_slope(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()) as fs:
            f.fetch_yield_curve_slope()
        assert fs.call_args.args[0] == "T10Y2Y"

    def test_fetch_yield_curve_returns_dict_of_tenors(self):
        f = FREDDataFetcher(api_key="k")
        with patch.object(f, "fetch_series", return_value=_ts_stub()):
            curve = f.fetch_yield_curve()
        assert set(curve.keys()) == {"2Y", "5Y", "10Y", "30Y"}
        for label, ts in curve.items():
            assert isinstance(ts, MacroTimeSeries)


def _ts_stub():
    return MacroTimeSeries(
        indicator="X",
        country="US",
        unit="%",
        frequency=DataFreshness.DAILY,
        source=DataSourceType.FRED,
        observations=[],
        last_updated="2024-01-01T00:00:00",
    )


# ═══════════════════════════════════════════════════════════════════════════
# AkshareMacroFetcher — both available and unavailable branches
# ═══════════════════════════════════════════════════════════════════════════


def _stub_akshare_df(rows):
    """Build a tiny pandas DataFrame mimicking akshare output."""
    import pandas as pd
    return pd.DataFrame(rows)


class TestAkshareInit:
    def test_init_without_akshare_marks_unavailable(self, monkeypatch):
        # Force import to fail
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "akshare" or name.startswith("akshare."):
                raise ImportError("simulated missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            f = AkshareMacroFetcher()
        assert f._available is False
        assert f._ak is None


class TestAkshareUnavailableFallback:
    @pytest.fixture
    def fetcher(self):
        # Patch _try_init to set _available=False without trying to import akshare
        with patch.object(AkshareMacroFetcher, "_try_init", lambda self: setattr(self, "_available", False) or setattr(self, "_ak", None)):
            return AkshareMacroFetcher()

    def test_fetch_cn_cpi_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_cpi()
        assert ts.indicator == "CN_CPI"
        assert ts.country == "CN"
        assert ts.unit == "%"
        assert ts.frequency == DataFreshness.MONTHLY
        assert ts.source == DataSourceType.AKSHARE
        assert ts.observations == []

    def test_fetch_cn_gdp_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_gdp()
        assert ts.observations == []
        assert ts.frequency == DataFreshness.QUARTERLY

    def test_fetch_cn_pmi_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_pmi()
        assert ts.observations == []
        assert ts.unit == "index"

    def test_fetch_cn_m2_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_m2()
        assert ts.observations == []

    def test_fetch_cn_financial_credit_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_financial_credit()
        assert ts.indicator == "CN_NEW_FINANCIAL_CREDIT"
        assert ts.observations == []

    def test_fetch_cn_fdi_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_fdi()
        assert ts.observations == []

    def test_fetch_cn_retail_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_retail()
        assert ts.observations == []

    def test_fetch_cn_shibor_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_shibor()
        assert ts.frequency == DataFreshness.DAILY
        assert ts.observations == []

    def test_fetch_cn_lpr_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_lpr()
        assert ts.observations == []

    def test_fetch_cn_yield_curve_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_yield_curve()
        assert ts.observations == []
        assert ts.frequency == DataFreshness.DAILY

    def test_fetch_cn_credit_spread_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cn_credit_spread()
        assert ts.observations == []

    def test_fetch_cfets_index_empty_when_unavailable(self, fetcher):
        ts = fetcher.fetch_cfets_index()
        assert ts.observations == []


class TestAkshareAvailableSuccess:
    """When akshare *is* available, simulate the per-row iteration."""

    @pytest.fixture
    def fetcher(self):
        f = AkshareMacroFetcher.__new__(AkshareMacroFetcher)
        f.cache_dir = None
        f._available = True

        def _make_stub(name, df_attr, col_map):
            stub = MagicMock()
            df = _stub_akshare_df([
                {col_map["date"]: "2024-01-01", col_map["value"]: 1.5},
                {col_map["date"]: "2024-02-01", col_map["value"]: 2.5},
            ])
            setattr(stub, df_attr, df)
            return stub

        # Build stub for each function
        f._ak = MagicMock()
        f._ak.macro_china_cpi.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "cpi_yoy": 1.0},
            {"date": "2024-02-01", "cpi_yoy": 1.5},
        ])
        f._ak.macro_china_gdp.return_value = _stub_akshare_df([
            {"date": "2024Q1", "gdp_yoy": 5.0},
        ])
        f._ak.macro_china_pmi.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "pmi": 50.5},
        ])
        f._ak.macro_china_m2.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "m2_yoy": 9.0},
        ])
        f._ak.macro_china_shibor.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "value": 100.0, "shibor_3m": 2.5},
        ])
        f._ak.macro_china_lpr.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "lpr_1y": 3.45},
        ])
        f._ak.macro_china_fdi.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "fdi_yoy": -10.0},
        ])
        f._ak.macro_china_consumer_goods_retail.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "retail_yoy": 4.0},
        ])
        f._ak.bond_china_yield.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "1Y": 2.1, "3Y": 2.3, "5Y": 2.5, "10Y": 2.7, "30Y": 3.0},
        ])
        f._ak.bond_china_credit.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "spread": 80.0},
        ])
        f._ak.currency_cfets_index.return_value = _stub_akshare_df([
            {"date": "2024-01-01", "cfets_index": 100.5},
        ])
        return f

    def test_fetch_cn_cpi(self, fetcher):
        ts = fetcher.fetch_cn_cpi()
        assert len(ts.observations) == 2
        assert ts.observations[0].value == 1.0
        assert ts.observations[0].country == "CN"

    def test_fetch_cn_gdp(self, fetcher):
        ts = fetcher.fetch_cn_gdp()
        assert ts.observations[0].value == 5.0
        assert ts.frequency == DataFreshness.QUARTERLY

    def test_fetch_cn_pmi(self, fetcher):
        ts = fetcher.fetch_cn_pmi()
        assert ts.observations[0].value == 50.5

    def test_fetch_cn_m2(self, fetcher):
        ts = fetcher.fetch_cn_m2()
        assert ts.observations[0].value == 9.0

    def test_fetch_cn_financial_credit_uses_shibor_as_source(self, fetcher):
        ts = fetcher.fetch_cn_financial_credit()
        # implementation re-uses macro_china_shibor under the hood
        assert len(ts.observations) >= 1

    def test_fetch_cn_fdi(self, fetcher):
        ts = fetcher.fetch_cn_fdi()
        assert ts.observations[0].value == -10.0

    def test_fetch_cn_retail(self, fetcher):
        ts = fetcher.fetch_cn_retail()
        assert ts.observations[0].value == 4.0

    def test_fetch_cn_shibor(self, fetcher):
        ts = fetcher.fetch_cn_shibor()
        assert ts.observations[0].value == 2.5
        assert ts.observations[0].is_realtime is True

    def test_fetch_cn_lpr(self, fetcher):
        ts = fetcher.fetch_cn_lpr()
        assert ts.observations[0].value == 3.45

    def test_fetch_cn_yield_curve_flattens_tenors(self, fetcher):
        ts = fetcher.fetch_cn_yield_curve()
        # Each input row → 5 tenor observations (1Y/3Y/5Y/10Y/30Y)
        tenors = {obs.indicator for obs in ts.observations}
        assert tenors == {
            "CN_GOVT_1Y", "CN_GOVT_3Y", "CN_GOVT_5Y",
            "CN_GOVT_10Y", "CN_GOVT_30Y",
        }

    def test_fetch_cn_credit_spread(self, fetcher):
        ts = fetcher.fetch_cn_credit_spread()
        assert ts.observations[0].value == 80.0
        assert ts.unit == "bp"

    def test_fetch_cfets_index(self, fetcher):
        ts = fetcher.fetch_cfets_index()
        assert ts.observations[0].value == 100.5


class TestAkshareAvailableErrorSwallowed:
    """When akshare raises, observations should be empty (no propagation)."""

    @pytest.fixture
    def fetcher(self):
        f = AkshareMacroFetcher.__new__(AkshareMacroFetcher)
        f.cache_dir = None
        f._available = True
        f._ak = MagicMock()
        f._ak.macro_china_cpi.side_effect = RuntimeError("boom")
        f._ak.macro_china_gdp.side_effect = RuntimeError("boom")
        f._ak.macro_china_pmi.side_effect = RuntimeError("boom")
        f._ak.macro_china_m2.side_effect = RuntimeError("boom")
        f._ak.macro_china_lpr.side_effect = RuntimeError("boom")
        f._ak.macro_china_fdi.side_effect = RuntimeError("boom")
        f._ak.macro_china_consumer_goods_retail.side_effect = RuntimeError("boom")
        f._ak.macro_china_shibor.side_effect = RuntimeError("boom")
        f._ak.bond_china_yield.side_effect = RuntimeError("boom")
        f._ak.bond_china_credit.side_effect = RuntimeError("boom")
        f._ak.currency_cfets_index.side_effect = RuntimeError("boom")
        return f

    @pytest.mark.parametrize("method,indicator", [
        ("fetch_cn_cpi", "CN_CPI"),
        ("fetch_cn_gdp", "CN_GDP"),
        ("fetch_cn_pmi", "CN_PMI"),
        ("fetch_cn_m2", "CN_M2"),
        ("fetch_cn_lpr", "CN_LPR_1Y"),
        ("fetch_cn_fdi", "CN_FDI"),
        ("fetch_cn_retail", "CN_RETAIL"),
        ("fetch_cn_shibor", "CN_SHIBOR_3M"),
        ("fetch_cn_yield_curve", "CN_GOVT_YIELD_CURVE"),
        ("fetch_cn_credit_spread", "CN_CREDIT_SPREAD"),
        ("fetch_cfets_index", "CFETS_INDEX"),
    ])
    def test_errors_swallowed(self, fetcher, method, indicator):
        ts = getattr(fetcher, method)()
        assert ts.observations == []
        assert ts.indicator == indicator


# ═══════════════════════════════════════════════════════════════════════════
# MacroCalendar
# ═══════════════════════════════════════════════════════════════════════════


class TestMacroCalendarGetUpcoming:
    def test_returns_list(self):
        cal = MacroCalendar()
        events = cal.get_upcoming_releases(days_ahead=14)
        assert isinstance(events, list)

    def test_event_shape(self):
        cal = MacroCalendar()
        events = cal.get_upcoming_releases(days_ahead=60)
        for ev in events:
            for key in ("name", "date", "country", "time", "impact", "description"):
                assert key in ev, f"event missing {key}: {ev}"

    def test_dates_within_window(self):
        cal = MacroCalendar()
        from datetime import timedelta
        end = cal.today + timedelta(days=7)
        events = cal.get_upcoming_releases(days_ahead=7)
        for ev in events:
            d = __import__("datetime").date.fromisoformat(ev["date"])
            assert cal.today <= d <= end

    def test_nfp_only_first_friday(self):
        cal = MacroCalendar()
        events = cal.get_upcoming_releases(days_ahead=60)
        nfp = [ev for ev in events if ev["name"] == "US NFP"]
        for ev in nfp:
            d = __import__("datetime").date.fromisoformat(ev["date"])
            assert d.weekday() == 4  # Friday
            # First Friday means day <= 7
            assert 1 <= d.day <= 7

    def test_us_cpi_only_weekdays(self):
        cal = MacroCalendar()
        events = cal.get_upcoming_releases(days_ahead=60)
        cpi = [ev for ev in events if ev["name"] == "US CPI"]
        for ev in cpi:
            d = __import__("datetime").date.fromisoformat(ev["date"])
            assert d.weekday() < 5
            assert 10 <= d.day <= 15

    def test_cn_pmi_first_days(self):
        cal = MacroCalendar()
        events = cal.get_upcoming_releases(days_ahead=60)
        cnpmi = [ev for ev in events if ev["name"] == "CN PMI"]
        for ev in cnpmi:
            d = __import__("datetime").date.fromisoformat(ev["date"])
            assert d.day <= 3

    def test_cn_cpi_window(self):
        cal = MacroCalendar()
        events = cal.get_upcoming_releases(days_ahead=60)
        cncpi = [ev for ev in events if ev["name"] == "CN CPI"]
        for ev in cncpi:
            d = __import__("datetime").date.fromisoformat(ev["date"])
            assert 9 <= d.day <= 12

    def test_days_ahead_zero_returns_empty_or_today_only(self):
        cal = MacroCalendar()
        # days_ahead=0 still includes the loop iteration for today
        events = cal.get_upcoming_releases(days_ahead=0)
        # Implementation: end = today + 0 = today → loop runs once for today.
        assert isinstance(events, list)


class TestMacroCalendarGetNextFOMC:
    def test_returns_dict_with_required_fields(self):
        cal = MacroCalendar()
        nxt = cal.get_next_fomc()
        assert nxt is not None
        for key in ("name", "date", "days_until", "country", "time", "impact"):
            assert key in nxt
        assert nxt["name"] == "US FOMC"
        assert nxt["country"] == "US"

    def test_fomc_is_future_or_today(self):
        from datetime import date as _date
        cal = MacroCalendar()
        nxt = cal.get_next_fomc()
        d = _date.fromisoformat(nxt["date"])
        assert d >= cal.today

    def test_fomc_is_wednesday(self):
        from datetime import date as _date
        cal = MacroCalendar()
        nxt = cal.get_next_fomc()
        d = _date.fromisoformat(nxt["date"])
        assert d.weekday() == 2  # Wednesday


class TestMacroCalendarGetNextNFP:
    def test_nfp_fields(self):
        cal = MacroCalendar()
        nfp = cal.get_next_nfp()
        for key in ("name", "date", "days_until", "time", "impact"):
            assert key in nfp

    def test_nfp_is_friday(self):
        from datetime import date as _date
        cal = MacroCalendar()
        nfp = cal.get_next_nfp()
        d = _date.fromisoformat(nfp["date"])
        assert d.weekday() == 4  # Friday
        assert 1 <= d.day <= 7

    def test_nfp_is_in_future(self):
        from datetime import date as _date
        cal = MacroCalendar()
        nfp = cal.get_next_nfp()
        d = _date.fromisoformat(nfp["date"])
        assert d >= cal.today


class TestMacroCalendarGenerateMarketBrief:
    def test_brief_contains_header(self):
        cal = MacroCalendar()
        with patch.object(FREDDataFetcher, "fetch_nfp", return_value=_ts_stub()), \
             patch.object(FREDDataFetcher, "fetch_cpi", return_value=_ts_stub()), \
             patch.object(FREDDataFetcher, "fetch_fed_rates", return_value=_ts_stub()), \
             patch.object(FREDDataFetcher, "fetch_ted_spread", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_pmi", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_cpi", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_gdp", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_lpr", return_value=_ts_stub()):
            brief = cal.generate_market_brief()
        assert "宏观市场简报" in brief
        assert "重要宏观日历" in brief

    def test_brief_includes_latest_value_with_observations(self):
        cal = MacroCalendar()
        ts = MacroTimeSeries(
            indicator="PAYEMS",
            country="US",
            unit="千人",
            frequency=DataFreshness.MONTHLY,
            source=DataSourceType.FRED,
            observations=[_make_obs(value=200_000.0, date="2024-03-01")],
            last_updated="2024-03-01T00:00:00",
        )
        with patch.object(FREDDataFetcher, "fetch_nfp", return_value=ts), \
             patch.object(FREDDataFetcher, "fetch_cpi", return_value=_ts_stub()), \
             patch.object(FREDDataFetcher, "fetch_fed_rates", return_value=_ts_stub()), \
             patch.object(FREDDataFetcher, "fetch_ted_spread", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_pmi", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_cpi", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_gdp", return_value=_ts_stub()), \
             patch.object(AkshareMacroFetcher, "fetch_cn_lpr", return_value=_ts_stub()):
            brief = cal.generate_market_brief()
        assert "200,000千人" in brief

    def test_brief_swallows_exceptions(self):
        cal = MacroCalendar()
        with patch.object(FREDDataFetcher, "fetch_nfp", side_effect=RuntimeError("boom")), \
             patch.object(FREDDataFetcher, "fetch_cpi", side_effect=RuntimeError("boom")), \
             patch.object(FREDDataFetcher, "fetch_fed_rates", side_effect=RuntimeError("boom")), \
             patch.object(FREDDataFetcher, "fetch_ted_spread", side_effect=RuntimeError("boom")), \
             patch.object(AkshareMacroFetcher, "fetch_cn_pmi", side_effect=RuntimeError("boom")), \
             patch.object(AkshareMacroFetcher, "fetch_cn_cpi", side_effect=RuntimeError("boom")), \
             patch.object(AkshareMacroFetcher, "fetch_cn_gdp", side_effect=RuntimeError("boom")), \
             patch.object(AkshareMacroFetcher, "fetch_cn_lpr", side_effect=RuntimeError("boom")):
            # Should not raise
            brief = cal.generate_market_brief()
        assert isinstance(brief, str)
        assert "宏观市场简报" in brief


# ═══════════════════════════════════════════════════════════════════════════
# MacroFinanceCenter
# ═══════════════════════════════════════════════════════════════════════════


class TestMacroFinanceCenterInit:
    def test_init_no_args(self):
        mfc = MacroFinanceCenter()
        assert mfc.cache_dir is None
        assert isinstance(mfc.fred, FREDDataFetcher)
        assert isinstance(mfc.ak, AkshareMacroFetcher)
        assert isinstance(mfc.calendar, MacroCalendar)
        assert mfc._cache == {}

    def test_init_with_cache_dir(self, tmp_path):
        mfc = MacroFinanceCenter(cache_dir=str(tmp_path))
        assert mfc.cache_dir == str(tmp_path)
        assert mfc.fred.cache_dir == str(tmp_path)
        assert mfc.ak.cache_dir == str(tmp_path)


class TestMacroFinanceCenterFetchFred:
    def test_delegates_to_fred(self):
        mfc = MacroFinanceCenter()
        with patch.object(mfc.fred, "fetch_series", return_value=_ts_stub()) as fs:
            ts = mfc.fetch_fred("PAYEMS")
        fs.assert_called_once_with("PAYEMS")
        assert ts.indicator == "X"

    def test_passes_kwargs(self):
        mfc = MacroFinanceCenter()
        with patch.object(mfc.fred, "fetch_series", return_value=_ts_stub()) as fs:
            mfc.fetch_fred("CPIAUCSL", start_date="2024-01-01", end_date="2024-12-31")
        kwargs = fs.call_args.kwargs
        assert kwargs["start_date"] == "2024-01-01"
        assert kwargs["end_date"] == "2024-12-31"


class TestMacroFinanceCenterFetchCNMacro:
    @pytest.mark.parametrize("name,method_name", [
        ("cpi", "fetch_cn_cpi"),
        ("gdp", "fetch_cn_gdp"),
        ("pmi", "fetch_cn_pmi"),
        ("m2", "fetch_cn_m2"),
        ("fdi", "fetch_cn_fdi"),
        ("retail", "fetch_cn_retail"),
        ("shibor", "fetch_cn_shibor"),
        ("lpr", "fetch_cn_lpr"),
        ("yield_curve", "fetch_cn_yield_curve"),
        ("credit_spread", "fetch_cn_credit_spread"),
        ("cfets", "fetch_cfets_index"),
    ])
    def test_dispatch(self, name, method_name):
        mfc = MacroFinanceCenter()
        stub = _ts_stub()
        with patch.object(mfc.ak, method_name, return_value=stub) as m:
            ts = mfc.fetch_cn_macro(name)
        m.assert_called_once()
        assert ts is stub

    def test_unknown_indicator_raises(self):
        mfc = MacroFinanceCenter()
        with pytest.raises(ValueError, match="Unknown CN macro indicator"):
            mfc.fetch_cn_macro("not_a_real_indicator")


class TestMacroFinanceCenterFetchMacroPanel:
    def test_us_routes_to_fred(self):
        mfc = MacroFinanceCenter()
        with patch.object(mfc.fred, "fetch_series", return_value=_ts_stub()) as fs:
            results = mfc.fetch_macro_panel(["PAYEMS", "CPIAUCSL"], country="US")
        assert set(results.keys()) == {"PAYEMS", "CPIAUCSL"}
        assert fs.call_count == 2

    def test_cn_routes_to_fetch_cn_macro(self):
        mfc = MacroFinanceCenter()
        with patch.object(mfc, "fetch_cn_macro", return_value=_ts_stub()) as fcm:
            results = mfc.fetch_macro_panel(["cpi", "gdp"], country="CN")
        assert set(results.keys()) == {"cpi", "gdp"}
        assert fcm.call_count == 2
        # Confirms it actually called with CN names
        called = [c.args[0] for c in fcm.call_args_list]
        assert called == ["cpi", "gdp"]

    def test_partial_failure_does_not_propagate(self):
        mfc = MacroFinanceCenter()
        def fake_fred(series_id, **kwargs):
            if series_id == "BAD":
                raise RuntimeError("boom")
            return _ts_stub()
        with patch.object(mfc.fred, "fetch_series", side_effect=fake_fred):
            results = mfc.fetch_macro_panel(["PAYEMS", "BAD"], country="US")
        assert "PAYEMS" in results
        assert "BAD" not in results


class TestMacroFinanceCenterGenerateMacroReport:
    def test_delegates_to_calendar(self):
        mfc = MacroFinanceCenter()
        with patch.object(mfc.calendar, "generate_market_brief", return_value="BRIEF") as g:
            out = mfc.generate_macro_report()
        g.assert_called_once()
        assert out == "BRIEF"