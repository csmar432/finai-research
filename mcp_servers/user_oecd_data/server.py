#!/usr/bin/env python3
"""
user-oecd-data MCP Server
=======================
OECD Data API 服务。

数据源：
  - OECD SDMX-JSON API: GDP、就业、贸易、TFP等
  - 无需API Key，免费使用

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings, os, re
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

server = Server("user-oecd-data")

_OECD_BASE = "https://stats.oecd.org/SDMX-JSON/data"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def _get(url: str, params: dict = None, timeout: int = 20) -> requests.Response:
    return _SESSION.get(url, params=params, timeout=timeout)


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_oecd_gdp",
        description="获取OECD GDP数据。\n\n"
                    "支持成员国GDP、GDP增速、人均GDP。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码: USA/CHN/DEU/JPN等或'OECD'"},
                "indicator": {"type": "string", "description": "指标: gdp/gdp_growth/gdp_per_capita", "default": "gdp_growth"},
                "year_range": {"type": "string", "description": "年份范围: 2010-2025", "default": "2010-2025"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_oecd_employment",
        description="获取OECD就业数据。\n\n"
                    "支持失业率、就业率、工资增速。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码"},
                "indicator": {"type": "string", "description": "指标: unemployment_rate/employment_rate/wage_growth", "default": "unemployment_rate"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_oecd_trade",
        description="获取OECD贸易数据。\n\n"
                    "支持进出口、贸易差额、贸易依存度。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码"},
                "indicator": {"type": "string", "description": "指标: exports/imports/trade_balance", "default": "exports"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_oecd_tfp",
        description="获取OECD TFP(全要素生产率)数据。\n\n"
                    "支持TFP水平、TFP增速。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码"},
                "indicator": {"type": "string", "description": "指标: tfp_level/tfp_growth", "default": "tfp_growth"}
            },
            "required": ["country_code"]
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

# ── OECD API 真实调用 ───────────────────────────────────────────────────────


def _oecd_fetch(url: str) -> dict | None:
    """Fetch data from OECD SDMX-JSON API. Returns None on failure."""
    try:
        resp = _SESSION.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def handle_gdp(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_gdp", "user-oecd-data")
    if check is not None:
        return check

    country = args.get("country_code", "USA")
    indicator = args.get("indicator", "gdp_growth")
    year_range = args.get("year_range", "2010-2025")
    try:
        start_year, end_year = year_range.split("-")
        start_year, end_year = int(start_year), int(end_year)
    except Exception:
        start_year, end_year = 2010, 2025

    # OECD SDMX-JSON: dataset/REF_AREA+Variable+Unit.Measure/Time
    country_map = {"USA": "USA", "CHN": "CHN", "DEU": "DEU", "JPN": "JPN",
                   "GBR": "GBR", "FRA": "FRA", "IND": "IND", "BRA": "BRA",
                   "CAN": "CAN", "AUS": "AUS", "KOR": "KOR", "MEX": "MEX",
                   "RUS": "RUS", "ZAF": "ZAF", "ITA": "ITA", "NLD": "NLD",
                   "CHE": "CHE", "POL": "POL", "SWE": "SWE", "NOR": "NOR"}
    oecd_country = country_map.get(country.upper(), country.upper())

    # GDP levels (USD billions) - use QNA dataset
    url = f"{_OECD_BASE}/QNA/{oecd_country}.GDPV.GP.Q/all"
    json_data = _oecd_fetch(url)

    if json_data and "dataSets" in json_data:
        try:
            observations = json_data["dataSets"][0]["observations"]
            years = sorted(observations.keys(), reverse=True)
            data = []
            for obs_key in years:
                parts = obs_key.split(":")
                if len(parts) >= 1:
                    year = int(parts[0])
                    if start_year <= year <= end_year:
                        val = observations[obs_key][0][0]
                        if val is not None:
                            data.append({"year": str(year), "value": round(val / 1e9, 1), "unit": "billion USD"})
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False, "source": "OECD QNA via SDMX-JSON",
                    "country": country, "indicator": "gdp",
                    "api_url": url, "data": sorted(data, key=lambda x: x["year"]),
                    "note": "GDP现价美元（十亿美元）"
                }, ensure_ascii=False))]

        except Exception:
            pass

    # Fallback: try GDP growth rate
    url2 = f"{_OECD_BASE}/QNA/{oecd_country}.GDPV.VOBARSA.Q/all"
    json_data2 = _oecd_fetch(url2)
    if json_data2 and "dataSets" in json_data2:
        try:
            observations = json_data2["dataSets"][0]["observations"]
            years = sorted(observations.keys(), reverse=True)
            data = []
            for obs_key in years:
                parts = obs_key.split(":")
                if len(parts) >= 1:
                    year = int(parts[0])
                    if start_year <= year <= end_year:
                        val = observations[obs_key][0][0]
                        if val is not None:
                            data.append({"year": str(year), "value": round(val, 2), "unit": "% YoY"})
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False, "source": "OECD QNA via SDMX-JSON",
                    "country": country, "indicator": "gdp_growth",
                    "api_url": url2, "data": sorted(data, key=lambda x: x["year"]),
                    "note": "GDP同比增速(%)"
                }, ensure_ascii=False))]
        except Exception:
            pass

    # API failed — return error marker (not mock data)
    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"OECD GDP API failed for {country}. Check network or try again.",
        "api_url": url,
        "note": "真实API调用失败，未返回模拟数据"
    }, ensure_ascii=False))]


async def handle_employment(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_employment", "user-oecd-data")
    if check is not None:
        return check

    country = args.get("country_code", "USA")
    indicator = args.get("indicator", "unemployment_rate")
    country_map = {"USA": "USA", "CHN": "CHN", "DEU": "DEU", "JPN": "JPN",
                   "GBR": "GBR", "FRA": "FRA", "ITA": "ITA", "CAN": "CAN",
                   "AUS": "AUS", "JPN": "JPN", "KOR": "KOR", "MEX": "MEX"}
    oecd_country = country_map.get(country.upper(), country.upper())

    # Unemployment rate from OECD database
    url = f"{_OECD_BASE}/LRSA/{oecd_country}.LRHURTT.SESA/all"
    json_data = _oecd_fetch(url)

    if json_data and "dataSets" in json_data:
        try:
            observations = json_data["dataSets"][0]["observations"]
            years = sorted(observations.keys(), reverse=True)
            data = []
            for obs_key in years[:10]:
                parts = obs_key.split(":")
                year = int(parts[0])
                val = observations[obs_key][0][0]
                if val is not None:
                    data.append({"year": str(year), "value": round(val, 1), "unit": "%"})
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False, "source": "OECD LRSA via SDMX-JSON",
                    "country": country, "indicator": indicator,
                    "api_url": url, "data": data,
                    "note": "失业率(%)"
                }, ensure_ascii=False))]
        except Exception:
            pass

    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"OECD Employment API failed for {country}.",
        "api_url": url,
        "note": "真实API调用失败"
    }, ensure_ascii=False))]


async def handle_trade(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_trade", "user-oecd-data")
    if check is not None:
        return check

    country = args.get("country_code", "USA")
    indicator = args.get("indicator", "exports")
    country_map = {"USA": "USA", "CHN": "CHN", "DEU": "DEU", "JPN": "JPN",
                   "GBR": "GBR", "FRA": "FRA", "ITA": "ITA", "CAN": "CAN"}
    oecd_country = country_map.get(country.upper(), country.upper())

    # Merchandise exports from OECD
    url = f"{_OECD_BASE}/TEND/{oecd_country}.M+X+goods.TCV_BAL/all"
    json_data = _oecd_fetch(url)

    if json_data and "dataSets" in json_data:
        try:
            obs = json_data["dataSets"][0]["observations"]
            years = sorted(obs.keys(), reverse=True)
            data = []
            for obs_key in years[:8]:
                parts = obs_key.split(":")
                year = int(parts[0])
                val = obs[obs_key][0][0]
                if val is not None:
                    data.append({"year": str(year), "value": round(val / 1e9, 1), "unit": "billion USD"})
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False, "source": "OECD TEND via SDMX-JSON",
                    "country": country, "indicator": indicator,
                    "api_url": url, "data": data,
                    "note": "商品贸易额(十亿美元)"
                }, ensure_ascii=False))]
        except Exception:
            pass

    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"OECD Trade API failed for {country}.",
        "api_url": url,
        "note": "真实API调用失败"
    }, ensure_ascii=False))]


async def handle_tfp(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_tfp", "user-oecd-data")
    if check is not None:
        return check

    country = args.get("country_code", "USA")
    indicator = args.get("indicator", "tfp_growth")
    country_map = {"USA": "USA", "CHN": "CHN", "DEU": "DEU", "JPN": "JPN",
                   "GBR": "GBR", "FRA": "FRA", "CAN": "CAN", "AUS": "AUS"}
    oecd_country = country_map.get(country.upper(), country.upper())

    # TFP from OECD Productivity database
    url = f"{_OECD_BASE}/PDB_GR/{oecd_country}.T_PDB_GRW+LV_PDB_GRW/all"
    json_data = _oecd_fetch(url)

    if json_data and "dataSets" in json_data:
        try:
            obs = json_data["dataSets"][0]["observations"]
            years = sorted(obs.keys(), reverse=True)
            data = []
            for obs_key in years[:8]:
                parts = obs_key.split(":")
                year = int(parts[0])
                val = obs[obs_key][0][0]
                if val is not None:
                    data.append({"year": str(year), "value": round(val, 2), "unit": "%"})
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False, "source": "OECD PDB via SDMX-JSON",
                    "country": country, "indicator": indicator,
                    "api_url": url, "data": data,
                    "note": "TFP同比增速(%)"
                }, ensure_ascii=False))]
        except Exception:
            pass

    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"OECD TFP API failed for {country}. TFP data may not be available for this country.",
        "api_url": url,
        "note": "真实API调用失败"
    }, ensure_ascii=False))]


TOOL_HANDLERS = {
    "get_oecd_gdp": handle_gdp,
    "get_oecd_employment": handle_employment,
    "get_oecd_trade": handle_trade,
    "get_oecd_tfp": handle_tfp,
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
    print("user-oecd-data MCP Server starting... (OECD API, no key required)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-oecd-data",
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
