#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup-daemon.sh — Install the FinAI Event Monitor as a system service
#
# Usage:
#   macOS:  bash config/daemon/setup-daemon.sh macos
#   Linux:  bash config/daemon/setup-daemon.sh linux
#   Cron:   bash config/daemon/setup-daemon.sh cron
#
# Prerequisites:
#   1. Python environment with dependencies installed:
#      pip install -e .
#      pip install apscheduler
#
#   2. .env file configured (at least one of DEEPSEEK_API_KEY, etc.)
#
#   3. For macOS launchd: replace placeholder paths in the .plist file
#
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
EVENT_MON="${PROJECT_ROOT}/scripts/event_monitor.py"
PID_FILE="${PROJECT_ROOT}/data/event_monitor.pid"
LOG_DIR="${PROJECT_ROOT}/logs"

mkdir -p "$LOG_DIR"

echo "=== FinAI Event Monitor Setup ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# ── Detect platform ────────────────────────────────────────────────────────────
PLATFORM="${1:-}"
if [ -z "$PLATFORM" ]; then
    if [ "$(uname)" == "Darwin" ]; then
        PLATFORM="macos"
    elif [ -d "/run/systemd/system" ]; then
        PLATFORM="linux"
    else
        PLATFORM="cron"
    fi
fi

echo "Platform: $PLATFORM"
echo ""

# ── Check prerequisites ─────────────────────────────────────────────────────────
echo "[1/4] Checking prerequisites..."

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Virtual environment not found at $VENV_PYTHON"
    echo "  Run: python3 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

if [ ! -f "$EVENT_MON" ]; then
    echo "ERROR: event_monitor.py not found at $EVENT_MON"
    exit 1
fi

# Check APScheduler
if ! "$VENV_PYTHON" -c "import apscheduler" 2>/dev/null; then
    echo "Installing APScheduler..."
    "$VENV_PYTHON" -m pip install apscheduler --quiet
fi

echo "  Python: $("$VENV_PYTHON" --version)"
echo "  APScheduler: installed"
echo "  event_monitor.py: OK"
echo ""

# ── Generate cron entry ────────────────────────────────────────────────────────
echo "[2/4] Generating cron entries..."

CRON_MARKER="# FinAI Research Workflow Event Monitor"
CRON_ENTRY="0 8,13,20 * * * cd '$PROJECT_ROOT' && '$VENV_PYTHON' '$EVENT_MON' --scheduler '08:00,13:30,20:00' --auto-trigger >> '$LOG_DIR/cron.log' 2>&1"

# Remove old entries
crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "$(basename "$EVENT_MON")" > /tmp/crontab.tmp || true

# Add new entry
if [ "$PLATFORM" == "cron" ]; then
    echo "$CRON_ENTRY" >> /tmp/crontab.tmp
    echo "$CRON_MARKER" >> /tmp/crontab.tmp
    echo ""  >> /tmp/crontab.tmp
    crontab /tmp/crontab.tmp
    echo "  Cron entry added."
    echo "  View: crontab -l | grep FinAI"
fi

# ── Install launchd (macOS) ───────────────────────────────────────────────────
if [ "$PLATFORM" == "macos" ]; then
    echo "[3/4] Installing launchd service..."

    # Update plist with actual paths
    PLIST_SRC="${SCRIPT_DIR}/com.finai.research-workflow.event-monitor.plist"
    PLIST_DEST="${HOME}/Library/LaunchAgents/com.finai.research-workflow.event-monitor.plist"

    if [ ! -f "$PLIST_SRC" ]; then
        echo "ERROR: .plist not found at $PLIST_SRC"
        exit 1
    fi

    # Replace placeholder paths
    sed -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
        "$PLIST_SRC" > /tmp/com.finai.research-workflow.event-monitor.plist

    mkdir -p "${HOME}/Library/LaunchAgents"
    cp /tmp/com.finai.research-workflow.event-monitor.plist "$PLIST_DEST"

    echo "  Plist installed to: $PLIST_DEST"
    echo ""
    echo "  To start now:"
    echo "    launchctl load $PLIST_DEST"
    echo ""
    echo "  To stop:"
    echo "    launchctl unload $PLIST_DEST"
    echo ""
    echo "  To start automatically at login: load is already set (RunAtLoad=true)"
fi

# ── Install systemd (Linux) ──────────────────────────────────────────────────
if [ "$PLATFORM" == "linux" ]; then
    echo "[3/4] Installing systemd service..."

    SYSTEMD_DIR="/etc/systemd/system"
    SERVICE_FILE="${SCRIPT_DIR}/finai-event-monitor.service"

    if [ "$(id -u)" != "0" ]; then
        echo "WARNING: Not running as root. System-wide install requires:"
        echo "  sudo bash config/daemon/setup-daemon.sh linux"
        echo ""
        echo "  For user-level install, copy to:"
        echo "    ~/.config/systemd/user/"
        echo "  And run:"
        echo "    systemctl --user daemon-reload"
        echo "    systemctl --user enable --now finai-event-monitor.service"
    else
    # Replace paths in service file
    sed -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
        "$SERVICE_FILE" > /tmp/finai-event-monitor.service

        cp /tmp/finai-event-monitor.service "$SYSTEMD_DIR/finai-event-monitor.service"
        systemctl daemon-reload
        systemctl enable finai-event-monitor.service
        echo "  Service installed: $SYSTEMD_DIR/finai-event-monitor.service"
        echo ""
        echo "  To start now:"
        echo "    sudo systemctl start finai-event-monitor"
        echo ""
        echo "  To check status:"
        echo "    sudo systemctl status finai-event-monitor"
    fi
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo "[4/4] Setup complete!"
echo ""
echo "=== Usage ==="
echo ""
echo "  [Polling mode] Continuous polling every 5 min:"
echo "    cd $PROJECT_ROOT"
echo "    .venv/bin/python scripts/event_monitor.py --interval 300 --auto-trigger"
echo ""
echo "  [Scheduler mode] Run at 08:00, 13:30, 20:00 daily:"
echo "    .venv/bin/python scripts/event_monitor.py --scheduler '08:00,13:30,20:00' --auto-trigger"
echo ""
echo "  [Macro-aware] Auto-trigger on macro events (NFP/FOMC/CPI/PMI):"
echo "    .venv/bin/python scripts/event_monitor.py --macro-scheduler --auto-trigger"
echo ""
echo "  [Cron] Added to crontab (runs 08:00, 13:30, 20:00 daily):"
echo "    crontab -l | grep FinAI"
echo ""
echo "  [Daemon] Running in background:"
echo "    .venv/bin/python scripts/event_monitor.py --daemon --auto-trigger --macro-scheduler \\"
echo "      --log-file logs/monitor.log"
echo ""
echo "  [Check status] View pending approvals:"
echo "    .venv/bin/python scripts/event_monitor.py --list-pending"
echo "    .venv/bin/python scripts/event_monitor.py --status"
echo ""
echo "=== Done ==="
