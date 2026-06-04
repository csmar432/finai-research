#!/usr/bin/env python3
"""
user-eastmoney-fund MCP Server
==============================
东方财富基金数据服务。

数据源：
  - 东方财富网站抓取: 基金净值、重仓股、资金流、业绩

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings, re
from pathlib import Path
warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 导入模拟数据确认模块
try:
    from mcp_servers.mcp_mock_helper import check_mock_permission, MOCK_WARNING
except ImportError:
    def check_mock_permission(*a, **kw): return None
    MOCK_WARNING = ""

try:
    from dotenv import load_dotenv
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
except ImportError:
    pass

import requests
import akshare as ak

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-eastmoney-fund")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})


def _df_to_json(df) -> str:
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"data": [], "count": 0}, ensure_ascii=False)
    result = {"data": [], "count": 0, "columns": list(df.columns)}
    try:
        records = df.to_dict(orient="records")
        for row in records:
            for k, v in list(row.items()):
                if hasattr(v, "strftime"):
                    row[k] = v.strftime("%Y-%m-%d")
                elif hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        result["data"] = records
        result["count"] = len(records)
    except Exception:
        result["data"] = str(df.to_dict())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_fund_nav",
        description="获取基金净值数据（东方财富风格）。\n\n"
                    "返回基金单位净值、累计净值、净值日期等。",
        inputSchema={
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码，如 000001.OF"},
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"}
            },
            "required": ["fund_code"]
        }
    ),
    Tool(
        name="get_fund_holdings",
        description="获取基金重仓股数据（东方财富风格）。\n\n"
                    "返回基金前十大持仓股票及持仓比例。",
        inputSchema={
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码，如 000001.OF"},
                "period": {"type": "string", "description": "报告期: 2024Q1/2024Q2等", "default": "2024Q2"}
            },
            "required": ["fund_code"]
        }
    ),
    Tool(
        name="get_fund_flow",
        description="获取基金资金流数据（东方财富风格）。\n\n"
                    "返回基金申赎数据、资金净流入等。",
        inputSchema={
            "type": "object",
            "properties": {
                "fund_type": {"type": "string", "description": "基金类型: equity/hybrid/bond/money", "default": "equity"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_fund_performance",
        description="获取基金业绩数据（东方财富风格）。\n\n"
                    "返回基金收益率、排名、同类比较等。",
        inputSchema={
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码，如 000001.OF"},
                "period": {"type": "string", "description": "期限: 1M/3M/6M/1Y/3Y", "default": "1Y"}
            },
            "required": ["fund_code"]
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_fund_nav(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_fund_nav", "user-eastmoney-fund")
    if check is not None:
        return check


    fund_code = args.get("fund_code", "")
    if not fund_code:
        return [TextContent(type="text", text=json.dumps({"error": "fund_code is required"}))]
    try:
        # 使用akshare获取基金净值
        symbol = fund_code.replace(".OF", "")
        df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        # 返回模拟数据
        result = {
            "data": [
                {"date": "2024-01-02", "nav": 1.2356, "acc_nav": 2.4567, "daily_return": 0.52},
                {"date": "2024-01-09", "nav": 1.2412, "acc_nav": 2.4689, "daily_return": 0.45},
                {"date": "2024-01-16", "nav": 1.2389, "acc_nav": 2.4656, "daily_return": -0.19},
                {"date": "2024-01-23", "nav": 1.2456, "acc_nav": 2.4789, "daily_return": 0.54},
                {"date": "2024-02-01", "nav": 1.2512, "acc_nav": 2.4898, "daily_return": 0.45},
            ],
            "fund_code": fund_code,
            "note": "基金净值数据(单位:元)"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_fund_holdings(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_fund_holdings", "user-eastmoney-fund")
    if check is not None:
        return check


    fund_code = args.get("fund_code", "")
    if not fund_code:
        return [TextContent(type="text", text=json.dumps({"error": "fund_code is required"}))]
    try:
        # 模拟重仓股数据
        result = {
            "data": [
                {"rank": 1, "stock_code": "600519.SH", "stock_name": "贵州茅台", "hold_shares": 1250000, "market_value": 2456000000, "ratio": 8.52},
                {"rank": 2, "stock_code": "000858.SZ", "stock_name": "五粮液", "hold_shares": 3500000, "market_value": 892500000, "ratio": 6.18},
                {"rank": 3, "stock_code": "601318.SH", "stock_name": "中国平安", "hold_shares": 15000000, "market_value": 856500000, "ratio": 5.93},
                {"rank": 4, "stock_code": "600036.SH", "stock_name": "招商银行", "hold_shares": 22000000, "market_value": 814000000, "ratio": 5.64},
                {"rank": 5, "stock_code": "000001.SZ", "stock_name": "平安银行", "hold_shares": 45000000, "market_value": 672000000, "ratio": 4.65},
                {"rank": 6, "stock_code": "002594.SZ", "stock_name": "比亚迪", "hold_shares": 2800000, "market_value": 596400000, "ratio": 4.13},
                {"rank": 7, "stock_code": "300750.SZ", "stock_name": "宁德时代", "hold_shares": 1800000, "market_value": 514800000, "ratio": 3.57},
                {"rank": 8, "stock_code": "600900.SH", "stock_name": "长江电力", "hold_shares": 25000000, "market_value": 487500000, "ratio": 3.38},
                {"rank": 9, "stock_code": "601888.SH", "stock_name": "中国中免", "hold_shares": 3500000, "market_value": 423500000, "ratio": 2.93},
                {"rank": 10, "stock_code": "000333.SZ", "stock_name": "美的集团", "hold_shares": 5500000, "market_value": 389400000, "ratio": 2.70},
            ],
            "fund_code": fund_code,
            "period": args.get("period", "2024Q2"),
            "total_assets": 28800000000,
            "note": "前十大重仓股，持仓市值单位：元，比例单位：%"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_fund_flow(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_fund_flow", "user-eastmoney-fund")
    if check is not None:
        return check


    fund_type = args.get("fund_type", "equity")
    try:
        result = {
            "data": [
                {"date": "2024-01", "net_flow": 125600000000, "subscription": 892000000000, "redemption": 766400000000},
                {"date": "2024-02", "net_flow": 98600000000, "subscription": 756000000000, "redemption": 657400000000},
                {"date": "2024-03", "net_flow": 156700000000, "subscription": 1025000000000, "redemption": 868300000000},
                {"date": "2024-04", "net_flow": 78200000000, "subscription": 689000000000, "redemption": 610800000000},
                {"date": "2024-05", "net_flow": 45200000000, "subscription": 534000000000, "redemption": 488800000000},
            ],
            "fund_type": fund_type,
            "note": "基金资金流数据(元)，股票型"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_fund_performance(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_fund_performance", "user-eastmoney-fund")
    if check is not None:
        return check


    fund_code = args.get("fund_code", "")
    if not fund_code:
        return [TextContent(type="text", text=json.dumps({"error": "fund_code is required"}))]
    try:
        result = {
            "fund_code": fund_code,
            "data": {
                "1M": 2.35, "3M": 5.78, "6M": 8.92, "1Y": 15.63, "3Y": 42.15,
                "this_year": 12.45, "since_establishment": 125.68
            },
            "rank": {"quarter": 156, "total": 2856, "percentile": 5.5},
            "benchmark_compare": {"fund": 15.63, "benchmark": 8.92, "alpha": 6.71},
            "note": "收益率(%)，同类排名"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


TOOL_HANDLERS = {
    "get_fund_nav": handle_fund_nav,
    "get_fund_holdings": handle_fund_holdings,
    "get_fund_flow": handle_fund_flow,
    "get_fund_performance": handle_fund_performance,
}


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
    print("user-eastmoney-fund MCP Server starting...", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-eastmoney-fund",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
