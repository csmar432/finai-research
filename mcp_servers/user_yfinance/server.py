#!/usr/bin/env python3
"""
yfinance MCP Server
===================
Yahoo Finance 美股/港股数据服务。

数据源：Yahoo Finance API（无需 API Key，完全免费）

Usage:
    python server.py
"""

from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("yfinance_mcp")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import yfinance as yf
    _YFINANCE_AVAILABLE = True
except ImportError:
    log.warning(
        "yfinance not installed. Server will run in MOCK mode (returns stub data). "
        "Install with: pip install yfinance"
    )
    _YFINANCE_AVAILABLE = False
    yf = None  # noqa: F841 — 标记 mock 模式

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    _MCP_AVAILABLE = True
except ImportError:
    log.warning(
        "mcp package not installed. Server cannot start. "
        "Install with: pip install mcp"
    )
    _MCP_AVAILABLE = False
    Server = None
    stdio_server = None
    Tool = None
    TextContent = None


if _MCP_AVAILABLE:
    server = Server("user-yfinance")
else:
    server = None  # MCP 不可用时禁用 server

TOOLS = [
    Tool(
        name="get_yf_quote",
        description="获取美股/港股实时报价。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "股票代码（如 AAPL, TSLA, 0700.HK）"}},
            "required": ["ticker"],
        },
    ),
    Tool(
        name="get_yf_historical",
        description="获取股票历史行情数据（日/周/月频）。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "股票代码"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "interval": {"type": "string", "description": "数据频率", "enum": ["1d", "1wk", "1mo"], "default": "1mo"},
            },
            "required": ["ticker", "start_date", "end_date"],
        },
    ),
    Tool(
        name="get_yf_financials",
        description="获取公司财务报表（利润表、资产负债表、现金流量表）。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "股票代码"},
                "statement_type": {"type": "string", "description": "报表类型", "enum": ["income", "balance", "cashflow", "ratios"], "default": "income"},
            },
            "required": ["ticker"],
        },
    ),
    Tool(
        name="get_yf_options",
        description="获取股票期权数据。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "股票代码"},
                "date": {"type": "string", "description": "期权到期日 YYYY-MM-DD（可选）"},
            },
            "required": ["ticker"],
        },
    ),
    Tool(
        name="get_yf_etf_holdings",
        description="获取ETF持仓明细。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "ETF代码（如 SPY, QQQ）"}},
            "required": ["ticker"],
        },
    ),
    Tool(
        name="get_yf_news",
        description="获取股票最新新闻。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "股票代码"},
            },
            "required": ["ticker"],
        },
    ),
    Tool(
        name="get_yf_earnings",
        description="获取股票盈利日期和分析师预期。使用 Yahoo Finance API，无需 API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "股票代码"},
            },
            "required": ["ticker"],
        },
    ),
]


@server.list_tools() if _MCP_AVAILABLE else (lambda f: f)
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool() if _MCP_AVAILABLE else (lambda f: f)
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # 当 yfinance 不可用时，返回 mock 数据而非崩溃
    if not _YFINANCE_AVAILABLE:
        return [TextContent(
            type="text",
            text=json.dumps(
                {"warning": "yfinance not installed; returning mock data",
                 "tool": name, "arguments": arguments,
                 "mock_value": None},
                ensure_ascii=False, indent=2,
            ),
        )]

    ticker = arguments.get("ticker", "")
    ticker = ticker.strip().upper()

    try:
        ticker_obj = yf.Ticker(ticker)

        if name == "get_yf_quote":
            info = ticker_obj.info
            # 提取关键字段
            keys = ["symbol", "shortName", "longName", "currentPrice", "previousClose",
                    "regularMarketPrice", "regularMarketChange", "fiftyTwoWeekHigh",
                    "fiftyTwoWeekLow", "volume", "marketCap", "trailingPE",
                    "forwardPE", "dividendYield", "profitMargins", "revenueGrowth"]
            result = {k: info.get(k) for k in keys if info.get(k) is not None}
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "get_yf_historical":
            start = arguments.get("start_date", "2020-01-01")
            end = arguments.get("end_date", "2024-12-31")
            interval = arguments.get("interval", "1mo")
            df = ticker_obj.history(start=start, end=end, interval=interval)
            if df.empty:
                return [TextContent(type="text", text=f"No data for {ticker} from {start} to {end}")]
            df = df.reset_index()
            df.columns = [str(c).replace(" ", "_") for c in df.columns]
            return [TextContent(type="text", text=df.to_csv(index=False))]

        elif name == "get_yf_financials":
            stype = arguments.get("statement_type", "income")
            if stype == "income":
                df = ticker_obj.income_stmt
            elif stype == "balance":
                df = ticker_obj.balance_sheet
            elif stype == "cashflow":
                df = ticker_obj.cashflow
            else:
                df = ticker_obj.financials
            if df is None or df.empty:
                return [TextContent(type="text", text=f"No {stype} data for {ticker}")]
            return [TextContent(type="text", text=df.to_csv())]

        elif name == "get_yf_options":
            date = arguments.get("date", None)
            if date:
                opts = ticker_obj.option_chain(date)
            else:
                dates = ticker_obj.options
                if not dates:
                    return [TextContent(type="text", text=f"No options data for {ticker}")]
                opts = ticker_obj.option_chain(dates[0])
            calls = opts.calls.to_csv(index=False)
            puts = opts.puts.to_csv(index=False)
            return [TextContent(type="text", text=f"CALLS:\n{calls}\n\nPUTS:\n{puts}")]

        elif name == "get_yf_etf_holdings":
            try:
                holdings = ticker_obj.info.get("holdings", [])
                if not holdings:
                    df = getattr(ticker_obj, "fund_holdings", None)
                    if df is not None and not df.empty:
                        return [TextContent(type="text", text=df.to_csv(index=False))]
                    return [TextContent(type="text", text=f"No holdings data for {ticker}")]
                return [TextContent(type="text", text=json.dumps(holdings, ensure_ascii=False, indent=2))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error fetching holdings: {e}")]

        elif name == "get_yf_news":
            try:
                news = ticker_obj.news
                if not news:
                    return [TextContent(type="text", text=f"No news for {ticker}")]
                items = [
                    {"title": n.get("title", ""), "link": n.get("link", ""),
                     "publisher": n.get("publisher", ""), "published": n.get("published", ""),
                     "summary": n.get("summary", "")[:300]}
                    for n in news[:20]
                ]
                return [TextContent(type="text", text=json.dumps(items, ensure_ascii=False, indent=2))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error fetching news: {e}")]

        elif name == "get_yf_earnings":
            try:
                earnings = ticker_obj.earnings_dates
                if earnings is None or earnings.empty:
                    return [TextContent(type="text", text=f"No earnings dates for {ticker}")]
                earnings = earnings.reset_index()
                earnings.columns = [str(c).replace(" ", "_") for c in earnings.columns]
                return [TextContent(type="text", text=earnings.to_csv(index=False))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error fetching earnings: {e}")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        log.error(f"Error in {name} for {ticker}: {e}")
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    if not _MCP_AVAILABLE:
        log.error("Cannot start: mcp package not installed. Run: pip install mcp")
        return
    if not _YFINANCE_AVAILABLE:
        log.warning("Starting in MOCK mode (yfinance not installed; all calls return mock data)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
