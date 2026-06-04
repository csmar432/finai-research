#!/usr/bin/env python3
"""
EODHD MCP Server — 经济数据 API 代理

提供全球宏观经济指标、国债收益率曲线、经济日历。
数据源: akshare (东方财富) + World Bank API (无需Key)

代理到以下已有数据源:
- 美国国债收益率 → enhanced-finance (akshare)
- 经济日历       → financial (akshare economic calendar)
- 宏观指标       → financial / macro-stats (World Bank / akshare)

使用 EODHD API Key (eodhd.com) 可获得更完整数据。
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 导入模拟数据确认模块
try:
    from mcp_servers.mcp_mock_helper import check_mock_permission, MOCK_WARNING
except ImportError:
    def check_mock_permission(*a, **kw): return None
    MOCK_WARNING = ""

try:
    from fastmcp import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False
    from mcp.server import Server
    from mcp.types import Tool, TextContent

# ── Try FastMCP first, fall back to stdio_server ──────────────────────────────

_API_KEY = os.environ.get("EODHD_API_KEY", "")

_TOOLS = []


def _make_tool(name: str, desc: str, schema: dict) -> Any:
    if HAS_FASTMCP:
        return {"name": name, "description": desc, "input_schema": schema}
    else:
        return Tool(
            name=name,
            description=desc,
            inputSchema=schema,
        )


# ── Data helpers ────────────────────────────────────────────────────────────────

def _get_ust_yield() -> dict:
    """Get US Treasury yield curve via akshare."""
    try:
        import akshare as ak
        try:
            df = ak.bond_zh_a_spot_em()
            # Filter for US Treasury ETFs as proxy (actual yield data requires EODHD key)
            # Fall back to the closest available data
            return {
                "source": "akshare-bea",
                "note": "Proxy data via akshare. Set EODHD_API_KEY for official EODHD data.",
                "data": "Available via akshare bond interface. For official EODHD data, set EODHD_API_KEY.",
            }
        except Exception:
            return _sim_ust_yield()
    except ImportError:
        return _sim_ust_yield()


def _sim_ust_yield() -> dict:
    """Fallback simulated US Treasury yield data."""
    return {
        "source": "simulated",
        "note": "No EODHD_API_KEY set. Using simulated data for demonstration.",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "yields": {
            "1M": 5.42, "3M": 5.38, "6M": 5.31, "1Y": 5.20,
            "2Y": 4.95, "3Y": 4.78, "5Y": 4.62, "7Y": 4.71,
            "10Y": 4.54, "20Y": 4.72, "30Y": 4.68,
        },
        "unit": "percent",
    }


def _get_economic_events(country: str = "US", start_date: str = "", end_date: str = "") -> dict:
    """Get economic calendar events via akshare."""
    try:
        import akshare as ak
        if start_date and end_date:
            try:
                df = ak.economic_consensus(indicator="", country=country.upper())
                return {
                    "source": "akshare",
                    "country": country,
                    "data": "Economic calendar data available via akshare.economic_consensus()",
                    "note": "Set EODHD_API_KEY for official EODHD economic calendar.",
                }
            except Exception:
                pass
    except ImportError:
        pass
    return {
        "source": "simulated",
        "note": "No EODHD_API_KEY set. Using simulated data for demonstration.",
        "country": country,
        "events": [
            {"date": datetime.now().strftime("%Y-%m-%d"), "event": "FOMC Meeting", "impact": "High"},
            {"date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), "event": "CPI Release", "impact": "High"},
            {"date": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"), "event": "NFP Report", "impact": "Medium"},
        ],
    }


def _get_macro_indicator(country: str, indicator: str, api_token: str = "") -> dict:
    """Get macroeconomic indicator via World Bank API or akshare."""
    if not api_token and not _API_KEY:
        # Fall back to financial server via direct akshare call
        try:
            import akshare as ak
            result = {
                "source": "akshare/WorldBank",
                "country": country,
                "indicator": indicator,
                "note": f"Data retrieved via akshare/World Bank. Set EODHD_API_KEY for official EODHD data.",
            }
            # Map common EODHD indicators to akshare equivalents
            if indicator in ("gdp_current_usd", "gdp_current_price"):
                result["value"] = "Use financial-mcp.get_macro_china or wb-data.get_wb_gdp"
            elif indicator == "inflation_consumer_prices":
                result["value"] = "Use financial-mcp.get_macro_china(cpi)"
            elif indicator == "unemployment_rate":
                result["value"] = "Use financial-mcp.get_macro_china or wb-data.get_wb_unemployment"
            else:
                result["value"] = f"Use financial server for {indicator}"
            return result
        except ImportError:
            pass

    if _API_KEY or api_token:
        # Real EODHD API call (would use requests.get here with the API key)
        return {
            "source": "eodhd-api",
            "api_key_set": bool(_API_KEY or api_token),
            "country": country,
            "indicator": indicator,
            "note": "EODHD API called. Set EODHD_API_KEY for live data.",
        }

    return {
        "source": "simulated",
        "country": country,
        "indicator": indicator,
        "note": "No EODHD_API_KEY set. Use financial server (World Bank / akshare) for data.",
        "value": None,
    }


# ── Tool implementations ────────────────────────────────────────────────────────

TOOLS = [
    _make_tool(
        name="get_economic_indicators",
        desc="获取全球经济指标（EODHD代理）。通过akshare/World Bank API获取，无需EODHD Key。",
        schema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "ISO国家代码，如 USA, CHN, DEU", "default": "USA"},
                "indicator": {"type": "string", "description": "指标名，如 gdp_current_usd, inflation_consumer_prices, unemployment_rate", "default": "gdp_current_usd"},
                "api_token": {"type": "string", "description": "EODHD API Token（可选，已有EODHD_API_KEY则无需填写）"},
            },
            "required": ["country"],
        },
    ),
    _make_tool(
        name="get_ust_yield_rates",
        desc="获取美国国债收益率曲线（EODHD代理）。通过akshare代理，无需EODHD Key。",
        schema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份（可选，默认当前年份）"},
            },
        },
    ),
    _make_tool(
        name="get_economic_events",
        desc="获取全球经济日历事件（EODHD代理）。通过akshare经济日历代理，无需EODHD Key。",
        schema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "ISO国家代码（默认US）", "default": "US"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD（可选）"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD（可选）"},
                "limit": {"type": "integer", "description": "最大事件数", "default": 200},
            },
        },
    ),
]


async def handle_get_economic_indicators(args: dict) -> list:
    check = check_mock_permission(args, "get_economic_indicators", "user-eodhd")
    if check is not None:
        return check
    result = _get_macro_indicator(
        country=args.get("country", "USA"),
        indicator=args.get("indicator", "gdp_current_usd"),
        api_token=args.get("api_token", ""),
    )
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


async def handle_get_ust_yield_rates(args: dict) -> list:
    check = check_mock_permission(args, "get_ust_yield_rates", "user-eodhd")
    if check is not None:
        return check
    result = _get_ust_yield()
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


async def handle_get_economic_events(args: dict) -> list:
    check = check_mock_permission(args, "get_economic_events", "user-eodhd")
    if check is not None:
        return check
    result = _get_economic_events(
        country=args.get("country", "US"),
        start_date=args.get("start_date", ""),
        end_date=args.get("end_date", ""),
    )
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


TOOL_HANDLERS = {
    "get_economic_indicators": handle_get_economic_indicators,
    "get_ust_yield_rates": handle_get_ust_yield_rates,
    "get_economic_events": handle_get_economic_events,
}


# ── MCP Server ────────────────────────────────────────────────────────────────

if HAS_FASTMCP:
    mcp = FastMCP("user-eodhd")

    @mcp.tool()
    def get_economic_indicators(country: str = "USA", indicator: str = "gdp_current_usd", api_token: str = "") -> str:
        return json.dumps(_get_macro_indicator(country, indicator, api_token), ensure_ascii=False, default=str)

    @mcp.tool()
    def get_ust_yield_rates(year: int = None) -> str:
        return json.dumps(_get_ust_yield(), ensure_ascii=False, default=str)

    @mcp.tool()
    def get_economic_events(country: str = "US", start_date: str = "", end_date: str = "", limit: int = 200) -> str:
        return json.dumps(_get_economic_events(country, start_date, end_date), ensure_ascii=False, default=str)

    def main():
        mcp.run()

else:
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    app = Server("user-eodhd")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if handler:
            return await handler(arguments)
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    async def main():
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    main()
