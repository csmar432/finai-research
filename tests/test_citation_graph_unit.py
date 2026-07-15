"""Unit tests for scripts/citation_graph.py (dataclass logic only)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def cg():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import citation_graph as c
    yield c
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestPaperNode:
    def test_to_dict_roundtrip(self, cg):
        node = cg.PaperNode(
            paper_id="S2:123",
            title="Test Paper",
            year=2022,
            venue="JFE",
            citation_count=50,
            influential_cites=5,
            authors=["Smith, J."],
            doi="10.1234/test",
        )
        d = node.to_dict()
        assert d["paper_id"] == "S2:123"
        assert d["title"] == "Test Paper"
        assert d["citation_count"] == 50


class TestCitationEdge:
    def test_default_weight(self, cg):
        edge = cg.CitationEdge(from_id="A", to_id="B")
        assert edge.weight == 1.0

    def test_custom_weight(self, cg):
        edge = cg.CitationEdge(from_id="A", to_id="B", weight=2.5)
        assert edge.weight == 2.5


class TestCitationGraph:
    def test_empty_graph(self, cg):
        g = cg.CitationGraph()
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_add_node(self, cg):
        g = cg.CitationGraph()
        node = cg.PaperNode(
            paper_id="S2:1", title="A", year=2020,
            venue="JFE", citation_count=10, influential_cites=1,
            authors=["Smith"],
        )
        g.add_node(node)
        assert "S2:1" in g.nodes
        assert g.nodes["S2:1"].title == "A"

    def test_add_edge_updates_degree(self, cg):
        g = cg.CitationGraph()
        n1 = cg.PaperNode(paper_id="A", title="A", year=2020, venue="JFE",
                          citation_count=5, influential_cites=0, authors=[])
        n2 = cg.PaperNode(paper_id="B", title="B", year=2021, venue="JF",
                          citation_count=10, influential_cites=0, authors=[])
        g.add_node(n1)
        g.add_node(n2)
        g.add_edge("A", "B")
        assert g.nodes["A"].out_degree == 1
        assert g.nodes["B"].in_degree == 1

    def test_add_edge_missing_node_no_crash(self, cg):
        g = cg.CitationGraph()
        g.add_edge("ghost", "ghost")  # nodes don't exist
        assert len(g.edges) == 1

    def test_get_foundation_papers(self, cg):
        g = cg.CitationGraph()
        for i, year in enumerate([2015, 2018, 2019, 2022, 2023]):
            node = cg.PaperNode(
                paper_id=f"S2:{i}", title=f"Paper {i}", year=year,
                venue="JFE", citation_count=10 + i*5,
                influential_cites=0, authors=[],
            )
            g.add_node(node)
        foundation = g.get_foundation_papers(top_n=3)
        assert len(foundation) == 3
        # Should all be < 2020
        for p in foundation:
            assert p.year < 2020
        # Should be sorted by citation count desc
        counts = [p.citation_count for p in foundation]
        assert counts == sorted(counts, reverse=True)

    def test_get_frontier_papers(self, cg):
        g = cg.CitationGraph()
        for i, year in enumerate([2015, 2018, 2021, 2022, 2023]):
            node = cg.PaperNode(
                paper_id=f"S2:{i}", title=f"Paper {i}", year=year,
                venue="JFE", citation_count=10 + i*5,
                influential_cites=0, authors=[],
            )
            g.add_node(node)
        frontier = g.get_frontier_papers(top_n=3)
        assert len(frontier) == 3
        for p in frontier:
            assert p.year >= 2021

    def test_get_bridge_papers(self, cg):
        g = cg.CitationGraph()
        # Node with many connections
        bridge = cg.PaperNode(paper_id="BRIDGE", title="Bridge", year=2020,
                             venue="JFE", citation_count=100,
                             influential_cites=10, authors=[])
        hub = cg.PaperNode(paper_id="HUB", title="Hub", year=2021,
                          venue="JF", citation_count=50,
                          influential_cites=5, authors=[])
        g.add_node(bridge)
        g.add_node(hub)
        # Add edges to make bridge a better bridge
        for i in range(5):
            n = cg.PaperNode(paper_id=f"N{i}", title=f"N{i}", year=2022,
                            venue="JFE", citation_count=5, influential_cites=0, authors=[])
            g.add_node(n)
            g.add_edge("BRIDGE", f"N{i}")
        g.add_edge("HUB", "BRIDGE")
        bridges = g.get_bridge_papers(top_n=2)
        assert len(bridges) == 2
        # BRIDGE has in_degree=1, out_degree=5 → score=5
        # HUB has in_degree=0, out_degree=1 → score=0
        assert bridges[0].paper_id == "BRIDGE"

    def test_to_dict_structure(self, cg):
        g = cg.CitationGraph(query="test query")
        node = cg.PaperNode(paper_id="S2:1", title="A", year=2020,
                           venue="JFE", citation_count=5,
                           influential_cites=0, authors=[])
        g.add_node(node)
        d = g.to_dict()
        assert d["query"] == "test query"
        assert d["stats"]["total_nodes"] == 1
        assert d["stats"]["total_edges"] == 0
        assert "S2:1" in d["nodes"]


class TestConstants:
    def test_ss_api_base_defined(self, cg):
        assert cg.SS_API_BASE.startswith("https://")
        assert "semanticscholar" in cg.SS_API_BASE

    def test_openalex_base_defined(self, cg):
        assert cg.OPENALEX_BASE.startswith("https://")
        assert "openalex" in cg.OPENALEX_BASE

    def test_rate_limit_positive(self, cg):
        assert cg._SS_RATE_LIMIT > 0

