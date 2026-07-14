"""Unit tests for scripts/verify_bib_dois.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def vbd():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import verify_bib_dois
    yield verify_bib_dois
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


SAMPLE_BIB = """\
@article{key_a_2020,
    author = {Smith, John},
    title = {A study of something},
    year = {2020},
    doi = {10.1234/example.2020.001},
    journal = {J. of Examples},
}

@book{key_b_no_doi,
    author = {Doe, Jane},
    title = {Another Study},
    year = {2021},
}
"""


class TestRegex:
    def test_entry_re_matches_article(self, vbd):
        m = vbd.ENTRY_RE.search("@article{foo,\ntitle={X}\n}")
        assert m is not None
        assert m.group("type") == "article"
        assert m.group("key") == "foo"

    def test_entry_re_matches_book(self, vbd):
        m = vbd.ENTRY_RE.search("@book{bar,\ntitle={X}\n}")
        assert m is not None
        assert m.group("type") == "book"

    def test_field_re_extracts_doi(self, vbd):
        m = vbd.FIELD_RE.search("doi = {10.1234/example}")
        assert m is not None
        assert m.group("value") == "10.1234/example"


class TestFindBibEntries:
    def _patch(self, vbd, tmp_path, monkeypatch):
        """Point REPO at the tmp_path so relative_to works."""
        monkeypatch.setattr(vbd, "REPO", tmp_path)

    def test_extracts_both_entries(self, vbd, tmp_path, monkeypatch):
        self._patch(vbd, tmp_path, monkeypatch)
        bib = tmp_path / "test.bib"
        bib.write_text(SAMPLE_BIB)
        entries = vbd.find_bib_entries(bib)
        assert len(entries) == 2

    def test_first_entry_has_doi(self, vbd, tmp_path, monkeypatch):
        self._patch(vbd, tmp_path, monkeypatch)
        bib = tmp_path / "test.bib"
        bib.write_text(SAMPLE_BIB)
        entries = vbd.find_bib_entries(bib)
        e0 = entries[0]
        assert e0["has_doi"] is True
        assert e0["doi"] == "10.1234/example.2020.001"
        assert e0["type"] == "article"

    def test_second_entry_missing_doi(self, vbd, tmp_path, monkeypatch):
        self._patch(vbd, tmp_path, monkeypatch)
        bib = tmp_path / "test.bib"
        bib.write_text(SAMPLE_BIB)
        entries = vbd.find_bib_entries(bib)
        e1 = entries[1]
        assert e1["has_doi"] is False
        assert e1["key"] == "key_b_no_doi"
        assert e1["type"] == "book"

    def test_extracts_author_title_year(self, vbd, tmp_path, monkeypatch):
        self._patch(vbd, tmp_path, monkeypatch)
        bib = tmp_path / "test.bib"
        bib.write_text(SAMPLE_BIB)
        entries = vbd.find_bib_entries(bib)
        e0 = entries[0]
        assert "Smith" in e0["author"]
        assert "A study" in e0["title"]
        assert e0["year"] == "2020"

    def test_empty_file_returns_empty(self, vbd, tmp_path, monkeypatch):
        self._patch(vbd, tmp_path, monkeypatch)
        bib = tmp_path / "empty.bib"
        bib.write_text("")
        assert vbd.find_bib_entries(bib) == []


class TestCheckOnline:
    def test_returns_false_on_error(self, vbd, monkeypatch):
        import urllib.error
        def fake_urlopen(*a, **kw):
            raise urllib.error.URLError("nope")
        monkeypatch.setattr(vbd.urllib.request, "urlopen", fake_urlopen)
        assert vbd.check_online("10.1234/test") is False

    def test_returns_true_on_200(self, vbd, monkeypatch):
        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        monkeypatch.setattr(vbd.urllib.request, "urlopen", lambda *a, **kw: R())
        assert vbd.check_online("10.1234/test") is True

    def test_returns_false_on_non_200(self, vbd, monkeypatch):
        class R:
            status = 404
            def __enter__(self): return self
            def __exit__(self, *a): return False
        monkeypatch.setattr(vbd.urllib.request, "urlopen", lambda *a, **kw: R())
        assert vbd.check_online("10.1234/test") is False


class TestMainNoBibs:
    def test_no_bib_files_returns_zero(self, vbd, tmp_path, monkeypatch):
        """When no .bib files exist, returns 0."""
        monkeypatch.setattr(vbd, "REPO", tmp_path)
        # Override BIB_PATTERNS at module level so glob finds nothing
        monkeypatch.setattr(vbd, "BIB_PATTERNS", ["nonexistent/*.bib"])
        monkeypatch.setattr(sys, "argv", ["verify_bib_dois"])
        rc = vbd.main()
        assert rc == 0

