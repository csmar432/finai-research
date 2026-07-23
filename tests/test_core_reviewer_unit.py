"""Minimal unit tests for scripts/core/reviewer.py.

Covers the dataclasses, enums and lightweight classes exposed by the
consolidated reviewer module. Heavy LLM-backed classes are NOT instantiated.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def reviewer():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import reviewer as r
    yield r
    if _p in sys.path:
        sys.path.remove(_p)


# ───────────────────────── module surface ─────────────────────────


class TestReviewerModuleSurface:
    def test_imports(self, reviewer):
        assert reviewer is not None

    def test_exposes_llm_reviewer_block(self, reviewer):
        for name in [
            "LLMReviewer",
            "ReviewResult",
            "ReviewScore",
            "CalibrationResult",
            "CalibrationDataset",
        ]:
            assert hasattr(reviewer, name), f"missing {name}"

    def test_exposes_pipeline_block(self, reviewer):
        for name in [
            "ReviewerPipeline",
            "ReviewStage",
            "StageResult",
            "UnifiedReviewReport",
        ]:
            assert hasattr(reviewer, name), f"missing {name}"

    def test_exposes_dual_reviewer_block(self, reviewer):
        for name in [
            "DualReviewer",
            "ReviewDimension",
            "DimensionScore",
            "ReviewReport",
        ]:
            assert hasattr(reviewer, name), f"missing {name}"

    def test_exposes_auto_review_block(self, reviewer):
        for name in [
            "AutoReviewRules",
            "AutoReviewRule",
            "AutoReviewScore",
        ]:
            assert hasattr(reviewer, name), f"missing {name}"

    def test_venue_configs_constant(self, reviewer):
        assert hasattr(reviewer, "REVIEWER_VENUE_CONFIGS")
        assert isinstance(reviewer.REVIEWER_VENUE_CONFIGS, dict)
        # finance venues should be present
        assert "JFE" in reviewer.REVIEWER_VENUE_CONFIGS
        assert "RFS" in reviewer.REVIEWER_VENUE_CONFIGS


# ───────────────────────── llm_reviewer dataclasses ─────────────────────────


class TestReviewScore:
    def test_init(self, reviewer):
        s = reviewer.ReviewScore(
            score=8.0,
            confidence=0.9,
            reasoning="well written",
        )
        assert s.score == pytest.approx(8.0)
        assert s.confidence == pytest.approx(0.9)
        assert s.reasoning == "well written"

    def test_fields(self, reviewer):
        names = {f.name for f in dataclasses.fields(reviewer.ReviewScore)}
        assert names == {"score", "confidence", "reasoning"}


class TestReviewResult:
    def test_init_with_default_metadata(self, reviewer):
        sub = reviewer.ReviewScore(score=7.0, confidence=0.8, reasoning="ok")
        r = reviewer.ReviewResult(
            scores={"rigor": sub},
            overall_score=7.5,
            overall_recommendation="accept_minor",
            summary="good paper",
            strengths=["s1"],
            weaknesses=["w1"],
            detailed_feedback="feedback text",
            confidence=0.85,
        )
        assert r.overall_score == pytest.approx(7.5)
        assert r.scores["rigor"] is sub
        assert r.metadata == {}  # default_factory dict

    def test_init_with_metadata(self, reviewer):
        sub = reviewer.ReviewScore(score=7.0, confidence=0.8, reasoning="ok")
        r = reviewer.ReviewResult(
            scores={},
            overall_score=7.0,
            overall_recommendation="revise",
            summary="s",
            strengths=[],
            weaknesses=[],
            detailed_feedback="",
            confidence=0.5,
            metadata={"venue": "JF"},
        )
        assert r.metadata == {"venue": "JF"}


class TestCalibrationResult:
    def test_init(self, reviewer):
        c = reviewer.CalibrationResult(
            balanced_accuracy=0.85,
            precision_per_class={"accept": 0.9},
            recall_per_class={"accept": 0.8},
            f1_per_class={"accept": 0.85},
            confusion_matrix=[[10, 1], [2, 7]],
            dimension_correlation={"rigor": 0.9},
            dataset_size=20,
            dataset_source="synthetic",
            total_predictions=20,
            correct_predictions=17,
        )
        assert c.balanced_accuracy == pytest.approx(0.85)
        assert c.total_predictions == 20
        assert c.confusion_matrix[0][1] == 1


# ───────────────────────── reviewer_pipeline dataclasses ─────────────────────────


class TestReviewStageEnum:
    def test_values(self, reviewer):
        assert reviewer.ReviewStage.LLM_SCORING.value == "llm_scoring"
        assert reviewer.ReviewStage.AUTO_RULES.value == "auto_rules"
        assert reviewer.ReviewStage.BIAS_CHECK.value == "bias_check"

    def test_three_members(self, reviewer):
        assert len(list(reviewer.ReviewStage)) == 3


class TestStageResult:
    def test_init(self, reviewer):
        sr = reviewer.StageResult(
            stage=reviewer.ReviewStage.AUTO_RULES,
            passed=True,
            score=8.0,
            details={"x": 1},
            latency_ms=120.0,
            error=None,
        )
        assert sr.stage is reviewer.ReviewStage.AUTO_RULES
        assert sr.passed is True
        assert sr.score == pytest.approx(8.0)
        assert sr.error is None


# ───────────────────────── dual_reviewer dataclasses ─────────────────────────


class TestReviewDimensionEnum:
    def test_values_subset(self, reviewer):
        names = {x.name for x in reviewer.ReviewDimension}
        expected = {
            "THEORY", "IDENTIFICATION", "DATA_QUALITY", "EMPIRICAL_RIGOR",
            "INTERPRETATION", "ROBUSTNESS", "WRITING", "NOVELTY",
        }
        assert expected <= names


class TestDimensionScore:
    def test_init(self, reviewer):
        d = reviewer.DimensionScore(
            dimension=reviewer.ReviewDimension.THEORY,
            score=7.5,
            verdict="ok",
            strengths=["s"],
            weaknesses=["w"],
            specific_issues=["i"],
            suggestions=["fix"],
        )
        assert d.dimension is reviewer.ReviewDimension.THEORY
        assert d.score == pytest.approx(7.5)
        assert d.verdict == "ok"


class TestReviewReport:
    def test_init(self, reviewer):
        ds = reviewer.DimensionScore(
            dimension=reviewer.ReviewDimension.WRITING,
            score=8.0,
            verdict="good",
            strengths=[], weaknesses=[], specific_issues=[], suggestions=[],
        )
        rep = reviewer.ReviewReport(
            document_type="paper",
            target="JF",
            primary_reviewer="p",
            shadow_reviewer="s",
            timestamp="2026-07-16T00:00:00",
            dimension_scores=[ds],
            weighted_score=7.8,
            hard_floor_passed=True,
            primary_review="primary text",
            shadow_review="shadow text",
            convergence_opinion="agree",
            disagreements=[],
            critical_issues=[],
            important_issues=[],
            minor_issues=[],
            verdict="accept_minor",
            confidence=0.9,
        )
        assert rep.document_type == "paper"
        assert rep.target == "JF"
        assert rep.weighted_score == pytest.approx(7.8)
        assert rep.hard_floor_passed is True
        assert rep.dimension_scores[0] is ds


# ───────────────────────── auto_review_rules dataclasses ─────────────────────────


class TestAutoReviewRule:
    def test_init(self, reviewer):
        rule = reviewer.AutoReviewRule(
            rule_id="R001",
            config={
                "description": "cluster SE required",
                "category": "robustness",
                "severity": "warning",
                "halt_on_fail": False,
                "validation": {"type": "content_structure_check", "rules": []},
            },
        )
        # AutoReviewRule stores rule_id as self.id (not rule_id)
        assert rule.id == "R001"
        assert rule.description == "cluster SE required"
        assert rule.category == "robustness"
        assert rule.severity == "warning"
        assert rule.halt_on_fail is False
        assert rule.validation_type == "content_structure_check"
        assert rule.rules == []

    def test_init_with_minimal_config(self, reviewer):
        rule = reviewer.AutoReviewRule(rule_id="R002", config={})
        # default values
        assert rule.id == "R002"
        assert rule.description == ""
        assert rule.category == "general"
        assert rule.severity == "warning"
        assert rule.halt_on_fail is False
        assert rule.validation_type == "unknown"


class TestAutoReviewScore:
    def test_init(self, reviewer):
        s = reviewer.AutoReviewScore(
            domain="empirical",
            overall=7.5,
            level="good",
            passed=True,
            dimension_scores={"rigor": 7.0},
            dimension_issues={"rigor": ["missing cluster SE"]},
            critical_issues=[],
            warnings=["warn1"],
            suggestions=["sug1"],
            rule_results=[{"id": "R001", "passed": True}],
            elapsed_ms=42.0,
        )
        assert s.domain == "empirical"
        assert s.overall == pytest.approx(7.5)
        assert s.passed is True
        assert s.elapsed_ms == pytest.approx(42.0)
        assert s.rule_results[0]["id"] == "R001"
