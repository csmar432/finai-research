#!/usr/bin/env python3
"""
科研智能体统一入口
==================
Usage:
    python scripts/agent.py                    # 交互模式
    python scripts/agent.py --goal "目标"    # 单次执行
    python scripts/agent.py --session "ID"   # 指定会话
    python scripts/agent.py --resume         # 恢复上次会话
    python scripts/agent.py --status        # 查看会话状态
    python scripts/agent.py --list          # 列出所有会话
    python scripts/agent.py --test          # 运行集成测试
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the Python path
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.core.session import ResearchSession, SessionConfig


def main():
    parser = argparse.ArgumentParser(description="经济类科研智能体")
    parser.add_argument("--goal", "-g", type=str, help="研究目标")
    parser.add_argument("--session", "-s", type=str, help="会话ID")
    parser.add_argument("--resume", "-r", action="store_true", help="恢复上次会话")
    parser.add_argument("--status", action="store_true", help="查看会话状态")
    parser.add_argument("--list", action="store_true", help="列出所有会话")
    parser.add_argument("--test", action="store_true", help="运行集成测试")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    if args.list:
        list_sessions()
        return

    if args.status:
        status_sessions()
        return

    if args.test:
        run_tests()
        return

    if args.resume:
        session_id = _get_last_session_id()
        if not session_id:
            print("❌ 未找到上次会话。请用 --goal 创建新会话。")
            return
        session = ResearchSession.resume(session_id)
        result = session.ask("继续上次的任务")
        _print_result(result)
        return

    # New session
    session_id = args.session or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not args.goal:
        print("❌ 请提供研究目标（--goal）。示例：")
        print("   python scripts/agent.py --goal '分析茅台2024年财务数据并生成研报'")
        print()
        print_examples()
        return

    config = SessionConfig(
        session_id=session_id,
        user_goal=args.goal,
        workspace_root=Path("."),
        auto_save=True,
        verbose=args.verbose,
    )
    session = ResearchSession(config)
    print(f"🚀 启动会话 {session_id}")
    print(f"📋 目标: {args.goal}")
    print()
    result = session.run(args.goal)
    _print_result(result)
    _save_last_session_id(session_id)


def _print_result(result: dict):
    """格式化打印结果"""
    print()
    print("=" * 60)
    print("📊 会话结果摘要")
    print("=" * 60)
    status = result.get("status")
    if hasattr(status, "state"):
        # SessionStatus dataclass
        print(f"会话ID: {result.get('session_id', 'N/A')}")
        print(f"状态:   {status.state.value if hasattr(status.state, 'value') else status.state}")
        print(f"完成任务: {status.completed_tasks}")
        print(f"失败任务: {status.failed_tasks}")
        avg = status.avg_score
        print(f"平均分:  {avg:.2f}/1.00" if avg is not None else "平均分:  N/A")
    else:
        print(f"会话ID: {result.get('session_id', 'N/A')}")
        print(f"状态:   {status if status else 'N/A'}")
        print(f"完成任务: {result.get('completed_tasks', 'N/A')}")
        print(f"失败任务: {result.get('failed_tasks', 'N/A')}")
        print(f"平均分:  {result.get('avg_score', 'N/A')}")
    print()
    print("📝 会话反思:")
    print(result.get("summary", "无"))
    print()


def list_sessions():
    """列出所有会话"""
    db_path = Path(".cache/research.db")
    if not db_path.exists():
        print("❌ 无历史会话。")
        return
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT session_id, updated_at, summary FROM sessions ORDER BY updated_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    if not rows:
        print("❌ 无历史会话。")
        return
    print("📁 历史会话:")
    for sid, updated_at, summary in rows:
        import time
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(updated_at))
        summary_short = (summary or "无")[:50]
        print(f"  {ts}  {sid}")
        print(f"          {summary_short}")


def status_sessions():
    """查看当前会话状态"""
    db_path = Path(".cache/research.db")
    if not db_path.exists():
        print("❌ 无活动会话。")
        return
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT session_id, updated_at, summary FROM sessions ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    if not rows:
        print("❌ 无活动会话。")
        return
    import time
    for sid, updated_at, summary in rows:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(updated_at))
        print(f"  {ts}  {sid}  {(summary or '无')[:40]}")


def run_tests():
    """运行所有核心模块测试"""
    import subprocess
    print("🧪 运行集成测试...")
    project_root = Path(__file__).parent.parent.resolve()
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "scripts/core/test_memory.py",
         "scripts/core/test_planner.py",
         "scripts/core/test_tool_selector.py",
         "scripts/core/test_reflector.py",
         "scripts/core/test_session.py",
         "-v", "--tb=short"],
        capture_output=True, text=True, cwd=str(project_root)
    )
    print(result.stdout)
    if result.returncode != 0:
        print("❌ 部分测试失败", file=sys.stderr)
    else:
        print("✅ 所有测试通过")
    sys.exit(result.returncode)


def print_examples():
    print("示例目标:")
    examples = [
        "分析茅台2024年财务数据并生成研报",
        "检索深度学习量化交易方向的最新文献，做综述",
        "设计一篇关于中美贸易摩擦对A股影响的学术论文大纲",
        "帮我分析苹果公司的ROE、毛利率和估值水平",
        "生成一份光伏行业的研究报告框架",
    ]
    for i, ex in enumerate(examples, 1):
        print(f"  {i}. {ex}")


def _get_last_session_id() -> str | None:
    path = Path(".cache/.last_session")
    if path.exists():
        return path.read_text().strip()
    return None


def _save_last_session_id(session_id: str):
    Path(".cache/.last_session").write_text(session_id)


if __name__ == "__main__":
    main()
