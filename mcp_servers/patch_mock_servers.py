#!/usr/bin/env python3
"""
patch_mock_servers.py
=====================
自动为所有模拟数据服务器注入确认机制。

用法:
    cd /path/to/mcp_servers
    python patch_mock_servers.py [--dry-run]

流程:
    1. 读取 server.py
    2. 添加 mock_helper 导入
    3. 为每个工具描述追加 MOCK_WARNING
    4. 为每个 handler 开头注入 check_mock_permission
    5. 写回文件
"""

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MCP_SERVERS = SCRIPT_DIR

# 所有模拟数据服务器（100%模拟 或 大量模拟）
MOCK_SERVERS = [
    "user_fed_data",
    "user_oecd_data",
    "user_imf_data",
    "user_nber_wp",
    "user_csmar",
    "user_eastmoney_option",
    "user_bea_data",
    "user_eastmoney_bond",
    "user_eastmoney_fund",
    "user_macro_ceic",
    "user_wind",
    "user_eodhd",
]

# 工具名到服务器名的映射（用于确认消息）
SERVER_DISPLAY_NAMES = {
    "user_fed_data": "user-fed-data",
    "user_oecd_data": "user-oecd-data",
    "user_imf_data": "user-imf-data",
    "user_nber_wp": "user-nber-wp",
    "user_csmar": "user-csmar",
    "user_eastmoney_option": "user-eastmoney-option",
    "user_bea_data": "user-bea-data",
    "user_eastmoney_bond": "user-eastmoney-bond",
    "user_eastmoney_fund": "user-eastmoney-fund",
    "user_macro_ceic": "user-macro-ceic",
    "user_wind": "user-wind",
    "user_eodhd": "user-eodhd",
}

MOCK_WARNING = (
    '\\n\\n'
    '[模拟数据警告] 此工具返回的是演示/模拟数据，非真实API数据。'
    ' 数据不代表真实市场情况，如需真实数据请：\\n'
    '  1. 配置相应的 API Key\\n'
    '  2. 或使用同类无Key工具（如 user-financial）\\n'
    '  3. 或使用 user-playwright-mcp 从网页直接抓取\\n'
)

MOCK_IMPORT = '''# 导入模拟数据确认模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from mcp_mock_helper import check_mock_permission, MOCK_WARNING
except ImportError:
    def check_mock_permission(*a, **kw): return None
    MOCK_WARNING = ""
'''


def add_mock_import(content: str) -> str:
    """在 import 区域添加 mock_helper 导入。"""
    # 找到第一个非注释 import 语句之后插入
    lines = content.split('\n')
    insert_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and (
            stripped.startswith('import ') or stripped.startswith('from ')
        ):
            insert_idx = i
            break

    if insert_idx is None:
        print("  ! 无法找到插入位置，跳过")
        return content

    # 检查是否已导入
    if 'mcp_mock_helper' in content:
        print("  - 已存在 mcp_mock_helper 导入，跳过")
        return content

    # 找到该 import 块的结束（连续的非缩进空行）
    indent = len(lines[insert_idx]) - len(lines[insert_idx].lstrip())
    end_idx = insert_idx + 1
    for i in range(insert_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= indent and (stripped.startswith('import ') or stripped.startswith('from ')):
                continue
            elif stripped and line_indent <= indent:
                end_idx = i
                break
        elif not stripped:
            continue
        else:
            end_idx = i + 1

    # 插入 mock import（找到 __future__ import 之后）
    for i in range(insert_idx, len(lines)):
        if 'from __future__' in lines[i]:
            insert_after = i
            break
    else:
        insert_after = insert_idx

    lines.insert(insert_after + 1, MOCK_IMPORT)
    return '\n'.join(lines)


def add_mock_warning_to_tools(content: str) -> str:
    """为每个 Tool 描述追加 MOCK_WARNING。"""
    # 匹配 Tool 定义中的 description 字符串
    # 找到所有 description="..." 或 description="...\n..."
    modified = 0

    # 更简单的策略：在每个 description 的最后追加 MOCK_WARNING
    # 找到 Tool( name=... description=...
    pattern = r'(description=)"([^"]+)"(?=,\s*\n\s*inputSchema)'
    replacement = rf'\1"\2{MOCK_WARNING}"'

    new_content, n = re.subn(pattern, replacement, content)
    if n > 0:
        print(f"  + 追加 MOCK_WARNING 到 {n} 个工具描述")
    return new_content


def add_check_to_handlers(content: str, server_name: str) -> str:
    """为每个 handler 函数开头注入 check_mock_permission 调用。"""
    display_name = SERVER_DISPLAY_NAMES.get(server_name, server_name)

    # 找到所有 async def handle_xxx(args: dict) -> list[TextContent]:
    # 并在函数体第一行（非docstring）后插入检查
    handler_pattern = r'(async def (handle_\w+)\(args: dict\) -> list\[TextContent\]:)'

    lines = content.split('\n')
    new_lines = []
    i = 0
    added_checks = []

    while i < len(lines):
        line = lines[i]

        # 检查是否是 handler 定义
        m = re.match(r'(\s*)(async def (handle_\w+)\(args: dict\) -> list\[TextContent\]:)', line)
        if m:
            indent = m.group(1)
            func_def = m.group(2)
            func_name = m.group(3)
            new_lines.append(line)

            i += 1
            # 跳过 docstring（如果有）
            if i < len(lines) and '"""' in lines[i]:
                new_lines.append(lines[i])
                i += 1
                # 多行 docstring
                while i < len(lines) and '"""' not in lines[i]:
                    new_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    new_lines.append(lines[i])
                    i += 1

            # 插入确认检查
            check_code = (
                f'{indent}    check = check_mock_permission(args, "{func_name}", "{display_name}")\n'
                f'{indent}    if check is not None:\n'
                f'{indent}        return check\n\n'
            )
            new_lines.append(check_code)
            added_checks.append(func_name)
            continue

        new_lines.append(line)
        i += 1

    if added_checks:
        print(f"  + 注入确认检查到 {len(added_checks)} 个 handler: {', '.join(added_checks)}")
    else:
        print("  ! 未找到 handler 函数")

    return '\n'.join(new_lines)


def patch_server(server_dir: Path, dry_run: bool = False) -> bool:
    """修补单个服务器。返回是否成功。"""
    server_file = server_dir / "server.py"
    if not server_file.exists():
        print(f"  ! server.py 不存在: {server_file}")
        return False

    content = server_file.read_text(encoding='utf-8')
    original = content

    print(f"\n处理 {server_dir.name}/...")

    # Step 1: 添加 import
    content = add_mock_import(content)

    # Step 2: 追加警告到工具描述
    content = add_mock_warning_to_tools(content)

    # Step 3: 注入确认检查
    content = add_check_to_handlers(content, server_dir.name)

    if dry_run:
        print(f"  [dry-run] 不写入文件")
        return True

    if content != original:
        server_file.write_text(content, encoding='utf-8')
        print(f"  ✓ 已写入 {server_file}")
        return True
    else:
        print(f"  - 内容未变化，跳过写入")
        return True


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("MCP Mock Server 确认机制补丁")
    print(f"模式: {'DRY RUN（不写入）' if dry_run else 'LIVE（写入文件）'}")
    print("=" * 60)

    servers_dir = MCP_SERVERS
    if not servers_dir.exists():
        print(f"错误: 目录不存在 {servers_dir}")
        sys.exit(1)

    results = {}
    for server_name in MOCK_SERVERS:
        server_dir = servers_dir / server_name
        if not server_dir.exists():
            print(f"\n处理 {server_name}/... ! 目录不存在，跳过")
            results[server_name] = "SKIP"
            continue
        ok = patch_server(server_dir, dry_run=dry_run)
        results[server_name] = "OK" if ok else "FAIL"

    print("\n" + "=" * 60)
    print("汇总:")
    for name, status in results.items():
        print(f"  {name}: {status}")
    print("=" * 60)


if __name__ == "__main__":
    main()
