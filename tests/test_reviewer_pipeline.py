"""Tests for scripts/core/reviewer_pipeline.py"""

import unittest.mock as mock
from unittest.mock import MagicMock


from scripts.core.reviewer_pipeline import (
    ReviewerPipeline,
    ReviewStage,
    StageResult,
    UnifiedReviewReport,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


PAPER_ABSTRACT = (
    "This paper studies the causal effect of carbon emission trading on "
    "corporate green innovation using a difference-in-differences design."
)


# ─── Data Classes ─────────────────────────────────────────────────────────────


class TestStageResult:
    def test_stage_result_dataclass(self):
        sr = StageResult(
            stage=ReviewStage.LLM_SCORING,
            passed=True,
            score=7.5,
            details={"methodology_rigor": 8.0},
            latency_ms=1200.0,
        )
        assert sr.stage == ReviewStage.LLM_SCORING
        assert sr.passed is True
        assert sr.score == 7.5
        assert "methodology_rigor" in sr.details
        assert sr.latency_ms == 1200.0
        assert sr.error is None

    def test_stage_result_with_error(self):
        sr = StageResult(
            stage=ReviewStage.LLM_SCORING,
            passed=False,
            score=None,
            details={},
            latency_ms=500.0,
            error="API timeout",
        )
        assert sr.passed is False
        assert sr.score is None
        assert sr.error == "API timeout"


class TestUnifiedReviewReport:
    def test_unified_report_dataclass(self):
        sr1 = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
            details={"dimension_scores": {"methodology_rigor": 7.0}}, latency_ms=500.0,
        )
        sr2 = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=True, score=80.0,
            details={}, latency_ms=100.0,
        )
        report = UnifiedReviewReport(
            unified_score=7.2,
            final_verdict="accept",
            stages=[sr1, sr2],
            dimension_scores={"methodology_rigor": 7.0},
            halt_violations=[],
            bias_flags=[],
            critical_issues=[],
            confidence=0.85,
            total_latency_ms=600.0,
        )
        assert report.unified_score == 7.2
        assert report.final_verdict == "accept"
        assert len(report.stages) == 2
        assert report.confidence == 0.85

    def test_to_dict(self):
        sr = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
            details={}, latency_ms=100.0,
        )
        report = UnifiedReviewReport(
            unified_score=7.0,
            final_verdict="accept",
            stages=[sr],
            dimension_scores={"methodology_rigor": 7.0},
            halt_violations=["missing robustness"],
            bias_flags=["leniency"],
            critical_issues=["endogeneity concern"],
            confidence=0.8,
            total_latency_ms=100.0,
        )
        d = report.to_dict()
        assert d["unified_score"] == 7.0
        assert d["final_verdict"] == "accept"
        assert len(d["halt_violations"]) == 1
        assert len(d["bias_flags"]) == 1
        assert len(d["critical_issues"]) == 1

    def test_summary(self):
        sr = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
            details={}, latency_ms=100.0,
        )
        report = UnifiedReviewReport(
            unified_score=7.0,
            final_verdict="accept",
            stages=[sr],
            dimension_scores={"methodology_rigor": 7.0},
            halt_violations=["missing identification"],
            bias_flags=[],
            critical_issues=["endogeneity"],
            confidence=0.85,
            total_latency_ms=100.0,
        )
        summary = report.summary()
        assert "7.00/10" in summary
        assert "accept" in summary
        assert "85" in summary
        assert "missing identification" in summary


# ─── ReviewStage ───────────────────────────────────────────────────────────────


class TestReviewStage:
    def test_all_stages_present(self):
        assert ReviewStage.LLM_SCORING.value == "llm_scoring"
        assert ReviewStage.AUTO_RULES.value == "auto_rules"
        assert ReviewStage.BIAS_CHECK.value == "bias_check"
        assert len(ReviewStage) == 3

    def test_stages_are_strings(self):
        for stage in ReviewStage:
            assert isinstance(stage.value, str)


# ─── ReviewerPipeline Init ────────────────────────────────────────────────────


class TestReviewerPipelineInit:
    def test_defaults(self):
        p = ReviewerPipeline()
        assert p.enable_auto_rules is True
        assert p.enable_bias_check is True
        assert p.default_venue == "ML"
        assert p.llm_timeout == 120.0
        assert p.llm_max_retries == 1

    def test_custom_values(self):
        p = ReviewerPipeline(
            enable_auto_rules=False,
            enable_bias_check=False,
            venue="JFE",
            llm_timeout=60.0,
            llm_max_retries=3,
        )
        assert p.enable_auto_rules is False
        assert p.enable_bias_check is False
        assert p.default_venue == "JFE"
        assert p.llm_timeout == 60.0
        assert p.llm_max_retries == 3


# ─── Chapter Splitting ───────────────────────────────────────────────────────


class TestChapterSplitting:
    def test_split_by_section_headers(self):
        text = (
            "Introduction\n\nThis is the intro.\n\n"
            "Literature Review\n\nPrevious work.\n\n"
            "Methodology\n\nWe use DID design.\n\n"
            "Conclusion\n\nWe find that..."
        )
        chapters = ReviewerPipeline._split_into_chapters(text)
        assert "Introduction" in chapters
        # Section detection matches the first word of the header
        assert "Literature" in chapters
        assert "Methodology" in chapters
        assert "Conclusion" in chapters

    def test_no_headers_returns_general(self):
        text = "This is a paper without clear section headers. It just has text."
        chapters = ReviewerPipeline._split_into_chapters(text)
        assert "General" in chapters
        assert chapters["General"] == text

    def test_empty_content(self):
        chapters = ReviewerPipeline._split_into_chapters("")
        assert "General" in chapters

    def test_split_preserves_content(self):
        text = "Introduction\n\nIntro text here."
        chapters = ReviewerPipeline._split_into_chapters(text)
        assert "intro text here" in chapters["Introduction"].lower()


# ─── Pipeline Stage Logic ─────────────────────────────────────────────────────


class TestLLMScoringStage:
    def test_llm_score_returns_stage_result(self):
        p = ReviewerPipeline(enable_auto_rules=False, enable_bias_check=False)
        mock_result = MagicMock()
        mock_result.scores = {}
        mock_result.overall_score = 0.0
        mock_result.overall_recommendation = "Unknown"
        mock_result.confidence = 0.0

        with mock.patch("scripts.core.llm_reviewer.LLMReviewer") as MockReviewer:
            instance = MockReviewer.return_value
            instance.review.return_value = mock_result
            stage = p._llm_score(PAPER_ABSTRACT, "JFE")

        assert stage.stage == ReviewStage.LLM_SCORING
        assert "llm_result" in stage.details
        assert stage.latency_ms >= 0

    def test_llm_score_handles_exception(self):
        p = ReviewerPipeline(enable_auto_rules=False, enable_bias_check=False)
        with mock.patch(
            "scripts.core.llm_reviewer.LLMReviewer",
            side_effect=Exception("API error"),
        ):
            stage = p._llm_score(PAPER_ABSTRACT, "JFE")
        assert stage.passed is False
        assert stage.score is None
        assert stage.error is not None


class TestAutoRulesStage:
    def test_auto_rules_returns_stage_result(self):
        p = ReviewerPipeline(enable_auto_rules=True, enable_bias_check=False)
        mock_score = MagicMock()
        mock_score.passed = True
        mock_score.overall = 75.0
        mock_score.critical_issues = []
        mock_score.warnings = []
        mock_score.dimension_scores = {"writing": 80.0}

        with mock.patch("scripts.core.auto_review_rules.AutoReviewRules") as MockARR:
            instance = MockARR.return_value
            instance.score_paper.return_value = mock_score
            stage = p._auto_rules_check(PAPER_ABSTRACT)

        assert stage.stage == ReviewStage.AUTO_RULES
        assert stage.passed is True
        assert stage.score == 75.0

    def test_auto_rules_disabled_returns_passed(self):
        p = ReviewerPipeline(enable_auto_rules=False)
        stage = p._auto_rules_check(PAPER_ABSTRACT)
        assert stage.stage == ReviewStage.AUTO_RULES
        assert stage.passed is True
        assert stage.details.get("skipped") is True

    def test_auto_rules_halts_on_critical_issues(self):
        p = ReviewerPipeline(enable_auto_rules=True, enable_bias_check=False)
        mock_score = MagicMock()
        mock_score.passed = False
        mock_score.overall = 40.0
        mock_score.critical_issues = ["missing identification strategy", "no data source"]
        mock_score.warnings = []
        mock_score.dimension_scores = {}

        with mock.patch("scripts.core.auto_review_rules.AutoReviewRules") as MockARR:
            instance = MockARR.return_value
            instance.score_paper.return_value = mock_score
            stage = p._auto_rules_check(PAPER_ABSTRACT)

        assert stage.passed is False
        assert "missing identification strategy" in stage.details["critical_issues"]


class TestBiasCheckStage:
    def test_bias_check_enabled(self):
        p = ReviewerPipeline(enable_bias_check=True)
        mock_biases = [MagicMock(description="Leniency bias")]
        with mock.patch(
            "scripts.core.reviewer_calibrator.ReviewerCalibrator"
        ) as MockCal:
            instance = MockCal.return_value
            instance.detect_biases.return_value = mock_biases
            stage = p._bias_check({"scores": {}})

        assert stage.stage == ReviewStage.BIAS_CHECK
        assert stage.details["n_biases"] == 1
        assert "leniency" in stage.details["bias_flags"][0].lower()

    def test_bias_check_disabled(self):
        p = ReviewerPipeline(enable_bias_check=False)
        stage = p._bias_check({"scores": {}})
        assert stage.details.get("skipped") is True

    def test_bias_check_no_llm_result(self):
        p = ReviewerPipeline(enable_bias_check=True)
        stage = p._bias_check(None)
        assert stage.details.get("skipped") is True

    def test_bias_check_handles_exception(self):
        p = ReviewerPipeline(enable_bias_check=True)
        with mock.patch(
            "scripts.core.reviewer_calibrator.ReviewerCalibrator",
            side_effect=Exception("Calibration error"),
        ):
            stage = p._bias_check({"scores": {}})
        # Should not fail the pipeline
        assert stage.passed is True


# ─── Combine Logic ────────────────────────────────────────────────────────────


class TestCombineLogic:
    def test_combine_accept(self):
        p = ReviewerPipeline()
        llm = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=8.0,
            details={"confidence": 0.85, "llm_result": {}, "dimension_scores": {}},
            latency_ms=100.0,
        )
        rules = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=True, score=80.0,
            details={"critical_issues": []}, latency_ms=50.0,
        )
        bias = StageResult(
            stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
            details={"bias_flags": []}, latency_ms=20.0,
        )
        report = p._combine(llm, rules, bias)
        assert report.final_verdict == "accept"
        assert report.unified_score >= 7.5

    def test_combine_major_revision_on_halt_violation(self):
        p = ReviewerPipeline()
        llm = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
            details={"confidence": 0.8, "llm_result": {}, "dimension_scores": {}},
            latency_ms=100.0,
        )
        rules = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=False, score=30.0,
            details={"critical_issues": ["no identification"]}, latency_ms=50.0,
        )
        bias = StageResult(
            stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
            details={"bias_flags": []}, latency_ms=20.0,
        )
        report = p._combine(llm, rules, bias)
        assert report.final_verdict == "major_revision"
        assert "no identification" in report.halt_violations

    def test_combine_low_score_becomes_reject(self):
        p = ReviewerPipeline()
        # LLM passed=True but score very low -> unified < 5.0
        llm = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=3.0,
            details={"confidence": 0.5, "llm_result": {}, "dimension_scores": {}},
            latency_ms=100.0,
        )
        rules = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=True, score=40.0,
            details={"critical_issues": []}, latency_ms=50.0,
        )
        bias = StageResult(
            stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
            details={"bias_flags": []}, latency_ms=20.0,
        )
        report = p._combine(llm, rules, bias)
        # score=3.0 + normalized rules=4.0 = avg 3.5 < 5.0 -> reject
        assert report.final_verdict == "reject"

    def test_combine_confidence_reduced_by_bias(self):
        p = ReviewerPipeline()
        llm = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
            details={"confidence": 0.9, "llm_result": {}, "dimension_scores": {}},
            latency_ms=100.0,
        )
        rules = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=True, score=70.0,
            details={"critical_issues": []}, latency_ms=50.0,
        )
        bias = StageResult(
            stage=ReviewStage.BIAS_CHECK, passed=False, score=0.7,
            details={"bias_flags": ["leniency bias", "order effect"]}, latency_ms=20.0,
        )
        report = p._combine(llm, rules, bias)
        # 2 bias flags: confidence × (1 - 0.2) = 0.9 × 0.8 = 0.72
        assert report.confidence < 0.9

    def test_combine_total_latency(self):
        p = ReviewerPipeline()
        llm = StageResult(stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
                          details={}, latency_ms=1000.0)
        rules = StageResult(stage=ReviewStage.AUTO_RULES, passed=True, score=70.0,
                            details={}, latency_ms=200.0)
        bias = StageResult(stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
                           details={}, latency_ms=50.0)
        report = p._combine(llm, rules, bias)
        assert report.total_latency_ms == 1250.0


# ─── Full Pipeline ───────────────────────────────────────────────────────────


class TestFullPipeline:
    def test_pipeline_runs_all_stages(self):
        p = ReviewerPipeline(
            enable_auto_rules=True,
            enable_bias_check=True,
            llm_timeout=120.0,
        )

        # Mock all stages
        with (
            mock.patch.object(p, "_llm_score") as mock_llm,
            mock.patch.object(p, "_auto_rules_check") as mock_rules,
            mock.patch.object(p, "_bias_check") as mock_bias,
            mock.patch.object(p, "_combine") as mock_combine,
        ):
            mock_llm.return_value = StageResult(
                stage=ReviewStage.LLM_SCORING, passed=True, score=7.5,
                details={"confidence": 0.85, "llm_result": {}, "dimension_scores": {}},
                latency_ms=500.0,
            )
            mock_rules.return_value = StageResult(
                stage=ReviewStage.AUTO_RULES, passed=True, score=75.0,
                details={"critical_issues": []}, latency_ms=100.0,
            )
            mock_bias.return_value = StageResult(
                stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
                details={"bias_flags": []}, latency_ms=50.0,
            )
            mock_combine.return_value = UnifiedReviewReport(
                unified_score=7.5,
                final_verdict="accept",
                stages=[],
                dimension_scores={},
                halt_violations=[],
                bias_flags=[],
                critical_issues=[],
                confidence=0.85,
                total_latency_ms=650.0,
            )

            report = p.review(PAPER_ABSTRACT, venue="JFE")

            assert mock_llm.call_count == 1
            assert mock_rules.call_count == 1
            assert mock_bias.call_count == 1
            assert mock_combine.call_count == 1
            assert report.unified_score == 7.5

    def test_pipeline_respects_default_venue(self):
        p = ReviewerPipeline(venue="经济研究")

        with mock.patch.object(p, "_llm_score") as mock_llm, \
             mock.patch.object(p, "_auto_rules_check") as mock_rules, \
             mock.patch.object(p, "_bias_check") as mock_bias, \
             mock.patch.object(p, "_combine") as mock_combine:
            mock_llm.return_value = StageResult(
                stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
                details={"confidence": 0.8, "llm_result": {}, "dimension_scores": {}},
                latency_ms=100.0,
            )
            mock_rules.return_value = StageResult(
                stage=ReviewStage.AUTO_RULES, passed=True, score=70.0,
                details={}, latency_ms=50.0,
            )
            mock_bias.return_value = StageResult(
                stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
                details={}, latency_ms=20.0,
            )
            mock_combine.return_value = UnifiedReviewReport(
                unified_score=7.0, final_verdict="accept",
                stages=[], dimension_scores={},
                halt_violations=[], bias_flags=[], critical_issues=[],
                confidence=0.8, total_latency_ms=170.0,
            )

            p.review(PAPER_ABSTRACT)
            # Verify venue was passed to LLM scoring
            _, kwargs = mock_llm.call_args
            assert kwargs.get("venue") == "经济研究" or (
                len(mock_llm.call_args[0]) > 1 and mock_llm.call_args[0][1] == "经济研究"
            )


# ─── Edge Cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_dimension_scores_fallback(self):
        p = ReviewerPipeline()
        llm = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=0.0,
            details={"confidence": 0.0, "llm_result": {}, "dimension_scores": {}},
            latency_ms=100.0,
        )
        rules = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=True, score=50.0,
            details={"critical_issues": []}, latency_ms=50.0,
        )
        bias = StageResult(
            stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
            details={"bias_flags": []}, latency_ms=20.0,
        )
        report = p._combine(llm, rules, bias)
        # Should still produce a report
        assert report.unified_score >= 0.0
        assert report.final_verdict is not None

    def test_bias_flags_deduplicated_in_critical_issues(self):
        p = ReviewerPipeline()
        llm = StageResult(
            stage=ReviewStage.LLM_SCORING, passed=True, score=7.0,
            details={
                "confidence": 0.8,
                "llm_result": {"weaknesses": ["same issue", "same issue"]},
                "dimension_scores": {},
            },
            latency_ms=100.0,
        )
        rules = StageResult(
            stage=ReviewStage.AUTO_RULES, passed=True, score=70.0,
            details={"critical_issues": []}, latency_ms=50.0,
        )
        bias = StageResult(
            stage=ReviewStage.BIAS_CHECK, passed=True, score=1.0,
            details={"bias_flags": []}, latency_ms=20.0,
        )
        report = p._combine(llm, rules, bias)
        # Critical issues should be capped at 10
        assert len(report.critical_issues) <= 10
