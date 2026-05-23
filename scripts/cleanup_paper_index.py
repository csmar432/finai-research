#!/usr/bin/env python3
"""
清理 knowledge/papers/index.json 中的碎片条目，
合并为规范的单篇论文条目，并删除 金融AI/ 目录下的40个碎片文件。

用法：
  python scripts/cleanup_paper_index.py --dry-run
  python scripts/cleanup_paper_index.py
"""

import json
import re
import argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.parent
INDEX_FILE = SCRIPT_DIR / "knowledge" / "papers" / "index.json"
FRAG_DIR = SCRIPT_DIR / "knowledge" / "papers" / "金融AI"


def is_garbage_entry(entry: dict) -> bool:
    """判断一个条目是否是碎片/垃圾条目。"""
    title = entry.get("title", "")
    paper_id = entry.get("id", "")

    # 完全空或占位符
    if not title or title == "--":
        return True

    # ID 是 _0519 的空条目
    if paper_id == "_0519":
        return True

    # 标题以特定前缀开头（碎片标识）
    garbage_prefixes = (
        "作者**：", "发表年份**：", "发表期刊/会议**：",
        "DOI**：", "主要贡献**：", "说明", "领域选择理由**：",
        "权威性**：", "时效性**：",
        "1. 论文标题：**", "2. 论文标题：**", "3. 论文标题：**",
        "4. 论文标题：**", "5. 论文标题：**", "6. 论文标题：**",
        "7. 论文标题：**", "8. 论文标题：**", "9. 论文标题：**",
        "10. 论文标题：**",
    )
    for prefix in garbage_prefixes:
        if title.startswith(prefix):
            return True

    # 标题包含 ** 但没有正规论文信息
    # 碎片条目通常标题短于20字符
    if len(title) < 20:
        return True

    return False


def has_meaningful_content(entry: dict) -> bool:
    """判断条目是否有实质内容。"""
    if is_garbage_entry(entry):
        return False

    title = entry.get("title", "")
    # 有 analysis 字段的条目是正规论文
    if entry.get("analysis"):
        return True
    # 有 url 或 doi 的条目是正规论文
    if entry.get("url") or entry.get("doi"):
        return True
    # 标题足够长的条目可能是正规论文（需要人工确认）
    if len(title) > 50:
        return True

    return False


def clean_index() -> dict:
    """清理 index.json，返回干净的数据结构。"""
    if not INDEX_FILE.exists():
        print(f"❌ 文件不存在: {INDEX_FILE}")
        return {"papers": [], "topics": {}, "last_updated": datetime.now().isoformat()}

    with open(INDEX_FILE, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])

    print(f"  原始条目数: {len(papers)}")

    # 统计碎片类型
    garbage_count = 0
    good_count = 0
    good_papers = []

    for entry in papers:
        if is_garbage_entry(entry):
            garbage_count += 1
        else:
            good_count += 1
            good_papers.append(entry)

    print(f"  碎片条目: {garbage_count} 个（将删除）")
    print(f"  有效条目: {good_count} 个（将保留）")

    return {
        "papers": good_papers,
        "topics": data.get("topics", {}),
        "last_updated": datetime.now().isoformat(),
    }


def list_fragment_files() -> list[Path]:
    """列出碎片 JSON 文件。"""
    if not FRAG_DIR.exists():
        return []
    return list(FRAG_DIR.glob("*.json"))


def main():
    parser = argparse.ArgumentParser(description="清理论文索引：删除碎片条目 + 合并文件")
    parser.add_argument("--dry-run", action="store_true", help="仅显示待删除内容，不实际执行")
    parser.add_argument("--no-delete-frag-dir", action="store_true", help="不删除金融AI碎片目录")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  🧹 清理论文索引")
    print(f"{'='*60}")

    # Step 1: 清理 index.json 中的碎片条目
    print(f"\n  Step 1: 清理 index.json 中的碎片条目")
    cleaned = clean_index()

    if args.dry_run:
        print(f"\n  🔍 [DRY RUN] 不会实际写入文件")
        print(f"  清理后会保留 {len(cleaned['papers'])} 个条目")
        return

    # 写入清理后的 index.json
    INDEX_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n  ✅ index.json 已清理，保留 {len(cleaned['papers'])} 个条目")

    # Step 2: 删除碎片 JSON 文件
    frag_files = list_fragment_files()
    if frag_files:
        print(f"\n  Step 2: 删除 {len(frag_files)} 个碎片 JSON 文件")
        if args.no_delete_frag_dir:
            print(f"  ⚠ 跳过删除（--no-delete-frag-dir）")
        else:
            for f in frag_files:
                f.unlink()
            print(f"  ✅ 已删除 {FRAG_DIR.name}/ 下的所有碎片 JSON")
            # 如果目录空了，删除空目录
            try:
                FRAG_DIR.rmdir()
                print(f"  ✅ 已删除空目录 {FRAG_DIR.name}/")
            except OSError:
                pass
    else:
        print(f"\n  Step 2: 碎片目录为空，跳过")

    # Step 3: 打印保留的论文列表
    papers = cleaned["papers"]
    if papers:
        print(f"\n  {'='*60}")
        print(f"  保留的论文列表（共 {len(papers)} 篇）")
        print(f"  {'─'*60}")
        for i, p in enumerate(papers, 1):
            title = p.get("title", "无标题")
            # 清理标题中的 markdown 标记
            title = re.sub(r"\*+", "", title).strip()
            if len(title) > 60:
                title = title[:57] + "..."
            topic = p.get("topic", "未知领域")
            has_analysis = "✅" if p.get("analysis") else "⚠️"
            print(f"  {i:2d}. {has_analysis} [{topic}] {title}")

    print(f"\n{'='*60}")
    print(f"  ✅ 清理完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
