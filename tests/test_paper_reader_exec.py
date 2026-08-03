"""Behavior tests for the local-only parts of ``paper_reader``.

Network and LLM calls are replaced with deterministic fakes.  These tests are
deliberately assertion-heavy: a swallowed exception here would make the CLI
look healthy while silently losing papers or notes.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import paper_reader as mod


class Response:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.fixture
def paper_dirs(tmp_path, monkeypatch):
    fulltext = tmp_path / "fulltext"
    meta = tmp_path / "meta"
    fulltext.mkdir()
    meta.mkdir()
    monkeypatch.setattr(mod, "PAPERS_DIR", fulltext)
    monkeypatch.setattr(mod, "META_DIR", meta)
    return fulltext, meta


def test_arxiv_and_filename_helpers_are_strictly_normalized():
    assert mod.arxiv_id_from_url("https://arxiv.org/abs/2301.12345v2") == "2301.12345v2"
    assert mod.arxiv_id_from_url("https://arxiv.org/pdf/2301.12345.pdf") == "2301.12345"
    assert mod.arxiv_id_from_url("  custom-id  ") == "custom-id"
    assert mod.sanitize_filename('a/b:c*?.pdf') == "a_b_c__.pdf"
    assert len(mod.sanitize_filename("x" * 100)) == 80


def test_loaders_handle_missing_and_truncate_text(paper_dirs):
    fulltext, meta = paper_dirs
    assert mod.load_paper_text("missing") == ""
    assert mod.load_paper_meta("missing") == {}
    (fulltext / "1.txt").write_text("abcdef", encoding="utf-8")
    (meta / "1.json").write_text('{"title":"T"}', encoding="utf-8")
    assert mod.load_paper_text("1", max_chars=3) == "abc"
    assert mod.load_paper_meta("1") == {"title": "T"}


def test_download_parses_atom_and_reuses_existing_text(paper_dirs, monkeypatch):
    fulltext, meta_dir = paper_dirs
    (fulltext / "2301.12345.txt").write_text("paper body", encoding="utf-8")
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>  A test paper\n</title><summary> An abstract </summary>
      <published>2024-02-03T00:00:00Z</published>
      <author><name>Alice</name></author><author><name>Bob</name></author>
      <category term="cs.AI" />
    </entry></feed>'''
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((getattr(request, "full_url", request), timeout))
        return Response(atom)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = mod.download_from_arxiv("https://arxiv.org/abs/2301.12345")

    assert result["arxiv_id"] == "2301.12345"
    assert result["title"] == "A test paper"
    assert result["authors"] == ["Alice", "Bob"]
    assert result["word_count"] == len("paper body")
    saved = json.loads((meta_dir / "2301.12345.json").read_text(encoding="utf-8"))
    assert saved["categories"] == ["cs.AI"]
    assert len(calls) == 2  # metadata plus PDF; existing text avoids extraction


def test_download_reports_network_and_xml_errors(paper_dirs, monkeypatch):
    import urllib.error

    monkeypatch.setattr(
        "urllib.request.urlopen",
        Mock(side_effect=urllib.error.URLError("offline")),
    )
    assert "无法连接" in mod.download_from_arxiv("2301.12345")["error"]

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response(b"<broken>"))
    assert "XML 解析失败" in mod.download_from_arxiv("2301.12345")["error"]


def test_semantic_scholar_requires_identifier_and_uses_cache(paper_dirs, monkeypatch):
    fulltext, _ = paper_dirs
    assert mod.get_from_semantic_scholar() == {"error": "需要提供 arXiv ID 或论文标题"}
    cache = fulltext / ".semantic_cache" / "2301.12345.json"
    cache.parent.mkdir()
    cache.write_text('{"title":"cached"}', encoding="utf-8")
    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: pytest.fail("cache should avoid rate limit"))
    assert mod.get_from_semantic_scholar(arxiv_id="2301.12345") == {"title": "cached"}


def test_semantic_scholar_parses_response_and_handles_http_error(paper_dirs, monkeypatch):
    import urllib.error

    payload = {"title": "T", "authors": [{"name": "A"}], "year": 2024,
               "abstract": "abs", "venue": "J", "citationCount": 7,
               "openAccessPdf": {"url": "https://example.test/t.pdf"}}
    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response(json.dumps(payload).encode()))
    result = mod.get_from_semantic_scholar(title="A paper")
    assert result == {"title": "T", "authors": ["A"], "year": 2024, "abstract": "abs",
                      "venue": "J", "citations": 7, "pdf_url": "https://example.test/t.pdf"}

    error = urllib.error.HTTPError("url", 404, "missing", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", Mock(side_effect=error))
    assert mod.get_from_semantic_scholar(arxiv_id="other") == {"error": "Semantic Scholar 上未找到论文"}


def test_notes_and_paper_reader_delegate(paper_dirs, monkeypatch):
    _, meta_dir = paper_dirs
    (meta_dir / "1.json").write_text(json.dumps({"title": "Title", "authors": ["A", "B"],
                                                  "published": "2024-01-01"}), encoding="utf-8")
    monkeypatch.setattr(mod, "summarize_with_ai", lambda aid, detail="medium": f"summary-{aid}-{detail}")
    path, content = mod.generate_reading_notes("1")
    assert Path(path).exists()
    assert "summary-1-medium" in content and "2024" in content

    reader = mod.PaperReader(storage_dir="custom")
    assert reader.storage_dir == "custom"
    assert reader.read("1") == ""
    assert reader.summarize("1") == "summary-1-medium"
    monkeypatch.setattr(mod, "ask_paper_with_ai", lambda aid, question: f"answer-{aid}-{question}")
    assert reader.ask("1", "q") == "answer-1-q"
    monkeypatch.setattr(mod, "compare_papers_with_ai", lambda aids, question: f"compare-{aids}-{question}")
    assert reader.compare("1", "2", "q") == "compare-['1', '2']-q"


def test_ai_wrappers_use_gateway_and_short_summary(monkeypatch, paper_dirs):
    _, meta_dir = paper_dirs
    (meta_dir / "1.json").write_text(json.dumps({"title": "Title", "authors": ["A"],
                                                  "abstract": "Abstract", "word_count": 10}), encoding="utf-8")
    fake_gateway = Mock()
    fake_gateway.generate.return_value = SimpleNamespace(response="generated")
    monkeypatch.setitem(sys.modules, "scripts.ai_router", types.SimpleNamespace(Task=SimpleNamespace(CODE_ANALYSIS="code")))
    monkeypatch.setitem(sys.modules, "scripts.core.llm_gateway", types.SimpleNamespace(LLMGateway=lambda **_: fake_gateway))
    assert mod.summarize_with_ai("1", detail="short") == "generated"
    assert mod.ask_paper_with_ai("1", "What?") == "generated"
    assert "generated" == mod.compare_papers_with_ai(["1", "1"], "compare")
    assert fake_gateway.generate.call_count == 3


def test_cli_read_list_and_download_commands(paper_dirs, monkeypatch, capsys):
    fulltext, meta_dir = paper_dirs
    (fulltext / "1.txt").write_text("hello world", encoding="utf-8")
    (meta_dir / "1.json").write_text(json.dumps({"arxiv_id": "1", "title": "T",
                                                  "authors": ["A"], "word_count": 11,
                                                  "downloaded_at": "2024-01-01"}), encoding="utf-8")
    mod.cmd_read(SimpleNamespace(arxiv_ids=["1"], max_chars=5))
    mod.cmd_list(SimpleNamespace())
    output = capsys.readouterr().out
    assert "显示字数" in output and "已下载论文" in output and "hello" in output

    monkeypatch.setattr(mod, "download_from_arxiv", lambda aid: {"arxiv_id": aid, "title": "T", "word_count": 1})
    result = mod.cmd_download(SimpleNamespace(arxiv_ids=["1", "2"]))
    assert [r["arxiv_id"] for r in result] == ["1", "2"]
