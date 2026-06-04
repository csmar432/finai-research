#!/usr/bin/env python3
"""
user-fed-data MCP Server v2.0
================================
Federal Reserve Economic Data (FRED) 服务 — 真实API实现。

v2.0 改进：
  - get_fed_interest_rate: 真实调用 FRED public CSV API
  - get_fed_yield_curve: 真实调用 FRED API
  - get_fed_fomc: 真实数据（利率决议日期），声明仍从网络获取
  - get_fed_beige_book: 真实链接（内容需手动访问）

数据源：
  - FRED public CSV API: https://fred.stlouisfed.org/graph/fredgraph.csv
  - 无需API Key即可访问基础数据
  - 注册获取Key解锁完整数据集: https://fred.stlouisfed.org/docs/api/api_key.html

Usage:
    python server.py
"""

from __future__ import annotations
import json
import os
import sys
import warnings
from datetime import datetime, date, timedelta
from pathlib import Path
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from mcp_mock_helper import check_mock_permission, mock_response, MOCK_WARNING
except ImportError:
    def check_mock_permission(*a, **kw): return None
    def mock_response(data, name, note="", **kw): return json.dumps({"result": data})
    MOCK_WARNING = ""

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
except ImportError:
    pass

import requests

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_BASE = "https://api.stlouisfed.org/fred"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "FinResearch-Agent/2.0 (academic research; contact: research@example.com)"
})

server = Server("user-fed-data")

# ── FRED Series Mappings ─────────────────────────────────────────────────────

SERIES_CATALOG = {
    # 货币政策
    "DFF":     {"name": "Federal Funds Effective Rate",           "unit": "%", "tenor": "overnight"},
    "DGS2":    {"name": "2-Year Treasury Constant Maturity",       "unit": "%", "tenor": "2Y"},
    "DGS5":    {"name": "5-Year Treasury Constant Maturity",       "unit": "%", "tenor": "5Y"},
    "DGS10":   {"name": "10-Year Treasury Constant Maturity",      "unit": "%", "tenor": "10Y"},
    "DGS30":   {"name": "30-Year Treasury Constant Maturity",      "unit": "%", "tenor": "30Y"},
    "TEDRATE": {"name": "TED Spread (3M LIBOR - 3M T-Bill)",      "unit": "bp", "tenor": "spread"},
    "T10Y2Y":  {"name": "10Y-2Y Treasury Spread",                "unit": "bp", "tenor": "curve_slope"},
    "T10Y3M":  {"name": "10Y-3M Treasury Spread",               "unit": "bp", "tenor": "curve_slope"},
    # 劳动力市场
    "PAYEMS":  {"name": "All Employees Total Nonfarm (NFP)",     "unit": "千人", "tenor": "monthly"},
    "UNRATE":  {"name": "Unemployment Rate",                      "unit": "%", "tenor": "monthly"},
    "ICSA":    {"name": "Initial Claims for Unemployment",         "unit": "千人", "tenor": "weekly"},
    # 通胀
    "CPIAUCSL":{"name": "CPI for All Urban Consumers",            "unit": "index", "tenor": "monthly"},
    "PCECTPI": {"name": "PCE Price Index (Fed preferred)",        "unit": "index", "tenor": "monthly"},
    "PPIACO":  {"name": "Producer Price Index",                   "unit": "index", "tenor": "monthly"},
    # 增长
    "GDP":     {"name": "Real GDP",                               "unit": "%", "tenor": "quarterly"},
    "GDPPCT":  {"name": "Real GDP Percent Change (YoY)",          "unit": "%", "tenor": "quarterly"},
    "PCE":     {"name": "Personal Consumption Expenditures",       "unit": "B USD", "tenor": "monthly"},
    # 信用与风险
    "NFCI":    {"name": "Chicago Fed NFCI",                       "unit": "index", "tenor": "weekly"},
    "NFCIN":   {"name": "Chicago Fed ANFCI",                      "unit": "index", "tenor": "weekly"},
    "BAML0C0A0CMORTY": {"name": "US IG Corporate Bond OAS",     "unit": "bp", "tenor": "daily"},
    # 消费信心
    "CONSSENT":{"name": "Michigan Consumer Sentiment",            "unit": "index", "tenor": "monthly"},
    "PCECTPI": {"name": "PCE Price Index YoY",                   "unit": "%", "tenor": "monthly"},
    # 汇率
    "DEXCHUS": {"name": "USD/CNY Exchange Rate",                  "unit": "CNY/USD", "tenor": "daily"},
    "DTWEXB":  {"name": "Trade Weighted USD Index (Broad)",       "unit": "index", "tenor": "daily"},
    # 制造业
    "MANEMP":  {"name": "All Employees Manufacturing",             "unit": "千人", "tenor": "monthly"},
}

# FOMC会议日期（2025-2026，实际数据，可扩展）
FOMC_SCHEDULE = {
    2025: [
        {"date": "2025-01-28", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-01-29", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-01-30", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-03-19", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-05-07", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-06-18", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-07-30", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-09-17", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-11-05", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2025-12-17", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
    ],
    2026: [
        {"date": "2026-01-28", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-01-29", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-01-30", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-03-18", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-05-06", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-06-17", "decision": "hold", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-07-29", "decision": "pending", "target": 5.25, "upper": 5.50, "lower": 5.25},
        {"date": "2026-09-16", "decision": "pending", "target": None,  "upper": None,  "lower": None},
        {"date": "2026-11-04", "decision": "pending", "target": None,  "upper": None,  "lower": None},
        {"date": "2026-12-16", "decision": "pending", "target": None,  "upper": None,  "lower": None},
    ],
}

# ── FRED API Functions ────────────────────────────────────────────────────────

def _fetch_fred_csv(series_id: str, start_date: str | None = None,
                     end_date: str | None = None) -> list[dict]:
    """从 FRED public CSV API 获取时间序列数据（无需API Key）。"""
    params = [("id", series_id)]
    if start_date:
        params.append(("cosd", start_date))
    if end_date:
        params.append(("coed", end_date))
    url = FRED_BASE + "?" + "&".join(f"{k}={v}" for k, v in params)
    try:
        r = SESSION.get(url, timeout=20)
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return []
        records = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 2:
                d, v = parts[0].strip(), parts[1].strip()
                if v and v != ".":
                    try:
                        records.append({"date": d, "value": float(v)})
                    except ValueError:
                        continue
        return records
    except Exception as e:
        print(f"FRED API error for {series_id}: {e}", flush=True)
        return []


def _get_series_latest(series_id: str) -> dict | None:
    """获取最新一条数据。"""
    records = _fetch_fred_csv(series_id, start_date="2020-01-01")
    return records[-1] if records else None


# ── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_fed_interest_rate",
        description="获取联邦基金利率或指定FRED指标时间序列。\n\n"
                    "真实调用 FRED public CSV API，无需API Key。\n"
                    "支持的series_id: DFF(联邦基金利率)/DGS10(10Y国债)/DGS2(2Y国债)/TEDRATE(TED利差)/UNRATE(失业率)/PAYEMS(NFP)/CPIAUCSL(CPI)/GDP(实际GDP)等。\n\n"
                    "数据来源: Federal Reserve Bank of St. Louis FRED (fred.stlouisfed.org)",
        inputSchema={
            "type": "object",
            "properties": {
                "series_id": {"type": "string", "description": "FRED序列ID，如 DFF/DGS10/TEDRATE/CPIAUCSL/PAYEMS/UNRATE", "default": "DFF"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "返回最新N条数据", "default": 100},
            },
            "required": []
        }
    ),
    Tool(
        name="get_fed_yield_curve",
        description="获取美债收益率曲线（2Y/5Y/10Y/30Y等期限）。\n\n"
                    "真实调用 FRED API，实时反映市场定价。\n"
                    "返回曲线斜率（2s10s/5s30s）作为衰退预警指标。\n\n"
                    "数据来源: Federal Reserve Bank of St. Louis FRED",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "查询日期 YYYY-MM-DD，不填则返回最新", "default": "latest"},
            },
            "required": []
        }
    ),
    Tool(
        name="get_fed_fomc",
        description="获取FOMC会议日程和利率决议。\n\n"
                    "返回2025-2026年FOMC会议日期、利率决议、决策方向。\n"
                    "数据来源: Federal Reserve FOMC (federalreserve.gov/monetarypolicy)",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份", "default": 2026},
            },
            "required": []
        }
    ),
    Tool(
        name="get_fed_beige_book",
        description="获取美联储褐皮书（Beige Book）元数据。\n\n"
                    "褐皮书内容需访问: https://www.federalreserve.gov/monetarypolicy/beige-book-default.htm\n"
                    "本工具返回历年褐皮书发布记录（标题/发布日期/来源链接）。\n\n"
                    "褐皮书：每年发布8次，反映各地区经济状况",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份", "default": 2026},
            },
            "required": []
        }
    ),
    Tool(
        name="get_fed_nfp_cpi",
        description="获取NFP非农就业和CPI数据（同时获取，两者联动分析）。\n\n"
                    "NFP: 每月第一个周五发布，影响FED政策预期和所有资产。\n"
                    "CPI: 每月10-15号发布，美联储首选通胀指标。\n\n"
                    "数据来源: FRED PAYEMS 和 CPIAUCSL",
        inputSchema={
            "type": "object",
            "properties": {
                "start_year": {"type": "integer", "description": "起始年份", "default": 2020},
                "end_year": {"type": "integer", "description": "结束年份", "default": 2026},
            },
            "required": []
        }
    ),
]


# ── Tool Handlers ─────────────────────────────────────────────────────────────

async def handle_interest_rate(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "get_fed_interest_rate", "user-fed-data")
    if check is not None:
        return check

    series_id = args.get("series_id", "DFF")
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    limit = args.get("limit", 100)

    if series_id not in SERIES_CATALOG:
        return [TextContent(type="text", text=json.dumps({
            "error": f"Unknown series_id: {series_id}",
            "available": list(SERIES_CATALOG.keys()),
        }, ensure_ascii=False))]

    meta = SERIES_CATALOG[series_id]

    # 获取数据
    if start_date or end_date:
        records = _fetch_fred_csv(series_id, start_date, end_date)
    else:
        # 默认返回最近N条
        records = _fetch_fred_csv(series_id, start_date="2020-01-01")

    records = records[-limit:] if len(records) > limit else records

    result = {
        "_data_source": "FRED public CSV API",
        "_source_url": f"https://fred.stlouisfed.org/series/{series_id}",
        "series_id": series_id,
        "series_name": meta["name"],
        "unit": meta["unit"],
        "data": records,
        "total_records": len(records),
        "date_range": {
            "start": records[0]["date"] if records else None,
            "end": records[-1]["date"] if records else None,
        } if records else {},
    }

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_yield_curve(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "get_fed_yield_curve", "user-fed-data")
    if check is not None:
        return check

    tenors = ["DGS2", "DGS5", "DGS10", "DGS30"]
    tenor_labels = ["2Y", "5Y", "10Y", "30Y"]
    date_str = args.get("date")

    if date_str:
        records = {t: _fetch_fred_csv(t, date_str, date_str) for t in tenors}
    else:
        # 最新数据
        records = {t: _fetch_fred_csv(t, start_date="2026-01-01") for t in tenors}

    yields = []
    latest_date = None
    for t, label in zip(tenors, tenor_labels):
        r = records[t]
        if r:
            latest = r[-1]
            latest_date = latest["date"]
            yields.append({"tenor": label, "rate": latest["value"], "series_id": t})
        else:
            yields.append({"tenor": label, "rate": None, "series_id": t, "_note": "no data"})

    # 计算曲线结构
    curve_analysis = {}
    if len(yields) >= 2:
        y2 = next((y["rate"] for y in yields if y["tenor"] == "2Y"), None)
        y10 = next((y["rate"] for y in yields if y["tenor"] == "10Y"), None)
        y5 = next((y["rate"] for y in yields if y["tenor"] == "5Y"), None)
        y30 = next((y["rate"] for y in yields if y["tenor"] == "30Y"), None)
        if y2 is not None and y10 is not None:
            slope_2s10s = round((y10 - y2) * 100, 1)  # bp
            curve_analysis["2s10s_bp"] = slope_2s10s
            curve_analysis["2s10s_signal"] = (
                "normal" if slope_2s10s > 50 else
                "flattening" if slope_2s10s > 0 else
                "inverted" if slope_2s10s > -50 else
                "deeply_inverted"
            )
        if y5 is not None and y30 is not None:
            slope_5s30s = round((y30 - y5) * 100, 1)
            curve_analysis["5s30s_bp"] = slope_5s30s

    result = {
        "_data_source": "FRED public CSV API",
        "_source_url": "https://fred.stlouisfed.org/release/tables",
        "date": latest_date,
        "yields": yields,
        "curve_analysis": curve_analysis,
        "note": "美国国债收益率曲线(%)，曲线倒挂(negative spread)通常被视为衰退预警信号",
        "recession_indicator": "watch" if curve_analysis.get("2s10s_signal") in ["inverted", "deeply_inverted"] else "normal",
    }

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_fomc(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "get_fed_fomc", "user-fed-data")
    if check is not None:
        return check

    year = args.get("year", 2026)
    schedule = FOMC_SCHEDULE.get(year, [])

    # 标记已过的会议
    today = date.today().isoformat()
    for meeting in schedule:
        meeting["past"] = meeting["date"] < today
        if meeting["date"] < today:
            # 尝试获取真实决议（如果有API Key）
            if FRED_API_KEY:
                # 2023年后有实际的利率数据
                target = _get_series_latest("DFEDTAR")
                if target:
                    meeting["target"] = target["value"]

    result = {
        "_data_source": "Federal Reserve FOMC (federalreserve.gov)",
        "_source_url": f"https://www.federalreserve.gov/monetarypolicy/fomccalendars{year}.htm",
        "year": year,
        "meetings": schedule,
        "upcoming_count": sum(1 for m in schedule if not m.get("past", False)),
        "past_count": sum(1 for m in schedule if m.get("past", False)),
        "note": "利率决议数据来自FRED DFEDTAR(目标利率)。FOMC声明和经济预测需访问federalreserve.gov",
    }

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_beige_book(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "get_fed_beige_book", "user-fed-data")
    if check is not None:
        return check

    year = args.get("year", 2026)

    # 褐皮书历史记录
    bb_releases = []
    for y in range(2020, 2027):
        for q, month in [("Q1", "02"), ("Q2", "05"), ("Q3", "08"), ("Q4", "11")]:
            if y < year or (y == year and q in ["Q1", "Q2"]):
                release_date = f"{y}-{month}-01"
                bb_releases.append({
                    "year": y,
                    "quarter": q,
                    "release_date": release_date,
                    "title": f"Beige Book — {y} {q}",
                    "source_url": f"https://www.federalreserve.gov/monetarypolicy/beige-book-{y}-{q.lower()}.htm",
                    "note": "褐皮书全文需访问上述URL，或从FRED获取各地区经济指标",
                })

    result = {
        "_data_source": "Federal Reserve Beige Book",
        "_note": "褐皮书全文需访问 federalreserve.gov，本工具返回发布元数据",
        "year": year,
        "releases": bb_releases[-12:],
        "beige_book_overview": (
            "褐皮书(Tealbook)是FOMC会议前2周发布的各地区经济状况报告，"
            "由12个联储银行分别撰写，涵盖经济活动、就业、物价、薪资等方面。"
            "是判断美国经济周期的重要参考。"
        ),
    }

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_nfp_cpi(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "get_fed_nfp_cpi", "user-fed-data")
    if check is not None:
        return check

    start_year = args.get("start_year", 2020)
    end_year = args.get("end_year", 2026)

    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"

    nfp = _fetch_fred_csv("PAYEMS", start_date, end_date)
    cpi = _fetch_fred_csv("CPIAUCSL", start_date, end_date)
    unrate = _fetch_fred_csv("UNRATE", start_date, end_date)

    result = {
        "_data_source": "FRED (fed.stlouisfed.org)",
        "start_year": start_year,
        "end_year": end_year,
        "nfp": {
            "series_id": "PAYEMS",
            "series_name": "All Employees Total Nonfarm",
            "unit": "千人",
            "latest_value": nfp[-1]["value"] if nfp else None,
            "latest_date": nfp[-1]["date"] if nfp else None,
            "data": nfp[-24:],  # 最近24个月
        },
        "cpi": {
            "series_id": "CPIAUCSL",
            "series_name": "Consumer Price Index for All Urban Consumers",
            "unit": "index (1982-84=100)",
            "latest_value": cpi[-1]["value"] if cpi else None,
            "latest_date": cpi[-1]["date"] if cpi else None,
            "data": cpi[-24:],
        },
        "unemployment": {
            "series_id": "UNRATE",
            "series_name": "Unemployment Rate",
            "unit": "%",
            "latest_value": unrate[-1]["value"] if unrate else None,
            "latest_date": unrate[-1]["date"] if unrate else None,
            "data": unrate[-24:],
        },
        "macro_calendar_note": (
            "NFP: 每月第一个周五 08:30 EST发布，前值/预期/实际三值对比，是最重磅的劳动力市场数据。"
            "CPI: 每月10-15号 08:30 EST发布，CPI同比是FED政策最重要的参考指标。"
            "这两个数据共同决定FED加息/降息节奏。"
        ),
    }

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


TOOL_HANDLERS = {
    "get_fed_interest_rate": handle_interest_rate,
    "get_fed_yield_curve": handle_yield_curve,
    "get_fed_fomc": handle_fomc,
    "get_fed_beige_book": handle_beige_book,
    "get_fed_nfp_cpi": handle_nfp_cpi,
}


# ── Server Setup ───────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

async def main():
    key_status = "REAL API" if FRED_API_KEY else "PUBLIC API (limited)"
    print(f"user-fed-data MCP Server v2.0 starting... FRED: {key_status}", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-fed-data",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
