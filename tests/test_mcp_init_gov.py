"""MCP 服务器 __init__.py 治理测试 (audit 2026-06-28 P3-4).

历史：2026-06-28 审计报告称"9 个 0 行占位 Python 文件"。
实际情况：7 个 mcp_servers/user_*/__init__.py 是 0 字符（Python 包规范）
        + 2 个已被 ROADMAP/examples 删除时附带删除。
用户决策（2026-06-28）：加 docstring（不是删除，因为 __init__.py 是
Python 包的命名标记文件，删了会导致包无法识别）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_ROOT = PROJECT_ROOT / "mcp_servers"


def test_no_zero_byte_init_py_in_mcp_servers():
    """所有 mcp_servers/user_*/__init__.py 必须有内容（docstring 或更多）。

    Bug 历史：审计前有 7 个 0 字符 __init__.py（Python 包的命名标记，
    实际是规范但看起来像占位）。本次添加 docstring。
    """
    empty = []
    for init in MCP_ROOT.rglob("__init__.py"):
        if "__pycache__" in str(init):
            continue
        if init.stat().st_size == 0:
            empty.append(init)
    assert not empty, (
        f"以下 __init__.py 是 0 字节（应至少含 docstring）: "
        f"{[str(e.relative_to(PROJECT_ROOT)) for e in empty]}"
    )


@pytest.mark.parametrize("server", [
    "user_tushare", "user_province_stats", "user_enhanced_finance",
    "user_financial", "user_wuhan_stats", "user_hubei_stats",
    "user_eastmoney_reports",
])
def test_mcp_init_has_docstring(server):
    """每个 MCP 服务器的 __init__.py 必须含 docstring。"""
    init = MCP_ROOT / server / "__init__.py"
    assert init.exists(), f"{server}/__init__.py 不存在"
    content = init.read_text()
    assert content.startswith('"""') or content.startswith("'''"), (
        f"{server}/__init__.py 缺少 module docstring"
    )


def test_mcp_init_imports_work():
    """所有 mcp_servers/user_*/__init__.py 必须能 import。"""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    for d in sorted(MCP_ROOT.iterdir()):
        if not d.is_dir() or not d.name.startswith("user_"):
            continue
        # 不能用 __import__ 因为有 dash
        pkg = f"mcp_servers.{d.name}"
        try:
            __import__(pkg)
        except Exception as e:
            pytest.fail(f"import {pkg} 失败: {e}")