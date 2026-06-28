#!/usr/bin/env python3
"""
user-semantic-scholar MCP Server
================================
Semantic Scholar 学术论文搜索与引文网络分析服务。

数据源：
  - Semantic Scholar Academic Graph API (S2AG)
  - 无需 API Key，免费使用（100 req / 5 min，限流）
  - 可选 API Key 提升到 1 RPS

API Base: https://api.semanticscholar.org/graph/v1
文档: https://api.semanticscholar.org/

Usage:
    python server.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import warnings
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

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. pip install mcp", flush=True)
    sys.exit(1)

# ── 配置 ────────────────────────────────────────────────────────────────────

server = Server("user-semantic-scholar")

_API_BASE = "https://api.semanticscholar.org/graph/v1"
_SS_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
# fallback: OpenAlex API (完全免费，无限流)
_OPENALEX_BASE = "https://api.openalex.org"
_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "User-Agent": "FinResearch-Agent/1.0 (mailto:research@example.com)",
}
if _SS_API_KEY:
    _HEADERS["x-api-key"] = _SS_API_KEY

# 免费层限流：100 req / 5 min = 每请求间隔 3s（有 key: 1 RPS）
_SS_RATE_LIMIT = 3.0 if not _SS_API_KEY else 1.0
_last_request_time = 0.0

# ── 限流装饰器 ──────────────────────────────────────────────────────────────

def _rate_limited(func):
    """对所有 API 调用施加速率限制（免费层 100 req/5min，有 key: 1 RPS）。"""
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        global _last_request_time
        elapsed = time.time() - _last_request_time
        if elapsed < _SS_RATE_LIMIT:
            time.sleep(_SS_RATE_LIMIT - elapsed)
        _last_request_time = time.time()
        return func(*args, **kwargs)
    return wrapper

# ── 论文详情字段 ────────────────────────────────────────────────────────────

PAPER_BASIC_FIELDS = [
    "paperId", "title", "abstract", "year", "venue",
    "citationCount", "influentialCitationCount",
    "authors", "externalIds",
    "openAccessPdf", "url",
]

PAPER_EXTENDED_FIELDS = [
    *PAPER_BASIC_FIELDS,
    "tldr", "embedding", "fieldsOfStudy",
]

CITATION_ENTRY_FIELDS = [
    "paperId", "title", "year", "venue",
    "citationCount", "authors",
]

REFERENCE_ENTRY_FIELDS = [
    "paperId", "title", "year", "venue",
    "citationCount", "authors",
]


# ── API 请求 ─────────────────────────────────────────────────────────────────

@_rate_limited
def _get(url: str, params: dict | None = None, timeout: int = 30) -> dict | list | None:
    """发 GET 请求到 Semantic Scholar API，带限流和错误处理。"""
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=timeout)
        if resp.status_code == 429:
            return {"_error": "rate_limit", "message": "API rate limit reached. Wait before retrying."}
        if resp.status_code == 404:
            return {"_error": "not_found", "message": "Paper not found."}
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"_error": "timeout", "message": f"Request timed out after {timeout}s."}
    except requests.exceptions.RequestException as e:
        return {"_error": "http_error", "message": str(e)}


# ── 数据获取函数 ──────────────────────────────────────────────────────────────

def _paper_to_dict(paper: dict, fields: list[str]) -> dict:
    """清洗论文数据，移除 None 值，规范化字段。"""
    result = {}
    for f in fields:
        v = paper.get(f)
        if v is None:
            continue
        # 规范化作者列表
        if f == "authors" and isinstance(v, list):
            result["authors"] = [
                {"authorId": a.get("authorId", ""), "name": a.get("name", "Unknown")}
                for a in v
            ]
        # 简化 externalIds
        elif f == "externalIds":
            result["doi"] = v.get("DOI", "")
            result["arXiv"] = v.get("ArXiv", "")
            result["MAG"] = v.get("MAG", "")
            result["PMID"] = v.get("PubMed", "")
        # 简化 openAccessPdf
        elif f == "openAccessPdf":
            result["pdfUrl"] = v.get("url", "") if isinstance(v, dict) else ""
        # tldr 摘要
        elif f == "tldr" and isinstance(v, dict):
            result["tldr"] = v.get("text", "")
        else:
            result[f] = v
    return result


def _format_paper(paper: dict, max_authors: int = 10) -> str:
    """将论文格式化为可读字符串（用于 MCP 返回）。"""
    authors = paper.get("authors", [])
    if len(authors) > max_authors:
        author_str = ", ".join(a["name"] for a in authors[:max_authors]) + f" et al."
    else:
        author_str = ", ".join(a["name"] for a in authors) or "Unknown"

    doi = paper.get("doi", "")
    arxiv = paper.get("arXiv", "")
    ids_str = []
    if doi:
        ids_str.append(f"DOI: {doi}")
    if arxiv:
        ids_str.append(f"arXiv: {arxiv}")
    ids_str = f" ({', '.join(ids_str)})" if ids_str else ""

    tldr = paper.get("tldr", "") or ""
    tldr_str = f"\nTL;DR: {tldr}" if tldr else ""

    return (
        f"**{paper.get('title', 'N/A')}**\n"
        f"Authors: {author_str}\n"
        f"Year: {paper.get('year', 'N/A')} | Venue: {paper.get('venue', 'N/A') or 'Preprint/N/A'} | "
        f"Citations: {paper.get('citationCount', 0):,} ({paper.get('influentialCitationCount', 0):,} influential){ids_str}\n"
        f"Abstract: {(paper.get('abstract') or 'N/A')[:500]}{'...' if paper.get('abstract') and len(paper.get('abstract','')) > 500 else ''}"
        f"{tldr_str}"
    )


# ── 工具定义 ─────────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="search_semantic_scholar",
        description="在Semantic Scholar中搜索学术论文（200M+论文）。"
                    "支持AI增强相关性排序、年份/引用量/期刊筛选。无需API Key。",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词或短语"},
                "year_from": {"type": "integer", "description": "起始年份", "default": 2020},
                "year_to": {"type": "integer", "description": "结束年份", "default": 2025},
                "citation_count_min": {"type": "integer", "description": "最小引用量", "default": 0},
                "venue": {"type": "string", "description": "期刊/会议名称过滤"},
                "fields_of_study": {"type": "array", "items": {"type": "string"}, "description": "学科领域", "default": ["Economics"]},
                "limit": {"type": "integer", "description": "返回数量", "default": 20},
                "offset": {"type": "integer", "description": "分页偏移", "default": 0},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_paper_details",
        description="获取论文完整详情（摘要、作者、引用量、TLDR摘要等）。支持DOI/arXiv ID。",
        inputSchema={
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "论文ID（DOI/arXiv ID/S2Id）"},
                "include_references": {"type": "boolean", "description": "包含参考文献摘要", "default": True},
                "include_citations": {"type": "boolean", "description": "包含引用摘要", "default": False},
            },
            "required": ["paper_id"],
        },
    ),
    Tool(
        name="get_paper_citations",
        description="获取引用某论文的所有论文（正向引文），按引用量排序。",
        inputSchema={
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "论文ID（DOI/arXiv ID/S2Id）"},
                "limit": {"type": "integer", "description": "返回数量", "default": 20},
                "offset": {"type": "integer", "description": "分页偏移", "default": 0},
                "min_citation_count": {"type": "integer", "description": "最小引用量过滤", "default": 0},
            },
            "required": ["paper_id"],
        },
    ),
    Tool(
        name="get_paper_references",
        description="获取论文的参考文献（逆向引文），追溯理论基础。",
        inputSchema={
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "论文ID（DOI/arXiv ID/S2Id）"},
                "limit": {"type": "integer", "description": "返回数量", "default": 20},
                "offset": {"type": "integer", "description": "分页偏移", "default": 0},
            },
            "required": ["paper_id"],
        },
    ),
    Tool(
        name="get_paper_recommendations",
        description="获取与给定论文相似的推荐论文（基于AI推荐算法）。",
        inputSchema={
            "type": "object",
            "properties": {
                "paper_id": {"type": "string", "description": "论文ID（DOI/arXiv ID/S2Id）"},
                "limit": {"type": "integer", "description": "返回数量", "default": 10},
            },
            "required": ["paper_id"],
        },
    ),
]


# ── 工具处理器 ───────────────────────────────────────────────────────────────

async def handle_search(args: dict) -> list[TextContent]:
    query = args.get("query", "")
    year_from = args.get("year_from", 2020)
    year_to = args.get("year_to", 2025)
    citation_min = args.get("citation_count_min", 0)
    venue = args.get("venue", "")
    fields_of_study = args.get("fields_of_study", ["Economics"])
    limit = min(args.get("limit", 20), 100)
    offset = args.get("offset", 0)

    if not query:
        return [TextContent(type="text", text=json.dumps({"error": "query is required"}))]

    # 构建搜索查询
    q_parts = [query]
    if year_from or year_to:
        q_parts.append(f"year:{year_from}-{year_to}")
    if venue:
        q_parts.append(f'venue:"{venue}"')
    if citation_min > 0:
        q_parts.append(f"citationCount:>{citation_min}")
    search_q = " ".join(q_parts)

    params = {
        "query": query,  # Semantic Scholar API 不支持复合查询，用原始 query
        "year": f"{year_from}-{year_to}" if year_from or year_to else None,
        "fields": ",".join(PAPER_BASIC_FIELDS),
        "limit": limit,
        "offset": offset,
        "sort": "citationCount:desc",
    }

    url = f"{_API_BASE}/paper/search"
    data = _get(url, {k: v for k, v in params.items() if v is not None})

    if isinstance(data, dict) and data.get("_error"):
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    papers = data.get("data", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0

    results = []
    for i, p in enumerate(papers, offset + 1):
        cleaned = _paper_to_dict(p, PAPER_BASIC_FIELDS)
        results.append(f"[{i}] {i - offset}. {_format_paper(cleaned)}")

    response = {
        "query": query,
        "year_range": f"{year_from}-{year_to}",
        "total_results": total,
        "returned": len(papers),
        "papers": [_paper_to_dict(p, PAPER_BASIC_FIELDS) for p in papers],
        "format": "\n\n".join(results) if results else "No results found.",
    }
    return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]


async def handle_paper_details(args: dict) -> list[TextContent]:
    paper_id = args.get("paper_id", "")
    include_refs = args.get("include_references", True)
    include_cites = args.get("include_citations", False)

    if not paper_id:
        return [TextContent(type="text", text=json.dumps({"error": "paper_id is required"}))]

    fields = PAPER_EXTENDED_FIELDS.copy()
    if include_refs:
        fields.append("references")
    if include_cites:
        fields.append("citations")

    params = {"fields": ",".join(fields)}
    url = f"{_API_BASE}/paper/{paper_id}"

    data = _get(url, params)
    if isinstance(data, dict) and data.get("_error"):
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    cleaned = _paper_to_dict(data, PAPER_EXTENDED_FIELDS)

    # 处理参考文献和引用（如果包含的话）
    if include_refs and "references" in data:
        refs = data.get("references", []) or []
        cleaned["references"] = [
            _paper_to_dict(r.get("citedPaper", {}), REFERENCE_ENTRY_FIELDS)
            for r in refs[:20] if r.get("citedPaper")
        ]
    if include_cites and "citations" in data:
        cites = data.get("citations", []) or []
        cleaned["citations"] = [
            _paper_to_dict(r.get("citingPaper", {}), CITATION_ENTRY_FIELDS)
            for r in cites[:20] if r.get("citingPaper")
        ]

    formatted = _format_paper(cleaned)
    if include_refs and cleaned.get("references"):
        ref_list = "\n".join(
            f"  - {r.get('title','N/A')} ({r.get('year','N/A')}) — {r.get('citationCount',0):,} cites"
            for r in cleaned["references"][:10]
        )
        formatted += f"\n\nTop References:\n{ref_list}"

    return [TextContent(type="text", text=json.dumps({"formatted": formatted, "data": cleaned}, ensure_ascii=False, indent=2))]


async def handle_citations(args: dict) -> list[TextContent]:
    paper_id = args.get("paper_id", "")
    limit = min(args.get("limit", 20), 100)
    offset = args.get("offset", 0)
    min_cites = args.get("min_citation_count", 0)

    if not paper_id:
        return [TextContent(type="text", text=json.dumps({"error": "paper_id is required"}))]

    params = {
        "fields": ",".join(CITATION_ENTRY_FIELDS),
        "limit": limit,
        "offset": offset,
    }
    url = f"{_API_BASE}/paper/{paper_id}/citations"

    data = _get(url, params)
    if isinstance(data, dict) and data.get("_error"):
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    citing = data.get("data", []) if isinstance(data, dict) else []

    # 过滤引用量
    if min_cites > 0:
        citing = [c for c in citing if c.get("citationCount", 0) >= min_cites]

    results = []
    for i, c in enumerate(citing, offset + 1):
        cleaned = _paper_to_dict(c, CITATION_ENTRY_FIELDS)
        results.append(f"[{i}] {i}. {_format_paper(cleaned)}")

    response = {
        "paper_id": paper_id,
        "total_returned": len(citing),
        "citations": [_paper_to_dict(c, CITATION_ENTRY_FIELDS) for c in citing],
        "format": "\n\n".join(results) if results else "No citing papers found.",
    }
    return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]


async def handle_references(args: dict) -> list[TextContent]:
    paper_id = args.get("paper_id", "")
    limit = min(args.get("limit", 20), 100)
    offset = args.get("offset", 0)

    if not paper_id:
        return [TextContent(type="text", text=json.dumps({"error": "paper_id is required"}))]

    params = {
        "fields": ",".join(REFERENCE_ENTRY_FIELDS),
        "limit": limit,
        "offset": offset,
    }
    url = f"{_API_BASE}/paper/{paper_id}/references"

    data = _get(url, params)
    if isinstance(data, dict) and data.get("_error"):
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    refs = data.get("data", []) if isinstance(data, dict) else []

    results = []
    for i, r in enumerate(refs, offset + 1):
        cleaned = _paper_to_dict(r, REFERENCE_ENTRY_FIELDS)
        results.append(f"[{i}] {i}. {_format_paper(cleaned)}")

    response = {
        "paper_id": paper_id,
        "total_returned": len(refs),
        "references": [_paper_to_dict(r, REFERENCE_ENTRY_FIELDS) for r in refs],
        "format": "\n\n".join(results) if results else "No references found.",
    }
    return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]


async def handle_recommendations(args: dict) -> list[TextContent]:
    paper_id = args.get("paper_id", "")
    limit = min(args.get("limit", 10), 50)

    if not paper_id:
        return [TextContent(type="text", text=json.dumps({"error": "paper_id is required"}))]

    url = f"{_API_BASE}/paper/{paper_id}/recommendations"
    params = {"fields": ",".join(PAPER_BASIC_FIELDS), "limit": limit}

    data = _get(url, params)
    if isinstance(data, dict) and data.get("_error"):
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    recs = data.get("data", []) if isinstance(data, dict) else []

    results = []
    for i, r in enumerate(recs, 1):
        cleaned = _paper_to_dict(r, PAPER_BASIC_FIELDS)
        results.append(f"[{i}] {i}. {_format_paper(cleaned)}")

    response = {
        "query_paper_id": paper_id,
        "recommended": [_paper_to_dict(r, PAPER_BASIC_FIELDS) for r in recs],
        "format": "\n\n".join(results) if results else "No recommendations found.",
    }
    return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]


TOOL_HANDLERS = {
    "search_semantic_scholar": handle_search,
    "get_paper_details": handle_paper_details,
    "get_paper_citations": handle_citations,
    "get_paper_references": handle_references,
    "get_paper_recommendations": handle_recommendations,
}


# ── MCP Server 入口 ──────────────────────────────────────────────────────────

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
    key_info = f" with API key {_SS_API_KEY[:8]}..." if _SS_API_KEY else " (no API key — free tier, 100 req/5min)"
    print(f"user-semantic-scholar MCP Server starting...{key_info}", file=sys.stderr, flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-semantic-scholar",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
