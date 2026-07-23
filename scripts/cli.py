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
import os
import sys
from pathlib import Path

# ── Banner ─────────────────────────────────────────────────────────────
def _read_pyproject_version() -> str:
    """Read version from pyproject.toml (single source of truth).

    Fallback chain:
      1. tomllib load (Python 3.11+)
      2. tomli load (backport)
      3. regex extract from pyproject.toml
      4. importlib.metadata (installed package)
      5. hardcoded fallback (last resort)
    """
    try:
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                tomllib = None  # type: ignore[assignment]

        if tomllib is not None:
            from pathlib import Path as _P

            pyproject = _P(__file__).resolve().parent.parent / "pyproject.toml"
            if pyproject.exists():
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                v = data.get("project", {}).get("version")
                if v:
                    return str(v)
    except Exception:  # noqa: S110
        pass

    # Regex fallback (works on any pyproject.toml without tomllib)
    try:
        from pathlib import Path as _P
        import re

        pyproject = _P(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8")
            m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if m:
                return m.group(1)
    except Exception:  # noqa: S110
        pass

    # importlib.metadata fallback (when installed via pip)
    try:
        from importlib.metadata import version as _v

        return _v("finai-research-workflow")
    except Exception:  # noqa: S110
        pass

    return "0.0.0+unknown"


BANNER = f"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   FinAI Research Workflow · CLI                          ║
║   经济金融领域 AI 学术研究工作流                            ║
║                                                          ║
║   v{_read_pyproject_version()} · MIT License · 2026                     ║
║   43 MCP Servers · 47 Methods · 30 Journal Templates     ║
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


def pipeline_cmd_wrapper(argv: list[str] | None = None) -> int:
    """``finai-pipeline`` 入口：解析 ``--topic`` 等参数并启动流水线。

    这是从 PyPI wheel 安装后的主要入口路径。优先级：

    1. 如果传入了 ``--topic`` 等参数（或者在 wheel 安装后用户直接运行
       ``finai-pipeline --topic "..."``），调用 ``agent_pipeline.main()``。
    2. 如果没有参数但 ``sys.stdin`` 是 TTY（用户在 shell 里直接敲了
       ``finai-pipeline`` 而忘了加参数），打印友好的使用提示并退出 0。
    3. 如果没有参数且 stdin 不是 TTY（例如脚本里调用），按空 topic 调用
       ``agent_pipeline.main()``，让它走交互模式。
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="finai-pipeline",
        description="FinAI Research Workflow · 流水线入口（PyPI wheel 推荐调用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  finai-pipeline --topic '碳排放权交易与企业绿色创新'\n"
            "  finai-pipeline --topic 'CBAM 信息类型与高碳企业市场重估' --venue JFE\n"
            "  finai-pipeline --help\n"
        ),
    )
    parser.add_argument("--topic", help="研究主题")
    parser.add_argument(
        "--venue",
        "--journal",
        dest="venue",
        default="经济研究",
        choices=["经济研究", "金融研究", "管理世界", "JF", "JFE", "RFS", "JAE"],
        help="目标期刊",
    )
    parser.add_argument("--langgraph", action="store_true", help="使用 LangGraph 编排")
    parser.add_argument("--use-hitl", action="store_true", help="启用人工干预检查点")
    parser.add_argument("--language", choices=["zh", "en"], default="zh", help="输出语言")
    parser.add_argument("--output-dir", default="./output", help="输出目录")
    parser.add_argument("--novelty-check", action="store_true", help="强制做新颖性检查")
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="跳过启动时的健康检查（已通过 finai-doctor 验证时使用）",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互模式（即使 --topic 为空也启动）",
    )
    parser.add_argument(
        "--strict-llm",
        action="store_true",
        help="无 LLM 时直接退出码 4（默认行为；保留参数以兼容旧脚本）",
    )

    args = parser.parse_args(argv)

    if not args.topic and not args.interactive:
        # 用户忘了加参数：提示一下再退出。
        print("🚀 FinAI Research Workflow · 流水线")
        print()
        print("ℹ️  用法：finai-pipeline --topic '<研究主题>'")
        print()
        print("示例：")
        print("  finai-pipeline --topic '碳排放权交易与企业绿色创新'")
        print("  finai-pipeline --topic 'CBAM 信息类型与高碳企业市场重估' --venue JFE")
        print()
        print("💡 首次使用请先运行 `finai-doctor` 检查环境。")
        return 0

    # 委托给真正的流水线入口
    try:
        from scripts.agent_pipeline import main as pipeline_main
    except ImportError as exc:  # pragma: no cover - 极端情况
        print(f"❌ 无法导入 scripts.agent_pipeline: {exc}", file=sys.stderr)
        print("   请确认 finai-research-workflow 已正确安装。", file=sys.stderr)
        return 2

    forwarded = [
        "--topic", args.topic,
        "--venue", args.venue,
        "--language", args.language,
        "--output-dir", args.output_dir,
    ]
    if args.langgraph:
        forwarded.append("--langgraph")
    if args.use_hitl:
        forwarded.append("--use-hitl")
    if args.novelty_check:
        forwarded.append("--novelty-check")
    if args.skip_health:
        forwarded.append("--skip-health")
    if args.interactive:
        forwarded.append("--interactive")

    return pipeline_main(forwarded)


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
    version = _read_pyproject_version()
    print(f"FinAI Research Workflow v{version}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"平台: {sys.platform}")
    return 0


def doctor_cmd(argv: list[str] | None = None) -> int:
    """``finai-doctor`` 入口：诊断环境变量、.env、llm_config.json 来源。

    列出每个已知 API key 的最终解析值与来源，方便用户在"Claude 改了
    .env 但 health-check 还是找不到"等场景下快速定位问题。
    """
    print("🩺 FinAI Doctor · 环境诊断\n")

    # 1. 项目根解析
    try:
        from scripts.core.paths import resolve_project_root, find_env_file

        root = resolve_project_root()
        print(f"📁 项目根目录: {root}")
    except Exception as exc:  # pragma: no cover
        print(f"❌ 无法解析项目根目录: {exc}")
        return 2

    # 2. .env 文件查找
    print("\n📄 .env 文件查找：")
    for name in (".env", ".env.local"):
        path = find_env_file(name)
        if path:
            print(f"  ✅ {name}: {path}")
        else:
            print(f"  ⚪ {name}: 未找到")

    # 3. 关键 API key 来源追踪
    print("\n🔑 关键 API key 来源追踪：")
    keys = [
        "DEEPSEEK_API_KEY",
        "RELAY_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TUSHARE_TOKEN",
        "EODHD_API_KEY",
        "FRED_API_KEY",
        "BRAVE_SEARCH_API_KEY",
        "NEWSAPI_API_KEY",
        "E2B_API_KEY",
    ]
    from scripts.core.paths import find_env_file as _fef

    for key in keys:
        sources = []
        # os.environ
        env_val = os.environ.get(key, "")
        if env_val:
            sources.append(("os.environ", _mask(env_val)))
        # .env.local
        for env_name in (".env.local", ".env"):
            env_path_obj = _fef(env_name)
            if env_path_obj:
                dot_val = _read_dotenv_value(env_path_obj, key)
                if dot_val:
                    sources.append((env_name, _mask(dot_val)))
        # config/llm_config.json
        llm_cfg = root / "config" / "llm_config.json"
        cfg_val = _read_llm_config_value(llm_cfg, key) if llm_cfg.is_file() else ""
        if cfg_val and not cfg_val.startswith("$"):
            sources.append(("config/llm_config.json", _mask(cfg_val)))

        if sources:
            line = "  ✅ " + key + "："
            line += " | ".join(f"{src}={val}" for src, val in sources)
            print(line)
        else:
            print(f"  ⚪ {key}: 未设置")

    # 4. LLM 路由就绪状态
    print("\n🤖 LLM 路由就绪状态：")
    try:
        from scripts.ai_router import AI  # noqa: F401

        ai = AI()
        status = ai.status() if hasattr(ai, "status") else "unknown"
        if isinstance(status, dict):
            available = [k for k, v in status.items() if v]
            print(f"  可用模型: {available or '无'}")
        else:
            print(f"  AI.status() 返回: {status}")
    except Exception as exc:
        print(f"  ⚠️  AI router 初始化失败: {exc}")

    # 5. 总结与建议
    print("\n📋 总结：")
    has_deepseek = False
    for src in (".env", ".env.local"):
        env_path_obj = _fef(src)
        if env_path_obj and _read_dotenv_value(env_path_obj, "DEEPSEEK_API_KEY"):
            has_deepseek = True
            break
    if not has_deepseek and os.environ.get("DEEPSEEK_API_KEY"):
        has_deepseek = True
    if has_deepseek:
        print("  ✅ 已检测到 LLM 配置。可运行 finai-pipeline --topic '...' 启动流水线。")
        return 0
    print("  ⚠️  未检测到 LLM 配置。建议：")
    print("     1. 创建 .env 并写入 DEEPSEEK_API_KEY=sk-...")
    print("     2. 或运行 `ollama serve` 启用本地模型")
    print("     3. 详见 INSTALL.md")
    return 4


def _mask(value: str, head: int = 4, tail: int = 4) -> str:
    """部分掩码 API key。"""
    if not value or len(value) <= head + tail + 3:
        return "***"
    return f"{value[:head]}...{value[-tail:]}"


def _read_dotenv_value(env_path, key: str) -> str:
    """从 .env 文件读取指定 key 的值（不解析为环境变量）。"""
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k == key:
                return v
    except Exception:  # noqa: S110
        pass
    return ""


def _read_llm_config_value(json_path, key: str) -> str:
    """从 config/llm_config.json 读取与 key 对应的 provider 的 api_key。"""
    try:
        import json

        data = json.loads(json_path.read_text(encoding="utf-8"))
        # key 形如 DEEPSEEK_API_KEY，映射到 deepseek.api_key
        provider = key.replace("_API_KEY", "").replace("_TOKEN", "").lower()
        provider_cfg = data.get(provider, {})
        return str(provider_cfg.get("api_key", "") or "")
    except Exception:  # noqa: S110
        return ""


if __name__ == "__main__":
    sys.exit(main())
