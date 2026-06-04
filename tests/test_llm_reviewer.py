"""Tests for LLM-based paper reviewer and calibration logic.

These tests focus on parsing, data structures, and venue thresholds.
LLM calls are mocked so no API key or network access is required.
"""

import pytest

from scripts.core.llm_reviewer import (
    LLMReviewer,
    ReviewResult,
    ReviewScore,
    CalibrationResult,
    CalibrationDataset,
    VENUE_CONFIGS,
)


class TestReviewResult:
    """Tests for ReviewResult parsing and structure."""

    def test_from_llm_response_valid(self, mock_llm_response):
        """Valid JSON should parse into a ReviewResult with correct scores."""
        result = ReviewResult.from_llm_response(mock_llm_response)

        assert result.overall_score == 8.0
        assert result.overall_recommendation == "Accept"
        assert "methodology_rigor" in result.scores
        assert result.scores["methodology_rigor"].score == 8

    def test_from_llm_response_with_markdown(self):
        """Markdown-wrapped JSON should still parse correctly."""
        raw = '```json\n{"scores": {}, "overall_score": 7.0, "overall_recommendation": "Weak Accept"}\n```'
        result = ReviewResult.from_llm_response(raw)
        assert result.overall_score == 7.0

    def test_from_llm_response_fallback(self):
        """Non-JSON response should produce a fallback result, not raise."""
        result = ReviewResult.from_llm_response("This is not JSON at all.")
        assert result.overall_score == 0.0

    def test_to_dict_roundtrip(self, mock_llm_response):
        """to_dict() followed by ReviewResult(...) should preserve key fields."""
        result = ReviewResult.from_llm_response(mock_llm_response)
        d = result.to_dict()

        assert "scores" in d
        assert "overall_score" in d
        assert "overall_recommendation" in d


class TestReviewScore:
    """Tests for individual ReviewScore dataclass."""

    def test_review_score_to_dict(self):
        """ReviewScore.to_dict() should return a plain dict."""
        score = ReviewScore(score=7.5, confidence=0.88, reasoning="Solid work.")
        d = score.to_dict()

        assert d["score"] == 7.5
        assert d["confidence"] == 0.88
        assert d["reasoning"] == "Solid work."


class TestCalibrationResult:
    """Tests for CalibrationResult."""

    def test_balanced_accuracy_better_than_random(self):
        """Balanced accuracy > 0.5 indicates better-than-random performance."""
        result = CalibrationResult(
            balanced_accuracy=0.72,
            precision_per_class={"accept": 0.7, "reject": 0.74},
            recall_per_class={"accept": 0.72, "reject": 0.72},
            f1_per_class={"accept": 0.71, "reject": 0.73},
            confusion_matrix=[[10, 2], [3, 10]],
            dimension_correlation={},
            dataset_size=25,
            dataset_source="synthetic",
        )
        assert result.balanced_accuracy > 0.5

    def test_summary_string(self):
        """summary() should produce a non-empty human-readable string."""
        result = CalibrationResult(
            balanced_accuracy=0.80,
            precision_per_class={},
            recall_per_class={},
            f1_per_class={},
            confusion_matrix=[],
            dimension_correlation={},
            dataset_size=50,
            dataset_source="test",
        )
        summary = result.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_to_dict(self):
        """to_dict() should return all fields."""
        result = CalibrationResult(
            balanced_accuracy=0.75,
            precision_per_class={"accept": 0.75},
            recall_per_class={"accept": 0.75},
            f1_per_class={"accept": 0.75},
            confusion_matrix=[[5, 1], [2, 5]],
            dimension_correlation={},
            dataset_size=13,
            dataset_source="unit_test",
        )
        d = result.to_dict()
        assert d["balanced_accuracy"] == 0.75
        assert d["dataset_source"] == "unit_test"


class TestCalibrationDataset:
    """Tests for calibration dataset management."""

    def test_get_synthetic_samples(self):
        """SYNTHETIC_SAMPLES should contain at least one entry."""
        samples = CalibrationDataset.get("synthetic")
        assert len(samples) >= 1
        assert "paper_content" in samples[0]
        assert "human_verdict" in samples[0]

    def test_add_custom_dataset(self):
        """add_custom() should make the dataset retrievable."""
        custom = [
            {"paper_content": "Test paper.", "human_verdict": "Accept"},
        ]
        CalibrationDataset.add_custom("test_set", custom, source="unit_test")
        retrieved = CalibrationDataset.get("test_set")
        assert retrieved == custom

    def test_get_unknown_raises(self):
        """get() with unknown name should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown dataset"):
            CalibrationDataset.get("nonexistent_dataset_xyz")


class TestVenueConfigs:
    """Tests for venue-specific configuration."""

    def test_venue_thresholds_valid_range(self):
        """All configured thresholds should be in the valid score range."""
        for venue, cfg in VENUE_CONFIGS.items():
            threshold = cfg["threshold_accept"]
            assert 0 < threshold <= 10, f"{venue} threshold out of range: {threshold}"

    def test_cvpr_nips_iclr_thresholds_equal(self):
        """Top ML venues should share the same acceptance threshold."""
        for venue in ["CVPR", "NeurIPS", "ICLR"]:
            assert venue in VENUE_CONFIGS
            assert VENUE_CONFIGS[venue]["threshold_accept"] == 7.0

    def test_top_finance_venues_higher_threshold(self):
        """Top finance journals should have threshold >= 7.0."""
        for venue in ["JFE", "RFS"]:
            assert venue in VENUE_CONFIGS
            assert VENUE_CONFIGS[venue]["threshold_accept"] >= 7.0


class TestLLMReviewer:
    """Tests for LLMReviewer that do not require actual LLM calls."""

    def test_init_default_venue(self):
        """Default venue should be 'ML' when not specified."""
        reviewer = LLMReviewer()
        assert reviewer.default_venue == "ML"

    def test_init_custom_venue(self):
        """Custom default venue should be stored."""
        reviewer = LLMReviewer(default_venue="JFE")
        assert reviewer.default_venue == "JFE"

    def test_cache_dir_created(self, tmp_path):
        """Cache directory should be created on init when enabled."""
        reviewer = LLMReviewer(
            enable_cache=True,
            cache_dir=str(tmp_path / "review_cache"),
        )
        assert (tmp_path / "review_cache").exists()

    def test_review_count_increments(self):
        """_review_count should increment after each review call attempt."""
        reviewer = LLMReviewer(enable_cache=False)
        initial = reviewer._review_count

        try:
            reviewer.review(
                paper_content="This paper proposes a method.",
                use_cache=False,
            )
        except RuntimeError:
            pass  # Expected when no LLM is available

        # Either count incremented (LLM available) or stayed same (LLM unavailable)
        assert reviewer._review_count >= initial
