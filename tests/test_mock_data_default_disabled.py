"""Mock 数据默认禁用与确认边界测试。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 加项目根到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# 代表性 mock 服务器；全量守卫数量由 test_default_mode_blocks_all_guarded_servers 校验
PROTECTED_SERVERS = [
    ("user_nber_wp", "handle_search"),
    ("user_bea_data", "handle_gdp"),
    ("user_csmar", "handle_financial"),
    ("user_wuhan_stats", "handle_wuhan_gdp"),
    ("user_macro_datas", "handle_rd_panel"),
]


@pytest.fixture(autouse=True)
def reset_mock_mode():
    """每个测试前清掉 MCP_MOCK_MODE，确保默认 disabled。"""
    if "MCP_MOCK_MODE" in os.environ:
        del os.environ["MCP_MOCK_MODE"]
    yield
    if "MCP_MOCK_MODE" in os.environ:
        del os.environ["MCP_MOCK_MODE"]


def test_default_mode_blocks_mock_call():
    """默认 MCP_MOCK_MODE 应为 disabled。"""
    from mcp_servers.mcp_mock_helper import check_mock_permission

    result = check_mock_permission({}, "handle_search", "user-nber-wp")
    assert result is not None, "默认模式应返回拒绝响应"
    text = result[0].text
    assert "MOCK_DISABLED" in text
    assert "MCP_MOCK_MODE=allow" in text


def test_allow_mode_passes_through():
    """MCP_MOCK_MODE=allow 应直接通过。"""
    from mcp_servers.mcp_mock_helper import check_mock_permission

    os.environ["MCP_MOCK_MODE"] = "allow"
    result = check_mock_permission({}, "handle_search", "user-nber-wp")
    assert result is None, "allow 模式应直接通过"


def test_confirm_mode_works_as_before():
    """MCP_MOCK_MODE=confirm 应返回确认提示（向后兼容）。"""
    from mcp_servers.mcp_mock_helper import check_mock_permission

    os.environ["MCP_MOCK_MODE"] = "confirm"
    # 无批准关键词 → 返回确认提示
    result = check_mock_permission({}, "handle_search", "user-nber-wp")
    assert result is not None, "confirm 模式无批准词应返回确认提示"

    # 含批准关键词 → 通过
    result = check_mock_permission(
        {}, "handle_search", "user-nber-wp", request_context="我确认使用 mock 数据"
    )
    assert result is None, "confirm 模式含批准词应通过"


@pytest.mark.parametrize("context", ["yesterday", "okayish", "confirmation pending"])
def test_confirm_mode_does_not_accept_approval_substrings(context):
    """Unrelated English words must not authorize mock data."""
    from mcp_servers.mcp_mock_helper import check_mock_permission

    os.environ["MCP_MOCK_MODE"] = "confirm"
    result = check_mock_permission(
        {}, "handle_search", "user-nber-wp", request_context=context
    )
    assert result is not None, f"{context!r} must not authorize mock data"


@pytest.mark.parametrize("server_name,tool_name", PROTECTED_SERVERS)
def test_representative_mock_servers_protected(server_name, tool_name):
    """代表性 mock server 必须调用 check_mock_permission。

    防止未来回归：有人删除 mock 拦截。
    """
    server_dir = server_name.replace("user_", "user_")  # 目录已带 user_ 前缀
    server_py = Path(f"mcp_servers/{server_dir}/server.py")
    if not server_py.exists():
        pytest.skip(f"{server_py} 不存在")

    text = server_py.read_text()
    assert "check_mock_permission" in text, (
        f"{server_name}/server.py 缺少 check_mock_permission 拦截，"
        f"必须显式调用以确保 mock 数据默认禁用"
    )


def test_wuhan_stats_handlers_all_protected():
    """user_wuhan_stats 所有 6 个 handler 必须被 check_mock_permission 保护。"""
    server_py = Path("mcp_servers/user_wuhan_stats/server.py")
    text = server_py.read_text()

    # 数 handle_wuhan_* 函数
    import re
    handlers = re.findall(r"async def (handle_\w+)", text)
    # 数 check_mock_permission 调用
    checks = text.count("check_mock_permission(")

    assert len(handlers) >= 6, f"应至少 6 个 handler，实际 {len(handlers)}"
    assert checks >= 6, f"应至少 6 次 check_mock_permission 调用，实际 {checks}"


def test_macro_datas_handlers_all_protected():
    """user_macro_datas 所有 5 个 handler 必须被 check_mock_permission 保护。"""
    server_py = Path("mcp_servers/user_macro_datas/server.py")
    text = server_py.read_text()

    import re
    handlers = re.findall(r"async def (handle_\w+)", text)
    checks = text.count("check_mock_permission(")

    assert len(handlers) >= 5, f"应至少 5 个 handler，实际 {len(handlers)}"
    assert checks >= 5, f"应至少 5 次 check_mock_permission 调用，实际 {checks}"


def test_default_mode_blocks_all_guarded_servers():
    """默认模式下所有接入统一守卫的 server 都会被拦截。"""
    from mcp_servers.mcp_mock_helper import check_mock_permission

    protected = []
    for server_py in sorted(Path("mcp_servers").glob("user_*/server.py")):
        text = server_py.read_text()
        if "check_mock_permission" not in text:
            continue
        protected.append((server_py.parent.name, "regression_probe"))

    assert len(protected) >= 17, f"expected at least 17 guarded servers, found {len(protected)}"
    for server_name, tool_name in protected:
        result = check_mock_permission({}, tool_name, server_name.replace("_", "-"))
        assert result is not None, (
            f"{server_name}.{tool_name} 默认模式应被拦截，但通过了"
        )
        assert "MOCK_DISABLED" in result[0].text
