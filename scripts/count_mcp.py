#!/usr/bin/env python3
"""Count MCP servers and persist the count for docs/reports.

本脚本是文档中 `{{MCP_COUNT}}` 占位符的真相源 (single source of truth)。
输出同时写到:
  - stdout (供人/CI 阅读)
  - .docs-cache/MCP_COUNT.txt (供后续脚本和文档渲染器消费)

用法:
    python scripts/count_mcp.py            # 打印 + 写入 .docs-cache
    python scripts/count_mcp.py --json     # 同时输出 JSON

约束:
  - 占位符约定: 文档中以 `{{MCP_COUNT}}` 替换硬编码的 MCP 数量
  - 该目录在 .gitignore 中, 不会污染仓库
  - 被 scripts/count_assets.py 中的 count_mcp_servers() 内部复用

维护:
  新增/删除 mcp_servers/user_* 目录后, 跑一次:
      python scripts/count_mcp.py
  即可让所有引用 `{{MCP_COUNT}}` 的文档保持准确。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_ROOT = PROJECT_ROOT / "mcp_servers"
CACHE_DIR = PROJECT_ROOT / ".docs-cache"
CACHE_FILE = CACHE_DIR / "MCP_COUNT.txt"


def count_mcp_directories(mcp_root: Path = MCP_ROOT) -> int:
    """统计 mcp_servers/ 下 user_* 目录数.

    与 scripts/count_assets.py 中的同名函数保持一致: 仅统计顶层目录中
    以 `user_` 开头且含 server.py 的目录 (即真实 MCP 实现)。
    """
    if not mcp_root.is_dir():
        return 0
    return sum(
        1
        for d in mcp_root.iterdir()
        if d.is_dir()
        and d.name.startswith("user_")
        and (d / "server.py").exists()
    )


def write_cache(count: int) -> None:
    """写入 .docs-cache/MCP_COUNT.txt."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(f"{count}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count MCP server directories and persist to .docs-cache/MCP_COUNT.txt"
    )
    parser.add_argument("--json", action="store_true", help="Also print machine-readable JSON")
    args = parser.parse_args()

    count = count_mcp_directories()
    write_cache(count)

    print(f"MCP server directories: {count}")
    print(f"   ├─ cache file: {CACHE_FILE.relative_to(PROJECT_ROOT)}")
    print(f"   └─ docs placeholder: `{{{{MCP_COUNT}}}}` → {count}")
    if args.json:
        print(json.dumps({"mcp_count": count, "cache_file": str(CACHE_FILE)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
