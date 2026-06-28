#!/usr/bin/env python3
"""
user-wb-data MCP Server
=======================
World Bank Data API 服务。

数据源：
  - World Bank API: 全球GDP、人口、贸易、债务、健康、教育等指标
  - 无需API Key，免费使用

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

server = Server("user-wb-data")

_WB_BASE = "https://api.worldbank.org/v2"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def _get(url: str, params: dict = None, timeout: int = 15) -> requests.Response:
    return _SESSION.get(url, params=params, timeout=timeout)


def _wb_indicator(country: str, indicator: str, per_page: int = 50) -> list[dict]:
    url = f"{_WB_BASE}/country/{country}/indicator/{indicator}"
    params = {"format": "json", "per_page": per_page}
    try:
        r = _get(url, params)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            return []
        return data[1] or []
    except Exception:
        return []


def _wb_to_records(wb_data: list[dict]) -> list[dict]:
    records = []
    for item in wb_data:
        records.append({
            "year": item.get("date", ""),
            "value": item.get("value"),
            "indicator_id": item.get("indicator", {}).get("id", ""),
            "indicator_value": item.get("indicator", {}).get("value", ""),
            "country": item.get("country", {}).get("value", ""),
        })
    return records


# ── 指标映射 ───────────────────────────────────────────────────────────────

_WB_INDICATORS = {
    "gdp_usd": "NY.GDP.MKTP.CD",
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",
    "gdp_per_capita": "NY.GDP.PCAP.CD",
    "population": "SP.POP.TOTL",
    "population_growth": "SP.POP.GROW",
    "trade_gdp": "BN.CAB.XOKA.GD.ZS",
    "exports": "NE.EXP.GNFS.ZS",
    "imports": "NE.IMP.GNFS.ZS",
    "debt_gdp": "GC.DOD.TOTL.GD.ZS",
    "inflation": "FP.CPI.TOTL.ZG",
    "unemployment": "SL.UEM.TOTL.ZS",
    "life_expectancy": "SP.DYN.LE00.IN",
    "fertility_rate": "SP.DYN.TFRT.IN",
    "school_enrollment": "SE.TER.ENRR",
    "literacy_rate": "SE.ADT.LITR.ZS",
    "co2_emissions": "EN.ATM.CO2E.PC",
}

_WB_COUNTRIES = {
    "usa": "USA", "us": "USA", "america": "USA",
    "chn": "CHN", "china": "CHN",
    "deu": "DEU", "germany": "DEU",
    "jpn": "JPN", "japan": "JPN",
    "gbr": "GBR", "uk": "GBR", "united kingdom": "GBR",
    "fra": "FRA", "france": "FRA",
    "ind": "IND", "india": "IND",
    "bra": "BRA", "brazil": "BRA",
    "can": "CAN", "canada": "CAN",
    "aus": "AUS", "australia": "AUS",
    "all": "all",
}


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_wb_gdp",
        description="获取World Bank GDP数据。\n\n"
                    "支持美元计价GDP、GDP增速、人均GDP。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码: USA/CHN/DEU/JPN/GBR等或'all'"},
                "indicator": {"type": "string", "description": "指标: gdp_usd/gdp_growth/gdp_per_capita", "default": "gdp_usd"},
                "per_page": {"type": "integer", "description": "返回记录数", "default": 50}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_wb_population",
        description="获取World Bank人口数据。\n\n"
                    "支持总人口、人口增速。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码或'all'"},
                "indicator": {"type": "string", "description": "指标: population/population_growth", "default": "population"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_wb_trade",
        description="获取World Bank贸易数据。\n\n"
                    "支持贸易占GDP比重、出口、进口。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码或'all'"},
                "indicator": {"type": "string", "description": "指标: trade_gdp/exports/imports", "default": "trade_gdp"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_wb_debt",
        description="获取World Bank债务数据。\n\n"
                    "支持政府债务占GDP比重。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码或'all'"},
                "indicator": {"type": "string", "description": "指标: debt_gdp", "default": "debt_gdp"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_wb_health",
        description="获取World Bank健康数据。\n\n"
                    "支持预期寿命、生育率、CO2排放。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码或'all'"},
                "indicator": {"type": "string", "description": "指标: life_expectancy/fertility_rate/co2_emissions", "default": "life_expectancy"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_wb_education",
        description="获取World Bank教育数据。\n\n"
                    "支持入学率、识字率。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码或'all'"},
                "indicator": {"type": "string", "description": "指标: school_enrollment/literacy_rate", "default": "school_enrollment"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_wb_gender",
        description="获取World Bank性别相关数据。\n\n"
                    "支持女性议员比例、童婚率等。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码或'all'"},
                "indicator": {"type": "string", "description": "指标名称"}
            },
            "required": ["country_code"]
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def _fetch_wb(country_code: str, indicator: str, per_page: int) -> list[TextContent]:
    # 支持直接传入 WB 代码（如 SG.GEN.PARL.ZS）或短别名（如 gdp_growth）
    wb_code = _WB_INDICATORS.get(indicator, indicator)
    if not wb_code:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown indicator: {indicator}"}))]
    wb_country = _WB_COUNTRIES.get(country_code.lower(), country_code)
    data = _wb_indicator(wb_country, wb_code, per_page)
    records = _wb_to_records(data)
    return [TextContent(type="text", text=json.dumps({"data": records, "count": len(records)}, ensure_ascii=False))]


TOOL_HANDLERS = {
    "get_wb_gdp": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "gdp_usd"), a.get("per_page", 50)),
    "get_wb_population": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "population"), 50),
    "get_wb_trade": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "trade_gdp"), 50),
    "get_wb_debt": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "debt_gdp"), 50),
    "get_wb_health": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "life_expectancy"), 50),
    "get_wb_education": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "school_enrollment"), 50),
    "get_wb_gender": lambda a: _fetch_wb(a.get("country_code", "USA"), a.get("indicator", "SG.GEN.PARL.ZS"), 50),
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
    print("user-wb-data MCP Server starting... (World Bank API, no key required)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-wb-data",
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
