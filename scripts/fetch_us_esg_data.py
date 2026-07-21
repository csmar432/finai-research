"""直接用 yfinance Python 包拉取美股能源公司财务数据。

P0 修复 2026-06-28: MCP yfinance 失败时 fallback，避免 P0 数据获取
失败导致下游 docx/figures 无法生成。

输出 data/us_esg_panel.csv，含 us_esg_regression.py 期望的全部列。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# 16 个能源公司（与 us_esg_regression.py 的 ENERGY_TICKERS 对齐）
ENERGY_TICKERS = [
    "XOM", "CVX",  # Integrated Majors
    "COP", "EOG", "PXD", "DVN", "FANG", "OXY",  # E&P
    "PSX", "VLO", "MPC",  # Refining
    "WMB", "KMI",  # Midstream
    "SLB", "HAL", "BKR",  # Equipment & Services
]

SECTOR_MAP = {
    "XOM": "integrated", "CVX": "integrated",
    "COP": "e&p", "EOG": "e&p", "PXD": "e&p", "DVN": "e&p",
    "FANG": "e&p", "OXY": "e&p",
    "PSX": "refining", "VLO": "refining", "MPC": "refining",
    "WMB": "midstream", "KMI": "midstream",
    "SLB": "equipment", "HAL": "equipment", "BKR": "equipment",
}

SECTOR_ESG_TIER = {
    "integrated": "high",
    "refining": "high",
    "midstream": "medium",
    "e&p": "low",
    "equipment": "low",
}

YEARS = list(range(2018, 2025))  # 2018-2024


def _get_year_value(stmt_df: pd.DataFrame, field: str, year: int) -> float | None:
    """从 yfinance statement df 中取指定年份的值。

    yfinance 返回的列是 Timestamp，需找到离 year-12-31 最近的列。
    """
    if stmt_df is None or stmt_df.empty:
        return None
    target = pd.Timestamp(f"{year}-12-31")
    if target not in stmt_df.columns:
        # 找最近的列（idxmin 在 TimedeltaIndex 上不可用，手动计算）
        diffs = [(col, abs((col - target).days)) for col in stmt_df.columns]
        nearest = min(diffs, key=lambda x: x[1])[0]
    else:
        nearest = target
    # 找匹配 field 的行
    for idx in stmt_df.index:
        if isinstance(idx, str) and field.lower() in idx.lower():
            val = stmt_df.loc[idx, nearest]
            if pd.notna(val):
                return float(val)
    return None


def fetch_ticker_panel(ticker: str) -> list[dict]:
    """对单个 ticker 拉所有年份财务数据。"""
    print(f"  Fetching {ticker}...", flush=True)
    try:
        t = yf.Ticker(ticker)
        bs = t.balance_sheet
        inc = t.income_stmt
        cf = t.cashflow
    except Exception as e:
        print(f"    FAIL {ticker}: {e}")
        return []

    sector = SECTOR_MAP.get(ticker, "e&p")
    esg_tier = SECTOR_ESG_TIER.get(sector, "medium")
    rows = []
    for year in YEARS:
        rec = {"ticker": ticker, "year": year, "sector": sector, "esg_tier": esg_tier}
        rec["total_assets"]   = _get_year_value(bs, "total assets", year)
        rec["total_debt"]     = _get_year_value(bs, "total debt", year)
        rec["long_term_debt"] = _get_year_value(bs, "long term debt", year)
        rec["current_debt"]   = _get_year_value(bs, "current debt", year)
        rec["equity"]         = _get_year_value(bs, "stockholders equity", year)
        rec["cash"]           = _get_year_value(bs, "cash and cash equivalents", year) or _get_year_value(bs, "cash", year)
        rec["ppe"]            = _get_year_value(bs, "property plant equipment", year) or _get_year_value(bs, "net ppe", year)
        rec["revenue"]        = _get_year_value(inc, "total revenue", year)
        rec["net_income"]     = _get_year_value(inc, "net income", year)
        rec["interest_exp"]   = _get_year_value(inc, "interest expense", year)
        rec["op_cashflow"]    = _get_year_value(cf, "operating cash flow", year) or _get_year_value(cf, "cash flow from continuing operating", year)
        rec["market_cap"]     = None  # yfinance quote 才有
        rec["book_value"]     = rec["equity"]
        rec["shares_out"]     = None
        rows.append(rec)
    return rows


def main():
    out_dir = Path("papers/us_esg_financing")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "panel_data.csv"

    print(f"Fetching {len(ENERGY_TICKERS)} energy tickers × {len(YEARS)} years via yfinance Python...")
    all_rows = []
    for ticker in ENERGY_TICKERS:
        rows = fetch_ticker_panel(ticker)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df.to_csv(out_csv, index=False)
    print(f"\n✅ Saved {len(df)} rows to {out_csv}")
    print(f"   Non-null per column:")
    for col in df.columns:
        nonnull = df[col].notna().sum()
        print(f"     {col}: {nonnull}/{len(df)}")


if __name__ == "__main__":
    main()
