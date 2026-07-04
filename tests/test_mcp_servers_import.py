"""Smoke tests for mcp_servers/ — import every server.py

P3-audit-2026-07-04: mcp_servers/ 之前 1235 stmts 0% 覆盖（含 43 个 user_*/server.py）。
本测试仅验证每个 server.py 能成功 import，绕过实际网络调用。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MCP_DIR = ROOT / "mcp_servers"

# 把项目根加进 sys.path
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _discover_servers() -> list[str]:
    """找到所有 user_*/server.py 模块路径。"""
    servers = []
    for entry in sorted(MCP_DIR.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("user_"):
            continue
        server_py = entry / "server.py"
        if not server_py.exists():
            continue
        # 用 mcp_servers.user_xxx.server 形式（保证 __init__.py 存在）
        servers.append(f"mcp_servers.{entry.name}.server")
    return servers


SERVERS = _discover_servers()


@pytest.mark.parametrize("module_name", SERVERS, ids=lambda x: x.replace("mcp_servers.", ""))
def test_server_module_imports(module_name: str):
    """每个 user_*/server.py 必须能成功 import（或优雅处理缺失依赖）。

    P3-audit-2026-07-04: 一些 server.py 在 mcp 包缺失时调用 sys.exit(1) 而非 raise。
    我们 capture SystemExit（在依赖缺失时算作正常失败）。
    """
    try:
        mod = importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError) as e:
        # 可选依赖缺失（如 tushare 需 TUSHARE_TOKEN）— 允许失败但报告原因
        pytest.skip(f"可选依赖缺失: {e}")
    except SystemExit as e:
        # mcp 包未安装 — server.py 主动 sys.exit(1)，跳过
        pytest.skip(f"server.py 显式 sys.exit({e.code}) — 缺 mcp 或其他可选依赖")
    assert mod is not None, f"{module_name} import 返回 None"
    # 验证模块有 main 或 list_tools 或 mcp 对象
    has_main = hasattr(mod, "main") or hasattr(mod, "list_tools") or hasattr(mod, "mcp")
    assert has_main, f"{module_name} 缺少 main/list_tools/mcp"


def test_base_module_imports():
    """mcp_servers/base.py 也能 import。"""
    mod = importlib.import_module("mcp_servers.base")
    assert mod is not None


def test_mcp_healthcheck_imports():
    """mcp_healthcheck.py 也能 import。"""
    mod = importlib.import_module("mcp_servers.mcp_healthcheck")
    assert mod is not None


def test_mcp_servers_count_at_least_40():
    """确保 43 个 server 都被发现（防止某天用户删了导致测试真空）。"""
    assert len(SERVERS) >= 40, f"只发现 {len(SERVERS)} 个 server，期望 >= 40"
