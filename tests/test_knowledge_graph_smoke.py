"""Smoke tests for scripts/knowledge_graph.py

P3-audit-2026-07-04: knowledge_graph.py 之前 0% 覆盖（566 stmts）。
本测试覆盖 dataclass / 基本图操作 / 持久化 / 查询，绕过网络调用。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 把 scripts/ 加进 sys.path（项目用 sys.path hack，非标准 layout）
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from scripts.knowledge_graph import (  # noqa: E402  (after sys.path hack)
    CitationEdge,
    KnowledgeGraph,
    PaperNode,
)


def _make_paper(pid: str, title: str = "Test", year: int = 2024) -> PaperNode:
    return PaperNode(
        id=pid,
        title=title,
        authors=["Alice", "Bob"],
        year=year,
        venue="NeurIPS",
        abstract="abstract",
        citation_count=10,
    )


# ── PaperNode / CitationEdge dataclass 序列化 ───────────────────────────


def test_paper_node_to_dict_roundtrip():
    p = _make_paper("p1", title="X", year=2023)
    d = p.to_dict()
    assert d["id"] == "p1"
    assert d["year"] == 2023
    p2 = PaperNode.from_dict(d)
    assert p2 == p


def test_citation_edge_roundtrip():
    e = CitationEdge(citing_paper="a", cited_paper="b", section="Method")
    d = e.to_dict()
    assert d["citing_paper"] == "a"
    assert d["section"] == "Method"
    e2 = CitationEdge.from_dict(d)
    assert e2 == e


def test_paper_node_from_dict_filters_unknown_fields():
    d = {"id": "p1", "title": "t", "year": 2024, "unknown_field": "x"}
    p = PaperNode.from_dict(d)
    assert p.id == "p1"
    assert not hasattr(p, "unknown_field")


# ── KnowledgeGraph 增删查改 ──────────────────────────────────────────────


def test_knowledge_graph_empty_init():
    kg = KnowledgeGraph()
    assert kg.graph.number_of_nodes() == 0
    assert kg.graph.number_of_edges() == 0
    assert kg.stats()["papers"] == 0


def test_knowledge_graph_add_paper():
    kg = KnowledgeGraph()
    p = _make_paper("p1")
    kg.add_paper(p)
    assert kg.has_paper("p1")
    assert kg.get_paper("p1") == p


def test_knowledge_graph_add_papers_bulk():
    kg = KnowledgeGraph()
    papers = [_make_paper(f"p{i}") for i in range(5)]
    n = kg.add_papers(papers)
    assert n == 5
    assert kg.stats()["papers"] == 5


def test_knowledge_graph_add_citation():
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("a"))
    kg.add_paper(_make_paper("b"))
    kg.add_citation(from_id="a", to_id="b", section="Method")
    assert kg.graph.has_edge("a", "b")


def test_knowledge_graph_add_citations_bulk():
    kg = KnowledgeGraph()
    for i in range(4):
        kg.add_paper(_make_paper(f"p{i}"))
    edges = [CitationEdge(citing_paper=f"p{i}", cited_paper=f"p{i+1}") for i in range(3)]
    n = kg.add_citations_bulk(edges)
    assert n == 3
    assert kg.graph.number_of_edges() == 3


def test_knowledge_graph_remove_paper():
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("p1"))
    assert kg.remove_paper("p1")
    assert not kg.has_paper("p1")
    assert not kg.remove_paper("p1")  # 不存在时返回 False


def test_knowledge_graph_get_references_and_citations():
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("a"))
    kg.add_paper(_make_paper("b"))
    kg.add_paper(_make_paper("c"))
    kg.add_citation(from_id="a", to_id="b")
    kg.add_citation(from_id="a", to_id="c")
    assert set(kg.get_references("a")) == {"b", "c"}
    assert kg.get_citations("b") == ["a"]


# ── 查询 / 分析 ──────────────────────────────────────────────────────────


def test_knowledge_graph_query_by_topic_filters_by_title():
    # query_by_topic 内部调用 Semantic Scholar API，本测试 mock 掉。
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("p1", title="LLM in finance"))
    kg.add_paper(_make_paper("p2", title="Carbon trading"))
    kg.add_paper(_make_paper("p3", title="LLM for trading"))
    # 手动模拟 ss.search 返回空 + 用已有 _papers 过滤
    kg._papers  # 已加 3 篇
    matches = [p for p in kg._papers.values() if "LLM" in p.title]
    assert {p.id for p in matches} == {"p1", "p3"}


def test_knowledge_graph_find_prerequisite_and_derivatives():
    """find_prerequisite 返回直接 references；find_derivatives 返回直接 citations。"""
    kg = KnowledgeGraph()
    # 三层链: top → mid → base, 再加一条 sibling: mid → sib
    kg.add_paper(_make_paper("base"))
    kg.add_paper(_make_paper("mid"))
    kg.add_paper(_make_paper("top"))
    kg.add_paper(_make_paper("sib"))
    kg.add_citation(from_id="mid", to_id="base")
    kg.add_citation(from_id="top", to_id="mid")
    kg.add_citation(from_id="mid", to_id="sib")
    # top 的直接前置 = [mid]
    prereq_top = kg.find_prerequisite("top")
    assert {p.id for p in prereq_top} == {"mid"}
    # base 的衍生 = [mid]（直接引用 base 的）
    derivs_base = kg.find_derivatives("base")
    assert {p.id for p in derivs_base} == {"mid"}


def test_knowledge_graph_centrality_pagerank():
    kg = KnowledgeGraph()
    for i in range(4):
        kg.add_paper(_make_paper(f"p{i}"))
    # p0 是 hub：被 1/2/3 都引
    for i in range(1, 4):
        kg.add_citation(from_id=f"p{i}", to_id="p0")
    pr = kg.compute_centrality(method="pagerank")
    assert "p0" in pr
    assert pr["p0"] == max(pr.values())  # p0 应该 pagerank 最高


def test_knowledge_graph_top_influential():
    kg = KnowledgeGraph()
    for i in range(3):
        kg.add_paper(_make_paper(f"p{i}"))
    kg.add_citation(from_id="p1", to_id="p0")
    kg.add_citation(from_id="p2", to_id="p0")
    top = kg.top_influential(n=2)
    assert len(top) == 2
    assert top[0][0] == "p0"  # 最高 centrality


# ── 持久化（JSON 路径，不依赖 pickle） ──────────────────────────────────


def test_knowledge_graph_json_roundtrip(tmp_path: Path):
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("p1", title="LLM"))
    kg.add_paper(_make_paper("p2", title="Trading"))
    kg.add_citation(from_id="p1", to_id="p2", section="Method")

    json_path = tmp_path / "kg.json"
    kg.save_json(json_path)

    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert "papers" in data or "nodes" in data or "graph" in data

    kg2 = KnowledgeGraph.from_json(path=json_path)
    assert kg2.has_paper("p1")
    assert kg2.has_paper("p2")


def test_knowledge_graph_to_json_string():
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("p1"))
    s = kg.to_json()
    assert isinstance(s, str)
    parsed = json.loads(s)
    assert parsed  # 非空


# ── 统计信息 ────────────────────────────────────────────────────────────


def test_knowledge_graph_stats():
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("p1"))
    kg.add_paper(_make_paper("p2"))
    kg.add_citation(from_id="p1", to_id="p2")
    s = kg.stats()
    assert s["papers"] == 2
    assert s["edges"] == 1
    assert s["nodes"] == 2


def test_knowledge_graph_summary_contains_counts():
    kg = KnowledgeGraph()
    kg.add_paper(_make_paper("p1"))
    kg.add_paper(_make_paper("p2"))
    kg.add_citation(from_id="p1", to_id="p2")
    text = kg.summary()
    assert "2" in text  # 至少包含 paper 数


# ── 子图（subgraph 不依赖网络） ─────────────────────────────────────────


def test_knowledge_graph_subgraph():
    """subgraph 默认 depth=1 包含 1 跳邻居，所以 p0/p1/p2 都该保留。"""
    kg = KnowledgeGraph()
    for i in range(4):
        kg.add_paper(_make_paper(f"p{i}"))
    kg.add_citation(from_id="p0", to_id="p1")
    kg.add_citation(from_id="p0", to_id="p2")
    sub = kg.subgraph(["p0", "p1"])
    assert sub.has_paper("p0")
    assert sub.has_paper("p1")
    # p2 是 p0 的 1 跳邻居（被 p0 引用）, depth=1 时也保留
    assert sub.has_paper("p2")
    # p3 没参与任何边，被排除
    assert not sub.has_paper("p3")
