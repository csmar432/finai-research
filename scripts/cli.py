#!/usr/bin/env python3
"""
FinAI Research Workflow · CLI 入口

提供 5 个用户级命令:
  - finai              : 主交互入口
  - finai-pipeline     : 启动研究流水线
  - finai-test         : 跑测试
  - finai-health       : 健康检查
  - finai-data         : 数据获取

设计原则:
  - 不强制任何 LLM 真实调用
  - 提供清晰的中文/英文帮助
  - 出错时给出修复建议
"""
import argparse
import sys
from pathlib import Path

# ── Banner ─────────────────────────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   FinAI Research Workflow · CLI                          ║
║   经济金融领域 AI 学术研究工作流                            ║
║                                                          ║
║   v1.0.0 · MIT License · 2026                            ║
║   49 MCP Servers · 49 Methods · 17 Skills                ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


def main() -> int:
    """主入口：自动路由到子命令。"""
    print(BANNER)
    parser = argparse.ArgumentParser(
        prog="finai",
        description="FinAI Research Workflow · 主 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── pipeline 子命令 ──────────────────────────────────────
    p_pipeline = subparsers.add_parser("pipeline", help="启动研究流水线")
    p_pipeline.add_argument("--topic", required=True, help="研究主题")
    p_pipeline.add_argument(
        "--journal",
        default="经济研究",
        choices=["经济研究", "金融研究", "管理世界", "JF", "JFE", "RFS", "JAE"],
        help="目标期刊",
    )
    p_pipeline.add_argument("--output-dir", default="./output", help="输出目录")
    p_pipeline.add_argument("--max-iter", type=int, default=3, help="最大迭代次数")

    # ── test 子命令 ──────────────────────────────────────────
    p_test = subparsers.add_parser("test", help="跑测试")
    p_test.add_argument("-x", "--exitfirst", action="store_true", help="遇错即停")
    p_test.add_argument("-k", "--keyword", help="只跑匹配的文件名")
    p_test.add_argument("--cov", action="store_true", help="显示覆盖率")

    # ── health 子命令 ────────────────────────────────────────
    subparsers.add_parser("health", help="系统健康检查")

    # ── data 子命令 ──────────────────────────────────────────
    p_data = subparsers.add_parser("data", help="数据获取")
    p_data.add_argument("--ticker", help="股票代码")
    p_data.add_argument(
        "--type", choices=["quote", "financial", "macro"], default="quote"
    )
    p_data.add_argument("--start", default="2024-01-01")
    p_data.add_argument("--end", default="2024-12-31")

    # ── lit-review 子命令 ────────────────────────────────────
    p_lit = subparsers.add_parser("lit-review", help="文献综述")
    p_lit.add_argument("--topic", required=True, help="研究主题")
    p_lit.add_argument("--max", type=int, default=20, help="最多返回几篇")
    p_lit.add_argument("--output", default="./output/lit-review.md")

    # ── version 子命令 ───────────────────────────────────────
    subparsers.add_parser("version", help="显示版本")

    args = parser.parse_args()

    # 默认命令：version
    if args.command is None:
        return version_cmd(None)

    # 路由
    commands = {
        "pipeline": pipeline_cmd,
        "test": test_cmd,
        "health": health_cmd,
        "data": data_cmd,
        "lit-review": lit_review_cmd,
        "version": version_cmd,
    }
    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


def pipeline_cmd_wrapper() -> int:
    """finai-pipeline 入口：打印提示并退出（避免误触发 LLM）。"""
    print("🚀 FinAI Research Workflow · 流水线")
    print()
    print("⚠️  流水线会调用 LLM API。请确认：")
    print("   1. .env 中已配置 DEEPSEEK_API_KEY")
    print("   2. 网络可达")
    print()
    print("实际启动：")
    print("   python scripts/agent_pipeline.py --topic '你的研究主题'")
    print()
    print("或交互式：")
    print("   python scripts/agent_pipeline.py --interactive")
    return 0


def pipeline_cmd(args) -> int:
    """启动研究流水线（仅作为子命令路由）。"""
    return pipeline_cmd_wrapper()


def test_cmd(args=None) -> int:
    """跑测试。入口点签名兼容无参调用。"""
    if args is None:
        # 无参调用：用默认参数
        args = type("Args", (), {"exitfirst": False, "keyword": None, "cov": False})()
    import subprocess

    print("🧪 跑测试套件")
    cmd = ["pytest", "tests/"]
    if args and getattr(args, "exitfirst", False):
        cmd.append("-x")
    if args and getattr(args, "keyword", None):
        cmd.extend(["-k", args.keyword])
    if args and getattr(args, "cov", False):
        cmd.extend(["--cov=scripts", "--cov-report=term-missing"])
    cmd.extend(["-v", "--tb=short"])
    print(f"   命令: {' '.join(cmd)}")
    return subprocess.call(cmd)


def health_cmd(args=None) -> int:
    """健康检查。入口点签名兼容无参调用。"""
    print("🔍 系统健康检查")
    print("🔍 系统健康检查")
    print()
    checks = [
        ("Python 版本", "3.10+", sys.version_info >= (3, 10)),
        ("scripts/ 目录", "./scripts", Path("scripts").exists()),
        ("tests/ 目录", "./tests", Path("tests").exists()),
        ("knowledge/skills/", "./knowledge/skills", Path("knowledge/skills").exists()),
        ("mcp_servers/", "./mcp_servers", Path("mcp_servers").exists()),
        (".env 文件", "./.env", Path(".env").exists() or Path(".env.example").exists()),
        ("pyproject.toml", "./pyproject.toml", Path("pyproject.toml").exists()),
    ]
    ok = 0
    for name, target, passed in checks:
        icon = "✅" if passed else "❌"
        print(f"  {icon}  {name:30s} {target}")
        if passed:
            ok += 1
    print()
    print(f"  汇总: {ok}/{len(checks)} 项通过")
    return 0 if ok == len(checks) else 1


def data_cmd(args) -> int:
    """数据获取演示。"""
    print("📊 数据获取演示")
    print(f"   类型: {args.type}")
    if args.ticker:
        print(f"   代码: {args.ticker}")
    print(f"   时间: {args.start} ~ {args.end}")
    print()
    print("💡 实际使用：")
    print("   from scripts.universal_data_fetcher import fetch_data")
    print("   df = fetch_data(ticker='000001.SZ', start='2024-01-01', end='2024-12-31')")
    return 0


def lit_review_cmd(args) -> int:
    """文献综述演示。"""
    print("📚 文献综述演示")
    print(f"   主题: {args.topic}")
    print(f"   最多: {args.max} 篇")
    print(f"   输出: {args.output}")
    print()
    print("💡 实际使用 skill: fin-lit-review")
    print("   或调用: from scripts.literature_download import run_lit_review")
    return 0


def version_cmd(args=None) -> int:
    """显示版本。"""
    try:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version", "?")
    except Exception:
        version = "1.0.0"
    print(f"FinAI Research Workflow v{version}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"平台: {sys.platform}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
