"""Unit tests for scripts/fix_mcp_stdout_banners.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def fmsb():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import fix_mcp_stdout_banners
    yield fix_mcp_stdout_banners
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestFindViolations:
    def test_no_violations_clean(self, fmsb, tmp_path):
        """Clean code has no violations."""
        f = tmp_path / "server.py"
        f.write_text('print("ok", file=sys.stderr, flush=True)\n', encoding="utf-8")
        assert fmsb.find_violations(f) == []

    def test_detects_violation_in_main(self, fmsb, tmp_path):
        """Banner in main() with 4-space indent is detected."""
        text = (
            "def main():\n"
            '    print("hello", flush=True)\n'
        )
        f = tmp_path / "server.py"
        f.write_text(text, encoding="utf-8")
        violations = fmsb.find_violations(f)
        assert len(violations) >= 1
        line_no, line = violations[0]
        assert line_no == 2
        assert "flush=True" in line

    def test_detects_multiple_violations(self, fmsb, tmp_path):
        text = (
            "def main():\n"
            '    print("first", flush=True)\n'
            '    print("second", flush=True)\n'
        )
        f = tmp_path / "server.py"
        f.write_text(text, encoding="utf-8")
        violations = fmsb.find_violations(f)
        # Both should be detected
        assert len(violations) >= 2

    def test_skips_stderr(self, fmsb, tmp_path):
        """print to stderr is not a violation."""
        text = (
            "def main():\n"
            '    print("err", file=sys.stderr, flush=True)\n'
        )
        f = tmp_path / "server.py"
        f.write_text(text, encoding="utf-8")
        assert fmsb.find_violations(f) == []

    def test_skips_error_prints(self, fmsb, tmp_path):
        """Prints containing ERROR keyword are skipped."""
        text = (
            "def main():\n"
            '    print("ERROR: bad", flush=True)\n'
        )
        f = tmp_path / "server.py"
        f.write_text(text, encoding="utf-8")
        assert fmsb.find_violations(f) == []

    def test_skips_non_main_indent(self, fmsb, tmp_path):
        """Top-level (0 indent) print is not main()-level."""
        text = 'print("module level", flush=True)\n'
        f = tmp_path / "server.py"
        f.write_text(text, encoding="utf-8")
        # 0 indent, skip
        assert fmsb.find_violations(f) == []

    def test_missing_file_returns_empty(self, fmsb, tmp_path):
        assert fmsb.find_violations(tmp_path / "missing.py") == []


class TestFixServer:
    def test_fix_server_modifies_file(self, fmsb, tmp_path):
        text = (
            "def main():\n"
            '    print("hello", flush=True)\n'
        )
        f = tmp_path / "server.py"
        f.write_text(text, encoding="utf-8")
        n = fmsb.fix_server(f)
        assert n >= 1
        # File now has stderr
        assert "file=sys.stderr" in f.read_text()

    def test_fix_server_clean_returns_zero(self, fmsb, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text('print("ok", file=sys.stderr, flush=True)\n', encoding="utf-8")
        assert fmsb.fix_server(f) == 0

    def test_fix_server_no_modify(self, fmsb, tmp_path):
        """Without violations, file unchanged."""
        text = 'print("ok", file=sys.stderr, flush=True)\n'
        f = tmp_path / "ok.py"
        f.write_text(text, encoding="utf-8")
        original = f.read_text()
        fmsb.fix_server(f)
        assert f.read_text() == original

