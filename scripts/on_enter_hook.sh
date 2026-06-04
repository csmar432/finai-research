# ─────────────────────────────────────────────────────────────────────────────
# on_enter_hook.sh — zsh cd hook for 自动唤醒 FinResearch 工作流
#
# 使用方法：将以下内容添加到 ~/.zshrc：
#
#   source /path/to/论文-研报工作流/scripts/on_enter_hook.sh
#
# 效果：
#   1. 每次 cd 进入本目录，自动打印欢迎信息 + 快捷命令
#   2. Cursor 聊天框也会看到这个欢迎，并自动加载 CLAUDE.md 上下文
#   3. 输入数字可执行对应操作，或直接输入研究主题启动 pipeline
#
# 环境变量：
#   finai_auto_enter=0    — 关闭自动唤醒
#   finai_quiet=1         — 静默模式（只显示一行摘要）
# ─────────────────────────────────────────────────────────────────────────────

# 使用动态检测，不硬编码绝对路径
_proj_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_finai_hook_root="$_proj_root"

# 如果不在项目目录，则不执行
if [[ "$PWD" != "$_finai_hook_root" ]]; then
    return 0 2>/dev/null
fi

# 关闭自动唤醒
if [[ "${finai_auto_enter:-1}" == "0" ]]; then
    return 0 2>/dev/null
fi

# 非交互式终端
if [[ ! -t 0 ]]; then
    return 0 2>/dev/null
fi

# 检查 Python
_finai_py="${_finai_hook_root}/.venv/bin/python3"
if [[ ! -x "$_finai_py" ]]; then
    _finai_py="python3"
fi

# 静默模式
if [[ "${finai_quiet:-0}" == "1" ]]; then
    _s=$("$_finai_py" -c "
import sys, os
sys.path.insert(0, '${_finai_hook_root}')
try:
    from scripts.event_monitor import get_running_pipelines
    from pathlib import Path
    pid = Path('${_finai_hook_root}/data/event_monitor.pid')
    dmn = 'daemon running' if (pid.exists() and os.path.exists('/proc/'+pid.read_text().strip())) else 'no daemon'
    print(f'FinAI: {dmn} | {len(get_running_pipelines())} pipelines | \c')
except:
    print('FinAI: \c')
" 2>/dev/null)
    echo -n "  $_s "
    return 0 2>/dev/null
fi

# ── 欢迎信息 ───────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  论文-研报工作流 · FinResearch Agent"
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  告诉我研究主题，我来帮你完成从文献到论文的全流程。"
echo ""
echo "  常用操作："
echo "    1)  扫描事件"
echo "    2)  启动监控（每5分钟）"
echo "    3)  日历感知调度（NFP/CPI/FOMC）"
echo "    R)  输入研究主题 → 启动完整论文流程"
echo ""
echo "  或直接在 Cursor 聊天框输入："
echo "    Skill: fin-full-pipeline \"[你的研究方向]\""
echo ""

# 取消下行注释以启用交互菜单：
# "$_finai_py" "${_finai_hook_root}/scripts/on_enter.py"
