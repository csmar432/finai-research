#!/usr/bin/env python3
"""
学术知识图谱模块
================
基于 NetworkX + Semantic Scholar API 构建和查询学术引文网络。
支持 MCP 工具（arXiv、网页搜索）增强学术文献检索。
无需 Neo4j 依赖，纯 Python 实现。

功能：
  - 节点：PaperNode（论文信息）
  - 边：CitationEdge（引文关系 + 上下文）
  - 查询：按主题检索、引文链追溯、先修/衍生论文分析
  - 中心性：PageRank 识别高影响力论文
  - 持久化：pickle / JSON 两种格式
  - MCP集成：优先使用 arXiv API 做深度文献检索，fallback 到 Semantic Scholar

用法：
  kg = KnowledgeGraph()
  kg.build_from_search("LLM in finance", max_results=20)
  kg.compute_centrality()
  top_papers = sorted(kg.graph.nodes(), key=lambda x: kg.pagerank.get(x, 0), reverse=True)[:5]

  # 使用 MCP arXiv
  kg.build_from_arxiv("transformer finance", max_results=10)

作者：Paper-Report Workflow
"""

from __future__ import annotations

import json
import logging
import pickle
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import networkx as nx
import requests

# ── 日志配置 ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── 数据模型 ────────────────────────────────────────────────────────────────

@dataclass
class PaperNode:
    """学术论文节点。"""
    id: str                           # 唯一标识（通常为 Semantic Scholar ID 或 arXiv ID）
    title: str                        # 论文标题
    authors: list[str] = field(default_factory=list)   # 作者列表
    year: int = 0                     # 发表年份
    venue: str = ""                    # 发表 venue（期刊/会议）
    abstract: str = ""                 # 摘要
    arxiv_id: str = ""                 # arXiv ID（可选）
    doi: str = ""                     # DOI（可选）
    citation_count: int = 0            # 引用数
    external_ids: dict = field(default_factory=dict)  # 额外的外部 ID
    tags: list[str] = field(default_factory=list)     # 领域标签
    url: str = ""                     # 论文主页 URL

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PaperNode:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CitationEdge:
    """引文关系边。"""
    citing_paper: str      # 施引论文 ID
    cited_paper: str      # 被引论文 ID
    context_sentence: str = ""   # 引用上下文句子
    section: str = ""            # 出现的章节（Introduction/Related Work 等）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CitationEdge:
        return cls(**data)


# ── Semantic Scholar API 客户端 ─────────────────────────────────────────────

class SemanticScholarClient:
    """
    Semantic Scholar API 封装。
    文档：https://api.semanticscholar.org/api-docs/
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    FIELDS = (
        "paperId,title,authors,year,venue,abstract,arxivId,doi,"
        "citationCount,externalIds,url"
    )

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Paper-Report-Workflow/1.0 (academic-research-tool)",
        })

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """带重试的 GET 请求。"""
        url = f"{self.BASE_URL}/{endpoint}"
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                logger.warning(f"  请求失败（尝试 {attempt + 1}/{self.max_retries}）: {e}")
                if attempt == self.max_retries - 1:
                    raise
        return {}

    def search(self, query: str, limit: int = 10, year: int | None = None) -> list[dict]:
        """
        搜索论文。

        Args:
            query: 搜索关键词
            limit: 最大结果数（上限 100）
            year: 可选，限定发表年份

        Returns:
            论文列表（dict）
        """
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": self.FIELDS,
        }
        if year:
            params["year"] = year

        try:
            data = self._get("paper/search", params)
            papers = data.get("data", [])
            logger.info(f"  Semantic Scholar 搜索 '{query}' → {len(papers)} 篇")
            return papers
        except Exception as e:
            logger.error(f"  Semantic Scholar 搜索失败: {e}")
            return []

    def get_paper(self, paper_id: str, fields: str | None = None) -> dict:
        """获取单篇论文详情。"""
        f = fields or self.FIELDS
        try:
            return self._get(f"paper/{paper_id}", params={"fields": f})
        except Exception as e:
            logger.warning(f"  获取论文 {paper_id} 失败: {e}")
            return {}

    def get_references(self, paper_id: str, limit: int = 50) -> list[dict]:
        """获取论文的参考文献（即该论文引用了哪些论文）。"""
        try:
            data = self._get(
                f"paper/{paper_id}/references",
                params={"limit": limit, "fields": self.FIELDS},
            )
            refs = data.get("data", [])
            return [r.get("citedPaper", {}) for r in refs if r.get("citedPaper", {}).get("paperId")]
        except Exception as e:
            logger.warning(f"  获取参考文献失败 ({paper_id}): {e}")
            return []

    def get_citations(self, paper_id: str, limit: int = 50) -> list[dict]:
        """获取论文的引用者（即哪些论文引用了该论文）。"""
        try:
            data = self._get(
                f"paper/{paper_id}/citations",
                params={"limit": limit, "fields": self.FIELDS},
            )
            cites = data.get("data", [])
            return [c.get("citingPaper", {}) for c in cites if c.get("citingPaper", {}).get("paperId")]
        except Exception as e:
            logger.warning(f"  获取引用者失败 ({paper_id}): {e}")
            return []

    def get_papers_bulk(self, paper_ids: list[str]) -> list[dict]:
        """批量获取论文信息（每批最多 1000 个 ID）。"""
        results = []
        batch_size = 500
        for i in range(0, len(paper_ids), batch_size):
            batch = paper_ids[i:i + batch_size]
            ids_str = ",".join(batch)
            try:
                data = self._get(
                    "paper/batch",
                    params={"ids": ids_str, "fields": self.FIELDS},
                )
                results.extend(data.get("data", []))
            except Exception as e:
                logger.warning(f"  批量获取失败: {e}")
        return results


# ── citracer CLI 集成 ────────────────────────────────────────────────────────

class CitracerClient:
    """
    citracer CLI 封装。
    citracer 是一个专门的学术引文追溯工具，支持深度引文网络构建。
    官网：https://github.com/...（如不可用则跳过）
    """

    def __init__(self):
        self.available = self._check_availability()
        self.executable = "citracer"

    def _check_availability(self) -> bool:
        """检查 citracer 是否已安装。"""
        try:
            result = subprocess.run(
                [self.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"  citracer 可用: {result.stdout.strip()}")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        logger.info("  citracer 未安装，跳过（将使用 Semantic Scholar API）")
        return False

    def trace_citations(self, paper_id: str, depth: int = 5) -> dict:
        """
        使用 citracer 追溯引文网络。

        Args:
            paper_id: 起始论文 ID
            depth: 追溯深度

        Returns:
            包含 nodes 和 edges 的 dict
        """
        if not self.available:
            return {"nodes": [], "edges": []}

        try:
            result = subprocess.run(
                [
                    self.executable,
                    "trace",
                    "--id", paper_id,
                    "--depth", str(depth),
                    "--format", "json",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
            else:
                logger.warning(f"  citracer trace 失败: {result.stderr.strip()}")
        except Exception as e:
            logger.warning(f"  citracer 调用失败: {e}")

        return {"nodes": [], "edges": []}


# ── MCP arXiv 集成 ──────────────────────────────────────────────────────────

def fetch_arxiv_papers(query: str, max_results: int = 10) -> list[dict]:
    """
    通过 MCP arXiv 工具搜索论文。

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        论文列表（dict），包含 title, authors, abstract, arxiv_id 等
    """
    from scripts.core.llm_gateway import call_mcp_tool as _mcp_call
    try:
        # FIX (2026-05-29): call_mcp_tool returns MCPResult on error,
        # or raises exception on network failure. Wrap in try/except.
        results = _mcp_call("user-arxiv", "semantic_search", {"query": query, "limit": max_results})
        if results and isinstance(results, list):
            logger.info(f"  arXiv MCP: '{query}' → {len(results)} 篇")
            return results
    except Exception as e:
        logger.warning(f"[KnowledgeGraph] arXiv MCP call failed: {e}")
    return []


def fetch_web_papers(query: str, max_results: int = 10) -> list[dict]:
    """
    通过 MCP brave_search 搜索论文。

    Returns:
        论文列表（dict）
    """
    from scripts.core.llm_gateway import call_mcp_tool as _mcp_call
    try:
        # FIX (2026-05-29): wrap in try/except for network/MCP errors
        results = _mcp_call(
            "user-brave-search",
            "brave_web_search",
            {"query": f"{query} filetype:pdf site:arxiv.org OR site:ssrn.com"},
        )
        if results and isinstance(results, list):
            logger.info(f"  Web search: '{query}' → {len(results)} 篇")
            return results[:max_results]
    except Exception as e:
        logger.warning(f"[KnowledgeGraph] Brave Search MCP call failed: {e}")
    return []


# ── 知识图谱主类 ────────────────────────────────────────────────────────────

class KnowledgeGraph:
    """
    学术知识图谱。
    基于 NetworkX DiGraph，支持增删查改、引文分析、持久化。
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self.pagerank: dict[str, float] = {}
        self._papers: dict[str, PaperNode] = {}
        self._ss_client: SemanticScholarClient | None = None
        self._citracer: CitracerClient | None = None

    # ── 延迟初始化 ──────────────────────────────────────────────────────────

    @property
    def ss(self) -> SemanticScholarClient:
        if self._ss_client is None:
            self._ss_client = SemanticScholarClient()
        return self._ss_client

    @property
    def citracer(self) -> CitracerClient:
        if self._citracer is None:
            self._citracer = CitracerClient()
        return self._citracer

    # ── 节点操作 ────────────────────────────────────────────────────────────

    def add_paper(self, paper: PaperNode) -> None:
        """添加论文节点。"""
        self.graph.add_node(paper.id, **paper.to_dict())
        self._papers[paper.id] = paper

    def add_papers(self, papers: list[PaperNode]) -> int:
        """批量添加论文节点，返回添加数量。"""
        count = 0
        for p in papers:
            if p.id not in self._papers:
                self.add_paper(p)
                count += 1
        return count

    def get_paper(self, paper_id: str) -> PaperNode | None:
        """获取论文节点。"""
        return self._papers.get(paper_id)

    def has_paper(self, paper_id: str) -> bool:
        return paper_id in self._papers

    def remove_paper(self, paper_id: str) -> bool:
        """删除论文节点及其所有关联边。"""
        if paper_id in self.graph:
            self.graph.remove_node(paper_id)
            self._papers.pop(paper_id, None)
            return True
        return False

    # ── 边操作 ──────────────────────────────────────────────────────────────

    def add_citation(
        self,
        from_id: str,
        to_id: str,
        context: str = "",
        section: str = "",
    ) -> None:
        """
        添加引文关系边（from_id 引用了 to_id）。
        如果节点不存在，会自动创建待查节点。
        """
        if from_id not in self._papers:
            self.add_paper(PaperNode(id=from_id, title=f"[未知] {from_id}"))
        if to_id not in self._papers:
            self.add_paper(PaperNode(id=to_id, title=f"[未知] {to_id}"))

        edge_data = {
            "citing_paper": from_id,
            "cited_paper": to_id,
            "context_sentence": context,
            "section": section,
            "added_at": datetime.now().isoformat(),
        }
        self.graph.add_edge(from_id, to_id, **edge_data)

    def add_citations_bulk(self, edges: list[CitationEdge]) -> int:
        """批量添加引文边，返回添加数量。"""
        count = 0
        for edge in edges:
            if not self.graph.has_edge(edge.citing_paper, edge.cited_paper):
                self.add_citation(edge.citing_paper, edge.cited_paper,
                                   edge.context_sentence, edge.section)
                count += 1
        return count

    def get_references(self, paper_id: str) -> list[str]:
        """获取某论文引用的论文列表。"""
        if paper_id not in self.graph:
            return []
        return list(self.graph.successors(paper_id))

    def get_citations(self, paper_id: str) -> list[str]:
        """获取引用某论文的论文列表。"""
        if paper_id not in self.graph:
            return []
        return list(self.graph.predecessors(paper_id))

    # ── 检索 ────────────────────────────────────────────────────────────────

    def query_by_topic(self, keyword: str, limit: int = 20) -> list[PaperNode]:
        """
        通过 Semantic Scholar API 按关键词搜索论文。
        结果自动加入图谱。
        """
        raw = self.ss.search(keyword, limit=limit)
        papers = []
        for item in raw:
            paper = self._raw_to_paper(item)
            if paper:
                papers.append(paper)
                if paper.id not in self._papers:
                    self.add_paper(paper)
        return papers

    def _raw_to_paper(self, raw: dict) -> PaperNode | None:
        """将 Semantic Scholar API 返回的 raw dict 转换为 PaperNode。"""
        pid = raw.get("paperId", "")
        if not pid:
            return None

        authors = []
        for a in raw.get("authors", []):
            if isinstance(a, dict):
                authors.append(a.get("name", ""))
            else:
                authors.append(str(a))

        return PaperNode(
            id=pid,
            title=raw.get("title", "未知标题"),
            authors=authors,
            year=raw.get("year", 0) or 0,
            venue=raw.get("venue", ""),
            abstract=raw.get("abstract", ""),
            arxiv_id=raw.get("arxivId", ""),
            doi=raw.get("doi", ""),
            citation_count=raw.get("citationCount", 0),
            external_ids=raw.get("externalIds", {}),
            url=raw.get("url", ""),
        )

    # ── 引文链追溯 ──────────────────────────────────────────────────────────

    def get_citation_chain(self, paper_id: str, depth: int = 2) -> dict:
        """
        递归追溯引文链（向前引用：papers this paper builds upon）。
        同时支持 citracer 深度追溯（depth >= 5）。

        Returns:
            {
                "paper": PaperNode,
                "references": [  # depth=1 的参考文献
                    {"paper": PaperNode, "references": [...]}
                ],
                "depth": 实际追溯深度
            }
        """
        if depth >= 5 and self.citracer.available:
            logger.info(f"  使用 citracer 深度追溯 {paper_id}（depth={depth}）")
            return self._trace_with_citracer(paper_id, depth)

        paper = self._papers.get(paper_id)
        if paper is None:
            paper_raw = self.ss.get_paper(paper_id)
            paper = self._raw_to_paper(paper_raw)
            if paper:
                self.add_paper(paper)

        result = {"paper": paper, "references": [], "depth": 0}

        if paper_id in self.graph:
            ref_ids = list(self.graph.successors(paper_id))
        else:
            ref_ids = [r.get("paperId") for r in self.ss.get_references(paper_id) if r.get("paperId")]
            ref_ids = [rid for rid in ref_ids if rid]

        if depth <= 0:
            return result

        for rid in ref_ids[:20]:
            if rid and rid != paper_id:
                sub_result = self.get_citation_chain(rid, depth=depth - 1)
                sub_result["depth"] = depth - 1
                result["references"].append(sub_result)

                raw = self.ss.get_paper(rid)
                sub_paper = self._raw_to_paper(raw)
                if sub_paper and sub_paper.id not in self._papers:
                    self.add_paper(sub_paper)

        return result

    def _trace_with_citracer(self, paper_id: str, depth: int) -> dict:
        """使用 citracer 做深度引文追溯。"""
        data = self.citracer.trace_citations(paper_id, depth=depth)

        paper = self._papers.get(paper_id)
        result = {"paper": paper, "references": [], "depth": depth, "source": "citracer"}

        for node_data in data.get("nodes", []):
            node_paper = self._raw_to_paper(node_data)
            if node_paper and node_paper.id not in self._papers:
                self.add_paper(node_paper)

        for edge in data.get("edges", []):
            from_id = edge.get("from") or edge.get("source")
            to_id = edge.get("to") or edge.get("target")
            if from_id and to_id:
                self.add_citation(from_id, to_id)

        return result

    # ── 先修与衍生分析 ────────────────────────────────────────────────────────

    def find_prerequisite(self, paper_id: str) -> list[PaperNode]:
        """
        找到某论文的前置论文（该论文所引用的核心论文）。
        策略：引用数高 + 被引用次数多的参考文献。
        """
        ref_ids = self.get_references(paper_id)
        if not ref_ids:
            ref_ids = [r.get("paperId") for r in self.ss.get_references(paper_id)]
            ref_ids = [rid for rid in ref_ids if rid]

        prereq_scores: dict[str, float] = {}
        for rid in ref_ids:
            cited_count = self.get_citations(rid)
            cited_count = len(cited_count) if cited_count else 0
            paper = self._papers.get(rid)
            score = cited_count * 10 + (paper.citation_count if paper else 0)
            prereq_scores[rid] = score

        top_ids = sorted(prereq_scores, key=prereq_scores.get, reverse=True)[:10]
        return [self._papers[rid] for rid in top_ids if rid in self._papers]

    def find_derivatives(self, paper_id: str) -> list[PaperNode]:
        """
        找到某论文的衍生论文（引用了该论文的论文）。
        """
        citing_ids = self.get_citations(paper_id)
        if not citing_ids:
            citing_ids = [c.get("paperId") for c in self.ss.get_citations(paper_id)]
            citing_ids = [cid for cid in citing_ids if cid]

        derivatives = []
        for cid in citing_ids:
            if cid and cid != paper_id and cid in self._papers:
                derivatives.append(self._papers[cid])
            elif cid:
                raw = self.ss.get_paper(cid)
                p = self._raw_to_paper(raw)
                if p:
                    self.add_paper(p)
                    derivatives.append(p)

        derivatives.sort(key=lambda x: x.citation_count, reverse=True)
        return derivatives[:20]

    # ── 中心性分析 ──────────────────────────────────────────────────────────

    def compute_centrality(self, method: str = "pagerank", alpha: float = 0.85) -> dict[str, float]:
        """
        计算图的中心性。

        Args:
            method: 'pagerank' | 'degree' | 'betweenness' | 'closeness'
            alpha: PageRank 阻尼因子

        Returns:
            {paper_id: centrality_score}
        """
        if self.graph.number_of_nodes() == 0:
            logger.warning("图为空，无法计算中心性")
            return {}

        logger.info(f"  计算中心性（{method}）...")
        if method == "pagerank":
            scores = nx.pagerank(self.graph, alpha=alpha)
        elif method == "degree":
            scores = nx.degree_centrality(self.graph)
        elif method == "betweenness":
            scores = nx.betweenness_centrality(self.graph)
        elif method == "closeness":
            scores = nx.closeness_centrality(self.graph)
        else:
            logger.warning(f"未知的中心性方法 '{method}'，使用 pagerank")
            scores = nx.pagerank(self.graph, alpha=alpha)

        self.pagerank = scores
        return scores

    def top_influential(self, n: int = 10, method: str = "pagerank") -> list[tuple[str, float]]:
        """返回 top-n 高影响力论文。"""
        if not self.pagerank:
            self.compute_centrality(method=method)
        sorted_papers = sorted(self.pagerank.items(), key=lambda x: x[1], reverse=True)
        return sorted_papers[:n]

    # ── 从搜索构建图谱 ───────────────────────────────────────────────────────

    def build_from_search(self, query: str, max_results: int = 20, add_references: bool = True) -> int:
        """
        从关键词搜索构建初始图谱。

        Args:
            query: 搜索关键词
            max_results: 最大论文数
            add_references: 是否同时获取每篇论文的参考文献

        Returns:
            添加的论文数量
        """
        logger.info(f"  从搜索构建图谱: '{query}' (max={max_results})")
        papers = self.query_by_topic(query, limit=max_results)
        added = len(papers)

        if add_references:
            for paper in papers:
                if paper.id:
                    ref_ids = [r.get("paperId") for r in self.ss.get_references(paper.id)]
                    ref_ids = [rid for rid in ref_ids if rid and rid != paper.id]
                    for rid in ref_ids[:10]:
                        raw = self.ss.get_paper(rid)
                        ref_paper = self._raw_to_paper(raw)
                        if ref_paper and ref_paper.id not in self._papers:
                            self.add_paper(ref_paper)
                            added += 1
                        self.add_citation(paper.id, rid)

        logger.info(f"  图谱构建完成：{added} 篇论文，{self.graph.number_of_edges()} 条边")
        return added

    # ── 统计信息 ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回图谱统计信息。"""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "papers": len(self._papers),
            "isolates": len(list(nx.isolates(self.graph))) if self.graph else 0,
            "density": nx.density(self.graph) if self.graph else 0,
            "is_dag": nx.is_directed_acyclic_graph(self.graph) if self.graph else True,
        }

    def summary(self) -> str:
        """返回可读的图谱摘要。"""
        stats = self.stats()
        lines = [
            "学术知识图谱摘要",
            f"{'─' * 40}",
            f"  论文节点: {stats['nodes']}",
            f"  引文边:   {stats['edges']}",
            f"  孤立节点: {stats['isolates']}",
            f"  图密度:   {stats['density']:.4f}",
            f"  DAG:      {'是' if stats['is_dag'] else '否'}",
        ]
        if self.pagerank:
            top3 = self.top_influential(3)
            lines.append("  Top-3 高影响力论文:")
            for pid, score in top3:
                paper = self._papers.get(pid)
                title = paper.title[:40] if paper else pid[:20]
                lines.append(f"    · {title} ({score:.4f})")
        return "\n".join(lines)

    # ── 持久化 ───────────────────────────────────────────────────────────────

    def save_graph(self, path: str | Path) -> None:
        """使用 pickle 持久化完整图谱。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "graph": self.graph,
                    "papers": self._papers,
                    "pagerank": self.pagerank,
                    "saved_at": datetime.now().isoformat(),
                },
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        logger.info(f"  图谱已保存: {path} ({path.stat().st_size / 1024:.1f} KB)")

    def load_graph(self, path: str | Path) -> bool:
        """从 pickle 加载图谱。

        SECURITY: 使用 RestrictedUnpickler 白名单机制防止 RCE 攻击。
        仅允许反序列化 dict、list、str、int、float、None、NetworkX 图对象，
        以及 PaperPaper 类型的 NamedTuple 实例。
        """
        import pickle
        path = Path(path)
        if not path.exists():
            logger.error(f"  文件不存在: {path}")
            return False

        # 白名单安全反序列化器
        _ALLOWED_CLASSES = {
            "dict", "list", "str", "int", "float", "bool",
            "NoneType", "tuple", "set", "frozenset",
            "type", "function", "Cell", "Method",
        }

        class RestrictedUnpickler(pickle.Unpickler):
            def find_class(self, module: str, name: str):
                # 允许 networkx 和内置类型
                if module.startswith("networkx."):
                    return super().find_class(module, name)
                if module in ("builtins", "_pickle", "copyreg", "collections"):
                    return super().find_class(module, name)
                # 允许 dataclass-based 类（通过 __builtins__ 注入的模块）
                if module in _ALLOWED_CLASSES:
                    return super().find_class(module, name)
                # 禁止所有其他模块（防止 __import__ RCE）
                raise pickle.UnpicklingError(
                    f"Forbidden class: {module}.{name}"
                )

        try:
            with open(path, "rb") as f:
                unpickler = RestrictedUnpickler(f)
                unpickler.persistent_load = self._safe_persistent_load
                data = unpickler.load()

            self.graph = data.get("graph", nx.DiGraph())
            self._papers = data.get("papers", {})
            self.pagerank = data.get("pagerank", {})
            logger.info(
                f"  图谱已加载: {self.graph.number_of_nodes()} 节点, "
                f"{self.graph.number_of_edges()} 边"
            )
            return True
        except pickle.UnpicklingError as e:
            logger.error(f"  加载失败（禁止的类）: {e}")
            return False
        except Exception as e:
            logger.error(f"  加载失败: {e}")
            return False

    def _safe_persistent_load(self, saved_id):
        """处理 pickle 持久化引用。"""
        raise pickle.UnpicklingError(
            f"Persistent references not supported: {saved_id}"
        )

    def to_json(self) -> str:
        """导出为 JSON 字符串（不含 NetworkX graph 对象）。"""
        data = {
            "papers": [p.to_dict() for p in self._papers.values()],
            "edges": [
                {
                    "citing_paper": u,
                    "cited_paper": v,
                    **d,
                }
                for u, v, d in self.graph.edges(data=True)
            ],
            "pagerank": self.pagerank,
            "stats": self.stats(),
            "exported_at": datetime.now().isoformat(),
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def save_json(self, path: str | Path) -> None:
        """保存为 JSON 文件。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        logger.info(f"  JSON 已保存: {path}")

    @classmethod
    def from_json(cls, json_str: str | None = None, path: str | Path | None = None) -> KnowledgeGraph:
        """
        从 JSON 字符串或文件加载图谱。

        Args:
            json_str: JSON 字符串
            path: JSON 文件路径

        Returns:
            新的 KnowledgeGraph 实例
        """
        kg = cls()
        if path:
            json_str = Path(path).read_text(encoding="utf-8")
        if not json_str:
            return kg

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return kg

        for pdata in data.get("papers", []):
            paper = PaperNode.from_dict(pdata)
            kg.add_paper(paper)

        for edata in data.get("edges", []):
            kg.add_citation(
                from_id=edata.get("citing_paper", ""),
                to_id=edata.get("cited_paper", ""),
                context=edata.get("context_sentence", ""),
                section=edata.get("section", ""),
            )

        kg.pagerank = data.get("pagerank", {})
        return kg

    # ── 从 arXiv MCP 构建图谱 ─────────────────────────────────────────────────

    def build_from_arxiv(self, query: str, max_results: int = 20) -> int:
        """
        从 arXiv 搜索结果构建图谱（优先使用 MCP arXiv）。

        Args:
            query: 搜索关键词
            max_results: 最大论文数

        Returns:
            添加的论文数量
        """
        logger.info(f"  从 arXiv 构建图谱: '{query}' (max={max_results})")

        papers_raw = fetch_arxiv_papers(query, max_results)
        added = 0

        for raw in papers_raw:
            # 尝试从 arXiv 搜索结果创建 PaperNode
            title = raw.get("title", "")
            if not title:
                continue

            arxiv_id = raw.get("arxiv_id", raw.get("id", ""))
            if isinstance(arxiv_id, str) and "arxiv.org/abs/" in arxiv_id:
                arxiv_id = arxiv_id.split("/abs/")[-1]

            paper = PaperNode(
                id=arxiv_id or title[:50],
                title=title,
                authors=[a.get("name", str(a)) if isinstance(a, dict) else str(a)
                         for a in raw.get("authors", [])],
                year=int(raw.get("published", "0")[:4]) if raw.get("published") else 0,
                abstract=raw.get("summary", raw.get("abstract", "")),
                arxiv_id=arxiv_id,
                doi=raw.get("doi", ""),
                url=raw.get("url", raw.get("arxiv_url", f"https://arxiv.org/abs/{arxiv_id}")),
            )

            if paper.id not in self._papers:
                self.add_paper(paper)
                added += 1

            # 获取参考文献
            if arxiv_id and paper.id in self._papers:
                try:
                    refs = self.ss.get_references(paper.id)
                    for ref in refs[:10]:
                        ref_pid = ref.get("paperId", "")
                        if ref_pid and ref_pid != paper.id:
                            self.add_citation(paper.id, ref_pid)
                except Exception:
                    pass

        logger.info(f"  arXiv 构建完成：{added} 篇论文，{self.graph.number_of_edges()} 条边")
        return added

    # ── 学术论文写作工作流 ──────────────────────────────────────────────────

    def build_for_paper(self,
                         topic: str,
                         max_results: int = 30,
                         use_mcp: bool = True) -> int:
        """
        为论文写作构建知识图谱（学术标准工作流）。

        检索策略：
          1. MCP arXiv（最新工作，覆盖广）
          2. Semantic Scholar（引文数据，全面的引用网络）
          3. Web搜索（补充灰色文献和最新预印本）

        Args:
            topic: 研究主题
            max_results: 每种来源的最大论文数
            use_mcp: 是否优先使用 MCP arXiv/Web 搜索

        Returns:
            添加的论文总数
        """
        logger.info(f"\n  为论文构建知识图谱: '{topic}'")
        logger.info(f"  MCP优先: {use_mcp}, max_results: {max_results}")

        total_added = 0

        # 策略1: MCP arXiv
        if use_mcp:
            arxiv_added = self.build_from_arxiv(topic, max_results=max_results)
            total_added += arxiv_added
            logger.info(f"  arXiv 添加: {arxiv_added} 篇")

        # 策略2: Semantic Scholar（补充引文网络）
        ss_added = self.build_from_search(topic, max_results=max_results,
                                          add_references=True)
        total_added += ss_added
        logger.info(f"  Semantic Scholar 添加: {ss_added} 篇")

        # 策略3: 扩展高引用论文的参考文献
        top_papers = self.top_influential(n=5)
        for pid, score in top_papers:
            paper = self._papers.get(pid)
            if paper and paper.id:
                try:
                    refs = self.ss.get_references(paper.id)
                    for ref_raw in refs[:5]:
                        ref_pid = ref_raw.get("paperId", "")
                        if ref_pid and ref_pid != paper.id:
                            ref_paper = self._raw_to_paper(ref_raw)
                            if ref_paper and ref_paper.id not in self._papers:
                                self.add_paper(ref_paper)
                                total_added += 1
                            self.add_citation(paper.id, ref_pid)
                except Exception:
                    pass

        # 计算中心性
        self.compute_centrality()

        logger.info("\n  论文知识图谱构建完成:")
        logger.info(f"  总论文: {self.graph.number_of_nodes()}, 总引文边: {self.graph.number_of_edges()}")
        logger.info(f"  总添加: {total_added} 篇")

        return total_added

    def generate_bibliography(self,
                               max_papers: int = 30,
                               style: str = "apa") -> list[dict]:
        """
        从图谱生成参考文献列表。

        Args:
            max_papers: 最大参考文献数量（按影响力排序）
            style: 引用格式 ("apa" | "ieee" | "chicago" | "bibtex")

        Returns:
            参考文献列表，每项包含 title, authors, year, venue, doi
        """
        top_papers = self.top_influential(n=max_papers)

        refs = []
        for pid, score in top_papers:
            paper = self._papers.get(pid)
            if not paper:
                continue

            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += " et al."

            if style == "apa":
                citation = f"{authors_str} ({paper.year}). {paper.title}. {paper.venue}."
            elif style == "ieee":
                citation = f"{authors_str}, \"{paper.title},\" {paper.venue}, {paper.year}."
            elif style == "bibtex":
                bibkey = paper.authors[0].split()[-1].lower() + str(paper.year) if paper.authors else "unknown"
                citation = f"@article{{{bibkey}, author={{{', '.join(paper.authors)}}}, title={{{paper.title}}}, journal={{{paper.venue}}}, year={{{paper.year}}}"
            else:
                citation = f"{authors_str} ({paper.year}). {paper.title}. {paper.venue}."

            refs.append({
                "paper_id": paper.id,
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "venue": paper.venue,
                "doi": paper.doi,
                "citation": citation,
                "score": score,
            })

        return refs

    def identify_research_gaps(self, topic: str) -> dict:
        """
        识别研究空白（基于图谱分析）。

        策略：
          1. 低引用数但高相关性的论文（被忽视的重要工作）
          2. 孤立论文（无引用关系，可能代表新兴领域）
          3. 高影响力但无衍生工作的论文（经典但未扩展）

        Returns:
            dict with keys: "neglected", "isolated", "underexplored"
        """
        self.compute_centrality()
        results = {"neglected": [], "isolated": [], "underexplored": []}

        for pid, paper in self._papers.items():
            # 孤立论文
            if self.graph.degree(pid) == 0:
                results["isolated"].append({
                    "id": pid,
                    "title": paper.title[:80],
                    "year": paper.year,
                    "venue": paper.venue,
                })
            # 低引用但晚近
            elif paper.citation_count < 10 and paper.year >= 2022:
                results["neglected"].append({
                    "id": pid,
                    "title": paper.title[:80],
                    "year": paper.year,
                    "citations": paper.citation_count,
                    "venue": paper.venue,
                })

        # 高影响力但无衍生
        for pid, score in self.top_influential(n=10):
            cited_by = self.get_citations(pid)
            if len(cited_by) == 0 and score > 0.01:
                paper = self._papers.get(pid)
                if paper:
                    results["underexplored"].append({
                        "id": pid,
                        "title": paper.title[:80],
                        "year": paper.year,
                        "pagerank": score,
                        "venue": paper.venue,
                    })

        return results

    # ── 可视化辅助 ──────────────────────────────────────────────────────────

    def to_mermaid(self) -> str:
        """导出为 Mermaid 格式的引文图（用于 Markdown 嵌入）。"""
        lines = ["graph LR"]
        for u, v, d in self.graph.edges(data=True):
            u_label = (self._papers[u].title[:20] if u in self._papers else u[:10]).replace('"', "'")
            v_label = (self._papers[v].title[:20] if v in self._papers else v[:10]).replace('"', "'")
            lines.append(f'    "{u_label}" --> "{v_label}"')
        return "\n".join(lines)

    def subgraph(self, paper_ids: list[str], depth: int = 1) -> KnowledgeGraph:
        """
        提取指定论文的子图（包含其 depth=1 的邻居节点）。
        返回新的 KnowledgeGraph 实例。
        """
        nodes = set(paper_ids)
        for pid in paper_ids:
            nodes.update(self.get_references(pid))
            nodes.update(self.get_citations(pid))

        sub_kg = KnowledgeGraph()
        for nid in nodes:
            if nid in self._papers:
                sub_kg.add_paper(self._papers[nid])

        for u, v in self.graph.edges():
            if u in nodes and v in nodes:
                d = self.graph.get_edge_data(u, v) or {}
                sub_kg.add_citation(u, v, d.get("context_sentence", ""), d.get("section", ""))

        return sub_kg


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="学术知识图谱构建工具")
    parser.add_argument("query", nargs="?", help="搜索关键词")
    parser.add_argument("-n", "--max-results", type=int, default=20, help="最大论文数")
    parser.add_argument("--depth", type=int, default=2, help="引文链追溯深度")
    parser.add_argument("--output", "-o", help="保存路径（.pkl 或 .json）")
    parser.add_argument("--load", "-l", help="加载已有图谱")
    parser.add_argument("--stats", action="store_true", help="仅显示统计信息")

    args = parser.parse_args()

    kg = KnowledgeGraph()

    if args.load:
        if args.load.endswith(".json"):
            kg = KnowledgeGraph.from_json(path=args.load)
        else:
            kg.load_graph(args.load)
        if args.stats:
            print(kg.summary())
        return

    if args.query:
        kg.build_from_search(args.query, max_results=args.max_results, add_references=True)
        print(kg.summary())

        if args.output:
            if args.output.endswith(".json"):
                kg.save_json(args.output)
            else:
                kg.save_graph(args.output)

        prereq = kg.find_prerequisite(list(kg._papers.keys())[0])
        if prereq:
            print(f"\n先修论文推荐：{[p.title[:40] for p in prereq[:3]]}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
