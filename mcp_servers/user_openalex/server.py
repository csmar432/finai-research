"""OpenAlex MCP Server — 学术文献元数据.

数据来源：OpenAlex API (https://api.openalex.org)
覆盖：2亿+学术论文、作者、机构、期刊数据。
无需API Key，完全免费。
"""

from __future__ import annotations

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
logger = logging.getLogger("openalex-mcp")

APP_NAME = "openalex-mcp"
APP_VERSION = "1.0.0"
BASE_URL = "https://api.openalex.org"
server = Server(APP_NAME)


def _safe_json_response(data: Any, error: str | None = None) -> list[TextContent]:
    import json
    if error:
        return [TextContent(type="text", text=f"Error: {error}")]
    try:
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]
    except Exception:
        return [TextContent(type="text", text=str(data))]


def _clean_work(work: dict) -> dict:
    """Extract relevant fields from OpenAlex work record."""
    return {
        "id": work.get("id", "").replace("https://openalex.org/", ""),
        "title": work.get("title", ""),
        "abstract": (work.get("abstract_inverted_index") or {}) ,
        "authors": [
            {"name": a.get("display_name"), "id": a.get("id", "").replace("https://openalex.org/", "")}
            for a in (work.get("authorships", [])[:8])
        ],
        "year": work.get("publication_year"),
        "doi": work.get("doi", ""),
        "source": work.get("primary_location", {}).get("source", {}).get("display_name", ""),
        "cited_by_count": work.get("cited_by_count", 0),
        "concepts": [
            {"name": c.get("display_name"), "score": c.get("score")}
            for c in (work.get("concepts", [])[:5])
        ],
        "open_access": work.get("open_access", {}).get("is_oa", False),
        "url": work.get("doi", ""),
    }


# ── Tool Handlers ──────────────────────────────────────────────────────────────


async def handle_get_works(args: dict) -> list[TextContent]:
    query = args.get("query", "").strip()
    per_page = min(int(args.get("per_page", 25)), 100)
    if not query:
        return _safe_json_response(None, "query is required")

    try:
        import requests
        params = {
            "search": query,
            "per-page": per_page,
            "sort": "relevance_score:desc",
        }
        resp = requests.get(f"{BASE_URL}/works", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        results = [_clean_work(w) for w in data.get("results", [])]
        meta = {
            "query": query,
            "total_count": data.get("meta", {}).get("count", 0),
            "returned": len(results),
        }
        return _safe_json_response({"meta": meta, "works": results})
    except Exception as e:
        logger.warning(f"[OpenAlex] get_works error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_author(args: dict) -> list[TextContent]:
    author_id = args.get("author_id", "").strip()
    if not author_id:
        return _safe_json_response(None, "author_id is required")

    try:
        import requests
        clean_id = author_id.replace("https://openalex.org/", "")
        resp = requests.get(f"{BASE_URL}/authors/{clean_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = {
            "id": data.get("id", "").replace("https://openalex.org/", ""),
            "name": data.get("display_name"),
            "orcid": data.get("orcid", ""),
            "institutions": [
                i.get("display_name") for i in (data.get("last_known_institutions", []))
            ],
            "works_count": data.get("works_count", 0),
            "cited_by_count": data.get("cited_by_count", 0),
            "topics": [
                {"name": t.get("display_name"), "score": t.get("score")}
                for t in (data.get("topics", [])[:5])
            ],
        }
        return _safe_json_response(result)
    except Exception as e:
        logger.warning(f"[OpenAlex] get_author error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_institution(args: dict) -> list[TextContent]:
    inst_id = args.get("institution_id", "").strip()
    if not inst_id:
        return _safe_json_response(None, "institution_id is required")

    try:
        import requests
        clean_id = inst_id.replace("https://openalex.org/", "")
        resp = requests.get(f"{BASE_URL}/institutions/{clean_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = {
            "id": data.get("id", "").replace("https://openalex.org/", ""),
            "name": data.get("display_name"),
            "country": data.get("country_code"),
            "type": data.get("type"),
            "works_count": data.get("works_count", 0),
            "cited_by_count": data.get("cited_by_count", 0),
            "topics": [
                {"name": t.get("display_name"), "works_count": t.get("works_count")}
                for t in (data.get("topics", [])[:5])
            ],
        }
        return _safe_json_response(result)
    except Exception as e:
        logger.warning(f"[OpenAlex] get_institution error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_concept(args: dict) -> list[TextContent]:
    concept_id = args.get("concept_id", "").strip()
    if not concept_id:
        return _safe_json_response(None, "concept_id is required")

    try:
        import requests
        clean_id = concept_id.replace("https://openalex.org/", "")
        resp = requests.get(f"{BASE_URL}/concepts/{clean_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = {
            "id": data.get("id", "").replace("https://openalex.org/", ""),
            "name": data.get("display_name"),
            "level": data.get("level"),
            "description": data.get("description", ""),
            "works_count": data.get("works_count", 0),
            "cited_by_count": data.get("cited_by_count", 0),
            "ancestors": [
                {"id": a.get("id", "").replace("https://openalex.org/", ""), "name": a.get("display_name")}
                for a in (data.get("ancestors", []))
            ],
        }
        return _safe_json_response(result)
    except Exception as e:
        logger.warning(f"[OpenAlex] get_concept error: {e}")
        return _safe_json_response(None, str(e))


# ── Server Setup ───────────────────────────────────────────────────────────────


TOOLS = [
    Tool(name="get_openalex_works", description="检索学术论文元数据",
         inputSchema={"type": "object", "properties": {
             "query": {"type": "string"}, "per_page": {"type": "integer", "default": 25}
         }, "required": ["query"]}),
    Tool(name="get_openalex_author", description="获取作者信息",
         inputSchema={"type": "object", "properties": {"author_id": {"type": "string"}}, "required": ["author_id"]}),
    Tool(name="get_openalex_institutions", description="获取机构信息",
         inputSchema={"type": "object", "properties": {"institution_id": {"type": "string"}}, "required": ["institution_id"]}),
    Tool(name="get_openalex_concepts", description="获取主题概念树",
         inputSchema={"type": "object", "properties": {"concept_id": {"type": "string"}}, "required": ["concept_id"]}),
]

TOOL_HANDLERS = {
    "get_openalex_works": handle_get_works,
    "get_openalex_author": handle_get_author,
    "get_openalex_institutions": handle_get_institution,
    "get_openalex_concepts": handle_get_concept,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
