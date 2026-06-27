#!/usr/bin/env python3
"""Update SCRIPTS_INDEX.md overview table from real disk state.

直接对账 scripts/ 目录真实内容，更新总览段的分类计数。
对账方式：
  - scripts/*.py         → 顶级脚本
  - scripts/core/*.py    → 核心库
  - scripts/research_framework/*.py → 计量方法
  - scripts/research_directions/*.py → 研究方向
  - mcp_servers/user_*/  → MCP servers

每次大改后跑：
    python scripts/update_scripts_index.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_MD = PROJECT_ROOT / "scripts" / "SCRIPTS_INDEX.md"


def count_py(dir_: Path) -> int:
    """Count .py files in dir_, excluding __pycache__."""
    if not dir_.exists():
        return 0
    return sum(1 for f in dir_.glob("*.py") if not f.name.startswith("_"))


def count_dirs(parent: Path, prefix: str) -> int:
    """Count subdirectories starting with prefix."""
    if not parent.exists():
        return 0
    return sum(1 for d in parent.iterdir() if d.is_dir() and d.name.startswith(prefix))


def compute_stats() -> dict[str, int]:
    scripts = PROJECT_ROOT / "scripts"
    return {
        "top_level_scripts": count_py(scripts),
        "core_modules": count_py(scripts / "core"),
        "research_framework": count_py(scripts / "research_framework"),
        "research_directions": count_py(scripts / "research_directions"),
        "mcp_servers": count_dirs(PROJECT_ROOT / "mcp_servers", "user_"),
        "tests": count_py(PROJECT_ROOT / "tests"),
    }


def make_overview_table(stats: dict[str, int]) -> str:
    """Build the new 分类总览 table markdown."""
    lines = [
        "| 分类 | 数量 | 说明 |",
        "|------|------|------|",
        f"| 🚀 Entry Points (`scripts/*.py`) | {stats['top_level_scripts']} | 顶级入口脚本（含 CLI） |",
        f"| 📦 Core Modules (`scripts/core/`) | {stats['core_modules']} | 核心库（被其他模块导入）|",
        f"| 📊 Research Framework (`scripts/research_framework/`) | {stats['research_framework']} | 计量方法模块 |",
        f"| 🧭 Research Directions (`scripts/research_directions/`) | {stats['research_directions']} | 研究方向领域 |",
        f"| 🧪 Tests (`tests/`) | {stats['tests']} | 测试文件 |",
        f"| 🔌 MCP Servers (`mcp_servers/user_*/`) | {stats['mcp_servers']} | MCP 数据源 |",
        f"| **合计（仅 Python 文件）** | **{stats['top_level_scripts'] + stats['core_modules'] + stats['research_framework'] + stats['research_directions'] + stats['tests']}** | 不含 MCP / docs / tests fixtures |",
    ]
    return "\n".join(lines)


def update_index_md(stats: dict[str, int], dry_run: bool = False) -> bool:
    """Replace the 分类总览 section in SCRIPTS_INDEX.md."""
    if not INDEX_MD.exists():
        print(f"❌ {INDEX_MD} not found")
        return False

    content = INDEX_MD.read_text()
    new_table = make_overview_table(stats)

    # 替换 "## 分类总览" 到下一个 "---" 之间的内容
    pattern = r"(## 分类总览\n\n)(.*?)(\n---)"
    if not re.search(pattern, content, re.DOTALL):
        print("⚠️  Could not find 分类总览 section in SCRIPTS_INDEX.md")
        return False

    # 也更新"最后更新"日期
    new_content = re.sub(
        pattern,
        lambda m: m.group(1) + new_table + "\n\n> 自动生成于 " + _today() + m.group(3),
        content,
        flags=re.DOTALL,
    )

    # 替换"最后更新: 2026-06-13"
    new_content = re.sub(
        r"最后更新: \d{4}-\d{2}-\d{2}(.*?)$",
        f"最后更新: {_today()}（自动对账）",
        new_content,
    )

    if new_content == content:
        print("ℹ️  No changes needed")
        return True

    if dry_run:
        print("📋 Would update to:")
        print(new_table)
        return True

    INDEX_MD.write_text(new_content)
    print(f"✅ Updated {INDEX_MD.name}")
    print(new_table)
    return True


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update SCRIPTS_INDEX.md from disk state")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    stats = compute_stats()
    print("📊 Current counts:")
    for k, v in stats.items():
        print(f"   {k}: {v}")
    print()

    update_index_md(stats, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())