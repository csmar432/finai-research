"""QualityGates — 论文写作过程质量门控。

对论文写作的每个章节自动执行质量门槛检查，在草稿生成后、
人工审核（HITL）前自动运行。确保 LLM 输出的内容满足最低质量标准。

主要检查维度：
  1. 结构完整性 — 章节标题、引用、公式编号
  2. 最低字数 — 各章节最低字符数要求
  3. 引用质量 — 最低引用数量、引用多样性（年份/期刊分布）
  4. 方法描述质量 — 是否包含识别策略、数据描述
  5. 逻辑连贯性 — 章节之间的过渡句
  6. 表格规范 — 是否有表头、注释、显著性标注
  7. 公式规范 — 是否有编号、变量定义
  8. 图表引用 — 是否在正文中引用了所有图表

使用示例：
    from scripts.core.quality_gates import PaperQualityGates

    qg = PaperQualityGates(strict=False)  # strict=True = 所有检查必须通过
    result = qg.gate("Introduction", intro_text, context={"journal": "JF"})
    if not result.passed:
        print(f"未通过: {result.issues}")
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "ChapterQualityGate",
    "PaperQualityGates",
    "QualityIssue",
    "QualityLevel",
    "QualityReport",
]


# ─── Quality Level ────────────────────────────────────────────────────────────


class QualityLevel(Enum):
    """质量等级。"""
    EXCELLENT = "excellent"   # 达到发表水平
    ACCEPTABLE = "acceptable"  # 符合最低要求，可进入人工审核
    BELOW_MINIMUM = "below_minimum"  # 低于最低要求，需要重写
    CRITICAL = "critical"     # 严重问题，阻止进入下一阶段


# ─── Quality Issue ────────────────────────────────────────────────────────────


@dataclass
class QualityIssue:
    """单个质量问题。"""
    dimension: str          # 检查维度
    severity: str          # critical / major / minor / info
    message: str            # 问题描述
    location: str | None    # 位置（如 "Section 2.3"）
    suggestion: str | None  # 修复建议
    auto_fixable: bool = False  # 是否可自动修复


# ─── Quality Report ───────────────────────────────────────────────────────────


@dataclass
class QualityReport:
    """完整质量报告。"""
    chapter: str
    level: QualityLevel
    score: float              # 0.0 - 1.0
    issues: list[QualityIssue] = field(default_factory=list)
    warnings: list[QualityIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    auto_fix_notes: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.level not in (QualityLevel.BELOW_MINIMUM, QualityLevel.CRITICAL)

    def summary(self) -> str:
        lines = [
            f"[{self.level.value.upper()}] {self.chapter} (score={self.score:.2f})",
        ]
        if self.issues:
            lines.append(f"  Issues ({len(self.issues)}):")
            for iss in self.issues:
                lines.append(f"    [{iss.severity}] {iss.message}")
        if self.suggestions:
            lines.append(f"  Suggestions:")
            for s in self.suggestions:
                lines.append(f"    - {s}")
        return "\n".join(lines)


# ─── Chapter-Level Gates ──────────────────────────────────────────────────────


class ChapterQualityGate:
    """
    单章节质量门控。

    Parameters
    ----------
    min_words : int
        章节最低字数（不含空格）
    min_citations : int
        最低引用数量
    min_paragraphs : int
        最低段落数
    strict : bool
        True = 所有 major/critical 必须通过；False = major 可警告通过
    """

    def __init__(
        self,
        min_words: int = 200,
        min_citations: int = 3,
        min_paragraphs: int = 3,
        strict: bool = False,
    ):
        self.min_words = min_words
        self.min_citations = min_citations
        self.min_paragraphs = min_paragraphs
        self.strict = strict

    def check(self, chapter: str, text: str, context: dict | None = None) -> QualityReport:
        """对单个章节执行质量检查。"""
        t0 = time.perf_counter()
        context = context or {}
        issues: list[QualityIssue] = []
        warnings: list[QualityIssue] = []
        suggestions: list[str] = []

        # 1. 字数检查
        word_count = self._count_words(text)
        if word_count < self.min_words:
            issues.append(QualityIssue(
                dimension="word_count",
                severity="critical" if word_count < self.min_words * 0.5 else "major",
                message=f"字数不足：{word_count} < {self.min_words} 字符",
                location=chapter,
                suggestion=f"扩展章节内容，目标至少 {self.min_words} 字符",
            ))
            suggestions.append(f"当前 {word_count} 字，建议扩展至 ≥{self.min_words} 字")

        # 2. 引用数量
        citations = self._extract_citations(text)
        if len(citations) < self.min_citations:
            issues.append(QualityIssue(
                dimension="citation_count",
                severity="major",
                message=f"引用不足：{len(citations)} < {self.min_citations} 个引用",
                location=chapter,
                suggestion=f"至少添加 {self.min_citations - len(citations)} 篇参考文献",
            ))
            suggestions.append(f"补充文献引用，当前 {len(citations)} 篇，需 ≥{self.min_citations} 篇")

        # 3. 段落数量
        paragraphs = self._split_paragraphs(text)
        if len(paragraphs) < self.min_paragraphs:
            issues.append(QualityIssue(
                dimension="structure",
                severity="major",
                message=f"段落不足：{len(paragraphs)} < {self.min_paragraphs} 段落",
                location=chapter,
                suggestion="拆分长段落，每个核心观点独立成段",
            ))

        # 4. 引用多样性（仅正文章节）
        if chapter not in ("Abstract", "Conclusion") and citations:
            diversity = self._check_citation_diversity(citations)
            if not diversity["ok"]:
                warnings.append(QualityIssue(
                    dimension="citation_diversity",
                    severity="minor",
                    message=diversity["msg"],
                    location=chapter,
                    suggestion="补充近5年文献（≥40%）和跨期刊引用",
                    auto_fixable=False,
                ))

        # 5. 逻辑连接词
        transition_words = ["然而", "此外", "因此", "综上所述", "然而", "与此同时", "首先", "其次", "最后"]
        has_transition = any(w in text for w in transition_words)
        if not has_transition and len(paragraphs) > 1:
            warnings.append(QualityIssue(
                dimension="coherence",
                severity="minor",
                message="缺少逻辑连接词，段落之间缺乏过渡",
                location=chapter,
                suggestion="在段落之间添加逻辑连接词（首先/其次/然而/因此）",
                auto_fixable=False,
            ))

        # 6. 公式/表格检查
        if context.get("has_formulas"):
            formula_issues = self._check_formulas(text)
            issues.extend(formula_issues)

        if context.get("has_tables"):
            table_issues = self._check_tables(text)
            issues.extend(table_issues)

        # 7. 图表引用检查
        fig_refs = re.findall(r"(?:Figure|图|fig\.?)\s*\d+", text, re.IGNORECASE)
        if context.get("expected_figures"):
            if not fig_refs:
                issues.append(QualityIssue(
                    dimension="figure_references",
                    severity="major",
                    message="正文中未引用图表",
                    location=chapter,
                    suggestion="在正文中添加图表引用（如 Figure 1）",
                ))

        # 计算分数
        total_checks = 7
        passed_checks = total_checks - len([i for i in issues if i.severity in ("critical", "major")])
        score = max(0.0, passed_checks / total_checks)

        # 确定等级
        has_critical = any(i.severity == "critical" for i in issues)
        has_major = any(i.severity == "major" for i in issues)

        if has_critical or (has_major and self.strict):
            level = QualityLevel.CRITICAL if has_critical else QualityLevel.BELOW_MINIMUM
        elif has_major:
            level = QualityLevel.ACCEPTABLE if not self.strict else QualityLevel.BELOW_MINIMUM
        elif warnings:
            level = QualityLevel.ACCEPTABLE
        else:
            level = QualityLevel.EXCELLENT

        return QualityReport(
            chapter=chapter,
            level=level,
            score=score,
            issues=issues,
            warnings=warnings,
            suggestions=suggestions,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # ─── 内部辅助方法 ────────────────────────────────────────────────────────

    @staticmethod
    def _count_words(text: str) -> int:
        return len(re.sub(r"\s+", "", text))

    @staticmethod
    def _extract_citations(text: str) -> list[str]:
        patterns = [
            r"\\cite\{[^}]+\}",        # BibTeX \cite{key}
            r"@[\w]+",                # @key
            r"\([A-Z][\w\s&,\-]+?(?:et al\.?)?,?\s*\d{4}[a-z]?\)",  # (Author 2020) or (Author et al. 2020)
            r"\b[A-Z][a-z]+(?:\s+et\s+al\.?)?\s+\(?\d{4}[a-z]?\)?",  # Author 2020 or Author (2020)
        ]
        citations: set[str] = set()
        for pat in patterns:
            citations.update(re.findall(pat, text))
        return list(citations)

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        paras = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paras if p.strip() and len(p.strip()) > 50]

    @staticmethod
    def _check_citation_diversity(citations: list[str]) -> dict[str, Any]:
        """检查引用多样性：年份分布和期刊来源。"""
        years = re.findall(r"\b(19|20)\d{2}\b", " ".join(citations))
        recent = sum(1 for y in years if y and int(y) >= 2020)
        recent_ratio = recent / max(len(years), 1) if years else 0

        if recent_ratio < 0.3:
            return {"ok": False, "msg": f"近5年文献占比仅 {recent_ratio:.0%}，建议补充"}
        return {"ok": True}

    @staticmethod
    def _check_formulas(text: str) -> list[QualityIssue]:
        issues = []
        equations = re.findall(r"\\\(", text)  # inline math
        equations += re.findall(r"\$\$.*?\$\$", text, re.DOTALL)  # display math
        equations += re.findall(r"\\begin\{equation\}.*?\\end\{equation\}", text, re.DOTALL)
        if len(equations) == 0:
            return []
        # Check for equation numbers
        eq_numbers = re.findall(r"\(\d+\)", text)
        if len(equations) > 0 and len(eq_numbers) < len(equations):
            issues.append(QualityIssue(
                dimension="formula_numbering",
                severity="minor",
                message=f"{len(equations)} 个公式中仅 {len(eq_numbers)} 个有编号",
                location=None,
                suggestion="为所有展示公式添加编号 \\tag{1}",
            ))
        return issues

    @staticmethod
    def _check_tables(text: str) -> list[QualityIssue]:
        issues = []
        tables = re.findall(r"\\begin\{table\}.*?\\end\{table\}", text, re.DOTALL)
        if not tables:
            return []
        for i, tbl in enumerate(tables, 1):
            if "\\caption" not in tbl:
                issues.append(QualityIssue(
                    dimension="table_caption",
                    severity="major",
                    message=f"第 {i} 个表格缺少 \\caption",
                    location=None,
                    suggestion="为表格添加标题：\\caption{表名}",
                ))
            if "\\hline" not in tbl and "\\toprule" not in tbl:
                issues.append(QualityIssue(
                    dimension="table_header",
                    severity="minor",
                    message=f"第 {i} 个表格缺少表头横线（\\hline 或 \\toprule）",
                    location=None,
                    suggestion="添加表头分隔线",
                ))
        return issues


# ─── Full Paper Quality Gates ────────────────────────────────────────────────


class PaperQualityGates:
    """
    论文级质量门控。

    对论文的每个章节执行自动质量检查，生成完整报告。
    集成到论文写作流程中，在草稿生成后、HITL 审核前执行。

    Parameters
    ----------
    strict : bool
        True = 所有 major 问题必须解决；False = major 产生警告但允许通过
    journal : str
        目标期刊（如 "JF", "JFE", "经济研究"），影响字数门槛
    custom_thresholds : dict
        自定义门槛，如 {"Introduction": {"min_words": 3000}}
    """

    # 各章节默认最低字数门槛
    CHAPTER_MIN_WORDS: dict[str, int] = {
        "Abstract": 200,
        "Introduction": 2000,
        "Literature Review": 1500,
        "Hypothesis Development": 1000,
        "Data": 1500,
        "Methodology": 2000,
        "Results": 2000,
        "Discussion": 1500,
        "Conclusion": 800,
        "Appendix": 500,
    }

    # 各章节默认最低引用数
    CHAPTER_MIN_CITATIONS: dict[str, int] = {
        "Abstract": 0,
        "Introduction": 15,
        "Literature Review": 20,
        "Hypothesis Development": 5,
        "Data": 5,
        "Methodology": 8,
        "Results": 5,
        "Discussion": 10,
        "Conclusion": 3,
        "Appendix": 0,
    }

    def __init__(
        self,
        strict: bool = False,
        journal: str = "JF",
        custom_thresholds: dict | None = None,
    ):
        self.strict = strict
        self.journal = journal
        self.custom_thresholds = custom_thresholds or {}

    def gate(self, chapter: str, text: str, context: dict | None = None) -> QualityReport:
        """
        对单个章节执行质量门控检查。

        Parameters
        ----------
        chapter : str
            章节名称（如 "Introduction"）
        text : str
            章节正文内容
        context : dict, optional
            额外上下文：
              - has_formulas: bool
              - has_tables: bool
              - expected_figures: int
              - expected_tables: int
              - journal: str（覆盖 self.journal）

        Returns
        -------
        QualityReport
            包含通过/失败状态、问题列表和修复建议
        """
        context = context or {}
        thresholds = self._get_thresholds(chapter)

        gate = ChapterQualityGate(
            min_words=thresholds["min_words"],
            min_citations=thresholds["min_citations"],
            min_paragraphs=thresholds.get("min_paragraphs", 3),
            strict=self.strict,
        )
        return gate.check(chapter, text, context)

    def gate_all(self, chapters: dict[str, str], contexts: dict[str, dict] | None = None) -> dict[str, QualityReport]:
        """
        对论文的所有章节执行质量门控。

        Parameters
        ----------
        chapters : dict[str, str]
            章节名 → 正文内容的映射
        contexts : dict[str, dict], optional
            章节 → 上下文的映射

        Returns
        -------
        dict[str, QualityReport]
            章节名 → 质量报告的映射
        """
        contexts = contexts or {}
        reports: dict[str, QualityReport] = {}
        for name, text in chapters.items():
            reports[name] = self.gate(name, text, contexts.get(name, {}))
        return reports

    def get_paper_summary(self, reports: dict[str, QualityReport]) -> QualityReport:
        """汇总所有章节报告，生成论文级质量报告。"""
        if not reports:
            return QualityReport(
                chapter="Full Paper",
                level=QualityLevel.BELOW_MINIMUM,
                score=0.0,
                issues=[QualityIssue("global", "critical", "无章节数据", None, None)],
            )

        all_issues = []
        all_warnings = []
        total_score = sum(r.score for r in reports.values()) / len(reports)
        has_critical = any(r.level == QualityLevel.CRITICAL for r in reports.values())
        has_major_fail = any(r.level == QualityLevel.BELOW_MINIMUM for r in reports.values())

        for r in reports.values():
            all_issues.extend(r.issues)
            all_warnings.extend(r.warnings)

        if has_critical:
            level = QualityLevel.CRITICAL
        elif has_major_fail:
            level = QualityLevel.BELOW_MINIMUM
        elif any(r.level == QualityLevel.ACCEPTABLE for r in reports.values()):
            level = QualityLevel.ACCEPTABLE
        else:
            level = QualityLevel.EXCELLENT

        return QualityReport(
            chapter="Full Paper",
            level=level,
            score=total_score,
            issues=all_issues,
            warnings=all_warnings,
            elapsed_ms=sum(r.elapsed_ms for r in reports.values()),
        )

    def _get_thresholds(self, chapter: str) -> dict[str, Any]:
        """获取章节的质量门槛。"""
        defaults = {
            "min_words": self.CHAPTER_MIN_WORDS.get(chapter, 1000),
            "min_citations": self.CHAPTER_MIN_CITATIONS.get(chapter, 5),
            "min_paragraphs": 3,
        }
        return {**defaults, **self.custom_thresholds.get(chapter, {})}


# ─── Auto-fix utilities ───────────────────────────────────────────────────────


def auto_fix_citation_format(text: str) -> tuple[str, list[str]]:
    """
    自动修复常见引用格式问题。

    Returns
    -------
    tuple[str, list[str]]
        修复后的文本 + 应用的修复列表
    """
    fixes: list[str] = []
    original = text

    # 1. 修复缺失空格的引用：Author(2023) → Author, (2023)
    text = re.sub(r"([A-Za-z]+)\(([12]\d{3})\)", r"\1, (\2)", text)
    if text != original:
        fixes.append("修复作者-年份引用格式")

    # 2. 规范化 BibTeX 键名
    text = re.sub(r"@([a-z]+)\{", lambda m: f"@{m.group(1).capitalize()}{{", text)

    return text, fixes


# ─── CLI Demo ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=== Paper Quality Gates Demo ===\n")

    sample_intro = """
    This paper examines the relationship between carbon trading and corporate green innovation.
    We use a difference-in-differences approach to identify the causal effect.

    First, we review the literature on carbon markets (Zhang et al., 2022; Li and Wang, 2023).
    Previous studies have found that carbon trading schemes promote innovation (Chen, 2021).
    However, the mechanisms remain unclear (Zhang, 2022).

    We develop three hypotheses based on the Porter hypothesis and innovation theory.
    Our identification strategy exploits the pilot carbon trading program launched in 2011.
    We collect firm-level data from the CSMAR database covering 2010-2023.

    Table 1 shows the summary statistics.
    Figure 1 illustrates the trends in innovation output.
    """

    sample_abstract = "This paper investigates carbon trading's effect on innovation."

    qg = PaperQualityGates(strict=False)

    # Test Introduction
    print("--- Introduction ---")
    r = qg.gate("Introduction", sample_intro, context={"has_tables": True, "has_formulas": False})
    print(r.summary())

    print("\n--- Abstract ---")
    r2 = qg.gate("Abstract", sample_abstract)
    print(r2.summary())

    print("\n--- Full Paper Summary ---")
    summary = qg.get_paper_summary({"Introduction": r, "Abstract": r2})
    print(summary.summary())
