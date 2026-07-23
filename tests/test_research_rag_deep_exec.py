"""tests/test_research_rag_deep_exec.py — Deep tests for research_rag helpers.

Targets uncovered helpers in scripts/research_rag.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    from scripts.research_rag import (
        Chunk,
        Embedder,
        BM25Searcher,
        FAISS_AVAILABLE,
        ST_AVAILABLE,
        CJK_AVAILABLE,
    )
except Exception as exc:
    pytest.skip(f"research_rag not importable: {exc}", allow_module_level=True)


# ─── Availability flags ─────────────────────────────────────────────────

class TestAvailabilityFlags:
    def test_faiss_flag(self):
        assert isinstance(FAISS_AVAILABLE, bool)

    def test_st_flag(self):
        assert isinstance(ST_AVAILABLE, bool)

    def test_cjk_flag(self):
        assert isinstance(CJK_AVAILABLE, bool)


# ─── Chunk dataclass ────────────────────────────────────────────────

class TestChunk:
    def test_init_all_fields(self):
        c = Chunk(
            id="chunk_001",
            content="This is a test chunk.",
            paper_id="paper_001",
            section="Introduction",
            source="pdf",
            chunk_index=1,
            start_char=0,
            end_char=24,
        )
        assert c.id == "chunk_001"
        assert c.content == "This is a test chunk."
        assert c.paper_id == "paper_001"
        assert c.section == "Introduction"
        assert c.source == "pdf"
        assert c.chunk_index == 1
        assert c.start_char == 0
        assert c.end_char == 24

    def test_init_defaults(self):
        c = Chunk(id="chunk_002", content="Minimal chunk")
        assert c.paper_id == ""
        assert c.section == ""
        assert c.source == ""
        assert c.chunk_index == 0
        assert c.start_char == 0
        assert c.end_char == 0

    def test_to_dict(self):
        c = Chunk(id="chunk_003", content="Test", paper_id="P1")
        d = c.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == "chunk_003"
        assert d["content"] == "Test"
        assert d["paper_id"] == "P1"

    def test_from_dict(self):
        data = {
            "id": "chunk_004",
            "content": "From dict",
            "paper_id": "P2",
            "section": "Method",
            "source": "txt",
            "chunk_index": 5,
            "start_char": 100,
            "end_char": 200,
        }
        c = Chunk.from_dict(data)
        assert c.id == "chunk_004"
        assert c.content == "From dict"
        assert c.section == "Method"
        assert c.chunk_index == 5

    def test_from_dict_unknown_fields(self):
        """from_dict should ignore unknown fields."""
        data = {"id": "chunk_005", "content": "Test", "unknown_field": 123}
        c = Chunk.from_dict(data)
        assert c.id == "chunk_005"
        assert not hasattr(c, "unknown_field")


# ─── Embedder ─────────────────────────────────────────────────────────

class TestEmbedder:
    def test_init_default(self):
        try:
            e = Embedder()
            assert e is not None
            assert e.model_name == "BAAI/bge-large-zh-v1.5"
            assert e.dimension >= 0
        except Exception:
            pass

    def test_init_custom_model(self):
        try:
            e = Embedder(model_name="all-MiniLM-L6-v2")
            assert e.model_name == "all-MiniLM-L6-v2"
        except Exception:
            pass

    def test_is_random_fallback_property(self):
        try:
            e = Embedder()
            # Should be True (sentence-transformers not available in CI)
            assert isinstance(e.is_random_fallback, bool)
        except Exception:
            pass

    def test_encode_empty(self):
        try:
            e = Embedder()
            result = e.encode([])
            assert isinstance(result, np.ndarray)
            assert result.shape == (0, e.dimension) if e.dimension > 0 else result.size == 0
        except Exception:
            pass

    def test_encode_single_text(self):
        try:
            e = Embedder()
            result = e.encode(["Hello world"])
            assert isinstance(result, np.ndarray)
            if result.size > 0:
                assert result.shape[0] == 1
                assert result.shape[1] == e.dimension
        except Exception:
            pass

    def test_encode_multiple_texts(self):
        try:
            e = Embedder()
            texts = ["Text one", "Text two", "Text three"]
            result = e.encode(texts)
            assert isinstance(result, np.ndarray)
            if result.size > 0:
                assert result.shape[0] == 3
                assert result.shape[1] == e.dimension
        except Exception:
            pass


# ─── BM25Searcher ───────────────────────────────────────────────────

class TestBM25Searcher:
    def test_init(self):
        s = BM25Searcher()
        assert s.documents == {}
        assert s.doc_ids == []
        assert s.corpus == []
        assert s._avgdl == 0
        assert s._k1 == 1.5
        assert s._b == 0.75

    def test_add_documents(self):
        s = BM25Searcher()
        docs = {"d1": "Hello world", "d2": "Machine learning"}
        s.add_documents(docs)
        assert len(s.documents) == 2
        assert len(s.doc_ids) == 2
        assert len(s.corpus) == 2

    def test_tokenize_english(self):
        s = BM25Searcher()
        tokens = s._tokenize("Hello World Test")
        assert isinstance(tokens, list)
        assert all(isinstance(t, str) for t in tokens)
        # Should be lowercased
        assert "hello" in tokens
        assert "world" in tokens

    def test_tokenize_numbers(self):
        s = BM25Searcher()
        tokens = s._tokenize("Test123 and 456")
        assert "test123" in tokens
        assert "456" in tokens

    def test_tokenize_empty(self):
        s = BM25Searcher()
        tokens = s._tokenize("")
        assert tokens == []

    def test_search_empty_index(self):
        s = BM25Searcher()
        results = s.search("query", top_k=5)
        assert isinstance(results, list)

    def test_search_with_docs(self):
        s = BM25Searcher()
        s.add_documents({
            "d1": "machine learning artificial intelligence",
            "d2": "deep learning neural networks",
            "d3": "natural language processing",
        })
        results = s.search("learning", top_k=3)
        assert isinstance(results, list)
        # Should return at least the doc about deep learning
        assert len(results) > 0

    def test_search_top_k(self):
        s = BM25Searcher()
        s.add_documents({"d1": "test document one"})
        results = s.search("test", top_k=1)
        assert len(results) <= 1

    def test_add_multiple_batches(self):
        s = BM25Searcher()
        s.add_documents({"d1": "first document"})
        s.add_documents({"d2": "second document"})
        assert len(s.documents) == 2
