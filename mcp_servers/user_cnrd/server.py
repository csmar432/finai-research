#!/usr/bin/env python3
"""CNRDS MCP Server — 中国研究数据服务平台

API文档: https://www.cnrds.com
注册获取Key: https://www.cnrds.com/Account/Register

数据覆盖:
  - 专利数据（发明/实用新型/外观设计）
  - 学术论文（中文期刊/学位论文）
  - 上市公司财务数据
  - 高新技术企业认定数据

STUB模式: 无API Key时返回占位数据，标注 _stub: true
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path
from typing import Any

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
API_KEY = os.environ.get("CNRDS_API_KEY", "")
BASE_URL = "https://www.cnrds.com/api"

# ─── Tool Definitions ──────────────────────────────────────────────────────────


TOOLS: list[Tool] = [
    Tool(
        name="get_cnrd_patent",
        description="查询CNRDS专利数据库。支持按申请人、发明人、关键词、日期范围检索专利。覆盖中国所有专利类型（发明/实用新型/外观设计）。",
        inputSchema={
            "type": "object",
            "properties": {
                "applicant": {"type": "string", "description": "专利申请人/权利人"},
                "inventor": {"type": "string", "description": "发明人"},
                "keyword": {"type": "string", "description": "关键词"},
                "patent_type": {"type": "string", "enum": ["发明", "实用新型", "外观设计", "all"], "default": "all", "description": "专利类型"},
                "start_date": {"type": "string", "description": "申请日期起（YYYY-MM-DD）"},
                "end_date": {"type": "string", "description": "申请日期止（YYYY-MM-DD）"},
                "page": {"type": "integer", "default": 1, "description": "页码"},
                "page_size": {"type": "integer", "default": 20, "description": "每页条数（最大100）"},
            },
        },
    ),
    Tool(
        name="search_cnrd_papers",
        description="检索CNRDS学术论文数据库。覆盖中文核心期刊、学位论文、会议论文。",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "论文标题关键词"},
                "author": {"type": "string", "description": "作者"},
                "journal": {"type": "string", "description": "期刊名称"},
                "year_from": {"type": "integer", "description": "发表年份起"},
                "year_to": {"type": "integer", "description": "发表年份止"},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
            },
        },
    ),
    Tool(
        name="get_cnrd_company",
        description="查询CNRDS上市公司数据库。获取上市公司基本信息、股权结构、高管信息。",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码（支持沪深格式）"},
                "company_name": {"type": "string", "description": "公司名称（模糊匹配）"},
            },
        },
    ),
    Tool(
        name="get_cnrd_financial",
        description="查询CNRDS上市公司财务数据库。获取资产负债、利润表、现金流量数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "股票代码"},
                "year": {"type": "integer", "description": "年份"},
                "quarter": {"type": "integer", "description": "季度（1-4），不填则返回年度"},
            },
        },
    ),
]


# ─── Tool Handlers ─────────────────────────────────────────────────────────────


async def handle_get_cnrd_patent(params: dict) -> dict:
    """Handle patent query or return stub."""
    check = check_mock_permission(params, "get_cnrd_patent", "user_cnrd")
    if check is not None:
        return check

    keyword = params.get("keyword", "")
    applicant = params.get("applicant", "")

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "message": "CNRDS API not configured. Returning sample patent data.",
            "query": {"keyword": keyword, "applicant": applicant},
            "total_results": 3,
            "patents": [
                {
                    "patent_id": "CN202110001234.5",
                    "title": "基于区块链技术的供应链金融风控方法",
                    "applicant": "蚂蚁区块链科技（上海）有限公司",
                    "inventor": "张三, 李四",
                    "patent_type": "发明",
                    "application_date": "2021-01-05",
                    "ipc_code": "G06Q40/02",
                },
                {
                    "patent_id": "CN202120123456.8",
                    "title": "一种智能合约自动执行系统",
                    "applicant": "中国平安保险(集团)股份有限公司",
                    "inventor": "王五",
                    "patent_type": "实用新型",
                    "application_date": "2021-02-10",
                    "ipc_code": "G06F9/455",
                },
            ],
            "note": "Sample data. Configure CNRDS_API_KEY at https://www.cnrds.com for real data.",
        }

    url = f"{BASE_URL}/patent/search"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params={k: v for k, v in params.items() if v is not None})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[CNRDS] API call failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


async def handle_search_cnrd_papers(params: dict) -> dict:
    """Handle paper search or return stub."""
    check = check_mock_permission(params, "search_cnrd_papers", "user_cnrd")
    if check is not None:
        return check

    title = params.get("title", "")
    author = params.get("author", "")

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "message": "CNRDS API not configured. Returning sample paper data.",
            "query": {"title": title, "author": author},
            "total_results": 5,
            "papers": [
                {
                    "paper_id": "CNKI-2021-001",
                    "title": "数字金融对企业创新投入的影响研究",
                    "authors": ["张三", "李四"],
                    "journal": "经济研究",
                    "year": 2021,
                    "volume": "56(3)",
                    "pages": "123-145",
                    "doi": "10.3969/j.issn.0577-9154.2021.03.006",
                },
                {
                    "paper_id": "CNKI-2021-002",
                    "title": "绿色信贷政策对重污染企业转型升级的影响",
                    "authors": ["王五", "赵六"],
                    "journal": "金融研究",
                    "year": 2021,
                    "volume": "48(5)",
                    "pages": "78-95",
                    "doi": "10.3969/j.issn.1002-2848.2021.05.005",
                },
                {
                    "paper_id": "CNKI-2022-001",
                    "title": "碳排放权交易机制对企业绿色创新的激励效应",
                    "authors": ["钱七", "孙八"],
                    "journal": "管理世界",
                    "year": 2022,
                    "volume": "38(8)",
                    "pages": "56-72",
                    "doi": "10.3969/j.issn.1002-5502.2022.08.004",
                },
            ],
            "note": "Sample data. Configure CNRDS_API_KEY at https://www.cnrds.com for real data.",
        }

    url = f"{BASE_URL}/paper/search"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params={k: v for k, v in params.items() if v is not None})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[CNRDS] Paper search failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


async def handle_get_cnrd_company(params: dict) -> dict:
    """Handle company query or return stub."""
    check = check_mock_permission(params, "get_cnrd_company", "user_cnrd")
    if check is not None:
        return check

    stock_code = params.get("stock_code", "")
    company_name = params.get("company_name", "")

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "stock_code": stock_code,
            "company_name": company_name or "样本科技有限公司",
            "established_date": "2010-03-15",
            "industry": "软件开发",
            "listing_date": "2018-06-20",
            "registered_capital": "50000万元",
            "employees": 5200,
            "chairman": "张三",
            "legal_representative": "张三",
            "note": "Sample company data. Configure CNRDS_API_KEY at https://www.cnrds.com for real data.",
        }

    url = f"{BASE_URL}/company/info"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[CNRDS] Company query failed: %s", e)
        return {"status": "error", "message": str(e), "data": {}}


async def handle_get_cnrd_financial(params: dict) -> dict:
    """Handle financial data query or return stub."""
    check = check_mock_permission(params, "get_cnrd_financial", "user_cnrd")
    if check is not None:
        return check

    stock_code = params.get("stock_code", "")
    year = params.get("year", 2024)

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "stock_code": stock_code,
            "year": year,
            "income_statement": {
                "revenue": 125000.5,
                "operating_cost": 85000.3,
                "operating_profit": 28000.2,
                "net_profit": 22000.8,
            },
            "balance_sheet": {
                "total_assets": 450000.0,
                "total_liabilities": 180000.0,
                "equity": 270000.0,
            },
            "cash_flow": {
                "operating_cash_flow": 35000.5,
                "investing_cash_flow": -15000.0,
                "financing_cash_flow": -8000.3,
            },
            "unit": "万元",
            "note": "Sample financial data. Configure CNRDS_API_KEY at https://www.cnrds.com for real data.",
        }

    url = f"{BASE_URL}/financial/statement"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params={k: v for k, v in params.items() if v is not None})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[CNRDS] Financial query failed: %s", e)
        return {"status": "error", "message": str(e), "data": {}}


# ─── MCP Server ────────────────────────────────────────────────────────────────


TOOL_HANDLERS = {
    "get_cnrd_patent": handle_get_cnrd_patent,
    "search_cnrd_papers": handle_search_cnrd_papers,
    "get_cnrd_company": handle_get_cnrd_company,
    "get_cnrd_financial": handle_get_cnrd_financial,
}


def create_server():
    server = Server("user-cnrd")

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
            _log.error("[CNRDS] Tool %s failed: %s", name, e)
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))]

    return server


async def main():
    """Entry point — wires async handlers to the MCP server and runs stdio transport."""
    print("user-cnrd MCP Server starting... (stub mode without API key)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-cnrd",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
