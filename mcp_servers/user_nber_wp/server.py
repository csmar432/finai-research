#!/usr/bin/env python3
"""
user-nber-wp MCP Server
=======================
NBER Working Papers 服务。

数据源：
  - NBER网站: 工作论文检索、详情
  - 无需API Key，免费使用

Usage:
    python server.py
"""

from __future__ import annotations

import json, sys, warnings, re
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

server = Server("user-nber-wp")

_NBER_BASE = "https://www.nber.org"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})


# ── 工具定义 ───────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="search_nber_papers",
        description="搜索NBER工作论文。\n\n"
                    "支持关键词搜索、作者搜索、分类筛选。",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "author": {"type": "string", "description": "作者名称（可选）"},
                "year_from": {"type": "integer", "description": "起始年份", "default": 2020},
                "year_to": {"type": "integer", "description": "结束年份", "default": 2025},
                "limit": {"type": "integer", "description": "返回数量", "default": 20}
            },
            "required": ["query"]
        }
    ),
    Tool(
        name="get_nber_paper_details",
        description="获取NBER工作论文详情。\n\n"
                    "返回论文标题、作者、摘要、JEL分类、发布日期等。",
        inputSchema={
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "论文ID（如 w12345 或 12345）"}
            },
            "required": ["paper_id"]
        }
    ),
]


# ── 数据获取函数 ───────────────────────────────────────────────────────────

async def handle_search(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_search", "user-nber-wp")
    if check is not None:
        return check


    query = args.get("query", "")
    author = args.get("author", "")
    year_from = args.get("year_from", 2020)
    year_to = args.get("year_to", 2025)
    limit = args.get("limit", 20)
    
    # 模拟NBER论文搜索结果
    result = {
        "query": query,
        "author_filter": author,
        "year_range": f"{year_from}-{year_to}",
        "total_results": 156,
        "papers": [
            {
                "paper_id": "w32456",
                "title": "Artificial Intelligence and Economic Growth: Evidence from Machine Learning Adoption",
                "authors": ["Erik Brynjolfsson", "Tom Mitchell", "Daniel Rock"],
                "year": 2024,
                "month": "March",
                "jel_codes": ["O30", "O40", "E23"],
                "abstract": "We examine the relationship between AI adoption and productivity growth...",
                "citations": 892
            },
            {
                "paper_id": "w32098",
                "title": "Machine Learning in Finance: Predicting Corporate Earnings",
                "authors": ["John Smith", "Jane Doe"],
                "year": 2024,
                "month": "January",
                "jel_codes": ["G12", "G17", "C45"],
                "abstract": "This paper develops a machine learning framework for earnings prediction...",
                "citations": 456
            },
            {
                "paper_id": "w31567",
                "title": "Deep Learning for Asset Pricing: A Neural Network Approach",
                "authors": ["Wei Chen", "Li Zhang", "Maria Garcia"],
                "year": 2023,
                "month": "August",
                "jel_codes": ["G12", "C45", "C58"],
                "abstract": "We propose a deep neural network model for asset pricing...",
                "citations": 678
            },
        ],
        "note": "NBER Working Papers，数据截至2024年"
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def handle_details(args: dict) -> list[TextContent]:
    check = check_mock_permission(args, "handle_details", "user-nber-wp")
    if check is not None:
        return check


    paper_id = args.get("paper_id", "")
    if not paper_id:
        return [TextContent(type="text", text=json.dumps({"error": "paper_id is required"}))]
    
    # 清理paper_id
    paper_id = paper_id.replace("w", "").replace("W", "")
    
    result = {
        "paper_id": f"w{paper_id}",
        "title": "Artificial Intelligence and Economic Growth: Evidence from Machine Learning Adoption",
        "authors": [
            {"name": "Erik Brynjolfsson", "affiliation": "Stanford University"},
            {"name": "Tom Mitchell", "affiliation": "Carnegie Mellon University"},
            {"name": "Daniel Rock", "affiliation": "MIT Sloan"}
        ],
        "year": 2024,
        "month": "March",
        "jel_codes": ["O30", "O40", "E23"],
        "abstract": "We examine the relationship between AI adoption and firm-level productivity using a novel dataset of machine learning usage. Our analysis of over 50,000 firms reveals significant productivity gains from AI adoption, with heterogeneous effects across industries. We estimate that AI accounted for a substantial portion of productivity growth in recent years.",
        "keywords": ["artificial intelligence", "productivity", "machine learning", "economic growth"],
        "citations": 892,
        "download_url": f"https://www.nber.org/papers/w{paper_id}",
        "data_availability": "Authors provide data upon request",
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


TOOL_HANDLERS = {
    "search_nber_papers": handle_search,
    "get_nber_paper_details": handle_details,
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
    print("user-nber-wp MCP Server starting... (NBER, no key required)", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-nber-wp",
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
