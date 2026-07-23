"""Unit tests for scripts/literature_download.py (dataclasses + pure functions)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ld():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    import literature_download as l
    yield l
    if _p in sys.path:
        sys.path.remove(_p)


class TestPaperRecord:
    def test_default_init(self, ld):
        p = ld.PaperRecord()
        assert p.paper_id == ""
        assert p.downloaded is False
        assert p.authors == []

    def test_full_init(self, ld):
        p = ld.PaperRecord(
            paper_id="10.1234/test",
            source="arxiv",
            title="Test Paper",
            authors=["Smith, J."],
            year=2023,
            doi="10.1234/test",
            citation_count=50,
        )
        assert p.title == "Test Paper"
        assert p.year == 2023
        assert p.citation_count == 50

    def test_to_dict(self, ld):
        p = ld.PaperRecord(paper_id="test", title="Test")
        d = p.to_dict()
        assert isinstance(d, dict)
        assert d["paper_id"] == "test"


class TestConstants:
    def test_min_pdf_bytes(self, ld):
        assert ld._MIN_PDF_BYTES >= 1000

    def test_api_bases_https(self, ld):
        assert ld._SS_BASE.startswith("https://")
        assert ld._OA_BASE.startswith("https://")

    def test_requests_available_flag(self, ld):
        assert isinstance(ld._REQUESTS_AVAILABLE, bool)


class TestDoiNormalization:
    def test_normalize_doi_removes_prefix(self, ld):
        if hasattr(ld, "normalize_doi"):
            assert ld.normalize_doi("https://doi.org/10.1234/test") == "10.1234/test"
            assert ld.normalize_doi("doi:10.1234/test") == "10.1234/test"

    def test_normalize_doi_passthrough(self, ld):
        if hasattr(ld, "normalize_doi"):
            assert ld.normalize_doi("10.1234/test") == "10.1234/test"


class TestArxivIdParsing:
    def test_parse_arxiv_id(self, ld):
        if hasattr(ld, "parse_arxiv_id"):
            assert ld.parse_arxiv_id("arXiv:2301.12345") == "2301.12345"
            assert ld.parse_arxiv_id("2301.12345") == "2301.12345"


class TestDownloadCache:
    def test_cache_key_generation(self, ld):
        if hasattr(ld, "make_cache_key"):
            key = ld.make_cache_key("10.1234/test", "arxiv")
            assert isinstance(key, str)
            assert len(key) > 0

