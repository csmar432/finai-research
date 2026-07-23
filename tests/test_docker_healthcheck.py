"""docker-compose.yml healthcheck 配置验证。

P0 修复 2026-06-28: 健康检查从 `sys.exit(0)` no-op 改为真实 MCP initialize。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def compose_cfg():
    """读取 docker-compose.yml。"""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML 未安装")
    cfg_path = Path("docker-compose.yml")
    if not cfg_path.exists():
        pytest.skip(f"{cfg_path} 不存在")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def test_no_sys_exit_noop_healthcheck(compose_cfg):
    """确保没有任何 healthcheck 是 sys.exit(0) no-op。"""
    bad = []
    for name, svc in compose_cfg.get("services", {}).items():
        h = svc.get("healthcheck")
        if not h:
            continue
        test = h.get("test", [])
        # 序列化为字符串便于搜索
        test_str = " ".join(str(x) for x in test)
        if "sys.exit(0)" in test_str:
            bad.append(name)
    assert not bad, f"以下服务仍用 sys.exit(0) no-op healthcheck: {bad}"


def test_healthchecks_use_real_probe(compose_cfg):
    """healthcheck 应使用真实探测（mcp_healthcheck.py 或类似）。"""
    bad = []
    for name, svc in compose_cfg.get("services", {}).items():
        h = svc.get("healthcheck")
        if not h:
            continue
        test_str = " ".join(str(x) for x in h.get("test", []))
        # kill -0 1 也算 no-op（只检查进程存在，不检查健康）
        if "kill -0" in test_str:
            bad.append(name)
    assert not bad, f"以下服务用 kill -0 假阳性 healthcheck: {bad}"


def test_healthchecks_have_timeout(compose_cfg):
    """所有 healthcheck 应有 timeout 配置（避免卡死）。"""
    for name, svc in compose_cfg.get("services", {}).items():
        h = svc.get("healthcheck")
        if not h:
            continue
        assert "timeout" in h, f"服务 {name} healthcheck 缺 timeout"


def test_healthchecks_have_retries(compose_cfg):
    """所有 healthcheck 应有 retries 配置。"""
    for name, svc in compose_cfg.get("services", {}).items():
        h = svc.get("healthcheck")
        if not h:
            continue
        assert "retries" in h, f"服务 {name} healthcheck 缺 retries"


def test_mcp_healthcheck_script_exists():
    """mcp_healthcheck.py 脚本必须存在（docker healthcheck 依赖）。"""
    path = Path("mcp_servers/mcp_healthcheck.py")
    assert path.exists(), f"{path} 不存在"
    text = path.read_text()
    # 必须实现基于 MCP initialize 的真实探测
    assert "ClientSession" in text or "stdio_client" in text, (
        "mcp_healthcheck.py 未实现真实 MCP initialize 探测"
    )


def test_healthcheck_script_executable():
    """mcp_healthcheck.py 顶部应有 shebang。"""
    text = Path("mcp_servers/mcp_healthcheck.py").read_text()
    assert text.startswith("#!/usr/bin/env python"), "缺 shebang"
