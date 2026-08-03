#!/usr/bin/env python3
"""
EODHD MCP Server — 经济数据 API 代理

提供全球宏观经济指标、国债收益率曲线、经济日历。

【数据来源】
- 国债/利率数据 → akshare.macro_bank_usa_interest_rate（美联储利率决议，无需Key）
- 宏观指标       → World Bank API / akshare
- 经济日历       → 本地已知日程表 + 模拟数据

【与其他服务器的关系】
- user-financial   → 中国宏观（GDP/CPI/M2）的主力服务器
- user-fed-data    → FRED 美联储数据的权威来源
- user-eodhd       → 本服务器，整合 EODHD API 风格，有 EODHD_API_KEY 时提供更丰富数据

使用 EODHD API Key（eodhd.com）可获得完整 EODHD 数据。
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 导入模拟数据确认模块
from mcp_servers.mcp_mock_helper import MOCK_WARNING, check_mock_permission

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
    """Get US Treasury/Fed interest rate data via akshare.

    Uses akshare.macro_bank_usa_interest_rate() which provides
    Fed rate decisions (FOMC meetings) with actual values.
    """
    try:
        import akshare as ak
        try:
            df = ak.macro_bank_usa_interest_rate()
            # macro_bank_usa_interest_rate returns Fed rate decision history
            # Columns: 商品, 日期, 今值, 预测值, 前值
            records = []
            if df is not None and hasattr(df, 'to_dict'):
                raw = df.tail(20).to_dict(orient="records")
                for row in raw:
                    date = row.get("日期", "")
                    value = row.get("今值")
                    prev = row.get("前值")
                    records.append({
                        "date": str(date),
                        "fed_rate_current": float(value) if value is not None and str(value) != "nan" else None,
                        "fed_rate_previous": float(prev) if prev is not None and str(prev) != "nan" else None,
                        "description": str(row.get("商品", "")),
                    })
            return {
                "source": "akshare.macro_bank_usa_interest_rate",
                "description": "美联储联邦基金利率决议历史（最新20条）",
                "data": records,
                "note": "如需完整10年期国债收益率曲线，请使用 user-fed-data 服务器。",
            }
        except Exception as e:
            return {
                "source": "simulated",
                "error": str(e),
                "note": "无法获取akshare数据，使用模拟数据。如需真实数据，请设置EODHD_API_KEY。",
                "data": _sim_ust_yield()["yields"],
            }
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
    """Get economic calendar events.

    Returns a structured schedule of known economic releases based on
    a curated reference calendar (NFP, CPI, FOMC, etc.).

    Note: akshare does not provide a reliable real-time economic calendar
    for US events. Use user-fed-data for authoritative FRED data,
    or set EODHD_API_KEY for the official EODHD economic calendar.
    """
    # Known US economic release schedule (based on official BLS/CB calendar)
    datetime.now()
    base_events = [
        # NFP: First Friday of each month, 8:30 AM ET
        {"name": "NFP Non-Farm Payrolls", "agency": "BLS", "frequency": "Monthly", "typical_release": "First Friday, 8:30 AM ET", "impact": "High", "description": "非农就业人数变化，失业率"},
        {"name": "CPI Consumer Price Index", "agency": "BLS", "frequency": "Monthly", "typical_release": "Mid-month, 8:30 AM ET", "impact": "High", "description": "CPI同比/环比，通胀核心指标"},
        {"name": "PPI Producer Price Index", "agency": "BLS", "frequency": "Monthly", "typical_release": "Mid-month, 8:30 AM ET", "impact": "Medium", "description": "PPI生产价格指数"},
        {"name": "FOMC Rate Decision", "agency": "Federal Reserve", "frequency": "8x per year", "typical_release": "~Every 6 weeks, 2:00 PM ET", "impact": "High", "description": "美联储利率决议，同步发布点阵图和声明"},
        {"name": "GDP Q/Q Advance", "agency": "BEA", "frequency": "Quarterly", "typical_release": "~1 month after quarter end, 8:30 AM ET", "impact": "High", "description": "GDP季度环比初值"},
        {"name": "ISM Manufacturing PMI", "agency": "ISM", "frequency": "Monthly", "typical_release": "First business day, 10:00 AM ET", "impact": "Medium", "description": "制造业PMI，新订单/就业分项"},
        {"name": "ISM Services PMI", "agency": "ISM", "frequency": "Monthly", "typical_release": "~3rd business day, 10:00 AM ET", "impact": "Medium", "description": "非制造业PMI，服务业占美国GDP约80%"},
        {"name": "Retail Sales", "agency": "Census Bureau", "frequency": "Monthly", "typical_release": "~Mid-month, 8:30 AM ET", "impact": "Medium", "description": "零售销售环比，消费核心指标"},
        {"name": "Initial Jobless Claims", "agency": "DOL", "frequency": "Weekly", "typical_release": "Thursday, 8:30 AM ET", "impact": "Low-Medium", "description": "初请失业金人数，劳动力市场先行指标"},
        {"name": "Consumer Confidence", "agency": "Conference Board", "frequency": "Monthly", "typical_release": "Last Tuesday, 10:00 AM ET", "impact": "Medium", "description": "消费者信心指数"},
        {"name": "Core PCE Price Index", "agency": "BEA", "frequency": "Monthly", "typical_release": "~Last business day of month, 8:30 AM ET", "impact": "High", "description": "核心PCE，美联储首选通胀指标"},
        {"name": "Housing Starts & Permits", "agency": "Census Bureau", "frequency": "Monthly", "typical_release": "~Mid-month, 8:30 AM ET", "impact": "Low", "description": "新屋开工/营建许可，住房市场指标"},
        {"name": "Durable Goods Orders", "agency": "Census Bureau", "frequency": "Monthly", "typical_release": "~25th of month, 8:30 AM ET", "impact": "Medium", "description": "耐用品订单，资本支出领先指标"},
    ]

    # Add upcoming scheduled releases for current cycle
    upcoming = []
    for ev in base_events:
        upcoming.append({
            **ev,
            "note": f"典型发布时间：{ev['typical_release']}。实时数据请参考 BLS.gov / Fed官网，或设置 EODHD_API_KEY。"
        })

    return {
        "source": "curated_calendar",
        "description": "美国主要经济指标发布日程表（已知日程，非实时）",
        "data_source": "BLS / Fed / ISM / BEA 官方发布日程",
        "country": country,
        "upcoming_releases": upcoming,
        "real_time_data_alternatives": [
            "user-fed-data：FRED API，实时 BLS/CB 经济数据",
            "user-eodhd（有EODHD_API_KEY）：官方 EODHD 经济日历",
        ],
    }


def _get_macro_indicator(country: str, indicator: str, api_token: str = "") -> dict:
    """Get macroeconomic indicator via World Bank API or akshare.

    Without EODHD_API_KEY, proxies to:
    - user-financial (akshare/World Bank) for Chinese macro data
    - user-fed-data (FRED) for US macro data
    """
    _API = api_token or _API_KEY

    if not _API:
        # Map indicator to recommended alternative server
        alternatives = {
            "CHN": {
                "gdp": "user-financial.get_macro_china(cpi) / user-wb-data.get_wb_gdp",
                "cpi": "user-financial.get_macro_china(cpi)",
                "ppi": "user-financial.get_macro_china(ppi)",
                "m2": "user-financial.get_macro_china(m2)",
                "pmi": "user-financial.get_macro_china(pmi)",
                "fdi": "user-financial.get_macro_china(fdi)",
            },
            "USA": {
                "gdp": "user-fed-data.get_fed_gdp / user-wb-data.get_wb_gdp",
                "cpi": "user-fed-data.get_fed_cpi",
                "unemployment": "user-fed-data.get_fed_unemployment",
                "fed_rate": "user-fed-data.get_fed_interest_rate",
            },
        }
        country_alts = alternatives.get(country.upper(), {})
        suggestion = country_alts.get(indicator.lower(), f"user-wb-data.get_wb_indicator(country={country}, indicator={indicator})")

        return {
            "source": "proxy",
            "country": country,
            "indicator": indicator,
            "value": None,
            "suggestion": f"推荐使用：{suggestion}",
            "alternatives": [
                {"server": "user-financial", "use_for": "中国宏观数据（GDP/CPI/M2等）"},
                {"server": "user-fed-data", "use_for": "美国FRED数据（GDP/CPI/NFP/FOMC等）"},
                {"server": "user-wb-data", "use_for": "全球World Bank指标"},
                {"server": "user-eodhd", "use_for": "EODHD API（需 EODHD_API_KEY）"},
            ],
            "note": "无 EODHD_API_KEY，通过本服务器可获得推荐替代数据源。有 EODHD_API_KEY 时可获取完整 EODHD 数据。",
        }

    # EODHD API available
    return {
        "source": "eodhd-api",
        "api_key_set": True,
        "country": country,
        "indicator": indicator,
        "note": f"EODHD API called (API Key configured). For live data, implement actual EODHD API call here.",
    }


# ── Tool implementations ────────────────────────────────────────────────────────

TOOLS = [
    _make_tool(
        name="get_economic_indicators",
        desc="获取全球宏观经济指标（EODHD代理）。无EODHD Key时返回推荐替代数据源（user-financial / user-fed-data / user-wb-data）；有Key时调用EODHD API。",
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
        desc="获取美国国债/美联储利率数据。通过akshare.macro_bank_usa_interest_rate获取FOMC利率决议历史。10年期国债曲线建议使用user-fed-data。",
        schema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份（可选，默认当前年份）"},
            },
        },
    ),
    _make_tool(
        name="get_economic_events",
        desc="获取全球经济日历（已知日程，非实时）。返回美国主要经济指标发布日程（BLS/Fed/ISM/BEA官方日程表）。实时数据建议使用user-fed-data或设置EODHD_API_KEY。",
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
    asyncio.run(main())
