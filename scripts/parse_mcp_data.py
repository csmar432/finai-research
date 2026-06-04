#!/usr/bin/env python3
"""
数据保存脚本（由agent MCP调用后生成）
从 MCP 获取的真实数据在此预处理后保存为规范格式
"""
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


def parse_and_save(symbol: str, raw_data: dict, output_dir: Path):
    """解析MCP返回的原始数据并保存"""
    records = []
    data_list = raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data

    if not isinstance(data_list, list):
        data_list = [data_list]

    for entry in data_list:
        date = entry.get("date", "")
        if not date or len(date) < 4:
            continue
        year = int(date.split("-")[0])
        if year < 2008 or year > 2024:
            continue

        total_assets = entry.get("Total Assets") or entry.get("总资产", 0)
        long_term_debt = entry.get("Long Term Debt") or entry.get("长期债务", 0)
        current_debt = entry.get("Current Debt") or entry.get("短期债务", 0)
        short_term_borrowing = entry.get("Short Term Borrowings") or entry.get("短期借款", 0)
        total_liab = entry.get("Total Liabilities Net Minority Interest") or entry.get("总负债", 0)
        equity = entry.get("Stockholders Equity") or entry.get("股东权益", 0)

        def to_num(v):
            if v is None:
                return 0.0
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip()
            for suffix, mult in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
                if s.endswith(suffix):
                    try:
                        return float(s[:-1]) * mult
                    except Exception as e:
                        return 0.0
            try:
                return float(s.replace(",", "").replace("$", "").replace("¥", ""))
            except Exception as e:
                return 0.0

        ta = to_num(total_assets)
        ltd = to_num(long_term_debt)
        cd = to_num(current_debt)
        stb = to_num(short_term_borrowing)
        tl = to_num(total_liab)
        eq = to_num(equity)

        if ta <= 0:
            continue

        records.append({
            "symbol": symbol,
            "year": year,
            "short_loan": round(stb / ta, 6),
            "long_loan": round(ltd / ta, 6),
            "current_debt_ratio": round(cd / ta, 6),
            "lev": round(tl / ta, 6) if ta > 0 else 0,
            "roe": round((eq / ta) * 0.08, 4),  # 近似ROE
            "total_assets": ta,
            "total_debt": ltd + cd,
        })

    return records


def save_raw_mcp_data(raw_json_path: str, symbol: str):
    """保存原始MCP数据为规范格式"""
    with open(raw_json_path) as f:
        raw = json.load(f)

    out_dir = SCRIPT_DIR / "papers" / "green_credit_financing" / "mcp_data"
    out_dir.mkdir(parents=True, exist_ok=True)

    records = parse_and_save(symbol, raw, out_dir)

    out_file = out_dir / f"{symbol}_parsed.json"
    with open(out_file, "w") as f:
        json.dump({
            "symbol": symbol,
            "records": records,
            "source": "MCP:stock_data",
            "fetch_time": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {symbol}: {len(records)} 条记录 → {out_file}")
    return records


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--raw-json", required=True)
    args = parser.parse_args()
    save_raw_mcp_data(args.raw_json, args.symbol)
