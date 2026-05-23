#!/usr/bin/env python3
"""
文献管理器
==========
自动保存、检索、管理 AI 检索到的论文文献。

功能：
- 保存检索结果为 JSON / Markdown 格式
- 按主题/时间组织文献库
- 生成 BibTeX 引用格式
- 搜索已有文献
- 导出阅读笔记

使用方式：
  python scripts/literature_manager.py search "深度学习 量化交易"
  python scripts/literature_manager.py list
  python scripts/literature_manager.py show <paper_id>
  python scripts/literature_manager.py export bibtex
"""

import json
import os
import re
import sys
import textwrap
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ─── Memory Integration ────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.parent
KNOWLEDGE_DIR = SCRIPT_DIR / "knowledge"
PAPERS_DIR = KNOWLEDGE_DIR / "papers"
NOTES_DIR = KNOWLEDGE_DIR / "notes"
INDEX_FILE = PAPERS_DIR / "index.json"


# ─── Memory Integration ────────────────────────────────────────────────

_memory: "ResearchMemory | None" = None
_memory_short_term: deque = deque(maxlen=20)


def set_memory(memory: "ResearchMemory | None"):
    """Inject a ResearchMemory instance for long-term knowledge integration."""
    global _memory
    _memory = memory
    if memory is not None:
        _push_to_memory("初始化文献管理器", {"status": "memory_connected"}, ["set_memory"])


def _push_to_memory(task: str, result: Any, tools: list[str]):
    """Push a literature operation to the memory short-term layer."""
    if _memory is None:
        return
    _memory.push(task, result, {"tools": tools, "type": "literature"})


# ─── 索引管理 ────────────────────────────────────────────

def ensure_dirs():
    """确保目录存在。"""
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump({"papers": [], "last_updated": None}, f, ensure_ascii=False, indent=2)


def load_index() -> dict:
    """加载索引文件（含损坏容错）。"""
    ensure_dirs()
    try:
        with open(INDEX_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        import warnings
        warnings.warn(f"索引文件损坏或读取失败，创建新索引: {e}", stacklevel=2)
        return {"papers": [], "last_updated": None}


def save_index(index: dict):
    """原子写入索引文件（先写临时文件再 rename，防止并发损坏）。"""
    index["last_updated"] = datetime.now().isoformat()
    tmp = INDEX_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        tmp.rename(INDEX_FILE)  # atomic on POSIX
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"写入索引文件失败: {e}") from e


def generate_id(title: str) -> str:
    """根据标题生成简短 ID。"""
    clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", title)
    prefix = clean[:6]
    timestamp = datetime.now().strftime("%m%d")
    return f"{prefix}_{timestamp}"


# ─── 论文解析 ────────────────────────────────────────────

def parse_paper_from_text(text: str, topic: str = "") -> list[dict]:
    """
    从 AI 返回的文本中解析论文信息。
    支持多种格式：Markdown 列表、纯文本描述等。
    """
    papers = []

    lines = text.strip().split("\n")
    current = {}

    for line in lines:
        line = line.strip()
        if not line:
            if current and "title" in current:
                papers.append(current.copy())
                current = {}
            continue

        # 匹配标题行
        title_patterns = [
            r"^\d+[.、)]\s*[\*\[\]◆]?\s*[\"'']?(.+?)(?:[\"'']?\s*$)",  # 1. "标题"
            r"^\*\*标题[:：]?\s*\*\*(.+)",                           # **标题:** xxx
            r"^[-•*]\s*[\"'']?(.+?)(?:[\"'']?$)",                    # - "xxx"
            r"^#{1,3}\s*(.+)",                                        # # 标题
        ]

        matched = False
        for pattern in title_patterns:
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                if current and "title" in current:
                    papers.append(current.copy())
                    current = {}
                current["title"] = m.group(1).strip().strip('"').strip("'").strip("**")
                matched = True
                break

        if matched:
            continue

        # 匹配其他字段
        field_map = {
            r"作者[:：]": "authors",
            r"期刊|会议|来源[:：]": "venue",
            r"年份|发表[:：]": "year",
            r"DOI[:：]": "doi",
            r"链接|URL[:：]": "url",
            r"主要贡献|摘要|贡献[:：]": "contribution",
        }

        for pattern, field in field_map.items():
            m = re.match(rf".*?{pattern}\s*(.+)", line)
            if m:
                current[field] = m.group(1).strip().strip('"').strip("'").strip("**")
                break

        # 如果没有任何字段标记，尝试作为贡献描述处理
        if not matched and "title" in current and "contribution" not in current:
            if len(line) > 20:
                current["contribution"] = line

    if current and "title" in current:
        papers.append(current)

    # 添加元数据
    for i, paper in enumerate(papers):
        paper["id"] = generate_id(paper.get("title", f"paper_{i}"))
        paper["topic"] = topic
        paper["added_at"] = datetime.now().isoformat()
        paper["notes"] = ""

    return papers


# ─── 保存操作 ────────────────────────────────────────────

def save_paper(paper: dict) -> str:
    """保存单篇论文到文件，同时存入 ResearchMemory 长期记忆。"""
    index = load_index()

    # 检查是否已存在
    existing = next((p for p in index["papers"] if p["id"] == paper["id"]), None)
    if existing:
        existing.update(paper)
        existing["updated_at"] = datetime.now().isoformat()
        paper = existing
    else:
        index["papers"].append(paper)

    save_index(index)

    # Store to long-term memory
    arxiv_id = paper.get("doi") or paper.get("id", "")
    if arxiv_id and _memory is not None:
        _memory.store_knowledge(
            key=f"paper:{arxiv_id}",
            value={
                "title": paper.get("title", ""),
                "authors": paper.get("authors", ""),
                "year": paper.get("year", ""),
                "venue": paper.get("venue", ""),
                "topic": paper.get("topic", ""),
                "contribution": paper.get("contribution", ""),
            },
            tags=["literature", "paper", paper.get("topic", "general")],
        )

    _push_to_memory(
        f"保存论文: {paper.get('title', paper['id'])}",
        {"paper_id": paper["id"], "topic": paper.get("topic")},
        ["save_paper"],
    )

    return paper["id"]


def save_batch(papers: list[dict], topic: str = ""):
    """批量保存论文。"""
    if topic:
        topic_dir = PAPERS_DIR / topic
        topic_dir.mkdir(exist_ok=True)

    saved_ids = []
    for paper in papers:
        paper["topic"] = paper.get("topic") or topic
        pid = save_paper(paper)
        saved_ids.append(pid)

        if topic:
            # 额外保存到主题目录
            paper_file = topic_dir / f"{pid}.json"
            with open(paper_file, "w", encoding="utf-8") as f:
                json.dump(paper, f, ensure_ascii=False, indent=2)

    return saved_ids


# ─── 查询操作 ────────────────────────────────────────────

def list_papers(topic: Optional[str] = None, limit: int = 50) -> list[dict]:
    """列出所有论文。"""
    index = load_index()
    papers = index.get("papers", [])

    if topic:
        papers = [p for p in papers if p.get("topic") == topic]

    return sorted(papers, key=lambda x: x.get("added_at", ""), reverse=True)[:limit]


def search_papers(keyword: str) -> list[dict]:
    """搜索论文（标题/作者/贡献/主题）。"""
    index = load_index()
    kw = keyword.lower()
    results = []

    for paper in index.get("papers", []):
        if (kw in paper.get("title", "").lower() or
            kw in paper.get("authors", "").lower() or
            kw in paper.get("contribution", "").lower() or
            kw in paper.get("topic", "").lower()):
            results.append(paper)

    return sorted(results, key=lambda x: x.get("added_at", ""), reverse=True)


def get_paper(paper_id: str) -> Optional[dict]:
    """根据 ID 获取论文详情。"""
    index = load_index()
    for paper in index.get("papers", []):
        if paper["id"] == paper_id:
            return paper
    return None


# ─── 导出操作 ────────────────────────────────────────────

def export_bibtex(paper: dict) -> str:
    """将单篇论文转换为 BibTeX 格式。"""
    key = re.sub(r"[^a-zA-Z0-9]", "", paper.get("title", "unknown"))[:20].lower()
    if paper.get("authors"):
        first_author = paper["authors"].split(",")[0].split()[0].lower()
        key = f"{first_author}{paper.get('year', 'nd')}"
    else:
        key = f"{key}{paper.get('year', 'nd')}"

    lines = [
        f"@article{{{key},",
        f'  title = {{{paper.get("title", "Unknown Title")}}},',
    ]

    if paper.get("authors"):
        lines.append(f'  author = {{{paper["authors"]}}},')
    if paper.get("year"):
        lines.append(f'  year = {{{paper["year"]}}},')
    if paper.get("venue"):
        lines.append(f'  journal = {{{paper["venue"]}}},')
    if paper.get("doi"):
        lines.append(f'  doi = {{{paper["doi"]}}},')
    if paper.get("url"):
        lines.append(f'  url = {{{paper["url"]}}},')

    lines.append("}")
    return "\n".join(lines)


def export_all_bibtex() -> str:
    """导出所有论文为 BibTeX 格式。"""
    index = load_index()
    entries = []
    for paper in index.get("papers", []):
        entries.append(export_bibtex(paper))
    return "\n\n".join(entries)


def export_markdown(paper: dict) -> str:
    """将单篇论文转换为 Markdown 格式。"""
    lines = [
        f"## {paper.get('title', '无标题')}",
        "",
        f"- **ID**: `{paper['id']}`",
        f"- **作者**: {paper.get('authors', '未知')}",
        f"- **年份**: {paper.get('year', '未知')}",
        f"- **来源**: {paper.get('venue', '未知')}",
        f"- **主题**: {paper.get('topic', '未分类')}",
        "",
        "### 主要贡献",
        "",
        paper.get("contribution", "无描述"),
    ]
    if paper.get("doi"):
        lines.append("")
        lines.append(f"**DOI**: {paper['doi']}")
    if paper.get("url"):
        lines.append(f"**链接**: {paper['url']}")
    return "\n".join(lines)


# ─── 笔记操作 ────────────────────────────────────────────

def add_note(paper_id: str, note: str):
    """为论文添加阅读笔记。"""
    index = load_index()
    for paper in index["papers"]:
        if paper["id"] == paper_id:
            existing = paper.get("notes", "")
            timestamp = datetime.now().strftime("%Y-%m-%d")
            new_note = f"\n\n[{timestamp}]\n{note}"
            paper["notes"] = (existing or "") + new_note
            save_index(index)
            print(f"[✓] 已为 {paper_id} 添加笔记")
            return
    print(f"[✗] 未找到论文 {paper_id}")


# ─── CLI 界面 ────────────────────────────────────────────

def print_paper(paper: dict, detailed: bool = False):
    """打印单篇论文。"""
    title = paper.get("title", "无标题")
    authors = paper.get("authors", "未知")
    year = paper.get("year", "?")
    venue = paper.get("venue", "未知来源")
    topic = paper.get("topic", "未分类")
    pid = paper["id"]

    print(f"\n{'='*70}")
    print(f"  [{pid}] {title}")
    print(f"  作者: {authors} ({year})")
    print(f"  来源: {venue}")
    print(f"  主题: {topic}")

    if detailed:
        print(f"\n  主要贡献:")
        contrib = paper.get("contribution", "无")
        for line in textwrap.wrap(contrib, width=66):
            print(f"    {line}")
        if paper.get("doi"):
            print(f"  DOI: {paper['doi']}")
        if paper.get("url"):
            print(f"  URL: {paper['url']}")
        notes = paper.get("notes", "")
        if notes:
            print(f"\n  我的笔记:")
            for note_line in textwrap.wrap(notes, width=66):
                print(f"    {note_line}")


def cmd_list(args):
    """列出所有论文。"""
    papers = list_papers(topic=args.topic, limit=args.limit)
    if not papers:
        print("📭 文献库为空，先用 search 命令添加文献。")
        return

    print(f"\n📚 文献库（共 {len(papers)} 篇）")
    if args.topic:
        print(f"   筛选主题: {args.topic}")
    for paper in papers:
        print_paper(paper, detailed=args.detail)


def cmd_search(args):
    """搜索论文。"""
    if args.keyword:
        results = search_papers(args.keyword)
    else:
        results = list_papers(topic=args.topic, limit=args.limit)

    if not results:
        print(f"🔍 未找到相关文献（关键词: {args.keyword}）")
        return

    print(f"\n🔍 找到 {len(results)} 篇相关文献:")
    for paper in results:
        print_paper(paper, detailed=args.detail)


def cmd_show(args):
    """显示论文详情。"""
    paper = get_paper(args.paper_id)
    if paper:
        print_paper(paper, detailed=True)
    else:
        print(f"[✗] 未找到论文 {args.paper_id}")


def cmd_add(args):
    """手动添加论文。"""
    ensure_dirs()
    paper = {
        "id": generate_id(args.title),
        "title": args.title,
        "authors": args.authors or "",
        "year": args.year or "",
        "venue": args.venue or "",
        "doi": args.doi or "",
        "topic": args.topic or "",
        "contribution": args.contribution or "",
        "added_at": datetime.now().isoformat(),
        "notes": "",
    }
    pid = save_paper(paper)
    print(f"[✓] 已保存论文: {paper['title']} (ID: {pid})")


def cmd_note(args):
    """添加笔记。"""
    add_note(args.paper_id, args.text)


def cmd_export(args):
    """导出文献。"""
    if args.format == "bibtex":
        content = export_all_bibtex() if args.all else export_bibtex(get_paper(args.paper_id) or {})
    elif args.format == "markdown":
        content = export_markdown(get_paper(args.paper_id) or {})
    elif args.format == "json":
        papers = list_papers() if args.all else [get_paper(args.paper_id)]
        content = json.dumps(papers, ensure_ascii=False, indent=2)
    else:
        print(f"[✗] 不支持的格式: {args.format}")
        return

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"[✓] 已导出到 {args.output}")
    else:
        print(content)


def cmd_import(args):
    """导入文本中的文献。"""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        print("请提供要导入的文件路径: --file <path>")
        return

    topic = args.topic or "general"
    papers = parse_paper_from_text(text, topic=topic)

    if not papers:
        print("[✗] 未能从文本中解析出论文信息")
        print("\n请确保文本包含论文标题，格式如:")
        print("1. 论文标题")
        print("   作者: xxx")
        print("   来源: xxx 会议/期刊")
        return

    saved = save_batch(papers, topic=topic)
    print(f"[✓] 成功导入 {len(saved)} 篇论文")
    for pid in saved:
        print(f"     - {pid}")


# ─── 主入口 ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="文献管理器 — 保存、搜索、管理 AI 检索到的论文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # list
    p_list = subparsers.add_parser("list", help="列出所有文献")
    p_list.add_argument("--topic", "-t", help="按主题筛选")
    p_list.add_argument("--limit", "-n", type=int, default=50, help="显示数量")
    p_list.add_argument("--detail", "-d", action="store_true", help="显示详细信息")

    # search
    p_search = subparsers.add_parser("search", help="搜索文献")
    p_search.add_argument("keyword", nargs="?", help="搜索关键词")
    p_search.add_argument("--topic", "-t", help="按主题筛选")
    p_search.add_argument("--limit", "-n", type=int, default=20, help="显示数量")
    p_search.add_argument("--detail", "-d", action="store_true", help="显示详细信息")

    # show
    p_show = subparsers.add_parser("show", help="显示论文详情")
    p_show.add_argument("paper_id", help="论文 ID")

    # add
    p_add = subparsers.add_parser("add", help="手动添加论文")
    p_add.add_argument("--title", "-t", required=True, help="论文标题")
    p_add.add_argument("--authors", "-a", help="作者（逗号分隔）")
    p_add.add_argument("--year", "-y", help="发表年份")
    p_add.add_argument("--venue", "-v", help="期刊/会议")
    p_add.add_argument("--doi", help="DOI")
    p_add.add_argument("--topic", help="主题/分类")
    p_add.add_argument("--contribution", "-c", help="主要贡献")

    # note
    p_note = subparsers.add_parser("note", help="添加阅读笔记")
    p_note.add_argument("paper_id", help="论文 ID")
    p_note.add_argument("text", help="笔记内容")

    # export
    p_export = subparsers.add_parser("export", help="导出文献")
    p_export.add_argument("--format", "-f", choices=["bibtex", "markdown", "json"],
                          default="bibtex", help="导出格式")
    p_export.add_argument("--paper-id", help="导出单篇（指定 ID）")
    p_export.add_argument("--all", "-a", action="store_true", help="导出全部")
    p_export.add_argument("--output", "-o", help="输出文件路径")

    # import
    p_import = subparsers.add_parser("import", help="从文本导入文献")
    p_import.add_argument("--file", "-f", help="包含文献信息的文本文件")
    p_import.add_argument("--topic", "-t", help="主题/分类")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "note":
        cmd_note(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "import":
        cmd_import(args)
    else:
        parser.print_help()
        print("\n--- 示例 ---")
        print("  python literature_manager.py list                  # 列出所有文献")
        print("  python literature_manager.py search 深度学习         # 搜索文献")
        print("  python literature_manager.py show abc123_0519      # 查看详情")
        print("  python literature_manager.py add -t '标题' -a '作者' # 添加论文")
        print("  python literature_manager.py note abc123 我的笔记    # 添加笔记")
        print("  python literature_manager.py export --all -f bibtex # 导出 BibTeX")


if __name__ == "__main__":
    main()
