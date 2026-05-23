#!/usr/bin/env python3
"""
论文全流程写作工具
=================
端到端完成：选题 → 大纲 → 各章节 → 全文整合。

与 ai_router.py 深度集成，自动路由最优模型：
  文献调研   → DeepSeek（快、便宜）
  中文写作   → DeepSeek
  英文润色   → GPT-5.5（最强）
  复杂推理   → Gemini-3.1-Pro

用法：
  python scripts/paper_write.py --topic "深度学习 量化交易"
  python scripts/paper_write.py --topic "大模型 金融文档" --venue ACL --save
  python scripts/paper_write.py --step outline         # 仅生成大纲
  python scripts/paper_write.py --step intro           # 仅生成引言
  python scripts/paper_write.py --step full            # 完整流程
  python scripts/paper_write.py --assemble              # 仅整合已有章节
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scripts.ai_router import AI, Task
from scripts.review_layer import ReviewLayer, ReviewType


# ─── 章节审查辅助函数 ─────────────────────────────────

def _review_chapter(content: str, chapter_name: str,
                    content_type: ReviewType, topic: str, venue: str) -> str:
    """审查单个章节。返回修复后的内容（如果质量<7分则修复）。"""
    layer = ReviewLayer(use_cache=True)
    result = layer.review_and_fix(content, content_type, {"topic": topic, "venue": venue})
    score = result.overall_score
    issues = result.issues

    if score >= 8.0:
        print(f"  [{chapter_name}] ✅ 质量良好（{score}/10）")
        return content
    elif score >= 6.0:
        print(f"  [{chapter_name}] ⚠️  质量一般（{score}/10），修复中...")
    else:
        print(f"  [{chapter_name}] ❌ 质量问题较多（{score}/10），修复中...")

    if issues:
        for issue in issues[:3]:
            print(f"       - {issue[:70]}")
    return result.fixed_content


PAPER_DIR = SCRIPT_DIR / "knowledge" / "papers"
OUTLINE_DIR = SCRIPT_DIR / "knowledge" / "outlines"
CHAPTER_DIR = SCRIPT_DIR / "knowledge" / "chapters"
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for d in [PAPER_DIR, OUTLINE_DIR, CHAPTER_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_MAX_TOKENS = {
    "outline": 4096,
    "intro": 2048,
    "related": 4096,
    "method": 6144,
    "experiment": 6144,
    "conclusion": 2048,
    "assemble": 8192,
}


# ─── 步骤 1：大纲生成 ────────────────────────────────

def generate_outline(
    topic: str,
    target_venue: str = "",
    max_tokens: int = 4096,
) -> dict:
    """生成论文选题与大纲。"""
    venue_hint = f"（目标投稿：{target_venue}）" if target_venue else ""

    prompt = f"""你是一位顶级 AI/金融 领域的研究专家。请为以下研究方向设计一篇高质量学术论文的整体框架。

研究方向：{topic} {venue_hint}

请输出以下内容（全部使用中文）：

## 一、候选论文标题
给出 3 个候选标题（中英文），说明各标题的侧重点。

## 二、研究问题定位
将研究主题聚焦为 1-2 个可操作的、具体的研究问题。

## 三、主要创新点（3-5 条）
每条说明：创新类型（理论/方法/应用/数据集）、具体内容、与现有工作的核心区别。

## 四、论文大纲
按以下标准结构给出每个章节的内容概要：
### 1 Introduction（引言，约 800 字）
### 2 Related Work（相关工作，约 1000 字）
### 3 Methodology / Proposed Method（方法论，约 2000 字）
  3.1 问题定义
  3.2 模型/算法设计
  3.3 训练策略
### 4 Experiments（实验，约 1500 字）
  4.1 数据集与基线
  4.2 主实验结果
  4.3 消融实验
### 5 Conclusion & Future Work（结论，约 400 字）

## 五、研究路线图
按时间顺序说明完成这篇论文的研究步骤。

## 六、预期结果
预期能在哪些方面超越现有方法？
"""

    print(f"\n{'='*70}")
    print(f"  [1/7] 生成论文大纲")
    print(f"  主题: {topic}")
    if target_venue:
        print(f"  目标: {target_venue}")
    print(f"{'='*70}")

    result = AI.chat(prompt, task=Task.RESEARCH, model="deepseek",
                     temperature=0.5, max_tokens=max_tokens)
    print(f"  耗时: {result.latency_ms/1000:.1f}s | 模型: {result.model_used}")

    outline = _parse_outline_result(result.response)
    outline["topic"] = topic
    outline["target_venue"] = target_venue
    outline["generated_at"] = datetime.now().isoformat()
    return outline


def _parse_outline_result(text: str) -> dict:
    """从 AI 返回中解析大纲结构。"""
    def extract_section(name: str) -> str:
        for p in [
            rf"{name}（.*?）\n([\s\S]*?)(?=\n## |\n#|$)",
            rf"{name}\n([\s\S]*?)(?=\n## |\n#|\n\n\n|$)",
        ]:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()[:5000]
        return ""

    return {
        "title": extract_section("候选论文标题") or extract_section("论文标题"),
        "research_question": extract_section("研究问题定位"),
        "contributions": _extract_bullets(text, "创新点"),
        "outline": {
            "introduction": extract_section("Introduction（引言"),
            "related_work": extract_section("Related Work（相关工作"),
            "methodology": extract_section("Methodology / Proposed Method（方法论"),
            "experiments": extract_section("Experiments（实验"),
            "conclusion": extract_section("Conclusion & Future Work（结论"),
        },
        "methodology": extract_section("研究路线图"),
        "expected_results": extract_section("预期结果"),
        "raw": text,
    }


def _extract_bullets(text: str, section: str) -> list[str]:
    lines, in_section = [], False
    for line in text.split("\n"):
        if re.search(rf"##?\s*{section}", line):
            in_section = True
            continue
        if in_section and re.match(r"##?\s*\d", line):
            break
        if in_section and line.strip():
            lines.append(line.strip())
    return [l for l in lines if len(l) > 10][:10]


# ─── 步骤 2：引言 + 相关工作 ─────────────────────────

def write_intro_related(outline: dict, max_tokens: int = 4096) -> dict:
    """生成 Introduction + Related Work。"""
    topic = outline.get("topic", "")
    outline_json = json.dumps(outline.get("outline", {}), ensure_ascii=False, indent=2)
    contrib = "\n".join(f"- {c}" for c in outline.get("contributions", []))
    refs = _load_reference_material(topic)

    chapters = {}

    # Introduction
    prompt_intro = f"""你是一位经验丰富的学术论文写作者。请为以下研究撰写 **Introduction**（目标 800 字，中文）：

## 研究主题
{topic}

## 创新点
{contrib}

## 大纲
{outline_json}

## 要求
1. 开场与领域背景（1-2段）
2. 研究问题与挑战（1-2段）
3. 本文方法概述（1段）
4. 主要贡献（以 We propose... 格式，3-4条）
5. 论文结构（最后一段）
"""
    print(f"\n  [2/7] 撰写 Introduction...")
    r = AI.chat(prompt_intro, task=Task.PAPER_CN, model="deepseek",
                temperature=0.4, max_tokens=max_tokens)
    print(f"    耗时: {r.latency_ms/1000:.1f}s")
    chapters["introduction"] = r.response.strip()

    # Related Work
    prompt_related = f"""你是一位经验丰富的学术论文写作者。请为以下研究撰写 **Related Work**（目标 1000 字，中文）：

## 研究主题
{topic}

## 大纲
{outline_json}

## 文献参考
{refs[:5000]}

## 要求
1. 技术基础（1-2段，引用2-3篇代表性工作）
2. 现有方法分类（2-4段，按技术路线分组，每组分析优点和局限性）
3. 数据集与基准（1段）
4. 与本文的关联（1段，不要详述本文方法）
格式：用 \\cite{{author2023}} 引用，小标题分组
"""
    print(f"\n  [3/7] 撰写 Related Work...")
    r = AI.chat(prompt_related, task=Task.PAPER_CN, model="deepseek",
                temperature=0.4, max_tokens=max_tokens)
    print(f"    耗时: {r.latency_ms/1000:.1f}s")
    chapters["related_work"] = r.response.strip()

    return chapters


# ─── 步骤 3：方法论 ──────────────────────────────────

def write_methodology(outline: dict, max_tokens: int = 6144) -> str:
    """生成 Methodology 章节。"""
    topic = outline.get("topic", "")
    outline_json = json.dumps(outline.get("outline", {}), ensure_ascii=False, indent=2)
    contrib = "\n".join(f"- {c}" for c in outline.get("contributions", []))

    prompt = f"""你是一位经验丰富的学术论文写作者。请为以下研究撰写 **Methodology**（目标 2000 字，中文）：

## 研究主题
{topic}

## 创新点
{contrib}

## 大纲
{outline_json}

## 要求
### 3.1 问题定义
形式化定义输入、输出，用数学符号说明研究问题，定义评估指标。

### 3.2 模型/算法设计
详细描述本文提出的模型架构或算法，包含关键组件说明。

### 3.3 训练策略
损失函数、优化器与学习率调度、正则化策略。

### 3.4 复杂度分析（可选）
时间/空间复杂度，与基线方法对比。

风格：语言严谨、数学符号用 LaTeX 格式、每个决策要有动机。
"""
    print(f"\n  [4/7] 撰写 Methodology...")
    r = AI.chat(prompt, task=Task.PAPER_CN, model="deepseek",
                temperature=0.4, max_tokens=max_tokens)
    print(f"  耗时: {r.latency_ms/1000:.1f}s")
    return r.response.strip()


# ─── 步骤 4：实验 + 结论 ─────────────────────────────

def write_experiment_conclusion(outline: dict, max_tokens: int = 6144) -> dict:
    """生成 Experiments + Conclusion 章节。"""
    topic = outline.get("topic", "")
    outline_json = json.dumps(outline.get("outline", {}), ensure_ascii=False, indent=2)
    contrib = "\n".join(f"- {c}" for c in outline.get("contributions", []))

    chapters = {}

    # Experiment
    prompt_exp = f"""你是一位经验丰富的学术论文写作者。请为以下研究撰写 **Experiments**（目标 1500 字，中文）：

## 研究主题
{topic}

## 创新点
{contrib}

## 大纲
{outline_json}

## 要求
### 4.1 数据集与基线（至少3-4个基线，说明选择理由）
### 4.2 实验设置（环境、超参数、评估指标）
### 4.3 主实验结果（表格对比，显著性标注 ∗p<0.05）
### 4.4 消融实验（各组件贡献分析）
格式：使用 LaTeX 表格格式（\\begin{{table}}）
"""
    print(f"\n  [5/7] 撰写 Experiments...")
    r = AI.chat(prompt_exp, task=Task.PAPER_CN, model="deepseek",
                temperature=0.3, max_tokens=max_tokens)
    print(f"    耗时: {r.latency_ms/1000:.1f}s")
    chapters["experiment"] = r.response.strip()

    # Conclusion
    prompt_conc = f"""你是一位经验丰富的学术论文写作者。请为以下研究撰写 **Conclusion**（目标 400 字，中文）：

## 研究主题
{topic}

## 创新点
{contrib}

## 要求
1. 总结（简要概述研究问题和目标，主要结果用具体数字）
2. 主要贡献回顾（3条）
3. 局限性（数据集规模/计算成本/未覆盖场景）
4. 未来工作（2-3个有价值的改进方向）

风格：简洁、避免重复 Introduction 内容、未来工作要有前瞻性。
"""
    print(f"\n  [6/7] 撰写 Conclusion...")
    r = AI.chat(prompt_conc, task=Task.PAPER_CN, model="deepseek",
                temperature=0.4, max_tokens=2048)
    print(f"    耗时: {r.latency_ms/1000:.1f}s")
    chapters["conclusion"] = r.response.strip()

    return chapters


# ─── 步骤 5：全文整合 ────────────────────────────────

def assemble_full_paper(
    topic: str,
    outline: dict,
    chapters: dict,
    max_tokens: int = 8192,
) -> str:
    """整合所有章节，生成完整论文。"""
    outline_text = json.dumps(outline, ensure_ascii=False, indent=2)[:3000]
    chapter_text = "\n\n".join(f"# {k.upper()}\n{v}" for k, v in chapters.items())
    refs = _load_reference_material(topic)[:3000]

    prompt = f"""你是一位专业学术论文编辑。请将以下材料整合成一篇完整学术论文（中文）。

## 研究主题
{topic}

## 论文大纲
{outline_text}

## 已有章节
{chapter_text[:8000]}

## 文献参考
{refs}

## 要求
生成完整论文，包含：
1. **Title** — 论文标题
2. **Abstract** — 约200字，涵盖背景、问题、方法、结论
3. **Introduction** — 约800字（用已有章节内容）
4. **Related Work** — 约1000字
5. **Methodology** — 约2000字
6. **Experiments** — 约1500字
7. **Conclusion** — 约400字

整合要求：
- 填充已有章节内容
- 补充缺失章节
- 确保章节间逻辑连贯
- Abstract 覆盖全文核心信息
- 补充过渡句

格式：Markdown，LaTeX公式用 $$...$$
"""
    print(f"\n  [7/7] 整合全文...")
    r = AI.chat(prompt, task=Task.PAPER_CN, model="deepseek",
                temperature=0.4, max_tokens=max_tokens)
    print(f"    耗时: {r.latency_ms/1000:.1f}s")
    return r.response.strip()


# ─── 辅助函数 ────────────────────────────────────────

def _load_reference_material(topic: str = "", max_chars: int = 8000) -> str:
    """加载文献综述和大纲作为参考。"""
    material = []

    reviews = sorted((PAPER_DIR.parent / "reviews").glob("*.md"), reverse=True)
    if reviews:
        material.append(f"【文献综述】\n{reviews[0].read_text(encoding='utf-8')[:max_chars//2]}")

    outlines = sorted((PAPER_DIR.parent / "outlines").glob("*.md"), reverse=True)
    if outlines:
        material.append(f"【论文大纲】\n{outlines[0].read_text(encoding='utf-8')[:max_chars//2]}")

    index_file = PAPER_DIR / "index.json"
    if index_file.exists():
        try:
            index = json.loads(index_file.read_text(encoding="utf-8"))
            papers = index.get("papers", [])[:8]
            if papers:
                papers_text = "\n".join(
                    f"- {p.get('title','未知')}: "
                    f"方法={p.get('analysis',{}).get('model_method','未知')} "
                    f"结论={'; '.join(p.get('analysis',{}).get('main_conclusions',[])[:1])}"
                    for p in papers
                )
                material.append(f"【论文库文献】\n{papers_text}")
        except Exception:
            pass

    return "\n\n---\n\n".join(material)[:max_chars]


def _save_outline(outline: dict) -> str:
    """保存大纲到知识库。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "_", outline.get("topic", "topic"))[:15]
    filepath = OUTLINE_DIR / f"{safe}_{timestamp}.md"

    md = f"""# 论文选题与大纲

**主题**: {outline.get('topic', '')}
**目标期刊**: {outline.get('target_venue', '未定')}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 候选论文标题

{outline.get('title', '')}

---

## 研究问题定位

{outline.get('research_question', '')}

---

## 主要创新点

"""
    for i, c in enumerate(outline.get('contributions', []), 1):
        md += f"{i}. {c}\n"

    md += "\n---\n\n## 论文大纲\n\n"
    for sec, content in outline.get("outline", {}).items():
        if content:
            md += f"### {sec.upper()}\n{content}\n\n"

    md += f"\n---\n*由 DeepSeek 生成 | {datetime.now().strftime('%Y-%m-%d')}*\n"
    filepath.write_text(md, encoding="utf-8")
    print(f"\n💾 大纲已保存: {filepath}")
    return str(filepath)


def _save_chapters(chapters: dict, topic: str) -> str:
    """保存各章节草稿。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "_", topic)[:15]
    filepath = CHAPTER_DIR / f"{safe}_{timestamp}.md"

    md = f"# 论文章节草稿\n\n**主题**: {topic}\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    for name, content in chapters.items():
        md += f"---\n\n## {name.upper()}\n\n{content}\n\n"

    filepath.write_text(md, encoding="utf-8")
    print(f"💾 章节已保存: {filepath}")
    return str(filepath)


def _save_paper(content: str, topic: str, fmt: str = "markdown") -> str:
    """保存完整论文。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "_", topic)[:15]
    ext = "tex" if fmt == "latex" else ("docx" if fmt == "word" else "md")
    filepath = OUTPUT_DIR / f"{safe}_{timestamp}.{ext}"
    filepath.write_text(content, encoding="utf-8")
    print(f"\n💾 论文已保存: {filepath}")
    return str(filepath)


# ─── 主入口 ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="论文全流程写作工具 v2.0")
    parser.add_argument("--topic", "-t", help="研究方向/主题")
    parser.add_argument("--venue", help="目标期刊/会议（如 NeurIPS, ACL, JFE）")
    parser.add_argument("--step",
                       choices=["outline", "intro", "full"],
                       default="full",
                       help="outline=仅大纲, intro=大纲+引言+相关工作, full=完整流程（默认）")
    parser.add_argument("--assemble", action="store_true",
                       help="仅整合已有章节为完整论文")
    parser.add_argument("--max-tokens", type=int, default=0,
                       help="最大 token 数")
    parser.add_argument("--save", action="store_true", help="保存到知识库")
    parser.add_argument("--format", "-f", default="markdown",
                       choices=["markdown", "latex", "word"],
                       help="输出格式")
    parser.add_argument("--outline-file", help="指定大纲文件（跳过生成）")

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"  论文写作工具 v2.0")
    print(f"  AI路由: DeepSeek(中文) / GPT-5.5(英文) / Gemini(推理)")
    print(f"{'='*70}")

    # 路由1：仅整合
    if args.assemble:
        refs = _load_reference_material()
        topic = args.topic or "待定"
        outline = _load_outline_file(args.outline_file) if args.outline_file else {}
        outline.setdefault("topic", topic)
        outline.setdefault("contributions", [])

        chapters = _load_existing_chapters()
        if not chapters:
            print("⚠ 未找到已有章节，请先生成章节内容")
            return

        print(f"  整合 {len(chapters)} 个章节...")
        full = assemble_full_paper(topic, outline, chapters)
        print(f"\n{'='*70}")
        print(full[:2000])
        if args.save:
            _save_paper(full, topic, args.format)
        return

    # 路由2：生成
    if not args.topic:
        parser.print_help()
        print("\n--- 示例 ---")
        print("  python scripts/paper_write.py --topic '深度学习 量化交易' --save")
        print("  python scripts/paper_write.py --topic '大模型 金融文档' --venue ACL --step full")
        print("  python scripts/paper_write.py --step outline --topic '强化学习 做市商'")
        return

    max_t = args.max_tokens or 0
    mt = {k: max_t for k in DEFAULT_MAX_TOKENS} if max_t else DEFAULT_MAX_TOKENS

    # Step 1: 大纲
    outline = None
    if args.outline_file:
        print(f"\n加载已有大纲: {args.outline_file}")
        outline = _load_outline_file(args.outline_file)
        outline["topic"] = args.topic or outline.get("topic", "")
    else:
        outline = generate_outline(args.topic, args.venue, mt.get("outline", 4096))

    if args.step == "outline":
        print_outline_summary(outline)
        if args.save:
            _save_outline(outline)
        return

    if outline and args.save:
        _save_outline(outline)

    # Step 2-3: 引言 + 相关工作
    chapters = write_intro_related(outline, mt.get("intro", 4096))

    if args.step == "intro":
        if args.save:
            _save_chapters(chapters, args.topic)
        for name, content in chapters.items():
            print(f"\n{'='*70}")
            print(f"  {name.upper()}")
            print(f"{'='*70}")
            print(content[:500])
        return

    # 🔍 审查：引言 + 相关工作
    print(f"\n{'='*70}")
    print(f"  🔍 审查章节...")
    venue = args.venue or "Unknown"
    for key in ("introduction", "intro", "related_work"):
        if key in chapters:
            chapters[key] = _review_chapter(
                chapters[key], key.upper(),
                ReviewType.PAPER_CHAPTER, args.topic, venue
            )

    # Step 4: 方法论
    chapters["methodology"] = write_methodology(outline, mt.get("method", 6144))

    # 🔍 审查：方法论
    chapters["methodology"] = _review_chapter(
        chapters["methodology"], "METHODOLOGY",
        ReviewType.PAPER_CHAPTER, args.topic, venue
    )

    # Step 5: 实验 + 结论
    exp_conc = write_experiment_conclusion(outline, mt.get("experiment", 6144))
    chapters.update(exp_conc)

    # 🔍 审查：实验 + 结论
    for key in ("experiments", "experiment", "conclusion"):
        if key in chapters:
            chapters[key] = _review_chapter(
                chapters[key], key.upper(),
                ReviewType.PAPER_CHAPTER, args.topic, venue
            )

    # 保存章节
    if args.save:
        _save_chapters(chapters, args.topic)

    # Step 6: 全文整合
    full_paper = assemble_full_paper(args.topic, outline, chapters, mt.get("assemble", 8192))

    print(f"\n{'='*70}")
    print(f"  🔍 审查完整论文...")
    full_paper = _review_chapter(
        full_paper, "FULL PAPER",
        ReviewType.PAPER_CHAPTER, args.topic, venue
    )

    print(f"\n{'='*70}")
    print(f"  完整论文预览（前2000字）")
    print(f"{'='*70}")
    print(full_paper[:2000])

    if args.save:
        _save_paper(full_paper, args.topic, args.format)

    print(f"\n{'='*70}")
    print(f"  ✅ 完成！")
    print(f"{'='*70}")


def _load_outline_file(path: str) -> dict:
    """加载大纲文件（.json 或 .md）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"大纲文件不存在: {path}")

    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        return json.loads(text)

    # 从 Markdown 提取
    outline = {"topic": "", "contributions": [], "outline": {}}
    for key, pattern in [
        ("topic", r"\*\*主题\*\*[:：]\s*(.+)"),
        ("title", r"## 候选论文标题\n([\s\S]*?)(?=\n## |$)"),
        ("research_question", r"## 研究问题定位\n([\s\S]*?)(?=\n## |$)"),
    ]:
        m = re.search(pattern, text)
        if m:
            outline[key] = m.group(1).strip()

    for key, pattern in [
        ("introduction", r"### 1\.?.*introduction\n([\s\S]*?)(?=\n###|## )"),
        ("related_work", r"### 2\.?.*related.?work\n([\s\S]*?)(?=\n###|## )"),
        ("methodology", r"### 3\.?.*methodology\n([\s\S]*?)(?=\n###|## )"),
        ("experiments", r"### 4\.?.*experiments\n([\s\S]*?)(?=\n###|## )"),
        ("conclusion", r"### 5\.?.*conclusion\n([\s\S]*?)(?=\n###|## |$)"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            outline["outline"][key] = m.group(1).strip()

    return outline


def _load_existing_chapters() -> dict:
    """加载最新的已有章节。"""
    chapters = {}
    files = sorted(CHAPTER_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return chapters

    text = files[0].read_text(encoding="utf-8")
    for key, pattern in [
        ("introduction", r"## 1\.?\s*introduction\n([\s\S]*?)(?=\n## |\n#|$)"),
        ("related_work", r"## 2\.?\s*related.?work\n([\s\S]*?)(?=\n## |\n#|$)"),
        ("methodology", r"## 3\.?\s*methodology\n([\s\S]*?)(?=\n## |\n#|$)"),
        ("experiment", r"## 4\.?\s*experiments?\n([\s\S]*?)(?=\n## |\n#|$)"),
        ("conclusion", r"## 5\.?\s*conclusion\n([\s\S]*?)(?=\n## |\n#|$)"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            content = m.group(1).strip()
            if content:
                chapters[key] = content
    return chapters


def print_outline_summary(outline: dict):
    """打印大纲摘要。"""
    print(f"\n{'='*70}")
    print(f"  📋 大纲摘要")
    print(f"{'='*70}")
    title = outline.get("title", "")
    if title:
        print(f"\n  候选标题\n  {'─'*60}")
        for line in title.split("\n")[:5]:
            if line.strip():
                print(f"    {line.strip()[:70]}")

    rq = outline.get("research_question", "")
    if rq:
        print(f"\n  研究问题\n  {'─'*60}")
        for line in rq.split("\n")[:4]:
            if line.strip():
                print(f"    {line.strip()[:70]}")

    contributions = outline.get("contributions", [])
    if contributions:
        print(f"\n  创新点（{len(contributions)}条）\n  {'─'*60}")
        for i, c in enumerate(contributions[:5], 1):
            print(f"    [{i}] {c[:80]}")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
