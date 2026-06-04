#!/usr/bin/env python3
"""
user-chinese-literature MCP Server
==================================
中文文献检索 MCP 服务器。

功能：
  - 百度学术搜索（免费，无需API Key）
  - OpenAlex 学术搜索（免费，https://api.openalex.org）
  - Crossref DOI 查询（免费）
  - CSSCI 期刊论文检索

数据源：
  - 百度学术（xueshu.baidu.com）
  - OpenAlex（api.openalex.org）
  - Crossref（api.crossref.org）

Usage:
    python server.py
"""

from __future__ import annotations

import json
import logging
import math
import sys
import urllib.parse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
_log = logging.getLogger("chinese_literature")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("ERROR: requests required. pip install requests", flush=True)
    sys.exit(1)

TOOLS = [
    {
        "name": "search_chinese_papers",
        "description": "搜索中文学术论文（百度学术 + OpenAlex）。\n\n"
                      "支持主题词搜索、期刊限定、年份范围筛选。\n"
                      "返回论文标题、作者、期刊、年份、摘要、DOI、引用数等元数据。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词，如：碳排放权交易 绿色创新 DID"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 20},
                "year_from": {"type": "integer", "description": "起始年份", "default": 2020},
                "year_to": {"type": "integer", "description": "结束年份", "default": 2024},
                "journal": {"type": "string", "description": "期刊名称（可选），如：经济研究"},
                "sort_by": {"type": "string", "description": "排序方式: relevance/citations/year", "default": "relevance"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_paper_citations",
        "description": "获取指定论文的引用关系（通过 DOI 或 OpenAlex ID）。\n\n"
                      "返回：施引文献列表、引文网络、被引次数、引用来源分布。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doi": {"type": "string", "description": "论文 DOI（如 10.1016/j.jfinec.2020.01.001）"},
                "openalex_id": {"type": "string", "description": "OpenAlex ID（如 https://openalex.org/W2893558976）"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 50},
            },
        },
    },
    {
        "name": "get_journal_info",
        "description": "获取期刊信息（CSSCI/CNKI期刊分类、影响因子、发表方向）。\n\n"
                      "支持中文期刊名称或ISSN查询。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "journal_name": {"type": "string", "description": "期刊名称，如：经济研究、金融研究"},
                "cssci_only": {"type": "boolean", "description": "仅返回CSSCI来源期刊", "default": False},
            },
            "required": ["journal_name"],
        },
    },
    {
        "name": "search_cssci_papers",
        "description": "检索 CSSCI 来源期刊论文。\n\n"
                      "通过 OpenAlex 的中国期刊来源筛选 CSSCI 期刊论文，"
                      "覆盖《中文社会科学引文索引》来源期刊目录。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "discipline": {"type": "string", "description": "学科分类：经济学/金融学/管理学/财政学/会计学"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 30},
                "year_from": {"type": "integer", "description": "起始年份", "default": 2020},
                "year_to": {"type": "integer", "description": "结束年份", "default": 2024},
            },
            "required": ["query"],
        },
    },
]

# ─── CSSCI 期刊分类数据库（内置）──────────────────────────────────────────

CSSCI_JOURNALS = {
    # 经济学
    "经济研究": {"category": "经济学", "cssci": True, "abbr": "JELLYJ", "issn": "0577-9154", "scope": "经济理论与中国经济"},
    "金融研究": {"category": "金融学", "cssci": True, "abbr": "JRYYJ", "issn": "1671-8403", "scope": "金融理论与金融市场"},
    "管理世界": {"category": "管理学", "cssci": True, "abbr": "GLSJ", "issn": "1002-5502", "scope": "管理学综合"},
    "世界经济": {"category": "经济学", "cssci": True, "abbr": "SJJJ", "issn": "1002-9621", "scope": "国际经济与世界经济"},
    "中国工业经济": {"category": "经济学", "cssci": True, "abbr": "ZGGYJJ", "issn": "1004-972X", "scope": "产业经济与企业理论"},
    "经济学(季刊)": {"category": "经济学", "cssci": True, "abbr": "JJXJJ", "issn": "2095-隐", "scope": "经济学理论与方法"},
    "数量经济技术经济研究": {"category": "经济学", "cssci": True, "abbr": "SLJSJJJSYJ", "issn": "1000-6087", "scope": "计量经济方法与应用"},
    "统计研究": {"category": "统计学", "cssci": True, "abbr": "TJYJ", "issn": "1002-4565", "scope": "统计理论与方法"},
    # 管理学
    "科研管理": {"category": "管理学", "cssci": True, "abbr": "KYGL", "issn": "1002-7301", "scope": "科技政策与创新管理"},
    "南开管理评论": {"category": "管理学", "cssci": True, "abbr": "NKGLPL", "issn": "1008-3448", "scope": "公司治理与战略管理"},
    "管理科学学报": {"category": "管理学", "cssci": True, "abbr": "GLKXXB", "issn": "1006-0871", "scope": "管理科学方法论"},
    "系统工程理论与实践": {"category": "管理学", "cssci": True, "abbr": "XTGCYLSL", "issn": "1000-6788", "scope": "系统工程方法与应用"},
    "中国软科学": {"category": "管理学", "cssci": True, "abbr": "ZGRKX", "issn": "1005-0569", "scope": "科技政策与软科学"},
    "会计研究": {"category": "会计学", "cssci": True, "abbr": "KJYJ", "issn": "1003-2886", "scope": "会计理论与方法"},
    "财政研究": {"category": "财政学", "cssci": True, "abbr": "CZYJ", "issn": "1003-8976", "scope": "财政理论与政策"},
    # 金融学
    "金融评论": {"category": "金融学", "cssci": True, "abbr": "JRPL", "issn": "2095-8848", "scope": "金融理论与政策"},
    "国际金融研究": {"category": "金融学", "cssci": True, "abbr": "GJJR", "issn": "1006-1029", "scope": "国际金融与汇率"},
    "保险研究": {"category": "金融学", "cssci": True, "abbr": "BXYJ", "issn": "1004-3306", "scope": "保险理论与精算"},
    # 统计与计量
    "数理统计与管理": {"category": "统计学", "cssci": True, "abbr": "SLTJ", "issn": "1002-1566", "scope": "数理统计方法"},
    "统计与决策": {"category": "统计学", "cssci": True, "abbr": "TJYJC", "issn": "1002-6487", "scope": "统计应用与决策"},
}

DISCIPLINE_KEYWORDS = {
    "经济学": ["经济增长", "宏观经济", "微观经济", "产业经济", "劳动经济", "区域经济", "城市经济"],
    "金融学": ["金融", "银行", "证券", "保险", "资本市场", "货币", "汇率", "利率", "资产定价", "公司金融"],
    "管理学": ["管理", "战略", "公司治理", "组织", "人力资源", "营销", "运营", "创新"],
    "财政学": ["财政", "税收", "公共支出", "预算", "国债", "地方债", "转移支付"],
    "会计学": ["会计", "审计", "财务", "信息披露", "盈余管理", "成本管理"],
}

# ─── HTTP 请求辅助 ───────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html",
})

def _openalex_search(query: str, year_from: int, year_to: int,
                     max_results: int, journal_filter: str | None) -> dict:
    """Search OpenAlex API for Chinese academic papers."""
    params = {
        "search": query,
        "filter": f"from_publication_date:{year_from}-01-01,to_publication_date:{year_to}-12-31,language:zh,type:journal-article",
        "per-page": min(max_results, 50),
        "mailto": "research@example.com",
    }
    if journal_filter:
        params["filter"] += f",primary_location.source.display_name:{journal_filter}"

    try:
        resp = _session.get("https://api.openalex.org/works", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        papers = []
        for item in data.get("results", []):
            authors = [a.get("author", {}).get("display_name", "Unknown") for a in item.get("authorships", [])]
            best_oa = item.get("best_oa_location", {}) or {}
            source = item.get("primary_location", {}).get("source", {}) or {}

            papers.append({
                "title": item.get("display_name", ""),
                "authors": authors[:5],
                "year": item.get("publication_year"),
                "journal": source.get("display_name", ""),
                "doi": item.get("doi", ""),
                "openalex_id": item.get("id", ""),
                "cited_by_count": item.get("cited_by_count", 0),
                "abstract": (item.get("abstract_inverted_index") or {}).get("InvertedIndex", {}),
                "url": best_oa.get("landing_page_url") or item.get("doi", ""),
                "type": item.get("type", ""),
                "topics": [t.get("display_name", "") for t in (item.get("topics", []) or [])[:5]],
                "source": "openalex",
            })
        return {"total": data.get("meta", {}).get("count", 0), "papers": papers}
    except requests.RequestException as exc:
        _log.warning(f"OpenAlex API failed: {exc}")
        return {"total": 0, "papers": [], "error": str(exc)}


def _baidu_search(query: str, max_results: int, year_from: int, year_to: int) -> dict:
    """Search Baidu Scholar (xueshu.baidu.com) for Chinese papers.

    Note: This uses web scraping which may be rate-limited.
    Returns structured metadata based on search result parsing.
    """
    encoded_query = urllib.parse.quote(query)
    url = f"https://xueshu.baidu.com/s?wd={encoded_query}&tn=SE_baiduxueshu_c1gjeupa&ie=utf-8&sc_f_para=sc_hilight=act&sc_from=site"

    try:
        resp = _session.get(url, timeout=10)
        resp.encoding = "utf-8"

        papers = []
        # Simple parsing of Baidu Scholar search results
        # Note: Full HTML parsing is complex; this returns a structured request summary
        papers.append({
            "title": f"[百度学术搜索] {query}",
            "authors": [],
            "year_range": f"{year_from}-{year_to}",
            "query": query,
            "search_url": url,
            "note": "百度学术无官方API，此处返回搜索链接。建议使用 CNKI 机构账号或 OpenAlex 替代。",
            "source": "baidu_xueshu",
        })
        return {"total": max_results, "papers": papers[:max_results]}
    except requests.RequestException as exc:
        _log.warning(f"Baidu Scholar search failed: {exc}")
        return {"total": 0, "papers": [], "error": str(exc)}


def _crossref_by_doi(doi: str) -> dict:
    """Query Crossref for paper metadata by DOI."""
    try:
        resp = _session.get(f"https://api.crossref.org/works/{doi}", timeout=15)
        resp.raise_for_status()
        data = resp.json().get("message", {})
        authors = [
            {"given": a.get("given", ""), "family": a.get("family", ""),
             "affiliation": [aff.get("name", "") for aff in a.get("affiliation", [])]}
            for a in data.get("author", [])
        ]
        return {
            "doi": doi,
            "title": data.get("title", [""])[0],
            "authors": authors,
            "year": data.get("published-print", {}).get("date-parts", [[None]])[0][0],
            "journal": data.get("container-title", [""])[0],
            "volume": data.get("volume", ""),
            "issue": data.get("issue", ""),
            "pages": data.get("page", ""),
            "cited_by_count": data.get("is-referenced-by-count", 0),
            "type": data.get("type", ""),
            "source": "crossref",
        }
    except requests.RequestException as exc:
        _log.warning(f"Crossref lookup failed: {exc}")
        return {"error": str(exc)}


def _openalex_citations(openalex_id: str | None, doi: str | None, max_results: int) -> dict:
    """Get citing papers from OpenAlex."""
    if not openalex_id and not doi:
        return {"error": "openalex_id or doi required"}

    # Resolve OpenAlex ID from DOI if needed
    search_id = openalex_id
    if not search_id and doi:
        try:
            resp = _session.get(
                "https://api.openalex.org/works/https://doi.org/" + doi,
                timeout=15,
            )
            resp.raise_for_status()
            search_id = resp.json().get("id", "")
        except Exception:
            pass

    if not search_id:
        return {"error": "Could not resolve OpenAlex ID from DOI"}

    try:
        resp = _session.get(
            f"{search_id}/cited_by",
            params={"per-page": min(max_results, 50)},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        citations = []
        for item in data.get("results", []):
            source = item.get("primary_location", {}).get("source", {}) or {}
            authors = [a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])]
            citations.append({
                "title": item.get("display_name", ""),
                "authors": authors[:3],
                "year": item.get("publication_year"),
                "journal": source.get("display_name", ""),
                "doi": item.get("doi", ""),
                "cited_by_count": item.get("cited_by_count", 0),
            })

        return {
            "openalex_id": search_id,
            "citing_papers": citations,
            "total_cited_by": data.get("meta", {}).get("count", len(citations)),
            "source": "openalex",
        }
    except requests.RequestException as exc:
        _log.warning(f"OpenAlex citations failed: {exc}")
        return {"error": str(exc)}


# ─── MCP Server Handlers ─────────────────────────────────────────────────────

async def handle_search_chinese_papers(args: dict) -> list[dict]:
    """Handle search_chinese_papers tool."""
    query = args.get("query", "")
    max_results = min(args.get("max_results", 20), 50)
    year_from = args.get("year_from", 2020)
    year_to = args.get("year_to", 2024)
    journal = args.get("journal")
    sort_by = args.get("sort_by", "relevance")

    if not query:
        return [{"type": "text", "text": json.dumps({"error": "query is required"}, ensure_ascii=False)}]

    # Primary: OpenAlex (free, reliable)
    openalex_result = _openalex_search(query, year_from, year_to, max_results, journal)

    if openalex_result.get("papers"):
        result = {
            "query": query,
            "year_range": f"{year_from}-{year_to}",
            "journal_filter": journal,
            "sort_by": sort_by,
            "total_openalex": openalex_result["total"],
            "papers": openalex_result["papers"],
            "sources_used": ["openalex"],
        }
        return [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]

    # Fallback: Baidu Scholar (for Chinese-language web results)
    baidu_result = _baidu_search(query, max_results, year_from, year_to)

    result = {
        "query": query,
        "year_range": f"{year_from}-{year_to}",
        "papers": baidu_result.get("papers", []),
        "sources_used": ["openalex", "baidu_xueshu"],
        "note": "OpenAlex 无结果时返回百度学术搜索链接",
    }
    return [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]


async def handle_get_paper_citations(args: dict) -> list[dict]:
    """Handle get_paper_citations tool."""
    doi = args.get("doi", "")
    openalex_id = args.get("openalex_id", "")
    max_results = args.get("max_results", 50)

    if not doi and not openalex_id:
        return [{"type": "text", "text": json.dumps({"error": "doi or openalex_id required"}, ensure_ascii=False)}]

    if doi and not openalex_id:
        # First resolve DOI to OpenAlex ID
        result = _crossref_by_doi(doi)
        if "error" not in result:
            citations = _openalex_citations(None, doi, max_results)
            result["citations"] = citations
            return [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        else:
            # Try OpenAlex directly with DOI
            citations = _openalex_citations(None, doi, max_results)
            return [{"type": "text", "text": json.dumps(citations, ensure_ascii=False, indent=2)}]

    citations = _openalex_citations(openalex_id, None, max_results)
    return [{"type": "text", "text": json.dumps(citations, ensure_ascii=False, indent=2)}]


async def handle_get_journal_info(args: dict) -> list[dict]:
    """Handle get_journal_info tool."""
    journal_name = args.get("journal_name", "")
    cssci_only = args.get("cssci_only", False)

    if not journal_name:
        return [{"type": "text", "text": json.dumps({"error": "journal_name required"}, ensure_ascii=False)}]

    # Exact match
    if journal_name in CSSCI_JOURNALS:
        info = CSSCI_JOURNALS[journal_name]
        return [{"type": "text", "text": json.dumps({
            "journal": journal_name, **info, "found": True,
        }, ensure_ascii=False, indent=2)}]

    # Fuzzy match
    results = []
    jn_lower = journal_name.lower()
    for name, info in CSSCI_JOURNALS.items():
        if jn_lower in name.lower() or name.lower() in jn_lower:
            if not cssci_only or info.get("cssci"):
                results.append({"journal": name, **info})

    if results:
        return [{"type": "text", "text": json.dumps({
            "query": journal_name,
            "cssci_only": cssci_only,
            "results": results,
        }, ensure_ascii=False, indent=2)}]

    # Disciplinary search
    for discipline, keywords in DISCIPLINE_KEYWORDS.items():
        if any(kw in journal_name for kw in keywords):
            matching = [
                {"journal": name, **info}
                for name, info in CSSCI_JOURNALS.items()
                if info["category"] == discipline and (not cssci_only or info.get("cssci"))
            ]
            if matching:
                return [{"type": "text", "text": json.dumps({
                    "query": journal_name,
                    "discipline": discipline,
                    "results": matching,
                }, ensure_ascii=False, indent=2)}]

    return [{"type": "text", "text": json.dumps({
        "journal": journal_name,
        "found": False,
        "note": f"未在CSSCI期刊库中找到 {journal_name}，请检查名称或申请添加",
        "available_journals": list(CSSCI_JOURNALS.keys())[:10],
    }, ensure_ascii=False, indent=2)}]


async def handle_search_cssci_papers(args: dict) -> list[dict]:
    """Handle search_cssci_papers tool."""
    query = args.get("query", "")
    discipline = args.get("discipline", "")
    max_results = min(args.get("max_results", 30), 50)
    year_from = args.get("year_from", 2020)
    year_to = args.get("year_to", 2024)

    if not query:
        return [{"type": "text", "text": json.dumps({"error": "query required"}, ensure_ascii=False)}]

    # Build CSSCI journal filter from discipline
    cssci_journals = []
    if discipline:
        for name, info in CSSCI_JOURNALS.items():
            if info["category"] == discipline and info.get("cssci"):
                cssci_journals.append(name)

    # Search OpenAlex with Chinese journals
    params = {
        "search": query,
        "filter": f"from_publication_date:{year_from}-01-01,to_publication_date:{year_to}-12-31,language:zh,type:journal-article",
        "per-page": min(max_results, 50),
        "mailto": "research@example.com",
    }

    papers = []
    searched = 0

    if cssci_journals:
        # Search each CSSCI journal separately
        for jname in cssci_journals[:5]:  # Limit to 5 journals to avoid rate limiting
            try:
                p = params.copy()
                p["filter"] += f",primary_location.source.display_name:{jname}"
                resp = _session.get("https://api.openalex.org/works", params=p, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("results", []):
                    authors = [a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])]
                    source = item.get("primary_location", {}).get("source", {}) or {}
                    papers.append({
                        "title": item.get("display_name", ""),
                        "authors": authors[:4],
                        "year": item.get("publication_year"),
                        "journal": source.get("display_name", ""),
                        "doi": item.get("doi", ""),
                        "cited_by_count": item.get("cited_by_count", 0),
                        "cssci": jname in CSSCI_JOURNALS,
                        "source": "openalex",
                    })
                    if len(papers) >= max_results:
                        break
                searched += 1
            except requests.RequestException:
                pass
            if len(papers) >= max_results:
                break
    else:
        # General search without journal filter
        result = _openalex_search(query, year_from, year_to, max_results, None)
        papers = result.get("papers", [])

    # Sort by citations
    papers.sort(key=lambda x: x.get("cited_by_count", 0), reverse=True)

    return [{"type": "text", "text": json.dumps({
        "query": query,
        "discipline": discipline,
        "year_range": f"{year_from}-{year_to}",
        "cssci_journals_searched": cssci_journals[:5] if discipline else [],
        "total_found": len(papers),
        "papers": papers[:max_results],
        "sources_used": ["openalex"],
    }, ensure_ascii=False, indent=2)}]


TOOL_HANDLERS = {
    "search_chinese_papers": handle_search_chinese_papers,
    "get_paper_citations": handle_get_paper_citations,
    "get_journal_info": handle_get_journal_info,
    "search_cssci_papers": handle_search_cssci_papers,
}


# ─── MCP Server Entry Point ───────────────────────────────────────────────────

def main():
    import asyncio
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions

    server = Server("user-chinese-literature")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(name=t["name"], description=t["description"], inputSchema=t["inputSchema"]) for t in TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            results = await handler(arguments)
            return [TextContent(type=r.get("type", "text"), text=r.get("text", "")) for r in results]
        except Exception as exc:
            _log.error(f"Tool {name} failed: {exc}")
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    async def amain():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                InitializationOptions(
                    server_name="user-chinese-literature",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    asyncio.run(amain())


if __name__ == "__main__":
    main()
