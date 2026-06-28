"""MCP server stdout 干净性 + health_check 双层验证。

P0 修复 2026-06-28:
- MCP stdio 协议规定 stdout 只能有 JSON-RPC 帧
- 26 个 server 之前在 main() 顶部 print banner 到 stdout，污染协议流
- health_check.py --verify 模式之前 0 个 MCP 验证通过，现 4/4 通过
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ROOT = Path(__file__).resolve().parents[1]
MCP_SERVERS = ROOT / "mcp_servers"


def _python_path() -> str:
    """健康检查自身 Python（保证 mcp 包可导入）。"""
    return sys.executable


def _send_init_and_read(server_path: Path, timeout: float = 8.0) -> tuple[bool, str]:
    """启动 server，发送 initialize 请求，验证 stdout 干净。

    Returns:
        (success, message)
    """
    env = os.environ.copy()
    for env_path in [ROOT / ".env", ROOT / ".env.local"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    try:
        proc = subprocess.Popen(
            [_python_path(), str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(ROOT),
        )
    except Exception as e:
        return False, f"启动失败: {e}"

    try:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
        proc.stdin.write((json.dumps(init_req) + "\n").encode())
        proc.stdin.flush()

        start = time.time()
        while time.time() - start < timeout:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    stderr = proc.stderr.read(300).decode("utf-8", errors="replace")
                    return False, f"进程退出 (exit={proc.returncode}): {stderr[:80]}"
                time.sleep(0.05)
                continue
            line_str = line.decode("utf-8", errors="replace").strip()
            try:
                resp = json.loads(line_str)
            except json.JSONDecodeError:
                return False, f"stdout 有非 JSON-RPC 行: {line_str[:80]}"
            if resp.get("id") == 1 and "result" in resp:
                # 成功握手
                server_name = resp["result"].get("serverInfo", {}).get("name", "?")
                return True, f"握手成功 ({server_name})"
            if "error" in resp:
                return False, f"initialize error: {resp['error']}"

        return False, f"超时 ({timeout}s 内无响应)"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_fed_data_stdout_clean():
    """fed-data 的 stdout 应只包含 JSON-RPC 帧（之前含 banner 污染）。"""
    sp = MCP_SERVERS / "user_fed_data" / "server.py"
    if not sp.exists():
        pytest.skip(f"{sp} 不存在")
    ok, msg = _send_init_and_read(sp, timeout=10)
    assert ok, f"fed-data 握手失败: {msg}"


def test_wb_data_stdout_clean():
    """wb-data 的 stdout 应只包含 JSON-RPC 帧。"""
    sp = MCP_SERVERS / "user_wb_data" / "server.py"
    if not sp.exists():
        pytest.skip(f"{sp} 不存在")
    ok, msg = _send_init_and_read(sp, timeout=10)
    assert ok, f"wb-data 握手失败: {msg}"


def test_imf_data_stdout_clean():
    """imf-data 的 stdout 应只包含 JSON-RPC 帧。"""
    sp = MCP_SERVERS / "user_imf_data" / "server.py"
    if not sp.exists():
        pytest.skip(f"{sp} 不存在")
    ok, msg = _send_init_and_read(sp, timeout=10)
    assert ok, f"imf-data 握手失败: {msg}"


def test_nber_wp_stdout_clean():
    """nber-wp 的 stdout 应只包含 JSON-RPC 帧。"""
    sp = MCP_SERVERS / "user_nber_wp" / "server.py"
    if not sp.exists():
        pytest.skip(f"{sp} 不存在")
    ok, msg = _send_init_and_read(sp, timeout=10)
    assert ok, f"nber-wp 握手失败: {msg}"


def test_oecd_data_stdout_clean():
    """oecd-data 的 stdout 应只包含 JSON-RPC 帧。"""
    sp = MCP_SERVERS / "user_oecd_data" / "server.py"
    if not sp.exists():
        pytest.skip(f"{sp} 不存在")
    ok, msg = _send_init_and_read(sp, timeout=10)
    assert ok, f"oecd-data 握手失败: {msg}"


def test_bea_data_stdout_clean():
    """bea-data 的 stdout 应只包含 JSON-RPC 帧。"""
    sp = MCP_SERVERS / "user_bea_data" / "server.py"
    if not sp.exists():
        pytest.skip(f"{sp} 不存在")
    ok, msg = _send_init_and_read(sp, timeout=10)
    assert ok, f"bea-data 握手失败: {msg}"


def test_no_main_banner_print_to_stdout():
    """所有 server.py 的 main() 函数不应有 stdout print（只允许 stderr）。"""
    import re

    servers = list(MCP_SERVERS.glob("user_*/server.py"))
    assert len(servers) >= 20, f"只发现 {len(servers)} 个 server（应 >= 20）"

    # main() 内（4 空格缩进）的 print(... flush=True) 必须含 file=sys.stderr
    # 否则违规
    banner_pat = re.compile(r"^ {4}print\((?P<body>.+?),\s*flush=True\)\s*$", re.MULTILINE)
    violations = []
    for sp in servers:
        text = sp.read_text(encoding="utf-8")
        for m in banner_pat.finditer(text):
            line = m.group(0)
            if "file=sys.stderr" in line:
                continue  # 已修
            if "ERROR" in line or "error" in line.lower():
                continue  # ERROR print 是在 sys.exit(1) 前的顶层，不影响 stdio
            line_no = text.count("\n", 0, m.start()) + 1
            violations.append(f"{sp.name}:L{line_no}: {line.strip()[:80]}")
    assert not violations, (
        f"以下 server 仍有 stdout banner 污染:\n  " + "\n  ".join(violations)
    )


def test_mcp_healthcheck_script_exists():
    """mcp_healthcheck.py 必须存在且可执行。"""
    path = ROOT / "mcp_servers" / "mcp_healthcheck.py"
    assert path.exists(), f"{path} 不存在"
    text = path.read_text()
    assert text.startswith("#!/usr/bin/env python"), "缺 shebang"
    # 必须使用 mcp.client.stdio 或 asyncio.subprocess
    assert "ClientSession" in text or "stdio_client" in text, (
        "mcp_healthcheck.py 未实现 MCP stdio 客户端"
    )


def test_mcp_healthcheck_runs_against_fed_data():
    """mcp_healthcheck.py 实际能验证 fed-data。"""
    script = ROOT / "mcp_servers" / "mcp_healthcheck.py"
    if not script.exists():
        pytest.skip(f"{script} 不存在")
    server_dir = ROOT / "mcp_servers" / "user_fed_data"
    if not server_dir.exists():
        pytest.skip(f"{server_dir} 不存在")

    proc = subprocess.run(
        [_python_path(), str(script), "--server-dir", str(server_dir)],
        capture_output=True, text=True, timeout=15,
        cwd=str(ROOT),
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        f"mcp_healthcheck.py exit={proc.returncode}\n"
        f"stdout: {proc.stdout[:200]}\nstderr: {proc.stderr[:200]}"
    )
    assert "OK" in output or "✓" in output, (
        f"mcp_healthcheck.py 未报告成功:\n{output[:300]}"
    )


def test_health_check_uses_sys_executable():
    """health_check.py 必须用 sys.executable（而非 shutil.which）启动子进程。"""
    text = (ROOT / "scripts" / "health_check.py").read_text()
    assert "sys.executable" in text, (
        "health_check.py 未使用 sys.executable，可能误用 homebrew python3（缺 mcp）"
    )
    # 不应再用 shutil.which 作为默认（注释中提到除外）
    import re
    code = re.sub(r"#[^\n]*\n", "", text)  # 去注释行
    assert 'shutil.which("python3")' not in code, (
        "health_check.py 仍使用 shutil.which('python3')，可能导致子进程 mcp 缺失"
    )