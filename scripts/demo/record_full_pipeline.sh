#!/usr/bin/env bash
# scripts/demo/record_full_pipeline.sh
#
# Wrap the commands to record into an asciicast v2 file.
# Use `bash scripts/demo/record_full_pipeline.sh | tee /tmp/recording.typescript`
# then convert typescript → cast via `script2cast` (not in toolchain),
# OR drive termtosvg in headless mode against this stream.
#
# For the demo, we hand-craft a terminal session via Python and emit
# both output pre-roll (so timing aligns with the cast JSON format).
set -euo pipefail

cmd_help() {
  cat <<EOF
Usage: bash scripts/demo/record_full_pipeline.sh [demo_dir]

This script prints terminal commands + outputs for the Quick Demo.
Capture output with:

    bash scripts/demo/record_full_pipeline.sh > /tmp/demo_full.typescript
    termtosvg -i /tmp/demo_full.typescript \\
              -o /tmp/demo_full.svg \\
              -t gnu-light \\
              -g 100x30

Then convert SVG → GIF:

    python3 scripts/demo/svg_to_gif.py /tmp/demo_full.svg \\
            /tmp/demo_full.gif

EOF
  exit 0
}

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && cmd_help

# Realistic 30-second demo session
{
  PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
  cd "$PROJECT_ROOT"

  echo '$ export PATH="$HOME/.local/bin:$PATH"     # finai cli on PATH'
  echo '$ bash'
  echo

  echo '$ python3 scripts/cli.py health'
  timeout 30 python3 scripts/cli.py health 2>&1 | head -40
  echo

  echo '$ python3 scripts/count_assets.py --markdown'
  timeout 30 python3 scripts/count_assets.py --markdown 2>&1 | head -10
  echo

  echo '$ python3 scripts/cli.py version'
  timeout 10 python3 scripts/cli.py version 2>&1 | head -10
  echo

  echo '$ pip show finai-research-workflow'
  timeout 10 pip show finai-research-workflow 2>&1 | head -10 || echo "(not installed via PyPI yet — git clone + pip install -e .[extras] works)"
  echo

  echo '$ cat papers/us_esg_financing/AUDIT_NOTES.md'
  echo '  ... (full audit document, see repo)'
  echo

  echo '---'
  echo
  echo 'Next steps:'
  echo '  $ python scripts/agent_pipeline.py --topic "碳排放权与企业创新"'
  echo '  $ python scripts/research_framework/pipeline.py --topic "..."'
  echo
} 2>&1
