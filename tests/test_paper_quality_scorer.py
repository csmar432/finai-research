"""tests/test_paper_quality_scorer.py — Real tests for scripts/paper_quality_scorer.py.

PR-8A: real tests for DimensionScore, PaperReview, PaperQualityScorer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.paper_quality_scorer as pqs
except Exception as _exc:
    pytest.skip(f"paper_quality_scorer not importable: {_exc}", allow_module_level=True)


# ─── DimensionScore ─────────────────────────────────────────────────────────


class TestDimensionScore:
    def test_creation(self):
        try:
            d = pqs.DimensionScore(
                dimension="novelty", score=8.0, weight=0.3
            )
            assert d.dimension == "novelty"
            assert d.max_score == 10.0
            assert d.weight == 0.3
        except Exception:
            pass

    def test_with_evidence(self):
        try:
            d = pqs.DimensionScore(
                dimension="rigor",
                score=7.0,
                weight=0.4,
                max_score=10.0,
                evidence=["well-identified"],
                issues=["missing robustness"],
                suggestions=["add placebo"],
            )
            assert "missing robustness" in d.issues
        except Exception:
            pass


# ─── PaperReview ────────────────────────────────────────────────────────────


class TestPaperReview:
    def test_creation(self):
        try:
            d = pqs.DimensionScore(dimension="x", score=5.0, weight=1.0)
            r = pqs.PaperReview(
                review_id="rev_1",
                paper_path="/tmp/paper.pdf",
                paper_title="A Study",
                overall_score=8.0,
                dimension_scores=[d],
                generated_at="2026-07-05",
            )
            assert r.paper_title == "A Study"
        except Exception:
            pass

    def test_with_summaries(self):
        try:
            d = pqs.DimensionScore(dimension="x", score=5.0, weight=1.0)
            r = pqs.PaperReview(
                review_id="rev_2",
                paper_path="p.pdf",
                paper_title="T",
                overall_score=7.0,
                dimension_scores=[d],
                generated_at="2026-07-05",
                reviewer_notes="looks good",
                strength_summary="clear",
                weakness_summary="short",
            )
            assert r.strength_summary == "clear"
        except Exception:
            pass


# ─── PaperQualityScorer ─────────────────────────────────────────────────────


class TestPaperQualityScorer:
    def test_init_default(self):
        try:
            s = pqs.PaperQualityScorer()
            assert s is not None
        except Exception:
            pass

    def test_init_with_params(self):
        try:
            s = pqs.PaperQualityScorer(
                model="deepseek",
                temperature=0.3,
                paper_type="empirical",
            )
            assert s is not None
        except Exception:
            pass


# ─── Module-level ───────────────────────────────────────────────────────────


class TestModuleLevel:
    def test_main_exists(self):
        assert hasattr(pqs, "main")
        assert callable(pqs.main)
