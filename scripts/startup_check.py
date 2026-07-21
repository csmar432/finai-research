#!/usr/bin/env python3
"""Startup Preflight Check (PR6, Audit 2026-06-27).

在 start_research.py 之前运行，快速诊断系统是否就绪。

使用：
    python scripts/startup_check.py           # 标准检查
    python scripts/startup_check.py --fix     # 提供修复建议
    python scripts/startup_check.py --json   # JSON 输出（供 CI 解析）
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT))


@dataclass
class CheckItem:
    category: str
    name: str
    status: str          # "✅" | "❌" | "⚠️ "
    message: str
    fix_hint: str = ""


def check_python_version() -> CheckItem:
    import sys
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    return CheckItem(
        category="环境",
        name="Python 版本",
        status="✅" if ok else "❌",
        message=f"Python {v.major}.{v.minor}.{v.micro}",
        fix_hint="需要 Python 3.10+，建议使用 conda 或 pyenv",
    )


def check_llm_keys() -> list[CheckItem]:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env.local", override=False)
    import os

    items = []
    keys = {
        "DEEPSEEK_API_KEY": "DeepSeek（中文写作/分析，可选）",
        "RELAY_API_KEY": "Relay（英文写作/GPT/Claude，可选）",
        "OLLAMA_ENABLED": "Ollama（本地模型，无网时兜底）",
    }
    for key, desc in keys.items():
        val = os.getenv(key, "").strip()
        if key == "OLLAMA_ENABLED":
            status = "✅" if val.lower() != "false" else "⚠️ "
            message = f"Ollama {'已启用' if val.lower() != 'false' else '未启用（可跳过，有 DeepSeek）'}"
        else:
            status = "✅" if val and not val.startswith("YOUR_") else "❌"
            message = f"{'已配置' if status == '✅' else '未配置'}: {desc}"
        items.append(CheckItem(
            category="LLM",
            name=key,
            status=status,
            message=message,
            fix_hint=f"在 .env.local 中设置 {key}" if status == "❌" else "",
        ))
    return items


def check_mcp_servers() -> list[CheckItem]:
    items = []
    critical_mcp = [
        ("user-yfinance", "美股行情/ETF/期权（免费）"),
        ("user-financial", "中国宏观数据（GDP/CPI/M2，免费）"),
        ("user-openalex", "学术论文元数据（免费）"),
        ("user-eastmoney-reports", "东方财富研报/新闻（免费）"),
        ("user-tushare", "A股数据（需 TUSHARE_TOKEN）"),
    ]
    mcp_config = _PROJECT_ROOT / ".cursor" / "mcp.json"
    configured_servers = set()
    if mcp_config.exists():
        try:
            data = json.loads(mcp_config.read_text())
            if "mcpServers" in data:
                configured_servers = set(data["mcpServers"].keys())
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
            print(f"  ⚠️  无法解析 .cursor/mcp.json: {exc}")

    for server, desc in critical_mcp:
        is_configured = server in configured_servers
        status = "✅" if is_configured else "⚠️ "
        items.append(CheckItem(
            category="MCP",
            name=server,
            status=status,
            message=f"{'已注册' if is_configured else '未注册'}: {desc}",
            fix_hint=f"运行: python scripts/register_mcp_servers.py" if not is_configured else "",
        ))
    return items


def check_latex() -> list[CheckItem]:
    items = []
    backends = ["tectonic", "xelatex", "pdflatex", "lualatex", "pandoc"]
    found = []
    for be in backends:
        path = shutil.which(be)
        if path:
            found.append(f"{be} → {path}")

    if "tectonic" in str(found):
        status = "✅"
        message = f"tectonic 可用（推荐）"
    elif found:
        status = "⚠️ "
        message = f"可用: {', '.join(found)}（无 tectonic，建议安装）"
    else:
        status = "❌"
        message = "无 LaTeX 编译器"
    items.append(CheckItem(
        category="LaTeX",
        name="编译器",
        status=status,
        message=message,
        fix_hint="安装 tectonic: brew install tectonic（推荐）或 brew install --cask mactex",
    ))

    # 检查字体
    import subprocess as sp
    try:
        result = sp.run(["fc-list", ":lang=zh"], capture_output=True, text=True, timeout=5)
        fonts = [l.strip().split(":")[0] for l in result.stdout.strip().splitlines() if l.strip()]
        if fonts:
            items.append(CheckItem(
                category="LaTeX",
                name="中文字体",
                status="✅",
                message=f"已安装: {fonts[0]}{'等' if len(fonts)>1 else ''}",
            ))
        else:
            items.append(CheckItem(
                category="LaTeX",
                name="中文字体",
                status="⚠️ ",
                message="fc-list 未找到中文字体（macOS 自带字体可能未注册到 fontconfig）",
                fix_hint="macOS 自带 STHeiti/Songti，xelatex 可用；tectonic 使用 ctex 宏包自动处理",
            ))
    except Exception:
        items.append(CheckItem(
            category="LaTeX",
            name="中文字体",
            status="⚠️ ",
            message="无法检测字体（fc-list 不可用）",
            fix_hint="tectonic + ctex 宏包可自动处理",
        ))
    return items


def check_did_audit() -> CheckItem:
    from scripts.core.did_audit_guard import DID_AUDIT_ENABLED
    return CheckItem(
        category="审计",
        name="DID Audit Guard",
        status="✅" if DID_AUDIT_ENABLED else "⚠️ ",
        message=f"DID 审计{'已开启' if DID_AUDIT_ENABLED else '已关闭'}",
        fix_hint="DID_AUDIT_ENABLED=false 可关闭（仅测试用）",
    )


def run_all_checks() -> list[CheckItem]:
    items = []
    items.append(check_python_version())
    items.append(check_did_audit())
    items.extend(check_llm_keys())
    items.extend(check_mcp_servers())
    items.extend(check_latex())
    return items


def print_report(items: list[CheckItem], fix: bool = False, json_output: bool = False):
    if json_output:
        data = [{"category": i.category, "name": i.name,
                 "status": i.status, "message": i.message,
                 "fix_hint": i.fix_hint} for i in items]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print("\n" + "═" * 65)
    print("  系统启动预检")
    print("═" * 65)

    by_category = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)

    for cat, cat_items in by_category.items():
        print(f"\n  【{cat}】")
        for item in cat_items:
            print(f"  {item.status} {item.name}")
            print(f"     {item.message}")
            if fix and item.fix_hint:
                print(f"     💡 {item.fix_hint}")

    passed = sum(1 for i in items if i.status == "✅")
    warn = sum(1 for i in items if i.status == "⚠️ ")
    failed = sum(1 for i in items if i.status == "❌")

    print(f"\n  {'─' * 65}")
    print(f"  总结: ✅ {passed} 通过  ⚠️  {warn} 警告  ❌ {failed} 失败")
    print("═" * 65 + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="系统启动预检")
    parser.add_argument("--fix", action="store_true", help="显示修复建议")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    items = run_all_checks()
    print_report(items, fix=args.fix, json_output=args.json)

    failed = [i for i in items if i.status == "❌"]
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
