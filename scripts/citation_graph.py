#!/usr/bin/env python3
"""
citation_graph.py — 引文图谱构建与分析
=====================================
基于 Semantic Scholar API 构建论文的引文网络，识别：
  - 高引经典文献（奠基性工作）
  - 近期高引文献（领域前沿）
  - 引用聚类（研究脉络）
  - 核心论文（hub nodes）
  - 引文网络中的桥接论文

用法：
  python scripts/citation_graph.py "tariff innovation DID economics" --depth 2 --max-papers 50
  python scripts/citation_graph.py --doi 10.1093/qje/fbs042 --depth 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

warnings.filterwarnings("ignore")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

# ── 配置 ────────────────────────────────────────────────────────────────────

SS_API_BASE = "https://api.semanticscholar.org/graph/v1"
SS_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "FinResearch-Agent/1.0",
}
SS_API_KEY = ""
OPENALEX_BASE = "https://api.openalex.org"
OA_HEADERS = {"User-Agent": "FinResearch-Agent/1.0 (mailto:xuzheyi@example.com)"}

# 免费层限流
_SS_RATE_LIMIT = 3.0  # seconds between calls
_last_call = 0.0


def _ss_rate_limit():
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _SS_RATE_LIMIT:
        time.sleep(_SS_RATE_LIMIT - elapsed)
    _last_call = time.time()


# ── 数据模型 ──────────────────────────────────────────────────────────────────

@dataclass
class PaperNode:
    """引文图谱中的一个节点（论文）。"""
    paper_id: str          # S2Id 或 DOI
    title: str
    year: int | None
    venue: str
    citation_count: int
    influential_cites: int
    authors: list[str]
    doi: str = ""
    arxiv_id: str = ""
    # 图谱属性（由分析器填充）
    in_degree: int = 0       # 被多少论文引用
    out_degree: int = 0      # 引用了多少论文
    centrality: float = 0.0  # 介数中心性（近似）
    tier: str = ""           # "foundational" / "frontier" / "bridge" / "recent"
    depth: int = 0           # 搜索深度

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CitationEdge:
    """引文边（引用关系）。"""
    from_id: str   # 引用方
    to_id: str     # 被引用方
    weight: float = 1.0


@dataclass
class CitationGraph:
    """引文图谱。"""
    nodes: dict[str, PaperNode] = field(default_factory=dict)
    edges: list[CitationEdge] = field(default_factory=list)
    query: str = ""
    total_searched: int = 0
    total_cited: int = 0
    total_citing: int = 0

    def add_node(self, node: PaperNode):
        self.nodes[node.paper_id] = node

    def add_edge(self, from_id: str, to_id: str):
        self.edges.append(CitationEdge(from_id=from_id, to_id=to_id))
        if from_id in self.nodes:
            self.nodes[from_id].out_degree += 1
        if to_id in self.nodes:
            self.nodes[to_id].in_degree += 1

    def get_foundation_papers(self, top_n: int = 10) -> list[PaperNode]:
        """被引用最多的论文（奠基性工作）。"""
        return sorted(
            [n for n in self.nodes.values() if n.year and n.year < 2020],
            key=lambda x: x.citation_count,
            reverse=True,
        )[:top_n]

    def get_frontier_papers(self, top_n: int = 10) -> list[PaperNode]:
        """高引用近期论文（领域前沿，2021+）。"""
        return sorted(
            [n for n in self.nodes.values() if n.year and n.year >= 2021],
            key=lambda x: x.citation_count,
            reverse=True,
        )[:top_n]

    def get_bridge_papers(self, top_n: int = 10) -> list[PaperNode]:
        """同时有高入度和高出度的论文（桥接不同研究方向）。"""
        return sorted(
            self.nodes.values(),
            key=lambda x: x.in_degree * x.out_degree,
            reverse=True,
        )[:top_n]

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "stats": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "total_searched": self.total_searched,
                "papers_cited": self.total_cited,
                "papers_citing": self.total_citing,
            },
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [asdict(e) for e in self.edges],
        }


# ── Semantic Scholar API ─────────────────────────────────────────────────────

def _ss_get(path: str, params: dict | None = None) -> dict | None:
    """发 GET 请求到 Semantic Scholar API。"""
    if not _REQUESTS_AVAILABLE:
        return None
    _ss_rate_limit()
    try:
        headers = {**SS_HEADERS}
        if SS_API_KEY:
            headers["x-api-key"] = SS_API_KEY
        resp = requests.get(
            f"{SS_API_BASE}{path}",
            params=params,
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 429:
            print(f"  ⚠️  SS rate limited, trying OpenAlex fallback...", file=sys.stderr)
            return None
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ⚠️  SS API error {path}: {e}", file=sys.stderr)
        return None


def _oa_search(query: str, limit: int = 10) -> list[dict]:
    """用 OpenAlex 搜索论文（SS 限流时的备选）。"""
    if not _REQUESTS_AVAILABLE:
        return []
    try:
        resp = requests.get(
            f"{OPENALEX_BASE}/works",
            params={
                "search": query,
                "per_page": limit,
                "sort": "cited_by_count:desc",
                "filter": "publication_year:2015-2025",
            },
            headers=OA_HEADERS,
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for w in data.get("results", []):
            authors = [a["author"]["display_name"] for a in w.get("authorships", [])[:5]]
            results.append({
                "paperId": w["id"].split("/")[-1],
                "title": w.get("title", ""),
                "year": w.get("publication_year"),
                "venue": w.get("primary_location", {}).get("source", {}).get("display_name", ""),
                "citationCount": w.get("cited_by_count", 0),
                "influentialCitationCount": 0,
                "authors": [{"name": a} for a in authors],
                "externalIds": {"DOI": w.get("doi", "").replace("https://doi.org/", "")},
            })
        return results
    except Exception:
        return []


def search_papers(query: str, limit: int = 20) -> list[dict]:
    """搜索论文。优先 SS，备选 OpenAlex。"""
    data = _ss_get("/paper/search", {
        "query": query,
        "year": "2015-2025",
        "fields": "paperId,title,year,venue,citationCount,influentialCitationCount,authors,externalIds",
        "limit": min(limit, 100),
        "sort": "citationCount:desc",
    })
    if data and data.get("data"):
        return data["data"]

    # Fallback to OpenAlex
    return _oa_search(query, limit)


def get_paper_with_citations(paper_id: str, depth: int = 1) -> dict | None:
    """获取论文详情及其引用/参考文献。"""
    fields = "paperId,title,year,venue,citationCount,influentialCitationCount,authors,externalIds,abstract,tldr"
    data = _ss_get(f"/paper/{paper_id}", {
        "fields": fields,
    })
    if not data:
        return None

    # 获取引用
    if depth >= 1:
        cites_data = _ss_get(f"/paper/{paper_id}/citations", {
            "fields": "paperId,title,year,venue,citationCount,authors",
            "limit": 20,
        })
        data["_citations"] = cites_data.get("data", []) if cites_data else []

    # 获取参考文献
    if depth >= 1:
        refs_data = _ss_get(f"/paper/{paper_id}/references", {
            "fields": "paperId,title,year,venue,citationCount,authors",
            "limit": 20,
        })
        data["_references"] = refs_data.get("data", []) if refs_data else []

    return data


# ── 图谱构建 ──────────────────────────────────────────────────────────────────

def build_graph(
    query: str,
    max_depth: int = 2,
    max_papers: int = 50,
    seed_limit: int = 20,
) -> CitationGraph:
    """
    构建引文图谱。

    Args:
        query: 搜索关键词
        max_depth: 递归深度（0=仅种子，1=加引用，2=深度探索）
        max_papers: 最多节点数
        seed_limit: 种子论文数量
    """
    graph = CitationGraph(query=query)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = []  # (paper_id, depth)

    # 种子搜索
    seeds = search_papers(query, limit=seed_limit)
    print(f"[Graph Builder] Found {len(seeds)} seed papers")
    graph.total_searched += len(seeds)

    for p in seeds:
        paper_id = p.get("paperId", "")
        if not paper_id or paper_id in visited:
            continue
        if len(graph.nodes) >= max_papers:
            break

        node = _make_node(p)
        graph.add_node(node)
        visited.add(paper_id)

        if max_depth >= 1:
            queue.append((paper_id, 1))

    graph.total_cited = len([n for n in graph.nodes.values() if n.citation_count > 0])
    graph.total_citing = len([n for n in graph.nodes.values() if n.out_degree > 0])

    # BFS 扩展
    while queue and len(graph.nodes) < max_papers:
        paper_id, depth = queue.pop(0)
        if depth > max_depth:
            continue

        detail = get_paper_with_citations(paper_id, depth=depth)
        if not detail:
            continue

        # 添加引用（正向）
        for citing in detail.get("_citations", []):
            citing_paper = citing.get("citingPaper", {})
            cp_id = citing_paper.get("paperId", "")
            if not cp_id or cp_id in visited:
                continue
            if len(graph.nodes) >= max_papers:
                break

            node = _make_node(citing_paper)
            graph.add_node(node)
            graph.add_edge(cp_id, paper_id)  # citing → cited
            visited.add(cp_id)
            graph.total_citing += 1
            if depth < max_depth:
                queue.append((cp_id, depth + 1))

        # 添加参考文献（逆向）
        for ref in detail.get("_references", []):
            ref_paper = ref.get("citedPaper", {})
            rp_id = ref_paper.get("paperId", "")
            if not rp_id or rp_id in visited:
                continue
            if len(graph.nodes) >= max_papers:
                break

            node = _make_node(ref_paper)
            graph.add_node(node)
            graph.add_edge(paper_id, rp_id)  # paper → ref
            visited.add(rp_id)
            graph.total_cited += 1

        graph.total_searched += 1

    # 分类节点
    _classify_nodes(graph)

    return graph


def _make_node(p: dict) -> PaperNode:
    """从 API 响应构建 PaperNode。"""
    external = p.get("externalIds", {}) or {}
    return PaperNode(
        paper_id=p.get("paperId", ""),
        title=p.get("title", "N/A"),
        year=p.get("year"),
        venue=p.get("venue", ""),
        citation_count=p.get("citationCount", 0),
        influential_cites=p.get("influentialCitationCount", 0),
        authors=[a.get("name", "") for a in p.get("authors", []) if a.get("name")],
        doi=external.get("DOI", ""),
        arxiv_id=external.get("ArXiv", ""),
    )


def _classify_nodes(graph: CitationGraph):
    """将节点分类为奠基性/前沿/桥接/近期。"""
    median_cites = sorted(n.citation_count for n in graph.nodes.values())[len(graph.nodes) // 2] or 1

    for node in graph.nodes.values():
        cites = node.citation_count
        year = node.year or 2020

        if cites >= median_cites * 3 and year <= 2018:
            node.tier = "foundational"
        elif cites >= median_cites * 2 and year >= 2021:
            node.tier = "frontier"
        elif node.in_degree > 0 and node.out_degree > 0:
            node.tier = "bridge"
        elif year >= 2023:
            node.tier = "recent"
        else:
            node.tier = "other"


# ── 分析报告 ──────────────────────────────────────────────────────────────────

def generate_report(graph: CitationGraph) -> str:
    """生成图谱分析报告。"""
    lines = [
        f"# Citation Graph Report",
        f"",
        f"**Query**: {graph.query}",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## Statistics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total nodes (papers) | {len(graph.nodes)} |",
        f"| Total edges (citations) | {len(graph.edges)} |",
        f"| Seed papers | {graph.total_searched} |",
        f"| Papers with citations | {graph.total_cited} |",
        f"| Papers with references | {graph.total_citing} |",
        f"",
    ]

    # 奠基性工作
    foundational = graph.get_foundation_papers(5)
    if foundational:
        lines += [
            "## Foundational Works (High-Cite, Pre-2020)",
            "",
        ]
        for i, n in enumerate(foundational, 1):
            lines.append(f"**{i}. {n.title}** ({n.year})")
            lines.append(f"   Authors: {', '.join(n.authors[:3]) or 'N/A'}")
            lines.append(f"   Venue: {n.venue or 'N/A'} | Citations: {n.citation_count:,}")
            lines.append(f"   ID: `{n.paper_id}` | DOI: `{n.doi}`")
            lines.append("")

    # 前沿工作
    frontier = graph.get_frontier_papers(5)
    if frontier:
        lines += [
            "## Frontier Papers (High-Cite, 2021+)",
            "",
        ]
        for i, n in enumerate(frontier, 1):
            lines.append(f"**{i}. {n.title}** ({n.year})")
            lines.append(f"   Authors: {', '.join(n.authors[:3]) or 'N/A'}")
            lines.append(f"   Venue: {n.venue or 'N/A'} | Citations: {n.citation_count:,}")
            lines.append(f"   ID: `{n.paper_id}` | DOI: `{n.doi}`")
            lines.append("")

    # 桥接论文
    bridges = graph.get_bridge_papers(5)
    if bridges:
        lines += [
            "## Bridge Papers (High In + Out Degree)",
            "   These connect different research threads.",
            "",
        ]
        for i, n in enumerate(bridges, 1):
            lines.append(f"**{i}. {n.title}** ({n.year})")
            lines.append(f"   Cited by: {n.in_degree} papers | References: {n.out_degree} papers | Citations: {n.citation_count:,}")
            lines.append("")

    # 节点汇总
    lines += [
        "## All Nodes Summary",
        "",
        "| Title | Year | Venue | Citations | Type |",
        "|-------|------|-------|-----------|------|",
    ]
    for node in sorted(graph.nodes.values(), key=lambda x: x.citation_count, reverse=True)[:30]:
        lines.append(f"| {node.title[:60]} | {node.year or 'N/A'} | {node.venue or 'N/A'} | {node.citation_count:,} | {node.tier} |")

    lines.append("")
    lines.append(f"*Total: {len(graph.nodes)} papers in graph*")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Citation graph builder — trace citation networks from any paper or query.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--doi", help="Start from a specific DOI")
    parser.add_argument("--arxiv", help="Start from a specific arXiv ID")
    parser.add_argument("--depth", type=int, default=2, help="BFS depth (0-2)")
    parser.add_argument("--max-papers", type=int, default=50, help="Max papers in graph")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--report", "-r", help="Output Markdown report file")
    parser.add_argument("--format", choices=["json", "report", "both"], default="both")

    args = parser.parse_args(argv)

    if not args.query and not args.doi and not args.arxiv:
        parser.print_help()
        return 0

    # 确定起始点
    if args.doi:
        start_id = args.doi
        query = f"DOI: {args.doi}"
    elif args.arxiv:
        start_id = f"arXiv:{args.arxiv}"
        query = f"arXiv: {args.arxiv}"
    else:
        start_id = None
        query = args.query

    print(f"Building citation graph for: {query}")
    print(f"  Depth: {args.depth}, Max papers: {args.max_papers}")

    if start_id:
        graph = CitationGraph(query=query)
        detail = get_paper_with_citations(start_id, depth=args.depth)
        if not detail:
            print(f"❌ Paper not found: {start_id}")
            return 1
        graph.add_node(_make_node(detail))
        # BFS expansion
        visited = {start_id}
        queue = [(start_id, 1)]
        while queue and len(graph.nodes) < args.max_papers:
            pid, depth = queue.pop(0)
            if depth > args.depth:
                continue
            d = get_paper_with_citations(pid, depth=depth)
            if not d:
                continue
            for citing in d.get("_citations", []):
                cp = citing.get("citingPaper", {})
                cid = cp.get("paperId", "")
                if cid and cid not in visited:
                    graph.add_node(_make_node(cp))
                    graph.add_edge(cid, pid)
                    visited.add(cid)
                    if depth < args.depth:
                        queue.append((cid, depth + 1))
            for ref in d.get("_references", []):
                rp = ref.get("citedPaper", {})
                rid = rp.get("paperId", "")
                if rid and rid not in visited:
                    graph.add_node(_make_node(rp))
                    graph.add_edge(pid, rid)
                    visited.add(rid)
    else:
        graph = build_graph(query, max_depth=args.depth, max_papers=args.max_papers)

    _classify_nodes(graph)
    print(f"✅ Graph built: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    if args.output or args.format in ("json", "both"):
        out = args.output or f"output/citation_graph_{hash(query) % 1e6}.json"
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(graph.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"📊 JSON: {out}")

    if args.report or args.format in ("report", "both"):
        rep_out = args.report or f"output/citation_graph_report_{hash(query) % 1e6}.md"
        Path(rep_out).parent.mkdir(parents=True, exist_ok=True)
        report = generate_report(graph)
        with open(rep_out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"📝 Report: {rep_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
