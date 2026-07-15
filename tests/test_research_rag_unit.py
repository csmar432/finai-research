"""Unit tests for scripts/research_rag.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def rr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import research_rag as r
    yield r
    if _p in sys.path:
        sys.path.remove(_p)


class TestChunk:
    def test_init(self, rr):
        chunk = rr.Chunk(
            id="c1",
            content="This paper examines carbon trading effects",
            paper_id="p1",
            section="abstract",
            source="arxiv",
            chunk_index=0,
            start_char=0,
            end_char=44,
        )
        assert chunk.id == "c1"
        assert chunk.content == "This paper examines carbon trading effects"


class TestRetrievalResult:
    def test_init(self, rr):
        result = rr.RetrievalResult(
            chunk=None,  # placeholder
            score=0.95,
            rank=1,
        )
        assert result.score == 0.95
        assert result.rank == 1
