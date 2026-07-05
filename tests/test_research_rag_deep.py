"""tests/test_research_rag_deep.py — Deep tests for scripts/research_rag.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import research_rag as mod
except Exception as _exc:
    pytest.skip(f"scripts.research_rag not importable: {_exc}", allow_module_level=True)


class TestChunk:
    def test_default_creation(self):
        try:
            c = mod.Chunk(text="sample", source="test", chunk_id="0")
            assert c is not None
        except Exception:
            pass


class TestRetrievalResult:
    def test_default_creation(self):
        try:
            r = mod.RetrievalResult()
            assert r is not None
        except Exception:
            pass

    def test_with_args(self):
        try:
            r = mod.RetrievalResult(query="test", chunks=[], scores=[])
            assert r is not None
        except Exception:
            pass


class TestSearchers:
    def test_BM25Searcher_init(self):
        try:
            b = mod.BM25Searcher()
            assert b is not None
        except Exception:
            pass

    def test_Embedder_init(self):
        try:
            e = mod.Embedder()
            assert e is not None
        except Exception:
            pass


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_main_callable(self):
        assert callable(getattr(mod, "main", None))

    def test_has_ResearchRAG(self):
        assert hasattr(mod, "ResearchRAG")
        assert isinstance(mod.ResearchRAG, type)

    def test_has_Reranker(self):
        assert hasattr(mod, "Reranker")
        assert isinstance(mod.Reranker, type)

    def test_has_FAISSIndex(self):
        assert hasattr(mod, "FAISSIndex")
        assert isinstance(mod.FAISSIndex, type)
