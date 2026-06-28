#!/usr/bin/env python3
"""
user-enhanced-finance MCP Server
================================
增强金融数据 — 外汇/大宗商品/加密货币/航运指数/期货。
使用 akshare 实现，无需 API Key。
"""

from __future__ import annotations

import json, os, sys, warnings
from pathlib import Path
import pandas as pd  # noqa: E402
warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
except ImportError:
    pass

try:
    import akshare as ak
except ImportError:
    print("ERROR: akshare required. pip install akshare", flush=True)
    sys.exit(1)

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-enhanced-finance")

TOOLS = [
    Tool(
        name="get_forex_spot",
        description="获取外汇即期汇率（主要货币对）。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="get_forex_hist",
        description="获取外汇历史走势数据（仅支持指定货币对）。使用 akshare 东方财富接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "currency_pair": {
                    "type": "string",
                    "description": "货币对，如 USD/CNY, EUR/USD（需大写）",
                    "default": "USDCNY"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期 YYYYMMDD（可选，默认返回全部历史）"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期 YYYYMMDD（可选）"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="get_commodity_price",
        description="获取大宗商品价格（黄金/白银/原油）。使用 akshare 接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "commodity": {
                    "type": "string",
                    "description": "商品类型",
                    "enum": ["gold", "silver", "brent_oil", "wti_oil"]
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期 YYYYMMDD（可选）"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期 YYYYMMDD（可选）"
                }
            },
            "required": ["commodity"]
        }
    ),
    Tool(
        name="get_shipping_index",
        description="获取航运指数（BDI/BCI/BPI/BDTI/BCTI）。使用 akshare 接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "index_name": {
                    "type": "string",
                    "description": "指数名称",
                    "enum": ["bdi", "bci", "bpi", "bdti", "bcti"]
                }
            },
            "required": ["index_name"]
        }
    ),
    Tool(
        name="get_crypto_price",
        description="获取加密货币实时行情数据。使用 akshare + CoinGecko 接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "coin": {
                    "type": "string",
                    "description": "加密货币代码，如 BTC, ETH（需大写）"
                }
            },
            "required": ["coin"]
        }
    ),
    Tool(
        name="get_futures_price",
        description="获取期货价格数据。使用 akshare 接口，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "期货合约代码，如 RB0（螺纹钢默认）, IF, IC 等"
                }
            },
            "required": []
        }
    ),
]


def _safe_json_response(data: Any, tool_name: str = "") -> str:
    """Standardized response format for all MCP tools.
    - Success: {"result": <data>, "success": True}
    - Error:   {"error": <message>, "success": False}
    """
    if isinstance(data, dict) and "error" in data:
        return json.dumps({"error": data["error"], "success": False, "tool": tool_name}, ensure_ascii=False)
    if isinstance(data, dict) and "result" in data:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps({"result": data, "success": True, "tool": tool_name}, ensure_ascii=False)


def _df_to_json(df) -> str:
    """Convert DataFrame to JSON string with standardized success wrapper."""
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"result": {"data": [], "count": 0}, "success": True}, ensure_ascii=False)
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
    except Exception as e:
        return _safe_json_response({"error": str(e)}, "unknown")
    return _safe_json_response(result, "unknown")


def _filter_by_date(df, start_date: str | None, end_date: str | None) -> any:
    """Filter DataFrame by date range (checks '日期' or 'date' column)."""
    if df is None or df.empty:
        return df
    if not start_date and not end_date:
        return df

    date_col = None
    for col in ["日期", "date", "Date"]:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        return df

    if not hasattr(df[date_col], "strftime") and not hasattr(df[date_col], "dt"):
        return df

    try:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])
        if start_date:
            df = df[df[date_col] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df[date_col] <= pd.to_datetime(end_date)]
    except Exception:
        pass
    return df


async def handle_forex_spot(args: dict) -> list[TextContent]:
    try:
        df = ak.forex_spot_em()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_forex_spot"))]


async def handle_forex_hist(args: dict) -> list[TextContent]:
    pair = args.get("currency_pair", "USDCNY")
    if not pair:
        return [TextContent(type="text", text=_safe_json_response({"error": "currency_pair is required"}, "get_forex_hist"))]
    try:
        df = ak.forex_hist_em(symbol=pair)
        df = _filter_by_date(df, args.get("start_date"), args.get("end_date"))
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_forex_hist"))]


async def handle_commodity_price(args: dict) -> list[TextContent]:
    commodity = args.get("commodity", "")
    if not commodity:
        return [TextContent(type="text", text=_safe_json_response({"error": "commodity is required"}, "get_commodity_price"))]
    try:
        if commodity == "gold":
            df = ak.spot_golden_benchmark_sge()
        elif commodity == "silver":
            df = ak.spot_silver_benchmark_sge()
        elif commodity in ("brent_oil", "wti_oil"):
            symbol = "Brent" if commodity == "brent_oil" else "WTI"
            df = ak.energy_oil_hist(symbol=symbol)
        else:
            return [TextContent(type="text", text=_safe_json_response({"error": f"Unknown commodity: {commodity}"}, "get_commodity_price"))]
        df = _filter_by_date(df, args.get("start_date"), args.get("end_date"))
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_commodity_price"))]


async def handle_shipping_index(args: dict) -> list[TextContent]:
    index_name = args.get("index_name", "")
    if not index_name:
        return [TextContent(type="text", text=_safe_json_response({"error": "index_name is required"}, "get_shipping_index"))]
    func_map = {
        "bdi":   ("BDI波罗的海干散货指数",  ak.macro_shipping_bdi),
        "bci":   ("BCI波罗的海海岬型指数",  ak.macro_shipping_bci),
        "bpi":   ("BPI巴拿马型指数",        ak.macro_shipping_bpi),
        "bdti":  ("BDTI原油运输指数",        None),
        "bcti":  ("BCTI燃油运输指数",        ak.macro_shipping_bcti),
    }

    if index_name not in func_map:
        return [TextContent(type="text", text=_safe_json_response({"error": f"Unknown index: {index_name}"}, "get_shipping_index"))]

    name, func = func_map[index_name]
    if func is None:
        avail = [k for k, v in func_map.items() if v[1] is not None]
        return [TextContent(type="text", text=_safe_json_response({
            "error": f"Index {index_name} is not available in the current akshare version",
            "available": avail
        }, "get_shipping_index"))]

    try:
        df = func()
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_shipping_index"))]


async def handle_crypto_price(args: dict) -> list[TextContent]:
    coin = args.get("coin", "").upper()
    if not coin:
        return [TextContent(type="text", text=_safe_json_response({"error": "coin is required"}, "get_crypto_price"))]
    try:
        df = ak.crypto_js_spot(symbol=coin)
    except Exception:
        try:
            df = ak.crypto(symbol=f"tether-{coin.lower()}")
        except Exception as e:
            return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_crypto_price"))]
    return [TextContent(type="text", text=_df_to_json(df))]


async def handle_futures_price(args: dict) -> list[TextContent]:
    symbol = args.get("symbol", "RB0")
    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
        return [TextContent(type="text", text=_df_to_json(df))]
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, "get_futures_price"))]


TOOL_HANDLERS = {
    "get_forex_spot":     handle_forex_spot,
    "get_forex_hist":     handle_forex_hist,
    "get_commodity_price": handle_commodity_price,
    "get_shipping_index":  handle_shipping_index,
    "get_crypto_price":    handle_crypto_price,
    "get_futures_price":   handle_futures_price,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=_safe_json_response({"error": f"Unknown tool: {name}"}, name))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=_safe_json_response({"error": str(e)}, name))]


async def main():
    print(f"user-enhanced-finance MCP Server starting... (akshare {ak.__version__})", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-enhanced-finance",
                server_version="1.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
