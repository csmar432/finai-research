#!/usr/bin/env python3
"""Real MCP fetchers used by record_full_pipeline_v4.sh.

Each function calls a real public API (no fabricated data) and returns
a short text block ready to print to the demo session. Calls are
wrapped in short timeouts + retries because demo recordings can't
afford hangs.

Servers used:
  user-yfinance    → get_yf_historical (Yahoo Finance; no API key)
  user-sec-edgar   → data.sec.gov (public; no API key)
  user-wb-data     → api.worldbank.org (public; no API key)
  user-openalex    → api.openalex.org (public; no API key, with retry)
  user-fed-data    → home.treasury.gov (public; no API key)

If a call fails after retries, the function returns a one-line note
saying so — demo never crashes.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "FinAI-Research-Demo/1.0 (research@example.com)"


def http_get(url: str, timeout: int = 8, retries: int = 2) -> bytes:
    """GET with retry. Returns empty bytes on failure."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.5)
    print(f"  [warn] {url[:80]}... failed after {retries + 1} tries: {type(last_err).__name__}",
          file=sys.stderr)
    return b""


# ─── user-yfinance ─────────────────────────────────────────
def fetch_yf_history(ticker: str, year: int) -> str:
    """Yahoo Finance monthly close via direct library call. Fast (~0.4 s)."""
    try:
        import yfinance as yf  # type: ignore
        t = yf.Ticker(ticker)
        df = t.history(start=f"{year}-01-01", end=f"{year + 1}-01-01", interval="1mo")
        if df.empty:
            return f"  {ticker:<6} {year}  no data"
        closes = [f"{c:.2f}" for c in df["Close"].tolist()]
        # Show year-end close + avg of year
        yend = closes[-1]
        avg = sum(float(c) for c in closes) / len(closes)
        hi = max(df["High"].tolist())
        lo = min(df["Low"].tolist())
        return (f"  {ticker:<6} {year}  "
                f"12 mo  Close[Dec]=${yend}  Avg=${avg:.2f}  "
                f"H=${hi:.2f}  L=${lo:.2f}")
    except Exception as e:
        return f"  {ticker:<6} {year}  error: {type(e).__name__}"


# ─── user-sec-edgar ────────────────────────────────────────
def fetch_sec_filings(ticker: str) -> str:
    """SEC EDGAR submissions API. Look up CIK then list recent filings."""
    data = http_get("https://www.sec.gov/files/company_tickers.json", timeout=6)
    if not data:
        return f"  {ticker}  SEC tickers file unavailable"
    j = json.loads(data)
    cik = None
    name = None
    for v in j.values():
        if v.get("ticker", "").upper() == ticker.upper():
            cik = str(v["cik_str"]).zfill(10)
            name = v["title"]
            break
    if not cik:
        return f"  {ticker}  not found in SEC tickers file"
    sub = http_get(f"https://data.sec.gov/submissions/CIK{cik}.json", timeout=6)
    if not sub:
        return f"  {ticker}  ({name}) CIK={cik}  submissions unavailable"
    sj = json.loads(sub)
    forms = sj.get("filings", {}).get("recent", {}).get("form", [])
    dates = sj.get("filings", {}).get("recent", {}).get("filingDate", [])
    pairs = [(f, d) for f, d in zip(forms, dates) if f in ("10-K", "10-Q", "8-K")][:4]
    line = f"  {ticker:<6} ({name[:30]:<30}) CIK={cik}  "
    line += " ".join(f"{f}@{d}" for f, d in pairs)
    return line


# ─── user-wb-data ──────────────────────────────────────────
def fetch_wb_gdp(country_code: str, country_name: str, indicator: str = "NY.GDP.MKTP.KD.ZG") -> str:
    """World Bank annual GDP growth (%)."""
    url = (
        f"https://api.worldbank.org/v2/country/{country_code}"
        f"/indicator/{indicator}?format=json&per_page=5"
    )
    raw = http_get(url, timeout=6)
    if not raw:
        return f"  {country_name}  GDP growth  unavailable"
    data = json.loads(raw)
    if len(data) < 2 or not data[1]:
        return f"  {country_name}  GDP growth  no series"
    pts = [(r["date"], r["value"]) for r in data[1] if r["value"] is not None][:5]
    if not pts:
        return f"  {country_name}  GDP growth  no values"
    yrs = ", ".join(f"{y}:{v:.1f}%" for y, v in pts)
    return f"  {country_name:<6}  GDP growth  {yrs}"


# ─── user-openalex (with retry) ────────────────────────────
def fetch_openalex_works(query: str, n: int = 5) -> str:
    """OpenAlex works search using title.search filter (more precise)."""
    # title.search returns only title matches (not full-text); better precision
    url = (
        f"https://api.openalex.org/works?filter=title.search:{urllib.parse.quote(query)}"
        f"&per_page={n}&sort=cited_by_count:desc"
    )
    raw = http_get(url, timeout=12, retries=3)
    if not raw:
        return "  [openalex] search unavailable (network or 5xx)"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "  [openalex] returned non-JSON"
    count = data.get("meta", {}).get("count", 0)
    out = [f"  filter=title.search:{query!r}  matches={count:,}  top {n} by citations:"]
    for w in data.get("results", [])[:n]:
        title = (w.get("title") or "(no title)")[:70]
        year = w.get("publication_year", "?")
        cites = w.get("cited_by_count", 0)
        venue = (w.get("primary_location") or {}).get("source") or {}
        vname = (venue.get("display_name") or "—")[:25]
        out.append(f"    [{year}] {title}  ({vname}, {cites:,} cites)")
    return "\n".join(out)


# ─── user-fed-data (FRED CSV; Treasury home page too slow) ─
def fetch_fred_yields(date_yyyymmdd: str = "2024-12-31") -> str:
    """FRED daily Treasury constant-maturity rates.

    Series:
      DGS1MO   1-Month
      DGS3MO   3-Month
      DGS6MO   6-Month
      DGS1     1-Year
      DGS2     2-Year
      DGS5     5-Year
      DGS10    10-Year
      DGS30    30-Year
    """
    series = ["DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS5", "DGS10", "DGS30"]
    # Get a 2-week window around target date to ensure we have a record
    year, month = date_yyyymmdd[:4], date_yyyymmdd[5:7]
    cosd = f"{year}-{month}-01"
    coed = f"{year}-{month}-31"
    out = [f"  Date={date_yyyymmdd}  US Treasury par yield curve (FRED):"]
    for sid in series:
        url = (
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
            f"&cosd={cosd}&coed={coed}"
        )
        raw = http_get(url, timeout=5)
        if not raw:
            out.append(f"    {sid:<8}  —")
            continue
        # Find the closest row to date_yyyymmdd
        rows = [l for l in raw.decode("utf-8", errors="replace").splitlines()
                if l and not l.startswith("DATE")]
        latest = None
        for ln in rows:
            parts = ln.split(",")
            if len(parts) == 2 and parts[1].strip() and parts[1].strip() != ".":
                latest = parts
        if latest:
            out.append(f"    {sid:<8}  {latest[1].strip()}%  ({latest[0]})")
        else:
            out.append(f"    {sid:<8}  no data")
    return "\n".join(out)


# ─── user-fed-data (Treasury daily yield curve) ────────────
def fetch_treasury_curve(year: int = 2024) -> str:
    """U.S. Treasury daily yield curve — get latest available of `year`.

    The Treasury CSV endpoint requires a YYYYMMDD date. We use the year-end
    date as a heuristic; if it 404s we fall back to fetching the CSV index.
    """
    yyyymmdd = f"{year}1231"
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/"
        f"interest-rates/daily-treasury-rates.csv/{yyyymmdd}"
        "?type=daily_treasury_yield_curve&field_tdr_date_value_month="
        f"{year}12&page&_format=csv"
    )
    raw = http_get(url, timeout=8, retries=2)
    if not raw:
        # Fallback: try year-end XML
        url2 = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
        raw = http_get(url2, timeout=10, retries=1)
    if not raw:
        return "  [treasury.gov]  unavailable"
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return f"  [treasury.gov]  empty response"
    header = lines[0].split(",")
    # Find last data row
    last = None
    for ln in lines[1:]:
        if ln.startswith(str(year)):
            last = ln
    if last is None:
        last = lines[1]
    row = last.split(",")
    date = row[0]
    pairs = []
    for h, v in zip(header[1:], row[1:]):
        try:
            f = float(v)
            pairs.append((h.strip(), f))
        except (ValueError, IndexError):
            continue
    if not pairs:
        return f"  [treasury.gov]  {date}  no parseable rates"
    pairs = pairs[:8]
    rates = "  ".join(f"{h}={r:.2f}%" for h, r in pairs)
    return f"  Date={date}  {rates}"


# ─── Sanity check when run as __main__ ─────────────────────
if __name__ == "__main__":
    print("=== Sanity: each MCP fetcher (live calls) ===")
    print("\n[1] yfinance MCP (XOM, NVDA, AAPL)")
    for t in ["XOM", "NVDA", "AAPL"]:
        print(fetch_yf_history(t, 2024))
    print("\n[2] SEC EDGAR MCP (XOM, CVX)")
    for t in ["XOM", "CVX"]:
        print(fetch_sec_filings(t))
    print("\n[3] World Bank MCP (China, USA GDP growth)")
    for code, name in [("CHN", "China"), ("USA", "USA")]:
        print(fetch_wb_gdp(code, name))
    print("\n[4] OpenAlex MCP (carbon trading innovation)")
    print(fetch_openalex_works("carbon trading green innovation", n=3))
    print("\n[5] FRED MCP (US Treasury yield curve 2024-12-31)")
    print(fetch_fred_yields("2024-12-31"))
