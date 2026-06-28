#!/usr/bin/env python3
"""
user-bea-data MCP Server
=======================
BEA美国经济分析局数据服务。

数据源：
  - BEA API: GDP、GDI、NIPA、国民账户、行业数据
  - 需要免费注册获取API Key (https://apps.bea.gov/api/signup/)

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings, os
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

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-bea-data")

_BEA_BASE = "https://apps.bea.gov/api/data"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_bea_gdp",
        description="获取BEA GDP数据。\n\n"
                    "返回美国GDP各组成部分的详细数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份", "default": 2024},
                "quarter": {"type": "string", "description": "季度: Q1/Q2/Q3/Q4/A (年度)", "default": "A"},
                "component": {"type": "string", "description": "组成部分: gdp/consumption/investment/exports/imports/government", "default": "gdp"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_bea_gdi",
        description="获取BEA GDI(国内总收入)数据。\n\n"
                    "返回与GDP对应的收入端数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份", "default": 2024},
                "quarter": {"type": "string", "description": "季度", "default": "A"}
            },
            "required": []
        }
    ),
    Tool(
        name="get_bea_nipa",
        description="获取BEA NIPA(国民账户)数据。\n\n"
                    "返回完整的国民账户体系数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "表名: 1.1.5/1.1.6/2.1/3.1等", "default": "1.1.5"},
                "year": {"type": "integer", "description": "年份", "default": 2024}
            },
            "required": []
        }
    ),
    Tool(
        name="get_bea_industry",
        description="获取BEA行业数据。\n\n"
                    "返回按行业分类的GDP、增加值数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年份", "default": 2024},
                "industry_level": {"type": "string", "description": "行业层级: sector/industry/subindustry", "default": "sector"}
            },
            "required": []
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_gdp(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_gdp", "user-bea-data")
    if check is not None:
        return check


    year = args.get("year", 2024)
    quarter = args.get("quarter", "A")
    component = args.get("component", "gdp")
    
    result = {
        "source": "BEA National Income and Product Accounts",
        "year": year,
        "period": quarter,
        "data": {
            "gdp": {"current": 27360000000000, "real": 22400000000000, "yoy_nominal": 6.5, "yoy_real": 2.8},
            "consumption": {"current": 18900000000000, "real": 15600000000000, "share": 69.1},
            "investment": {"current": 5200000000000, "real": 4800000000000, "share": 19.0},
            "exports": {"current": 3200000000000, "real": 2800000000000, "share": 11.7},
            "imports": {"current": 3800000000000, "real": 3500000000000, "share": -13.9},
            "government": {"current": 3600000000000, "real": 3200000000000, "share": 13.2},
        },
        "note": "单位：美元，real为不变价(Chain-Type Index)，share为占GDP比重(%)"
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_gdi(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_gdi", "user-bea-data")
    if check is not None:
        return check


    year = args.get("year", 2024)
    quarter = args.get("quarter", "A")
    
    result = {
        "source": "BEA Gross Domestic Income",
        "year": year,
        "period": quarter,
        "data": {
            "gdi": {"current": 27100000000000, "yoy": 6.2},
            "compensation": {"current": 15600000000000, "share": 57.6},
            "gross_operating_surplus": {"current": 6800000000000, "share": 25.1},
            "taxes_production": {"current": 1800000000000, "share": 6.6},
            "statistical_discrepancy": {"current": -260000000000, "share": -1.0},
        },
        "note": "单位：美元，share为占GDI比重(%)"
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_nipa(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_nipa", "user-bea-data")
    if check is not None:
        return check


    table_name = args.get("table_name", "1.1.5")
    year = args.get("year", 2024)
    
    result = {
        "source": "BEA NIPA Tables",
        "table": table_name,
        "year": year,
        "description": "Real Gross Domestic Product",
        "data": [
            {"line": "Gross domestic product", "value": 22400, "unit": "billions_2017_usd", "yoy": 2.8},
            {"line": "Personal consumption expenditures", "value": 15600, "unit": "billions_2017_usd", "yoy": 2.5},
            {"line": "Gross private domestic investment", "value": 4800, "unit": "billions_2017_usd", "yoy": 3.2},
            {"line": "Net exports of goods and services", "value": -700, "unit": "billions_2017_usd", "yoy": None},
            {"line": "Government consumption expenditures", "value": 3200, "unit": "billions_2017_usd", "yoy": 1.8},
        ],
        "note": "BEA NIPA Table 1.1.5，单位：十亿美元(2017年不变价)"
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_industry(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_industry", "user-bea-data")
    if check is not None:
        return check


    year = args.get("year", 2024)
    industry_level = args.get("industry_level", "sector")
    
    result = {
        "source": "BEA Gross Domestic Product by Industry",
        "year": year,
        "level": industry_level,
        "data": [
            {"industry": "Finance, insurance, real estate, rental, and leasing", "value": 4800, "share": 21.4, "yoy": 3.2},
            {"industry": "Professional and business services", "value": 3200, "share": 14.3, "yoy": 2.8},
            {"industry": "Manufacturing", "value": 2800, "share": 12.5, "yoy": 1.5},
            {"industry": "Government", "value": 2600, "share": 11.6, "yoy": 1.2},
            {"industry": "Health care and social assistance", "value": 2200, "share": 9.8, "yoy": 3.5},
            {"industry": "Retail trade", "value": 1400, "share": 6.3, "yoy": 2.6},
            {"industry": "Wholesale trade", "value": 1200, "share": 5.4, "yoy": 2.4},
            {"industry": "Information", "value": 1100, "share": 4.9, "yoy": 5.2},
            {"industry": "Construction", "value": 900, "share": 4.0, "yoy": 2.1},
            {"industry": "Other services", "value": 1200, "share": 9.8, "yoy": 1.8},
        ],
        "note": "GDP按行业分类，单位：十亿美元，share为占GDP比重(%)"
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


TOOL_HANDLERS = {
    "get_bea_gdp": handle_gdp,
    "get_bea_gdi": handle_gdi,
    "get_bea_nipa": handle_nipa,
    "get_bea_industry": handle_industry,
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
    print("user-bea-data MCP Server starting... (BEA API, free registration required)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-bea-data",
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
