#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# FinAI Research Workflow - Environment Setup
# ─────────────────────────────────────────────────────────────────────
# Sets up Python + pip + dependencies in a clean virtual environment.
# Tested on macOS (Apple Silicon & Intel) and Ubuntu 22.04+.

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No color

log() { printf "${BLUE}[finai]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[finai]${NC} ⚠  %s\n" "$*"; }
err() { printf "${RED}[finai]${NC} ✗  %s\n" "$*" >&2; }
ok() { printf "${GREEN}[finai]${NC} ✓  %s\n" "$*"; }

# ── 1. Detect environment ─────────────────────────────────────────
log "Detecting environment..."

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ "$version" == "3.10" || "$version" == "3.11" || "$version" == "3.12" ]]; then
            PYTHON_BIN="$candidate"
            ok "Found Python $version at $(command -v "$candidate")"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    err "Python 3.10+ is required but not found."
    echo "    Install with: brew install python@3.12  (macOS)"
    echo "                 sudo apt install python3.12  (Ubuntu)"
    exit 1
fi

# ── 2. Create virtual environment ──────────────────────────────────
VENV_NAME="finai"
VENV_DIR=".venv"

if [[ -d "$VENV_DIR" ]]; then
    warn "Virtual environment $VENV_DIR already exists."
    read -p "$(printf "${BLUE}[finai]${NC} Recreate? [y/N]: ")" -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Removing existing $VENV_DIR"
        rm -rf "$VENV_DIR"
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating virtual environment in $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    ok "Virtual environment created"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# ── 3. Upgrade pip ─────────────────────────────────────────────────
log "Upgrading pip..."
python -m pip install --upgrade pip wheel setuptools

# ── 4. Install dependencies ────────────────────────────────────────
log "Installing dependencies..."

# Determine extras
EXTRAS="${1:-all}"

case "$EXTRAS" in
    minimal)
        log "Installing minimal dependencies (no econometrics, no RAG)"
        pip install -e "."
        ;;
    econometrics)
        log "Installing with econometrics extras"
        pip install -e ".[econometrics]"
        ;;
    dev)
        log "Installing with dev dependencies"
        pip install -e ".[dev]"
        ;;
    *)
        log "Installing with all extras"
        pip install -e ".[all]"
        ;;
esac

# ── 5. Verify installation ─────────────────────────────────────────
log "Verifying installation..."

if python -c "import finai" 2>/dev/null; then
    ok "finai module imports successfully"
else
    err "finai module import failed"
    exit 1
fi

if python -c "from finai.scripts.health_check import main" 2>/dev/null; then
    ok "health_check module available"
fi

# ── 6. Show next steps ─────────────────────────────────────────────
ok "Setup complete!"
echo
echo "Next steps:"
echo
echo "  1. Activate the virtual environment:"
echo "     ${GREEN}source .venv/bin/activate${NC}"
echo
echo "  2. Verify the installation:"
echo "     ${GREEN}python scripts/health_check.py${NC}"
echo
echo "  3. (Optional) Configure API keys:"
echo "     ${GREEN}cp .env.example .env${NC}"
echo "     ${GREEN}vim .env${NC}  # edit and add your DEEPSEEK_API_KEY, TUSHARE_TOKEN, etc."
echo
echo "  4. Try a quick demo:"
echo "     ${GREEN}python scripts/agent_pipeline.py --topic \"Carbon trading and green innovation\"${NC}"
echo
echo "  5. Read the Chinese manual:"
echo "     ${GREEN}cat 使用指南.md${NC}"
echo

ok "All done! Happy researching."
