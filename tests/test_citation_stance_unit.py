"""Unit tests for scripts/citation_stance.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def cs():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import citation_stance as c
    yield c
    if _p in sys.path:
        sys.path.remove(_p)


class TestCitationContext:
    def test_init(self, cs):
        ctx = cs.CitationContext(
            citation_marker="[1]",
            surrounding_text="As shown in [1], carbon trading...",
            section="introduction",
            claim="Carbon trading improves innovation",
        )
        assert ctx.citation_marker == "[1]"
        assert ctx.section == "introduction"


class TestCitationAnalysis:
    def test_init(self, cs):
        analysis = cs.CitationAnalysis(
            marker="[1]",
            stance="supportive",
            confidence=0.85,
            reasoning="Strong empirical evidence cited",
            related_claims=[],
        )
        assert analysis.stance == "supportive"
        assert analysis.confidence == 0.85


class TestCitationExtractor:
    def test_init(self, cs):
        extractor = cs.CitationExtractor()
        assert extractor is not None


class TestCitationStanceClassifier:
    def test_init(self, cs):
        classifier = cs.CitationStanceClassifier()
        assert classifier is not None


class TestCitationStance:
    def test_values(self, cs):
        # CitationStance is an enum
        assert len(list(cs.CitationStance)) >= 3
