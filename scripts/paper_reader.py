#!/usr/bin/env python3
"""
论文阅读器
==========
下载论文 → 提取内容 → AI 分析 → 随时查证

功能：
- 从 arXiv 下载论文 PDF
- 从 Semantic Scholar 获取论文元信息 + 摘要
- 提取 PDF 全文文本
- AI 摘要论文
- AI 问答（针对论文内容）
- 生成论文阅读笔记
- RAG 模式：让 AI 基于论文内容回答问题（可引用原文）

使用方式：
  python scripts/paper_reader.py download "2303.08774"          # 下载 arXiv 论文
  python scripts/paper_reader.py summarize "2303.08774"          # AI 摘要
  python scripts/paper_reader.py ask "2303.08774" "这篇论文的创新点是什么？"  # 问答
  python scripts/paper_reader.py read "2303.08774"               # 读取正文（前2000字）
  python scripts/paper_reader.py batch-download "2303.08774" "2201.00001"  # 批量下载
"""

import json
import sys
import re
import os
import time
import textwrap
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# ─── 配置 ────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.parent
PAPERS_DIR = SCRIPT_DIR / "knowledge" / "papers_fulltext"  # 存放原文
META_DIR = SCRIPT_DIR / "knowledge" / "papers_meta"          # 存放元信息
PAPERS_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)

# ─── 辅助函数 ────────────────────────────────────────────

def arxiv_id_from_url(url_or_id: str) -> str:
    """从 URL 或纯 ID 中提取 arXiv ID。"""
    m = re.search(r"(\d{4}\.\d{4,5}(v\d+)?)", url_or_id)
    if m:
        return m.group(1)
    return url_or_id.strip()


def sanitize_filename(name: str) -> str:
    """清理文件名。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:80]


# ─── 论文下载 ────────────────────────────────────────────

def download_from_arxiv(arxiv_id: str) -> dict:
    """
    从 arXiv 下载论文 PDF 并提取文本。
    返回论文元信息 + 全文内容。
    """
    import urllib.request
    import urllib.error

    arxiv_id = arxiv_id_from_url(arxiv_id)

    # 1. 获取元信息（Atom feed）
    atom_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        with urllib.request.urlopen(atom_url, timeout=30) as resp:
            atom_xml = resp.read().decode("utf-8")
    except Exception as e:
        return {"error": f"无法连接 arXiv API: {e}"}

    # 2. 解析元信息（arXiv API 返回 Atom XML，无需命名空间前缀）
    meta = {
        "arxiv_id": arxiv_id,
        "title": "",
        "authors": [],
        "abstract": "",
        "published": "",
        "categories": [],
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
    }

    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(atom_xml)
        # arXiv Atom feed：根元素本身有默认命名空间，用 local-name() 跨命名空间匹配
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

            if tag == "entry" and not meta["title"]:
                # 解析 entry 子元素
                for child in elem:
                    ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ctag == "title" and not meta["title"]:
                        meta["title"] = (child.text or "").strip().replace("\n", " ")
                    elif ctag == "summary":
                        meta["abstract"] = (child.text or "").strip().replace("\n", " ")
                    elif ctag == "published":
                        meta["published"] = (child.text or "").strip()
                    elif ctag == "author":
                        for grandchild in child:
                            gtag = grandchild.tag.split("}")[-1] if "}" in grandchild.tag else grandchild.tag
                            if gtag == "name" and grandchild.text:
                                meta["authors"].append(grandchild.text.strip())
                    elif ctag == "category":
                        term = child.get("term", "")
                        if term:
                            meta["categories"].append(term)
    except Exception as e:
        return {"error": f"XML 解析失败: {e}"}

    # 3. 下载 PDF（带重试）
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    pdf_path = PAPERS_DIR / f"{arxiv_id}.pdf"
    txt_path = PAPERS_DIR / f"{arxiv_id}.txt"

    def _download_pdf(url: str, path: Path) -> bool:
        """下载 PDF，带 3 次重试和指数退避。"""
        import urllib.request
        import urllib.error

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; paper_reader/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    with open(path, "wb") as f:
                        f.write(resp.read())
                return True
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    import time
                    wait = (attempt + 1) * 5
                    print(f"  ⚠ arXiv 请求受限，等待 {wait}s 后重试...")
                    time.sleep(wait)
                else:
                    raise
            except Exception as e:
                if attempt < 2:
                    import time
                    print(f"  ⚠ 下载失败，{attempt+1}s 后重试: {e}")
                    time.sleep(attempt + 1)
                else:
                    raise
        return False

    try:
        if not pdf_path.exists():
            print(f"  ↓ 下载 PDF: {pdf_url}")
            ok = _download_pdf(pdf_url, pdf_path)
            if ok:
                print(f"  ✓ PDF 已保存: {pdf_path.name}")
            else:
                return {"error": f"PDF 下载失败（已重试 3 次）"}
        else:
            print(f"  ↺ PDF 已存在，跳过下载")
    except urllib.error.HTTPError:
        return {"error": f"arXiv 上未找到论文: {arxiv_id}"}
    except Exception as e:
        return {"error": f"PDF 下载失败: {e}"}

    # 4. 提取文本（使用 pdfplumber，替代已废弃的 PyPDF2）
    if not txt_path.exists():
        try:
            import pdfplumber

            with pdfplumber.open(str(pdf_path)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
            full_text = "\n\n".join(pages)
            txt_path.write_text(full_text, encoding="utf-8")
            print(f"  ✓ 文本已提取: {txt_path.name} ({len(full_text)} 字)")
        except ImportError:
            print(f"  ⚠ pdfplumber 未安装，跳过文本提取（pip install pdfplumber）")
            full_text = ""
        except Exception as e:
            print(f"  ⚠ 文本提取失败: {e}")
            full_text = ""
    else:
        full_text = txt_path.read_text(encoding="utf-8")
        print(f"  ↺ 文本已存在: {txt_path.name} ({len(full_text)} 字)")

    # 5. 保存元信息
    meta_path = META_DIR / f"{arxiv_id}.json"
    meta["downloaded_at"] = datetime.now().isoformat()
    meta["pdf_path"] = str(pdf_path)
    meta["txt_path"] = str(txt_path)
    meta["word_count"] = len(full_text)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {
        "arxiv_id": arxiv_id,
        "title": meta["title"],
        "authors": meta["authors"],
        "abstract": meta["abstract"],
        "pdf_url": meta["pdf_url"],
        "word_count": len(full_text),
        "pdf_saved": str(pdf_path),
        "text_saved": str(txt_path),
    }


def get_from_semantic_scholar(arxiv_id: str = "", title: str = "") -> dict:
    """
    从 Semantic Scholar API 获取论文元信息和摘要。
    结果缓存到本地，24小时内不重复请求。
    """
    import urllib.request
    import urllib.error
    import time

    if not arxiv_id and not title:
        return {"error": "需要提供 arXiv ID 或论文标题"}

    # 检查本地缓存（24小时）
    cache_dir = PAPERS_DIR / ".semantic_cache"
    cache_dir.mkdir(exist_ok=True)
    cache_key = arxiv_id if arxiv_id else hashlib.md5(title.encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:  # 24小时
            return json.loads(cache_file.read_text(encoding="utf-8"))

    # 请求 API（带速率限制）
    time.sleep(1.5)  # 避免触发限流
    query = arxiv_id if arxiv_id else title
    api_url = f"https://api.semanticscholar.org/graph/v1/paper/{query}?fields=title,authors,year,abstract,venue,citationCount,openAccessPdf"

    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "paper_reader/1.0 (academic research tool)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = {
                "title": data.get("title", ""),
                "authors": [a["name"] for a in data.get("authors", [])],
                "year": data.get("year", ""),
                "abstract": data.get("abstract", ""),
                "venue": data.get("venue", ""),
                "citations": data.get("citationCount", 0),
                "pdf_url": (data.get("openAccessPdf") or {}).get("url", ""),
            }
            # 写入本地缓存
            try:
                cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass  # 缓存写入失败不影响主流程
            return result
    except urllib.error.HTTPError:
        return {"error": f"Semantic Scholar 上未找到论文"}
    except Exception as e:
        return {"error": f"Semantic Scholar API 请求失败: {e}"}


# ─── 内容读取 ────────────────────────────────────────────

def load_paper_text(arxiv_id: str, max_chars: int = 50000) -> str:
    """加载论文全文（限制 token 范围）。"""
    txt_path = PAPERS_DIR / f"{arxiv_id}.txt"
    if not txt_path.exists():
        return ""
    text = txt_path.read_text(encoding="utf-8")
    return text[:max_chars]


def load_paper_meta(arxiv_id: str) -> dict:
    """加载论文元信息。"""
    meta_path = META_DIR / f"{arxiv_id}.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {}


# ─── AI 分析 ─────────────────────────────────────────────

def summarize_with_ai(arxiv_id: str, detail: str = "medium") -> str:
    """让 AI 摘要论文。"""
    sys.path.insert(0, str(SCRIPT_DIR))
    from scripts.ai_router import AI, Task

    meta = load_paper_meta(arxiv_id)
    abstract = meta.get("abstract", "")
    title = meta.get("title", "")
    authors = meta.get("authors", [])
    word_count = meta.get("word_count", 0)

    text = load_paper_text(arxiv_id, max_chars=30000)
    full_content = text if text else abstract

    if not full_content:
        return f"[错误] 论文 {arxiv_id} 未找到本地原文，请先下载。"

    prompt = f"""你是一位专业的研究论文审稿人。请对以下学术论文进行{detail}程度的摘要。

## 论文信息
- 标题：{title}
- 作者：{", ".join(authors) if authors else "未知"}
- 全文字数：约 {word_count} 字

## 论文正文（部分）
---
{full_content[:25000]}
---

请按以下结构输出摘要：
1. **研究问题**：这篇论文要解决什么问题？
2. **核心方法**：提出了什么方法？关键技术是什么？
3. **主要贡献**：相比已有工作有何创新？
4. **实验结果**：关键数据和结论是什么？
5. **局限性**：存在哪些不足？
6. **对你的研究的启发**：有哪些可以借鉴的地方？
"""

    from scripts.review_layer import ReviewLayer, ReviewType

    if detail == "short":
        prompt = f"""请用 200 字以内概括以下论文的核心贡献：

标题：{title}
作者：{", ".join(authors[:3])}{"等" if len(authors) > 3 else ""}
摘要：{abstract}
正文（部分）：{full_content[:15000]}"""
        result = AI.chat(prompt, task=Task.CODE_ANALYSIS, temperature=0.3)
        return result.response

    # 标准摘要（含 DeepSeek 审查 + GPT 修复）
    result = AI.chat(prompt, task=Task.CODE_ANALYSIS, temperature=0.3)
    draft = result.response.strip()
    print(f"  摘要草稿完成（{len(draft)} 字）")

    print(f"  🔍 DeepSeek 审查摘要...")
    review_layer = ReviewLayer(use_cache=True)
    review_result = review_layer.review_and_fix(
        content=draft,
        content_type=ReviewType.PAPER_SUMMARY,
        context={"topic": title},
    )
    print(f"  审查评分: {review_result.overall_score}/10  |  问题: {len(review_result.issues)} 项")
    if review_result.issues:
        for issue in review_result.issues[:3]:
            print(f"    - {issue[:80]}")
        print(f"  ✏️  GPT-5.5 修复摘要...")
    return review_result.fixed_content


def ask_paper_with_ai(arxiv_id: str, question: str) -> str:
    """
    RAG 模式：基于论文原文回答问题。
    把论文内容作为上下文，让 AI 引用原文回答。
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    from scripts.ai_router import AI, Task

    meta = load_paper_meta(arxiv_id)
    title = meta.get("title", "")
    authors = meta.get("authors", [])
    abstract = meta.get("abstract", "")
    text = load_paper_text(arxiv_id, max_chars=40000)
    full_content = text if text else abstract

    if not full_content:
        return f"[错误] 论文 {arxiv_id} 未找到本地原文，请先下载。"

    prompt = f"""你是一位严谨的学术研究员。用户正在阅读以下论文，请基于论文原文回答问题。

## 论文信息
- 标题：{title}
- 作者：{", ".join(authors) if authors else "未知"}
- arXiv ID：{arxiv_id}

## 论文原文（完整）
---
{full_content}
---

## 用户问题
{question}

## 回答要求
1. 必须基于论文原文回答，不要编造内容
2. 引用原文时用「"..."」标注原文句子
3. 如果论文没有提到相关内容，直接说明"论文中没有涉及这个问题"
4. 如果需要补充背景知识，请明确说明这是基于常识而非论文内容
"""

    result = AI.chat(prompt, task=Task.CODE_ANALYSIS, temperature=0.3)
    return result.response


def compare_papers_with_ai(arxiv_ids: list[str], question: str) -> str:
    """对比多篇论文。"""
    sys.path.insert(0, str(SCRIPT_DIR))
    from scripts.ai_router import AI, Task

    papers_content = []
    for aid in arxiv_ids:
        meta = load_paper_meta(aid)
        text = load_paper_text(aid, max_chars=10000)
        papers_content.append({
            "arxiv_id": aid,
            "title": meta.get("title", ""),
            "authors": meta.get("authors", []),
            "abstract": meta.get("abstract", ""),
            "text": text,
        })

    combined = "\n\n".join([
        f"=== 论文 {i+1}: {p['title']} (arXiv: {p['arxiv_id']}) ===\n"
        f"作者: {', '.join(p['authors'])}\n"
        f"摘要: {p['abstract']}\n"
        f"正文: {p['text']}"
        for i, p in enumerate(papers_content)
    ])

    prompt = f"""你是一位学术研究员。请对比以下多篇论文，并回答用户的问题。

=== 待对比论文 ===
{combined[:30000]}

=== 用户问题 ===
{question}

=== 回答要求 ===
1. 基于原文进行对比分析
2. 指出各论文的异同点
3. 引用原文支持你的分析
"""

    result = AI.chat(prompt, task=Task.CODE_ANALYSIS, temperature=0.3)
    return result.response


# ─── 笔记生成 ────────────────────────────────────────────

def generate_reading_notes(arxiv_id: str) -> str:
    """自动生成论文阅读笔记。"""
    summary = summarize_with_ai(arxiv_id, detail="medium")
    meta = load_paper_meta(arxiv_id)
    title = meta.get("title", "")
    authors = meta.get("authors", [])
    year = meta.get("published", "")[:4] if meta.get("published") else ""

    note_path = META_DIR / f"{arxiv_id}_notes.md"
    note_content = f"""# 📄 论文阅读笔记

## 基本信息
- **标题**: {title}
- **作者**: {", ".join(authors) if authors else "未知"}
- **年份**: {year}
- **arXiv ID**: {arxiv_id}
- **阅读时间**: {datetime.now().strftime('%Y-%m-%d')}

---

## 摘要

{summary}

---

## 我的思考

<!-- 在这里写下你的思考、疑问、收获 -->



## 可引用观点

<!-- 从原文中摘录可引用的关键句子 -->



## 与我的研究的相关性

<!-- 这篇论文对你的研究有什么帮助 -->



## 下一步

- [ ] 精读第 X 节
- [ ] 复现文中的实验
- [ ] 查找相关论文
- [ ] 与 XX 论文对比
"""

    note_path.write_text(note_content, encoding="utf-8")
    return str(note_path), note_content


# ─── CLI 命令 ────────────────────────────────────────────

def cmd_download(args):
    """下载论文。"""
    arxiv_ids = [arxiv_id_from_url(a) for a in args.arxiv_ids]

    print(f"\n📥 开始下载 {len(arxiv_ids)} 篇论文...")
    print("=" * 60)

    results = []
    for i, aid in enumerate(arxiv_ids, 1):
        print(f"\n[{i}/{len(arxiv_ids)}] 处理: {aid}")
        result = download_from_arxiv(aid)
        results.append(result)
        if i < len(arxiv_ids):
            time.sleep(3)  # 避免过快请求

    print("\n" + "=" * 60)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r.get('arxiv_id', r)}: {r['error']}")
        else:
            print(f"  ✅ {r['title'][:60]}")
            print(f"     arXiv: {r['arxiv_id']} | {r['word_count']:,} 字")

    return results


def cmd_summarize(args):
    """AI 摘要论文。"""
    for raw_aid in args.arxiv_ids:
        aid = arxiv_id_from_url(raw_aid)
        print(f"\n📄 摘要论文: {aid}")
        print("=" * 60)
        summary = summarize_with_ai(aid, detail=args.detail)
        print(summary)

        if args.save:
            _, note = generate_reading_notes(aid)
            note_path = META_DIR / f"{aid}_notes.md"
            note_path.write_text(note + f"\n\n---\n## AI 摘要\n\n{summary}", encoding="utf-8")
            print(f"\n💾 笔记已保存: {note_path}")


def cmd_ask(args):
    """AI 问答。"""
    for raw_aid in args.arxiv_ids:
        aid = arxiv_id_from_url(raw_aid)
        meta = load_paper_meta(aid)
        if not meta:
            print(f"\n⚠ 论文 {aid} 未找到，请先下载：")
            print(f"   python scripts/paper_reader.py download {aid}")
            continue

        print(f"\n📖 论文: {meta.get('title', aid)}")
        print(f"   字数: {meta.get('word_count', 0):,} 字")
        print("=" * 60)

        question_to_ask = args.question or ""
        if question_to_ask:
            print(f"\n❓ {question_to_ask}")
            print("-" * 60)
            answer = ask_paper_with_ai(aid, question_to_ask)
            print(answer)

        if args.interactive:
            print("\n💬 进入问答模式（输入 quit 退出）")
            while True:
                try:
                    q = input("\n❓ 你: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n已退出。")
                    break
                if q.lower() in ("quit", "q", "exit"):
                    break
                if not q:
                    continue
                print("\n🤖 AI:")
                answer = ask_paper_with_ai(aid, q)
                print(textwrap.indent(answer, "   "))


def cmd_read(args):
    """读取论文正文。"""
    for raw_aid in args.arxiv_ids:
        aid = arxiv_id_from_url(raw_aid)
        text = load_paper_text(aid, max_chars=args.max_chars)
        meta = load_paper_meta(aid)

        if not text:
            print(f"⚠ 论文 {aid} 未找到本地文本，请先下载。")
            if meta:
                print(f"   摘要: {meta.get('abstract', '')[:500]}")
            continue

        title = meta.get("title", aid)
        authors = ", ".join(meta.get("authors", [])[:3])
        print(f"\n📄 {title}")
        print(f"   作者: {authors}")
        print(f"   显示字数: {len(text):,} / {meta.get('word_count', 0):,}")
        print("=" * 60)
        print(text[:args.max_chars])
        if len(text) > args.max_chars:
            print(f"\n... (还有 {len(text) - args.max_chars:,} 字未显示，用 --max-chars 调整)")


def cmd_compare(args):
    """对比多篇论文。"""
    arxiv_ids = [arxiv_id_from_url(a) for a in args.arxiv_ids]
    print(f"\n🔍 对比 {len(arxiv_ids)} 篇论文...")
    print("=" * 60)
    result = compare_papers_with_ai(arxiv_ids, args.question)
    print(result)


def cmd_notes(args):
    """生成阅读笔记。"""
    for raw_aid in args.arxiv_ids:
        aid = arxiv_id_from_url(raw_aid)
        note_path, _ = generate_reading_notes(aid)
        print(f"✅ 笔记模板已生成: {note_path}")


def cmd_list(args):
    """列出已下载的论文。"""
    files = sorted(META_DIR.glob("*.json"))
    if not files:
        print("📭 还没有下载任何论文。")
        print("   下载第一篇：python scripts/paper_reader.py download 2303.08774")
        return

    print(f"\n📚 已下载论文（共 {len(files)} 篇）")
    print("-" * 70)
    for f in files:
        meta = json.loads(f.read_text(encoding="utf-8"))
        title = meta.get("title", "未知标题")
        authors = ", ".join(meta.get("authors", [])[:2])
        word_count = meta.get("word_count", 0)
        downloaded = meta.get("downloaded_at", "")[:10]
        arxiv_id = meta.get("arxiv_id", f.stem)
        print(f"\n  [{arxiv_id}] {title[:50]}")
        print(f"     {authors}{'等' if len(meta.get('authors', [])) > 2 else ''} | {word_count:,} 字 | {downloaded}")


# ─── 主入口 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="论文阅读器 — 下载、摘要、问答、笔记",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # download
    p = subparsers.add_parser("download", help="从 arXiv 下载论文")
    p.add_argument("arxiv_ids", nargs="+", help="arXiv ID（如 2303.08774）")

    # summarize
    p = subparsers.add_parser("summarize", help="AI 摘要论文")
    p.add_argument("arxiv_ids", nargs="+", help="arXiv ID")
    p.add_argument("--detail", choices=["short", "medium", "full"], default="medium",
                    help="摘要详细程度")
    p.add_argument("--save", "-s", action="store_true", help="保存摘要到笔记文件")

    # ask
    p = subparsers.add_parser("ask", help="基于论文内容提问")
    p.add_argument("arxiv_ids", nargs="+", help="arXiv ID")
    p.add_argument("--question", "-q", dest="question", default=None,
                    help="问题（省略则进入交互模式）")
    p.add_argument("--interactive", "-i", action="store_true",
                    help="交互式问答")

    # read
    p = subparsers.add_parser("read", help="读取论文正文")
    p.add_argument("arxiv_ids", nargs="+", help="arXiv ID")
    p.add_argument("--max-chars", "-n", type=int, default=5000,
                    help="最多显示字数（默认5000）")

    # compare
    p = subparsers.add_parser("compare", help="对比多篇论文")
    p.add_argument("arxiv_ids", nargs="+", help="要对比的 arXiv ID（至少2个）")
    p.add_argument("--question", "-q", dest="question", required=True,
                    help="对比问题，如：这些论文的方法有何不同？")

    # notes
    p = subparsers.add_parser("notes", help="生成阅读笔记模板")
    p.add_argument("arxiv_ids", nargs="+", help="arXiv ID")

    # list
    p = subparsers.add_parser("list", help="列出已下载的论文")

    args = parser.parse_args()

    if args.command == "download":
        cmd_download(args)
    elif args.command == "summarize":
        cmd_summarize(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "read":
        cmd_read(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "notes":
        cmd_notes(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()
        print("\n--- 示例 ---")
        print("  python scripts/paper_reader.py list                          # 列出已下载")
        print("  python scripts/paper_reader.py download 2303.08774            # 下载论文")
        print("  python scripts/paper_reader.py read 2303.08774 -n 3000       # 读正文")
        print("  python scripts/paper_reader.py summarize 2303.08774           # AI 摘要")
        print("  python scripts/paper_reader.py ask 2303.08774 '创新点？'      # 问答")
        print("  python scripts/paper_reader.py ask 2303.08774 -i             # 交互问答")
        print("  python scripts/paper_reader.py notes 2303.08774              # 生成笔记模板")
        print("  python scripts/paper_reader.py compare 2303.08774 2201.00001 '方法有何不同？'")


if __name__ == "__main__":
    main()
