"""Unit tests for scripts/knowledge_graph.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def kg():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import knowledge_graph as k
    yield k
    if _p in sys.path:
        sys.path.remove(_p)


class TestPaperNode:
    def test_init(self, kg):
        node = kg.PaperNode(
            id="p1",
            title="Carbon Trading and Innovation",
            authors=["Smith, J.", "Jones, A."],
            year=2024,
            venue="JFE",
        )
        assert node.id == "p1"
        assert node.year == 2024
        assert len(node.authors) == 2


class TestCitationEdge:
    def test_init(self, kg):
        edge = kg.CitationEdge(
            citing_paper="p2",
            cited_paper="p1",
            context_sentence="This paper builds on Smith (2024)",
            section="introduction",
        )
        assert edge.citing_paper == "p2"
        assert edge.cited_paper == "p1"


class TestKnowledgeGraph:
    def test_init(self, kg):
        graph = kg.KnowledgeGraph()
        assert graph is not None


class TestClients:
    def test_semantic_scholar_client(self, kg):
        assert hasattr(kg, "SemanticScholarClient")

    def test_citracer_client(self, kg):
        assert hasattr(kg, "CitracerClient")
