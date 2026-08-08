#!/usr/bin/env python3
"""5 轮渐进式主题澄清 · 统一研究入口 (Audit 2026-06-27).

解决问题：
  #1 主题确认不够细致 → 5 轮逐步澄清（ProgressiveClarifier）
  #2 出大纲后没同步 → 大纲门控（必须 ack）
  #10 生成文章没征询意见 → 整流为 gate-by-gate

使用：
    # 交互式：5 轮 input() 后打印下一步（默认不自动开跑）
    python scripts/start_research.py --topic "碳排放权交易对绿色创新的影响"

    # 澄清后继续进入写作流水线（显式 opt-in）
    python scripts/start_research.py --topic "..." --continue --use-hitl

    # 指定输出目录
    python scripts/start_research.py --topic "..." --output-dir ./research_001

    # 跳过澄清（不推荐，仅用于批处理）
    python scripts/start_research.py --topic "..." --skip-clarify

    # 恢复上次会话（断点续传）
    python scripts/start_research.py --resume --session-dir ./output/.clarify_session/
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
import time
from pathlib import Path

# Bootstrap
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.core.progressive_clarifier import (
    ProgressiveClarifier,
    ResearchProfile,
)
from scripts.core.platform import PROJECT_ROOT
from scripts.core.variable_redundancy import VariableRedundancyResolver
from scripts.core.data_gate import DataGate, DataGateLevel
from scripts.core.did_audit_guard import install_all_audit_guards

logger = logging.getLogger(__name__)


def _print_banner(msg: str, color: str = "36") -> None:
    """打印彩色横幅（ANSI）。"""
    print(f"\n\033[1;{color}m{'═' * 70}\033[0m")
    print(f"\033[1;{color}m  {msg}\033[0m")
    print(f"\033[1;{color}m{'═' * 70}\033[0m\n")


def cmd_new_research(args) -> int:
    """新建研究：5 轮逐步澄清 → 研究画像 → 下一步。"""
    topic = args.topic.strip()
    if not topic:
        print("❌ 主题不能为空")
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "output" / ".clarify_session"
    output_dir.mkdir(parents=True, exist_ok=True)

    _print_banner("主题澄清 · 5 轮逐步引导")
    print(f"  📌 主题: {topic}")
    print(f"  📂 会话目录: {output_dir}")
    print(f"  ⏱️  开始: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. 5 轮澄清（强制 5 轮）
    clarifier = ProgressiveClarifier(output_dir=output_dir, auto_ack=False, cli_mode=True)
    try:
        profile = clarifier.run_interactive(topic)
    except KeyboardInterrupt:
        print("\n  ⚠️  会话中止（已保存部分答案，可恢复）")
        return 130

    # 2. 落盘画像
    profile_path = output_dir / "research_profile.json"
    profile_path.write_text(json.dumps({
        "topic": profile.topic,
        "question_type": profile.question_type,
        "identification": profile.identification,
        "sample_window": profile.sample_window,
        "geography": profile.geography,
        "unit": profile.unit,
        "venue": profile.venue,
        "locked_at": profile.locked_at,
        "variables": {
            "dependent": [v.__dict__ for v in profile.variables.dependent],
            "independent": [v.__dict__ for v in profile.variables.independent],
            "control": [v.__dict__ for v in profile.variables.control],
            "policy_event": [v.__dict__ for v in profile.variables.policy_event],
        },
    }, ensure_ascii=False, indent=2))

    _print_banner("✅ 研究画像已锁定", "32")
    print(f"  📄 画像文件: {profile_path}")
    print(f"  🔬 类型: {profile.question_type}")
    print(f"  🧪 策略: {profile.identification}")
    print(f"  📅 窗口: {profile.sample_window or '(待定)'}")
    print(f"  🎯 期刊: {profile.venue}")

    # 2.5 变量冗余解析（PR2 集成：从画像自动补充候选变量）
    _print_banner("📊 变量冗余解析 · 自动化备选变量补充", "36")
    try:
        resolver = VariableRedundancyResolver(output_dir=output_dir)
        redundancy_report = resolver.resolve(profile)
        print(redundancy_report.summary())
        if redundancy_report.has_minimum_redundancy:
            print("\n  ✅ 变量冗余充足（因变量/自变量/控制变量/政策变量满足最小阈值）")
        else:
            print("\n  ⚠️  变量冗余不足，可能影响后续实证的备选方案")
            print("     建议：在文献综述后由 resolver 补充，或在 REFINED_DESIGN.md 中扩展")
    except Exception as exc:
        print(f"  ⚠️  变量冗余解析失败: {exc}")

    # 2.6 安装 DID 审计守卫（PR5 集成：拦截 mock 数据进入 DID）
    _print_banner("🛡️  DID 审计守卫 · 安装中", "36")
    guard_status = install_all_audit_guards()
    for engine_name, installed in guard_status.items():
        icon = "✅" if installed else "⚠️ "
        print(f"  {icon} {engine_name}")

    # 2.7 DataGate 状态报告（PR2 集成：验证数据是否就绪）
    _print_banner("🔍 DataGate 状态检查 · 写作前数据验证", "36")
    try:
        gate = DataGate(session_dir=output_dir, level=DataGateLevel.PROVENANCE)
        gate_result = gate.check()
        if gate_result.is_ready:
            print("  ✅ 数据验证通过，可以进入写作阶段")
        else:
            print("  🔴 数据未就绪 — 禁止自动进入写作阶段")
            print(f"     缺失项: {len(gate_result.missing)}")
            for m in gate_result.missing:
                print(f"       • {m}")
            if gate_result.warnings:
                print(f"     警告: {len(gate_result.warnings)}")
                for w in gate_result.warnings:
                    print(f"       ⚠️  {w}")
            print("\n     💡 解决方案:")
            print("       ① 补充数据后重新检查: python scripts/start_research.py --resume")
            print("       ② 或授权模拟数据: CLI_ACCEPT_RISK=1 python scripts/...")
            # Bug fix 2026-07-12: prior version only PRINTED the gate result and
            # gave users no way to interactively authorize synthetic data or skip.
            # Now we delegate to gate.prompt_user() which offers 3 actionable
            # choices in non-TTY / EOF-safe mode.
            try:
                print("\n     ── 进入交互式授权 ──")
                gate.prompt_user()
            except (EOFError, KeyboardInterrupt):
                print("\n     → EOF/Ctrl-C，跳过交互 (保留 blocked.json)")
    except Exception as exc:
        print(f"  ⚠️  DataGate 检查失败: {exc}")

    # 3. 下一步指引（默认不自动进入流水线；--continue 显式 opt-in）
    tq = shlex.quote(profile.topic)
    venue_arg = (
        f" --venue {shlex.quote(profile.venue)}"
        if profile.venue and profile.venue != "auto"
        else ""
    )
    print("\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  📋 下一步操作（需手动确认；或使用 --continue 一键进入写作流水线）：")
    print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print(f"  ① 文献综述：python scripts/literature_download.py {tq} --dry-run")
    print(f"  ② 新颖性验证：python scripts/agent_pipeline.py --topic {tq} --novelty-check")
    print(f"  ③ 实证设计 scaffold：python scripts/research_framework/pipeline.py --mode design --topic {tq}")
    print(f"  ④ 实证回归：python -m scripts.research_framework.enhanced_pipeline --topic {tq}")
    print(f"  ⑤ 端到端写作：python scripts/agent_pipeline.py --topic {tq}{venue_arg} --use-hitl")
    print()
    print(f"  📄 研究画像：{profile_path}")
    print("  💡 写作轨与实证轨分开：agent_pipeline 不跑 DID；实证用 enhanced_pipeline / modern_did。")
    print("  💡 HITL：agent_pipeline --use-hitl（默认停在 outline/literature/draft）。")
    print()

    if getattr(args, "continue_pipeline", False):
        return _continue_to_agent_pipeline(profile, args)

    return 0


def _continue_to_agent_pipeline(profile: ResearchProfile, args) -> int:
    """显式 --continue：把锁定画像交给 agent_pipeline（带 HITL 默认阶段）。"""
    _print_banner("继续进入写作流水线（agent_pipeline）", "32")
    from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

    hitl = bool(getattr(args, "use_hitl", True))
    config = AgentPipelineConfig(
        topic=profile.topic,
        venue=profile.venue if profile.venue and profile.venue != "auto" else "通用",
        use_hitl=hitl,
        hitl_stages=["outline", "literature", "draft"] if hitl else [],
    )
    out = args.output_dir or str(PROJECT_ROOT / "output" / "papers")
    pipeline = AgentPipeline(config=config)
    result = pipeline.run(topic=profile.topic, output_dir=out)
    return 0 if result.success else 1


def cmd_resume(args) -> int:
    """恢复 澄清会话。"""
    session_dir = Path(args.session_dir)
    if not session_dir.exists():
        print(f"❌ 会话目录不存在: {session_dir}")
        return 1

    clarifier = ProgressiveClarifier(output_dir=session_dir, auto_ack=False, cli_mode=True)
    try:
        state = clarifier.resume(session_dir)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    _print_banner("恢复 澄清会话")
    print(f"  📌 主题: {state.topic}")
    print(f"  📈 进度: {state.progress_pct}%")
    print(f"  🎯 当前阶段: {state.current_stage.value}")

    if state.is_complete:
        print("  ✅ 画像已锁定")
        return 0

    # 继续澄清（从已恢复的 state 继续，禁止 start() 清空进度）
    try:
        clarifier.run_interactive_from_state(state)
    except KeyboardInterrupt:
        return 130

    return 0


def cmd_skip_clarify(args) -> int:
    """跳过 5 轮澄清（仅用于批处理，不推荐）。"""
    print("\033[1;33m⚠️  警告：跳过 主题澄清，直接使用 --topic 作为研究画像。\033[0m")
    print("\033[1;33m   这将导致：\033[0m")
    print("\033[1;33m   - 因变量/自变量/控制变量只能靠文献综述自动挖掘\033[0m")
    print("\033[1;33m   - 识别策略默认为 multi（DID + IV + RDD）\033[0m")
    print("\033[1;33m   - 样本窗口默认 2010-2022\033[0m")
    print()
    confirm = input("确认跳过？[y/N]: ")
    if confirm.lower() != "y":
        print("已取消")
        return 0

    topic = args.topic.strip()
    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "output" / ".clarify_session"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 写出默认 profile
    profile = ResearchProfile(
        topic=topic,
        question_type="empirical",
        identification="multi",
        sample_window="2010-2022",
        venue="auto",
        locked_at=time.time(),
    )
    profile_path = output_dir / "research_profile.json"
    profile_path.write_text(json.dumps({
        "topic": profile.topic,
        "question_type": profile.question_type,
        "identification": profile.identification,
        "sample_window": profile.sample_window,
        "venue": profile.venue,
        "locked_at": profile.locked_at,
        "skipped_clarify": True,
    }, ensure_ascii=False, indent=2))

    print(f"\n  ✅ 默认画像已写入: {profile_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="研究入口（5 轮逐步澄清 → 研究画像 → 手动进入下一步）"
    )
    parser.add_subparsers(dest="command", required=False)

    # 默认行为：新建研究
    parser.add_argument("--topic", "-t", type=str, help="研究主题")
    parser.add_argument("--output-dir", "-o", type=str, help="会话产物目录")
    parser.add_argument("--skip-clarify", action="store_true", help="跳过 5 轮澄清（仅批处理）")
    parser.add_argument(
        "--continue",
        dest="continue_pipeline",
        action="store_true",
        help="澄清锁定后继续进入 agent_pipeline（显式 opt-in，默认不开）",
    )
    parser.add_argument(
        "--use-hitl",
        action="store_true",
        default=True,
        help="与 --continue 联用时启用 HITL（默认开启）",
    )
    parser.add_argument(
        "--no-hitl",
        action="store_false",
        dest="use_hitl",
        help="与 --continue 联用时关闭 HITL",
    )

    # 恢复
    parser.add_argument("--resume", action="store_true", help="恢复上次会话")
    parser.add_argument("--session-dir", type=str, help="会话目录路径")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.resume:
        if not args.session_dir:
            print("❌ --resume 必须配合 --session-dir")
            return 1
        return cmd_resume(args)

    if args.skip_clarify:
        if not args.topic:
            print("❌ --skip-clarify 必须配合 --topic")
            return 1
        return cmd_skip_clarify(args)

    if not args.topic:
        parser.print_help()
        return 0

    return cmd_new_research(args)


if __name__ == "__main__":
    sys.exit(main())
