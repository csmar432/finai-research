#!/usr/bin/env python3
"""
paper_language_checker.py

论文文字质量自动化检测工具。

检测维度：
1. AI 味检测 — 扫描典型 AI 生成句式
2. 底气检测 — 验证结论段是否包含具体数字/机制
3. 表格引导句检测 — 验证每表前后是否有引导句
4. 图表注释检测 — 验证每图注释是否包含解读
5. 段落数检测 — 验证每章最小段落数
6. 缩略语检测 — 验证首次出现是否写全称

用法：
    python scripts/paper_language_checker.py paper.tex
    python scripts/paper_language_checker.py draft_v1/ --report
    python scripts/paper_language_checker.py --batch output/fin-manuscript/
"""

import re
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# AI 味关键词列表（零容忍）
# =============================================================================

AI_PATTERNS_ZH = [
    (r"值得注意的是", "过渡套话"),
    (r"综上所述", "过渡套话"),
    (r"从某种意义上", "模糊程度"),
    (r"客观来说", "过渡套话"),
    (r"客观地讲", "过渡套话"),
    (r"在一定程度上", "模糊程度"),
    (r"某种程度上", "模糊程度"),
    (r"相对而言", "模糊程度"),
    (r"近年来", "空洞开头"),
    (r"随着时代发展", "空洞开头"),
    (r"在当今社会", "空洞开头"),
    (r"可能存在", "无力结论"),
    (r"有待进一步研究", "无力结论"),
    (r"有待未来研究", "无力结论"),
    (r"首先我们需要", "废话开头"),
    (r"首先必须", "废话开头"),
    (r"非常重要的", "堆砌形容词"),
    (r"具有重大意义的", "堆砌形容词"),
    (r"已经被证实", "被动过度"),
    (r"已经被证明", "被动过度"),
    (r"可以被认为", "被动过度"),
    (r"可以被视为", "被动过度"),
    (r"XX研究表明", "空洞引用"),
    (r"研究表明", "空洞引用"),  # 仅当无具体发现时
    (r"已有学者指出", "空洞引用"),
    (r"值得深入研究", "空洞结论"),
    (r"值得进一步探讨", "空洞结论"),
    (r"具有重要的理论和实践意义", "空洞套话"),
    (r"从总体上看", "模糊程度"),
    (r"整体而言", "模糊程度"),
    (r"不言而喻", "空洞套话"),
    (r"毋庸置疑", "空洞套话"),
    (r"不得不承认", "空洞套话"),
]

AI_PATTERNS_EN = [
    (r"it is worth noting that", "过渡套话"),
    (r"it should be noted that", "过渡套话"),
    (r"in conclusion", "过渡套话"),
    (r"to some extent", "模糊程度"),
    (r"to a certain extent", "模糊程度"),
    (r"relatively speaking", "模糊程度"),
    (r"recently", "空洞开头"),
    (r"in recent years", "空洞开头"),
    (r"in today's society", "空洞开头"),
    (r"with the development of society", "空洞开头"),
    (r"it is important to note", "废话开头"),
    (r"it is important to emphasize", "废话开头"),
    (r"it should be emphasized that", "废话开头"),
    (r"has been proven", "被动过度"),
    (r"has been shown", "被动过度"),
    (r"can be considered as", "被动过度"),
    (r"is widely believed that", "空洞套话"),
    (r"research shows that", "空洞引用"),
    (r"studies have shown that", "空洞引用"),
    (r"much evidence suggests", "空洞引用"),
    (r"a growing body of literature", "空洞开头"),
    (r"the literature suggests that", "空洞引用"),
]

# =============================================================================
# 底气检测正则（结论段必须满足至少一项）
# =============================================================================

CONFIDENCE_PATTERNS = [
    (r"β\s*=\s*[\-0-9.]+", "具体数字：β系数"),
    (r"95%\s*CI\s*\[[\-0-9.,\s]+\]", "具体数字：置信区间"),
    (r"p\s*=\s*0\.[0-9]+", "具体数字：p值"),
    (r"p\s*<\s*0\.0[0-9]", "具体数字：p显著性"),
    (r"占样本均值的\s*[0-9.]+%", "经济规模：占均值"),
    (r"占.*标准差的\s*[0-9.]+%", "经济规模：占标准差"),
    (r"相当于\s*[0-9,]+亿", "经济规模：亿元"),
    (r"相当于\s*[0-9,]+万", "经济规模：万吨/万人"),
    (r"通过.*渠道.*而非.*渠道", "机制描述：双渠道对比"),
    (r"通过.*机制.*而非.*机制", "机制描述：双机制对比"),
    (r"是.*的\s*[0-9.]+倍", "对比发现：倍数关系"),
    (r"远大于.*远小于", "对比发现：大小对比"),
    (r"与.*预测一致", "理论对应：一致"),
    (r"与.*预测相反", "理论对应：相反"),
    (r"Porter\s*Hypothesis", "理论对应：Porter假说"),
    (r"环境规制.*创新.*促进", "机制描述：环境规制创新机制"),
]

# =============================================================================
# 章节结构检测
# =============================================================================

CHAPTER_PATTERNS = {
    "abstract": re.compile(r"\\begin\{abstract\}|摘\s*要|\\cnabstract", re.IGNORECASE),
    "introduction": re.compile(r"\\section\{.*引.*\}|\\section\{Introduction", re.IGNORECASE),
    "literature": re.compile(r"\\section\{.*文献.*\}|\\section\{Literature", re.IGNORECASE),
    "hypothesis": re.compile(r"\\section\{.*假.*\}|\\section\{Hypothes", re.IGNORECASE),
    "methodology": re.compile(r"\\section\{.*研究设计.*\}|\\section\{.*数据.*\}|\\section\{Data", re.IGNORECASE),
    "results": re.compile(r"\\section\{.*实证.*\}|\\section\{Results", re.IGNORECASE),
    "robustness": re.compile(r"\\section\{.*稳健.*\}|\\section\{.*Robustness", re.IGNORECASE),
    "conclusion": re.compile(r"\\section\{.*结论.*\}|\\section\{Conclusion", re.IGNORECASE),
}

MIN_PARAGRAPHS = {
    "abstract": 1,
    "introduction": 5,
    "literature": 4,
    "methodology": 4,
    "results": 6,
    "robustness": 4,
    "conclusion": 4,
}

# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class LanguageCheckResult:
    """单文件检测结果"""
    file_path: str
    ai_issues: list = field(default_factory=list)
    confidence_issues: list = field(default_factory=list)
    table_intro_issues: list = field(default_factory=list)
    figure_caption_issues: list = field(default_factory=list)
    paragraph_issues: list = field(default_factory=list)
    abbreviation_issues: list = field(default_factory=list)
    passed: bool = True
    score: float = 100.0

    def add_issue(self, category: str, message: str, line: Optional[int] = None):
        self.passed = False
        issue = {"category": category, "message": message}
        if line:
            issue["line"] = line
        if category == "AI味":
            self.ai_issues.append(issue)
            self.score -= 1.5
        elif category == "底气":
            self.confidence_issues.append(issue)
            self.score -= 2.0
        elif category == "表格引导句":
            self.table_intro_issues.append(issue)
            self.score -= 1.0
        elif category == "图表注释":
            self.figure_caption_issues.append(issue)
            self.score -= 1.0
        elif category == "段落数":
            self.paragraph_issues.append(issue)
            self.score -= 2.0
        elif category == "缩略语":
            self.abbreviation_issues.append(issue)
            self.score -= 0.5
        self.score = max(0.0, self.score)


# =============================================================================
# 检测器类
# =============================================================================

class PaperLanguageChecker:
    """论文语言质量检测器"""

    def __init__(self, content: str, file_path: str):
        self.content = content
        self.file_path = file_path
        self.lines = content.split("\n")
        self.result = LanguageCheckResult(file_path)

    def check_ai_patterns(self) -> None:
        """检测 AI 味关键词"""
        for line_no, line in enumerate(self.lines, 1):
            for pattern, label in AI_PATTERNS_ZH + AI_PATTERNS_EN:
                if re.search(pattern, line, re.IGNORECASE):
                    self.result.add_issue(
                        "AI味",
                        f"[{label}] 关键词 '{pattern}' 出现在: {line.strip()[:80]}",
                        line_no,
                    )

    def check_confidence_in_conclusion(self) -> None:
        """检测结论段底气"""
        conclusion_section = self._extract_section("conclusion")
        if not conclusion_section:
            return

        # 检查是否包含底气要素
        has_confidence = any(
            re.search(p, conclusion_section, re.IGNORECASE)
            for p, _ in CONFIDENCE_PATTERNS
        )

        if not has_confidence:
            self.result.add_issue(
                "底气",
                "结论段未发现具体数字、经济规模、机制描述或对比发现，底气不足"
            )

    def check_table_intro_sentences(self) -> None:
        """检测表格引导句"""
        tables = list(re.finditer(r"\\begin\{table\}.*?\\end\{table\}", self.content, re.DOTALL))
        for i, table_match in enumerate(tables):
            table_pos = table_match.start()
            table_content = table_match.group(0)
            table_label = re.search(r"\\label\{([^}]+)\}", table_content)
            label_str = table_label.group(1) if table_label else f"table_{i+1}"

            # 获取表格前的文字（最多前500字符）
            before_text = self.content[max(0, table_pos - 500):table_pos]

            # 统计表格前的句子数（按句号/分号/感叹号/问号分隔）
            sentences = re.split(r"[。；！？\n]", before_text)
            meaningful_sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

            # 过滤掉注释和命令
            meaningful_sentences = [
                s for s in meaningful_sentences
                if not s.startswith("%") and not s.startswith("\\")
            ]

            if len(meaningful_sentences) < 2:
                self.result.add_issue(
                    "表格引导句",
                    f"表格 \\ref{{{label_str}}} 前的引导句不足（发现 {len(meaningful_sentences)} 句，要求 ≥2 句）"
                )

            # 检查表格后是否有解读
            after_text = self.content[table_match.end():table_match.end() + 300]
            after_sentences = re.split(r"[。；！？\n]", after_text)
            after_meaningful = [s.strip() for s in after_sentences if len(s.strip()) > 10]

            if len(after_meaningful) < 1:
                self.result.add_issue(
                    "表格引导句",
                    f"表格 \\ref{{{label_str}}} 后缺少解读句（要求 ≥1 句）"
                )

    def check_figure_captions(self) -> None:
        """检测图表注释"""
        figures = list(re.finditer(r"\\begin\{figure\}.*?\\end\{figure\}", self.content, re.DOTALL))
        for i, fig_match in enumerate(figures):
            fig_content = fig_match.group(0)
            fig_label = re.search(r"\\label\{([^}]+)\}", fig_content)
            label_str = fig_label.group(1) if fig_label else f"figure_{i+1}"

            caption_match = re.search(r"\\caption\{([^}]+)\}", fig_content)
            if not caption_match:
                self.result.add_issue(
                    "图表注释",
                    f"图 \\ref{{{label_str}}} 缺少 \\caption 命令"
                )
                continue

            caption_text = caption_match.group(1)

            # 检查 caption 是否包含解读（而非仅描述"展示什么"）
            has_interpretation = any(word in caption_text for word in [
                "表明", "显示", "说明", "揭示", "呈现", "证实",
                "显著", "上升", "下降", "高于", "低于", "大于", "小于",
                "increases", "decreases", "significant", "higher", "lower",
                "suggests", "indicates", "reveals", "shows that"
            ])

            if not has_interpretation:
                self.result.add_issue(
                    "图表注释",
                    f"图 \\ref{{{label_str}}} 的 caption 仅描述'展示什么'，缺少'说明什么'的解读"
                )

    def check_paragraph_count(self) -> None:
        """检测每章最小段落数"""
        for chapter_name, pattern in CHAPTER_PATTERNS.items():
            section_text = self._extract_section(chapter_name)
            if not section_text:
                continue

            # 统计段落数（按空行或 \n\n 分隔）
            paragraphs = re.split(r"\n\s*\n|\\\\", section_text)
            meaningful_paragraphs = [
                p.strip() for p in paragraphs
                if len(p.strip()) > 50 and not p.strip().startswith("%")
            ]

            min_count = MIN_PARAGRAPHS.get(chapter_name, 3)
            if len(meaningful_paragraphs) < min_count:
                self.result.add_issue(
                    "段落数",
                    f"章节 '{chapter_name}' 有 {len(meaningful_paragraphs)} 个段落（要求 ≥{min_count}）"
                )

    def check_abbreviations(self) -> None:
        """检测缩略语首次出现是否写全称"""
        # 常见缩略语及其全称
        KNOWN_ABBREV = {
            "TR": "Transition Readiness",
            "ESP": "Energy System Performance",
            "ETI": "Energy Transition Index",
            "DID": "Difference-in-Differences",
            "IV": "Instrumental Variable",
            "RDD": "Regression Discontinuity Design",
            "PSM": "Propensity Score Matching",
            "GMM": "Generalized Method of Moments",
            "LCCP": "Low-Carbon City Pilot",
            "GDP": "国内生产总值|Gross Domestic Product",
            "ESG": "Environmental, Social, and Governance",
            "API": "Application Programming Interface",
            "NLP": "Natural Language Processing",
        }

        for abbrev, full_name in KNOWN_ABBREV.items():
            # 查找首次出现位置
            first_occurrence = re.search(rf"\b{abbrev}\b", self.content)
            if not first_occurrence:
                continue

            # 检查首次出现是否包含全称（括号内或前面）
            context_start = max(0, first_occurrence.start() - 100)
            context_end = min(len(self.content), first_occurrence.end() + 50)
            context = self.content[context_start:context_end]

            # 检查是否有全称模式：缩写（全称）或 缩写 - 全称
            has_full_name = bool(
                re.search(rf"{abbrev}\s*[\(（].*?{full_name}|{full_name}.*?{abbrev}", context, re.IGNORECASE)
            )

            if not has_full_name:
                self.result.add_issue(
                    "缩略语",
                    f"缩写 '{abbrev}' 首次出现时未写全称（建议：'{abbrev}（{full_name.split('|')[0]}）'）"
                )

    def _extract_section(self, section_name: str) -> Optional[str]:
        """提取指定章节的内容"""
        section_patterns = {
            "abstract": r"(?:\\begin\{abstract\}.*?\\end\{abstract\}|\{摘\s*要\}.*?(?=\\section|\\subsection|\\end\{document\}))",
            "introduction": r"(\\section\{[^}]*引[言导].*?\})(.*?)(?=\\section\{|$)",
            "literature": r"(\\section\{[^}]*文献.*?\})(.*?)(?=\\section\{|$)",
            "hypothesis": r"(\\section\{[^}]*假[说设].*?\})(.*?)(?=\\section\{|$)",
            "methodology": r"(\\section\{[^}]*(?:研究设计|数据|方法).*?\})(.*?)(?=\\section\{|$)",
            "results": r"(\\section\{[^}]*(?:实证|结果).*?\})(.*?)(?=\\section\{|$)",
            "robustness": r"(\\section\{[^}]*(?:稳健|稳健性).*?\})(.*?)(?=\\section\{|$)",
            "conclusion": r"(\\section\{[^}]*结论.*?\})(.*?)(?=\\section\{|$)",
        }

        pattern = section_patterns.get(section_name)
        if not pattern:
            return None

        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(2) if match.lastindex >= 2 else match.group(1)
        return None

    def run_all_checks(self) -> LanguageCheckResult:
        """运行所有检测"""
        self.check_ai_patterns()
        self.check_confidence_in_conclusion()
        self.check_table_intro_sentences()
        self.check_figure_captions()
        self.check_paragraph_count()
        self.check_abbreviations()
        return self.result


# =============================================================================
# 报告生成
# =============================================================================

def format_report(result: LanguageCheckResult) -> str:
    """生成检测报告"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"论文语言质量检测报告")
    lines.append(f"{'='*60}")
    lines.append(f"文件: {result.file_path}")
    lines.append(f"质量得分: {result.score:.1f}/100")
    lines.append(f"状态: {'✅ 通过' if result.passed else '❌ 不合格'}")
    lines.append("-" * 60)

    def print_category(name: str, issues: list, icon: str = "❌"):
        if not issues:
            lines.append(f"{icon} {name}: 通过（0 问题）")
            return
        lines.append(f"{icon} {name}: 发现 {len(issues)} 个问题")
        for issue in issues[:5]:  # 最多显示5个
            loc = f" (行 {issue['line']})" if "line" in issue else ""
            lines.append(f"   - {issue['message']}{loc}")
        if len(issues) > 5:
            lines.append(f"   ... 还有 {len(issues) - 5} 个问题")

    print_category("AI 味检测", result.ai_issues)
    print_category("底气检测", result.confidence_issues)
    print_category("表格引导句", result.table_intro_issues)
    print_category("图表注释", result.figure_caption_issues)
    print_category("段落数", result.paragraph_issues)
    print_category("缩略语", result.abbreviation_issues)

    total_issues = (
        len(result.ai_issues) + len(result.confidence_issues) +
        len(result.table_intro_issues) + len(result.figure_caption_issues) +
        len(result.paragraph_issues) + len(result.abbreviation_issues)
    )

    lines.append("-" * 60)
    lines.append(f"问题总计: {total_issues}")
    lines.append("=" * 60)

    if not result.passed:
        lines.append("\n💡 改进建议:")
        if result.ai_issues:
            lines.append("  - 替换 AI 典型句式，使用具体数据或机制描述替代")
        if result.confidence_issues:
            lines.append("  - 结论段必须包含具体数字（β = X.XX）或经济规模描述")
        if result.table_intro_issues:
            lines.append("  - 每张表格前补充 ≥2 句引导，后补充 ≥1 句解读")
        if result.figure_caption_issues:
            lines.append("  - 图表注释需包含'说明什么'而非仅'展示什么'")
        if result.paragraph_issues:
            lines.append("  - 章节段落数不足，需扩充内容或拆分章节")

    return "\n".join(lines)


# =============================================================================
# 批量检测
# =============================================================================

def batch_check(directory: Path) -> list[LanguageCheckResult]:
    """批量检测目录下所有 .tex 文件"""
    results = []
    tex_files = sorted(directory.rglob("*.tex"))
    for tex_file in tex_files:
        try:
            content = tex_file.read_text(encoding="utf-8")
            checker = PaperLanguageChecker(content, str(tex_file))
            result = checker.run_all_checks()
            results.append(result)
        except Exception as e:
            print(f"⚠️  跳过 {tex_file}: {e}")
    return results


def print_batch_summary(results: list[LanguageCheckResult]) -> None:
    """打印批量检测摘要"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    avg_score = sum(r.score for r in results) / total if total else 0

    print(f"\n{'='*60}")
    print(f"批量检测摘要")
    print(f"{'='*60}")
    print(f"检测文件: {total}")
    print(f"通过: {passed} ({passed/total*100:.0f}%)")
    print(f"不合格: {total - passed} ({(total-passed)/total*100:.0f}%)")
    print(f"平均得分: {avg_score:.1f}/100")
    print("-" * 60)

    # 按问题数排序
    sorted_results = sorted(
        results,
        key=lambda r: (
            len(r.ai_issues), len(r.confidence_issues),
            len(r.table_intro_issues), len(r.figure_caption_issues)
        ),
        reverse=True,
    )

    print("问题文件 TOP 5:")
    for r in sorted_results[:5]:
        total_issues = (
            len(r.ai_issues) + len(r.confidence_issues) +
            len(r.table_intro_issues) + len(r.figure_caption_issues)
        )
        print(f"  [{r.score:.0f}分] {Path(r.file_path).name} ({total_issues} 问题)")

    print("=" * 60)


# =============================================================================
# 主函数
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="论文语言质量自动化检测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/paper_language_checker.py paper.tex
  python scripts/paper_language_checker.py draft_v1/ --report
  python scripts/paper_language_checker.py output/fin-manuscript/ --batch
        """,
    )
    parser.add_argument("target", nargs="?", help="论文文件或目录路径")
    parser.add_argument("--report", action="store_true", help="生成详细报告")
    parser.add_argument("--batch", action="store_true", help="批量检测目录下所有 .tex 文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式结果")
    parser.add_argument("--strict", action="store_true", help="严格模式（AI 味关键词零容忍）")
    args = parser.parse_args()

    if not args.target:
        parser.print_help()
        sys.exit(1)

    target_path = Path(args.target)

    if not target_path.exists():
        print(f"❌ 文件不存在: {target_path}")
        sys.exit(1)

    if args.batch and target_path.is_dir():
        results = batch_check(target_path)
        print_batch_summary(results)
        if args.report:
            for r in results:
                print(format_report(r))
        sys.exit(0 if all(r.passed for r in results) else 1)

    # 单文件模式（.tex）
    if target_path.is_file() and target_path.suffix == ".tex":
        content = target_path.read_text(encoding="utf-8")
        checker = PaperLanguageChecker(content, str(target_path))
        result = checker.run_all_checks()
        print(format_report(result))
        sys.exit(0 if result.passed else 1)

    # 目录模式（无 --batch 时也支持目录自动批量）
    if target_path.is_dir():
        results = batch_check(target_path)
        print_batch_summary(results)
        if args.report:
            for r in results:
                print(format_report(r))
        sys.exit(0 if all(r.passed for r in results) else 1)

    print(f"❌ 无法处理: {target_path}（请提供 .tex 文件或目录路径）")
    sys.exit(1)


if __name__ == "__main__":
    main()
