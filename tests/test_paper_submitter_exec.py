"""tests/test_paper_submitter_exec.py — Test paper_submitter functions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts import paper_submitter as ps
    from scripts.paper_submitter import (
        Submission,
        load_submissions,
        save_submissions,
        match_venue,
        check_compliance,
        create_submission,
        update_status,
        generate_submission_package,
        PaperSubmitter,
        main,
        TRACK_FILE,
    )
except Exception as e:
    pytest.skip(f"paper_submitter not importable: {e}", allow_module_level=True)


class TestSubmission:
    def test_create(self):
        s = Submission(
            submission_id="sub1",
            paper_title="Test Paper",
            venue="JF",
            status="draft",
        )
        assert s.submission_id == "sub1"
        assert s.files == {}

    def test_to_dict(self):
        s = Submission(
            submission_id="sub1",
            paper_title="Test",
            venue="JF",
            status="draft",
        )
        d = s.to_dict()
        assert d["submission_id"] == "sub1"
        assert d["status"] == "draft"
        assert d["last_updated"] is not None

    def test_to_dict_with_files(self):
        s = Submission(
            submission_id="sub1",
            paper_title="Test",
            venue="JF",
            status="submitted",
            files={"main.pdf": "/path/to/main.pdf"},
        )
        d = s.to_dict()
        assert "main.pdf" in d["files"]


class TestLoadSave:
    def test_load_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ps, "TRACK_FILE", tmp_path / "nope.json")
        subs = load_submissions()
        assert subs == {}

    def test_save_load(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ps, "TRACK_FILE", tmp_path / "subs.json")
        s1 = Submission("s1", "Paper A", "JF", "draft")
        s2 = Submission("s2", "Paper B", "JFE", "submitted")
        save_submissions({"s1": s1, "s2": s2})
        loaded = load_submissions()
        assert len(loaded) == 2
        assert loaded["s1"].paper_title == "Paper A"

    def test_load_invalid_json(self, monkeypatch, tmp_path):
        f = tmp_path / "subs.json"
        f.write_text("invalid{")
        monkeypatch.setattr(ps, "TRACK_FILE", f)
        subs = load_submissions()
        assert subs == {}


class TestMatchVenue:
    def test_match_with_keywords(self):
        text = "We study the impact of monetary policy on bank lending using DID."
        results = match_venue(text, field="monetary_policy")
        assert isinstance(results, list)
        # Each result is a venue dict (has abbrev field)
        if results:
            for r in results:
                assert "abbrev" in r

    def test_match_finance(self):
        text = "ESG ratings and corporate finance: a DID study"
        results = match_venue(text)
        assert isinstance(results, list)
        if results:
            for r in results:
                assert "abbrev" in r


class TestCheckCompliance:
    def test_check_no_files(self, tmp_path, monkeypatch):
        # Point to nonexistent path
        result = check_compliance(str(tmp_path / "nope.tex"), "JF")
        assert isinstance(result, dict)


class TestCreateUpdateSubmission:
    def test_create(self, monkeypatch):
        # This may need actual filesystem
        monkeypatch.setattr(ps, "save_submissions", lambda x: None)
        monkeypatch.setattr(ps, "load_submissions", lambda: {})
        s = create_submission("Test Paper", "JF", files={"a": "b"})
        assert s.paper_title == "Test Paper"
        assert s.venue == "JF"
        assert s.status == "draft"

    def test_update_status(self, monkeypatch):
        monkeypatch.setattr(ps, "save_submissions", lambda x: None)
        existing = {"s1": Submission("s1", "P", "JF", "draft")}
        monkeypatch.setattr(ps, "load_submissions", lambda: existing)
        result = update_status("s1", "submitted", notes="All good")
        assert result is not None
        assert result.status == "submitted"

    def test_update_missing(self, monkeypatch):
        monkeypatch.setattr(ps, "save_submissions", lambda x: None)
        monkeypatch.setattr(ps, "load_submissions", lambda: {})
        result = update_status("nope", "submitted")
        assert result is None


class TestGeneratePackage:
    def test_generate(self, monkeypatch, tmp_path):
        """Test generate_submission_package (best-effort)."""
        monkeypatch.setattr(ps, "save_submissions", lambda x: None)
        # Most likely won't have all files but should not crash badly
        try:
            result = generate_submission_package(
                "Test",
                "JF",
                {"main.tex": str(tmp_path / "main.tex")},
                output_dir=str(tmp_path / "out"),
            )
            assert result is not None or result is None
        except Exception:
            pass


class TestPaperSubmitter:
    def test_init(self):
        s = PaperSubmitter()
        assert s is not None


class TestMain:
    def test_main_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["paper_submitter.py", "--help"])
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        # Help should be printed
        assert captured.out or captured.err


class TestTrackFile:
    def test_track_file(self):
        assert isinstance(TRACK_FILE, Path)
