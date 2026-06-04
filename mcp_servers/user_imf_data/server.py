#!/usr/bin/env python3
"""
user-imf-data MCP Server
=======================
IMF Data API 服务。

数据源：
  - IMF API: WEO数据、国际收支(BOP)、国际金融统计(IFS)
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

server = Server("user-imf-data")

_IMF_BASE = "https://dataservices.imf.org/REST/SDMX_JSON.svc"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def _get(url: str, params: dict = None, timeout: int = 20) -> requests.Response:
    return _SESSION.get(url, params=params, timeout=timeout)


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_imf_world_economic_outlook",
        description="获取IMF世界经济展望(WEO)数据。\n\n"
                    "支持GDP增速、通胀、失业率、财政余额等宏观指标。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码: USA/CHN/DEU/JPN等"},
                "indicator": {"type": "string", "description": "指标: gdp_growth/inflation/unemployment/fiscal_balance", "default": "gdp_growth"},
                "year_range": {"type": "string", "description": "年份范围: 2010-2025", "default": "2010-2025"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_imf_bop",
        description="获取IMF国际收支(BOP)数据。\n\n"
                    "支持经常账户、资本账户、金融账户、储备资产。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码"},
                "indicator": {"type": "string", "description": "指标: current_account/capital_account/financial_account/reserve", "default": "current_account"}
            },
            "required": ["country_code"]
        }
    ),
    Tool(
        name="get_imf_ifs",
        description="获取IMF国际金融统计(IFS)数据。\n\n"
                    "支持汇率、国际储备、货币供应量、利率等。",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {"type": "string", "description": "国家代码"},
                "indicator": {"type": "string", "description": "指标: exchange_rate/reserve/money_supply/interest_rate", "default": "exchange_rate"}
            },
            "required": ["country_code"]
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

# ── IMF API 真实调用 ─────────────────────────────────────────────────────────


def _imf_fetch(url: str) -> dict | None:
    """Fetch data from IMF API. Returns None on failure."""
    try:
        resp = _SESSION.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def handle_weo(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_weo", "user-imf-data")
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

    # IMF WEO database via IFS API
    # Use CompactData/WS_DATA/PCOLLEG + country + indicator
    indicator_map = {
        "gdp_growth": ("NGDP_RPCH", "Gross domestic product - Real growth rates (Percent change)"),
        "inflation": ("PCPI_PC_PP", "Inflation, end of period consumer prices (Percent change)"),
        "unemployment": ("LUR_PC", "Unemployment rate (Percent of total labor force)"),
        "fiscal_balance": ("GGXCNL_GDP", "General government net lending/borrowing (Percent of GDP)"),
    }
    imf_indicator, indicator_label = indicator_map.get(
        indicator, ("NGDP_RPCH", "GDP Growth"))

    country_map = {
        "USA": "US", "CHN": "CN", "DEU": "DE", "JPN": "JP",
        "GBR": "GB", "FRA": "FR", "IND": "IN", "BRA": "BR",
        "CAN": "CA", "AUS": "AU", "KOR": "KR", "MEX": "MX",
        "ITA": "IT", "NLD": "NL", "CHE": "CH", "POL": "PL",
        "SWE": "SE", "NOR": "NO", "RUS": "RU", "ZAF": "ZA",
    }
    imf_country = country_map.get(country.upper(), country.upper())

    url = f"{_IMF_BASE}/CompactData/IFS/{imf_country}.{imf_indicator}"
    json_data = _imf_fetch(url)

    if json_data and "CompactData" in json_data:
        try:
            series = json_data["CompactData"]["DataSet"]["Series"]
            obs_list = series.get("Obs", [])
            if isinstance(obs_list, dict):
                obs_list = [obs_list]
            data = []
            for obs in obs_list:
                year_str = str(obs.get("@TIME_PERIOD", ""))
                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    continue
                if not (start_year <= year <= end_year):
                    continue
                val = obs.get("@OBS_VALUE")
                if val is not None:
                    data.append({
                        "year": year_str,
                        "value": round(float(val), 2),
                        "unit": "%"
                    })
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False,
                    "source": "IMF IFS via REST API",
                    "country": country,
                    "indicator": indicator,
                    "indicator_label": indicator_label,
                    "api_url": url,
                    "data": sorted(data, key=lambda x: x["year"]),
                    "note": f"IMF IFS数据 ({indicator_label})"
                }, ensure_ascii=False))]
        except Exception:
            pass

    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"IMF WEO API failed for {country} ({indicator}). Check network.",
        "api_url": url,
        "note": "真实API调用失败，未返回模拟数据"
    }, ensure_ascii=False))]


async def handle_bop(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_bop", "user-imf-data")
    if check is not None:
        return check

    country = args.get("country_code", "USA")
    indicator = args.get("indicator", "current_account")
    country_map = {
        "USA": "US", "CHN": "CN", "DEU": "DE", "JPN": "JP",
        "GBR": "GB", "FRA": "FR", "CAN": "CA", "AUS": "AU",
    }
    imf_country = country_map.get(country.upper(), country.upper())

    # IMF BOP via IFS
    indicator_map = {
        "current_account": ("BCA_BOPC_USD", "Current account balance (Billions of US dollars)"),
        "capital_account": ("BCABP_BOPC_USD", "Capital account (Billions of US dollars)"),
        "financial_account": ("BFA_BOPC_USD", "Financial account (Billions of US dollars)"),
        "reserve": ("RER_USD", "Total reserves (Millions of US dollars)"),
    }
    imf_indicator, indicator_label = indicator_map.get(
        indicator, ("BCA_BOPC_USD", "Current account"))

    url = f"{_IMF_BASE}/CompactData/BOP/{imf_country}.{imf_indicator}"
    json_data = _imf_fetch(url)

    if json_data and "CompactData" in json_data:
        try:
            series = json_data["CompactData"]["DataSet"]["Series"]
            obs_list = series.get("Obs", [])
            if isinstance(obs_list, dict):
                obs_list = [obs_list]
            data = []
            for obs in obs_list[-10:]:
                year_str = str(obs.get("@TIME_PERIOD", ""))
                val = obs.get("@OBS_VALUE")
                if val is not None:
                    try:
                        year = int(year_str)
                        data.append({
                            "year": year_str,
                            "value": round(float(val), 3),
                            "unit": "billion USD"
                        })
                    except ValueError:
                        continue
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False,
                    "source": "IMF BOP via REST API",
                    "country": country,
                    "indicator": indicator,
                    "indicator_label": indicator_label,
                    "api_url": url,
                    "data": sorted(data, key=lambda x: x["year"]),
                    "note": f"IMF国际收支({indicator_label})，单位：十亿美元"
                }, ensure_ascii=False))]
        except Exception:
            pass

    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"IMF BOP API failed for {country}.",
        "api_url": url,
        "note": "真实API调用失败"
    }, ensure_ascii=False))]


async def handle_ifs(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_ifs", "user-imf-data")
    if check is not None:
        return check

    country = args.get("country_code", "USA")
    indicator = args.get("indicator", "exchange_rate")
    country_map = {
        "USA": "US", "CHN": "CN", "DEU": "DE", "JPN": "JP",
        "GBR": "GB", "FRA": "FR", "CAN": "CA", "AUS": "AU",
    }
    imf_country = country_map.get(country.upper(), country.upper())

    # IFS indicator map
    ifs_indicator_map = {
        "exchange_rate": ("ENDA_XDC_USD", "End-period exchange rate (National Currency per USD)"),
        "reserve": ("RESERVE_USD", "Total reserves (Millions of USD)"),
        "money_supply": ("MABME_USD", "Broad money (Millions of USD)"),
        "interest_rate": ("IRST_BBKC", "Short-term interest rates (Percent)"),
    }
    ifs_code, ifs_label = ifs_indicator_map.get(
        indicator, ("ENDA_XDC_USD", "Exchange rate"))

    # IFS exchange rates: ENDG_USD rate (units per USD)
    url = f"{_IMF_BASE}/CompactData/IFS/{imf_country}.{ifs_code}"
    json_data = _imf_fetch(url)

    if json_data and "CompactData" in json_data:
        try:
            series = json_data["CompactData"]["DataSet"]["Series"]
            obs_list = series.get("Obs", [])
            if isinstance(obs_list, dict):
                obs_list = [obs_list]
            data = []
            for obs in obs_list[-10:]:
                year_str = str(obs.get("@TIME_PERIOD", ""))
                val = obs.get("@OBS_VALUE")
                if val is not None:
                    try:
                        year = int(year_str)
                        data.append({
                            "year": year_str,
                            "value": round(float(val), 4),
                            "unit": "local units per USD"
                        })
                    except ValueError:
                        continue
            if data:
                return [TextContent(type="text", text=json.dumps({
                    "_mock": False,
                    "source": "IMF IFS via REST API",
                    "country": country,
                    "indicator": indicator,
                    "indicator_label": ifs_label,
                    "api_url": url,
                    "data": sorted(data, key=lambda x: x["year"]),
                    "note": f"IMF IFS: {ifs_label}"
                }, ensure_ascii=False))]
        except Exception:
            pass

    return [TextContent(type="text", text=json.dumps({
        "_error": True, "_mock": False,
        "message": f"IMF IFS API failed for {country} ({indicator}).",
        "api_url": url,
        "note": "真实API调用失败"
    }, ensure_ascii=False))]


TOOL_HANDLERS = {
    "get_imf_world_economic_outlook": handle_weo,
    "get_imf_bop": handle_bop,
    "get_imf_ifs": handle_ifs,
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
    print("user-imf-data MCP Server starting... (IMF API, no key required)", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-imf-data",
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
