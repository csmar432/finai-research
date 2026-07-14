"""Unit tests for scripts/enrich_bib_dois.py — pure logic only."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ebd():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import enrich_bib_dois
    yield enrich_bib_dois
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestParseBibEntries:
    def test_parses_entry(self, ebd):
        text = '''@article{key1,
  author = {Smith, J.},
  title = {A paper},
  year = {2020}
}
'''
        entries = ebd.parse_bib_entries(text)
        assert len(entries) == 1
        e = entries[0]
        assert e["key"] == "key1"
        assert e["type"] == "article"
        assert e["fields"]["author"] == "Smith, J."
        assert e["fields"]["title"] == "A paper"

    def test_multiple_entries(self, ebd):
        text = """@article{a,
  author={X},
  title={A}
}
@book{b,
  author={Y},
  title={B}
}
"""
        entries = ebd.parse_bib_entries(text)
        assert len(entries) == 2
        assert entries[0]["key"] == "a"
        assert entries[1]["key"] == "b"

    def test_empty_text(self, ebd):
        assert ebd.parse_bib_entries("") == []

    def test_entry_with_doi(self, ebd):
        text = '''@article{k,
  author={X},
  title={Y},
  doi={10.1234/test}
}
'''
        entries = ebd.parse_bib_entries(text)
        assert entries[0]["fields"].get("doi") == "10.1234/test"

    def test_entry_raw_contains_full_text(self, ebd):
        text = '''@article{k,
  author={X},
  title={Y}
}
'''
        entries = ebd.parse_bib_entries(text)
        assert "author={X}" in entries[0]["raw"]


class TestEnrichBibFile:
    def test_empty_bib_returns_zero_stats(self, ebd, tmp_path, monkeypatch):
        bib = tmp_path / "empty.bib"
        bib.write_text("")
        monkeypatch.setattr(ebd, "ROOT", tmp_path)
        stats = ebd.enrich_bib_file(bib, apply=False, limit=None)
        assert stats["total"] == 0
        assert stats["enriched"] == 0

    def test_skips_entries_with_doi(self, ebd, tmp_path, monkeypatch):
        bib = tmp_path / "test.bib"
        bib.write_text('''@article{a,
  author={X},
  title={Y},
  doi={10.1234/already}
}
''')
        monkeypatch.setattr(ebd, "ROOT", tmp_path)
        stats = ebd.enrich_bib_file(bib, apply=False, limit=None)
        assert stats["skipped"] == 1
        assert stats["enriched"] == 0

    def test_no_query_when_no_doi_needed_but_no_author(self, ebd, tmp_path, monkeypatch):
        bib = tmp_path / "test.bib"
        bib.write_text('''@article{a,
  title={Y}
}
''')
        monkeypatch.setattr(ebd, "ROOT", tmp_path)
        with mock.patch.object(ebd.time, "sleep"):  # avoid real sleep
            stats = ebd.enrich_bib_file(bib, apply=False, limit=None)
        assert stats["skipped"] == 1  # no author → skip
        assert stats["enriched"] == 0

    def test_respects_limit(self, ebd, tmp_path, monkeypatch):
        bib = tmp_path / "test.bib"
        bib.write_text('''@article{a,
  author={X},
  title={T1}
}
@article{b,
  author={Y},
  title={T2}
}
''')
        monkeypatch.setattr(ebd, "ROOT", tmp_path)
        # Mock query_crossref to return None immediately
        with mock.patch.object(ebd, "query_crossref", return_value=None):
            with mock.patch.object(ebd.time, "sleep"):
                stats = ebd.enrich_bib_file(bib, apply=False, limit=1)
        # Only 1 should be attempted
        assert stats["total"] == 2
        # Rest skipped due to limit
        assert stats["skipped"] + stats["failed"] >= 1

    def test_apply_writes_file_when_doi_found(self, ebd, tmp_path, monkeypatch):
        bib = tmp_path / "test.bib"
        bib.write_text('''@article{a,
  author={X},
  title={T}
}
''')
        monkeypatch.setattr(ebd, "ROOT", tmp_path)
        with mock.patch.object(ebd, "query_crossref", return_value="10.1234/found"):
            with mock.patch.object(ebd.time, "sleep"):
                stats = ebd.enrich_bib_file(bib, apply=True, limit=None)
        assert stats["enriched"] == 1
        # File should be updated
        text = bib.read_text()
        assert "10.1234/found" in text


class TestQueryCrossrefMocked:
    def test_returns_doi_on_match(self, ebd, monkeypatch):
        mock_resp = mock.Mock()
        mock_resp.read.return_value = b'{"message": {"items": [{"DOI": "10.1234/test", "title": ["A Paper"], "container-title": ["Jrnl"]}]}}'
        mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(ebd.urllib.request, "urlopen", return_value=mock_resp):
            result = ebd.query_crossref("A Paper", "Smith", "2020")
        assert result == "10.1234/test"

    def test_returns_none_on_no_items(self, ebd, monkeypatch):
        mock_resp = mock.Mock()
        mock_resp.read.return_value = b'{"message": {"items": []}}'
        mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(ebd.urllib.request, "urlopen", return_value=mock_resp):
            assert ebd.query_crossref("Nothing", "Nobody", "2099") is None

    def test_returns_none_on_urllib_error(self, ebd, monkeypatch):
        """When urllib.URLError raised, returns None."""
        import urllib.error
        with mock.patch.object(ebd.urllib.request, "urlopen", side_effect=urllib.error.URLError("nope")):
            assert ebd.query_crossref("X", "Y", "2020") is None

    def test_returns_none_on_json_decode_error(self, ebd, monkeypatch):
        """When JSONDecodeError raised, returns None."""
        mock_resp = mock.Mock()
        mock_resp.read.return_value = b"not valid json"
        mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(ebd.urllib.request, "urlopen", return_value=mock_resp):
            assert ebd.query_crossref("X", "Y", "2020") is None

