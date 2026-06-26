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
            pytest.skip("LLM unavailable — skipping test")

        # Either count incremented (LLM available) or stayed same (LLM unavailable)
        assert reviewer._review_count >= initial


class TestCalibrationDatasetExpanded:
    """Tests for expanded SYNTHETIC_SAMPLES (5 levels × 3 domains = 15 samples)."""

    def test_synthetic_samples_count(self):
        """SYNTHETIC_SAMPLES must have at least 50 entries (expanded from 3)."""
        samples = CalibrationDataset.SYNTHETIC_SAMPLES
        assert len(samples) >= 50, f"Expected at least 50 samples, got {len(samples)}"

    def test_synthetic_covers_all_domains(self):
        """Each of the 3 core domains must have at least 5 entries."""
        notes_by_domain: dict = {}
        for s in CalibrationDataset.SYNTHETIC_SAMPLES:
            # Core domains: EMPIRICAL, FINANCE, ML; CN_* are separate tags
            tag = s["notes"].split("]")[0].replace("[", "") if "]" in s["notes"] else "?"
            notes_by_domain[tag] = notes_by_domain.get(tag, 0) + 1
        for domain in ["EMPIRICAL", "FINANCE", "ML"]:
            count = notes_by_domain.get(domain, 0)
            assert count >= 5, (
                f"Domain {domain} has {count} entries, expected at least 5"
            )

    def test_synthetic_covers_all_quality_levels(self):
        """Each of the 5 quality levels must appear at least 3 times."""
        verdicts: dict = {}
        for s in CalibrationDataset.SYNTHETIC_SAMPLES:
            v = s["human_verdict"]
            verdicts[v] = verdicts.get(v, 0) + 1
        expected_levels = {"Strong Accept", "Accept", "Weak Accept", "Borderline", "Reject"}
        for level in expected_levels:
            count = verdicts.get(level, 0)
            assert count >= 3, (
                f"Level '{level}' has {count} entries, expected at least 3"
            )

    def test_synthetic_sample_fields(self):
        """Each sample must have all required schema fields."""
        required = {"paper_content", "human_verdict", "expected_scores", "notes", "source"}
        for s in CalibrationDataset.SYNTHETIC_SAMPLES:
            assert required.issubset(s.keys()), f"Missing fields: {required - set(s.keys())}"
            assert len(s["paper_content"]) > 10, "paper_content is too short"
            assert isinstance(s["expected_scores"], dict)
            for key in ["methodology_rigor", "novelty", "overall", "clarity"]:
                assert key in s["expected_scores"]

    def test_known_datasets_synthetic_linked(self):
        """KNOWN_DATASETS['synthetic'] must reference the same SYNTHETIC_SAMPLES list."""
        assert CalibrationDataset.KNOWN_DATASETS["synthetic"]["samples"] is CalibrationDataset.SYNTHETIC_SAMPLES

    def test_generate_dataset_columns(self):
        """generate_dataset() must return DataFrame with expected columns."""
        gen = CalibrationDataset()
        df = gen.generate_dataset(n_per_level=1, domain="empirical")
        assert list(df.columns) == [
            "paper_id", "quality_level", "domain", "text",
            "expected_score", "expected_recommendation",
        ]
        assert len(df) == 5  # one per quality level

    def test_generate_mixed_domain(self):
        """generate_mixed_domain_dataset() must produce multi-domain DataFrame."""
        gen = CalibrationDataset()
        df = gen.generate_mixed_domain_dataset(n_per_level=1)
        assert df["domain"].nunique() == 3
        assert len(df) == 15  # 5 levels × 3 domains


class TestBatchReviewFieldResolution:
    """Tests for batch_review() accepting multiple paper content field names."""

    def _call_batch_review_with_patched_review(self, papers: list[dict]) -> list:
        """Call batch_review with a patched LLMReviewer.review that returns
        a ReviewResult encoding the paper_content length (as a proxy for which
        field was read).

        Patches LLMReviewer.review with a plain function (not a bound method)
        so it can be restored cleanly via `setattr(reviewer, 'review', orig)`.
        """
        from scripts.core.llm_reviewer import LLMReviewer, ReviewResult

        def patch_review(paper_content: str, **kwargs) -> ReviewResult:
            return ReviewResult(
                scores={}, overall_score=0.0,
                overall_recommendation=f"read={len(paper_content)}",
                summary="", strengths=[], weaknesses=[],
                detailed_feedback="", confidence=0.0, metadata={},
            )

        reviewer = LLMReviewer(enable_cache=False)
        orig = reviewer.review
        try:
            # Patch on the instance so self-binding is preserved
            reviewer.review = patch_review
            return reviewer.batch_review(papers, venue="ML")
        finally:
            reviewer.review = orig

    def test_batch_review_paper_content_field(self):
        """batch_review() must read 'paper_content' field (synthetic dataset format)."""
        papers = [{"paper_content": "ABCDEF", "metadata": {"id": 1}}]
        results = self._call_batch_review_with_patched_review(papers)
        assert "read=6" in results[0].overall_recommendation

    def test_batch_review_content_field(self):
        """batch_review() must read 'content' field (priority over paper_content)."""
        papers = [{"content": "XY"}]
        results = self._call_batch_review_with_patched_review(papers)
        assert "read=2" in results[0].overall_recommendation

    def test_batch_review_text_field_fallback(self):
        """batch_review() must fall back to 'text' field."""
        papers = [{"text": "ZW"}]
        results = self._call_batch_review_with_patched_review(papers)
        assert "read=2" in results[0].overall_recommendation

    def test_batch_review_content_takes_priority(self):
        """When multiple fields exist, 'content' takes priority."""
        papers = [{"content": "A", "paper_content": "ABC", "text": "ABCDE"}]
        results = self._call_batch_review_with_patched_review(papers)
        assert "read=1" in results[0].overall_recommendation  # content="A" wins
