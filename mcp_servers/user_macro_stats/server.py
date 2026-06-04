#!/usr/bin/env python3
"""user-macro-stats MCP Server — 国家统计局分省年度数据 + World Bank API。

数据源：
  - World Bank API: 全球GDP/CPI/人口/贸易等（无需API Key，https://api.worldbank.org）
  - 国家统计局分省年度数据: https://data.stats.gov.cn/（SSL不稳定，返回备用方案）
  - 替代：马克数据网 https://www.macrodatas.cn/（付费面板数据）

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings, time
from pathlib import Path
from typing import Any
warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("ERROR: requests required.", flush=True)
    sys.exit(1)

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions

server = Server("user-macro-stats")

_WB_BASE = "https://api.worldbank.org/v2"


def _error_json(msg: str) -> str:
    return json.dumps({"error": msg, "success": False}, ensure_ascii=False)


def _ok_json(data: Any) -> str:
    return json.dumps({"result": data, "success": True}, ensure_ascii=False)


def _wb_fetch(url: str, params: dict, retries: int = 2) -> Any:
    """带重试的 World Bank API 请求。"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return None


# ─── World Bank 工具 ──────────────────────────────────────

async def handle_wb_indicator(args: dict) -> list[TextContent]:
    """查询World Bank指标数据（任意国家/指标/时间范围）。"""
    country = args.get("country_code", "CN")
    indicator = args.get("indicator", "NY.GDP.MKTP.CD")
    start = args.get("start_year", 2000)
    end = args.get("end_year", 2024)
    per_page = args.get("per_page", 100)

    url = f"{_WB_BASE}/country/{country}/indicator/{indicator}"
    params = {"format": "json", "per_page": per_page, "date": f"{start}:{end}"}
    data = _wb_fetch(url, params)
    if data is None or len(data) < 2:
        return [TextContent(type="text", text=_error_json("World Bank API请求失败"))]

    records = []
    for item in data[1]:
        if item["value"] is not None:
            records.append({
                "country": item["country"]["value"],
                "country_code": item["countryiso3code"],
                "year": int(item["date"]),
                "indicator": indicator,
                "indicator_name": item["indicator"]["value"],
                "value": item["value"],
                "unit": "美元（当前价）"
            })
    return [TextContent(type="text", text=_ok_json({"data": records, "count": len(records)}))]


async def handle_wb_gdp_usd(args: dict) -> list[TextContent]:
    """查询各国GDP（美元，当前价）。"""
    return await handle_wb_indicator({**args, "indicator": "NY.GDP.MKTP.CD"})


async def handle_wb_gdp_pc(args: dict) -> list[TextContent]:
    """查询各国人均GDP（美元）。"""
    return await handle_wb_indicator({**args, "indicator": "NY.GDP.PCAP.CD"})


async def handle_wb_population(args: dict) -> list[TextContent]:
    """查询各国人口。"""
    return await handle_wb_indicator({**args, "indicator": "SP.POP.TOTL"})


async def handle_wb_trade(args: dict) -> list[TextContent]:
    """查询各国货物贸易（出口/进口/净出口）。"""
    return await handle_wb_indicator({**args, "indicator": "BN.CAB.XOKA.CD"})


async def handle_wb_inflation(args: dict) -> list[TextContent]:
    """查询各国通货膨胀率（CPI同比）。"""
    return await handle_wb_indicator({**args, "indicator": "FP.CPI.TOTL.ZG"})


async def handle_wb_unemployment(args: dict) -> list[TextContent]:
    """查询各国失业率。"""
    return await handle_wb_indicator({**args, "indicator": "SL.UEM.TOTL.ZS"})


async def handle_wb_tech_rd(args: dict) -> list[TextContent]:
    """查询各国R&D支出占GDP比重（注：数据覆盖不完整，返回说明）。"""
    return await handle_wb_indicator({**args, "indicator": "GB.XPD.RSDV.GD.ZS"})


async def handle_nbs_fallback(args: dict) -> list[TextContent]:
    """国家统计局分省数据（注：SSL不稳定，返回备用方案）。"""
    note = {
        "note": "国家统计局分省数据API（data.stats.gov.cn）SSL不稳定",
        "已测试可行的替代": [
            "马克数据网（macrodatas.cn）：各省历年GDP/R&D/高校数据，需付费订阅",
            "湖北省统计局（tjj.hubei.gov.cn）：湖北省年度数据",
            "武汉市统计局（tjj.wuhan.gov.cn）：武汉市年度数据",
            "科技部公报（most.gov.cn）：全国及分省R&D数据"
        ],
        "可用WorldBank替代": "World Bank API提供各国GDP/人口/贸易数据（无需Key）",
        "常用WorldBank指标代码": {
            "NY.GDP.MKTP.CD": "GDP（美元，当前价）",
            "NY.GDP.PCAP.CD": "人均GDP（美元）",
            "SP.POP.TOTL": "总人口",
            "FP.CPI.TOTL.ZG": "通货膨胀率（CPI同比）",
            "SL.UEM.TOTL.ZS": "失业率（%）",
            "GB.XPD.RSDV.GD.ZS": "R&D支出占GDP比重（%）",
            "BN.CAB.XOKA.CD": "经常账户余额（美元）"
        }
    }
    return [TextContent(type="text", text=_ok_json(note))]


# ─── 工具定义 ─────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_wb_indicator",
        description="查询World Bank任意指标数据（无需API Key）。常用指标：NY.GDP.MKTP.CD(GDP)、SP.POP.TOTL(人口)、FP.CPI.TOTL.ZG(通胀)、GB.XPD.RSDV.GD.ZS(R&D强度)",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "default": "CN", "description": "国家代码，如CN/USA/DEU/JPN"},
                "indicator": {"type": "string", "default": "NY.GDP.MKTP.CD", "description": "WB指标代码"},
                "start_year": {"type": "integer", "default": 2000, "description": "起始年份"},
                "end_year": {"type": "integer", "default": 2024, "description": "结束年份"}
            }
        }
    ),
    Tool(name="get_wb_gdp_usd", description="查询各国GDP（美元，当前价）",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_wb_gdp_pc", description="查询各国人均GDP（美元）",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_wb_population", description="查询各国总人口",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_wb_trade", description="查询各国经常账户余额（贸易数据代理）",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_wb_inflation", description="查询各国CPI通胀率（同比）",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_wb_unemployment", description="查询各国失业率",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_wb_tech_rd", description="查询各国R&D支出占GDP比重（数据覆盖不完整）",
         inputSchema={"type": "object", "properties": {
             "country_code": {"type": "string", "default": "CN"},
             "start_year": {"type": "integer", "default": 2000},
             "end_year": {"type": "integer", "default": 2024}
         }}),
    Tool(name="get_nbs_fallback", description="国家统计局分省数据（SSL不稳定，返回备用方案指引）",
         inputSchema={"type": "object", "properties": {}}),
]

TOOL_HANDLERS = {
    "get_wb_indicator": handle_wb_indicator,
    "get_wb_gdp_usd": handle_wb_gdp_usd,
    "get_wb_gdp_pc": handle_wb_gdp_pc,
    "get_wb_population": handle_wb_population,
    "get_wb_trade": handle_wb_trade,
    "get_wb_inflation": handle_wb_inflation,
    "get_wb_unemployment": handle_wb_unemployment,
    "get_wb_tech_rd": handle_wb_tech_rd,
    "get_nbs_fallback": handle_nbs_fallback,
}

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=_error_json(f"Unknown tool: {name}"))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=_error_json(str(e)))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-macro-stats",
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
