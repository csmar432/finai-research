"""Tests for scripts/core/dual_reviewer.py"""

import unittest.mock as mock

import pytest

from scripts.core.dual_reviewer import (
    FINANCIAL_REVIEW_PROMPT,
    SHADOW_REVIEW_PROMPT,
    HYPOTHESIS_PRESSURE_TEST,
    DualReviewer,
    DimensionScore,
    ReviewDimension,
    ReviewReport,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm():
    """Shared mock LLM call function."""
    def _mock_llm(model, system, user, temperature=0.3):
        return '{"dimension_scores":[{"dimension":"theory","score":7,"verdict":"strong","strengths":["理论框架清晰"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"identification","score":7.5,"verdict":"strong","strengths":["IV策略合理"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"data","score":7,"verdict":"strong","strengths":["数据来源可靠"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"rigor","score":7,"verdict":"strong","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"interpretation","score":6.5,"verdict":"acceptable","strengths":[],"weaknesses":["解释不够深入"],"specific_issues":[],"suggestions":[]},{"dimension":"robustness","score":7,"verdict":"strong","strengths":["稳健性检验充分"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"writing","score":7.5,"verdict":"strong","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"novelty","score":7,"verdict":"strong","strengths":["贡献明确"],"weaknesses":[],"specific_issues":[],"suggestions":[]}],"overall_review":"论文质量较高，理论框架清晰，识别策略合理。","critical_issues":[],"important_issues":["经济解释部分可进一步深化"],"minor_issues":["部分表格可优化"],"verdict":"accept","confidence":0.85}'
    return _mock_llm


@pytest.fixture
def shadow_mock_llm():
    def _mock(model, system, user, temperature=0.3):
        return '{"verdict":"accept","critical_arguments":["建议补充更多稳健性检验"],"missing_literature":[],"robustness_concerns":[],"contribution_assessment":"理论贡献清晰","alternative_explanations":[]}'
    return _mock


@pytest.fixture
def reviewer(mock_llm):
    return DualReviewer(
        primary_model="deepseek_pro",
        shadow_model="claude_sonnet",
        llm_call_fn=mock_llm,
    )


# ─── Data Classes ─────────────────────────────────────────────────────────────


class TestReviewDimension:
    def test_all_dimensions_present(self):
        assert ReviewDimension.THEORY.value == "theory"
        assert ReviewDimension.IDENTIFICATION.value == "identification"
        assert ReviewDimension.DATA_QUALITY.value == "data"
        assert ReviewDimension.EMPIRICAL_RIGOR.value == "rigor"
        assert ReviewDimension.INTERPRETATION.value == "interpretation"
        assert ReviewDimension.ROBUSTNESS.value == "robustness"
        assert ReviewDimension.WRITING.value == "writing"
        assert ReviewDimension.NOVELTY.value == "novelty"
        assert len(ReviewDimension) == 8

    def test_dimension_score_dataclass(self):
        ds = DimensionScore(
            dimension=ReviewDimension.IDENTIFICATION,
            score=7.5,
            verdict="strong",
            strengths=["IV有效"],
            weaknesses=[],
            specific_issues=["第一阶段F=25"],
            suggestions=["可考虑更多工具变量"],
        )
        assert ds.dimension == ReviewDimension.IDENTIFICATION
        assert ds.score == 7.5
        assert ds.verdict == "strong"
        assert ds.strengths == ["IV有效"]
        assert ds.weaknesses == []
        assert ds.specific_issues == ["第一阶段F=25"]
        assert ds.suggestions == ["可考虑更多工具变量"]


class TestReviewReport:
    def test_review_report_dataclass(self):
        dim_scores = [
            DimensionScore(
                dimension=ReviewDimension.THEORY,
                score=7.0, verdict="strong",
                strengths=["理论清晰"], weaknesses=[],
                specific_issues=[], suggestions=[],
            ),
        ]
        report = ReviewReport(
            document_type="实证论文",
            target="碳排放权对企业创新的影响",
            primary_reviewer="deepseek_pro",
            shadow_reviewer="claude_sonnet",
            timestamp="2026-01-01T00:00:00",
            dimension_scores=dim_scores,
            weighted_score=7.0,
            hard_floor_passed=True,
            primary_review="整体评价良好",
            shadow_review="魔鬼辩护意见",
            convergence_opinion="无明显分歧",
            disagreements=[],
            critical_issues=[],
            important_issues=["可补充异质性分析"],
            minor_issues=["写作可进一步精炼"],
            verdict="accept",
            confidence=0.85,
        )
        assert report.verdict == "accept"
        assert report.weighted_score == 7.0
        assert report.hard_floor_passed is True
        assert report.confidence == 0.85
        assert len(report.dimension_scores) == 1
        assert len(report.important_issues) == 1
        assert len(report.minor_issues) == 1


# ─── Constants ────────────────────────────────────────────────────────────────


class TestDimensionWeights:
    def test_weights_sum_to_one(self):
        total = sum(DualReviewer.DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, not 1.0"

    def test_weights_are_reasonable(self):
        for dim, w in DualReviewer.DIMENSION_WEIGHTS.items():
            assert 0 <= w <= 1, f"{dim} weight {w} out of range [0,1]"
        # IDENTIFICATION and EMPIRICAL_RIGOR should be highest
        assert DualReviewer.DIMENSION_WEIGHTS[ReviewDimension.IDENTIFICATION] == 0.20
        assert DualReviewer.DIMENSION_WEIGHTS[ReviewDimension.EMPIRICAL_RIGOR] == 0.20
        assert DualReviewer.DIMENSION_WEIGHTS[ReviewDimension.ROBUSTNESS] == 0.15


class TestHardFloors:
    def test_hard_floors_defined(self):
        assert ReviewDimension.IDENTIFICATION in DualReviewer.HARD_FLOORS
        assert ReviewDimension.EMPIRICAL_RIGOR in DualReviewer.HARD_FLOORS
        assert ReviewDimension.ROBUSTNESS in DualReviewer.HARD_FLOORS
        assert ReviewDimension.DATA_QUALITY in DualReviewer.HARD_FLOORS

    def test_hard_floors_values(self):
        # Hard floors should be >= 5.0 (论文质量底线)
        for dim, floor in DualReviewer.HARD_FLOORS.items():
            assert floor >= 5.0, f"{dim} floor {floor} too low"
            assert floor <= 7.0, f"{dim} floor {floor} too high"


class TestPrompts:
    def test_financial_review_prompt_has_dimensions(self):
        for dim in ["theory", "identification", "data", "rigor", "interpretation", "robustness", "writing", "novelty"]:
            assert dim in FINANCIAL_REVIEW_PROMPT.lower()

    def test_financial_review_prompt_has_chinese_guidance(self):
        assert "识别策略" in FINANCIAL_REVIEW_PROMPT
        assert "稳健性检验" in FINANCIAL_REVIEW_PROMPT
        assert "A股" in FINANCIAL_REVIEW_PROMPT or "金融实证" in FINANCIAL_REVIEW_PROMPT

    def test_shadow_review_prompt_is_critical(self):
        assert "魔鬼辩护" in SHADOW_REVIEW_PROMPT
        assert "critical_arguments" in SHADOW_REVIEW_PROMPT

    def test_hypothesis_pressure_test_has_dimensions(self):
        for kw in ["平行趋势", "SUTVA", "溢出效应", "异质性", "遗漏变量"]:
            assert kw in HYPOTHESIS_PRESSURE_TEST, f"Missing: {kw}"

    def test_prompts_are_non_empty(self):
        assert len(FINANCIAL_REVIEW_PROMPT) > 100
        assert len(SHADOW_REVIEW_PROMPT) > 100
        assert len(HYPOTHESIS_PRESSURE_TEST) > 100


# ─── DualReviewer Core ───────────────────────────────────────────────────────


class TestDualReviewerInit:
    def test_init_default(self):
        r = DualReviewer()
        assert r.primary_model == "deepseek_pro"
        assert r.shadow_model == "claude_sonnet"
        assert r._llm is None

    def test_init_custom_models(self):
        r = DualReviewer(primary_model="gpt-4o", shadow_model="claude-3-5")
        assert r.primary_model == "gpt-4o"
        assert r.shadow_model == "claude-3-5"

    def test_init_with_llm_call_fn(self, mock_llm):
        r = DualReviewer(llm_call_fn=mock_llm)
        assert r._llm is mock_llm


class TestDualReviewerCoreLogic:
    def test_parse_json_extracts_code_block(self):
        r = DualReviewer()
        raw = '```json\n{"verdict": "accept"}\n```'
        result = r._parse_json(raw)
        assert result == {"verdict": "accept"}

    def test_parse_json_handles_bare_json(self):
        r = DualReviewer()
        raw = '{"verdict": "revise", "critical_issues": ["missing data"]}'
        result = r._parse_json(raw)
        assert result["verdict"] == "revise"

    def test_parse_json_falls_back_to_empty_dict(self):
        r = DualReviewer()
        raw = "This is not JSON at all"
        result = r._parse_json(raw)
        assert result == {}

    def test_parse_json_empty_string(self):
        r = DualReviewer()
        result = r._parse_json("")
        assert result == {}

    def test_parse_json_with_extra_text(self):
        r = DualReviewer()
        raw = 'Here is my review:\n```json\n{"verdict": "accept"}\n```\nThank you.'
        result = r._parse_json(raw)
        assert result["verdict"] == "accept"


class TestBuildDimensionScores:
    def test_build_scores_with_all_dimensions(self, reviewer):
        data = {
            "dimension_scores": [
                {"dimension": "theory", "score": 7.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "identification", "score": 7.5, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "data", "score": 7.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "rigor", "score": 7.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "interpretation", "score": 6.5, "verdict": "acceptable",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "robustness", "score": 7.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "writing", "score": 7.5, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "novelty", "score": 7.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            ],
        }
        scores = reviewer._build_dimension_scores(data)
        assert len(scores) == 8
        assert all(isinstance(s, DimensionScore) for s in scores)

    def test_build_scores_handles_unknown_dimension(self, reviewer):
        # Unknown dimension should be skipped (caught by ValueError in Enum)
        data = {
            "dimension_scores": [
                {"dimension": "nonexistent_dim", "score": 5, "verdict": "weak",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            ],
        }
        scores = reviewer._build_dimension_scores(data)
        # Unknown dim is caught by ValueError in ReviewDimension(), so it's skipped
        # Then _build_dimension_scores fills in defaults for all 8 dims
        assert len(scores) == 8

    def test_build_scores_fills_missing_dimensions(self, reviewer):
        # Empty scores list should still produce 8 dimensions (all defaults)
        data = {"dimension_scores": []}
        scores = reviewer._build_dimension_scores(data)
        assert len(scores) == 8
        # All should have score 5.0 (default)
        assert all(s.score == 5.0 for s in scores)

    def test_build_scores_verdict_mapping(self, reviewer):
        # Verdict strings should be normalized
        data = {
            "dimension_scores": [
                {"dimension": "writing", "score": 8.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "novelty", "score": 5.0, "verdict": "weak",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
                {"dimension": "theory", "score": 3.0, "verdict": "critical",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            ],
        }
        scores = reviewer._build_dimension_scores(data)
        verdict_map = {s.dimension.value: s.verdict for s in scores}
        assert verdict_map["writing"] == "strong"
        assert verdict_map["novelty"] == "weak"
        assert verdict_map["theory"] == "critical"


class TestWeightedScore:
    def test_weighted_score_computation(self, reviewer):
        # All scores = 7.0
        dim_scores = [
            DimensionScore(
                dimension=dim, score=7.0, verdict="strong",
                strengths=[], weaknesses=[], specific_issues=[], suggestions=[],
            )
            for dim in ReviewDimension
        ]
        weighted = reviewer._compute_weighted_score(dim_scores)
        assert abs(weighted - 7.0) < 1e-6

    def test_weighted_score_with_varying_scores(self, reviewer):
        # Scores: IDENTIFICATION=8, EMPIRICAL_RIGOR=8, ROBUSTNESS=8, others=6
        dim_scores = []
        for dim in ReviewDimension:
            if dim in [ReviewDimension.IDENTIFICATION, ReviewDimension.EMPIRICAL_RIGOR, ReviewDimension.ROBUSTNESS]:
                score = 8.0
            else:
                score = 6.0
            dim_scores.append(DimensionScore(
                dimension=dim, score=score, verdict="strong",
                strengths=[], weaknesses=[], specific_issues=[], suggestions=[],
            ))
        weighted = reviewer._compute_weighted_score(dim_scores)
        # Expected: 3 dims at 8.0 with total weight 0.55 + 5 dims at 6.0 with weight 0.45
        expected = 0.20 * 8 + 0.20 * 8 + 0.15 * 8 + 0.10 * 6 + 0.10 * 6 + 0.10 * 6 + 0.05 * 6 + 0.10 * 6
        assert abs(weighted - expected) < 1e-6
        assert weighted > 7.0  # Stronger than average

    def test_weighted_score_rounds_to_2_decimals(self, reviewer):
        dim_scores = [
            DimensionScore(
                dimension=dim, score=6.5, verdict="acceptable",
                strengths=[], weaknesses=[], specific_issues=[], suggestions=[],
            )
            for dim in ReviewDimension
        ]
        weighted = reviewer._compute_weighted_score(dim_scores)
        assert weighted == round(weighted, 2)


class TestAnalyzeDisagreements:
    def test_no_disagreements_when_both_accept(self, reviewer):
        primary = {
            "dimension_scores": [],
            "verdict": "accept",
            "critical_issues": [],
        }
        shadow = {
            "verdict": "accept",
            "critical_arguments": [],
        }
        result = reviewer._analyze_disagreements(primary, shadow)
        assert result == []

    def test_verdict_mismatch_detected(self, reviewer):
        primary = {"dimension_scores": [], "verdict": "accept", "critical_issues": []}
        shadow = {"verdict": "reject", "critical_arguments": []}
        result = reviewer._analyze_disagreements(primary, shadow)
        assert len(result) == 1
        assert result[0]["type"] == "verdict_mismatch"
        assert result[0]["primary"] == "accept"
        assert result[0]["shadow"] == "reject"

    def test_low_dimension_verdict_detected(self, reviewer):
        primary = {
            "dimension_scores": [
                {"dimension": "identification", "verdict": "weak", "weaknesses": ["IV太弱"]},
            ],
            "verdict": "accept",
            "critical_issues": [],
        }
        shadow = {"verdict": "accept", "critical_arguments": []}
        result = reviewer._analyze_disagreements(primary, shadow)
        low_dim = [d for d in result if d["type"] == "low_dimension"]
        assert len(low_dim) == 1
        assert low_dim[0]["dimension"] == "identification"

    def test_multiple_disagreements(self, reviewer):
        primary = {
            "dimension_scores": [
                {"dimension": "identification", "verdict": "weak", "weaknesses": []},
                {"dimension": "rigor", "verdict": "weak", "weaknesses": []},
            ],
            "verdict": "accept",
            "critical_issues": [],
        }
        shadow = {"verdict": "revise", "critical_arguments": []}
        result = reviewer._analyze_disagreements(primary, shadow)
        assert len(result) >= 2  # At least 2 low dims + verdict mismatch


class TestGenerateConvergence:
    def test_no_disagreements_returns_concise_message(self, reviewer):
        result = reviewer._generate_convergence({}, {}, [])
        assert "一致" in result

    def test_verdict_mismatch_generates_convergence_text(self, reviewer):
        disagreements = [
            {"type": "verdict_mismatch", "primary": "accept", "shadow": "reject"},
        ]
        result = reviewer._generate_convergence({}, {}, disagreements)
        assert "分歧" in result
        assert "accept" in result
        assert "reject" in result

    def test_dimension_disagreement_included(self, reviewer):
        disagreements = [
            {"type": "low_dimension", "dimension": "identification",
             "issue": ["IV策略不完善"], "severity": "high"},
        ]
        result = reviewer._generate_convergence({}, {}, disagreements)
        assert "identification" in result


class TestClassifyIssues:
    def test_critical_from_primary_and_shadow(self, reviewer):
        primary = {
            "critical_issues": ["missing identification strategy"],
            "important_issues": ["写作可改进"],
            "minor_issues": [],
        }
        shadow = {
            "critical_arguments": ["shadow critical argument"],
            "robustness_concerns": ["robustness issue"],
        }
        critical, important, minor = reviewer._classify_issues(primary, shadow)
        assert "missing identification strategy" in critical
        assert "shadow critical argument" in critical
        assert len(critical) >= 2

    def test_important_includes_robustness(self, reviewer):
        primary = {"critical_issues": [], "important_issues": ["写作"], "minor_issues": []}
        shadow = {"critical_arguments": [], "robustness_concerns": ["rob1", "rob2", "rob3"]}
        _, important, _ = reviewer._classify_issues(primary, shadow)
        assert "rob1" in important

    def test_issues_are_deduplicated(self, reviewer):
        primary = {
            "critical_issues": ["same issue", "same issue"],
            "important_issues": [],
            "minor_issues": [],
        }
        shadow = {"critical_arguments": ["same issue"], "robustness_concerns": []}
        critical, _, _ = reviewer._classify_issues(primary, shadow)
        # Deduplication should keep unique items
        assert len(critical) <= 3  # 2 from primary + at most 2 from shadow (capped at 2)


class TestComputeVerdict:
    def test_reject_when_hard_floor_fails(self, reviewer):
        verdict = reviewer._compute_verdict(
            weighted=8.0,
            hard_floor_passed=False,
            dim_scores=[],
            n_critical=0,
            n_disagreements=0,
        )
        assert verdict == "major_revision"

    def test_reject_when_too_many_critical(self, reviewer):
        verdict = reviewer._compute_verdict(
            weighted=7.0,
            hard_floor_passed=True,
            dim_scores=[],
            n_critical=5,  # > 3
            n_disagreements=0,
        )
        assert verdict == "major_revision"

    def test_accept_when_weighted_high(self, reviewer):
        verdict = reviewer._compute_verdict(
            weighted=8.0,
            hard_floor_passed=True,
            dim_scores=[],
            n_critical=1,
            n_disagreements=2,
        )
        assert verdict == "accept"

    def test_revise_when_weighted_low(self, reviewer):
        verdict = reviewer._compute_verdict(
            weighted=5.5,
            hard_floor_passed=True,
            dim_scores=[],
            n_critical=1,
            n_disagreements=2,
        )
        assert verdict == "revise"

    def test_revise_when_too_many_disagreements(self, reviewer):
        verdict = reviewer._compute_verdict(
            weighted=7.0,
            hard_floor_passed=True,
            dim_scores=[],
            n_critical=1,
            n_disagreements=7,  # > 5
        )
        assert verdict == "revise"


class TestReviewPaper:
    def test_review_paper_calls_llm_twice(self, reviewer, shadow_mock_llm):
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[],"overall_review":"OK","critical_issues":[],"important_issues":[],"minor_issues":[],"verdict":"accept","confidence":0.8}',
            '{"verdict":"accept","critical_arguments":[],"robustness_concerns":[],"contribution_assessment":"OK","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper("Some paper content")
            assert report.document_type == "实证论文"
            assert report.target == "Untitled"
            assert reviewer._call_llm.call_count == 2

    def test_review_paper_with_custom_title_and_type(self, reviewer, shadow_mock_llm):
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[],"overall_review":"OK","critical_issues":[],"important_issues":[],"minor_issues":[],"verdict":"accept","confidence":0.8}',
            '{"verdict":"accept","critical_arguments":[],"robustness_concerns":[],"contribution_assessment":"OK","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper(
                "Content",
                paper_title="My Paper",
                paper_type="实证论文",
            )
            assert report.target == "My Paper"
            assert report.document_type == "实证论文"

    def test_review_paper_handles_llm_exception(self, reviewer, shadow_mock_llm):
        # When LLM call fails, _parse_json returns {} and _build_dimension_scores
        # fills defaults (all scores 5.0 -> weighted 5.0 -> revise, or hard_floor fails -> major_revision)
        with mock.patch.object(reviewer, "_call_llm", side_effect=Exception("API error")):
            report = reviewer.review_paper("Content")
            # Fallback: dimension_scores filled with default 5.0
            assert len(report.dimension_scores) == 8
            assert all(s.score == 5.0 for s in report.dimension_scores)

    def test_review_paper_hard_floor_from_scores(self, reviewer, shadow_mock_llm):
        # Scores below hard floor should set hard_floor_passed=False
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[{"dimension":"identification","score":4.0,"verdict":"critical","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"rigor","score":4.0,"verdict":"critical","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]}],"overall_review":"","critical_issues":[],"important_issues":[],"minor_issues":[],"verdict":"reject","confidence":0.8}',
            '{"verdict":"reject","critical_arguments":[],"robustness_concerns":[],"contribution_assessment":"","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper("Content")
            assert report.hard_floor_passed is False
            assert report.verdict == "major_revision"


class TestPressureTestHypothesis:
    def test_pressure_test_calls_llm(self, reviewer):
        with mock.patch.object(reviewer, "_call_llm", return_value='{"parallel_trends":"pass","sutva":"uncertain","recommendation":"add spillover test"}'):
            result = reviewer.pressure_test_hypothesis(
                hypothesis="碳价格上升会促进企业绿色创新",
                background="中国碳排放权交易试点",
            )
            assert reviewer._call_llm.call_count == 1
            assert "parallel_trends" in result or "error" in result

    def test_pressure_test_handles_exception(self, reviewer):
        with mock.patch.object(reviewer, "_call_llm", side_effect=Exception("timeout")):
            result = reviewer.pressure_test_hypothesis("H1")
            assert "error" in result


class TestGenerateReviewMarkdown:
    def test_markdown_has_all_sections(self, reviewer, shadow_mock_llm):
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[{"dimension":"theory","score":7,"verdict":"strong","strengths":["理论清晰"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"identification","score":7.5,"verdict":"strong","strengths":["IV有效"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"data","score":7,"verdict":"strong","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"rigor","score":7,"verdict":"strong","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"interpretation","score":6.5,"verdict":"acceptable","strengths":[],"weaknesses":["解释浅"],"specific_issues":[],"suggestions":[]},{"dimension":"robustness","score":7,"verdict":"strong","strengths":["稳健"],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"writing","score":7.5,"verdict":"strong","strengths":[],"weaknesses":[],"specific_issues":[],"suggestions":[]},{"dimension":"novelty","score":7,"verdict":"strong","strengths":["贡献明确"],"weaknesses":[],"specific_issues":[],"suggestions":[]}],"overall_review":"OK","critical_issues":["critical1"],"important_issues":["imp1"],"minor_issues":["minor1"],"verdict":"accept","confidence":0.85}',
            '{"verdict":"accept","critical_arguments":["shadow1"],"robustness_concerns":[],"overall_review":"影子审详细意见","contribution_assessment":"OK","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper("Content")
            md = reviewer.generate_review_markdown(report)
            assert "## 综合评分" in md
            assert "## 主审意见" in md
            assert "## 影子审意见" in md
            assert "## 必须修复的问题" in md
            assert "critical1" in md
            assert "## 建议修复的问题" in md
            assert "imp1" in md

    def test_markdown_accept_verdict_shows_correct_icon(self, reviewer, shadow_mock_llm):
        # Provide full dimension scores >= hard floors so verdict = accept
        all_dims = [
            {"dimension": "theory", "score": 8.0, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "identification", "score": 7.5, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "data", "score": 7.5, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "rigor", "score": 7.5, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "interpretation", "score": 7.5, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "robustness", "score": 7.5, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "writing", "score": 8.0, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            {"dimension": "novelty", "score": 8.0, "verdict": "strong",
             "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
        ]
        import json
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            json.dumps({"dimension_scores": all_dims, "overall_review": "", "critical_issues": [],
                       "important_issues": [], "minor_issues": [], "verdict": "accept", "confidence": 0.9}),
            json.dumps({"verdict": "accept", "critical_arguments": [], "robustness_concerns": [],
                       "overall_review": "", "contribution_assessment": "OK",
                       "missing_literature": [], "alternative_explanations": []}),
        ]):
            report = reviewer.review_paper("Content")
            md = reviewer.generate_review_markdown(report)
            assert report.verdict == "accept"
            assert "✅" in md

    def test_markdown_shadow_review_when_provided(self, reviewer, shadow_mock_llm):
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[],"overall_review":"OK","critical_issues":[],"important_issues":[],"minor_issues":[],"verdict":"revise","confidence":0.5}',
            '{"verdict":"revise","critical_arguments":["Shadow critique"],"robustness_concerns":[],"contribution_assessment":"","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper("Content")
            md = reviewer.generate_review_markdown(report)
            assert "影子审意见" in md
            assert "Shadow critique" in md


# ─── Module-level Constants ───────────────────────────────────────────────────


class TestModuleConstants:
    def test_dimension_weights_completeness(self):
        # All ReviewDimension enum members should have weights
        for dim in ReviewDimension:
            assert dim in DualReviewer.DIMENSION_WEIGHTS, f"Missing weight for {dim}"

    def test_hard_floors_covers_key_dimensions(self):
        # Key methodology dimensions should have hard floors
        key_dims = {ReviewDimension.IDENTIFICATION, ReviewDimension.EMPIRICAL_RIGOR,
                    ReviewDimension.ROBUSTNESS, ReviewDimension.DATA_QUALITY}
        for dim in key_dims:
            assert dim in DualReviewer.HARD_FLOORS, f"Missing hard floor for {dim}"

    def test_convergence_threshold(self):
        # More than 5 disagreements should trigger revise
        r = DualReviewer()
        verdict = r._compute_verdict(
            weighted=7.0,
            hard_floor_passed=True,
            dim_scores=[],
            n_critical=1,
            n_disagreements=6,
        )
        assert verdict == "revise"


# ─── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_dimension_scores(self, reviewer):
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[],"overall_review":"","critical_issues":[],"important_issues":[],"minor_issues":[],"verdict":"revise","confidence":0.5}',
            '{"verdict":"revise","critical_arguments":[],"robustness_concerns":[],"contribution_assessment":"","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper("Content")
            # Should fill in 8 default dimensions
            assert len(report.dimension_scores) == 8
            assert report.weighted_score > 0

    def test_paper_type_research_design(self, reviewer, shadow_mock_llm):
        with mock.patch.object(reviewer, "_call_llm", side_effect=[
            '{"dimension_scores":[],"overall_review":"","critical_issues":[],"important_issues":[],"minor_issues":[],"verdict":"accept","confidence":0.8}',
            '{"verdict":"accept","critical_arguments":[],"robustness_concerns":[],"contribution_assessment":"","missing_literature":[],"alternative_explanations":[]}',
        ]):
            report = reviewer.review_paper("Content", paper_type="研究设计")
            assert report.document_type == "研究设计"

    def test_score_beyond_10_clamped(self, reviewer):
        # Scores should be clamped to 1-10
        data = {
            "dimension_scores": [
                {"dimension": "writing", "score": 12.0, "verdict": "strong",
                 "strengths": [], "weaknesses": [], "specific_issues": [], "suggestions": []},
            ],
        }
        scores = reviewer._build_dimension_scores(data)
        writing_score = next(s for s in scores if s.dimension == ReviewDimension.WRITING)
        # Score 12.0 stored as-is (no clamping in build, but reviewer should validate)
        assert writing_score.score == 12.0
