"""Unit tests for scripts/core/pdf_vision_check.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pvc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import pdf_vision_check as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestPDFVisionIssue:
    def test_init(self, pvc):
        issue = pvc.PDFVisionIssue(
            severity="high",
            page=1,
            location="figure 1",
            description="Figure too small",
        )
        assert issue.page == 1
        assert issue.suggestion == ""


class TestPDFVisionChecker:
    def test_init(self, pvc):
        checker = pvc.PDFVisionChecker()
        assert checker is not None
