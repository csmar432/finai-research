"""批量修复 MCP server 的 stdout banner 污染问题。

P0 修复 2026-06-28: MCP stdio 协议规定 stdout 只能包含 JSON-RPC 帧，
但 26 个 server 启动时在 main() 中 print() banner 到 stdout，
导致客户端 (如 health_check.py verify 模式) 无法 parse JSON-RPC 帧。

修复策略：仅修复 main() 函数内的 banner print（不影响 ERROR print
——后者在 sys.exit(1) 前，已退出进程）。

用法：
    python scripts/fix_mcp_stdout_banners.py           # 修复所有
    python scripts/fix_mcp_stdout_banners.py --dry-run # 仅预览
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# 匹配 main() 函数内的 banner print
# 模式：(缩进 4 空格) print(...) , flush=True
PATTERN = re.compile(
    r'^( {4})print\((.+?),\s*flush=True\)\s*$',
    re.MULTILINE,
)


def find_violations(server_path: Path) -> list[tuple[int, str]]:
    """返回 main() 函数内的 banner 违规（4 空格缩进）。"""
    if not server_path.exists():
        return []
    text = server_path.read_text(encoding="utf-8")
    violations = []
    for m in PATTERN.finditer(text):
        line = m.group(0)
        if "file=sys.stderr" in line:
            continue  # 已修
        if "ERROR" in line or "error" in line.lower():
            continue  # ERROR print 通常在 sys.exit 路径
        indent = m.group(1)
        if len(indent) != 4:
            continue  # main() 内的 print 通常 4 空格缩进
        line_no = text.count("\n", 0, m.start()) + 1
        violations.append((line_no, line.rstrip()))
    return violations


def fix_server(server_path: Path) -> int:
    """修复一个 server 的 banner。返回修改的行数。"""
    violations = find_violations(server_path)
    if not violations:
        return 0
    text = server_path.read_text(encoding="utf-8")
    n_fixed = 0
    for line_no, old in violations:
        new = old.rstrip()
        assert new.endswith(", flush=True)")
        new = new[:-len(", flush=True)")] + ", file=sys.stderr, flush=True)"
        if old in text:
            text = text.replace(old, new, 1)
            n_fixed += 1
    if n_fixed:
        server_path.write_text(text, encoding="utf-8")
    return n_fixed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅显示，不修改")
    args = parser.parse_args()

    servers_dir = ROOT / "mcp_servers"
    server_paths = sorted(servers_dir.glob("user_*/server.py"))
    total_fixed = 0
    total_servers = 0
    for sp in server_paths:
        violations = find_violations(sp)
        if not violations:
            continue
        total_servers += 1
        if args.dry_run:
            print(f"[DRY] {sp.relative_to(ROOT)}: {len(violations)} 处违规")
            for line_no, old in violations:
                print(f"      L{line_no}: {old.strip()}")
        else:
            n_fixed = fix_server(sp)
            total_fixed += n_fixed
            print(f"✅ {sp.relative_to(ROOT)}: 修复 {n_fixed} 处")

    print()
    if args.dry_run:
        print(f"📋 {total_servers} 个 server 待修复")
    else:
        print(f"✅ 共修复 {total_fixed} 处（{total_servers} 个 server）")
    return 0


if __name__ == "__main__":
    sys.exit(main())