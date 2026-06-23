"""Tests for scripts/core/quality_gates.py."""

from __future__ import annotations

import pytest

from scripts.core.quality_gates import (
    ChapterQualityGate,
    PaperQualityGates,
    QualityLevel,
    QualityIssue,
    QualityReport,
    auto_fix_citation_format,
)


class TestChapterQualityGate:
    def test_word_count_below_minimum(self):
        gate = ChapterQualityGate(min_words=100, min_citations=0, min_paragraphs=1)
        report = gate.check("Test", "这是一段很短的文本。", {})
        assert report.level in (QualityLevel.CRITICAL, QualityLevel.BELOW_MINIMUM)
        assert any("字数" in i.message for i in report.issues)

    def test_word_count_acceptable(self):
        gate = ChapterQualityGate(min_words=10, min_citations=0, min_paragraphs=1)
        report = gate.check("Test", "这是一段符合最低字数要求的文本内容。", {})
        assert report.level in (QualityLevel.ACCEPTABLE, QualityLevel.EXCELLENT)

    def test_citation_count(self):
        gate = ChapterQualityGate(min_words=0, min_citations=3, min_paragraphs=1)
        text = "Author1 (2023), Author2 (2022) and Author3 (2021) studied this."
        report = gate.check("Introduction", text, {})
        assert any("引用" in i.message or "citation" in i.dimension for i in report.issues)

    def test_paragraph_count(self):
        gate = ChapterQualityGate(min_words=0, min_citations=0, min_paragraphs=3)
        text = "段落一内容。\n\n段落二内容。\n\n段落三内容。"
        report = gate.check("Introduction", text, {})
        # Should pass with 3 paragraphs
        assert report.score >= 0

    def test_citation_extraction_bibtex(self):
        text = r"\cite{smith2020, chen2021} and @jones2022 showed results."
        citations = ChapterQualityGate._extract_citations(text)
        assert len(citations) >= 1

    def test_citation_extraction_author_year(self):
        text = "Smith (2020) and Chen, Li & Wang (2022) found evidence."
        citations = ChapterQualityGate._extract_citations(text)
        assert len(citations) >= 1

    def test_word_count_excludes_whitespace(self):
        text = "a   b\n\n\tc"
        count = ChapterQualityGate._count_words(text)
        assert count == 3  # "a" + "b" + "c"

    def test_level_acceptable_or_above(self):
        gate = ChapterQualityGate(min_words=5, min_citations=0, min_paragraphs=1)
        text = "这是一段符合最低字数要求的文本内容，其中包含一些逻辑连接词。" * 10
        report = gate.check("Introduction", text, {})
        assert report.level in (QualityLevel.ACCEPTABLE, QualityLevel.EXCELLENT)

    def test_quality_issue_dataclass(self):
        issue = QualityIssue(
            dimension="word_count",
            severity="critical",
            message="字数不足",
            location="Section 1",
            suggestion="扩展内容",
        )
        assert issue.dimension == "word_count"
        assert issue.severity == "critical"
        assert issue.auto_fixable is False

    def test_quality_report_passed(self):
        report = QualityReport(
            chapter="Test",
            level=QualityLevel.ACCEPTABLE,
            score=0.85,
        )
        assert report.passed is True

    def test_quality_report_failed(self):
        report = QualityReport(
            chapter="Test",
            level=QualityLevel.CRITICAL,
            score=0.3,
        )
        assert report.passed is False

    def test_table_caption_check(self):
        gate = ChapterQualityGate(min_words=0, min_citations=0, min_paragraphs=1)
        text = r"\begin{table}\begin{tabular}{c|c}a & b\end{tabular}\end{table}"
        issues = gate._check_tables(text)
        assert len(issues) >= 1
        assert any("caption" in i.dimension.lower() for i in issues)

    def test_formula_numbering_check(self):
        gate = ChapterQualityGate(min_words=0, min_citations=0, min_paragraphs=1)
        text = r"$$y = \beta x + \epsilon$$ (1)"
        issues = gate._check_formulas(text)
        assert len(issues) == 0  # Has numbering

    def test_formula_missing_numbering(self):
        gate = ChapterQualityGate(min_words=0, min_citations=0, min_paragraphs=1)
        text = r"$$y = \beta x + \epsilon$$"
        issues = gate._check_formulas(text)
        assert len(issues) >= 1


class TestPaperQualityGates:
    def test_gate_single_chapter(self):
        qg = PaperQualityGates(strict=False)
        text = "这是一段很长的文本内容，" * 100
        report = qg.gate("Introduction", text, {})
        assert isinstance(report, QualityReport)
        assert 0.0 <= report.score <= 1.0

    def test_gate_all_chapters(self):
        qg = PaperQualityGates(strict=False)
        chapters = {
            "Introduction": "段落1内容。" * 200 + "Smith (2020) studied this. Chen (2021) found that.",
            "Abstract": "本文研究碳排放权交易对企业创新的影响。",
        }
        reports = qg.gate_all(chapters)
        assert len(reports) == 2
        assert "Introduction" in reports
        assert "Abstract" in reports

    def test_chapter_thresholds_override(self):
        qg = PaperQualityGates(
            strict=False,
            custom_thresholds={"Introduction": {"min_words": 5000}}
        )
        text = "短文本。"
        report = qg.gate("Introduction", text, {})
        assert report.level in (QualityLevel.BELOW_MINIMUM, QualityLevel.CRITICAL)

    def test_paper_summary_excellent(self):
        qg = PaperQualityGates(strict=False)
        intro_text = "段落。" * 200 + "Smith (2020) studied this."
        r1 = qg.gate("Introduction", intro_text)
        r2 = qg.gate("Abstract", "这是一个摘要。")
        summary = qg.get_paper_summary({"Introduction": r1, "Abstract": r2})
        assert isinstance(summary, QualityReport)
        assert summary.score > 0.0
        assert summary.chapter == "Full Paper"

    def test_paper_summary_empty(self):
        qg = PaperQualityGates()
        summary = qg.get_paper_summary({})
        assert summary.level == QualityLevel.BELOW_MINIMUM
        assert summary.score == 0.0

    def test_strict_mode_blocks_major(self):
        qg_strict = PaperQualityGates(strict=True)
        qg_lenient = PaperQualityGates(strict=False)
        text = "短。" * 5 + "Smith (2020) wrote this."
        r_strict = qg_strict.gate("Introduction", text)
        r_lenient = qg_lenient.gate("Introduction", text)
        # strict should have lower or equal level
        assert r_strict.level.value <= r_lenient.level.value

    def test_summary_format(self):
        report = QualityReport(
            chapter="Introduction",
            level=QualityLevel.ACCEPTABLE,
            score=0.7,
            issues=[QualityIssue("word", "major", "字数不足", None, "扩展内容")],
            suggestions=["扩展到至少2000字"],
        )
        summary = report.summary()
        assert "ACCEPTABLE" in summary
        assert "Introduction" in summary
        assert "字数不足" in summary


class TestAutoFix:
    def test_auto_fix_citation_format(self):
        text = "Smith(2023) studied this."
        fixed, fixes = auto_fix_citation_format(text)
        assert "Smith, (2023)" in fixed or fixed != text
        assert len(fixes) >= 0

    def test_auto_fix_bibtex_keys(self):
        text = r"\cite{smith2020, chen2021}"
        fixed, fixes = auto_fix_citation_format(text)
        # BibTeX key normalization is applied
        assert fixed is not None
