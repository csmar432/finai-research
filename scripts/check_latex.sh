#!/usr/bin/env bash
# scripts/check_latex.sh
# 用法:
#   bash scripts/check_latex.sh                     # 编译所有主文档
#   bash scripts/check_latex.sh path/to/paper.tex   # 编译指定文件
# 退出码: 0=全部成功, 1=有失败
#
# 规则: 独立文档（有 \documentclass）正常编译；
#       片段文件（\input{} 目标，无 \documentclass）跳过不报错。

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
NC=$'\033[0m'

log()   { echo "[$(date +%H:%M:%S)] $*"; }
ok()    { echo "${GREEN}✓${NC} $*"; }
warn()  { echo "${YELLOW}⚠${NC} $*"; }
err()   { echo "${RED}✗${NC} $*"; }

# 判断一个 .tex 文件是否为独立文档（有 \documentclass）
is_standalone_doc() {
    grep -q '^\s*\\documentclass' "$1" 2>/dev/null
}

# 判断文件是否应被排除（表/图/演示片段）
is_excluded_fragment() {
    case "$1" in
        */tables/*|*/figures/*|*/charts/*|*/results/table_*|*/results/fig_*)
            return 0 ;;
        */event_runs/*|*/demo_*.tex)
            return 0 ;;
    esac
    return 1
}

# 收集待检查文件
TEX_FILES=""
if [ $# -gt 0 ]; then
    # 命令行指定文件
    for f in "$@"; do
        TEX_FILES="${TEX_FILES}${f}"$'\n'
    done
else
    # papers/ 下所有 .tex
    while IFS= read -r f; do
        TEX_FILES="${TEX_FILES}${f}"$'\n'
    done < <(find papers/ -name "*.tex" -type f 2>/dev/null | sort)
fi

if [ -z "$TEX_FILES" ]; then
    warn "No LaTeX files to check"
    exit 0
fi

# 统计
TOTAL=$(echo "$TEX_FILES" | grep -c .)
log "Found ${TOTAL} LaTeX file(s) in scope (before filtering)"
echo ""

PASS=0
FAIL=0
SKIP_FRAGMENT=0
SKIP_EXCLUDED=0
FAILED_FILES=""

while IFS= read -r TEX; do
    [ -z "$TEX" ] && continue
    [ ! -f "$TEX" ] && continue

    DIR=$(dirname "$TEX")
    BASENAME=$(basename "$TEX" .tex)

    # 跳过辅助文件
    case "$BASENAME" in
        preamble|settings|macros) warn "  $TEX: skipped (auxiliary)"; continue ;;
    esac

    # 排除表/图/演示片段
    if is_excluded_fragment "$TEX"; then
        SKIP_EXCLUDED=$((SKIP_EXCLUDED+1))
        continue
    fi

    # 判断是否为独立文档
    if ! is_standalone_doc "$TEX"; then
        warn "  $TEX: skipped (fragment — lacks \\documentclass)"
        SKIP_FRAGMENT=$((SKIP_FRAGMENT+1))
        continue
    fi

    log "Checking: $TEX"

    cd "$PROJECT_ROOT/$DIR" || continue

    : > "${BASENAME}.log" 2>/dev/null || true
    : > "${BASENAME}.blg" 2>/dev/null || true

    # 标准 4 步编译
    pdflatex -interaction=nonstopmode -halt-on-error "$BASENAME.tex" > /dev/null 2>&1

    if [ -f "${BASENAME}.aux" ] && grep -qE '\\\\citation|\\\\bibdata' "${BASENAME}.aux" 2>/dev/null; then
        bibtex "$BASENAME" > /dev/null 2>&1 || true
    fi

    pdflatex -interaction=nonstopmode -halt-on-error "$BASENAME.tex" > /dev/null 2>&1
    pdflatex -interaction=nonstopmode -halt-on-error "$BASENAME.tex" > /dev/null 2>&1

    if [ -f "${BASENAME}.pdf" ] && [ -s "${BASENAME}.pdf" ]; then
        SIZE=$(wc -c < "${BASENAME}.pdf" 2>/dev/null || echo 0)
        ok "  $BASENAME.pdf compiled ($SIZE bytes)"
        PASS=$((PASS+1))
    else
        err "  Compile FAILED for $BASENAME"
        if [ -f "${BASENAME}.log" ]; then
            grep -E "^!" "${BASENAME}.log" 2>/dev/null | head -3 | sed 's/^/    /'
        fi
        FAIL=$((FAIL+1))
        FAILED_FILES="${FAILED_FILES}  - ${TEX}"$'\n'
    fi

    cd "$PROJECT_ROOT"
done <<EOF
$(echo "$TEX_FILES")
EOF

echo ""
echo "================================================"
log "Result: $PASS passed, $FAIL failed, $SKIP_FRAGMENT skipped, $SKIP_EXCLUDED excluded"

if [ $FAIL -gt 0 ]; then
    err "Failed files:"
    echo "$FAILED_FILES"
    exit 1
fi

ok "All standalone LaTeX documents compiled successfully"
exit 0
