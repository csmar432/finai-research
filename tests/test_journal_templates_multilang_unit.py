"""Unit tests for scripts/journal_templates_multilang.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def jtm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import journal_templates_multilang as j
    yield j
    if _p in sys.path:
        sys.path.remove(_p)


class TestJournalTemplate:
    def test_init(self, jtm):
        tpl = jtm.JournalTemplate(
            name="Journal of Finance",
            short_name="JF",
            category="english_top",
            description="Top finance journal",
            latex_code=r"\documentclass{jf}",
            bibliography_style="jf",
            required_packages=["amsmath", "graphicx"],
            page_limit=50,
            author_notes=False,
            blind_review=True,
            url="https://afajof.org",
        )
        assert tpl.short_name == "JF"
        assert tpl.blind_review is True
        assert tpl.url == "https://afajof.org"
