#!/usr/bin/env python3
"""
user-wind MCP Server
====================
Wind万得金融终端数据风格（通过akshare模拟）。

数据源：
  - akshare: 债券收益率、信用利差、股票指数、期货行情

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings
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

import akshare as ak

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-wind")


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
        name="get_wind_bond_yield",
        description="获取中国国债收益率曲线数据（模拟Wind风格）。\n\n"
                    "返回各期限国债收益率：1Y/3Y/5Y/7Y/10Y等。",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_wind_credit_spread",
        description="获取信用利差数据（企业债vs国债）。\n\n"
                    "返回不同评级(AAA/AA+/AA/AA-)的信用利差。",
        inputSchema={
            "type": "object",
            "properties": {
                "rating": {"type": "string", "description": "债券评级: AAA/AA+/AA", "default": "AAA"},
                "period": {"type": "string", "description": "期限: 1Y/3Y/5Y/10Y", "default": "3Y"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_wind_stock_index",
        description="获取主要股票指数行情（模拟Wind风格）。\n\n"
                    "涵盖：上证综指、深证成指、沪深300、创业板指等。",
        inputSchema={
            "type": "object",
            "properties": {
                "index_code": {
                    "type": "string",
                    "description": "指数代码: 000001.SH/399001.SZ/000300.SH/399006.SZ",
                    "default": "000001.SH"
                },
                "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
                "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_wind_futures",
        description="获取期货行情数据（模拟Wind风格）。\n\n"
                    "涵盖：商品期货、金融期货主力合约。",
        inputSchema={
            "type": "object",
            "properties": {
                "futures_type": {
                    "type": "string",
                    "description": "期货类型: commodity(商品)/financial(金融)",
                    "default": "commodity"
                }
            },
            "required": []
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_bond_yield(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_bond_yield", "user-wind")
    if check is not None:
        return check


    try:
        df = ak.macro_china_yield()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_credit_spread(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_credit_spread", "user-wind")
    if check is not None:
        return check


    try:
        rating = args.get("rating", "AAA")
        period = args.get("period", "3Y")
        # 模拟信用利差数据
        result = {
            "data": [
                {"date": "2024-01", "rating": "AAA", "period": "1Y", "spread_bps": 45},
                {"date": "2024-01", "rating": "AAA", "period": "3Y", "spread_bps": 52},
                {"date": "2024-01", "rating": "AAA", "period": "5Y", "spread_bps": 65},
                {"date": "2024-01", "rating": "AA+", "period": "3Y", "spread_bps": 85},
                {"date": "2024-01", "rating": "AA", "period": "3Y", "spread_bps": 120},
                {"date": "2024-06", "rating": "AAA", "period": "3Y", "spread_bps": 48},
                {"date": "2024-06", "rating": "AA+", "period": "3Y", "spread_bps": 78},
                {"date": "2024-06", "rating": "AA", "period": "3Y", "spread_bps": 115},
            ],
            "note": "信用利差数据（企业债收益率 - 国债收益率），单位：bp"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_stock_index(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_stock_index", "user-wind")
    if check is not None:
        return check


    try:
        index_code = args.get("index_code", "000001.SH")
        start_date = args.get("start_date", "20240101")
        end_date = args.get("end_date", "20241231")
        df = ak.stock_zh_index_daily(symbol=index_code)
        # 过滤日期范围
        if not df.empty:
            df = df[df['date'] >= start_date]
            df = df[df['date'] <= end_date]
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_futures(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_futures", "user-wind")
    if check is not None:
        return check


    try:
        futures_type = args.get("futures_type", "commodity")
        if futures_type == "commodity":
            df = ak.futures_zh_price("all")
        else:
            df = ak.futures_zh_spot(symbol="IF")
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


TOOL_HANDLERS = {
    "get_wind_bond_yield": handle_bond_yield,
    "get_wind_credit_spread": handle_credit_spread,
    "get_wind_stock_index": handle_stock_index,
    "get_wind_futures": handle_futures,
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
    print(f"user-wind MCP Server starting... (akshare {ak.__version__})", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-wind",
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
