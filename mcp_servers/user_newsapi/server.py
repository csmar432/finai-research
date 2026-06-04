"""NewsAPI MCP Server — 财经新闻聚合.

数据来源：NewsAPI (https://newsapi.org)
免费tier：每月100次搜索。
需要 NEWSAPI_API_KEY 环境变量。
"""

from __future__ import annotations

import logging
import os
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
logger = logging.getLogger("newsapi-mcp")

APP_NAME = "newsapi-mcp"
APP_VERSION = "1.0.0"
BASE_URL = "https://newsapi.org/v2"
server = Server(APP_NAME)


def _safe_json_response(data: Any, error: str | None = None) -> list[TextContent]:
    import json
    if error:
        return [TextContent(type="text", text=f"Error: {error}")]
    try:
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]
    except Exception:
        return [TextContent(type="text", text=str(data))]


def _get_api_key() -> str:
    return os.getenv("NEWSAPI_API_KEY", os.getenv("NEWS_API_KEY", ""))


# ── Tool Handlers ──────────────────────────────────────────────────────────────


async def handle_news_search(args: dict) -> list[TextContent]:
    query = args.get("query", "").strip()
    if not query:
        return _safe_json_response(None, "query is required")

    api_key = _get_api_key()
    if not api_key:
        return _safe_json_response(None, "NEWSAPI_API_KEY not set. Get free key at https://newsapi.org/register")

    try:
        import requests
        params = {
            "q": query,
            "apiKey": api_key,
            "language": args.get("language", "en"),
            "from": args.get("from_date", ""),
            "to": args.get("to_date", ""),
            "pageSize": min(int(args.get("page_size", 20)), 100),
            "sortBy": "relevancy",
        }
        # Remove empty params
        params = {k: v for k, v in params.items() if v}

        resp = requests.get(f"{BASE_URL}/everything", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "ok":
            articles = [
                {"title": a.get("title"), "description": a.get("description", ""),
                 "source": a.get("source", {}).get("name"),
                 "author": a.get("author"), "url": a.get("url"),
                 "publishedAt": a.get("publishedAt")}
                for a in data.get("articles", [])
            ]
            return _safe_json_response({
                "query": query, "total_results": data.get("totalResults"),
                "articles": articles
            })
        return _safe_json_response(None, data.get("message", "API error"))
    except Exception as e:
        logger.warning(f"[NewsAPI] search error: {e}")
        return _safe_json_response(None, str(e))


async def handle_top_headlines(args: dict) -> list[TextContent]:
    api_key = _get_api_key()
    if not api_key:
        return _safe_json_response(None, "NEWSAPI_API_KEY not set")

    try:
        import requests
        params = {
            "apiKey": api_key,
            "category": args.get("category", "business"),
            "country": args.get("country", "us"),
            "pageSize": min(int(args.get("page_size", 20)), 50),
        }
        resp = requests.get(f"{BASE_URL}/top-headlines", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "ok":
            articles = [
                {"title": a.get("title"), "description": a.get("description", ""),
                 "source": a.get("source", {}).get("name"), "url": a.get("url"),
                 "publishedAt": a.get("publishedAt")}
                for a in data.get("articles", [])
            ]
            return _safe_json_response({"category": args.get("category"), "articles": articles})
        return _safe_json_response(None, data.get("message", "API error"))
    except Exception as e:
        logger.warning(f"[NewsAPI] headlines error: {e}")
        return _safe_json_response(None, str(e))


async def handle_news_sources(args: dict) -> list[TextContent]:
    api_key = _get_api_key()
    if not api_key:
        return _safe_json_response(None, "NEWSAPI_API_KEY not set")

    try:
        import requests
        params = {
            "apiKey": api_key,
            "language": args.get("language", "en"),
        }
        if args.get("category"):
            params["category"] = args["category"]

        resp = requests.get(f"{BASE_URL}/sources", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "ok":
            sources = [
                {"name": s.get("name"), "id": s.get("id"),
                 "category": s.get("category"), "language": s.get("language"),
                 "description": s.get("description")}
                for s in data.get("sources", [])
            ]
            return _safe_json_response({"sources": sources})
        return _safe_json_response(None, data.get("message", "API error"))
    except Exception as e:
        logger.warning(f"[NewsAPI] sources error: {e}")
        return _safe_json_response(None, str(e))


# ── Server Setup ───────────────────────────────────────────────────────────────


TOOLS = [
    Tool(name="get_news_search", description="搜索财经新闻",
         inputSchema={"type": "object", "properties": {
             "query": {"type": "string"}, "from_date": {"type": "string"},
             "to_date": {"type": "string"}, "language": {"type": "string", "default": "en"}
         }, "required": ["query"]}),
    Tool(name="get_news_top_headlines", description="获取财经头条",
         inputSchema={"type": "object", "properties": {
             "category": {"type": "string", "default": "business"},
             "country": {"type": "string", "default": "us"}
         }}),
    Tool(name="get_news_sources", description="获取新闻源列表",
         inputSchema={"type": "object", "properties": {
             "category": {"type": "string"}, "language": {"type": "string", "default": "en"}
         }}),
]

TOOL_HANDLERS = {
    "get_news_search": handle_news_search,
    "get_news_top_headlines": handle_top_headlines,
    "get_news_sources": handle_news_sources,
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
