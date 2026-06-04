"""Yahoo Finance MCP Server — 美股/港股数据.

数据来源：yfinance Python库（Yahoo Finance免费接口，无需API Key）。
支持：行情、历史价格、财务报表、期权、ETF、新闻。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
except ImportError:
    import warnings
    warnings.warn("mcp library not installed. Install with: pip install mcp")
    raise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yfinance-mcp")

APP_NAME = "yfinance-mcp"
APP_VERSION = "1.0.0"
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


async def handle_get_quote(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info

        result = {
            "symbol": ticker,
            "name": info.get("shortName", ""),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "change": info.get("regularMarketChange"),
            "change_pct": info.get("regularMarketChangePercent"),
            "volume": info.get("averageVolume"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "analyst_target": info.get("targetMeanPrice"),
            "recommendation": info.get("recommendationKey", ""),
        }
        return _safe_json_response(result)
    except Exception as e:
        logger.warning(f"[yfinance] get_quote error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_historical(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    start = args.get("start_date", "")
    end = args.get("end_date", "")
    interval = args.get("interval", "1d")
    if not ticker or not start or not end:
        return _safe_json_response(None, "ticker, start_date, end_date are required")

    try:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, interval=interval, progress=False)
        if df.empty:
            return _safe_json_response(None, f"No data for {ticker} in {start} to {end}")

        result = {
            "symbol": ticker,
            "start": start,
            "end": end,
            "interval": interval,
            "data_points": len(df),
            "recent_5": df.tail(5).to_dict(orient="records"),
        }
        return _safe_json_response(result)
    except Exception as e:
        logger.warning(f"[yfinance] get_historical error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_financials(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        financials = ticker_obj.financials
        balance = ticker_obj.balance_sheet
        cashflow = ticker_obj.cashflow

        return _safe_json_response({
            "symbol": ticker,
            "income_statement": financials.to_dict() if not financials.empty else {},
            "balance_sheet": balance.to_dict() if not balance.empty else {},
            "cashflow": cashflow.to_dict() if not cashflow.empty else {},
        })
    except Exception as e:
        logger.warning(f"[yfinance] get_financials error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_options(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        opts = ticker_obj.option_chain()
        if opts and opts[0] is not None and not opts[0].empty:
            calls = opts[0].head(10).to_dict(orient="records")
            puts = opts[1].head(10).to_dict(orient="records") if len(opts) > 1 else []
            return _safe_json_response({"symbol": ticker, "calls": calls, "puts": puts})
        return _safe_json_response({"symbol": ticker, "options": "No options data available"})
    except Exception as e:
        logger.warning(f"[yfinance] get_options error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_earnings(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        earnings = ticker_obj.earnings
        earnings_dates = ticker_obj.earnings_dates
        return _safe_json_response({
            "symbol": ticker,
            "earnings_history": earnings.to_dict() if not earnings.empty else {},
            "upcoming_earnings": earnings_dates.head(5).to_dict(orient="records") if not earnings_dates.empty else {},
        })
    except Exception as e:
        logger.warning(f"[yfinance] get_earnings error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_news(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        news = ticker_obj.news
        items = [
            {"title": n.get("title"), "publisher": n.get("publisher"), "link": n.get("link"), "pubDate": n.get("pubDate")}
            for n in (news or [])[:10]
        ]
        return _safe_json_response({"symbol": ticker, "news": items})
    except Exception as e:
        logger.warning(f"[yfinance] get_news error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_etf_holdings(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        holdings = ticker_obj.info.get("holdings", [])
        if not holdings:
            # Try to get from info dict
            top_holdings = ticker_obj.info.get("topHoldings", [])
            if top_holdings:
                return _safe_json_response({"symbol": ticker, "top_holdings": top_holdings[:20]})
            return _safe_json_response({"symbol": ticker, "holdings": "Not available for this ETF"})
        return _safe_json_response({"symbol": ticker, "holdings": holdings[:20]})
    except Exception as e:
        logger.warning(f"[yfinance] get_etf_holdings error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


# ── Server Setup ───────────────────────────────────────────────────────────────


TOOLS = [
    Tool(name="get_yf_quote", description="获取股票实时行情",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string", "description": "股票代码，例如 'AAPL'"}}, "required": ["ticker"]}),
    Tool(name="get_yf_historical", description="获取股票历史价格",
         inputSchema={"type": "object", "properties": {
             "ticker": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "interval": {"type": "string", "default": "1d"}
         }, "required": ["ticker", "start_date", "end_date"]}),
    Tool(name="get_yf_financials", description="获取财务报表",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
    Tool(name="get_yf_options", description="获取期权链",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
    Tool(name="get_yf_earnings", description="获取盈利数据",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
    Tool(name="get_yf_news", description="获取股票新闻",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
    Tool(name="get_yf_etf_holdings", description="获取ETF持仓",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
]

TOOL_HANDLERS = {
    "get_yf_quote": handle_get_quote,
    "get_yf_historical": handle_get_historical,
    "get_yf_financials": handle_get_financials,
    "get_yf_options": handle_get_options,
    "get_yf_earnings": handle_get_earnings,
    "get_yf_news": handle_get_news,
    "get_yf_etf_holdings": handle_get_etf_holdings,
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
