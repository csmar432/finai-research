"""
research_framework/data_fetcher.py
Generic data fetching layer with MCP probing and automatic fallback.

This module implements a universal data acquisition pipeline:
  1. Probe primary MCP source
  2. Fall through backup sources (ticker_info, analyst_ratings, etc.)
  3. Use proxy variables as last resort, clearly flagged as _sim
  4. Track all data provenance

Supported MCP servers: user-yfinance, user-eodhd

Usage:
    fetcher = DataFetcher(output_dir="output/")
    panel = fetcher.fetch_panel(["XOM","CVX","COP"], years=[2018,2019,2020,2021,2022,2023,2024])
    tracker = fetcher.get_provenance()
"""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_log = logging.getLogger("data_fetcher")

# ─── Single source of truth imports ───────────────────────────────────────────
from scripts.research_framework.base import DataSource, ProvenanceTracker
from scripts.core.provenance import ProvenanceChain

# ─── Tenacity / Circuit Breaker ─────────────────────────────────────────────

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

    _TENACITY_AVAILABLE = True
except ImportError:
    _TENACITY_AVAILABLE = False
    _log.warning("tenacity not installed; retry logic disabled. pip install tenacity")


class CircuitBreaker:
    """Simple in-memory circuit breaker for MCP service calls."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failures: dict[str, int] = {}
        self.last_failure: dict[str, float] = {}
        self.failure_threshold = failure_threshold
        self.timeout = timeout

    def is_open(self, service: str) -> bool:
        import time

        if self.failures.get(service, 0) >= self.failure_threshold:
            if time.time() - self.last_failure.get(service, 0) < self.timeout:
                return True
            else:
                self.failures[service] = 0
        return False

    def record_success(self, service: str):
        self.failures[service] = 0

    def record_failure(self, service: str):
        import time

        self.failures[service] = self.failures.get(service, 0) + 1
        self.last_failure[service] = time.time()


# Shared circuit breaker instance
_circuit_breaker = CircuitBreaker()


# ─── Local dataclasses (no duplicate DataSource/ProvenanceTracker) ───────────


class DataProbeResult:
    def __init__(self, available: bool = False, data: Any = None,
                 source: DataSource = DataSource.SIMULATED, error: str = ""):
        self.available = available; self.data = data
        self.source = source; self.error = error


class DataFallbackEngine:
    def __init__(self, tracker: ProvenanceTracker | None = None):
        self.tracker = tracker or ProvenanceTracker()
        self._probe_log: list = []

    def probe(self, field_name: str, chains: dict,
              min_success_rate: float = 0.3) -> DataProbeResult:
        for tier_name, (source, fn) in chains.items():
            try:
                data = fn()
                if self._check(data, min_success_rate):
                    self.tracker.record(field_name, source, tier_name)
                    self._log(field_name, source, tier_name, True)
                    return DataProbeResult(available=True, data=data, source=source)
                else:
                    self._log(field_name, source, tier_name, False, note="empty/insufficient")
            except Exception as exc:
                self._log(field_name, source, tier_name, False, error=str(exc))
                # Distinguish expected data errors from unexpected code bugs.
                # Expected: network timeout, API error, malformed response.
                # Unexpected: AttributeError, TypeError, etc. (likely code bugs).
                tb_str = traceback.format_exc()
                is_transient = any(
                    cls in tb_str for cls in (
                        "ConnectionError", "TimeoutError", "HTTPError",
                        "URLError", "SSLError", "JSONDecodeError"
                    )
                )
                if not is_transient:
                    _log.warning(
                        "Unexpected error in probe('%s', tier='%s'): %s — "
                        "this may indicate a code bug, not a data issue.",
                        field_name, tier_name, exc
                    )
        _log.warning(f"No data for '{field_name}' — all chains exhausted")
        return DataProbeResult(available=False, source=DataSource.SIMULATED,
                              error="all chains exhausted")

    def _check(self, data: Any, min_rate: float) -> bool:
        if data is None: return False
        if isinstance(data, pd.DataFrame):
            return not data.empty and data.notna().mean().mean() >= min_rate
        if isinstance(data, dict):
            return bool(data) and sum(1 for v in data.values() if v is not None) / max(len(data), 1) >= min_rate
        if isinstance(data, (list, tuple)): return len(data) > 0
        return True

    def _log(self, field, source, tier, success, error="", note=""):
        self._probe_log.append(dict(field=field, tier=tier, source=source.value,
                                     success=success, error=error, note=note,
                                     timestamp=datetime.now(timezone.utc).isoformat()))

    def get_probe_log(self) -> pd.DataFrame:
        return pd.DataFrame(self._probe_log)

    def save_probe_log(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.get_probe_log().to_csv(path, index=False)


_log = logging.getLogger("data_fetcher")
_log.setLevel(logging.INFO)


def save_df(df: pd.DataFrame, path: str | Path, **kwargs):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, **kwargs)
    _log.info(f"Saved: {path} ({len(df)} rows)")


def save_json(obj: Any, path: str | Path, indent: int = 2):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, default=str)
    _log.info(f"Saved JSON: {path}")


# ─────────────────────────────────────────────────────────────────────────────
# MCP CLIENT WRAPPER
# ─────────────────────────────────────────────────────────────────────────────
class MCPCallError(Exception):
    """Raised when an MCP call fails after all retries."""
    pass


def _call_mcp(server: str, tool: str, args: dict, timeout: float = 30.0) -> Any:
    """Internal MCP call without retry — used by tenacity and circuit breaker."""
    # Try via llm_gateway's call_mcp_tool first (uses proper venv python)
    try:
        from scripts.core.llm_gateway import call_mcp_tool as _mcp_call

        result = _mcp_call(server, tool, args, timeout=timeout)
        if result is not None and result.success:
            return result.data
        raise MCPCallError(f"MCP returned unsuccessful result: {result}")
    except ImportError:
        # Fallback: try stdio JSON-RPC directly
        _log.debug(f"llm_gateway import failed, trying direct JSON-RPC for {server}/{tool}")
        raise MCPCallError("llm_gateway unavailable")


if _TENACITY_AVAILABLE:

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
    def _call_mcp_with_retry(server: str, tool: str, args: dict, timeout: float = 30.0) -> Any:
        """Retry-wrapped MCP call. Signature mirrors _call_mcp so tenacity can pass through."""
        return _call_mcp(server, tool, args, timeout=timeout)

else:

    def _call_mcp_with_retry(server: str, tool: str, args: dict, timeout: float = 30.0) -> Any:
        """No-tenacity fallback: signature mirrors _call_mcp."""
        return _call_mcp(server, tool, args, timeout=timeout)


def call_mcp_tool(
    server: str, tool: str, args: dict,
    *, max_retries: int = 2, delay_ms: int = 300,
    timeout: float = 30.0,
) -> Any:
    """
    Call an MCP tool via subprocess with retry logic and circuit breaker.
    MCP servers must be registered via ``python scripts/register_mcp_servers.py``.
    Raises MCPCallError if all retries fail or circuit is open.
    """
    # Check circuit breaker first
    service_id = f"{server}/{tool}"
    if _circuit_breaker.is_open(service_id):
        _log.warning("Circuit breaker OPEN for %s — skipping call", service_id)
        raise MCPCallError(f"Circuit breaker open for {service_id}")

    for attempt in range(max_retries + 1):
        try:
            # Use tenacity-backed retry wrapper if available
            if _TENACITY_AVAILABLE:
                result = _call_mcp_with_retry(server, tool, args, timeout=timeout)
            else:
                result = _call_mcp(server, tool, args, timeout=timeout)
            _circuit_breaker.record_success(service_id)
            return result
        except MCPCallError:
            _log.warning("MCP call failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, service_id)
        except Exception as exc:
            _log.warning("MCP failure (attempt %d/%d): %s: %s", attempt + 1, max_retries + 1, service_id, exc)
            _circuit_breaker.record_failure(service_id)
        if attempt < max_retries:
            time.sleep(delay_ms / 1000)

    _circuit_breaker.record_failure(service_id)
    raise MCPCallError(f"All {max_retries + 1} attempts failed for {service_id}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DATA FETCHER
# ─────────────────────────────────────────────────────────────────────────────
class DataFetcher:
    """
    Generic data fetcher with MCP probing, fallback chains, and provenance tracking.

    Data acquisition priority chain:
      1. yfinance MCP  (get_yf_financials, get_yf_quote, get_yf_earnings)
      2. Simulated    (clearly flagged as _sim; never silently used)
    """

    DEFAULT_TICKERS = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "META", "TSLA", "BRK.B", "JPM", "JNJ",
        "XOM", "CVX", "COP", "SLB", "DVN",
        "HAL", "BKR", "OXY", "MRO", "FANG",
        "EOG", "PXD", "EQT", "OKE", "KMI",
        "WMB", "PSX", "VLO", "CTRA", "TRGP",
    ]

    def __init__(self, output_dir: str | Path = "data/",
                 tracker: ProvenanceTracker | None = None,
                 probe_delay_ms: int = 300, verbose: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = self.output_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.tracker = tracker or ProvenanceTracker()
        self.engine = DataFallbackEngine(self.tracker)
        self.probe_delay_ms = probe_delay_ms
        self.verbose = verbose
        self._fetch_log: list = []

    def fetch_panel(self, tickers=None, years=None,
                    statements=None, include_sustainability=True) -> pd.DataFrame:
        """
        Fetch a wide-format panel by iterating tickers and statements.

        yfinance MCP returns CSV text per call (see mcp_servers/user_yfinance/server.py).
        We parse the CSV to extract per-year columns — NOT dict key lookups.
        This fixes the previous bug where `row.get(str(year))` always returned None
        because the MCP response was a string, not a dict keyed by year.
        """
        tickers = tickers or self.DEFAULT_TICKERS
        years = years or list(range(2018, 2025))
        statements = statements or ["balance", "income", "cashflow"]
        rows = []
        for ticker in tickers:
            for stmt in statements:
                data = self.fetch_financials(ticker, stmt)
                if not data:
                    continue

                # data may be:
                #   - a CSV string  (from yfinance MCP — the common case)
                #   - a dict with a "data" list (if wrapped by engine elsewhere)
                #   - a DataFrame dict (from akshare fallback)
                # Normalise to DataFrame first.
                df_stmt = self._normalise_to_df(data)
                if df_stmt.empty:
                    continue

                # yfinance DataFrames have dates as index or as a column.
                # Extract year from the index/date column.
                if "Date" in df_stmt.columns:
                    date_col = "Date"
                elif df_stmt.index.name == "Date" or "Date" in str(df_stmt.index.name):
                    df_stmt = df_stmt.reset_index()
                    date_col = "Date"
                else:
                    date_col = None

                for year in years:
                    if date_col and date_col in df_stmt.columns:
                        # Filter rows matching this year, then unpivot
                        year_rows = df_stmt[df_stmt[date_col].astype(str).str.startswith(str(year))]
                        for _, row in year_rows.iterrows():
                            for col in df_stmt.columns:
                                if col == date_col:
                                    continue
                                val = row[col]
                                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                    rows.append(dict(ticker=ticker, year=year,
                                                   statement=stmt, field=str(col), value=val))
                    else:
                        # Fallback: treat each column as a separate year field
                        # (handles DataFrames where column names are years, e.g. "2019", "2020")
                        for col in df_stmt.columns:
                            if str(year) in col or f"{year}-" in col:
                                val = df_stmt[col].iloc[0] if len(df_stmt) > 0 else None
                                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                    rows.append(dict(ticker=ticker, year=year,
                                                   statement=stmt, field=str(col), value=val))
            time.sleep(self.probe_delay_ms / 1000)
        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        if not df.empty:
            save_df(df, self.output_dir / "panel_raw.csv")
            _log.info(f"Panel: {len(df)} records, {df['ticker'].nunique()} tickers")
        return df

    def _normalise_to_df(self, data: Any) -> pd.DataFrame:
        """
        Convert MCP response to DataFrame regardless of source format.

        Handles:
          - str (CSV from yfinance MCP) → parse with pandas
          - dict with "data" key → wrap in DataFrame
          - dict with list-valued columns → DataFrame
          - pd.DataFrame → pass through
        """
        if isinstance(data, pd.DataFrame):
            return data
        if isinstance(data, str):
            try:
                return pd.read_csv(pd.io.common.StringIO(data))
            except Exception as e:
                _log.warning(f"CSV parse failed: {e}"); return pd.DataFrame()
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return pd.DataFrame(data["data"])
            # dict-of-arrays format (yfinance FinancialsDataFrames serialised)
            try:
                return pd.DataFrame(data)
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    def fetch_financials(self, ticker: str, statement: str = "balance",
                         *, use_cache: bool = True) -> dict | None:
        raw_path = self.raw_dir / f"{ticker}_{statement}.json"
        if use_cache and raw_path.exists():
            try:
                with open(raw_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                _log.warning(f"Cache file corrupted, re-fetching: {raw_path} ({e})")
                raw_path.unlink(missing_ok=True)
        chains = {
            "primary_yf": (DataSource.MCP_YFINANCE,
                           lambda: self._mcp_yf_financials(ticker, statement)),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        result = self.engine.probe(f"{ticker}:{statement}", chains)
        payload = dict(ticker=ticker, statement=statement,
                       source=result.source.value, data=result.data or {})
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        self._log_fetch(ticker, statement, result.source.value, result.available)
        return result.data

    def fetch_ticker_info(self, ticker: str) -> dict | None:
        chains = {
            "primary_yf": (DataSource.MCP_YFINANCE, lambda: self._mcp_yf_ticker_info(ticker)),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        return self.engine.probe(f"{ticker}:info", chains).data

    def fetch_analyst_ratings(self, ticker: str) -> dict | None:
        chains = {
            "primary_yf": (DataSource.MCP_YFINANCE, lambda: self._mcp_yf_analyst(ticker)),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        return self.engine.probe(f"{ticker}:analyst", chains).data

    def fetch_sustainability(self, ticker: str) -> dict | None:
        chains = {
            "primary_yf": (DataSource.MCP_YFINANCE, lambda: self._mcp_yf_sustainability(ticker)),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        result = self.engine.probe(f"{ticker}:esg", chains)
        if not result.available:
            _log.warning(
                f"[{ticker}] SUSTAINABILITY UNAVAILABLE — "
                "using proxy variables. Check provenance tracker.")
            self.tracker.flag_simulated(f"esg_{ticker}",
                reason="yfinance sustainability empty for energy sector")
        return result.data

    def fetch_batch_ticker_info(self, tickers=None, delay_ms=None) -> pd.DataFrame:
        tickers = tickers or self.DEFAULT_TICKERS
        delay_ms = delay_ms or self.probe_delay_ms
        records = []
        for ticker in tickers:
            info = self.fetch_ticker_info(ticker)
            self.tracker.record(f"{ticker}:info", DataSource.MCP_YFINANCE, "fetch_batch_ticker_info")
            if info:
                info["_ticker"] = ticker
                records.append(info)
            time.sleep(delay_ms / 1000)
        if records:
            df = pd.DataFrame(records).set_index("_ticker")
            df.index.name = "ticker"
            save_df(df.reset_index(), self.output_dir / "ticker_info_batch.csv")
            return df
        return pd.DataFrame()

    def get_provenance(self) -> ProvenanceTracker:
        return self.tracker

    def get_probe_log(self) -> pd.DataFrame:
        return self.engine.get_probe_log()

    def save_provenance(self, path: str | Path | None = None):
        p = path or self.output_dir / "provenance.json"
        self.tracker.save(p)
        self.engine.save_probe_log(self.output_dir / "probe_log.csv")

    def _mcp_yf_financials(self, ticker: str, statement: str) -> dict | None:
        try:
            return call_mcp_tool("user-yfinance", "get_yf_financials",
                               {"ticker": ticker, "statement_type": statement})
        except MCPCallError as e:
            _log.debug(f"yfinance financials failed for {ticker}: {e}"); return None

    def _mcp_yf_ticker_info(self, ticker: str) -> dict | None:
        try: return call_mcp_tool("user-yfinance", "get_yf_quote", {"ticker": ticker})
        except MCPCallError as e: _log.debug(f"yfinance info failed for {ticker}: {e}"); return None

    def _mcp_yf_sustainability(self, ticker: str) -> dict | None:
        # yfinance MCP 无 sustainability 工具，使用 get_yf_financials ratios 作为部分替代
        try: return call_mcp_tool("user-yfinance", "get_yf_financials",
                                 {"ticker": ticker, "statement_type": "ratios"})
        except MCPCallError as e: _log.debug(f"yfinance sustainability failed for {ticker}: {e}"); return None

    def _mcp_yf_analyst(self, ticker: str) -> dict | None:
        # yfinance MCP 无 analyst_data 工具，使用 get_yf_earnings 作为分析师预测替代（EPS/营收）
        try: return call_mcp_tool("user-yfinance", "get_yf_earnings", {"ticker": ticker})
        except MCPCallError as e: _log.debug(f"yfinance analyst failed for {ticker}: {e}"); return None

    # ── EODHD macro methods ────────────────────────────────────────────────
    def _mcp_eodhd(self, tool: str, args: dict) -> dict | None:
        """Generic EODHD MCP call."""
        try: return call_mcp_tool("user-eodhd", tool, args)
        except MCPCallError as e: _log.debug(f"EODHD {tool} failed: {e}"); return None

    def fetch_macro_indicator(self, country: str, indicator: str = "gdp_current_usd",
                               api_token: str | None = None) -> dict | None:
        """
        Fetch a macroeconomic indicator for a country via EODHD.

        Args:
            country: ISO-3 alpha code (e.g. "USA", "CHN", "DEU", "JPN")
            indicator: One of documented indicators.
                Common: gdp_current_usd, inflation_consumer_prices, unemployment_rate,
                        population_total, trade_usd, debt_usd, life_expectancy
            api_token: Per-call token override.

        Returns:
            dict with historical time series for the indicator.
        """
        chains = {
            "primary": (
                DataSource.MCP_EODHD,
                lambda: self._mcp_eodhd("get_economic_indicators", {
                    "country": country, "indicator": indicator,
                    "api_token": api_token,
                }),
            ),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        result = self.engine.probe(f"macro:{country}:{indicator}", chains)
        # Note: engine.probe() already calls tracker.record() internally.
        # We do NOT record again here to avoid double-counting.
        # The provenance field is recorded as "macro:{indicator}:{country}" by probe().
        return result.data

    def fetch_ust_yield_rates(self, year: int | None = None) -> dict | None:
        """
        Fetch daily US Treasury par yield curve rates via EODHD.

        Args:
            year: Filter by year (default: current year).

        Returns:
            dict with yield curve rates: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y.
        """
        chains = {
            "primary": (
                DataSource.MCP_EODHD,
                lambda: self._mcp_eodhd("get_ust_yield_rates", {"year": year}),
            ),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        result = self.engine.probe("macro:ust_yield", chains)
        # Note: engine.probe() already calls tracker.record() internally.
        # We do NOT record again here to avoid double-counting.
        return result.data

    def fetch_economic_events(self, country: str = "US",
                               start_date: str | None = None,
                               end_date: str | None = None,
                               limit: int = 200) -> dict | None:
        """
        Fetch macroeconomic calendar events (GDP, CPI, employment, Fed meetings) via EODHD.

        Args:
            country: ISO-2 code (e.g. "US", "DE", "CN")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            limit: Max events to return (default 200)

        Returns:
            dict with array of economic events (actual/estimate/previous values).
        """
        chains = {
            "primary": (
                DataSource.MCP_EODHD,
                lambda: self._mcp_eodhd("get_economic_events", {
                    "country": country, "start_date": start_date,
                    "end_date": end_date, "limit": limit,
                }),
            ),
            "fallback_simulated": (DataSource.SIMULATED, lambda: None),
        }
        result = self.engine.probe(f"macro:events:{country}", chains)
        # Note: engine.probe() already calls tracker.record() internally.
        # We do NOT record again here to avoid double-counting.
        return result.data

    def fetch_macro_batch(self, countries: list[str],
                           indicators: list[str],
                           api_token: str | None = None) -> pd.DataFrame:
        """
        Fetch multiple macro indicators for multiple countries and return a wide DataFrame.

        Args:
            countries: List of ISO-3 country codes
            indicators: List of indicator names
            api_token: EODHD API token

        Returns:
            DataFrame with columns [country, year, indicator_1, indicator_2, ...]
        """
        rows = []
        for c in countries:
            for ind in indicators:
                data = self.fetch_macro_indicator(c, ind, api_token)
                if data:
                    rows.append({"country": c, "indicator": ind, "data": data})
                time.sleep(200 / 1000)  # avoid rate limit
        if not rows:
            return pd.DataFrame()
        # Normalize to DataFrame
        records = []
        for r in rows:
            d = r["data"]
            if isinstance(d, dict):
                for date, val in d.items():
                    records.append({"country": r["country"], "indicator": r["indicator"],
                                   "date": date, "value": val})
        df = pd.DataFrame(records) if records else pd.DataFrame()
        if not df.empty:
            save_df(df, self.output_dir / "macro_batch.csv")
        return df

    # ── Province Stats (province-stats MCP) ──────────────────────────────

    def _mcp_province_stats(self, tool: str, args: dict) -> dict | None:
        """Internal helper: call a province-stats tool and return the result dict.

        call_mcp_tool() returns result.data (the actual dict), not an MCPResult.
        服务器名: user-province-stats（来自 SERVER_METADATA.json）。
        """
        try:
            data = call_mcp_tool(  # returns result.data, not MCPResult
                "user-province-stats",
                tool,
                args,
            )
            # call_mcp_tool raises MCPCallError on failure, so we only reach here on success
            if data and isinstance(data, dict):
                return data
            if data and isinstance(data, str):
                try:
                    import json as _json
                    return _json.loads(data)
                except (ValueError, OSError) as e:
                    _log.warning(f"MCP returned non-JSON string for {tool}: {e}")
                    return None
            return data if data else None
        except MCPCallError:
            _log.warning(f"_mcp_province_stats({tool}) MCP call failed")
            return None
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as e:
            _log.warning(f"_mcp_province_stats({tool}) parse error: {e}")
            return None

    def fetch_province_indicator(
        self,
        province: str,
        indicator: str,
        year: str | None = None,
    ) -> dict | None:
        """
        Fetch a single indicator value for a province.

        Args:
            province: Province name, e.g. "湖北", "广东", "江苏"
            indicator: Indicator name or alias, e.g. "GDP", "R&D经费", "高新技术企业"
            year: Year string (optional), e.g. "2024". If omitted, returns latest available.

        Returns:
            dict with "success", "data" fields from the MCP server,
            or None if the call fails.
        """
        result = self._mcp_province_stats("get_province_indicator", {
            "province": province,
            "indicator": indicator,
            "year": year or "",
        })
        if result:
            self.tracker.record(
                f"province:{province}:{indicator}",
                DataSource.MCP_USER,
                detail="user-province-stats.get_province_indicator",
            )
        return result

    def fetch_province_timeseries(
        self,
        province: str,
        indicator: str,
    ) -> dict | None:
        """
        Fetch multi-year time series for a province and indicator.

        Args:
            province: Province name
            indicator: Series name, e.g. "GDP", "R&D经费", "高新技术企业"

        Returns:
            dict with "success", "data" (year→value mapping) from the MCP server,
            or None if the call fails.
        """
        result = self._mcp_province_stats("get_province_timeseries", {
            "province": province,
            "indicator": indicator,
        })
        if result:
            self.tracker.record(
                f"province_ts:{province}:{indicator}",
                DataSource.MCP_USER,
                detail="user-province-stats.get_province_timeseries",
            )
        return result

    def fetch_province_rankings(self, table: str) -> dict | None:
        """
        Fetch a national ranking table (e.g. "GDP_2024", "RD经费_2024").

        Args:
            table: Table ID, e.g. "GDP_2024", "RD经费_2024", "高新技术企业_2024"

        Returns:
            dict with ranking rows, or None if the call fails.
        """
        result = self._mcp_province_stats("get_province_rankings", {
            "table": table,
        })
        if result:
            self.tracker.record(
                f"province_rankings:{table}",
                DataSource.MCP_USER,
                detail="user-province-stats.get_province_rankings",
            )
        return result

    def fetch_province_summary(self) -> dict | None:
        """
        Fetch summary of all available provinces: coverage, verification status,
        available time series.

        Returns:
            dict with province list and metadata, or None if the call fails.
        """
        result = self._mcp_province_stats("get_province_rankings", {"table": "GDP_2024"})
        if result:
            self.tracker.record(
                "province_summary",
                DataSource.MCP_USER,
                detail="user-province-stats.get_province_rankings",
            )
        return result

    def _log_fetch(self, ticker, stmt, source, success):
        self._fetch_log.append(dict(ticker=ticker, statement=stmt,
                                     source=source, success=success,
                                     timestamp=datetime.now(timezone.utc).isoformat()))


# ─────────────────────────────────────────────────────────────────────────────
# PROXY VARIABLE BUILDER
# ─────────────────────────────────────────────────────────────────────────────
class ProxyVariableBuilder:
    """
    Build proxy variables from real data when ESG/sustainability data is unavailable.

    IMPORTANT: Proxy variables are clearly flagged as simulated and MUST be approved
    by the user before use in analysis. Pass allow_simulated=True only after user
    consent, or when working in a pure demonstration mode.
    """
    INDUSTRY_ESG_AVG = {
        "integrated": 72.0, "e&p": 58.0, "refining": 65.0,
        "equipment": 68.0, "midstream": 70.0, "tech": 78.0,
    }

    def __init__(self, tracker: ProvenanceTracker | None = None):
        self.tracker = tracker or ProvenanceTracker()

    def merge_to(self, parent_tracker: ProvenanceTracker) -> None:
        """Merge this builder's simulated field records into a parent tracker."""
        for field, record in self.tracker._r.items():
            parent_tracker.record(
                field,
                record.get("source", DataSource.SIMULATED),
                detail=f"[merged] {record.get('source_detail', '')}",
                is_simulated=record.get("is_simulated", False),
            )
            if record.get("is_simulated"):
                parent_tracker.flag_simulated(field, record.get("note", ""))

    def build_esg_proxy(self, df: pd.DataFrame, method: str = "industry_avg",
                        *, allow_simulated: bool = False) -> pd.DataFrame:
        """
        Build ESG proxy variable.

        Args:
            df: Input DataFrame with financial data
            method: "industry_avg" (default) | "carbon_intensity" | "controversy"
            allow_simulated: MUST be True to generate proxy values.
                            Raises ValueError if False (no silent simulation).
        """
        if not allow_simulated:
            raise ValueError(
                "ProxyVariableBuilder: attempted to generate ESG proxy without "
                "explicit allow_simulated=True. "
                "Either provide real ESG data or set allow_simulated=True "
                "with user consent."
            )
        df = df.copy()
        if method == "carbon_intensity":
            ppe_ratio = df.get("ppe_ratio", 0.7) if "ppe_ratio" in df.columns else 0.7
            df["esg_score_proxy"] = (100.0 - ppe_ratio * 40.0).clip(20.0, 80.0)
            self.tracker.flag_simulated("esg_score_proxy",
                "carbon_intensity proxy: 100 - ppe_ratio*40 (USER APPROVED)")
        elif method == "controversy":
            df["esg_score_proxy"] = 70.0
            self.tracker.flag_simulated("esg_score_proxy", "controversy proxy (USER APPROVED)")
        else:
            if "industry" in df.columns:
                df["esg_score_proxy"] = df["industry"].map(self.INDUSTRY_ESG_AVG).fillna(60.0)
            else:
                df["esg_score_proxy"] = 60.0
            self.tracker.flag_simulated("esg_score_proxy",
                "industry_avg proxy — get_sustainability returned empty (USER APPROVED)")
        return df

    def build_analyst_coverage_proxy(self, df: pd.DataFrame,
                                     *, allow_simulated: bool = False) -> pd.DataFrame:
        """Build analyst coverage proxy. Requires allow_simulated=True."""
        if not allow_simulated:
            raise ValueError(
                "ProxyVariableBuilder: attempted to generate analyst_coverage proxy "
                "without explicit allow_simulated=True. "
                "Either provide real analyst data or set allow_simulated=True with user consent."
            )
        df = df.copy()
        assets = df["total_assets"] if "total_assets" in df.columns else pd.Series(1e9, index=df.index)
        df["analyst_coverage_proxy"] = (np.log(assets / 1e9) * 3.0 + 8.0).clip(5.0, 30.0)
        self.tracker.flag_simulated("analyst_coverage_proxy",
            "log(total_assets) proxy for analyst coverage (USER APPROVED)")
        return df

    def build_cds_proxy(self, df: pd.DataFrame,
                        *, allow_simulated: bool = False) -> pd.DataFrame:
        """Build CDS spread proxy. Requires allow_simulated=True."""
        if not allow_simulated:
            raise ValueError(
                "ProxyVariableBuilder: attempted to generate CDS proxy "
                "without explicit allow_simulated=True. "
                "Either provide real CDS data or set allow_simulated=True with user consent."
            )
        df = df.copy()
        debt_ratio = df.get("debt_ratio", 0.3) if "debt_ratio" in df.columns else 0.3
        roa = df.get("roa", 0.05) if "roa" in df.columns else 0.05
        rng = np.random.default_rng(42)
        df["cds_spread_proxy"] = (debt_ratio * 200.0 + (1.0 - roa) * 80.0 +
                                    rng.normal(0.0, 5.0, len(df))).clip(40.0, 300.0)
        self.tracker.flag_simulated("cds_spread_proxy",
            "leverage + ROA proxy for CDS spread (USER APPROVED)")
        return df

    def build_carbon_intensity_proxy(self, df: pd.DataFrame,
                                     *, allow_simulated: bool = False) -> pd.DataFrame:
        """Build carbon intensity proxy. Requires allow_simulated=True."""
        if not allow_simulated:
            raise ValueError(
                "ProxyVariableBuilder: attempted to generate carbon_intensity proxy "
                "without explicit allow_simulated=True. "
                "Either provide real emissions data or set allow_simulated=True with user consent."
            )
        df = df.copy()
        ppe = df["ppe"] if "ppe" in df.columns else df["total_assets"] * 0.6
        assets = df["total_assets"] if "total_assets" in df.columns else 1e9
        df["carbon_intensity_proxy"] = ppe / assets
        self.tracker.flag_simulated("carbon_intensity_proxy",
            "PPE/assets proxy for carbon intensity (USER APPROVED)")
        return df

    def get_tracker(self) -> ProvenanceTracker:
        return self.tracker


__all__ = ["DataFetcher", "ProxyVariableBuilder", "MCPCallError",
           "DataSource", "ProvenanceTracker", "DataProbeResult",
           "DataFallbackEngine", "CircuitBreaker", "_TENACITY_AVAILABLE",
           "save_df", "save_json"]


# ─────────────────────────────────────────────────────────────────────────────
# CACHED DATA FETCHER — DuckDB 缓存层 + 7 层故障转移
# ─────────────────────────────────────────────────────────────────────────────


class CachedDataFetcher(DataFetcher):
    """
    增强版 DataFetcher：接入 DuckDB 缓存层 + 7 层故障转移。

    新增能力：
      - DuckDB 缓存（TTL=24h，ms 级响应）
      - 7 层故障转移（yfinance → Tiingo → Finnhub → ... → simulated）
      - Rate Limiter 持久化（智能退避）
      - 自然语言查询（通过 nl_router.py）

    Usage
    -----
        fetcher = CachedDataFetcher()
        # 自动使用缓存
        info = fetcher.fetch_ticker_info("AAPL")
        # 手动触发 7 层降级
        data = fetcher.fetch_with_fallback("stock_info", {"ticker": "AAPL"})
        # 自然语言
        result = fetcher.nl_query("Get CPI for China from 2010 to 2023")
    """

    def __init__(
        self,
        output_dir: str | Path = "data/",
        tracker: ProvenanceTracker | None = None,
        probe_delay_ms: int = 300,
        verbose: bool = False,
        *,
        cache_db_path: str = ".cache/mcp_cache.ddb",
        cache_ttl_seconds: float = 86400.0,
        enable_7layer_fallback: bool = True,
        enable_nl_router: bool = False,
        chain: ProvenanceChain | None = None,
    ):
        super().__init__(output_dir, tracker, probe_delay_ms, verbose)
        self.cache_db_path = cache_db_path
        self.cache_ttl = cache_ttl_seconds
        self._cache = None
        self._nl_router = None
        self.enable_7layer = enable_7layer_fallback
        self.enable_nl = enable_nl_router
        self._rate_limit_log: list[dict] = []
        self._chain = chain
        self._chain_enabled = chain is not None

    # ── Lazy cache init ──────────────────────────────────────────────────

    @property
    def cache(self):
        """延迟初始化 DuckDB 缓存。"""
        if self._cache is None:
            try:
                from scripts.core.data_cache import DataCache
                self._cache = DataCache(
                    db_path=self.cache_db_path,
                    default_ttl_seconds=self.cache_ttl,
                    verbose=self.verbose,
                )
            except Exception as exc:
                _log.warning(f"[CachedDataFetcher] Cache init failed: {exc}")
                self._cache = None
        return self._cache

    @property
    def nl_router(self):
        """延迟初始化自然语言路由。"""
        if self._nl_router is None:
            try:
                from scripts.core.nl_router import NLRouter
                self._nl_router = NLRouter(verbose=self.verbose)
            except Exception as exc:
                _log.warning(f"[CachedDataFetcher] NL Router init failed: {exc}")
        return self._nl_router

    # ── Cache-first fetch ─────────────────────────────────────────────────

    def _cached_mcp_call(
        self,
        server: str,
        tool: str,
        args: dict,
        *,
        ttl_seconds: float | None = None,
    ) -> dict | None:
        """
        缓存优先的 MCP 调用。

        流程：缓存命中 → 直接返回
              缓存miss → 穿透调用 → 写入缓存 → 返回
        """
        cache = self.cache
        if cache is None:
            # 无缓存，降级到原有 call_mcp_tool
            result = call_mcp_tool(server, tool, args)
            if result and result.success and result.data:
                return result.data
            return None

        ttl = ttl_seconds if ttl_seconds is not None else self.cache_ttl

        # Step 1: 检查缓存
        cached = cache.get(server, tool, args, ttl_seconds=ttl)
        if cached is not None:
            _log.debug(f"[CachedDataFetcher] CACHE HIT: {server}/{tool}")
            self.tracker.record(
                f"{server}:{tool}:{args.get('symbol', args.get('ticker', ''))}",
                DataSource.MCP_USER,
                detail=f"cache_hit:{server}/{tool}",
            )
            return cached

        # Step 2: 穿透获取
        _log.debug(f"[CachedDataFetcher] CACHE MISS: {server}/{tool} → fetching")
        try:
            result = call_mcp_tool(server, tool, args)
            # call_mcp_tool returns MCPResult, not dict — extract actual data
            if result is None or not result.success:
                _log.warning(f"[CachedDataFetcher] MCP call failed: {result.error if result else 'None'}")
                return None
            data = result.data if hasattr(result, 'data') else result
            if data is not None:
                cache.set(server, tool, args, data, source=f"{server}:{tool}")
                _log.info(f"[CachedDataFetcher] FETCHED & CACHED: {server}/{tool}")
                returned_fields = self._extract_fields(data)
                self.tracker.record(
                    f"{server}:{tool}:{args.get('symbol', args.get('ticker', ''))}",
                    DataSource.MCP_USER,
                    detail=f"cache_miss_fetch:{server}/{tool}",
                    returned_fields=returned_fields,
                )
            return data
        except MCPCallError:
            _log.warning(f"[CachedDataFetcher] All MCP retries failed: {server}/{tool}")
            return None

    @staticmethod
    def _extract_fields(data) -> list[str]:
        """Extract field/column names from an API response for provenance tracking."""
        if isinstance(data, dict):
            return list(data.keys())
        if isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
            return list(data[0].keys()) if data[0] else []
        return []

    # ── 7 层故障转移 ────────────────────────────────────────────────────

    def fetch_with_fallback(
        self,
        chain_name: str,
        args: dict,
        *,
        ttl_seconds: float | None = None,
    ) -> dict | None:
        """
        基于 7 层故障转移链获取数据。

        Parameters
        ----------
        chain_name : str
            故障转移链名称，对应 FallbackChain.DEFAULT_CHAINS 的 key。
        args : dict
            传递给各层 MCP 工具的参数（各层参数可能不同）。
        ttl_seconds : float | None
            缓存 TTL。

        Returns
        -------
        dict | None
        """
        from scripts.core.data_cache import FallbackChain

        chain = FallbackChain(chain_name) if chain_name else FallbackChain()
        fallback_log: list[dict] = []

        for tier in chain.tiers():
            tier_name = tier.name
            _log.info(
                f"[CachedDataFetcher] Fallback tier {tier.priority}: "
                f"{tier_name} ({tier.server}/{tier.tool})"
            )

            # 检查 Rate Limiter
            cache = self.cache
            if cache:
                limiter = cache._get_limiter(tier.server, tier.tool)
                if limiter.should_backoff():
                    backoff = limiter.backoff_seconds()
                    _log.warning(
                        f"[CachedDataFetcher] {tier_name} rate limited, "
                        f"backing off {backoff:.1f}s"
                    )
                    time.sleep(backoff)

            # 尝试从缓存获取
            if cache:
                cached = cache.get(tier.server, tier.tool, args, ttl_seconds=ttl_seconds)
                if cached is not None:
                    fallback_log.append({
                        "tier": tier_name,
                        "status": "cache_hit",
                        "server": tier.server,
                        "tool": tier.tool,
                    })
                    self.tracker.record(
                        f"fallback:{chain_name}",
                        DataSource.MCP_USER,
                        detail=f"hit:{tier_name}",
                    )
                    return cached

            # 穿透获取
            try:
                data = call_mcp_tool(tier.server, tier.tool, args)
                if data is not None:
                    fallback_log.append({
                        "tier": tier_name,
                        "status": "fetched",
                        "server": tier.server,
                        "tool": tier.tool,
                    })
                    if cache:
                        cache.set(tier.server, tier.tool, args, data, source=f"{tier_name}")
                    self.tracker.record(
                        f"fallback:{chain_name}",
                        DataSource.MCP_USER,
                        detail=f"fetched:{tier_name}",
                    )
                    self._rate_limit_log.append({
                        "chain": chain_name,
                        "tier": tier_name,
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    return data
                _log.warning(f"[CachedDataFetcher] {tier_name} returned None — trying next tier")
            except MCPCallError as exc:
                fallback_log.append({
                    "tier": tier_name,
                    "status": "failed",
                    "error": str(exc),
                })
                self._rate_limit_log.append({
                    "chain": chain_name,
                    "tier": tier_name,
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                _log.warning(
                    f"[CachedDataFetcher] {tier_name} failed: {exc} — trying next tier"
                )
                continue

        _log.error(
            f"[CachedDataFetcher] All fallback tiers exhausted for chain '{chain_name}'"
        )
        return None

    # ── 自然语言查询 ───────────────────────────────────────────────────

    def nl_query(self, query: str) -> dict | None:
        """
        自然语言查询 → 自动路由到 MCP 工具。

        Parameters
        ----------
        query : str
            自然语言查询，例如 "Get CPI for China from 2010 to 2023"。

        Returns
        -------
        dict | None
        """
        router = self.nl_router
        if router is None:
            _log.error("[CachedDataFetcher] NL Router not available")
            return None

        try:
            result = router.route(query)
            if result.plans:
                _log.info(
                    f"[CachedDataFetcher] NL Query routed to {len(result.plans)} step(s)"
                )
            return result.to_dict()
        except Exception as exc:
            _log.error(f"[CachedDataFetcher] NL Query failed: {exc}")
            return None

    # ── 缓存管理 ───────────────────────────────────────────────────────

    def prune_cache(self) -> int:
        """删除过期缓存条目。"""
        cache = self.cache
        if cache:
            return cache.prune_expired()
        return 0

    def get_cache_stats(self) -> dict:
        """返回缓存统计。"""
        cache = self.cache
        if cache:
            return cache.stats()
        return {"enabled": False}

    def get_fallback_stats(self) -> dict:
        """返回故障转移统计。"""
        return {
            "total_attempts": len(self._rate_limit_log),
            "success_count": sum(
                1 for r in self._rate_limit_log if r.get("status") == "success"
            ),
            "tier_distribution": self._summarize_tier_usage(),
        }

    def _summarize_tier_usage(self) -> dict:
        """统计各层使用频率。"""
        from collections import Counter
        tiers = [r.get("tier", "unknown") for r in self._rate_limit_log]
        return dict(Counter(tiers))

    # ── 覆盖父类方法（缓存优先版本）─────────────────────────────────

    def fetch_ticker_info(self, ticker: str) -> dict | None:
        """缓存优先版本的 fetch_ticker_info。"""
        args = {"ticker": ticker}
        return self._cached_mcp_call(
            "user-yfinance", "get_yf_quote", args,
        )

    def fetch_financials(
        self,
        ticker: str,
        statement: str = "balance",
        *,
        use_cache: bool = True,
    ) -> dict | None:
        """缓存优先版本的 fetch_financials（保留原有 raw 文件逻辑）。"""
        raw_path = self.raw_dir / f"{ticker}_{statement}.json"
        if use_cache and raw_path.exists():
            try:
                with open(raw_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                _log.warning(f"Cache file corrupted, re-fetching: {raw_path} ({e})")
                raw_path.unlink(missing_ok=True)

        args = {"ticker": ticker, "statement_type": statement}
        data = self._cached_mcp_call("user-yfinance", "get_yf_financials", args)

        if data is not None:
            payload = dict(ticker=ticker, statement=statement,
                          source="cached:mcp:yfinance", data=data)
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        return data

    def fetch_macro_indicator(
        self,
        country: str,
        indicator: str = "gdp_current_usd",
        api_token: str | None = None,
    ) -> dict | None:
        """缓存优先版本的 fetch_macro_indicator。"""
        if self.enable_7layer:
            return self.fetch_with_fallback(
                "macro",
                {"country": country, "indicator": indicator, "api_token": api_token},
            )
        args = {"country": country, "indicator": indicator, "api_token": api_token}
        return self._cached_mcp_call("user-eodhd", "get_economic_indicators", args)

    # ── ProvenanceChain 集成 ──────────────────────────────────────────────

    def get_provenance_tracker(self) -> ProvenanceTracker | None:
        """返回完整论文级溯源追踪器（需先调用 init_chain()）。"""
        if self._chain is None:
            return None
        pt = ProvenanceTracker()
        pt._chain = self._chain
        return pt

    def init_chain(self, project_dir: str | Path = "output/") -> ProvenanceChain:
        """初始化论文级溯源链（图表→数字→代码→数据节点）。"""
        if self._chain is None:
            self._chain = ProvenanceChain(project_dir)
            self._chain_enabled = True
        return self._chain

    def register_figure_provenance(
        self,
        figure_id: str,
        figure_path: str | Path,
        data_field: str = "",
        code_snippet: str = "",
    ) -> None:
        """将图表注册到 ProvenanceChain（建立图表→数据文件的血缘链路）。"""
        if self._chain is None:
            _log.debug("[CachedDataFetcher] chain not initialized — call init_chain() first")
            return
        from scripts.core.provenance import ProvenanceNode, SourceRef, NodeType
        node_id = self._chain.register_data_source(str(figure_path), label=figure_id)
        fig_node = ProvenanceNode(
            node_id=f"fig_{uuid.uuid4().hex[:8]}",
            node_type=NodeType.CHART,
            label=figure_id,
            sources=[SourceRef(type="file", path=str(figure_path))],
            content=code_snippet,
            parent_ids=[node_id],
        )
        self._chain.register_node(fig_node)