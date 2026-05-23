#!/usr/bin/env python3
"""
论文润色、格式检查与投稿工具
==============================
端到端完成：润色 → 查重 → LaTeX 格式检查 → 投稿信生成。

用法：
  python scripts/paper_submit.py paper.md --polish lang english
  python scripts/paper_submit.py paper.md --plagiarism-check
  python scripts/paper_submit.py paper.md --venue NeurIPS --cover-letter
  python scripts/paper_submit.py paper.md --all
"""

import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scripts.ai_router import AI, Task

OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── 1. 润色 ─────────────────────────────────────────

def polish(
    text: str,
    lang: str = "chinese",
    level: str = "standard",
) -> str:
    """
    润色文本。

    Args:
        lang: "chinese" | "english"
        level: "light" | "standard" | "intensive"
    """
    level_map = {
        "chinese": {
            "light": "仅修正语病，保持原意不变",
            "standard": "修正语病、优化表达、学术化语言",
            "intensive": "全面优化：语病、表达、学术风格、逻辑衔接",
        },
        "english": {
            "light": "仅修正语法和拼写，保持原意不变",
            "standard": "修正语法、拼写、标点，优化句子结构，提升可读性",
            "intensive": "全面优化：语法、拼写、句子结构、用词准确性、学术风格",
        },
    }
    desc = level_map.get(lang, {}).get(level, level_map[lang]["standard"])

    if lang == "english":
        prompt = f"""你是一位专业学术论文英文编辑。请对以下文本进行润色（{level}级）。

要求：
{desc}

待润色文本：
{text}

直接输出润色后的完整文本，开头标注 **[Polished English]**，不添加任何解释。"""
    else:
        prompt = f"""你是一位专业中文学术论文编辑。请对以下文本进行润色（{level}级）。

要求：
{desc}

待润色文本：
{text}

直接输出润色后的完整文本，开头标注 **[润色后]**，不添加任何解释。"""

    print(f"\n  ✏️  润色（{lang}，{level}级）...")
    result = AI.chat(prompt, task=Task.TRANSLATION, model="gpt5" if lang == "english" else "deepseek",
                     temperature=0.3, max_tokens=8192)
    text = result.response
    if "[Polished English]" in text:
        text = text.split("[Polished English]")[-1].strip()
    elif "[润色后]" in text:
        text = text.split("[润色后]")[-1].strip()
    print(f"    耗时: {result.latency_ms/1000:.1f}s")
    return text


def iterate_polish(text: str, lang: str, rounds: int = 2) -> str:
    """多轮迭代润色。"""
    print(f"\n  🔄 迭代润色（{rounds}轮）...")
    current = text
    for i in range(rounds):
        print(f"    第 {i+1}/{rounds} 轮...")
        current = polish(current, lang=lang, level="standard")
    return current


# ─── 2. 查重 ─────────────────────────────────────────

def check_plagiarism(text: str) -> dict:
    """
    简单查重（实际查重需使用 iThenticate / Turnitin）。
    """
    print(f"\n  🔍 查重检测...")

    total_chars = len(text)
    total_words = len(text.split())

    template_phrases = [
        "in recent years", "with the development of", "it is well known that",
        "大量研究表明", "近年来", "随着技术的进步",
        "具有重要意义", "引起了广泛关注",
    ]
    found = [p for p in template_phrases if p.lower() in text.lower()]

    template_ratio = len(found) * 50 / max(total_words, 1)
    est_sim = min(template_ratio, 100)

    analysis_prompt = f"""你是一位学术诚信审查员。请分析以下论文文本的重复风险。

待分析文本（5000字）：
{text[:5000]}

请评估：
1. 是否存在大量模板化表达？
2. 是否有拼接痕迹？
3. 核心贡献描述是否原创？
4. 主要风险点是什么？

简短评估即可。"""

    analysis = AI.chat(analysis_prompt, task=Task.RESEARCH, model="deepseek",
                       temperature=0.3, max_tokens=1024)

    risk = "低" if est_sim < 15 else ("中" if est_sim < 30 else "高")
    return {
        "total_chars": total_chars,
        "total_words": total_words,
        "template_found": found,
        "est_similarity": est_sim,
        "risk_level": risk,
        "analysis": analysis.response.strip(),
    }


def latex_check(tex_path: str) -> dict:
    """
    LaTeX 格式检查（需 pandoc + texlive）。
    检测：编译错误、参考文献格式、图表引用、公式编号。
    """
    print(f"\n  📐 LaTeX 格式检查...")

    p = Path(tex_path)
    if not p.exists():
        return {"error": f"文件不存在: {tex_path}"}

    text = p.read_text(encoding="utf-8")
    issues = []

    # 检查图表引用
    refs = {
        "fig": len(re.findall(r'\\ref\{fig:', text)),
        "table": len(re.findall(r'\\ref\{tab:', text)),
        "eq": len(re.findall(r'\\eqref\{', text)),
    }
    figs = len(re.findall(r'\\begin\{figure\}', text))
    tables = len(re.findall(r'\\begin\{table\}', text))
    eqs = len(re.findall(r'\\begin\{equation\}', text))

    if refs["fig"] < figs and figs > 0:
        issues.append(f"警告：{figs} 张图但仅 {refs['fig']} 个 \\ref 引用")
    if refs["table"] < tables and tables > 0:
        issues.append(f"警告：{tables} 张表但仅 {refs['table']} 个 \\ref 引用")
    if refs["eq"] < eqs and eqs > 0:
        issues.append(f"警告：{eqs} 个公式但仅 {refs['eq']} 个 \\eqref 引用")

    # 检查引用格式
    if not re.search(r'\\bibliography', text):
        issues.append("警告：未找到 \\bibliography，缺少参考文献")
    if not re.search(r'\\begin\{thebibliography\}', text) and not re.search(r'\\bibliography', text):
        issues.append("警告：缺少参考文献章节")

    # 检查摘要格式
    if not re.search(r'\\begin\{abstract\}', text):
        issues.append("提示：未找到摘要（\\begin{abstract}）")

    # 统计信息
    word_count = len(text.split())
    section_count = len(re.findall(r'\\section\{', text))

    return {
        "issues": issues,
        "stats": {
            "word_count": word_count,
            "sections": section_count,
            "figures": figs,
            "tables": tables,
            "equations": eqs,
            "fig_refs": refs["fig"],
            "table_refs": refs["table"],
            "eq_refs": refs["eq"],
        }
    }


# ─── 3. 投稿信 ───────────────────────────────────────

def generate_cover_letter(paper_content: str, venue: str, authors: str = "") -> str:
    """生成 Cover Letter。"""

    prompt = f"""你是一位专业学术期刊/会议投稿编辑。请为以下论文生成 **Cover Letter**。

## 论文摘要/内容
{paper_content[:5000]}

## 目标期刊/会议
{venue}

## 作者
{authors or "（请填入）"}

## 格式要求
按以下结构撰写：
1. 信头（姓名、单位、日期）
2. Dear [Editor / Editorial Board of {venue}]:
3. 正文（3-4段）：
   - 投稿声明（原创性、未一稿多投）
   - 核心贡献（1-2句，强调 novelty 和 impact）
   - 符合期刊范围说明
   - 声明作者同意、利益冲突、伦理审查（如适用）
4. 结尾（感谢考虑、期待回复）
5. 通讯作者信息（可选）

总长度：300-500词，语言专业礼貌，不夸大贡献。
"""

    print(f"\n  ✍️  生成 Cover Letter...")
    result = AI.chat(prompt, task=Task.PAPER_EN, model="gpt5",
                     temperature=0.4, max_tokens=4096)
    print(f"    耗时: {result.latency_ms/1000:.1f}s")
    return result.response.strip()


def generate_response_letter(
    paper_content: str,
    reviews: str,
    authors: str = "",
) -> str:
    """生成审稿回复信（Response Letter）。

    Args:
        paper_content: 论文内容（前3000字）
        reviews: 审稿意见（直接嵌入 prompt 防注入）
        authors: 作者列表
    """
    # 安全转义：防止审稿意见中的 prompt 注入指令影响 LLM 输出
    def _safe(s: str) -> str:
        return (s
            .replace("\x00", "")
            .replace("```", "\u200b```")
            .replace("{{", "\u200b{{")
            .replace("}}", "\u200b}}"))

    safe_reviews = _safe(reviews)
    safe_paper = _safe(paper_content[:3000])

    prompt = f"""你是一位经验丰富的学术论文作者。请为以下论文撰写 **Response Letter**（修改稿回复信）。

## 论文标题/内容
{safe_paper}

## 作者
{_safe(authors) if authors else "（请填入）"}

## 审稿意见
{safe_reviews}

## 格式要求
### 1. 信头
Dear Editor and Reviewers:
Thank you for your thoughtful comments...

### 2. 逐条回复（按审稿意见编号）
**Reviewer #X [Major/Minor]: [意见标题]**
> [引用审稿意见原文]

**Response:**
- 首先感谢审稿人
- 说明是否同意
- 如果同意：说明做了哪些修改
- 如果不同意：礼貌解释原因，提供证据
- 引用修改位置（如 "As shown in Section 3.2"）

### 3. 修改摘要（表格）
| Reviewer | Comment | Change Made |
|----------|---------|-------------|
| #1       | ...     | Added ...   |

### 4. 结尾
We hope the revisions adequately address all concerns...

总长度：根据审稿意见数量，1000-3000词。
风格：专业、礼貌、建设性，绝对不要 defensive。
"""

    print(f"\n  ✍️  生成 Response Letter...")
    result = AI.chat(prompt, task=Task.PAPER_EN, model="gpt5",
                     temperature=0.4, max_tokens=8192)
    print(f"    耗时: {result.latency_ms/1000:.1f}s")
    return result.response.strip()


# ─── 辅助 ────────────────────────────────────────────

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
    print(f"  🔍 查重报告")
    print(f"{'='*70}")
    print(f"  总字符数: {report['total_chars']:,}")
    print(f"  总词数:   {report['total_words']:,}")
    print(f"  风险等级: {report['risk_level']}")
    print(f"  估计相似度: {report['est_similarity']:.1f}%")
    print(f"  模板句式: {', '.join(report['template_found']) or '无'}")
    print(f"\n  AI 分析:")
    for line in report['analysis'].split('\n')[:5]:
        if line.strip():
            print(f"    {line.strip()}")


def print_latex_report(report: dict):
    if "error" in report:
        print(f"  错误: {report['error']}")
        return
    print(f"\n{'='*70}")
    print(f"  📐 LaTeX 格式检查报告")
    print(f"{'='*70}")
    s = report["stats"]
    print(f"  字数: {s['word_count']:,} | 章节: {s['sections']} | 图: {s['figures']} | 表: {s['tables']} | 公式: {s['equations']}")
    print(f"  引用: 图ref={s['fig_refs']} 表ref={s['table_refs']} 公式ref={s['eq_refs']}")
    if report["issues"]:
        print(f"\n  问题列表:")
        for iss in report["issues"]:
            print(f"    ⚠  {iss}")
    else:
        print(f"\n  ✅ 未发现问题")


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
    print(f"  论文润色、查重与投稿工具 v2.0")
    print(f"{'='*70}")

    paper_content = ""
    if args.paper:
        paper_content = load_paper(args.paper)
        print(f"  文件: {args.paper}")
        print(f"  字符数: {len(paper_content):,}")

    output_parts = []

    # 润色
    if args.polish:
        lang, level = args.polish
        if args.iterate > 0:
            polished = iterate_polish(paper_content, lang=lang, rounds=args.iterate)
        else:
            polished = polish(paper_content, lang=lang, level=level)
        print(f"\n[润色结果预览]")
        print(polished[:500])
        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_output(polished, f"polished_{lang}_{ts}.md")
        output_parts.append(("润色", polished))

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
        print(f"  Cover Letter")
        print(f"{'='*70}")
        print(letter[:1000])
        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_output(letter, f"cover_letter_{ts}.txt")

    # Response Letter
    if args.response_letter:
        letter = generate_response_letter(paper_content, args.response_letter, args.authors)
        print(f"\n{'='*70}")
        print(f"  Response Letter")
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
    print(f"  ✅ 完成！")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
