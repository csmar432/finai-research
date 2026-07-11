"""CryptoCompare MCP Server — 加密货币数据.

数据来源：CryptoCompare API (https://min-api.cryptocompare.com)
免费tier：10次/秒，日均10000次。
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
except ImportError:
    import warnings
    warnings.warn("mcp library not installed. Install with: pip install mcp")
    raise

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cryptocompare-mcp")

try:
    from mcp_servers._shared._version import APP_NAME as _APP_NAME, APP_VERSION
except Exception:
    _APP_NAME = "cryptocompare-mcp"
    APP_VERSION = "0.0.0+unknown"
APP_NAME = _APP_NAME
BASE_URL = "https://min-api.cryptocompare.com/data"
server = Server(APP_NAME)


def _safe_json_response(data: Any, error: str | None = None) -> list[TextContent]:
    import json
    if error:
        return [TextContent(type="text", text=json.dumps({"status": "error", "message": error}, ensure_ascii=False, indent=2))]
    try:
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]
    except Exception:
        return [TextContent(type="text", text=json.dumps({"status": "error", "data": str(data)}, ensure_ascii=False, indent=2))]


# ── Tool Handlers ──────────────────────────────────────────────────────────────


async def handle_get_price(args: dict) -> list[TextContent]:
    symbol = args.get("symbol", "").strip().upper()
    if not symbol:
        return _safe_json_response(None, "symbol is required")

    try:
        url = f"{BASE_URL}/price"
        params = {"fsym": symbol, "tsyms": "USD,CNY,EUR,BTC,ETH"}
        resp = _SESSION.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return _safe_json_response({"symbol": symbol, "prices": data})
    except Exception as e:
        logger.warning(f"[CryptoCompare] get_price error for {symbol}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_historical(args: dict) -> list[TextContent]:
    symbol = args.get("symbol", "").strip().upper()
    start = args.get("start_date", "")
    end = args.get("end_date", "")
    interval = args.get("interval", "day")

    if not symbol or not start or not end:
        return _safe_json_response(None, "symbol, start_date, end_date are required")

    try:
        from datetime import datetime

        tsym = "USD"
        limit = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days

        if interval == "hour":
            url = f"{BASE_URL}/v2/histohour"
            params = {"fsym": symbol, "tsym": tsym, "limit": min(limit * 24, 2000)}
        else:
            url = f"{BASE_URL}/v2/histoday"
            params = {"fsym": symbol, "tsym": tsym, "limit": min(limit, 2000)}

        resp = _SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("Response") == "Success":
            items = data.get("Data", {}).get("Data", [])[:100]
            return _safe_json_response({
                "symbol": symbol, "unit": tsym, "data_points": len(items),
                "recent_5": items[-5:] if items else []
            })
        return _safe_json_response(None, data.get("Message", "Unknown error"))
    except Exception as e:
        logger.warning(f"[CryptoCompare] get_historical error for {symbol}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_top_coins(args: dict) -> list[TextContent]:
    limit = min(int(args.get("limit", 20)), 100)
    try:
        url = f"{BASE_URL}/top/totalvolfull"
        params = {"limit": limit, "tsym": "USD"}
        resp = _SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("Data", [])
        if items:
            results = [
                {"rank": i+1, "symbol": c.get("CoinInfo", {}).get("Name"),
                 "name": c.get("CoinInfo", {}).get("FullName"),
                 "price": c.get("RAW", {}).get("USD", {}).get("PRICE"),
                 "change_24h": c.get("RAW", {}).get("USD", {}).get("CHANGEPCT24HOUR"),
                 "volume": c.get("RAW", {}).get("USD", {}).get("TOTALVOLUME24H")}
                for i, c in enumerate(items)
            ]
            return _safe_json_response({"top_coins": results})
        return _safe_json_response(None, data.get("Message") or "No data returned")
    except Exception as e:
        logger.warning(f"[CryptoCompare] get_top_coins error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_news(args: dict) -> list[TextContent]:
    categories = args.get("categories", "")
    try:
        url = f"{BASE_URL}/news/"
        params = {"categories": categories} if categories else {}
        resp = _SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("Type") == 100:
            articles = [
                {"title": a.get("title"), "body": a.get("body", "")[:300],
                 "source": a.get("source"), "published": a.get("published_on"),
                 "url": a.get("url")}
                for a in data.get("Data", [])[:20]
            ]
            return _safe_json_response({"articles": articles})
        return _safe_json_response(None, "News fetch failed")
    except Exception as e:
        logger.warning(f"[CryptoCompare] get_news error: {e}")
        return _safe_json_response(None, str(e))


# ── Server Setup ───────────────────────────────────────────────────────────────


TOOLS = [
    Tool(name="get_cc_price", description="获取加密货币实时价格",
         inputSchema={"type": "object", "properties": {"symbol": {"type": "string", "description": "币种符号，例如 'BTC'"}}, "required": ["symbol"]}),
    Tool(name="get_cc_historical", description="获取加密货币历史价格",
         inputSchema={"type": "object", "properties": {
             "symbol": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "interval": {"type": "string", "default": "day"}
         }, "required": ["symbol", "start_date", "end_date"]}),
    Tool(name="get_cc_top_coins", description="获取市值排名前N的加密货币",
         inputSchema={"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}),
    Tool(name="get_cc_news", description="获取加密货币新闻",
         inputSchema={"type": "object", "properties": {"categories": {"type": "string", "default": ""}}}),
]

TOOL_HANDLERS = {
    "get_cc_price": handle_get_price,
    "get_cc_historical": handle_get_historical,
    "get_cc_top_coins": handle_get_top_coins,
    "get_cc_news": handle_get_news,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
