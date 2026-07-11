"""SEC EDGAR MCP Server — 美国SEC公告获取.

数据来源：SEC EDGAR 公开API (https://efts.sec.gov)
无需API Key，完全免费。
支持：10-K年报、10-Q季报、8-K重大事件、公司搜索。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
except ImportError:
    import warnings
    warnings.warn("mcp library not installed. Install with: pip install mcp")
    raise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sec-edgar-mcp")

try:
    from mcp_servers._shared._version import APP_NAME as _APP_NAME, APP_VERSION
except Exception:
    # Fallback for standalone install / dev where shared package is missing
    _APP_NAME = "sec-edgar-mcp"
    APP_VERSION = "0.0.0+unknown"
APP_NAME = _APP_NAME
server = Server(APP_NAME)

_HEADERS = {"User-Agent": "FinResearch/1.0 research@example.com"}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


def _safe_json_response(data: Any, error: str | None = None) -> list[TextContent]:
    import json
    if error:
        return [TextContent(type="text", text=json.dumps({"status": "error", "message": error}, ensure_ascii=False, indent=2))]
    try:
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]
    except Exception:
        return [TextContent(type="text", text=json.dumps({"status": "error", "data": str(data)}, ensure_ascii=False, indent=2))]


# ── Tool Handlers ──────────────────────────────────────────────────────────────


async def handle_get_cik_by_ticker(args: dict) -> list[TextContent]:
    """Look up CIK number for a ticker symbol."""
    ticker = args.get("ticker", "").strip().upper()
    if not ticker:
        return _safe_json_response(None, "ticker is required")

    try:
        resp = _SESSION.get(
            "https://www.sec.gov/files/company_tickers.json",
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        # JSON structure: {index: {cik_str, ticker, title}}
        for key, info in data.items():
            if info.get("ticker", "").upper() == ticker:
                cik = str(info["cik_str"]).zfill(10)
                return _safe_json_response({
                    "ticker": ticker,
                    "cik": cik,
                    "company_name": info.get("title", ""),
                })

        return _safe_json_response(None, f"Ticker {ticker} not found in SEC database")
    except Exception as e:
        logger.warning(f"[SEC EDGAR] get_cik_by_ticker error for {ticker}: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_filings(args: dict) -> list[TextContent]:
    """Get recent filings of a specific type for a company."""
    cik = args.get("cik", "").strip().zfill(10)
    form_type = args.get("form_type", "10-K").upper()
    limit = min(int(args.get("limit", 10)), 100)
    if not cik:
        return _safe_json_response(None, "cik is required")

    try:
        resp = _SESSION.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accession_numbers = filings.get("accessionNumber", [])
        doc_urls = filings.get("primaryDocument", [])

        results = []
        for i, form in enumerate(forms):
            if form.upper() == form_type:
                acc = accession_numbers[i] if i < len(accession_numbers) else ""
                doc = doc_urls[i] if i < len(doc_urls) else ""
                results.append({
                    "filing_date": dates[i] if i < len(dates) else "",
                    "form": form,
                    "accession_number": acc,
                    "document_url": f"https://www.sec.gov/Archives/data/{cik}/{acc.replace('-', '')}/{doc}" if doc and acc else "",
                })
            if len(results) >= limit:
                break

        return _safe_json_response({
            "cik": cik,
            "company_name": data.get("name", ""),
            "form_type": form_type,
            "filings_found": len(results),
            "filings": results,
        })
    except Exception as e:
        logger.warning(f"[SEC EDGAR] get_filings error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_10k(args: dict) -> list[TextContent]:
    """Get 10-K annual report URL for a company."""
    cik = args.get("cik", "").strip().zfill(10)
    year = args.get("year", 2024)
    if not cik:
        return _safe_json_response(None, "cik is required")

    try:
        resp = _SESSION.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accession_numbers = filings.get("accessionNumber", [])
        doc_urls = filings.get("primaryDocument", [])

        results = []
        for i, form in enumerate(forms):
            if form.upper() == "10-K":
                date_str = dates[i] if i < len(dates) else ""
                filing_year = int(date_str[:4]) if date_str else 0
                if filing_year == year or filing_year == year - 1:
                    acc = accession_numbers[i] if i < len(accession_numbers) else ""
                    doc = doc_urls[i] if i < len(doc_urls) else ""
                    results.append({
                        "filing_date": date_str,
                        "form": form,
                        "accession_number": acc,
                        "document_url": f"https://www.sec.gov/Archives/data/{cik}/{acc.replace('-', '')}/{doc}" if doc and acc else "",
                    })
            if len(results) >= 3:
                break

        return _safe_json_response({
            "cik": cik,
            "company_name": data.get("name", ""),
            "year": year,
            "form": "10-K",
            "filings": results,
            "note": "10-K filings listed. Fetch the document URL for full annual report."
        })
    except Exception as e:
        logger.warning(f"[SEC EDGAR] get_10k error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_10q(args: dict) -> list[TextContent]:
    """Get 10-Q quarterly reports."""
    cik = args.get("cik", "").strip().zfill(10)
    year = args.get("year", 2024)
    quarter = args.get("quarter", 4)
    if not cik:
        return _safe_json_response(None, "cik is required")

    try:
        resp = _SESSION.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accession_numbers = filings.get("accessionNumber", [])
        doc_urls = filings.get("primaryDocument", [])

        results = []
        for i, form in enumerate(forms):
            if form.upper() == "10-Q":
                date_str = dates[i] if i < len(dates) else ""
                filing_year = int(date_str[:4]) if date_str else 0
                if filing_year == year:
                    acc = accession_numbers[i] if i < len(accession_numbers) else ""
                    doc = doc_urls[i] if i < len(doc_urls) else ""
                    results.append({
                        "filing_date": date_str,
                        "form": form,
                        "accession_number": acc,
                        "document_url": f"https://www.sec.gov/Archives/data/{cik}/{acc.replace('-', '')}/{doc}" if doc and acc else "",
                    })
            if len(results) >= 3:
                break

        return _safe_json_response({
            "cik": cik,
            "company_name": data.get("name", ""),
            "year": year,
            "quarter": quarter,
            "form": "10-Q",
            "filings": results,
        })
    except Exception as e:
        logger.warning(f"[SEC EDGAR] get_10q error: {e}")
        return _safe_json_response(None, str(e))


async def handle_get_8k(args: dict) -> list[TextContent]:
    """Get recent 8-K current reports (material events)."""
    cik = args.get("cik", "").strip().zfill(10)
    limit = min(int(args.get("limit", 10)), 100)
    if not cik:
        return _safe_json_response(None, "cik is required")

    try:
        resp = _SESSION.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accession_numbers = filings.get("accessionNumber", [])
        doc_urls = filings.get("primaryDocument", [])

        results = []
        for i, form in enumerate(forms):
            if form.upper() == "8-K":
                acc = accession_numbers[i] if i < len(accession_numbers) else ""
                doc = doc_urls[i] if i < len(doc_urls) else ""
                results.append({
                    "filing_date": dates[i] if i < len(dates) else "",
                    "form": form,
                    "accession_number": acc,
                    "document_url": f"https://www.sec.gov/Archives/data/{cik}/{acc.replace('-', '')}/{doc}" if doc and acc else "",
                })
            if len(results) >= limit:
                break

        return _safe_json_response({
            "cik": cik,
            "company_name": data.get("name", ""),
            "form": "8-K",
            "filings_found": len(results),
            "recent_filings": results,
        })
    except Exception as e:
        logger.warning(f"[SEC EDGAR] get_8k error: {e}")
        return _safe_json_response(None, str(e))


async def handle_company_search(args: dict) -> list[TextContent]:
    """Search for company by name."""
    company = args.get("company", "").strip()
    if not company:
        return _safe_json_response(None, "company is required")

    try:
        # Use SEC full-text search
        params = {
            "q": company,
            "forms": "10-K,10-Q,8-K",
            "dateRange": "custom",
            "startdt": "2020-01-01",
            "enddt": "2026-12-31",
        }
        resp = _SESSION.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params, timeout=20
        )
        resp.raise_for_status()
        # Fallback: return direct SEC search link
        return _safe_json_response({
            "company": company,
            "sec_search_url": f"https://www.sec.gov/cgi-bin/browse-edgar?company={company.replace(' ', '+')}&owner=include",
            "note": "SEC full-text search API. Use sec_edgar.get_cik_by_ticker for ticker lookup."
        })
    except Exception as e:
        logger.warning(f"[SEC EDGAR] company_search error: {e}")
        return _safe_json_response(None, str(e))


# ── Server Setup ───────────────────────────────────────────────────────────────


TOOLS = [
    Tool(name="get_sec_cik_by_ticker", description="通过 ticker 获取公司 CIK 编号",
         inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
    Tool(name="get_sec_company_search", description="搜索 SEC 公司信息",
         inputSchema={"type": "object", "properties": {"company": {"type": "string"}}, "required": ["company"]}),
    Tool(name="get_sec_filings", description="获取公司近期 SEC 公告",
         inputSchema={"type": "object", "properties": {
             "cik": {"type": "string"}, "form_type": {"type": "string", "default": "10-K"},
             "limit": {"type": "integer", "default": 10}
         }, "required": ["cik"]}),
    Tool(name="get_sec_10k", description="获取 10-K 年报",
         inputSchema={"type": "object", "properties": {"cik": {"type": "string"}, "year": {"type": "integer"}}, "required": ["cik", "year"]}),
    Tool(name="get_sec_10q", description="获取 10-Q 季报",
         inputSchema={"type": "object", "properties": {"cik": {"type": "string"}, "year": {"type": "integer"}, "quarter": {"type": "integer"}}, "required": ["cik"]}),
    Tool(name="get_sec_8k", description="获取 8-K 重大事件",
         inputSchema={"type": "object", "properties": {"cik": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["cik"]}),
]

TOOL_HANDLERS = {
    "get_sec_cik_by_ticker": handle_get_cik_by_ticker,
    "get_sec_company_search": handle_company_search,
    "get_sec_filings": handle_get_filings,
    "get_sec_10k": handle_get_10k,
    "get_sec_10q": handle_get_10q,
    "get_sec_8k": handle_get_8k,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return _safe_json_response(None, f"Unknown tool: {name}")
    return await handler(arguments)


async def main():
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
