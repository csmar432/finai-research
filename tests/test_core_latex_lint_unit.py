"""Unit tests for scripts/core/latex_lint.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ll():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import latex_lint as l
    yield l
    if _p in sys.path:
        sys.path.remove(_p)


class TestLintIssue:
    def test_init(self, ll):
        issue = ll.LintIssue(
            severity=ll.Severity.ERROR,
            line=42,
            message="Missing closing brace",
            rule="unclosed_brace",
        )
        assert issue.line == 42
        assert issue.context == ""


class TestLatexLintChecker:
    def test_init(self, ll, tmp_path):
        tex = tmp_path / "paper.tex"
        tex.write_text("Hello world")
        checker = ll.LatexLintChecker(tex_path=str(tex))
        assert checker is not None
