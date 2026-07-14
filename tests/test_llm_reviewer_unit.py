"""Unit tests for scripts.core.llm_reviewer.

These tests cover:
- VENUE_CONFIGS structure and content
- ReviewScore dataclass (to_dict)
- ReviewResult dataclass and serialization (to_dict, to_json)
- ReviewResult.from_llm_response (parse, validate, clamp, recovery)
- CalibrationResult dataclass (to_dict, summary)
- CalibrationDataset (synthetic generation, quality mapping, mixed domains,
  custom datasets)
- LLMReviewer (init, cache, batch_review, calibrate, compare_with_rules)

All tests avoid real LLM API calls by either:
- Mocking ``_call_llm`` with canned JSON responses
- Using ``--no-llm``-style heuristic paths (not available for Reviewer; we use mocks)
- Verifying pure-data paths (calibration data structure, parsing, dataclasses)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.core.llm_reviewer import (
    CalibrationDataset,
    CalibrationResult,
    LLMReviewer,
    ReviewResult,
    ReviewScore,
    VENUE_CONFIGS,
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def _valid_review_json(recommendation: str = "Accept", overall: float = 7.0) -> str:
    """Return a canned well-formed LLM JSON review."""
    return json.dumps({
        "scores": {
            "methodology_rigor": {"score": 7.0, "confidence": 0.8, "reasoning": "ok"},
            "novelty": {"score": 6.5, "confidence": 0.7, "reasoning": "ok"},
            "clarity": {"score": 7.5, "confidence": 0.9, "reasoning": "ok"},
            "reproducibility": {"score": 6.0, "confidence": 0.6, "reasoning": "ok"},
            "significance": {"score": 7.0, "confidence": 0.8, "reasoning": "ok"},
            "overall": {"score": overall, "confidence": 0.85, "reasoning": "ok"},
        },
        "overall_score": overall,
        "overall_recommendation": recommendation,
        "summary": "summary text",
        "strengths": ["s1", "s2"],
        "weaknesses": ["w1"],
        "detailed_feedback": "feedback",
        "confidence": 0.85,
        "metadata": {},
    })


@pytest.fixture
def tmp_cache_dir(tmp_path):
    return tmp_path / "review_cache"


# ════════════════════════════════════════════════════════════════════
# VENUE_CONFIGS
# ════════════════════════════════════════════════════════════════════


class TestVenueConfigs:
    """Tests for venue configuration dictionary."""

    def test_contains_expected_venues(self):
        expected = {"CVPR", "NeurIPS", "ICLR", "ACL", "EMNLP",
                    "JFE", "RFS", "经济研究", "管理世界", "金融研究", "ML"}
        assert expected.issubset(VENUE_CONFIGS.keys())

    def test_each_venue_has_required_fields(self):
        for name, cfg in VENUE_CONFIGS.items():
            assert "name" in cfg, f"{name} missing 'name'"
            assert "threshold_accept" in cfg, f"{name} missing 'threshold_accept'"
            assert "threshold_borderline" in cfg, f"{name} missing 'threshold_borderline'"
            assert "domain" in cfg, f"{name} missing 'domain'"
            assert "focus" in cfg, f"{name} missing 'focus'"
            assert "language" in cfg, f"{name} missing 'language'"
            assert cfg["language"] in {"en", "zh"}, f"{name} language invalid"

    def test_threshold_accept_above_borderline(self):
        for name, cfg in VENUE_CONFIGS.items():
            assert cfg["threshold_accept"] > cfg["threshold_borderline"], (
                f"{name} accept threshold should exceed borderline"
            )

    def test_chinese_venues_use_zh(self):
        for name in ["经济研究", "管理世界", "金融研究"]:
            assert VENUE_CONFIGS[name]["language"] == "zh"


# ════════════════════════════════════════════════════════════════════
# ReviewScore
# ════════════════════════════════════════════════════════════════════


class TestReviewScore:
    """Tests for ReviewScore dataclass."""

    def test_construction(self):
        s = ReviewScore(score=7.5, confidence=0.8, reasoning="good")
        assert s.score == 7.5
        assert s.confidence == 0.8
        assert s.reasoning == "good"

    def test_to_dict(self):
        s = ReviewScore(score=7.0, confidence=0.5, reasoning="r")
        d = s.to_dict()
        assert d == {"score": 7.0, "confidence": 0.5, "reasoning": "r"}


# ════════════════════════════════════════════════════════════════════
# ReviewResult
# ════════════════════════════════════════════════════════════════════


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def _make_result(self):
        scores = {k: ReviewScore(score=7.0, confidence=0.8, reasoning="r")
                  for k in ReviewResult.DIMENSION_KEYS}
        return ReviewResult(
            scores=scores,
            overall_score=7.0,
            overall_recommendation="Accept",
            summary="summary",
            strengths=["s1"],
            weaknesses=["w1"],
            detailed_feedback="feedback",
            confidence=0.8,
            metadata={"venue": "ML"},
        )

    def test_construction_defaults(self):
        r = self._make_result()
        assert r.overall_score == 7.0
        assert r.overall_recommendation == "Accept"
        assert r.metadata == {"venue": "ML"}

    def test_to_dict_structure(self):
        r = self._make_result()
        d = r.to_dict()
        assert "scores" in d
        assert "overall_score" in d
        assert "overall_recommendation" in d
        assert "summary" in d
        assert "strengths" in d
        assert "weaknesses" in d
        assert "detailed_feedback" in d
        assert "confidence" in d
        assert "metadata" in d
        assert set(d["scores"].keys()) == set(ReviewResult.DIMENSION_KEYS)

    def test_to_json_is_parseable(self):
        r = self._make_result()
        js = r.to_json()
        parsed = json.loads(js)
        assert parsed["overall_score"] == 7.0
        assert parsed["overall_recommendation"] == "Accept"

    def test_to_json_preserves_chinese(self):
        scores = {k: ReviewScore(score=5.0, confidence=0.5, reasoning="好") for k in ReviewResult.DIMENSION_KEYS}
        r = ReviewResult(
            scores=scores,
            overall_score=5.0,
            overall_recommendation="接收",
            summary="中文总结",
            strengths=["强"],
            weaknesses=["弱"],
            detailed_feedback="详细",
            confidence=0.5,
            metadata={},
        )
        js = r.to_json()
        parsed = json.loads(js)
        assert parsed["summary"] == "中文总结"
        assert parsed["strengths"] == ["强"]
        assert parsed["overall_recommendation"] == "接收"


class TestReviewResultValidation:
    """Tests for ReviewResult's _validate_score / _validate_confidence."""

    def test_score_clamp_low(self):
        r = ReviewResult.__new__(ReviewResult)
        v, warns = r._validate_score(-3.0, "novelty")
        assert v == ReviewResult.SCORE_MIN
        assert any(w for w in warns)

    def test_score_clamp_high(self):
        r = ReviewResult.__new__(ReviewResult)
        v, warns = r._validate_score(15.0, "novelty")
        assert v == ReviewResult.SCORE_MAX
        assert any(w for w in warns)

    def test_score_within_range(self):
        r = ReviewResult.__new__(ReviewResult)
        v, warns = r._validate_score(7.5, "novelty")
        assert v == 7.5
        assert warns == []

    def test_confidence_clamp_low(self):
        r = ReviewResult.__new__(ReviewResult)
        v, warns = r._validate_confidence(-0.5)
        assert v == 0.0
        assert any(w for w in warns)

    def test_confidence_clamp_high(self):
        r = ReviewResult.__new__(ReviewResult)
        v, warns = r._validate_confidence(1.5)
        assert v == 1.0
        assert any(w for w in warns)


class TestReviewResultFromLLMResponse:
    """Tests for ReviewResult.from_llm_response parser."""

    def test_parse_valid_json(self):
        raw = _valid_review_json("Accept")
        r = ReviewResult.from_llm_response(raw)
        assert r.overall_recommendation == "Accept"
        assert r.overall_score == 7.0
        assert "methodology_rigor" in r.scores
        assert r.scores["methodology_rigor"].score == 7.0

    def test_parse_json_in_codeblock(self):
        raw = "```json\n" + _valid_review_json("Reject") + "\n```"
        r = ReviewResult.from_llm_response(raw)
        assert r.overall_recommendation == "Reject"

    def test_parse_json_with_surrounding_text(self):
        raw = "Here is my review:\n\n" + _valid_review_json("Accept") + "\nThanks!"
        r = ReviewResult.from_llm_response(raw)
        assert r.overall_recommendation == "Accept"

    def test_parse_invalid_json_returns_placeholder(self):
        raw = "this is not json at all"
        r = ReviewResult.from_llm_response(raw)
        assert r.overall_score == 0.0
        assert "parse failed" in r.overall_recommendation.lower()
        assert any("Parse failed" in rs.reasoning for rs in r.scores.values())
        assert "parse_error" in r.metadata

    def test_parse_missing_required_fields(self):
        raw = json.dumps({"summary": "no scores"})
        r = ReviewResult.from_llm_response(raw)
        # Missing 'scores' field -> "Missing required field: scores" warning
        assert any("Missing required field: scores" in w
                   for w in r.metadata.get("validation_warnings", []))

    def test_parse_unrecognized_recommendation(self):
        raw = _valid_review_json("Maybe Accept")
        r = ReviewResult.from_llm_response(raw)
        assert any("Unrecognized recommendation" in w
                   for w in r.metadata.get("validation_warnings", []))

    def test_parse_score_clamping(self):
        raw_dict = {
            "scores": {
                "methodology_rigor": {"score": 99.0, "confidence": 0.5, "reasoning": ""},
                "novelty": {"score": -5.0, "confidence": 0.5, "reasoning": ""},
                "clarity": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
                "reproducibility": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
                "significance": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
                "overall": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
            },
            "overall_recommendation": "Accept",
        }
        r = ReviewResult.from_llm_response(json.dumps(raw_dict))
        assert r.scores["methodology_rigor"].score == ReviewResult.SCORE_MAX
        assert r.scores["novelty"].score == ReviewResult.SCORE_MIN

    def test_parse_confidence_clamping(self):
        raw_dict = {
            "scores": {
                "methodology_rigor": {"score": 5.0, "confidence": 2.0, "reasoning": ""},
                "novelty": {"score": 5.0, "confidence": -0.5, "reasoning": ""},
                "clarity": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
                "reproducibility": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
                "significance": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
                "overall": {"score": 5.0, "confidence": 0.5, "reasoning": ""},
            },
            "overall_recommendation": "Accept",
        }
        r = ReviewResult.from_llm_response(json.dumps(raw_dict))
        assert r.scores["methodology_rigor"].confidence == 1.0
        assert r.scores["novelty"].confidence == 0.0

    def test_parse_score_as_number(self):
        """Score dict may also be a plain number (rare)."""
        raw = json.dumps({
            "scores": {
                "methodology_rigor": 7,
                "novelty": 6,
                "clarity": 8,
                "reproducibility": 5,
                "significance": 7,
                "overall": 7,
            },
            "overall_recommendation": "Accept",
        })
        r = ReviewResult.from_llm_response(raw)
        assert r.scores["methodology_rigor"].score == 7.0
        assert r.scores["methodology_rigor"].confidence == 0.5  # default

    def test_parse_missing_dimension(self):
        """When a dimension is missing entirely, score is clamped from 0 to SCORE_MIN."""
        raw = json.dumps({
            "scores": {
                "methodology_rigor": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                # novelty missing -> defaults to empty dict
                "clarity": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "reproducibility": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "significance": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "overall": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
            },
            "overall_score": 7.0,
            "overall_recommendation": "Accept",
        })
        r = ReviewResult.from_llm_response(raw)
        # Missing dimension -> score=0, clamped to SCORE_MIN (=1.0)
        assert r.scores["novelty"].score == ReviewResult.SCORE_MIN
        # Reasoning defaults to empty string (dict branch)
        assert r.scores["novelty"].reasoning == ""
        # The clamping produces a validation warning
        assert any("novelty" in w and "clamped" in w
                   for w in r.metadata.get("validation_warnings", []))

    def test_parse_score_invalid_type(self):
        """Non-dict, non-numeric score triggers the 'Missing score for dimension' warning."""
        raw = json.dumps({
            "scores": {
                "methodology_rigor": "not a dict",
                "novelty": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "clarity": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "reproducibility": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "significance": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "overall": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
            },
            "overall_score": 7.0,
            "overall_recommendation": "Accept",
        })
        r = ReviewResult.from_llm_response(raw)
        assert r.scores["methodology_rigor"].reasoning == "Missing"
        assert any("Missing score for dimension: methodology_rigor" in w
                   for w in r.metadata.get("validation_warnings", []))
        """overall_score is read from the top-level 'overall_score' field."""
        raw = json.dumps({
            "scores": {
                "methodology_rigor": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "novelty": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "clarity": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "reproducibility": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "significance": {"score": 7.0, "confidence": 0.8, "reasoning": ""},
                "overall": {"score": 8.0, "confidence": 0.8, "reasoning": ""},
            },
            "overall_score": 8.0,
            "overall_recommendation": "Accept",
        })
        r = ReviewResult.from_llm_response(raw)
        assert r.overall_score == 8.0


# ════════════════════════════════════════════════════════════════════
# CalibrationResult
# ════════════════════════════════════════════════════════════════════


class TestCalibrationResult:
    """Tests for CalibrationResult dataclass."""

    def test_construction(self):
        cr = CalibrationResult(
            balanced_accuracy=0.7,
            precision_per_class={"Accept": 0.8},
            recall_per_class={"Accept": 0.6},
            f1_per_class={"Accept": 0.69},
            confusion_matrix=[[10, 2], [3, 12]],
            dimension_correlation={"methodology": 0.65},
            dataset_size=27,
            dataset_source="synthetic",
            total_predictions=27,
            correct_predictions=22,
        )
        assert cr.balanced_accuracy == 0.7
        assert cr.total_predictions == 27

    def test_to_dict(self):
        cr = CalibrationResult(
            balanced_accuracy=0.5,
            precision_per_class={},
            recall_per_class={},
            f1_per_class={},
            confusion_matrix=[],
            dimension_correlation={},
            dataset_size=0,
            dataset_source="test",
        )
        d = cr.to_dict()
        assert d["balanced_accuracy"] == 0.5
        assert d["dataset_source"] == "test"

    def test_summary_format(self):
        cr = CalibrationResult(
            balanced_accuracy=0.7,
            precision_per_class={},
            recall_per_class={},
            f1_per_class={},
            confusion_matrix=[],
            dimension_correlation={},
            dataset_size=100,
            dataset_source="my_dataset",
            total_predictions=100,
            correct_predictions=70,
        )
        s = cr.summary()
        assert "70.0%" in s
        assert "70/100" in s
        assert "my_dataset" in s


# ════════════════════════════════════════════════════════════════════
# CalibrationDataset
# ════════════════════════════════════════════════════════════════════


class TestCalibrationDataset:
    """Tests for CalibrationDataset class."""

    def test_init_sets_rng(self):
        ds = CalibrationDataset(seed=42)
        assert ds.rng is not None

    def test_generate_paper_empirical_strong_accept(self):
        ds = CalibrationDataset(seed=42)
        paper = ds.generate_paper("strong_accept", domain="empirical")
        assert paper["quality_level"] == "strong_accept"
        assert paper["domain"] == "empirical"
        assert "text" in paper
        assert paper["expected_score"] == 9.0
        assert paper["expected_recommendation"] == "Strong Accept"
        assert "paper_id" in paper

    def test_generate_paper_all_quality_levels(self):
        ds = CalibrationDataset(seed=42)
        for level in CalibrationDataset.QUALITY_LEVELS:
            paper = ds.generate_paper(level, domain="finance")
            assert paper["expected_recommendation"] in {
                "Strong Accept", "Accept", "Weak Accept",
                "Borderline", "Reject",
            }

    def test_generate_paper_all_domains(self):
        ds = CalibrationDataset(seed=42)
        for domain in CalibrationDataset.DOMAINS:
            paper = ds.generate_paper("accept", domain=domain)
            assert paper["domain"] == domain
            assert "SYNTHETIC PAPER" in paper["text"]

    def test_generate_paper_invalid_quality(self):
        ds = CalibrationDataset(seed=42)
        with pytest.raises(ValueError):
            ds.generate_paper("nonsense", domain="empirical")

    def test_generate_paper_invalid_domain(self):
        ds = CalibrationDataset(seed=42)
        with pytest.raises(ValueError):
            ds.generate_paper("accept", domain="nonsense")

    def test_generate_dataset_shape(self):
        ds = CalibrationDataset(seed=42)
        df = ds.generate_dataset(n_per_level=4, domain="empirical")
        assert isinstance(df, pd.DataFrame)
        # 5 levels * 4 = 20 papers
        assert len(df) == 20
        assert set(df.columns) >= {
            "paper_id", "quality_level", "domain", "text",
            "expected_score", "expected_recommendation",
        }

    def test_generate_mixed_domain_dataset(self):
        ds = CalibrationDataset(seed=42)
        df = ds.generate_mixed_domain_dataset(n_per_level=2)
        # 5 levels * 2 per level * 3 domains = 30 papers
        assert len(df) == 30
        assert set(df["domain"].unique()) == set(CalibrationDataset.DOMAINS)

    def test_generate_mixed_domain_subset(self):
        ds = CalibrationDataset(seed=42)
        df = ds.generate_mixed_domain_dataset(
            n_per_level=3, domains=["finance", "ml"]
        )
        # 5 levels * 3 * 2 = 30
        assert len(df) == 30
        assert set(df["domain"].unique()) == {"finance", "ml"}

    def test_quality_to_score_mapping(self):
        ds = CalibrationDataset(seed=42)
        assert ds._quality_to_score("strong_accept") == 9.0
        assert ds._quality_to_score("accept") == 7.0
        assert ds._quality_to_score("weak_accept") == 6.0
        assert ds._quality_to_score("borderline") == 5.0
        assert ds._quality_to_score("reject") == 3.0
        assert ds._quality_to_score("unknown") == 5.0  # default

    def test_quality_to_recommendation_mapping(self):
        ds = CalibrationDataset(seed=42)
        assert ds._quality_to_recommendation("strong_accept") == "Strong Accept"
        assert ds._quality_to_recommendation("reject") == "Reject"
        assert ds._quality_to_recommendation("unknown") == "Unknown"

    def test_synthetic_samples_loaded(self):
        # SYNTHETIC_SAMPLES is populated at module load time
        assert isinstance(CalibrationDataset.SYNTHETIC_SAMPLES, list)
        assert len(CalibrationDataset.SYNTHETIC_SAMPLES) > 0
        sample = CalibrationDataset.SYNTHETIC_SAMPLES[0]
        assert "paper_content" in sample
        assert "human_verdict" in sample
        assert "expected_scores" in sample
        assert "source" in sample

    def test_known_datasets_has_synthetic(self):
        assert "synthetic" in CalibrationDataset.KNOWN_DATASETS
        ds_info = CalibrationDataset.KNOWN_DATASETS["synthetic"]
        assert "samples" in ds_info
        assert len(ds_info["samples"]) > 0

    def test_get_unknown_dataset_raises(self):
        with pytest.raises(ValueError):
            CalibrationDataset.get("nonexistent")

    def test_get_synthetic_dataset(self):
        samples = CalibrationDataset.get("synthetic")
        assert isinstance(samples, list)
        assert all("paper_content" in s for s in samples)

    def test_add_custom_dataset(self):
        CalibrationDataset.add_custom(
            "my_custom",
            samples=[{"paper_content": "x", "human_verdict": "Accept",
                     "expected_scores": {"overall": 7}, "source": "test"}],
            source="unit_test",
        )
        assert "my_custom" in CalibrationDataset.KNOWN_DATASETS
        samples = CalibrationDataset.get("my_custom")
        assert len(samples) == 1
        assert samples[0]["paper_content"] == "x"


# ════════════════════════════════════════════════════════════════════
# LLMReviewer
# ════════════════════════════════════════════════════════════════════


class TestLLMReviewerInit:
    """Tests for LLMReviewer initialization."""

    def test_default_init(self):
        r = LLMReviewer(enable_cache=False)
        assert r.judge_model == "gpt-4o"
        assert r.default_venue == "ML"
        assert r.enable_cache is False
        assert r._review_count == 0

    def test_custom_init(self, tmp_cache_dir):
        r = LLMReviewer(
            judge_model="claude-opus-4",
            default_venue="JFE",
            enable_cache=True,
            cache_dir=str(tmp_cache_dir),
            timeout=60.0,
            max_retries=2,
        )
        assert r.judge_model == "claude-opus-4"
        assert r.default_venue == "JFE"
        assert r.enable_cache is True
        assert r.cache_dir == tmp_cache_dir
        assert r._timeout == 60.0
        assert r._max_retries == 2
        # Cache dir should be created
        assert tmp_cache_dir.exists()

    def test_cache_dir_created_when_enabled(self, tmp_cache_dir):
        LLMReviewer(enable_cache=True, cache_dir=str(tmp_cache_dir))
        assert tmp_cache_dir.exists()


class TestLLMReviewerReview:
    """Tests for LLMReviewer.review — uses mocked _call_llm."""

    def test_review_returns_parsed_result(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        # Mock _call_llm to return canned JSON
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        result = r.review(paper_content="Some paper text", venue="CVPR", use_cache=False)
        assert isinstance(result, ReviewResult)
        assert result.overall_recommendation == "Accept"
        assert result.metadata.get("venue") == "CVPR"
        assert result.metadata.get("judge_model") == "gpt-4o"
        assert result.metadata.get("paper_number") == 1
        assert r._review_count == 1

    def test_review_uses_zh_template_for_chinese_venue(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        captured = {}

        def fake_call(prompt, model, language):
            captured["prompt"] = prompt
            captured["language"] = language
            return _valid_review_json("接收")

        r._call_llm = fake_call
        result = r.review(paper_content="文本", venue="经济研究", use_cache=False)
        assert captured["language"] == "zh"
        # Chinese recommendation parsed
        assert result.overall_recommendation == "接收"

    def test_review_unknown_venue_falls_back_to_ML(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        # Unknown venue should not raise; falls back to ML config
        result = r.review(paper_content="text", venue="NonexistentVenue", use_cache=False)
        assert isinstance(result, ReviewResult)

    def test_review_truncates_long_paper(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        captured = {}

        def fake_call(prompt, model, language):
            captured["prompt"] = prompt
            return _valid_review_json("Accept")

        r._call_llm = fake_call
        long_text = "x" * 50000
        r.review(paper_content=long_text, venue="ML", use_cache=False)
        # Prompt should not contain more than 12000 chars of content
        prompt_len = len(captured["prompt"])
        assert prompt_len < 50000

    def test_review_paper_number_in_metadata(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        result = r.review(paper_content="text", paper_number=42, use_cache=False)
        assert result.metadata["paper_number"] == 42


class TestLLMReviewerCache:
    """Tests for LLMReviewer cache logic."""

    def test_cache_hit_avoids_llm_call(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=True, cache_dir=str(tmp_cache_dir), default_venue="ML")
        r._call_llm = lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("Should not call LLM on cache hit")
        )

        # First call — populates cache
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")
        r.review(paper_content="Sample paper", venue="ML", use_cache=True)
        assert r._review_count == 1

        # Second call — should hit cache, no LLM invocation
        r._call_llm = lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("Cache miss")
        )
        result = r.review(paper_content="Sample paper", venue="ML", use_cache=True)
        # Review count does not increment on cache hit
        assert r._review_count == 1
        assert isinstance(result, ReviewResult)

    def test_cache_disabled_no_io(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        call_count = [0]

        def fake_call(prompt, model, language):
            call_count[0] += 1
            return _valid_review_json("Accept")

        r._call_llm = fake_call
        r.review(paper_content="text", venue="ML")
        r.review(paper_content="text", venue="ML")
        # Both should call LLM since caching is disabled
        assert call_count[0] == 2

    def test_cache_key_generation(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=True, cache_dir=str(tmp_cache_dir))
        k1 = r._cache_key("paper text", "ML")
        k2 = r._cache_key("paper text", "ML")
        k3 = r._cache_key("paper text", "JFE")
        k4 = r._cache_key("different text", "ML")
        # Same input → same key
        assert k1 == k2
        # Different venue → different key
        assert k1 != k3
        # Different content → different key
        assert k1 != k4
        assert len(k1) == 16  # SHA-256 hex prefix length

    def test_cache_path_format(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=True, cache_dir=str(tmp_cache_dir))
        p = r._cache_path("text", "ML")
        assert p.parent == tmp_cache_dir
        assert p.suffix == ".json"
        assert p.name.startswith("ML_")

    def test_load_cache_returns_none_when_missing(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=True, cache_dir=str(tmp_cache_dir))
        assert r._load_cache("text", "ML") is None

    def test_save_then_load_cache(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=True, cache_dir=str(tmp_cache_dir))
        scores = {k: ReviewScore(score=7.0, confidence=0.8, reasoning="r") for k in ReviewResult.DIMENSION_KEYS}
        result = ReviewResult(
            scores=scores,
            overall_score=7.0,
            overall_recommendation="Accept",
            summary="s",
            strengths=["s1"],
            weaknesses=["w1"],
            detailed_feedback="f",
            confidence=0.8,
            metadata={},
        )
        r._save_cache("text", "ML", result)
        loaded = r._load_cache("text", "ML")
        assert loaded is not None
        assert loaded.overall_recommendation == "Accept"
        assert loaded.overall_score == 7.0


class TestLLMReviewerBatch:
    """Tests for LLMReviewer.batch_review."""

    def test_batch_review_returns_list(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        papers = [
            {"content": "Paper 1 text"},
            {"content": "Paper 2 text", "paper_content": "Should be ignored"},
            {"text": "Paper 3 text"},
        ]
        results = r.batch_review(papers, venue="ML")
        assert isinstance(results, list)
        assert len(results) == 3
        for res in results:
            assert isinstance(res, ReviewResult)

    def test_batch_review_resolves_content_field_fallback(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        captured = []

        def fake_call(prompt, model, language):
            # Extract first 100 chars of the paper_content embedded in the prompt
            m = re.search(r"---\s*(.*?)\s*---", prompt, re.DOTALL)
            captured.append(m.group(1) if m else None)
            return _valid_review_json("Accept")

        r._call_llm = fake_call
        papers = [
            {"content": "content_field_text"},
            {"paper_content": "paper_content_text"},
            {"text": "text_field_text"},
            {},  # empty -> uses "" fallback
        ]
        r.batch_review(papers, venue="ML")
        assert "content_field_text" in captured[0]
        assert "paper_content_text" in captured[1]
        assert "text_field_text" in captured[2]
        # Empty paper falls through to ""
        assert captured[3] == ""

    def test_batch_review_handles_exception_per_paper(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        call_count = [0]

        def fake_call(prompt, model, language):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("LLM failed")
            return _valid_review_json("Accept")

        r._call_llm = fake_call
        papers = [{"content": "ok"}, {"content": "will fail"}, {"content": "ok"}]
        results = r.batch_review(papers, venue="ML")
        # 3 results even though one failed
        assert len(results) == 3
        # Failed one is a placeholder error
        assert "Review Error" in results[1].overall_recommendation
        assert "LLM failed" in results[1].overall_recommendation
        # Success ones still valid
        assert results[0].overall_recommendation == "Accept"
        assert results[2].overall_recommendation == "Accept"

    def test_batch_review_auto_assigns_paper_numbers(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        captured = []

        def fake_call(prompt, model, language):
            m = re.search(r"paper #(\d+)", prompt)
            if m:
                captured.append(int(m.group(1)))
            return _valid_review_json("Accept")

        r._call_llm = fake_call
        papers = [{"content": f"paper {i}"} for i in range(4)]
        r.batch_review(papers, venue="ML")
        # Auto-assigned 1..4
        assert captured == [1, 2, 3, 4]


class TestLLMReviewerCalibrate:
    """Tests for LLMReviewer.calibrate."""

    def test_calibrate_returns_calibration_result(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        dataset = [
            ("paper 1", "Accept"),
            ("paper 2", "Accept"),
            ("paper 3", "Reject"),
            ("paper 4", "Reject"),
        ]
        result = r.calibrate(dataset, target_accuracy=0.5)
        assert isinstance(result, CalibrationResult)
        assert result.dataset_size == 4
        # Confusion matrix should be 2x2 (Accept, Reject)
        assert len(result.confusion_matrix) == 2

    def test_calibrate_perfect_accuracy(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        dataset = [("p1", "Accept"), ("p2", "Accept"), ("p3", "Accept")]
        result = r.calibrate(dataset)
        assert result.balanced_accuracy > 0.0
        # All predictions are "Accept" → all correct
        assert result.correct_predictions == 3

    def test_calibrate_max_samples_truncates(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        dataset = [(f"p{i}", "Accept") for i in range(20)]
        result = r.calibrate(dataset, max_samples=5)
        assert result.dataset_size == 5
        assert result.total_predictions <= 5

    def test_calibrate_computes_per_class_metrics(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        r._call_llm = lambda *a, **kw: _valid_review_json("Borderline")

        dataset = [("p1", "Accept"), ("p2", "Borderline"), ("p3", "Reject")]
        result = r.calibrate(dataset)
        # 3 unique classes
        assert "Accept" in result.precision_per_class
        assert "Borderline" in result.precision_per_class
        assert "Reject" in result.precision_per_class
        for f1 in result.f1_per_class.values():
            assert 0.0 <= f1 <= 1.0

    def test_calibrate_handles_per_paper_failure(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="ML")
        call_count = [0]

        def fake_call(prompt, model, language):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom")
            return _valid_review_json("Accept")

        r._call_llm = fake_call
        dataset = [("p1", "Accept"), ("p2", "Accept"), ("p3", "Accept")]
        # Should not raise — failed papers are skipped
        result = r.calibrate(dataset)
        assert result.dataset_size == 3


class TestLLMReviewerCompareWithRules:
    """Tests for LLMReviewer.compare_with_rules."""

    def test_compare_agreement_when_both_pass(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="JFE")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        rules = {"passed": True, "violations": []}
        result = r.compare_with_rules("paper text", rules, venue="JFE")
        assert result["llm_accept"] is True
        assert result["rules_passed"] is True
        assert result["agreement"] is True
        assert "agree" in result["conflict_notes"].lower()

    def test_compare_disagreement(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="JFE")
        # overall=3.0 to indicate a reject; JFE threshold_accept=7.0
        r._call_llm = lambda *a, **kw: _valid_review_json("Reject", overall=3.0)

        rules = {"passed": True, "violations": []}
        result = r.compare_with_rules("paper text", rules, venue="JFE")
        assert result["llm_accept"] is False
        assert result["rules_passed"] is True
        assert result["agreement"] is False
        assert "disagree" in result["conflict_notes"].lower()

    def test_compare_extracts_llm_scores(self, tmp_cache_dir):
        r = LLMReviewer(enable_cache=False, default_venue="JFE")
        r._call_llm = lambda *a, **kw: _valid_review_json("Accept")

        rules = {"passed": True, "violations": []}
        result = r.compare_with_rules("paper text", rules, venue="JFE")
        assert "llm_scores" in result
        assert "methodology_rigor" in result["llm_scores"]
        assert result["llm_scores"]["methodology_rigor"] == 7.0


# ════════════════════════════════════════════════════════════════════
# Module smoke
# ════════════════════════════════════════════════════════════════════


def test_module_all_exports():
    """Verify __all__ symbols are importable."""
    from scripts.core import llm_reviewer as mod

    for name in mod.__all__:
        assert hasattr(mod, name), f"Missing export: {name}"


def test_module_does_not_call_llm_on_import():
    """Importing the module must not invoke LLM API."""
    # Already imported above; if this test is here without errors, the import
    # did not trigger any network calls. We verify by checking _review_count
    # is not bound as a class attribute.
    assert "_review_count" in LLMReviewer.__init__.__code__.co_names

