#!/usr/bin/env python3
"""
将所有 mcp_servers/ 中的服务器注册到 MCP 配置文件。

支持多平台自动检测 (Cursor / Claude Code / VS Code / 通用)，
按优先级自动选择配置文件路径。

用法:
    python scripts/register_mcp_servers.py [--dry-run]
    python scripts/register_mcp_servers.py --list
    python scripts/register_mcp_servers.py --remove <server_name> ...
    RESEARCH_MCP_CONFIG=/path/to/mcp.json python scripts/register_mcp_servers.py  # 手动指定
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.core.platform import (
    get_mcp_config,
    get_mcp_config_paths,
)
from scripts.core.ide_platform import PLATFORM

VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def get_module_name(dir_name: str) -> str:
    return dir_name


def get_mcp_json_key(server_identifier: str) -> str:
    """将 SERVER_METADATA.serverIdentifier 转为 mcp.json key"""
    # serverIdentifier 格式: "user-province-stats" → mcp.json key: "province-stats"
    # serverIdentifier 格式: "user-eastmoney-reports" → "eastmoney-reports"
    # 已注册项验证: "user-hubei-stats" → "hubei-stats" ✓
    if server_identifier.startswith("user-"):
        return server_identifier[len("user-"):]
    return server_identifier


def get_server_entry(module: str) -> dict:
    """构建 mcp.json 中的一条服务器配置"""
    return {
        "command": str(VENV_PYTHON),
        "args": [
            "-c",
            (
                f"import asyncio; import sys; "
                f"sys.path.insert(0, '{ROOT}/mcp_servers'); "
                f"from {module}.server import main; "
                f"asyncio.run(main())"
            ),
        ],
        "env": {},
    }


def load_existing_mcp_json() -> dict:
    """Load existing MCP config from platform-aware paths (Cursor/Claude Code/VS Code/project-local)."""
    return get_mcp_config()


def discover_servers() -> list[dict]:
    servers = []
    for d in sorted((ROOT / "mcp_servers").glob("user_*/")):
        mdata_path = d / "SERVER_METADATA.json"
        module = get_module_name(d.name)
        if mdata_path.exists():
            with open(mdata_path) as _f:
                mdata = json.load(_f)
            server_id = mdata.get("serverIdentifier") or mdata.get("id")
            mcp_key = get_mcp_json_key(server_id) if server_id else None
            servers.append({
                "dir": d.name,
                "module": module,
                "server_id": server_id,
                "mcp_key": mcp_key,
                "description": mdata.get("description", "")[:60],
                "has_metadata": True,
            })
        else:
            servers.append({
                "dir": d.name,
                "module": module,
                "server_id": None,
                "mcp_key": None,
                "description": "(无 SERVER_METADATA.json — 需要手动创建)",
                "has_metadata": False,
            })
    return servers


def main():
    from scripts.core.platform import PROJECT_ROOT

    target_paths = get_mcp_config_paths()
    # Prefer the first existing path, otherwise write to project-local .mcp.json
    default_write_path = target_paths[0] if target_paths else (PROJECT_ROOT / ".mcp.json")

    parser = argparse.ArgumentParser(
        description=(
            f"注册 MCP 服务器到配置文件 (当前平台: {PLATFORM})\n"
            f"自动写入: {default_write_path}\n"
            f"可用路径: {' / '.join(str(p) for p in get_mcp_config_paths() or ['(无)'])}\n\n"
            "mcp.json key 格式 = SERVER_METADATA.serverIdentifier 去掉 'user-' 前缀"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="只显示将做的更改，不写入文件")
    parser.add_argument("--remove", nargs="+", help="从 mcp.json 移除指定服务器（按 mcp.json key）")
    parser.add_argument("--list", action="store_true", help="列出所有服务器及其注册状态")
    args = parser.parse_args()

    existing = load_existing_mcp_json()
    existing_keys = set(existing.get("mcpServers", {}).keys())
    servers = discover_servers()

    # ── List mode ────────────────────────────────────────────────────────────
    if args.list:
        print(f"{'状态':<5} {'mcp.json key':<24} {'SERVER_METADATA.id':<24} {'目录'}")
        print("-" * 75)
        for srv in servers:
            in_mcp = srv["mcp_key"] in existing_keys if srv["mcp_key"] else False
            sm = "✅" if in_mcp else ("⚠️" if srv["mcp_key"] else "❌")
            print(f"{sm:<5} {str(srv['mcp_key'] or '?'):<24} {str(srv['server_id'] or '?'):<24} {srv['dir']}")
            if srv["has_metadata"]:
                print(f"      {srv['description']}")
        print(f"\n现有 mcp.json: {sorted(existing_keys)}")
        print("脚本将生成 mcp.json key (去掉 user- 前缀)")
        return

    # ── Remove mode ───────────────────────────────────────────────────────────
    if args.remove:
        removed = []
        for key in args.remove:
            if key in existing.get("mcpServers", {}):
                del existing["mcpServers"][key]
                removed.append(key)
        if removed:
            write_path = target_paths[0] if target_paths else default_write_path
            write_path.parent.mkdir(parents=True, exist_ok=True)
            with open(write_path, "w") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            print(f"已移除: {removed}")
            print(f"已写入 {write_path}")
        else:
            print(f"未找到任何匹配的服务器: {args.remove}")
        return

    # ── Register mode ─────────────────────────────────────────────────────────
    new_entries = {}
    for srv in servers:
        if not srv["mcp_key"]:
            print(f"  ⏭  {srv['dir']}: 无 serverIdentifier，跳过")
            continue
        if srv["mcp_key"] in existing_keys:
            print(f"  ✅ {srv['mcp_key']}: 已存在")
            continue
        new_entries[srv["mcp_key"]] = get_server_entry(srv["module"])
        print(f"  ➕ {srv['mcp_key']}: 新增")

    if not new_entries:
        print("\n所有服务器均已注册，无需更改。")
        return

    print(f"\n将新增 {len(new_entries)} 个条目到 mcp.json")

    if args.dry_run:
        print("\n[DRY RUN] 未写入文件。去掉 --dry-run 执行写入。")
        return

    existing["mcpServers"].update(new_entries)
    write_path = target_paths[0] if target_paths else default_write_path
    write_path.parent.mkdir(parents=True, exist_ok=True)

    # 原子写入：先写临时文件，再 rename（防止写入中途崩溃导致配置损坏）
    if write_path.exists():
        import datetime
        import shutil
        backup_path = write_path.with_suffix(f".json.bak.{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copy2(write_path, backup_path)
        print(f"  已备份: {backup_path}")

    tmp_path = write_path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.rename(write_path)  # atomic on POSIX
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    print(f"已写入 {write_path}")
    print(f"总计 {len(existing['mcpServers'])} 个服务器")


if __name__ == "__main__":
    main()
