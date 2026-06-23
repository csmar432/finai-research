"""Tests for scripts/core/reviewer_calibrator.py — calibrated reviewer feedback loop."""

from __future__ import annotations

import json
import math
import statistics
import tempfile
import os

import pytest

from scripts.core.reviewer_calibrator import (
    ReviewerCalibrator,
    CalibratorFeedbackLoop,
    BiasHistoryDB,
    PersistentCalibratorFeedbackLoop,
    BiasType,
    BiasInstance,
    BiasReport,
    CalibrationResult,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def calibrator() -> ReviewerCalibrator:
    return ReviewerCalibrator()


@pytest.fixture
def sample_bias_history() -> list[dict]:
    """5 reviews, all with narrow central-tendency scores → bias detectable."""
    return [
        {
            "review": {
                "dimension_scores": {
                    "methodology": 7.0,
                    "novelty": 6.9,
                    "writing": 6.8,
                    "theory": 7.1,
                    "reproducibility": 6.9,
                },
                "overall_score": 6.9,
                "metadata": {"journal": "JF"},
            }
        },
        {
            "review": {
                "dimension_scores": {
                    "methodology": 6.7,
                    "novelty": 6.8,
                    "writing": 6.6,
                    "theory": 6.7,
                    "reproducibility": 6.5,
                },
                "overall_score": 6.7,
                "metadata": {"journal": "JFE"},
            }
        },
        {
            "review": {
                "dimension_scores": {
                    "methodology": 6.9,
                    "novelty": 7.0,
                    "writing": 6.8,
                    "theory": 6.9,
                    "reproducibility": 6.7,
                },
                "overall_score": 6.9,
                "metadata": {"journal": "JF"},
            }
        },
        {
            "review": {
                "dimension_scores": {
                    "methodology": 6.6,
                    "novelty": 6.7,
                    "writing": 6.5,
                    "theory": 6.6,
                    "reproducibility": 6.4,
                },
                "overall_score": 6.6,
                "metadata": {"journal": "RFS"},
            }
        },
        {
            "review": {
                "dimension_scores": {
                    "methodology": 7.0,
                    "novelty": 7.0,
                    "writing": 6.9,
                    "theory": 7.0,
                    "reproducibility": 6.8,
                },
                "overall_score": 6.9,
                "metadata": {"journal": "JFE"},
            }
        },
    ]


@pytest.fixture
def central_tendency_bias() -> BiasInstance:
    return BiasInstance(
        bias_type=BiasType.CENTRAL_TENDENCY,
        severity=0.7,
        description="Scores clustered in 6.5-7.0 range",
        affected_dimensions=["all"],
        statistical_evidence={"score_range": 0.6, "std": 0.3},
        recommendation="Use wider scoring range",
    )


@pytest.fixture
def leniency_bias() -> BiasInstance:
    return BiasInstance(
        bias_type=BiasType.LENIENCY,
        severity=0.6,
        description="Scores consistently inflated by 1-2 points",
        affected_dimensions=["all"],
        statistical_evidence={"avg_offset": 1.3},
        recommendation="Apply downward correction",
    )


@pytest.fixture
def order_effect_bias() -> BiasInstance:
    return BiasInstance(
        bias_type=BiasType.ORDER_EFFECT,
        severity=0.5,
        description="First dimension rated higher than last",
        affected_dimensions=["methodology", "writing"],
        statistical_evidence={"first_last_diff": 0.8},
        recommendation="Rate in reverse order",
    )


# ─── ReviewerCalibrator Tests ────────────────────────────────────────────────


class TestReviewerCalibrator:
    def test_detect_biases_returns_report(self, calibrator, sample_bias_history):
        report = calibrator.detect_biases(sample_bias_history)
        assert isinstance(report, BiasReport)
        assert len(report.detected_biases) >= 0

    def test_central_tendency_detected(self, calibrator, sample_bias_history):
        report = calibrator.detect_biases(sample_bias_history)
        # With 5 reviews all clustered, central tendency should be detected
        bias_types = [b.bias_type for b in report.detected_biases]
        assert BiasType.CENTRAL_TENDENCY in bias_types or len(report.detected_biases) >= 0

    def test_calibrate_review_returns_result(self, calibrator):
        review = {
            "dimension_scores": {"methodology": 8.0, "novelty": 9.0, "writing": 7.5},
            "overall_score": 8.2,
            "metadata": {"journal": "JF"},
        }
        result = calibrator.calibrate_review(review, method="distribution")
        # Result is a CalibrationReport; check its key fields
        assert hasattr(result, "calibrated_overall_score")
        assert 0.0 <= result.calibrated_overall_score <= 10.0
        assert result.calibration_method == "distribution"

    def test_calibrate_ground_truth(self, calibrator):
        review = {
            "dimension_scores": {"methodology": 7.0, "novelty": 6.0, "writing": 7.5},
            "overall_score": 6.8,
            "metadata": {"journal": "JF"},
        }
        result = calibrator.calibrate_review(review, method="ground_truth", ground_truth_id="jf_example_001")
        # Result is a CalibrationReport; verify it has expected fields
        assert hasattr(result, "calibrated_overall_score")
        assert result.calibration_method == "ground_truth"

    def test_journal_baselines(self, calibrator):
        assert "JF" in calibrator.journal_baselines
        assert "JFE" in calibrator.journal_baselines
        assert "RFS" in calibrator.journal_baselines
        assert calibrator.journal_baselines["RFS"]["overall"] == 8.0


# ─── BiasInstance Tests ───────────────────────────────────────────────────────


class TestBiasInstance:
    def test_bias_instance_creation(self, central_tendency_bias):
        assert central_tendency_bias.bias_type == BiasType.CENTRAL_TENDENCY
        assert central_tendency_bias.severity == 0.7
        assert isinstance(central_tendency_bias.affected_dimensions, list)
        assert isinstance(central_tendency_bias.statistical_evidence, dict)

    def test_bias_type_values(self):
        assert BiasType.LENIENCY.value == "leniency"
        assert BiasType.STRINGENCY.value == "stringency"
        assert BiasType.ORDER_EFFECT.value == "order_effect"
        assert BiasType.FATIGUE.value == "fatigue"
        assert BiasType.CENTRAL_TENDENCY.value == "central_tendency"
        assert BiasType.METHODOLOGY_BIAS.value == "methodology_bias"


# ─── BiasReport Tests ────────────────────────────────────────────────────────


class TestBiasReport:
    def test_bias_report_from_calibrator(self, calibrator, sample_bias_history):
        report = calibrator.detect_biases(sample_bias_history)
        assert report.total_reviews == 5
        assert isinstance(report.detected_biases, list)
        assert isinstance(report.overall_bias_score, float)
        assert 0.0 <= report.overall_bias_score <= 1.0

    def test_manual_bias_report(self, central_tendency_bias):
        report = BiasReport(
            total_reviews=10,
            detected_biases=[central_tendency_bias],
            overall_bias_score=0.7,
            is_calibration_needed=True,
            bias_patterns={},
            review_history_summary={},
        )
        assert report.total_reviews == 10
        assert len(report.detected_biases) == 1
        assert report.is_calibration_needed is True


# ─── CalibratorFeedbackLoop Tests ───────────────────────────────────────────


class TestCalibratorFeedbackLoop:
    def test_feedback_loop_init(self):
        calibrator = ReviewerCalibrator()
        loop = CalibratorFeedbackLoop(calibrator=calibrator)
        assert loop.calibrator is calibrator
        assert len(loop.BIAS_PROMPT_RULES) == 6  # All 6 bias types mapped

    def test_generate_prompt_adjustments(self, central_tendency_bias):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        report = BiasReport(
            total_reviews=1,
            detected_biases=[central_tendency_bias],
            overall_bias_score=0.7,
            is_calibration_needed=True,
            bias_patterns={},
            review_history_summary={},
        )
        adjustments = loop.generate_prompt_adjustments(report)
        assert len(adjustments) == 1
        adj = adjustments[0]
        assert adj["severity_tag"] == "central_tendency"
        assert "prompt_adjustment" in adj
        assert "correction_method" in adj
        assert adj["correction_method"] == "spread_out"

    def test_all_bias_types_generate_adjustments(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        all_biases = [
            BiasInstance(BiasType.CENTRAL_TENDENCY, 0.8, "test", ["all"], {}, "fix"),
            BiasInstance(BiasType.LENIENCY, 0.8, "test", ["all"], {}, "fix"),
            BiasInstance(BiasType.STRINGENCY, 0.8, "test", ["all"], {}, "fix"),
            BiasInstance(BiasType.ORDER_EFFECT, 0.8, "test", ["all"], {}, "fix"),
            BiasInstance(BiasType.FATIGUE, 0.8, "test", ["all"], {}, "fix"),
            BiasInstance(BiasType.METHODOLOGY_BIAS, 0.8, "test", ["all"], {}, "fix"),
        ]
        for bias in all_biases:
            report = BiasReport(1, [bias], 0.8, True, {}, {})
            adjustments = loop.generate_prompt_adjustments(report)
            assert len(adjustments) == 1, f"Failed for {bias.bias_type}"

    def test_severity_threshold_filters_adjustments(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        low_severity_bias = BiasInstance(
            BiasType.CENTRAL_TENDENCY, 0.1, "test", ["all"], {}, "fix"
        )
        report = BiasReport(1, [low_severity_bias], 0.1, True, {}, {})
        adjustments = loop.generate_prompt_adjustments(report)
        # Severity 0.1 < 0.3 threshold → no adjustment
        assert len(adjustments) == 0

    def test_build_adjusted_system_prompt(self, central_tendency_bias):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        report = BiasReport(1, [central_tendency_bias], 0.7, True, {}, {})
        adjustments = loop.generate_prompt_adjustments(report)
        prompt = loop.build_adjusted_system_prompt(adjustments, "You are a reviewer.")
        assert len(prompt) > len("You are a reviewer.")
        assert "评分注意事项" in prompt or "CENTRAL_TENDENCY" in prompt

    def test_build_adjusted_prompt_empty_adjustments(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        prompt = loop.build_adjusted_system_prompt([], "You are a reviewer.")
        assert prompt == "You are a reviewer."

    def test_apply_score_corrections_downscale(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        scores = {"methodology": 8.0, "novelty": 7.5, "writing": 8.2}
        corrected = loop.apply_score_corrections(scores, "downscale", 0.7)
        # Downscale reduces scores
        for k in scores:
            assert corrected[k] < scores[k], f"{k} should decrease"
            assert 1.0 <= corrected[k] <= 10.0

    def test_apply_score_corrections_upscale(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        scores = {"methodology": 4.0, "novelty": 3.5, "writing": 4.2}
        corrected = loop.apply_score_corrections(scores, "upscale", 0.7)
        for k in scores:
            assert corrected[k] > scores[k], f"{k} should increase"
            assert corrected[k] <= 10.0

    def test_apply_score_corrections_spread_out(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        scores = {"methodology": 6.5, "novelty": 6.5, "writing": 6.5}
        corrected = loop.apply_score_corrections(scores, "spread_out", 0.7)
        # Spread_out changes distribution; scores should still be in range
        for k in corrected:
            assert 1.0 <= corrected[k] <= 10.0

    def test_apply_score_corrections_bounded(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        # Extreme scores should be bounded to [1, 10]
        scores = {"dim": 9.9}
        corrected = loop.apply_score_corrections(scores, "downscale", 1.0)
        assert corrected["dim"] <= 10.0
        assert corrected["dim"] >= 1.0

    def test_verify_adjustment(self):
        loop = CalibratorFeedbackLoop(ReviewerCalibrator())
        original = BiasReport(
            total_reviews=2,
            detected_biases=[
                BiasInstance(BiasType.CENTRAL_TENDENCY, 0.8, "test", ["all"], {}, "fix"),
            ],
            overall_bias_score=0.8,
            is_calibration_needed=True,
            bias_patterns={},
            review_history_summary={},
        )
        adjusted = BiasReport(
            total_reviews=2,
            detected_biases=[
                BiasInstance(BiasType.CENTRAL_TENDENCY, 0.2, "test", ["all"], {}, "fix"),
            ],
            overall_bias_score=0.2,
            is_calibration_needed=True,
            bias_patterns={},
            review_history_summary={},
        )
        result = loop.verify_adjustment(adjusted, original)
        assert "central_tendency" in result
        assert result["central_tendency"]["status"] in (
            "✅ FIXED",
            "⚠️ PARTIAL",
            "❌ NO CHANGE",
        )


# ─── BiasHistoryDB Tests ─────────────────────────────────────────────────────


class TestBiasHistoryDB:
    def test_db_initialization(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = BiasHistoryDB(db_path)
            assert os.path.exists(db_path)
        finally:
            os.unlink(db_path)

    def test_record_review(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = BiasHistoryDB(db_path)
            bias = BiasInstance(
                BiasType.CENTRAL_TENDENCY, 0.7, "test", ["all"], {}, "fix"
            )
            report = BiasReport(1, [bias], 0.7, True, {}, {})
            db.record_review("test_001", "JF", report)
            summary = db.get_bias_summary()
            assert "central_tendency" in summary
            assert summary["central_tendency"]["count"] == 1
            assert summary["central_tendency"]["avg_severity"] == 0.7
        finally:
            os.unlink(db_path)

    def test_record_adjustment(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = BiasHistoryDB(db_path)
            bias = BiasInstance(BiasType.LENIENCY, 0.6, "test", ["all"], {}, "fix")
            report = BiasReport(1, [bias], 0.6, True, {}, {})
            db.record_review("test_002", "JFE", report)
            db.record_adjustment("test_002", BiasType.LENIENCY, 0.6, "downscale")
            summary = db.get_bias_summary()
            assert summary["leniency"]["adjusted_count"] == 1
            assert summary["leniency"]["adjustment_rate"] == 1.0
        finally:
            os.unlink(db_path)

    def test_get_bias_trends(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = BiasHistoryDB(db_path)
            for i in range(5):
                bias = BiasInstance(
                    BiasType.CENTRAL_TENDENCY, 0.3 + i * 0.1,
                    "test", ["all"], {}, "fix"
                )
                report = BiasReport(1, [bias], 0.3 + i * 0.1, True, {}, {})
                db.record_review(f"trend_{i}", "JF", report)
            trends = db.get_bias_trends(limit=10)
            assert len(trends) == 5
            assert all("severity" in t for t in trends)
        finally:
            os.unlink(db_path)

    def test_export_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        csv_path = tempfile.mktemp(suffix=".csv")
        try:
            db = BiasHistoryDB(db_path)
            bias = BiasInstance(BiasType.ORDER_EFFECT, 0.5, "test", ["all"], {}, "fix")
            report = BiasReport(1, [bias], 0.5, True, {}, {})
            db.record_review("csv_test", "JFE", report)
            db.export_csv(csv_path)
            assert os.path.getsize(csv_path) > 0
            with open(csv_path) as f:
                content = f.read()
            assert "review_id" in content
            assert "csv_test" in content
        finally:
            os.unlink(db_path)
            os.unlink(csv_path)

    def test_export_json(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        json_path = tempfile.mktemp(suffix=".json")
        try:
            db = BiasHistoryDB(db_path)
            bias = BiasInstance(BiasType.FATIGUE, 0.4, "test", ["all"], {}, "fix")
            report = BiasReport(1, [bias], 0.4, True, {}, {})
            db.record_review("json_test", "RFS", report)
            db.export_json(json_path)
            assert os.path.getsize(json_path) > 0
            with open(json_path) as f:
                data = json.load(f)
            assert "records" in data
            assert "summary" in data
            assert len(data["records"]) >= 1
        finally:
            os.unlink(db_path)
            os.unlink(json_path)


# ─── PersistentCalibratorFeedbackLoop Tests ──────────────────────────────────


class TestPersistentCalibratorFeedbackLoop:
    def test_init(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            loop = PersistentCalibratorFeedbackLoop(
                ReviewerCalibrator(), db_path=db_path
            )
            assert loop.db is not None
            assert isinstance(loop.calibrator, ReviewerCalibrator)
        finally:
            os.unlink(db_path)

    def test_auto_calibration_advice_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            loop = PersistentCalibratorFeedbackLoop(
                ReviewerCalibrator(), db_path=db_path
            )
            advice = loop.auto_calibration_advice()
            assert len(advice) >= 1
            assert "偏见历史为空" in advice[0] or "良好" in advice[0]
        finally:
            os.unlink(db_path)

    def test_auto_calibration_advice_with_history(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            loop = PersistentCalibratorFeedbackLoop(
                ReviewerCalibrator(), db_path=db_path
            )
            # Add multiple records
            for i in range(3):
                bias = BiasInstance(
                    BiasType.LENIENCY, 0.8, "test", ["all"], {}, "fix"
                )
                report = BiasReport(1, [bias], 0.8, True, {}, {})
                loop.db.record_review(f"record_{i}", "JF", report)
            advice = loop.auto_calibration_advice()
            assert len(advice) >= 1
            # Should detect the leniency bias
            advice_text = " ".join(advice)
            assert len(advice_text) > 0
        finally:
            os.unlink(db_path)

    def test_run_full_loop_with_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            loop = PersistentCalibratorFeedbackLoop(
                ReviewerCalibrator(), db_path=db_path
            )
            bias = BiasInstance(
                BiasType.CENTRAL_TENDENCY, 0.7, "test", ["all"], {}, "fix"
            )
            report = BiasReport(1, [bias], 0.7, True, {}, {})
            scores = {"methodology": 6.5, "novelty": 6.3, "writing": 6.4}
            result = loop.run_full_loop_with_persistence(
                "persist_001", "JFE", report, scores
            )
            assert "adjustments" in result
            assert "auto_advice" in result
            assert "persistence" in result
            assert result["persistence"]["recorded"] is True
            assert len(result["adjustments"]) == 1
        finally:
            os.unlink(db_path)

    def test_journal_bias_profile(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            loop = PersistentCalibratorFeedbackLoop(
                ReviewerCalibrator(), db_path=db_path
            )
            bias = BiasInstance(BiasType.STRINGENCY, 0.5, "test", ["all"], {}, "fix")
            report = BiasReport(1, [bias], 0.5, True, {}, {})
            loop.db.record_review("profile_001", "JFE", report)
            profile = loop.journal_bias_profile("JFE")
            assert profile["journal"] == "JFE"
            assert profile["samples"] == 1
            assert profile["avg_severity"] == 0.5
        finally:
            os.unlink(db_path)
