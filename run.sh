#!/usr/bin/env bash
# run.sh — One-step end-to-end reproducibility for 论文-研报工作流
#
# Usage:
#   ./run.sh                  # Full pipeline with demo
#   ./run.sh --stage lit      # Start from literature review
#   ./run.sh --checkpoint cp_abc123  # Resume from checkpoint
#   ./run.sh --test           # Run test suite
#
# Environment:
#   DEEPSEEK_API_KEY    — DeepSeek API key (recommended)
#   RELAY_API_KEY       — B.AI relay key for GPT/Claude (optional)
#   TUSHARE_TOKEN       — Tushare Pro token for A-share data (optional)
#   BRAVE_SEARCH_API_KEY — Brave Search for literature (optional)
#
# Output:
#   output/              — Generated papers, figures, tables
#   output/checkpoints/  — Pipeline checkpoints
#   output/provenance/   — Data lineage reports
#   output/pipeline_telemetry.jsonl — Execution telemetry

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"

# ─── Parse Arguments ──────────────────────────────────────────────────────────
STAGE=""
CHECKPOINT=""
RUN_TESTS=false
TOPIC=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --stage) STAGE="$2"; shift 2 ;;
        --checkpoint) CHECKPOINT="$2"; shift 2 ;;
        --test) RUN_TESTS=true; shift ;;
        --topic) TOPIC="$2"; shift 2 ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--stage STAGE] [--checkpoint ID] [--test] [--topic TOPIC]"
            exit 1
            ;;
    esac
done

# ─── Environment Check ────────────────────────────────────────────────────────
echo "[INFO] Checking environment..."
python scripts/health_check.py --json 2>/dev/null | python -c "
import sys, json
try:
    data = json.load(sys.stdin)
    issues = data.get('api_key_issues', [])
    if issues:
        print('[WARN] API Key issues:', ', '.join(issues))
    else:
        print('[OK] All required API keys present')
except:
    pass
" 2>/dev/null || true

# ─── Random Seed for Reproducibility ─────────────────────────────────────────
REPRODUCIBLE_SEED="${REPRODUCIBLE_SEED:-42}"
echo "[INFO] Using random seed: $REPRODUCIBLE_SEED"
export PYTHONHASHSEED="$REPRODUCIBLE_SEED"

# ─── Run Tests ────────────────────────────────────────────────────────────────
if $RUN_TESTS; then
    echo "[INFO] Running test suite..."
    python -m pytest tests/ -x -q --tb=short | tee "$LOG_DIR/tests.log"
    echo "[OK] Tests complete. Log: $LOG_DIR/tests.log"
    exit 0
fi

# ─── Pipeline Execution ────────────────────────────────────────────────────────
PIPELINE_ARGS=""

if [[ -n "$STAGE" ]]; then
    PIPELINE_ARGS="$PIPELINE_ARGS --stage $STAGE"
fi

if [[ -n "$CHECKPOINT" ]]; then
    PIPELINE_ARGS="$PIPELINE_ARGS --resume $CHECKPOINT"
fi

if [[ -n "$TOPIC" ]]; then
    PIPELINE_ARGS="$PIPELINE_ARGS --topic \"$TOPIC\""
fi

echo "[INFO] Starting pipeline at $(date)"
echo "[INFO] Log file: $LOG_FILE"
echo "[INFO] Pipeline args: $PIPELINE_ARGS"

# Run with timestamped log
python scripts/agent_pipeline.py $PIPELINE_ARGS 2>&1 | tee "$LOG_FILE"

PIPELINE_EXIT=${PIPELINE_STATUS:-$?}
if [[ $PIPELINE_EXIT -eq 0 ]]; then
    echo "[OK] Pipeline completed successfully at $(date)"
    echo "[INFO] Output: $PROJECT_DIR/output/"
    echo "[INFO] Provenance: $PROJECT_DIR/output/provenance/"
    echo "[INFO] Checkpoints: $PROJECT_DIR/output/checkpoints/"
    echo "[INFO] Telemetry: $PROJECT_DIR/data/pipeline_telemetry.jsonl"
else
    echo "[ERROR] Pipeline failed with exit code $PIPELINE_EXIT"
    echo "[INFO] Check log: $LOG_FILE"
    echo "[INFO] Resume from checkpoint with: $0 --checkpoint <id>"
    exit $PIPELINE_EXIT
fi
