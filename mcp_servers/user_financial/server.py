#!/usr/bin/env python3
"""
user-financial MCP Server
=========================
全球宏观金融数据（FRED风格）。

数据源：
  - akshare: 中国、英国、日本、德国、澳大利亚、加拿大宏观数据（无需API Key）
  - World Bank API: 全球GDP/CPI/人口/贸易等宏观指标（无需API Key，https://datahelpdesk.worldbank.org）
  - FRED API: 美联储数据（需 FRED_API_KEY 环境变量，无Key也可访问部分公开端点）

Usage:
    python server.py
"""

from __future__ import annotations

import json, os, sys, warnings
from pathlib import Path
from typing import Any
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
import akshare as ak

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-financial")


# ── HTTP 会话（带超时）───────────────────────────────────────────────────────
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def _get(url: str, params: dict = None, timeout: int = 15) -> requests.Response:
    return _SESSION.get(url, params=params, timeout=timeout)


# ── World Bank API（无需Key，全球宏观数据）───────────────────────────────────

_WB_BASE = "https://api.worldbank.org/v2"


def _wb_indicator(country: str, indicator: str, per_page: int = 50) -> list[dict]:
    """从 World Bank API 获取宏观指标。country 可以是 'all' 或国家码如 'USA'/'CHN'。"""
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
    """World Bank JSON → 标准化 records"""
    records = []
    for item in wb_data:
        year = item.get("date", "")
        value = item.get("value")
        records.append({
            "year": year,
            "value": value,
            "indicator_id": item.get("indicator", {}).get("id", ""),
            "indicator_value": item.get("indicator", {}).get("value", ""),
            "country": item.get("country", {}).get("value", ""),
            "unit": item.get("indicator", {}).get("unit", ""),
        })
    return records


# ── akshare 可用函数映射 ────────────────────────────────────────────────────
# 以下函数实测可访问（不走金十数据），在中国大陆网络环境下可用

_CHINA_INDICATORS = {
    "cpi":                 ("macro_china_cpi",                  ["月份", "全国-当月", "全国-同比增长"]),
    "ppi":                 ("macro_china_ppi",                  ["月份", "当月", "当月同比增长"]),
    "gdp":                 ("macro_china_gdp",                  ["季度", "国内生产总值-绝对值", "国内生产总值-同比增长"]),
    "pmi":                 ("macro_china_pmi",                  ["月份", "制造业-指数", "制造业-同比增长"]),
    "m2":                  ("macro_china_money_supply",          ["月份", "货币和准货币(M2)-数量(亿元)", "货币和准货币(M2)-同比增长"]),
    "new_financial_credit":("macro_china_new_financial_credit", ["月份", "当月", "当月-同比增长"]),
    "money_supply":         ("macro_china_money_supply",         ["月份", "货币和准货币(M2)-数量(亿元)", "货币和准货币(M2)-同比增长"]),
    "fdi":                 ("macro_china_fdi",                  ["月份", "当月", "当月-同比增长"]),
    "retail":              ("macro_china_consumer_goods_retail", ["月份", "当月", "同比增长"]),
    "real_estate":         ("macro_china_real_estate",          ["日期", "最新值", "涨跌幅"]),
    "fixed_asset":         ("macro_china_gdzctz",              ["月份", "当月", "同比增长"]),
    "lpr":                 ("macro_china_lpr",                  ["TRADE_DATE", "LPR1Y", "LPR5Y"]),
    "shibor":              ("macro_china_shibor_all",          ["日期", "O/N-定价", "O/N-涨跌幅"]),
    "trade_balance":        ("macro_china_imports_yoy",        ["月份", "当月", "当月同比增长"]),
}

_UK_INDICATORS = {
    "cpi":                 ("macro_uk_cpi_yearly",              ["时间", "前值", "现值"]),
    "cpi_monthly":         ("macro_uk_cpi_monthly",           ["时间", "前值", "现值"]),
    "gdp_quarterly":       ("macro_uk_gdp_quarterly",         ["时间", "前值", "现值"]),
    "unemployment_rate":    ("macro_uk_unemployment_rate",       ["时间", "前值", "现值"]),
    "bank_rate":           ("macro_uk_bank_rate",              ["时间", "前值", "现值"]),
    "retail_monthly":      ("macro_uk_retail_monthly",        ["时间", "前值", "现值"]),
    "trade":               ("macro_uk_trade",                  ["时间", "前值", "现值"]),
}

_JAPAN_INDICATORS = {
    "cpi":                 ("macro_japan_cpi_yearly",           ["时间", "前值", "现值"]),
    "unemployment_rate":   ("macro_japan_unemployment_rate",    ["时间", "前值", "现值"]),
    "bank_rate":           ("macro_japan_bank_rate",           ["时间", "前值", "现值"]),
    "head_indicator":      ("macro_japan_head_indicator",     ["时间", "前值", "现值"]),
}

_GERMANY_INDICATORS = {
    "cpi":                 ("macro_germany_cpi_yearly",        ["时间", "前值", "现值"]),
    "gdp":                 ("macro_germany_gdp",              ["时间", "前值", "现值"]),
    "trade":               ("macro_germany_trade_adjusted",    ["时间", "前值", "现值"]),
    "zew":                 ("macro_germany_zew",              ["时间", "前值", "现值"]),
    "ifo":                 ("macro_germany_ifo",              ["时间", "前值", "现值"]),
    "retail_monthly":      ("macro_germany_retail_sale_monthly", ["时间", "前值", "现值"]),
}

_AUSTRALIA_INDICATORS = {
    "cpi":                 ("macro_australia_cpi_yearly",       ["时间", "前值", "现值"]),
    "unemployment_rate":   ("macro_australia_unemployment_rate", ["时间", "前值", "现值"]),
    "bank_rate":           ("macro_australia_bank_rate",        ["时间", "前值", "现值"]),
}

_CANADA_INDICATORS = {
    "cpi":                 ("macro_canada_cpi_yearly",         ["时间", "前值", "现值"]),
    "unemployment_rate":   ("macro_canada_unemployment_rate",  ["时间", "前值", "现值"]),
    "bank_rate":           ("macro_canada_bank_rate",          ["时间", "前值", "现值"]),
    "gdp_monthly":         ("macro_canada_gdp_monthly",        ["时间", "前值", "现值"]),
    "trade":               ("macro_canada_trade",              ["时间", "前值", "现值"]),
}

# World Bank 指标映射（用于无法通过akshare获取的数据）
_WB_INDICATORS = {
    # GDP
    "wb_gdp_usd":         "NY.GDP.MKTP.CD",    # GDP (current USD)
    "wb_gdp_growth":      "NY.GDP.MKTP.KD.ZG", # GDP growth (annual %)
    # CPI
    "wb_inflation":       "FP.CPI.TOTL.ZG",     # Inflation, consumer prices (annual %)
    # Population
    "wb_population":      "SP.POP.TOTL",        # Population total
    # Trade
    "wb_trade_gdp":       "BN.CAB.XOKA.GD.ZS", # Trade (% of GDP)
    "wb_exports":         "NE.EXP.GNFS.ZS",     # Exports of goods and services (% of GDP)
    "wb_imports":         "NE.IMP.GNFS.ZS",     # Imports of goods and services (% of GDP)
    # Debt
    "wb_debt_gdp":        "GC.DOD.TOTL.GD.ZS", # Central government debt (% of GDP)
    # 特定国家GDP
    "wb_usa_gdp":         "NY.GDP.MKTP.CD",
    "wb_chn_gdp":         "NY.GDP.MKTP.CD",
    "wb_deu_gdp":         "NY.GDP.MKTP.CD",
    "wb_jpn_gdp":         "NY.GDP.MKTP.CD",
    "wb_gbr_gdp":         "NY.GDP.MKTP.CD",
    "wb_fra_gdp":         "NY.GDP.MKTP.CD",
}

# 各国 → World Bank 国家代码
_WB_COUNTRY_MAP = {
    "usa": "USA", "us": "USA", "america": "USA",
    "chn": "CHN", "china": "CHN",
    "deu": "DEU", "germany": "DEU", "de": "DEU",
    "jpn": "JPN", "japan": "JPN", "jp": "JPN",
    "gbr": "GBR", "uk": "GBR", "united kingdom": "GBR",
    "fra": "FRA", "france": "FRA",
    "kor": "KOR", "korea": "KOR",
    "ind": "IND", "india": "IND",
    "bra": "BRA", "brazil": "BRA",
    "can": "CAN", "canada": "CAN",
    "aus": "AUS", "australia": "AUS",
    "all": "all",
}


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_wb_indicator",
        description="从 World Bank API 获取宏观指标（GDP/CPI/人口/贸易等）。无需 API Key，覆盖全球所有国家。\n\n"
                    "常用指标：\n"
                    "  wb_gdp_usd: GDP（美元现价）\n"
                    "  wb_gdp_growth: GDP增速（年度%）\n"
                    "  wb_inflation: 通胀率（消费者价格，年度%）\n"
                    "  wb_population: 总人口\n"
                    "  wb_trade_gdp: 贸易占GDP比重\n"
                    "  wb_exports: 出口占GDP比重\n"
                    "  wb_imports: 进口占GDP比重\n"
                    "  wb_debt_gdp: 政府债务占GDP比重",
        inputSchema={
            "type": "object",
            "properties": {
                "country_code": {
                    "type": "string",
                    "description": "国家代码（World Bank格式）：USA/CHN/DEU/JPN/GBR/FRA/KOR/IND/BRA/CAN/AUS，或 'all'（所有国家）"
                },
                "indicator": {
                    "type": "string",
                    "description": "指标代码",
                    "enum": list(_WB_INDICATORS.keys())
                },
                "per_page": {
                    "type": "integer",
                    "default": 50,
                    "description": "返回记录数上限"
                }
            },
            "required": ["country_code", "indicator"]
        }
    ),
    Tool(
        name="get_macro_china",
        description="获取中国宏观经济指标。使用 akshare 接口，无需 API Key。\n\n"
                    "可用指标：\n"
                    "  cpi/ppi/gdp/pmi — CPI/PPI/GDP/制造业PMI\n"
                    "  m2/money_supply — 货币供应量M2\n"
                    "  new_financial_credit — 新增社融\n"
                    "  fdi — 外商直接投资\n"
                    "  retail — 社会消费品零售总额\n"
                    "  real_estate — 房地产开发投资\n"
                    "  fixed_asset — 固定资产投资\n"
                    "  lpr — LPR利率（1年期/5年期）\n"
                    "  shibor — 上海银行间同业拆借利率",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称",
                    "enum": list(_CHINA_INDICATORS.keys())
                }
            },
            "required": ["indicator"]
        }
    ),
    Tool(
        name="get_macro_uk",
        description="获取英国宏观经济指标。使用 akshare 接口，无需 API Key。\n\n"
                    "可用指标：cpi, cpi_monthly, gdp_quarterly, unemployment_rate, bank_rate, retail_monthly, trade",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称",
                    "enum": list(_UK_INDICATORS.keys())
                }
            },
            "required": ["indicator"]
        }
    ),
    Tool(
        name="get_macro_japan",
        description="获取日本宏观经济指标。使用 akshare 接口，无需 API Key。\n\n"
                    "可用指标：cpi, unemployment_rate, bank_rate, head_indicator",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称",
                    "enum": list(_JAPAN_INDICATORS.keys())
                }
            },
            "required": ["indicator"]
        }
    ),
    Tool(
        name="get_macro_germany",
        description="获取德国宏观经济指标。使用 akshare 接口，无需 API Key。\n\n"
                    "可用指标：cpi, gdp, trade, zew, ifo, retail_monthly",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称",
                    "enum": list(_GERMANY_INDICATORS.keys())
                }
            },
            "required": ["indicator"]
        }
    ),
    Tool(
        name="get_macro_australia",
        description="获取澳大利亚宏观经济指标。使用 akshare 接口，无需 API Key。\n\n"
                    "可用指标：cpi, unemployment_rate, bank_rate",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称",
                    "enum": list(_AUSTRALIA_INDICATORS.keys())
                }
            },
            "required": ["indicator"]
        }
    ),
    Tool(
        name="get_macro_canada",
        description="获取加拿大宏观经济指标。使用 akshare 接口，无需 API Key。\n\n"
                    "可用指标：cpi, unemployment_rate, bank_rate, gdp_monthly, trade",
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "指标名称",
                    "enum": list(_CANADA_INDICATORS.keys())
                }
            },
            "required": ["indicator"]
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

def _safe_json_response(data: Any, tool_name: str) -> dict:
    """Standardized response format for all MCP tools.
    - Success: {"result": <data>, "success": True, "tool": <tool_name>}
    - Error:   {"error": <message>, "success": False, "tool": <tool_name>}
    """
    if isinstance(data, dict) and "error" in data:
        return {"error": data["error"], "success": False, "tool": tool_name}
    if isinstance(data, dict) and "result" in data:
        return data
    return {"result": data, "success": True, "tool": tool_name}


def _df_to_json(df) -> str:
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"result": {"data": [], "count": 0}, "success": True}, ensure_ascii=False)
    result = {"data": [], "count": 0, "columns": list(df.columns)}
    try:
        records = df.to_dict(orient="records")
        for row in records:
            for k, v in list(row.items()):
                if hasattr(v, "strftime"):
                    row[k] = v.strftime("%Y-%m-%d")
                elif hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        result["data"] = records
        result["count"] = len(records)
    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)
    return json.dumps({"result": result, "success": True}, ensure_ascii=False)


def _akshare_fetch(indicator_map: dict, indicator: str) -> str:
    entry = indicator_map.get(indicator)
    if not entry:
        return json.dumps({"error": f"Unknown indicator: {indicator}", "success": False}, ensure_ascii=False)
    func_name, _ = entry
    func = getattr(ak, func_name, None)
    if not func:
        return json.dumps({"error": f"akshare has no function: {func_name}", "success": False}, ensure_ascii=False)
    try:
        df = func()
        return _df_to_json(df)
    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)


def _wb_fetch(country_code: str, indicator: str, per_page: int) -> str:
    wb_code = _WB_INDICATORS.get(indicator)
    if not wb_code:
        return json.dumps({"error": f"Unknown indicator: {indicator}", "success": False}, ensure_ascii=False)
    wb_country = _WB_COUNTRY_MAP.get(country_code.lower(), country_code)
    data = _wb_indicator(wb_country, wb_code, per_page)
    return json.dumps({"result": {"data": data, "count": len(data)}, "success": True}, ensure_ascii=False, default=str)


# ── 工具处理函数 ───────────────────────────────────────────────────────────

async def handle_wb(args: dict) -> list[TextContent]:
    result = _wb_fetch(
        args.get("country_code", "USA"),
        args.get("indicator", ""),
        args.get("per_page", 50)
    )
    return [TextContent(type="text", text=result)]


async def handle_china(args: dict) -> list[TextContent]:
    result = _akshare_fetch(_CHINA_INDICATORS, args.get("indicator", ""))
    return [TextContent(type="text", text=result)]


async def handle_uk(args: dict) -> list[TextContent]:
    result = _akshare_fetch(_UK_INDICATORS, args.get("indicator", ""))
    return [TextContent(type="text", text=result)]


async def handle_japan(args: dict) -> list[TextContent]:
    result = _akshare_fetch(_JAPAN_INDICATORS, args.get("indicator", ""))
    return [TextContent(type="text", text=result)]


async def handle_germany(args: dict) -> list[TextContent]:
    result = _akshare_fetch(_GERMANY_INDICATORS, args.get("indicator", ""))
    return [TextContent(type="text", text=result)]


async def handle_australia(args: dict) -> list[TextContent]:
    result = _akshare_fetch(_AUSTRALIA_INDICATORS, args.get("indicator", ""))
    return [TextContent(type="text", text=result)]


async def handle_canada(args: dict) -> list[TextContent]:
    result = _akshare_fetch(_CANADA_INDICATORS, args.get("indicator", ""))
    return [TextContent(type="text", text=result)]


TOOL_HANDLERS = {
    "get_wb_indicator": handle_wb,
    "get_macro_china": handle_china,
    "get_macro_uk": handle_uk,
    "get_macro_japan": handle_japan,
    "get_macro_germany": handle_germany,
    "get_macro_australia": handle_australia,
    "get_macro_canada": handle_canada,
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
    print(f"user-financial MCP Server starting... (akshare {ak.__version__})", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-financial",
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
