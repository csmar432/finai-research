"""Tests for scripts/core/auto_review_rules.py."""

from __future__ import annotations

import pytest

from scripts.core.auto_review_rules import (
    AutoReviewRules,
    AutoReviewRule,
    AutoReviewScore,
)


class TestAutoReviewRule:
    def test_data_description_check(self):
        rule = AutoReviewRule("test", {
            "severity": "error",
            "halt_on_fail": True,
            "validation": {"type": "data_description_check", "rules": []},
        })
        content = "数据来源为CSMAR数据库，样本选取A股上市公司，时间范围2010-2023年。"
        result = rule.score(content)
        assert result["score"] > 0
        assert "issues" in result

    def test_method_check(self):
        rule = AutoReviewRule("test", {
            "severity": "error",
            "halt_on_fail": True,
            "validation": {"type": "method_check", "rules": []},
        })
        content = "使用双向固定效应模型，标准误聚类到企业层面。"
        result = rule.score(content)
        assert "score" in result

    def test_robustness_check(self):
        rule = AutoReviewRule("test", {
            "severity": "error",
            "halt_on_fail": True,
            "validation": {"type": "robustness_check", "min_tests": 2, "rules": []},
        })
        content = "替换被解释变量和替换核心解释变量的结果均稳健。"
        result = rule.score(content)
        assert "passed" in result


class TestAutoReviewRules:
    def test_load_rules(self):
        arr = AutoReviewRules(domain="empirical_paper")
        assert len(arr.rules) > 0
        assert arr.domain == "empirical_paper"

    def test_score_paper_basic(self):
        arr = AutoReviewRules(domain="empirical_paper")
        chapters = {
            "Introduction": "This paper studies the effect of carbon trading on innovation. We develop hypotheses based on Porter hypothesis. H1: Carbon trading promotes innovation." * 20,
            "Methodology": "We use DID approach with two-way fixed effects. Standard errors clustered at firm level." * 20,
        }
        score = arr.score_paper(chapters)
        assert isinstance(score, AutoReviewScore)
        assert 0.0 <= score.overall <= 100.0
        assert score.level in ("A", "B", "C", "D", "F")
        assert "dimension_scores" in score.__dict__
        assert "critical_issues" in score.__dict__

    def test_score_chapter(self):
        arr = AutoReviewRules(domain="empirical_paper")
        result = arr.score_chapter("Introduction", "This is a test introduction." * 10)
        assert "overall" in result
        assert "level" in result
        assert "dimension_scores" in result

    def test_get_critical_rules(self):
        arr = AutoReviewRules(domain="empirical_paper")
        critical = arr.get_critical_rules()
        assert isinstance(critical, list)

    def test_score_empirical_paper_complete(self):
        arr = AutoReviewRules(domain="empirical_paper")
        chapters = {
            "Introduction": (
                "This paper studies carbon trading effect on innovation. "
                "Porter hypothesis suggests environmental regulation promotes innovation. "
                "We develop H1: Carbon trading promotes green innovation. "
            ) * 30,
            "Data": (
                "Data source: CSMAR database. Sample: A-share listed firms 2010-2023. "
                "Final sample: 5000 firms. Dependent variable: patent count. "
                "Independent variable: carbon trading participation. "
            ) * 20,
            "Methodology": (
                "Two-way fixed effects model with firm and year dummies. "
                "Standard errors clustered at firm level. "
                "Parallel trend assumption verified in Figure 2. "
            ) * 20,
            "Results": (
                "N=5000, R²=0.45. Coefficient: 0.23***. "
                "*** p<0.01, ** p<0.05, * p<0.1. "
            ) * 20,
        }
        score = arr.score_paper(chapters)
        assert 0.0 <= score.overall <= 100.0
        assert len(score.dimension_scores) > 0

    def test_empty_chapters(self):
        arr = AutoReviewRules(domain="empirical_paper")
        score = arr.score_paper({})
        assert score.overall >= 0.0
        assert score.level in ("A", "B", "C", "D", "F")

    def test_score_to_dict(self):
        arr = AutoReviewRules(domain="empirical_paper")
        chapters = {"Introduction": "Test content." * 50}
        score = arr.score_paper(chapters)
        d = score.to_dict()
        assert "overall" in d
        assert "level" in d
        assert "passed" in d
        assert isinstance(d["overall"], float)
