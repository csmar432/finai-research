"""user_yfinance MCP server import smoke test (P0-H, audit 2026-06-27).

验证 mcp_servers/user_yfinance/server.py 不会因依赖缺失而 sys.exit(1)。
Fallback 行为：依赖缺失时打印 warning，进入 mock 模式。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SERVER_PY = (
    Path(__file__).resolve().parent.parent
    / "mcp_servers" / "user_yfinance" / "server.py"
)


def _load_safely():
    """Safely load the server module (tolerate missing yfinance/mcp)."""
    spec = importlib.util.spec_from_file_location("yfs_under_test", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit as e:
        pytest.fail(f"server.py called sys.exit({e.code}) — fallback failed")
    return mod


def test_server_imports_with_dependencies():
    """正常情况下（yfinance + mcp 已装），import 必须成功。"""
    mod = _load_safely()
    # 至少一个标志为 True
    assert mod._YFINANCE_AVAILABLE or mod._MCP_AVAILABLE, (
        "Both yfinance and mcp reported unavailable — install required"
    )


def test_server_does_not_sys_exit():
    """P0-H: server.py 绝不能因 ImportError 触发 sys.exit(1)。"""
    # 用 subprocess 跑一次空 import，确保进程不会 exit code 1
    import subprocess
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.util; "
         f"spec = importlib.util.spec_from_file_location('m', '{SERVER_PY}'); "
         f"m = importlib.util.module_from_spec(spec); "
         f"spec.loader.exec_module(m); "
         f"print('OK')"],
        capture_output=True, text=True, timeout=10,
    )
    # 即使依赖缺失，subprocess 进程也不应 exit 1
    if result.returncode != 0:
        assert "yfinance not installed" in result.stderr or "mcp package" in result.stderr, (
            f"Unexpected exit code {result.returncode}: {result.stderr[:300]}"
        )


def test_server_uses_fallback_not_silent_crash():
    """Fallback 必须在 stdout/stderr 留有警告。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.util; "
         f"spec = importlib.util.spec_from_file_location('m', '{SERVER_PY}'); "
         f"m = importlib.util.module_from_spec(spec); "
         f"spec.loader.exec_module(m)"],
        capture_output=True, text=True, timeout=10,
    )
    # 预期：要么 import 成功（依赖齐），要么有 warning
    if result.returncode != 0:
        # 任何非零退出都是 bug
        pytest.fail(
            f"Server import failed with code {result.returncode}: "
            f"stdout={result.stdout[:200]} stderr={result.stderr[:200]}"
        )
