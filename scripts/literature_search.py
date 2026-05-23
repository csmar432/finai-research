#!/usr/bin/env python3
"""
文献研究与综述生成器
====================
端到端完成：AI 检索文献 → 下载原文 → 深度解析 → 结构化摘要 → 文献综述。

DeepSeek 全程参与：
  1. 检索文献线索（列表形式）
  2. 解析论文结构化摘要（变量、模型、方法、结论）
  3. 生成文献综述

用法：
  python scripts/literature_search.py "深度学习 量化交易" --topic "金融AI"
  python scripts/literature_search.py "ESG评级" -n 5 --no-review
  python scripts/literature_search.py "强化学习 做市商" --skip-download
"""

import json
import sys
import re
import time
import textwrap
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scripts.ai_router import AI, Task
from scripts.review_layer import ReviewLayer, ReviewType, ReviewResult
from scripts.paper_reader import (
    download_from_arxiv,
    load_paper_text,
    load_paper_meta,
    PAPERS_DIR as FULLTEXT_DIR,
    META_DIR,
)

KNOWLEDGE_DIR = SCRIPT_DIR / "knowledge"
REVIEWS_DIR = KNOWLEDGE_DIR / "reviews"
REVIEWS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Step 1: 检索文献 ──────────────────────────────────

def search_papers(query: str, max_results: int = 10) -> list[dict]:
    """
    用 DeepSeek 检索文献线索。
    返回论文基本信息列表（标题、作者、年份、arXiv ID、DOI 等）。
    """
    prompt = f"""你是一位专业学术研究员。请为以下研究主题检索近5年内最相关、最重要的学术论文。

研究主题：{query}

要求：
1. 列出 {max_results} 篇核心论文
2. 优先推荐：高引用、顶级会议/期刊、知名团队的工作
3. 对于每篇论文，提供以下信息（尽量完整）：

格式：
【论文1】
标题：[论文完整标题]
作者：[第一作者 等]
年份：[发表年份]
来源：[期刊/会议名称]
arXiv ID：[如果有，格式如 2303.08774]
DOI：[如果有]
链接：[论文链接或 arXiv URL]
核心贡献：[1-2句话概括主要贡献]

请确保 arXiv ID 准确（格式为YYMM.NNNNN，如2303.08774）。"""

    print(f"\n{'='*70}")
    print(f"  Step 1/4  🔍 检索文献（DeepSeek）")
    print(f"{'='*70}")
    print(f"  主题: {query}")
    print(f"  最大结果: {max_results}")
    print()

    result = AI.chat(prompt, task=Task.LITERATURE, model="deepseek")
    print(f"  耗时: {result.latency_ms/1000:.1f}s")

    papers = _parse_search_result(result.response, query)
    print(f"  解析到 {len(papers)} 篇论文")
    return papers, result.response


def _parse_search_result(text: str, topic: str) -> list[dict]:
    """
    从 AI 返回的文本中解析论文信息。
    识别【论文N】块，提取结构化字段。
    """
    papers = []
    # 按【论文N】分割
    blocks = re.split(r"【\s*论文\s*\d+\s*】", text)
    blocks = [b.strip() for b in blocks if b.strip()]

    for block in blocks:
        paper = _parse_paper_block(block, topic)
        if paper and paper.get("title"):
            papers.append(paper)

    # 也处理旧格式（数字编号）
    if not papers:
        lines = text.split("\n")
        current = {}
        for line in lines:
            line = line.strip()
            if not line:
                if current.get("title"):
                    papers.append(current)
                    current = {}
                continue
            if re.match(r"^\d+[.、)]\s*", line) and "：" not in line[:20]:
                if current.get("title"):
                    papers.append(current)
                    current = {}
                m = re.match(r"^\d+[.、)]\s*[\"'']?(.+)", line)
                if m:
                    current["title"] = m.group(1).strip().strip('"').strip("'")
                continue
            for field, key in [
                (r"标题[:：]\s*(.+)", "title"),
                (r"作者[:：]\s*(.+)", "authors"),
                (r"年份[:：]\s*(\d{4})", "year"),
                (r"来源[:：]\s*(.+)", "venue"),
                (r"arXiv\s*ID[:：]?\s*(\d{4}\.\d{4,5}[vV]?\d*)", "arxiv_id"),
                (r"DOI[:：]\s*(.+)", "doi"),
                (r"链接[:：]\s*(.+)", "url"),
                (r"核心贡献[:：]\s*(.+)", "contribution"),
            ]:
                m = re.match(field, line, re.IGNORECASE)
                if m:
                    val = m.group(1).strip().strip('"').strip("'")
                    if key == "arxiv_id":
                        val = re.sub(r"[vV]\d+$", "", val)
                    current[key] = val
                    break
        if current.get("title"):
            papers.append(current)

    for p in papers:
        p["topic"] = topic
        p["id"] = _gen_id(p.get("title", ""))
        p["added_at"] = datetime.now().isoformat()
        p["notes"] = ""

    return papers


def _parse_paper_block(block: str, topic: str) -> dict:
    """解析单个论文块。"""
    paper = {"topic": topic}
    for field, key in [
        (r"标题[:：]\s*(.+?)(?=\n|$)", "title"),
        (r"作者[:：]\s*(.+?)(?=\n|$)", "authors"),
        (r"年份[:：]\s*(\d{4})", "year"),
        (r"来源[:：]\s*(.+?)(?=\n|$)", "venue"),
        (r"arXiv\s*ID[:：]?\s*(\d{4}\.\d{4,5})", "arxiv_id"),
        (r"DOI[:：]\s*(.+?)(?=\n|$)", "doi"),
        (r"链接[:：]\s*(.+?)(?=\n|$)", "url"),
        (r"核心贡献[:：]\s*(.+?)(?=\n|$)", "contribution"),
    ]:
        m = re.search(field, block, re.IGNORECASE | re.DOTALL)
        if m:
            paper[key] = m.group(1).strip().strip('"').strip("'")
    return paper


def _gen_id(title: str) -> str:
    """生成论文 ID。"""
    clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", title)
    return f"{clean[:8]}_{datetime.now().strftime('%m%d')}"


# ─── Step 2: 下载原文 ──────────────────────────────────

def download_papers(papers: list[dict], skip_download: bool = False) -> list[dict]:
    """下载论文原文（PDF）。"""
    print(f"\n{'='*70}")
    print(f"  Step 2/4  📥 下载论文原文")
    print(f"{'='*70}")

    results = []
    for i, paper in enumerate(papers, 1):
        arxiv_id = paper.get("arxiv_id", "").strip()
        title = paper.get("title", "未知标题")[:50]

        if not arxiv_id:
            print(f"  [{i}/{len(papers)}] ⏭ 跳过（无 arXiv ID）: {title}")
            paper["downloaded"] = False
            paper["word_count"] = 0
            results.append(paper)
            continue

        if skip_download:
            print(f"  [{i}/{len(papers)}] ⏭ 跳过下载: {title}")
            meta = load_paper_meta(arxiv_id)
            paper["downloaded"] = bool(meta)
            paper["word_count"] = meta.get("word_count", 0) if meta else 0
            results.append(paper)
            continue

        print(f"  [{i}/{len(papers)}] ⏬ {arxiv_id} — {title}")
        result = download_from_arxiv(arxiv_id)
        if "error" in result:
            print(f"           ❌ {result['error']}")
            paper["downloaded"] = False
            paper["word_count"] = 0
        else:
            print(f"           ✅ 已下载（{result.get('word_count', 0):,} 字）")
            paper["downloaded"] = True
            paper["word_count"] = result.get("word_count", 0)
        results.append(paper)
        if i < len(papers):
            time.sleep(2)

    downloaded = sum(1 for p in results if p.get("downloaded"))
    print(f"\n  下载完成: {downloaded}/{len(results)} 篇")
    return results


# ─── Step 3: 深度解析 — 结构化摘要 ─────────────────────

def analyze_papers(papers: list[dict]) -> list[dict]:
    """
    用 DeepSeek 对每篇论文生成结构化摘要：
    研究问题、变量、模型/方法、实验设置、主要结论、局限性。
    """
    print(f"\n{'='*70}")
    print(f"  Step 3/4  🧠 深度解析论文（DeepSeek）")
    print(f"{'='*70}")

    results = []
    for i, paper in enumerate(papers, 1):
        arxiv_id = paper.get("arxiv_id", "").strip()
        title = paper.get("title", "未知标题")[:50]
        has_text = False

        # 尝试加载原文
        content = ""
        if arxiv_id:
            txt_path = FULLTEXT_DIR / f"{arxiv_id}.txt"
            if txt_path.exists():
                content = txt_path.read_text(encoding="utf-8")
                has_text = len(content) > 1000

        print(f"  [{i}/{len(papers)}] 分析: {title}")
        if has_text:
            print(f"           📄 原文已加载（{len(content):,} 字）")
        else:
            print(f"           ⚠ 无原文，使用摘要信息")

        # 构建解析 prompt
        analysis = _analyze_single_paper(paper, content, has_text)
        paper["analysis"] = analysis
        results.append(paper)
        print(f"           ✅ 完成")

    analyzed = sum(1 for p in results if p.get("analysis", {}).get("research_question"))
    print(f"\n  深度解析完成: {analyzed}/{len(results)} 篇（含原文）")
    return results


def _analyze_single_paper(paper: dict, content: str, has_full_text: bool) -> dict:
    """解析单篇论文的结构化摘要。"""
    title = paper.get("title", "")
    authors = paper.get("authors", "")
    year = paper.get("year", "")
    venue = paper.get("venue", "")
    abstract = paper.get("contribution", "")
    topic = paper.get("topic", "")

    text_chunk = content[:30000] if has_full_text else ""

    prompt = f"""你是一位严谨的学术研究员。请对以下论文进行深度结构化分析。

## 论文基本信息
- 标题：{title}
- 作者：{authors}
- 年份：{year}
- 来源：{venue}
- 主题：{topic}

## 论文摘要/贡献
{abstract}

{"## 论文正文（前部）\n" + text_chunk if text_chunk else ""}

请输出以下 JSON 格式的结构化摘要（仅输出 JSON，不要其他文字）：

{{
  "research_question": "这篇论文要解决的研究问题是什么？（1-2句话）",
  "independent_variables": ["自变量/输入变量列表"],
  "dependent_variables": "因变量/评价指标（如准确率、收益率、夏普比率等）",
  "model_method": "使用的核心模型或方法（如 LSTM、Transformer、强化学习等）",
  "data_source": "数据集或数据来源（如 A股 日线数据、Wind 数据库等）",
  "sample_period": "样本时间段（如 2015-2020）",
  "main_conclusions": ["主要结论列表，3-5条"],
  "limitations": ["论文的主要局限性，2-3条"],
  "key_findings": "最关键的发现（1句话）"
}}"""

    try:
        result = AI.chat(prompt, task=Task.LITERATURE, model="deepseek",
                         temperature=0.3, max_tokens=2048)
        text = result.response.strip()

        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = _parse_analysis_text(text)
    except json.JSONDecodeError:
        analysis = _parse_analysis_text(text)
    except Exception as e:
        analysis = {
            "research_question": "解析失败",
            "independent_variables": [],
            "dependent_variables": "未知",
            "model_method": "未知",
            "data_source": "未知",
            "sample_period": "未知",
            "main_conclusions": [],
            "limitations": [f"AI 分析失败: {e}"],
            "key_findings": "解析失败",
        }

    return analysis


def _parse_analysis_text(text: str) -> dict:
    """从纯文本中提取分析字段。"""
    def extract(key: str) -> str:
        patterns = [
            rf"{key}[:：]\s*(.+?)(?=\n[A-Z]|$)",
            rf'"{key}"\s*:\s*(.+?)(?=,\s*"|$)',
        ]
        for p in patterns:
            m = re.search(p, text, re.DOTALL)
            if m:
                return m.group(1).strip().strip('"').strip("'")
        return ""

    def extract_list(key: str) -> list:
        text_section = ""
        patterns = [
            rf"{key}[:：]\s*([\s\S]*?)(?=\n[A-Z]{{2}}|Limitations|\"limitations\"|$)",
        ]
        for p in patterns:
            m = re.search(p, text, re.DOTALL)
            if m:
                text_section = m.group(1)
                break
        items = re.findall(r"[-*\d]+\.\s*(.+?)(?=\n|$)", text_section)
        if not items:
            items = [l.strip() for l in text_section.split("\n") if l.strip() and len(l.strip()) > 10]
        return items[:5]

    return {
        "research_question": extract("research_question"),
        "independent_variables": extract_list("independent_variables"),
        "dependent_variables": extract("dependent_variables"),
        "model_method": extract("model_method"),
        "data_source": extract("data_source"),
        "sample_period": extract("sample_period"),
        "main_conclusions": extract_list("main_conclusions"),
        "limitations": extract_list("limitations"),
        "key_findings": extract("key_findings"),
    }


# ─── Step 4: 生成文献综述 ──────────────────────────────

def generate_review(papers: list[dict], topic: str) -> str:
    """用 DeepSeek 生成文献综述。"""
    print(f"\n{'='*70}")
    print(f"  Step 4/4  📝 生成文献综述（DeepSeek）")
    print(f"{'='*70}")

    papers_with_analysis = [p for p in papers if p.get("analysis", {}).get("research_question")]

    if not papers_with_analysis:
        print("  ⚠ 没有足够的结构化分析，跳过综述生成")
        return ""

    print(f"  基于 {len(papers_with_analysis)} 篇论文生成综述...")
    start = time.time()

    papers_text = []
    for i, p in enumerate(papers_with_analysis, 1):
        a = p.get("analysis", {})
        papers_text.append(f"""### 论文{i}: {p.get('title', '未知')}
- 作者: {p.get('authors', '未知')} ({p.get('year', '?')})
- 来源: {p.get('venue', '未知')}
- 研究问题: {a.get('research_question', '未知')}
- 自变量: {', '.join(a.get('independent_variables', [])[:3]) if a.get('independent_variables') else '未知'}
- 因变量: {a.get('dependent_variables', '未知')}
- 模型方法: {a.get('model_method', '未知')}
- 数据来源: {a.get('data_source', '未知')} ({a.get('sample_period', '')})
- 主要结论:
  - {'; '.join(a.get('main_conclusions', [])[:3]) if a.get('main_conclusions') else '未知'}
- 局限性: {', '.join(a.get('limitations', [])[:2]) if a.get('limitations') else '未知'}
""")

    prompt = f"""你是一位专业学术研究员。请为以下研究主题撰写文献综述。

## 研究主题
{topic}

## 待综述论文
{''.join(papers_text[:8])}

请按以下结构撰写文献综述：

### 一、研究主题概述
简述该领域的研究背景和重要性。

### 二、研究方法对比
对比各论文使用的方法、技术路线有何异同。

### 三、核心发现总结
归纳各论文的主要发现，找出共识和分歧点。

### 四、变量与指标梳理
总结该领域常用的变量体系（自变量、因变量、控制变量）。

### 五、研究局限性
指出当前研究的共同不足之处。

### 六、未来研究方向
基于现有研究的空白，提出有价值的未来研究方向。

### 七、对你研究的启发
结合上述分析，说明该综述对你具体研究的指导意义。

要求：
1. 语言专业、学术，逻辑清晰
2. 引用原文时请标注论文序号，如 [1]、[2]
3. 字数 800-1500 字
4. 中文撰写"""

    result = AI.chat(prompt, task=Task.LITERATURE, model="deepseek",
                     temperature=0.5, max_tokens=4096)
    draft_review = result.response.strip()
    elapsed = time.time() - start
    print(f"  综述草稿生成完成，耗时 {elapsed:.1f}s")

    # ── Step 5: DeepSeek 审查 + GPT 修复 ─────────────────
    print(f"\n  🔍 DeepSeek 审查中...")
    review_layer = ReviewLayer(use_cache=True)
    review_result = review_layer.review_and_fix(
        content=draft_review,
        content_type=ReviewType.LITERATURE_REVIEW,
        context={"topic": topic},
    )

    print(f"  审查评分: {review_result.overall_score}/10  |  发现问题: {len(review_result.issues)} 项")
    if review_result.issues:
        for issue in review_result.issues[:5]:
            print(f"    - {issue[:80]}")
        print(f"\n  ✏️  GPT-5.5 修复中...")
        final_review = review_result.fixed_content
        total_time = time.time() - start
        print(f"  修复完成，总耗时 {total_time:.1f}s")
    else:
        final_review = draft_review
        print(f"  综述质量良好，无需修复")

    print(f"  字数: {len(final_review)} 字")
    return final_review


# ─── 保存结果 ──────────────────────────────────────────

def save_results(query: str, topic: str, papers: list[dict],
                 raw_search: str, review: str):
    """保存所有结果到知识库。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "_", topic)[:20]
    review_file = REVIEWS_DIR / f"{safe_topic}_{timestamp}.md"

    # 保存文献综述
    if review:
        review_content = f"""# 📚 文献综述

**主题**: {topic}
**检索词**: {query}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**论文数量**: {len(papers)} 篇

---

{review}

---

## 附：论文结构化摘要

"""
        for i, p in enumerate(papers, 1):
            title = p.get("title", "未知标题")
            a = p.get("analysis", {})
            arxiv_id = p.get("arxiv_id", "")
            url = p.get("url", f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")

            review_content += f"""
### [{i}] {title}
**作者**: {p.get('authors', '未知')} | **年份**: {p.get('year', '?')} | **来源**: {p.get('venue', '未知')}

| 字段 | 内容 |
|------|------|
| arXiv ID | {arxiv_id or '无'} |
| 研究问题 | {a.get('research_question', '未知')} |
| 自变量 | {', '.join(a.get('independent_variables', [])[:5]) if a.get('independent_variables') else '未知'} |
| 因变量 | {a.get('dependent_variables', '未知')} |
| 模型方法 | {a.get('model_method', '未知')} |
| 数据来源 | {a.get('data_source', '未知')} ({a.get('sample_period', '')}) |
| 主要结论 | {'; '.join(a.get('main_conclusions', [])[:3]) if a.get('main_conclusions') else '未知'} |
| 局限性 | {', '.join(a.get('limitations', [])[:2]) if a.get('limitations') else '未知'} |
| 核心发现 | {a.get('key_findings', '未知')} |

链接: {url}
"""
        review_file.write_text(review_content, encoding="utf-8")
        print(f"\n💾 文献综述已保存: {review_file}")

    # 保存原始搜索结果
    raw_file = KNOWLEDGE_DIR / "papers" / f"raw_search_{safe_topic}_{timestamp}.txt"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(raw_search, encoding="utf-8")

    # 更新 index
    index_file = KNOWLEDGE_DIR / "papers" / "index.json"
    index = {"papers": [], "last_updated": datetime.now().isoformat()}
    if index_file.exists():
        try:
            index = json.loads(index_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    for paper in papers:
        # 检查是否已存在
        exists = any(
            p.get("title") == paper.get("title")
            for p in index["papers"]
        )
        if not exists:
            index["papers"].append(paper)

    index["last_updated"] = datetime.now().isoformat()
    # 原子写入：先写临时文件再 rename（防止并发损坏）
    tmp = index_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(index_file)

    return str(review_file)


# ─── 主流程 ─────────────────────────────────────────────

def research(query: str, topic: str = "", max_results: int = 10,
            skip_download: bool = False, no_review: bool = False):
    """
    完整文献研究流程。

    Step 1: DeepSeek 检索文献
    Step 2: 下载论文原文（arXiv）
    Step 3: DeepSeek 深度解析（结构化摘要）
    Step 4: DeepSeek 生成文献综述
    """
    if not topic:
        topic = query.strip()

    print(f"\n{'='*70}")
    print(f"  📚 文献研究与综述生成")
    print(f"  主题: {topic}")
    print(f"{'='*70}")

    # Step 1: 检索
    papers, raw_search = search_papers(query, max_results=max_results)
    if not papers:
        print("\n❌ 未能检索到论文，请尝试不同的关键词。")
        return

    # Step 2: 下载
    papers = download_papers(papers, skip_download=skip_download)

    # Step 3: 深度解析
    papers = analyze_papers(papers)

    # Step 4: 文献综述
    review = ""
    if not no_review:
        review = generate_review(papers, topic)

    # 保存
    review_file = save_results(query, topic, papers, raw_search, review)

    # 打印摘要
    print(f"\n{'='*70}")
    print(f"  📋 研究摘要")
    print(f"{'='*70}")
    for i, p in enumerate(papers, 1):
        a = p.get("analysis", {})
        title = p.get("title", "未知标题")[:50]
        method = a.get("model_method", "—")
        rq = a.get("research_question", "")[:60]
        conclusions = a.get("main_conclusions", [])
        print(f"\n  [{i}] {title}")
        print(f"      方法: {method}")
        if rq:
            print(f"      问题: {rq}...")
        if conclusions:
            print(f"      结论: {conclusions[0][:70]}...")

    print(f"\n{'='*70}")
    print(f"  ✅ 完成！")
    print(f"  文献综述: {review_file}")
    print(f"{'='*70}")

    return papers, review


# ─── CLI ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="文献研究与综述生成 — 检索 → 下载 → 解析 → 综述",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="检索关键词/研究主题")
    parser.add_argument("--topic", "-t", help="保存的主题名称（默认用 query）")
    parser.add_argument("--max-results", "-n", type=int, default=10, help="最大论文数")
    parser.add_argument("--skip-download", action="store_true",
                        help="跳过 PDF 下载，直接解析摘要信息")
    parser.add_argument("--no-review", action="store_true",
                        help="不生成文献综述")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        print("\n--- 示例 ---")
        print("  python scripts/literature_search.py '深度学习 量化交易'")
        print("  python scripts/literature_search.py '强化学习 做市商' -n 8")
        print("  python scripts/literature_search.py 'ESG评级' --skip-download")
        print("  python scripts/literature_search.py '因子投资' --no-review")
        return

    research(
        query=args.query,
        topic=args.topic or "",
        max_results=args.max_results,
        skip_download=args.skip_download,
        no_review=args.no_review,
    )


if __name__ == "__main__":
    main()
