#!/usr/bin/env python3
"""
论文润色、格式检查与投稿工具
==============================
端到端完成：润色 → 查重 → LaTeX 格式检查 → 投稿信生成。

此模块是 paper_submitter.py 的便捷 CLI 入口，
完整功能请使用 paper_submitter.py。

用法：
  python scripts/paper_submit.py paper.md --polish lang english
  python scripts/paper_submit.py paper.md --plagiarism-check
  python scripts/paper_submit.py paper.md --venue NeurIPS --cover-letter
  python scripts/paper_submit.py paper.md --all

完整投稿系统（期刊匹配/合规检查/状态追踪）：
  python scripts/paper_submitter.py check paper.tex --venue NeurIPS
  python scripts/paper_submitter.py match paper.pdf --field "Machine Learning"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scripts.paper_tools_core import (
    check_plagiarism,
    generate_cover_letter,
    generate_response_letter,
    iterate_polish,
    latex_check,
    polish,
)

OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── 辅助函数 ───────────────────────────────────────

def load_paper(path: str) -> str:
    """加载论文内容。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return p.read_text(encoding="utf-8")


def save_output(content: str, filename: str) -> str:
    """保存到 output 目录。"""
    filepath = OUTPUT_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"\n💾 已保存: {filepath}")
    return str(filepath)


def print_plagiarism_report(report: dict):
    print(f"\n{'='*70}")
    print("  🔍 查重报告")
    print(f"{'='*70}")
    print(f"  总字符数: {report['total_chars']:,}")
    print(f"  总词数:   {report['total_words']:,}")
    print(f"  风险等级: {report['risk_level']}")
    print(f"  估计相似度: {report['est_similarity']:.1f}%")
    print(f"  模板句式: {', '.join(report['template_found']) or '无'}")
    print("\n  AI 分析:")
    for line in report['analysis'].split('\n')[:5]:
        if line.strip():
            print(f"    {line.strip()}")


def print_latex_report(report: dict):
    if "error" in report:
        print(f"  错误: {report['error']}")
        return
    print(f"\n{'='*70}")
    print("  📐 LaTeX 格式检查报告")
    print(f"{'='*70}")
    s = report["stats"]
    print(f"  字数: {s['word_count']:,} | 章节: {s['sections']} | 图: {s['figures']} | 表: {s['tables']} | 公式: {s['equations']}")
    print(f"  引用: 图ref={s['fig_refs']} 表ref={s['table_refs']} 公式ref={s['eq_refs']}")
    if report["issues"]:
        print("\n  问题列表:")
        for iss in report["issues"]:
            print(f"    ⚠  {iss}")
    else:
        print("\n  ✅ 未发现问题")


# ─── 主入口 ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="论文润色、查重、格式检查与投稿工具 v2.0")
    parser.add_argument("paper", nargs="?", help="论文文件路径（.md/.tex）")
    parser.add_argument("--polish", nargs=2, metavar=("LANG", "LEVEL"),
                      help="润色，如 --polish english standard")
    parser.add_argument("--plagiarism-check", action="store_true", help="查重")
    parser.add_argument("--latex-check", action="store_true", help="LaTeX 格式检查")
    parser.add_argument("--cover-letter", action="store_true", help="生成 Cover Letter")
    parser.add_argument("--response-letter", help="根据审稿意见生成 Response Letter")
    parser.add_argument("--venue", "-v", default="", help="目标期刊/会议")
    parser.add_argument("--authors", "-a", default="", help="作者列表")
    parser.add_argument("--iterate", type=int, default=0, help="迭代润色轮数")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--save", action="store_true", help="保存到 output/")

    args = parser.parse_args()

    if not args.paper and not (args.cover_letter or args.response_letter):
        parser.print_help()
        print("\n--- 示例 ---")
        print("  python scripts/paper_submit.py paper.md --polish english intensive")
        print("  python scripts/paper_submit.py paper.md --plagiarism-check")
        print("  python scripts/paper_submit.py paper.md --latex-check")
        print("  python scripts/paper_submit.py paper.md --venue NeurIPS --cover-letter")
        print("  python scripts/paper_submit.py paper.md --response-letter '审稿意见...'")
        print("  python scripts/paper_submit.py paper.md --all --venue ACL")
        return

    print(f"\n{'='*70}")
    print("  论文润色、查重与投稿工具 v2.0")
    print(f"{'='*70}")

    paper_content = ""
    if args.paper:
        paper_content = load_paper(args.paper)
        print(f"  文件: {args.paper}")
        print(f"  字符数: {len(paper_content):,}")

    # 润色
    if args.polish:
        lang, level = args.polish
        if args.iterate > 0:
            polished = iterate_polish(paper_content, lang=lang, rounds=args.iterate)
        else:
            polished = polish(paper_content, lang=lang, level=level)
        print("\n[润色结果预览]")
        print(polished[:500])
        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_output(polished, f"polished_{lang}_{ts}.md")

    # 查重
    if args.plagiarism_check:
        report = check_plagiarism(paper_content)
        print_plagiarism_report(report)
        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_output(json.dumps(report, ensure_ascii=False, indent=2),
                       f"plagiarism_report_{ts}.json")

    # LaTeX 格式检查
    if args.latex_check and args.paper:
        if args.paper.endswith(".tex"):
            report = latex_check(args.paper)
            print_latex_report(report)
        else:
            print("  ⚠ LaTeX 检查仅适用于 .tex 文件")

    # Cover Letter
    if args.cover_letter:
        content = paper_content or args.output or ""
        letter = generate_cover_letter(content, args.venue, args.authors)
        print(f"\n{'='*70}")
        print("  Cover Letter")
        print(f"{'='*70}")
        print(letter[:1000])
        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_output(letter, f"cover_letter_{ts}.txt")

    # Response Letter
    if args.response_letter:
        letter = generate_response_letter(paper_content, args.response_letter, args.authors)
        print(f"\n{'='*70}")
        print("  Response Letter")
        print(f"{'='*70}")
        print(letter[:1000])
        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_output(letter, f"response_letter_{ts}.txt")

    # 全流程
    if args.paper and not any([args.polish, args.plagiarism_check,
                                args.latex_check, args.cover_letter,
                                args.response_letter]):
        print("  ⚠ 请指定操作：--polish / --plagiarism-check / --cover-letter 等")
        return

    print(f"\n{'='*70}")
    print("  ✅ 完成！")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()


# ─── 类式包装（供 ToolSelector / ResearchSession 导入）───────────────────

class PaperSubmitter:
    """
    论文投稿工具类式包装，支持工具化调用。

    完整功能代理到 paper_submitter.py。
    """

    def __init__(self):
        from scripts.paper_submitter import PaperSubmitter as _PS
        self._delegate = _PS()

    def polish(self, text: str, lang: str = "chinese", level: str = "standard") -> str:
        return polish(text, lang, level)

    def iterate_polish(self, text: str, lang: str = "chinese", rounds: int = 2) -> str:
        return iterate_polish(text, lang, rounds)

    def check_plagiarism(self, text: str) -> dict:
        return check_plagiarism(text)

    def latex_check(self, tex_path: str) -> dict:
        return latex_check(tex_path)

    def generate_cover_letter(
        self,
        paper_content: str = "",
        venue: str = "",
        authors: str = "",
    ) -> str:
        return generate_cover_letter(paper_content, venue, authors)

    def generate_response_letter(
        self,
        paper_content: str = "",
        reviews: str = "",
        authors: str = "",
    ) -> str:
        return generate_response_letter(paper_content, reviews, authors)

    # 扩展方法（来自 paper_submitter.py）
    def match_venue(self, paper_content: str, field: str = "") -> list[dict]:
        return self._delegate.match_venue(paper_content, field)

    def check_compliance(self, paper_path: str, venue: str) -> dict:
        return self._delegate.check_compliance(paper_path, venue)

    def create_submission(
        self,
        title: str = "",
        venue: str = "",
        files: dict = None,
    ) -> dict:
        return self._delegate.create_submission(title, venue, files)

    def update_status(
        self,
        submission_id: str = "",
        status: str = "",
        notes: str = "",
    ) -> dict:
        return self._delegate.update_status(submission_id, status, notes)

    def list_submissions(self) -> list[dict]:
        return self._delegate.list_submissions()

    def generate_package(
        self,
        paper_path: str = "",
        venue: str = "",
        authors: str = "",
        output_dir: str = "submission_package",
    ) -> dict:
        return self._delegate.generate_package(paper_path, venue, authors, output_dir)
