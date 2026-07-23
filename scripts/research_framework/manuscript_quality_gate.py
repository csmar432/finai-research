"""manuscript_quality_gate.py — 论文草稿质量静态门禁

对一份 Markdown 论文草稿做**静态**度量，标记以下问题：
  - 全文字数不达标（中文 CSSCI 实证论文通常 8,000–15,000 汉字）
  - 单个章节过薄（如文献综述、机制、讨论章节字数偏低）
  - 缺少「AI 生成 / 需研究者审阅」免责声明
  - 章节长度严重失衡

【设计原则】
- 阈值是**启发式指导**（针对中文 CSSCI 实证论文），全部可配置。
- 本门禁只负责「标记」，不改写论文；是否放行由人决定。
- 纯静态：不联网、不调用 LLM。

【用法】
    from scripts.research_framework.manuscript_quality_gate import check_manuscript
    report = check_manuscript(md_text, language="auto", min_total_zh=8000)
    if not report.passed:
        print(report.summary_message)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ── ANSI Colors ────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


# ── 文本度量 helpers ────────────────────────────────────────────────────────────

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def count_cjk_chars(text: str) -> int:
    """统计中文汉字数（仅 CJK 统一表意文字 \u4e00-\u9fff）。"""
    return len(_CJK_RE.findall(text))


def count_words(text: str) -> int:
    """统计以空白分隔的词数（英文）。"""
    return len(text.split())


def detect_language(text: str) -> str:
    """粗略判定语言：非空白字符中 CJK 占比 > 30% 视为中文，否则英文。"""
    non_space = re.sub(r"\s", "", text)
    if not non_space:
        return "en"
    cjk = count_cjk_chars(text)
    return "zh" if cjk / len(non_space) > 0.30 else "en"


# ── 数据结构 ────────────────────────────────────────────────────────────────────


@dataclass
class SectionStat:
    title: str
    char_count: int
    is_thin: bool
    min_expected: int


@dataclass
class QualityIssue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str


@dataclass
class QualityReport:
    language: str
    total_chars: int
    n_sections: int
    section_stats: list[SectionStat]
    issues: list[QualityIssue]
    has_disclaimer: bool
    passed: bool
    summary_message: str

    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ── 默认章节阈值 ─────────────────────────────────────────────────────────────────
# 章节标题包含以下关键词时，其正文汉字数应达到对应下限。
_DEFAULT_SECTION_MIN: dict[str, int] = {
    "引言": 800,
    "文献": 1000,
    "综述": 1000,
    "研究设计": 800,
    "设计": 800,
    "实证": 1000,
    "结果": 1000,
    "机制": 600,
    "讨论": 800,
    "结论": 500,
}

# 摘要类章节不受 section_min 约束（本身应短）。
_ABSTRACT_KEYWORDS = ("摘要", "abstract", "关键词", "keywords")

_DISCLAIMER_MARKERS = (
    "AI生成",
    "AI 生成",
    "人工智能生成",
    "本草稿",
    "未经",
    "逐字审阅",
    "AI-generated",
    "must be reviewed",
    "需研究者",
    "需经研究者",
)


class ManuscriptQualityGate:
    """论文草稿质量静态门禁。"""

    def __init__(
        self,
        md_text: str,
        *,
        language: str = "auto",
        min_total_zh: int = 8000,
        min_total_en: int = 4000,
        section_min: Optional[dict[str, int]] = None,
        require_disclaimer: bool = True,
    ) -> None:
        self.md_text = md_text or ""
        self.language = language
        self.min_total_zh = min_total_zh
        self.min_total_en = min_total_en
        self.section_min = dict(_DEFAULT_SECTION_MIN if section_min is None else section_min)
        self.require_disclaimer = require_disclaimer
        self._report: Optional[QualityReport] = None

    # ── 内部：分节 ────────────────────────────────────────────────────────────
    def _split_sections(self) -> list[tuple[str, str]]:
        """按 markdown 标题（>= 2 级，即 ## 起）分节。

        单个 `#` 顶级标题视为论文题目，不算章节。
        返回 [(section_title, section_body_text), ...]。
        """
        lines = self.md_text.splitlines()
        sections: list[tuple[str, list[str]]] = []
        current_title: Optional[str] = None
        current_body: list[str] = []

        for line in lines:
            m = re.match(r"^(#{2,6})\s+(.*)$", line)
            if m:
                # flush previous
                if current_title is not None:
                    sections.append((current_title, current_body))
                current_title = m.group(2).strip()
                current_body = []
            else:
                if current_title is not None:
                    current_body.append(line)
                # lines before first ## (incl. the # title) are ignored for section stats
        if current_title is not None:
            sections.append((current_title, current_body))

        return [(t, "\n".join(b)) for t, b in sections]

    @staticmethod
    def _strip_table_lines(text: str) -> str:
        """移除 markdown 表格行（以 | 开头），只保留散文用于字数统计。"""
        kept = [ln for ln in text.splitlines() if not ln.strip().startswith("|")]
        return "\n".join(kept)

    def _section_threshold(self, title: str) -> int:
        """返回标题匹配到的最大章节字数下限；无匹配返回 0。"""
        thresholds = [v for kw, v in self.section_min.items() if kw in title]
        return max(thresholds) if thresholds else 0

    @staticmethod
    def _is_abstract(title: str) -> bool:
        low = title.lower()
        return any(kw in title or kw in low for kw in _ABSTRACT_KEYWORDS)

    # ── 主分析 ────────────────────────────────────────────────────────────────
    def analyze(self) -> QualityReport:
        lang = self.language
        if lang == "auto":
            lang = detect_language(self.md_text)

        # 全文散文（排除表格行）字数
        prose = self._strip_table_lines(self.md_text)
        if lang == "zh":
            total = count_cjk_chars(prose)
        else:
            total = count_words(prose)
        min_total = self.min_total_zh if lang == "zh" else self.min_total_en

        issues: list[QualityIssue] = []

        if total < min_total:
            shortfall = (1 - total / min_total) * 100 if min_total else 0
            unit = "汉字" if lang == "zh" else "词"
            issues.append(
                QualityIssue(
                    severity="error",
                    code="TOO_SHORT",
                    message=(
                        f"全文仅 {total} {unit}，低于建议下限 {min_total} {unit}"
                        f"（缺口 {shortfall:.0f}%）"
                    ),
                )
            )

        # 章节统计
        section_stats: list[SectionStat] = []
        sections = self._split_sections()
        for title, body in sections:
            body_prose = self._strip_table_lines(body)
            cc = count_cjk_chars(body_prose) if lang == "zh" else count_words(body_prose)
            threshold = 0
            is_thin = False
            if not self._is_abstract(title):
                threshold = self._section_threshold(title)
                if threshold and cc < threshold:
                    is_thin = True
                    issues.append(
                        QualityIssue(
                            severity="warning",
                            code="THIN_SECTION",
                            message=f"章节「{title}」仅 {cc} 字，低于建议下限 {threshold} 字",
                        )
                    )
            section_stats.append(
                SectionStat(
                    title=title, char_count=cc, is_thin=is_thin, min_expected=threshold
                )
            )

        # 免责声明
        has_disclaimer = any(m in self.md_text for m in _DISCLAIMER_MARKERS)
        if self.require_disclaimer and not has_disclaimer:
            issues.append(
                QualityIssue(
                    severity="warning",
                    code="NO_DISCLAIMER",
                    message="未发现「AI 生成 / 需研究者逐字审阅」免责声明",
                )
            )

        # 章节失衡（非摘要章节）
        non_abstract = [s for s in section_stats if not self._is_abstract(s.title)]
        if len(non_abstract) >= 2:
            counts = [s.char_count for s in non_abstract]
            longest, shortest = max(counts), min(counts)
            if shortest > 0 and longest > 5 * shortest:
                issues.append(
                    QualityIssue(
                        severity="info",
                        code="SECTION_IMBALANCE",
                        message=(
                            f"章节长度失衡：最长 {longest} 字 vs 最短 {shortest} 字"
                            f"（>5×）"
                        ),
                    )
                )

        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        passed = error_count == 0

        verdict = "通过" if passed else "未通过"
        summary = (
            f"[{verdict}] 语言={lang} 全文={total} "
            f"章节={len(section_stats)} "
            f"错误={error_count} 警告={warning_count} "
            f"免责声明={'有' if has_disclaimer else '无'}"
        )

        self._report = QualityReport(
            language=lang,
            total_chars=total,
            n_sections=len(section_stats),
            section_stats=section_stats,
            issues=issues,
            has_disclaimer=has_disclaimer,
            passed=passed,
            summary_message=summary,
        )
        return self._report

    # ── 报告输出 ──────────────────────────────────────────────────────────────
    def print_report(self, report: Optional[QualityReport] = None) -> None:
        r = report or self._report or self.analyze()
        unit = "汉字" if r.language == "zh" else "词"
        min_total = self.min_total_zh if r.language == "zh" else self.min_total_en

        print()
        print(c("═" * 64, CYAN))
        print(c("  论文草稿质量门禁报告", CYAN))
        print(c("═" * 64, CYAN))
        print()

        head_color = GREEN if r.total_chars >= min_total else RED
        print(f"  语言: {r.language}")
        print(f"  全文字数: {c(str(r.total_chars), head_color)} {unit}（建议下限 {min_total}）")
        print(f"  章节数: {r.n_sections}")
        print(f"  免责声明: {c('有', GREEN) if r.has_disclaimer else c('无', YELLOW)}")
        print()

        thin = [s for s in r.section_stats if s.is_thin]
        if thin:
            print(c("  ⚠ 过薄章节:", YELLOW))
            for s in thin:
                print(f"     • {s.title}: {s.char_count} 字（下限 {s.min_expected}）")
            print()

        if r.issues:
            print(c("  问题清单:", BOLD))
            for i in r.issues:
                icon = {"error": c("🔴", RED), "warning": c("🟡", YELLOW), "info": c("⚪", DIM)}.get(
                    i.severity, "•"
                )
                print(f"    {icon} [{i.code}] {i.message}")
            print()

        verdict = c("✅ 通过", GREEN) if r.passed else c("❌ 未通过", RED)
        print(f"  结论: {verdict}")
        print(c("─" * 64, CYAN))
        print()

    def render_report_markdown(self, report: Optional[QualityReport] = None) -> str:
        r = report or self._report or self.analyze()
        unit = "汉字" if r.language == "zh" else "词"
        min_total = self.min_total_zh if r.language == "zh" else self.min_total_en

        lines = [
            "# 论文草稿质量门禁报告",
            "",
            f"- 语言: {r.language}",
            f"- 全文字数: {r.total_chars} {unit}（建议下限 {min_total}）",
            f"- 章节数: {r.n_sections}",
            f"- 免责声明: {'有' if r.has_disclaimer else '无'}",
            f"- 错误: {r.error_count()} | 警告: {r.warning_count()}",
            "",
            "## 章节字数明细",
            "",
            "| 章节 | 字数 | 建议下限 | 状态 |",
            "|---|---:|---:|---|",
        ]
        for s in r.section_stats:
            status = "⚠ 偏薄" if s.is_thin else "✅"
            lines.append(f"| {s.title} | {s.char_count} | {s.min_expected or '—'} | {status} |")

        lines += ["", "## 问题清单", ""]
        if r.issues:
            for i in r.issues:
                lines.append(f"- **[{i.severity}] {i.code}**: {i.message}")
        else:
            lines.append("- （无）")

        lines += ["", f"## 结论：{'通过' if r.passed else '未通过'}", ""]
        return "\n".join(lines)


# ── 便捷函数 ────────────────────────────────────────────────────────────────────


def check_manuscript(
    md_text: str,
    language: str = "auto",
    min_total_zh: int = 8000,
    min_total_en: int = 4000,
    require_disclaimer: bool = True,
) -> QualityReport:
    """一行调用：度量论文草稿质量并返回报告。"""
    gate = ManuscriptQualityGate(
        md_text,
        language=language,
        min_total_zh=min_total_zh,
        min_total_en=min_total_en,
        require_disclaimer=require_disclaimer,
    )
    return gate.analyze()
