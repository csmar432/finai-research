#!/usr/bin/env python3
"""mcp_healthcheck.py — MCP server 健康检查（用 MCP 官方客户端库）.

对 stdio-based MCP 服务器执行 initialize 握手，
超时或失败返回 1，否则返回 0。

参考：https://github.com/modelcontextprotocol/python-sdk

用法：
  python mcp_healthcheck.py --server-dir <path> [--timeout 10]

退出码：
  0 = healthy（initialize 成功，返回 protocolVersion + serverInfo）
  1 = unhealthy（启动失败 / 超时 / 协议错误）
  2 = 配置错误
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def healthcheck_async(server_dir: Path, timeout: float = 10.0) -> tuple[bool, str]:
    """对 server_dir/server.py 执行 MCP initialize 握手。

    Args:
        server_dir: MCP server 目录（含 server.py）
        timeout: 总超时秒数

    Returns:
        (healthy, message)
    """
    server_py = server_dir / "server.py"
    if not server_py.exists():
        return False, f"{server_py} 不存在"

    # 延迟 import：MCP 客户端库可能在某些环境未安装
    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError as e:
        return False, f"MCP 客户端库未安装: {e}"

    # server.py 路径相对 server_dir
    server_py_rel = "server.py"
    params = StdioServerParameters(
        command=sys.executable,
        args=[server_py_rel],
        cwd=str(server_dir.resolve()),
    )

    try:
        async with asyncio.timeout(timeout):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    init_result = await session.initialize()
                    server_name = (
                        init_result.serverInfo.name
                        if init_result.serverInfo
                        else "unknown"
                    )
                    return True, f"protocol={init_result.protocolVersion} server={server_name}"
    except TimeoutError:
        return False, f"超时（{timeout}s）"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP server 健康检查")
    parser.add_argument(
        "--server-dir",
        type=Path,
        required=True,
        help="MCP server 目录（应含 server.py）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="总超时秒数（默认 10）",
    )
    args = parser.parse_args()

    if not args.server_dir.is_dir():
        print(f"[healthcheck] FAIL: {args.server_dir} 不是目录", file=sys.stderr)
        return 2

    healthy, msg = asyncio.run(healthcheck_async(args.server_dir, args.timeout))
    if healthy:
        print(f"[healthcheck] OK: {args.server_dir.name} ({msg})")
        return 0
    print(f"[healthcheck] FAIL: {args.server_dir.name} — {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
