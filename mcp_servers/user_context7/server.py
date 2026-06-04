"""Context7 — 学术文献全文获取 MCP Server.

支持通过 ArXiv ID、DOI 或关键词检索获取论文PDF全文内容。
数据来源：Context7 API (https://context7.com)
注意：api.context7.com 在中国大陆需要VPN才能访问。
备选方案：通过 ArXiv API 直接检索摘要。
"""

from __future__ import annotations

import json
import re
import logging
from typing import Any

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
except ImportError:
    import warnings
    warnings.warn("mcp library not installed. Install with: pip install mcp")
    raise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("context7")

APP_NAME = "context7-mcp"
APP_VERSION = "1.0.0"
server = Server(APP_NAME)


def _json_response(data: dict, status: str = "success") -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({**data, "status": status}, ensure_ascii=False, indent=2))]


def _error_response(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"status": "error", "message": message}, ensure_ascii=False, indent=2))]


# ── Tool Handlers ──────────────────────────────────────────────────────────────


async def handle_get_by_arxiv(args: dict) -> list[TextContent]:
    """Get paper metadata + abstract by ArXiv ID."""
    arxiv_id = args.get("arxiv_id", "").strip()
    if not arxiv_id:
        return _error_response("arxiv_id is required")

    try:
        import requests
        clean_id = re.sub(r"v\d+$", "", arxiv_id).rstrip(".")
        url = f"https://export.arxiv.org/api/query?id_list={clean_id}"

        resp = requests.get(url, timeout=20)
        resp.raise_for_status()

        entry_match = re.search(r"<entry>(.*?)</entry>", resp.text, re.DOTALL)
        if not entry_match:
            return _error_response(f"ArXiv paper not found: {arxiv_id}")

        entry = entry_match.group(1)
        title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        authors = re.findall(r"<name>(.*?)</name>", entry)
        published = re.search(r"<published>(.*?)</published>", entry)
        updated = re.search(r"<updated>(.*?)</updated>", entry)
        abstract_link = re.search(r"<id>(https://arxiv\.org/abs/[^<]+)</id>", entry)

        result = {
            "arxiv_id": clean_id,
            "title": title.group(1).strip().replace("\n", " ") if title else "Unknown",
            "authors": authors[:10],
            "abstract": summary.group(1).strip() if summary else "",
            "published": published.group(1)[:10] if published else "",
            "updated": updated.group(1)[:10] if updated else "",
            "abstract_url": abstract_link.group(1) if abstract_link else f"https://arxiv.org/abs/{clean_id}",
            "pdf_url": f"https://arxiv.org/pdf/{clean_id}.pdf",
            "note": "api.context7.com 需要VPN访问。此处通过ArXiv API返回元数据。全文请访问PDF链接。"
        }
        return _json_response(result)

    except requests.exceptions.Timeout:
        return _error_response(f"ArXiv API timeout for {arxiv_id}")
    except Exception as e:
        logger.warning(f"[Context7] get_by_arxiv error: {e}")
        return _error_response(f"Failed to fetch ArXiv paper {arxiv_id}: {e}")


async def handle_get_by_doi(args: dict) -> list[TextContent]:
    """Get paper metadata by DOI (via Crossref)."""
    doi = args.get("doi", "").strip()
    if not doi:
        return _error_response("doi is required")

    try:
        import requests
        url = f"https://api.crossref.org/works/{doi}"
        headers = {"Accept": "application/json", "User-Agent": "FinResearch/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("message", {})

        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in data.get("author", [])
        ]
        links = data.get("link", [])
        arxiv_link = next((l["URL"] for l in links if "arxiv.org" in l.get("URL", "")), None)

        result = {
            "doi": doi,
            "title": data.get("title", [""])[0] if data.get("title") else "Unknown",
            "authors": authors[:10],
            "journal": data.get("container-title", [""])[0] if data.get("container-title") else "",
            "year": data.get("published-print", {}).get("date-parts", [[0]])[0][0] if data.get("published-print") else None,
            "arxiv_url": arxiv_link,
            "open_access": data.get("is-open-access", False),
            "cited_by_count": data.get("is-referenced-by-count", 0),
        }
        return _json_response(result)

    except Exception as e:
        logger.warning(f"[Context7] get_by_doi error: {e}")
        return _error_response(f"Failed to fetch DOI {doi}: {e}")


async def handle_get_by_query(args: dict) -> list[TextContent]:
    """Search ArXiv by keyword and return paper metadata."""
    query = args.get("query", "").strip()
    max_results = min(int(args.get("max_results", 5)), 20)
    if not query:
        return _error_response("query is required")

    try:
        import requests
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
        }
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()

        entries = re.findall(r"<entry>(.*?)</entry>", resp.text, re.DOTALL)
        results = []
        for entry in entries:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            authors = re.findall(r"<name>(.*?)</name>", entry)
            published = re.search(r"<published>(.*?)</published>", entry)
            abstract_url = re.search(r"<id>(https://arxiv\.org/abs/[^<]+)</id>", entry)
            arxiv_id = ""
            if abstract_url:
                abs_url = abstract_url.group(1)
                arxiv_id = abs_url.replace("https://arxiv.org/abs/", "")

            results.append({
                "arxiv_id": arxiv_id,
                "title": title.group(1).strip().replace("\n", " ") if title else "Unknown",
                "authors": authors[:5],
                "abstract": summary.group(1).strip()[:300] + "..." if summary else "",
                "published": published.group(1)[:10] if published else "",
                "url": abstract_url.group(1) if abstract_url else "",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "",
            })

        return _json_response({"query": query, "count": len(results), "papers": results})

    except Exception as e:
        logger.warning(f"[Context7] get_by_query error: {e}")
        return _error_response(f"Search failed: {e}")


# ── Server Setup ───────────────────────────────────────────────────────────────


TOOLS = [
    Tool(
        name="get_context7_by_arxiv",
        description="通过 ArXiv ID 获取论文元数据与摘要（附PDF链接）",
        inputSchema={
            "type": "object",
            "properties": {
                "arxiv_id": {
                    "type": "string",
                    "description": "ArXiv 论文 ID，例如 '2301.12345' 或 '2301.12345v2'"
                }
            },
            "required": ["arxiv_id"]
        }
    ),
    Tool(
        name="get_context7_by_doi",
        description="通过 DOI 获取论文元数据",
        inputSchema={
            "type": "object",
            "properties": {
                "doi": {
                    "type": "string",
                    "description": "论文 DOI，例如 '10.1038/nature12373'"
                }
            },
            "required": ["doi"]
        }
    ),
    Tool(
        name="get_context7_by_query",
        description="通过关键词查询 ArXiv 论文",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "max_results": {"type": "integer", "description": "最大返回数量", "default": 5}
            },
            "required": ["query"]
        }
    ),
]

TOOL_HANDLERS = {
    "get_context7_by_arxiv": handle_get_by_arxiv,
    "get_context7_by_doi": handle_get_by_doi,
    "get_context7_by_query": handle_get_by_query,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return _error_response(f"Unknown tool: {name}")
    return await handler(arguments)


async def main():
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
