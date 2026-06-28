#!/usr/bin/env python3
"""Chinese Customs MCP Server — 中国海关进出口数据

数据来源: https://stats.customs.gov.cn
注册: https://stats.customs.gov.cn/account/Register

数据覆盖:
  - 按HS编码的进出口金额/数量（金额单位：万美元）
  - 按贸易伙伴（国别/地区）的进出口数据
  - 按省份/城市的进出口数据
  - 按企业性质的进出口数据（国有企业/外资企业/民营企业）
  - 贸易顺差/逆差
  - 同比/环比增长率

用途:
  - 评估出口依存度（出口额/营业收入）
  - 关税政策效果评估（DID分析）
  - 中美贸易摩擦研究

STUB模式: 无API Key时返回占位数据，标注 _stub: true
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path

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

try:
    from mcp.server import Server, NotificationOptions
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
    from mcp.server.models import InitializationOptions
    import asyncio
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    import asyncio

try:
    from mcp_servers.mcp_mock_helper import check_mock_permission
except ImportError:
    def check_mock_permission(*a, **kw): return None

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

import os
API_KEY = os.environ.get("CHINESE_CUSTOMS_API_KEY", "")
BASE_URL = "https://stats.customs.gov.cn/api"

TOOLS: list[Tool] = [
    Tool(
        name="get_customs_import",
        description="查询中国海关进口数据。按HS编码、商品名称、贸易伙伴、月份等维度检索进口金额和数量。",
        inputSchema={
            "type": "object",
            "properties": {
                "hs_code": {"type": "string", "description": "HS商品编码（前6位，如847130=自动数据处理设备）"},
                "country": {"type": "string", "description": "贸易伙伴国家/地区代码（如USA、CHN、JPN）"},
                "province": {"type": "string", "description": "省份名称（如广东省、浙江省）"},
                "month_from": {"type": "string", "description": "起始月份（YYYY-MM）"},
                "month_to": {"type": "string", "description": "结束月份（YYYY-MM）"},
                "unit": {"type": "string", "default": "USD", "description": "金额单位：USD（美元）/CNY（人民币）/RMB"},
            },
        },
    ),
    Tool(
        name="get_customs_export",
        description="查询中国海关出口数据。按HS编码、商品名称、贸易伙伴、月份等维度检索出口金额和数量。",
        inputSchema={
            "type": "object",
            "properties": {
                "hs_code": {"type": "string", "description": "HS商品编码"},
                "country": {"type": "string", "description": "贸易伙伴国家/地区代码"},
                "province": {"type": "string", "description": "省份名称"},
                "month_from": {"type": "string", "description": "起始月份（YYYY-MM）"},
                "month_to": {"type": "string", "description": "结束月份（YYYY-MM）"},
                "unit": {"type": "string", "default": "USD"},
            },
        },
    ),
    Tool(
        name="get_customs_trade_balance",
        description="查询中国整体或特定商品/国家的贸易收支（出口-进口）。正值为顺差，负值为逆差。",
        inputSchema={
            "type": "object",
            "properties": {
                "hs_code": {"type": "string", "description": "HS商品编码（不填则返回总额）"},
                "country": {"type": "string", "description": "贸易伙伴国家/地区代码"},
                "year": {"type": "integer", "description": "年份"},
            },
        },
    ),
    Tool(
        name="get_customs_by_country",
        description="查询与特定国家/地区的双边贸易数据。包括进出口总额、贸易差额、主要商品构成。",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "国家/地区代码（如USA、DEU、KOR）"},
                "year": {"type": "integer", "description": "年份"},
                "top_hs_codes": {"type": "integer", "default": 10, "description": "返回前N大商品"},
            },
        },
    ),
]


async def _make_request(url: str, params: dict) -> dict:
    """Make authenticated request to customs API."""
    if not API_KEY:
        return {
            "status": "warning",
            "message": "CHINESE_CUSTOMS_API_KEY not configured. Register at https://stats.customs.gov.cn",
            "data": [],
            "fallback": "Use user-tushare for A-share data, or provide manual customs data files in data/customs/",
        }

    if not HAS_HTTPX:
        return {"status": "error", "message": "httpx not installed", "data": []}

    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params={k: v for k, v in params.items() if v is not None})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[Customs] API call failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


async def handle_import(params: dict) -> dict:
    """Get import data or return stub."""
    check = check_mock_permission(params, "get_customs_import", "user_chinese_customs")
    if check is not None:
        return check

    hs_code = params.get("hs_code", "")
    country = params.get("country", "")
    month_from = params.get("month_from", "")
    month_to = params.get("month_to", "")

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "message": "Customs API not configured. Returning sample data.",
            "hs_code": hs_code,
            "country": country,
            "data": [
                {"month": "2024-01", "import_value_usd": 218.5, "import_quantity": 12500, "yoy_change": 8.2},
                {"month": "2024-02", "import_value_usd": 195.3, "import_quantity": 11200, "yoy_change": 5.6},
                {"month": "2024-03", "import_value_usd": 232.1, "import_quantity": 13800, "yoy_change": 12.3},
                {"month": "2024-04", "import_value_usd": 208.7, "import_quantity": 12100, "yoy_change": 7.8},
                {"month": "2024-05", "import_value_usd": 225.4, "import_quantity": 13400, "yoy_change": 9.5},
            ],
            "unit": "10000 USD",
            "note": "Sample import data. Configure CHINESE_CUSTOMS_API_KEY for real data.",
        }

    return await _make_request(f"{BASE_URL}/import", params)


async def handle_export(params: dict) -> dict:
    """Get export data or return stub."""
    check = check_mock_permission(params, "get_customs_export", "user_chinese_customs")
    if check is not None:
        return check

    hs_code = params.get("hs_code", "")
    country = params.get("country", "")

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "message": "Customs API not configured. Returning sample data.",
            "hs_code": hs_code,
            "country": country,
            "data": [
                {"month": "2024-01", "export_value_usd": 298.5, "export_quantity": 18500, "yoy_change": 10.2},
                {"month": "2024-02", "export_value_usd": 265.3, "export_quantity": 16200, "yoy_change": 7.6},
                {"month": "2024-03", "export_value_usd": 315.2, "export_quantity": 20100, "yoy_change": 15.3},
                {"month": "2024-04", "export_value_usd": 288.7, "export_quantity": 17900, "yoy_change": 8.8},
                {"month": "2024-05", "export_value_usd": 302.4, "export_quantity": 19200, "yoy_change": 11.5},
            ],
            "unit": "10000 USD",
            "note": "Sample export data. Configure CHINESE_CUSTOMS_API_KEY for real data.",
        }

    return await _make_request(f"{BASE_URL}/export", params)


async def handle_balance(params: dict) -> dict:
    """Get trade balance or return stub."""
    check = check_mock_permission(params, "get_customs_trade_balance", "user_chinese_customs")
    if check is not None:
        return check

    hs_code = params.get("hs_code", "")
    country = params.get("country", "")
    year = params.get("year", 2024)

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "hs_code": hs_code,
            "country": country,
            "year": year,
            "export_value": 35000.5,
            "import_value": 25000.3,
            "trade_balance": 10000.2,
            "balance_type": "surplus",
            "unit": "10000 USD",
            "note": "Sample trade balance. Configure CHINESE_CUSTOMS_API_KEY for real data.",
        }

    return await _make_request(f"{BASE_URL}/balance", params)


async def handle_country(params: dict) -> dict:
    """Get bilateral trade data or return stub."""
    check = check_mock_permission(params, "get_customs_by_country", "user_chinese_customs")
    if check is not None:
        return check

    country = params.get("country", "USA")
    top_hs_codes = params.get("top_hs_codes", 10)

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "country": country,
            "year": params.get("year", 2024),
            "total_export": 50000.2,
            "total_import": 18000.5,
            "trade_balance": 32000.3,
            "top_goods": [
                {"rank": 1, "hs_code": "847130", "description": "自动数据处理设备", "export_value": 15000.3},
                {"rank": 2, "hs_code": "850152", "description": "电动机", "export_value": 8500.2},
                {"rank": 3, "hs_code": "851762", "description": "通讯设备", "export_value": 7200.5},
                {"rank": 4, "hs_code": "950450", "description": "玩具", "export_value": 5500.8},
                {"rank": 5, "hs_code": "640299", "description": "鞋类", "export_value": 4200.1},
            ][:top_hs_codes],
            "unit": "10000 USD",
            "note": "Sample bilateral trade data. Configure CHINESE_CUSTOMS_API_KEY for real data.",
        }

    return await _make_request(f"{BASE_URL}/bilateral", params)


TOOL_HANDLERS = {
    "get_customs_import": handle_import,
    "get_customs_export": handle_export,
    "get_customs_trade_balance": handle_balance,
    "get_customs_by_country": handle_country,
}


def create_server():
    server = Server("user-chinese-customs")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = await handler(arguments)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except Exception as e:
            _log.error("[Customs] Tool %s failed: %s", name, e)
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))]

    return server


async def main():
    print("user-chinese-customs MCP Server starting... (stub mode without API key)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-chinese-customs",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
