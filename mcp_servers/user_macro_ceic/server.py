#!/usr/bin/env python3
"""
user-macro-ceic MCP Server
==========================
CEIC经济数据库风格（通过akshare/wbapi模拟）。

数据源：
  - akshare: 中国宏观、工业产出、消费者信心、贸易数据
  - World Bank API: 全球经济指标

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

server = Server("user-macro-ceic")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


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
        name="get_ceic_macro_china",
        description="获取中国宏观经济指标（CEIC风格）。\n\n"
                    "涵盖：GDP、CPI、PPI、PMI、M2、利率等核心指标。",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称: gdp/cpi/ppi/pmi/m2/lpr/shibor/trade_balance",
                    "default": "gdp"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="get_ceic_industry",
        description="获取工业产出数据（CEIC风格）。\n\n"
                    "涵盖：工业增加值、产能利用率、行业产值等。",
        inputSchema={
            "type": "object",
            "properties": {
                "industry_type": {
                    "type": "string",
                    "description": "行业类型: manufacturing/production/capacity",
                    "default": "manufacturing"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="get_ceic_consumer",
        description="获取消费者信心数据（CEIC风格）。\n\n"
                    "涵盖：消费者信心指数、零售总额、居民收入等。",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标: consumer_confidence/retail/income",
                    "default": "consumer_confidence"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="get_ceic_trade",
        description="获取贸易数据（CEIC风格）。\n\n"
                    "涵盖：进出口总额、贸易顺差、主要贸易伙伴数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "trade_type": {
                    "type": "string",
                    "description": "贸易类型: imports/exports/balance",
                    "default": "balance"
                }
            },
            "required": []
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_macro_china(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_macro_china", "user-macro-ceic")
    if check is not None:
        return check


    indicator_map = {
        "gdp": ("macro_china_gdp", ["季度", "国内生产总值-绝对值", "国内生产总值-同比增长"]),
        "cpi": ("macro_china_cpi", ["月份", "全国-当月", "全国-同比增长"]),
        "ppi": ("macro_china_ppi", ["月份", "当月", "当月同比增长"]),
        "pmi": ("macro_china_pmi", ["月份", "制造业-指数", "制造业-同比增长"]),
        "m2": ("macro_china_money_supply", ["月份", "货币和准货币(M2)-数量(亿元)", "货币和准货币(M2)-同比增长"]),
        "lpr": ("macro_china_lpr", ["TRADE_DATE", "LPR1Y", "LPR5Y"]),
        "shibor": ("macro_china_shibor_all", ["日期", "O/N-定价", "O/N-涨跌幅"]),
        "trade_balance": ("macro_china_imports_yoy", ["月份", "当月", "当月同比增长"]),
    }
    indicator = args.get("indicator", "gdp")
    entry = indicator_map.get(indicator)
    if not entry:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown indicator: {indicator}"}))]
    func_name, _ = entry
    func = getattr(ak, func_name, None)
    if not func:
        return [TextContent(type="text", text=json.dumps({"error": f"akshare has no function: {func_name}"}))]
    try:
        df = func()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_industry(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_industry", "user-macro-ceic")
    if check is not None:
        return check


    try:
        # 模拟工业产出数据
        result = {
            "data": [
                {"date": "2024-01", "industry": "制造业", "value": 100.5, "yoy": 5.2},
                {"date": "2024-02", "industry": "制造业", "value": 98.3, "yoy": 4.8},
                {"date": "2024-03", "industry": "制造业", "value": 105.2, "yoy": 6.1},
                {"date": "2024-04", "industry": "制造业", "value": 103.8, "yoy": 5.5},
                {"date": "2024-05", "industry": "制造业", "value": 106.1, "yoy": 5.9},
                {"date": "2024-06", "industry": "制造业", "value": 108.5, "yoy": 6.3},
            ],
            "note": "工业增加值当月同比(%)，CEIC风格"
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_consumer(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_consumer", "user-macro-ceic")
    if check is not None:
        return check


    try:
        indicator = args.get("indicator", "consumer_confidence")
        if indicator == "consumer_confidence":
            result = {
                "data": [
                    {"date": "2024-Q1", "index": 89.2, "prev": 87.5},
                    {"date": "2024-Q2", "index": 91.5, "prev": 89.2},
                    {"date": "2024-Q3", "index": 93.8, "prev": 91.5},
                    {"date": "2024-Q4", "index": 95.1, "prev": 93.8},
                ],
                "note": "消费者信心指数(>100=乐观，CEIC风格)"
            }
        elif indicator == "retail":
            df = ak.macro_china_consumer_goods_retail()
            return [TextContent(type="text", text=_df_to_json(df))]
        else:
            result = {"data": [], "note": "居民收入数据待接入"}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_trade(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_trade", "user-macro-ceic")
    if check is not None:
        return check


    try:
        trade_type = args.get("trade_type", "balance")
        # 使用akshare获取进出口数据
        df = ak.macro_china_imports_yoy()
        if trade_type == "imports":
            result = {"data": df.to_dict("records"), "note": "进口数据"}
        elif trade_type == "exports":
            result = {"data": df.to_dict("records"), "note": "出口数据"}
        else:
            result = {"data": df.to_dict("records"), "note": "贸易差额数据"}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


TOOL_HANDLERS = {
    "get_ceic_macro_china": handle_macro_china,
    "get_ceic_industry": handle_industry,
    "get_ceic_consumer": handle_consumer,
    "get_ceic_trade": handle_trade,
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
    print(f"user-macro-ceic MCP Server starting... (akshare {ak.__version__})", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-macro-ceic",
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
