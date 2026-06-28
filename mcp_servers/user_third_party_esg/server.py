#!/usr/bin/env python3
"""Third-Party ESG MCP Server — 第三方ESG评级数据

数据来源:
  - 商道融绿 (SynTao) ESG评级: https://www.syntao.com
  - 华证指数 (CSI) ESG评级: http://www.csi.com.cn
  - 中证ESG评分: http://www.csindex.com.cn
  - 富时ESG评级（境外）

数据覆盖:
  - ESG综合评分（E/S/G三个维度）
  - ESG评级（AAA-C）
  - ESG争议事件
  - ESG排名（行业/全市场）
  - 碳排放数据（E维度）

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
SYNTAO_KEY = os.environ.get("SYNTAO_API_KEY", "")
CSI_KEY = os.environ.get("CSI_ESG_API_KEY", "")
CUSTOM_KEY = os.environ.get("THIRD_PARTY_ESG_KEY", "")

TOOLS: list[Tool] = [
    Tool(
        name="get_esg_rating",
        description="获取企业ESG综合评分和评级。支持商道融绿、华证、中证、富时等多家评级机构。返回E/S/G分项得分及综合评级。",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码（如000001.SZ）"},
                "company_name": {"type": "string", "description": "公司名称（与股票代码二选一）"},
                "provider": {"type": "string", "enum": ["syntao", "csi", "csi_esg", "ftse", "all"], "default": "all", "description": "评级机构"},
                "year": {"type": "integer", "description": "评级年份（默认最新）"},
                "include_subscores": {"type": "boolean", "default": True, "description": "是否包含E/S/G分项得分"},
            },
        },
    ),
    Tool(
        name="get_esg_trend",
        description="获取企业ESG评分历史趋势数据。展示近5年ESG得分变化，支持与行业均值对比。",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码"},
                "company_name": {"type": "string", "description": "公司名称"},
                "years": {"type": "integer", "default": 5, "description": "返回年份数"},
            },
        },
    ),
    Tool(
        name="get_esg_controversy",
        description="查询企业ESG相关争议事件。覆盖环境处罚、劳动纠纷、治理违规、财务造假等负面事件。",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码"},
                "event_type": {"type": "string", "enum": ["environmental", "social", "governance", "financial", "all"], "default": "all"},
                "severity": {"type": "string", "enum": ["high", "medium", "low", "all"], "default": "all"},
                "start_date": {"type": "string", "description": "事件日期起（YYYY-MM-DD）"},
                "end_date": {"type": "string", "description": "事件日期止（YYYY-MM-DD）"},
            },
        },
    ),
    Tool(
        name="get_esg_ranking",
        description="获取ESG评分全市场排名或行业排名。",
        inputSchema={
            "type": "object",
            "properties": {
                "market": {"type": "string", "enum": ["A-share", "CSI300", "CSI500", "CSI800", "all"], "default": "all"},
                "industry": {"type": "string", "description": "行业名称（如制造业、金融）"},
                "year": {"type": "integer", "description": "年份"},
                "top_n": {"type": "integer", "default": 100, "description": "返回前N名"},
            },
        },
    ),
]


def _check_credentials() -> dict:
    """Check if any ESG API key is configured."""
    if not (SYNTAO_KEY or CSI_KEY or CUSTOM_KEY):
        return {
            "status": "warning",
            "message": "No ESG API key configured. Set SYNTAO_API_KEY, CSI_ESG_API_KEY, or THIRD_PARTY_ESG_KEY environment variable.",
            "fallback_suggestion": "Use user-yfinance for ESG-related data, or provide manual ESG data files in data/esg/ directory.",
        }
    return {}


async def handle_esg_rating(params: dict) -> dict:
    """Get ESG rating or return stub data."""
    check = check_mock_permission(params, "get_esg_rating", "user_third_party_esg")
    if check is not None:
        return check

    stock_code = params.get("stock_code", "")
    company_name = params.get("company_name", "")
    provider = params.get("provider", "all")
    include_subscores = params.get("include_subscores", True)

    if not (SYNTAO_KEY or CSI_KEY):
        return {
            "status": "stub",
            "_stub": True,
            "message": "ESG API not configured. Returning sample data.",
            "stock_code": stock_code,
            "company_name": company_name,
            "provider": provider,
            "esg_rating": {
                "overall": {"score": 72.5, "rating": "A", "rank": 1568},
                "environmental": {"score": 68.2, "rating": "BBB", "weight": 0.35},
                "social": {"score": 75.8, "rating": "A", "weight": 0.35},
                "governance": {"score": 74.1, "rating": "A-", "weight": 0.30},
            } if include_subscores else {"overall": {"score": 72.5, "rating": "A", "rank": 1568}},
            "data_date": "2024-12-31",
            "note": "Sample data from stub. Configure ESG API keys for real data.",
        }

    if provider in ("syntao", "all") and SYNTAO_KEY:
        url = "https://api.syntao.com/esg/rating"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {SYNTAO_KEY}"},
                    params={k: v for k, v in params.items() if k != "provider" and v is not None},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            _log.warning("[ESG] SynTao API failed: %s", e)

    if provider in ("csi", "all") and CSI_KEY:
        url = "https://api.csi.com.cn/esg/rating"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    url,
                    headers={"X-API-Key": CSI_KEY},
                    params={k: v for k, v in params.items() if k != "provider" and v is not None},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            _log.warning("[ESG] CSI ESG API failed: %s", e)

    return {
        "status": "warning",
        "message": "No configured ESG API key returned data. Configure SYNTAO_API_KEY or CSI_ESG_API_KEY.",
        "data": {},
    }


async def handle_esg_trend(params: dict) -> dict:
    """Get ESG trend or return stub data."""
    check = check_mock_permission(params, "get_esg_trend", "user_third_party_esg")
    if check is not None:
        return check

    stock_code = params.get("stock_code", "")
    years = params.get("years", 5)

    if not SYNTAO_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "stock_code": stock_code,
            "trend": [
                {"year": 2020, "esg_score": 65.2, "industry_avg": 58.3},
                {"year": 2021, "esg_score": 67.8, "industry_avg": 60.1},
                {"year": 2022, "esg_score": 69.5, "industry_avg": 61.8},
                {"year": 2023, "esg_score": 71.2, "industry_avg": 63.5},
                {"year": 2024, "esg_score": 72.5, "industry_avg": 65.2},
            ],
            "note": "Sample trend data. Configure SYNTAO_API_KEY for real data.",
        }

    url = "https://api.syntao.com/esg/trend"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {SYNTAO_KEY}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[ESG] Trend API failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


async def handle_esg_controversy(params: dict) -> dict:
    """Get ESG controversy events or return stub data."""
    check = check_mock_permission(params, "get_esg_controversy", "user_third_party_esg")
    if check is not None:
        return check

    stock_code = params.get("stock_code", "")
    event_type = params.get("event_type", "all")

    if not CUSTOM_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "stock_code": stock_code,
            "controversies": [
                {
                    "event_id": "ESG2023001",
                    "event_date": "2023-06-15",
                    "event_type": "environmental",
                    "severity": "medium",
                    "description": "因排放超标被环保部门处罚",
                    "fine_amount": 50000,
                    "status": "resolved",
                },
                {
                    "event_id": "ESG2024003",
                    "event_date": "2024-03-20",
                    "event_type": "governance",
                    "severity": "low",
                    "description": "信息披露不及时",
                    "fine_amount": 10000,
                    "status": "resolved",
                },
            ],
            "total_count": 2,
            "note": "Sample controversy data. Configure THIRD_PARTY_ESG_KEY for real data.",
        }

    url = "https://api.esgdata.com/controversy"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {CUSTOM_KEY}"},
                params={k: v for k, v in params.items() if v is not None},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[ESG] Controversy API failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


async def handle_esg_ranking(params: dict) -> dict:
    """Get ESG ranking or return stub data."""
    check = check_mock_permission(params, "get_esg_ranking", "user_third_party_esg")
    if check is not None:
        return check

    market = params.get("market", "A-share")
    top_n = params.get("top_n", 100)

    if not CSI_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "market": market,
            "top_companies": [
                {"rank": 1, "stock_code": "600519.SH", "company_name": "贵州茅台", "esg_score": 92.3},
                {"rank": 2, "stock_code": "601318.SH", "company_name": "中国平安", "esg_score": 89.7},
                {"rank": 3, "stock_code": "000858.SZ", "company_name": "五粮液", "esg_score": 88.1},
                {"rank": 4, "stock_code": "600036.SH", "company_name": "招商银行", "esg_score": 87.5},
                {"rank": 5, "stock_code": "601888.SH", "company_name": "中国中免", "esg_score": 86.2},
            ][:top_n],
            "total_count": 4500,
            "note": "Sample ranking data. Configure CSI_ESG_API_KEY for real data.",
        }

    url = "http://www.csi.com.cn/api/esg/ranking"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url,
                headers={"X-API-Key": CSI_KEY},
                params={k: v for k, v in params.items() if v is not None},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[ESG] Ranking API failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


TOOL_HANDLERS = {
    "get_esg_rating": handle_esg_rating,
    "get_esg_trend": handle_esg_trend,
    "get_esg_controversy": handle_esg_controversy,
    "get_esg_ranking": handle_esg_ranking,
}


def create_server():
    server = Server("user-third-party-esg")

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
            _log.error("[ESG] Tool %s failed: %s", name, e)
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))]

    return server


async def main():
    print("user-third-party-esg MCP Server starting... (stub mode without API key)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-third-party-esg",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
