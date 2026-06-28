#!/usr/bin/env python3
"""SIPO MCP Server — 国家知识产权局专利数据

API文档: https://cpquery.cponline.cnipa.gov.cn
注册: https://cponline.cnipa.gov.cn

数据覆盖:
  - 专利基本信息（申请号、公开号、申请人、发明人）
  - 专利法律状态（有效、失效、审中）
  - 专利引文信息
  - 专利质押、许可、转让记录
  - 专利诉讼关联数据

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
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import os
API_KEY = os.environ.get("SIPO_API_KEY", "")
USERNAME = os.environ.get("SIPO_USERNAME", "")
BASE_URL = "https://cpquery.cponline.cnipa.gov.cn"

TOOLS: list[Tool] = [
    Tool(
        name="search_sipo_patent",
        description="按关键词、申请人、发明人检索中国专利数据库。覆盖发明专利、实用新型、外观设计。支持IPC分类号过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "关键词（专利名称/摘要中的词）"},
                "applicant": {"type": "string", "description": "申请人/权利人名称"},
                "inventor": {"type": "string", "description": "发明人"},
                "ipc_code": {"type": "string", "description": "IPC国际专利分类号（如H01M）"},
                "patent_type": {"type": "string", "enum": ["发明", "实用新型", "外观设计", "all"], "default": "all"},
                "date_from": {"type": "string", "description": "申请日期起（YYYY-MM-DD）"},
                "date_to": {"type": "string", "description": "申请日期止（YYYY-MM-DD）"},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
            },
        },
    ),
    Tool(
        name="get_patent_detail",
        description="获取指定专利的详细信息，包括摘要、权利要求书要点、附图说明。",
        inputSchema={
            "type": "object",
            "properties": {
                "patent_number": {"type": "string", "description": "专利号（如CN202110123456.7）"},
                "include_claims": {"type": "boolean", "default": False, "description": "是否包含权利要求"},
            },
        },
    ),
    Tool(
        name="get_patent_bibliographic",
        description="获取专利著录项目信息（申请人、发明人、IPC分类、申请日期、优先权等）。",
        inputSchema={
            "type": "object",
            "properties": {
                "patent_number": {"type": "string", "description": "专利号"},
            },
        },
    ),
    Tool(
        name="get_patent_litigation",
        description="查询专利相关的诉讼案件、质押记录、许可记录、转让记录。",
        inputSchema={
            "type": "object",
            "properties": {
                "patent_number": {"type": "string", "description": "专利号"},
                "record_type": {"type": "string", "enum": ["诉讼", "质押", "许可", "转让", "all"], "default": "all"},
            },
        },
    ),
]


async def handle_search(params: dict) -> dict:
    """Search patents from SIPO or return stub data."""
    check = check_mock_permission(params, "search_sipo_patent", "user_sipo")
    if check is not None:
        return check

    keyword = params.get("keyword", "")
    applicant = params.get("applicant", "")
    page = params.get("page", 1)
    page_size = params.get("page_size", 20)

    if not API_KEY and not USERNAME:
        return {
            "status": "stub",
            "_stub": True,
            "message": "SIPO API not configured. Returning sample data.",
            "query": {"keyword": keyword, "applicant": applicant, "page": page, "page_size": page_size},
            "total_results": 3,
            "patents": [
                {
                    "patent_number": "CN202110123456.7",
                    "title": "一种基于深度学习的风险管理方法及系统",
                    "applicant": "清华大学",
                    "inventor": "张三, 李四",
                    "patent_type": "发明",
                    "application_date": "2021-03-15",
                    "ipc_code": "G06Q40/06",
                    "status": "有效",
                    "abstract": "本发明公开了一种基于深度学习的风险管理方法及系统...",
                },
                {
                    "patent_number": "CN202110789012.3",
                    "title": "智能投顾系统的用户画像构建方法",
                    "applicant": "蚂蚁科技集团股份有限公司",
                    "inventor": "王五, 赵六",
                    "patent_type": "发明",
                    "application_date": "2021-07-20",
                    "ipc_code": "G06N3/08",
                    "status": "有效",
                    "abstract": "本发明涉及人工智能技术领域，尤其涉及一种智能投顾系统...",
                },
                {
                    "patent_number": "CN202220123456.1",
                    "title": "一种金融数据处理装置",
                    "applicant": "深圳证券交易所",
                    "inventor": "钱七",
                    "patent_type": "实用新型",
                    "application_date": "2022-01-10",
                    "ipc_code": "G06F16/25",
                    "status": "有效",
                    "abstract": "本实用新型公开了一种金融数据处理装置...",
                },
            ],
            "fallback": "Configure SIPO_API_KEY at https://cpquery.cponline.cnipa.gov.cn for real data",
        }

    if not HAS_REQUESTS:
        _log.warning("[SIPO] requests not installed, using stub")
        return {"status": "stub", "_stub": True, "message": "requests not installed"}

    try:
        import httpx
        url = f"{BASE_URL}/api/search"
        headers = {}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            resp = await client.get(url, params={k: v for k, v in params.items() if v is not None})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[SIPO] Search failed: %s", e)
        return {"status": "error", "message": str(e), "data": []}


async def handle_detail(params: dict) -> dict:
    """Get patent detail from SIPO or return stub data."""
    check = check_mock_permission(params, "get_patent_detail", "user_sipo")
    if check is not None:
        return check

    patent_number = params.get("patent_number", "")
    include_claims = params.get("include_claims", False)

    if not API_KEY and not USERNAME:
        return {
            "status": "stub",
            "_stub": True,
            "patent_number": patent_number,
            "title": "一种基于深度学习的风险管理方法及系统",
            "applicant": "清华大学",
            "inventor": ["张三", "李四"],
            "patent_type": "发明",
            "application_number": "202110123456.7",
            "publication_number": "CN113366987A",
            "application_date": "2021-03-15",
            "ipc_code": "G06Q40/06",
            "status": "有效",
            "abstract": "本发明公开了一种基于深度学习的风险管理方法及系统。该方法包括：获取用户的历史交易数据；构建深度学习风险评估模型；对用户的风险等级进行预测；根据预测结果生成风险管理建议。本发明能够提高风险管理的准确性和效率。",
            "claims": ["1. 一种基于深度学习的风险管理方法，其特征在于，包括：..."] if include_claims else [],
            "figures": ["图1 系统架构图", "图2 流程图"],
            "legal_status": "专利权有效",
        }

    if not HAS_REQUESTS:
        return {"status": "stub", "_stub": True, "message": "requests not installed"}

    try:
        import httpx
        url = f"{BASE_URL}/api/detail"
        headers = {}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _log.warning("[SIPO] Detail failed: %s", e)
        return {"status": "error", "message": str(e), "data": {}}


async def handle_bibliographic(params: dict) -> dict:
    """Get patent bibliographic info."""
    check = check_mock_permission(params, "get_patent_bibliographic", "user_sipo")
    if check is not None:
        return check

    patent_number = params.get("patent_number", "")
    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "patent_number": patent_number,
            "applicant": "清华大学",
            "inventor": ["张三", "李四"],
            "ipc_code": "G06Q40/06",
            "application_date": "2021-03-15",
            "publication_date": "2021-09-10",
            "priority": None,
        }
    return await handle_detail({**params, "mode": "bibliographic"})


async def handle_litigation(params: dict) -> dict:
    """Get patent litigation records."""
    check = check_mock_permission(params, "get_patent_litigation", "user_sipo")
    if check is not None:
        return check

    patent_number = params.get("patent_number", "")
    record_type = params.get("record_type", "all")

    if not API_KEY:
        return {
            "status": "stub",
            "_stub": True,
            "patent_number": patent_number,
            "litigation_records": [],
            "pledge_records": [],
            "license_records": [],
            "transfer_records": [],
            "message": "No litigation/transfer records found in stub data",
        }
    return await handle_detail({**params, "mode": "litigation"})


TOOL_HANDLERS = {
    "search_sipo_patent": handle_search,
    "get_patent_detail": handle_detail,
    "get_patent_bibliographic": handle_bibliographic,
    "get_patent_litigation": handle_litigation,
}


def create_server():
    server = Server("user-sipo")

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
            _log.error("[SIPO] Tool %s failed: %s", name, e)
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))]

    return server


async def main():
    print("user-sipo MCP Server starting... (SIPO, stub mode without API key)", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-sipo",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
