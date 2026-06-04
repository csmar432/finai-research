#!/usr/bin/env python3
"""
on-enter.py — 自动唤醒 FinResearch 工作流

当用户 cd 进入本目录时，由 .zshrc hook 自动调用。
显示：
  1. 今日宏观日历（NFP/CPI/FOMC/PMI）
  2. 最近的财报发布
  3. 快捷操作菜单（输入数字即可执行）
  4. 当前守护进程状态

Usage (add to ~/.zshrc):
  cd <本项目根目录> && source scripts/on_enter_hook.sh
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _get_macro_today() -> list[dict]:
    """Return today's macro events and upcoming releases."""
    today = date.today()
    events = []

    # NFP: first Friday of month
    first_friday = today
    day = date(today.year, today.month, 1)
    while day.weekday() != 4:
        day += timedelta(days=1)
    first_friday = day
    if first_friday >= today:
        events.append({
            "name": "US NFP",
            "date": first_friday.strftime("%m/%d"),
            "days": (first_friday - today).days,
            "status": "upcoming",
        })

    # CPI: ~10-14th of month
    if today.day < 10:
        events.append({
            "name": "US CPI",
            "date": f"{today.year}/{today.month:02d}/10-14",
            "days": 10 - today.day,
            "status": "upcoming",
        })
    elif 10 <= today.day <= 14:
        events.append({
            "name": "US CPI",
            "date": f"{today.year}/{today.month:02d}/{today.day:02d}",
            "days": 0,
            "status": "TODAY",
        })

    # FOMC: approximate (every 6 weeks on Wednesday)
    fomc_dates = []
    fomc = date(today.year, 1, 1)
    while fomc.weekday() != 2:
        fomc += timedelta(days=1)
    while fomc <= today:
        fomc += timedelta(weeks=6)
    if fomc <= today + timedelta(days=42):
        events.append({
            "name": "US FOMC",
            "date": fomc.strftime("%m/%d Wed"),
            "days": (fomc - today).days,
            "status": "today" if fomc == today else "upcoming",
        })

    # CN PMI: ~first business day of month
    if today.day <= 5:
        events.append({
            "name": "CN PMI",
            "date": f"{today.year}/{today.month:02d}/01",
            "days": 1 - today.day if today.day > 1 else 0,
            "status": "today" if today.day == 1 else "upcoming",
        })
    else:
        # Next month PMI
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        events.append({
            "name": "CN PMI",
            "date": f"{next_year}/{next_month:02d}/01",
            "days": "next month",
            "status": "upcoming",
        })

    return events


def _check_daemon() -> dict:
    """Check if the event monitor daemon is running."""
    pid_file = PROJECT_ROOT / "data" / "event_monitor.pid"
    state_file = PROJECT_ROOT / "data" / "event_trigger_state.json"

    status = {"daemon_running": False, "pid": None, "last_run": None}

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, 0)
                status["daemon_running"] = True
                status["pid"] = pid
            except OSError:
                status["daemon_running"] = False
        except (ValueError, OSError):
            pass

    if state_file.exists():
        try:
            with open(state_file, encoding="utf-8") as f:
                state = json.load(f)
            items = list(state.items())
            if items:
                last_key, last_val = items[-1]
                status["last_run"] = last_val.get("timestamp", "")
        except Exception:
            pass

    return status


def _get_pending_approvals() -> int:
    """Count pending pipeline approvals."""
    state_file = PROJECT_ROOT / "data" / "event_trigger_state.json"
    if not state_file.exists():
        return 0
    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
        return len(state.get("pending", {}))
    except Exception:
        return 0


def _get_running_pipelines() -> int:
    """Count running pipeline threads."""
    try:
        from scripts.event_monitor import get_running_pipelines
        return len(get_running_pipelines())
    except Exception:
        return 0


def print_banner() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print(f"  ┌──────────────────────────────────────────────────────┐")
    print(f"  │  论文-研报工作流 · FinResearch Agent              │")
    print(f"  │  {ts:<52}│")
    print(f"  └──────────────────────────────────────────────────────┘")
    print()
    print(f"  告诉我想研究什么主题，我来帮你完成从文献到论文的全流程。")
    print()


def print_macro_calendar(events: list[dict]) -> None:
    print(f"  📅 宏观日历")
    print(f"  {'─' * 52}")
    for ev in events:
        if ev["days"] == 0:
            days_str = "今天!"
            color = "\033[92m"  # green
        elif isinstance(ev["days"], int) and ev["days"] <= 3:
            days_str = f"{ev['days']} 天后"
            color = "\033[93m"  # yellow
        else:
            days_str = f"{ev['days']} 天"
            color = ""
        reset = "\033[0m"
        print(f"  {color}{ev['name']:<14}{ev['date']:<14}{days_str:<12}{reset}{ev['status']}")
    print()


def print_status(daemon: dict) -> None:
    print(f"  🔔  系统状态")
    print(f"  {'─' * 48}")
    if daemon["daemon_running"]:
        print(f"  守护进程:   ✅ 运行中 (PID {daemon['pid']})")
    else:
        print(f"  守护进程:   ⚠️  未运行")
    running = _get_running_pipelines()
    if running > 0:
        print(f"  Pipeline:   🔄 {running} 个运行中")
    pending = _get_pending_approvals()
    if pending > 0:
        print(f"  待审批:     ⏳ {pending} 个待审批")
    if daemon["last_run"]:
        print(f"  最近触发:  {daemon['last_run']}")
    print()


def print_menu() -> None:
    print(f"  ⚡ 快捷操作（输入数字回车）")
    print(f"  {'─' * 52}")
    print(f"  1) 🔍  扫描事件（--test）")
    print(f"  2) ▶️   启动监控（--interval 300）")
    print(f"  3) 📅  日历感知调度（--macro-scheduler）")
    print(f"  4) ⏰  每日调度（08:00/13:30/20:00）")
    print(f"  5) 🚀  自动触发模式")
    print(f"  6) 📋  查看待审批任务")
    print(f"  7) 📊  状态面板")
    print(f"  8) 🛠️   安装守护进程（macOS/Linux）")
    print(f"  9) 📖  帮助文档")
    print(f"  R) 📝  输入研究主题 → 直接启动完整论文流程")
    print(f"  0)  退出")
    print()


def run_action(choice: str) -> bool:
    """Execute the chosen action. Returns True to continue, False to exit."""
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = sys.executable

    em = PROJECT_ROOT / "scripts" / "event_monitor.py"
    daemon_status = _check_daemon()

    if choice == "1":
        print(f"\n  🔍 执行事件扫描...\n")
        subprocess.run([str(venv_python), str(em), "--test"], cwd=PROJECT_ROOT)
    elif choice == "2":
        print(f"\n  ▶️  启动持续监控 (Ctrl+C 停止)...\n")
        subprocess.run([str(venv_python), str(em), "--interval", "300"], cwd=PROJECT_ROOT)
    elif choice == "3":
        print(f"\n  📅  启动日历感知调度...\n")
        subprocess.run([str(venv_python), str(em), "--macro-scheduler"], cwd=PROJECT_ROOT)
    elif choice == "4":
        print(f"\n  ⏰  每日调度 08:00 / 13:30 / 20:00...\n")
        subprocess.run([str(venv_python), str(em), "--scheduler", "08:00,13:30,20:00"], cwd=PROJECT_ROOT)
    elif choice == "5":
        print(f"\n  🚀  自动触发模式（发现事件即运行）...\n")
        subprocess.run([str(venv_python), str(em), "--auto-trigger", "--macro-scheduler"], cwd=PROJECT_ROOT)
    elif choice == "6":
        print(f"\n  📋  待审批任务:\n")
        subprocess.run([str(venv_python), str(em), "--list-pending"])
        print()
        pending_list = _get_pending_approvals()
        if pending_list > 0:
            run_id = input("  输入 run_id 批准（或回车返回）: ").strip()
            if run_id:
                subprocess.run([str(venv_python), str(em), "--approve", run_id])
    elif choice == "7":
        print(f"\n  📊  状态面板:\n")
        subprocess.run([str(venv_python), str(em), "--status"])
    elif choice == "8":
        setup_script = PROJECT_ROOT / "config" / "daemon" / "setup-daemon.sh"
        if setup_script.exists():
            print(f"\n  🛠️  运行守护进程安装脚本...\n")
            subprocess.run(["bash", str(setup_script)], cwd=PROJECT_ROOT)
        else:
            print(f"  ❌ 安装脚本未找到: {setup_script}")
    elif choice == "9":
        print(f"\n  📖  使用指南:\n")
        print(f"  1. 修改 ~/.zshrc 添加以下行（自动唤醒）:")
        proj = str(PROJECT_ROOT).replace(" ", "\\ ")
        print(f"")
        print(f"     cd {proj} && source scripts/on_enter_hook.sh\n")
        print(f"  2. 可选安装守护进程（后台运行，开机自启）:")
        print(f"     bash {PROJECT_ROOT}/config/daemon/setup-daemon.sh macos\n")
        print(f"  3. 查看帮助:")
        print(f"     python scripts/event_monitor.py --help\n")
    elif choice.upper() == "R":
        print(f"\n  📝 请输入你的研究主题（直接粘贴或描述）:")
        topic = input("  > ").strip()
        if topic:
            print(f"\n  🎯 启动完整论文流程：{topic}\n")
            print(f"  正在加载...（你也可以直接在 Cursor 聊天框输入相同内容）")
            # Open the topic in a readable way
            print(f"\n  复制以下内容到 Cursor 聊天框启动完整流程：")
            print(f"  {'─' * 50}")
            print(f"  Skill: fin-full-pipeline \"{topic}\"")
            print(f"  {'─' * 50}")
            # Also try to launch via subprocess
            try:
                subprocess.run(
                    [str(venv_python), "-c",
                     f"import sys; sys.path.insert(0,'{PROJECT_ROOT}'); "
                     f"from scripts.research_framework.enhanced_pipeline import EnhancedPipeline; "
                     f"pl = EnhancedPipeline(topic='{topic}', output_dir='output/fin-manuscript', "
                     f"enable_modern_did=True, enable_validation_gates=True, "
                     f"enable_latex_lint=True, enable_latex_diff=True, enable_sandbox=False, "
                     f"enable_self_evolution=False); "
                     f"pl.run(); "
                     f"print('Done')"],
                    cwd=PROJECT_ROOT,
                    timeout=5,
                )
            except (subprocess.TimeoutExpired, Exception):
                pass  # Let user run manually
    elif choice == "0":
        return False
    else:
        print(f"  无效选项: {choice}")

    input(f"\n  按回车继续...")
    return True


def main():
    os.system("clear" if os.name != "nt" else "cls")
    print_banner()

    daemon = _check_daemon()
    macro = _get_macro_today()

    print_macro_calendar(macro)
    print_status(daemon)
    print_menu()

    while True:
        try:
            choice = input(f"  请输入选项 [0-9]: ").strip()
            if not choice:
                continue
            if not run_action(choice):
                break
            os.system("clear" if os.name != "nt" else "cls")
            daemon = _check_daemon()
            macro = _get_macro_today()
            print_banner()
            print_macro_calendar(macro)
            print_status(daemon)
            print_menu()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  退出。守护进程继续在后台运行（如已启动）。")
            break


if __name__ == "__main__":
    main()
