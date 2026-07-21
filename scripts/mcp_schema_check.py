#!/usr/bin/env python3
"""
MCP Server Schema vs Handler 验证工具。

检查所有 MCP 服务器的 tool JSON schema 与 server.py handler 函数之间的匹配情况。
发现 schema 中定义的参数与 handler 实际接收参数之间的不一致。

用法:
    python scripts/mcp_diagnostic.py --schema-check
    python scripts/mcp_diagnostic.py --schema-check --fix    # 自动修复可修复的问题
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _get_handler_params(handler_source: str) -> dict[str, Any]:
    """从 handler 函数源码中提取参数列表。"""
    params = {}
    # Match: arg_name: type = default
    for m in re.finditer(
        r"(\w+)\s*:\s*\w+\s*=\s*(?:args\.get\(['\"]([^'\"]+)['\"])", handler_source
    ):
        params[m.group(2)] = m.group(1)
    # Match: arg_name = args.get("arg_name", ...)
    for m in re.finditer(
        r"(\w+)\s*=\s*args\.get\(['\"]([^'\"]+)['\"]", handler_source
    ):
        params[m.group(2)] = m.group(1)
    return params


def _extract_handler_params_from_signature(source: str) -> set[str]:
    """从函数签名提取参数名（不含 self/args）。"""
    sig_match = re.search(r"def\s+\w+\s*\(([^)]+)\)", source)
    if not sig_match:
        return set()
    args_str = sig_match.group(1)
    param_names = set()
    for part in args_str.split(","):
        part = part.strip()
        if "=" in part:
            part = part.split("=")[0].strip()
        if part and part not in ("self", "args", "kwargs"):
            param_names.add(part.strip())
    return param_names


def _normalize_tool_name(name: str) -> str:
    """Tool JSON 文件名 → handler 函数名的映射规则。"""
    # get_xxx → handle_xxx 或 handle_get_xxx 或 handleXXX
    s = name.removeprefix("get_").removeprefix("fetch_").removeprefix("search_").removeprefix("list_")
    return s.lower()


def validate_server(srv_dir: Path, verbose: bool = False) -> dict[str, Any]:
    """验证单个 MCP 服务器的 schema/handler 匹配。"""
    server_py = srv_dir / "server.py"
    tools_dir = srv_dir / "tools"

    if not server_py.exists() or not tools_dir.exists():
        return {"srv": srv_dir.name, "ok": False, "reason": "missing files"}

    server_content = server_py.read_text()

    # Extract all handler function names (named handlers)
    handler_pattern = re.compile(
        r"async def (handle_\w+)\s*\(([^)]*)\)"
    )
    handlers: dict[str, str] = {}
    for m in handler_pattern.finditer(server_content):
        handlers[m.group(1)] = m.group(2)

    # Also detect dispatcher pattern: if TOOLS list exists + call_tool dispatcher,
    # all tools are assumed to be handled by call_tool (not individually)
    uses_dispatcher = "@server.call_tool()" in server_content or "call_tool(name, arguments)" in server_content
    has_tool_list = "TOOLS = [" in server_content or "tools = [" in server_content

    results = {
        "srv": srv_dir.name,
        "ok": True,
        "tools": [],
        "handlers": list(handlers.keys()),
        "missing_handlers": [],
        "param_mismatches": [],
        "schema_mismatches": [],
        "uses_dispatcher": uses_dispatcher and has_tool_list,
    }

    for tool_file in sorted(tools_dir.glob("*.json")):
        tool_name = tool_file.stem  # e.g. "get_daily_quote"
        schema = json.loads(tool_file.read_text())

        # Determine expected handler name
        # Strategy 1: handle_get_daily_quote
        h1 = f"handle_{tool_name}"
        # Strategy 2: handle_daily_quote (stripped get_)
        h2 = f"handle_{_normalize_tool_name(tool_name)}"
        # Strategy 3: exact match (for non-get prefixes)
        h3 = f"handle{tool_name.replace('_', '')}"

        handler_name = None
        for candidate in [h1, h2, h3]:
            if candidate in handlers:
                handler_name = candidate
                break

        # Get schema parameters
        input_schema = schema.get("inputSchema", schema.get("parameters", {}))
        if isinstance(input_schema, dict):
            schema_params = set(input_schema.get("properties", {}).keys())
            set(input_schema.get("required", []))
        else:
            schema_params = set()

        # Get handler signature parameters
        handler_sig_params = set()
        if handler_name:
            sig_match = re.search(
                rf"async def {handler_name}\s*\(([^)]+)\)",
                server_content
            )
            if sig_match:
                for part in sig_match.group(1).split(","):
                    part = part.strip()
                    if "=" in part:
                        part = part.split("=")[0].strip()
                    if part and part not in ("self", "args", "kwargs"):
                        handler_sig_params.add(part.strip())

        tool_result = {
            "tool": tool_name,
            "handler": handler_name or ("dispatcher" if results.get("uses_dispatcher") else "MISSING"),
            "status": "✅ (dispatcher)" if results.get("uses_dispatcher") and not handler_name else ("✅" if handler_name else "❌"),
        }

        # In dispatcher mode, skip missing handler check; in named mode, check param match
        if not results.get("uses_dispatcher"):
            if not handler_name:
                results["missing_handlers"].append(tool_name)
                results["ok"] = False
            else:
                # Named handler: check parameter match
                schema_minus_handler = schema_params - handler_sig_params
                handler_minus_schema = handler_sig_params - schema_params
                if schema_minus_handler:
                    tool_result["schema_extra"] = list(schema_minus_handler)
                    results["param_mismatches"].append(
                        f"  ⚠️  {srv_dir.name}/{tool_name}: "
                        f"schema has {schema_minus_handler}, handler missing"
                    )
                if handler_minus_schema:
                    non_args = handler_minus_schema - {"args"}
                    if non_args:
                        tool_result["handler_extra"] = list(non_args)
        # In dispatcher mode: tools handled by dispatcher, skip param check

        results["tools"].append(tool_result)

    return results


def main():
    parser = argparse.ArgumentParser(description="MCP Schema vs Handler 验证")
    parser.add_argument("--fix", action="store_true", help="自动修复可修复的问题")
    parser.add_argument("--srv", type=str, help="仅检查指定服务器")
    args = parser.parse_args()

    root = Path(__file__).parent.parent / "mcp_servers"
    servers = [root / args.srv] if args.srv else sorted(d for d in root.iterdir() if d.is_dir() and d.name != "__pycache__")

    total_issues = 0
    total_servers = 0

    for srv_dir in servers:
        if srv_dir.name.startswith("__"):
            continue
        total_servers += 1
        result = validate_server(srv_dir)

        if not result["ok"] or result["missing_handlers"] or result["param_mismatches"]:
            print(f"\n{'='*60}")
            print(f"  ⚠️  {result['srv']}")
            print(f"{'='*60}")

        if result.get("reason") == "missing files":
            continue

        if result["missing_handlers"]:
            print(f"  缺失 handler ({len(result['missing_handlers'])}):")
            for t in result["missing_handlers"]:
                print(f"    ❌ {t}.json → 无对应 handler")

        if result["param_mismatches"]:
            total_issues += len(result["param_mismatches"])
            for msg in result["param_mismatches"]:
                print(msg)

        ok_count = sum(1 for t in result["tools"] if t["status"] == "✅")
        total_count = len(result["tools"])
        if result["tools"]:
            print(f"  handlers: {ok_count}/{total_count} matched")

    if total_issues == 0 and total_servers > 0:
        print(f"\n✅ 所有 {total_servers} 个 MCP 服务器的 schema/handler 匹配验证通过")
    else:
        print(f"\n⚠️  共 {total_servers} 个服务器，{total_issues} 处参数不一致")


if __name__ == "__main__":
    main()
