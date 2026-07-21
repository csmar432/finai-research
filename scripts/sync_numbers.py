#!/usr/bin/env python3
"""
sync_numbers.py — Regenerate all hardcoded numbers in documentation from PROJECT_NUMBERS.json (SSOT).

This eliminates the root cause of repeated false-positive audits: numbers that are
manually maintained in 5+ docs drift out of sync with each other.

Usage:
    python scripts/sync_numbers.py              # dry run (show changes)
    python scripts/sync_numbers.py --apply     # actually write changes
    python scripts/sync_numbers.py --verify    # check current docs vs SSOT

The SSOT is scripts/PROJECT_NUMBERS.json. All numeric claims in docs must be
derived from it, not maintained independently.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SSOT_PATH = ROOT / "scripts" / "PROJECT_NUMBERS.json"


def load_ssot() -> dict:
    with open(SSOT_PATH) as f:
        return json.load(f)


# Maps: (file, regex_pattern) → SSOT lookup key
# Used by --verify to find inconsistencies
REPLACEMENTS = {
    # README.md
    "README.md": [
        (r"Integrates \d+ MCP", "Integrates {mcp_total} MCP"),
        # 匹配行内的 "**N MCP server directories"（markdown 加粗），
        # 模板不重复加 **，避免与已有 markdown 语法叠加
        (r"\*\*(\d+) MCP server directories", "**{mcp_total} MCP server directories"),
        (r"~30 econometric method implementations", "~{econ_total} econometric method implementations"),
        (r"\*\*(\d+) AI Skills", "**{skills_total} AI Skills"),
    ],
    # README_EN.md
    # 注意：template 不要再加 ** 前后缀，避免与原文 markdown 加粗叠加
    "README_EN.md": [
        (r"MCP data servers.*?\*\*(\d+)\*\*", "MCP data servers | **{mcp_total}**"),
        (r"Econometric methods.*?~\((\d+)", "Econometric Methods (~({econ_estimators}"),
        (r"(\d+) AI Skills \(", "{skills_total} AI Skills ("),
        (r"Coverage.*?\*\*~?(\d+)%\*\*?", "Coverage | **{cov_gate}%**"),
        (r"(\d+) test files", "{test_files} test files"),
    ],
    # CLAUDE.md
    "CLAUDE.md": [
        (r"（(\d+)个服务器目录）", "（{mcp_total}个服务器目录）"),
        (r"约(\d+)种独立实现", "约{econ_total}种独立实现"),
        (r"(\d+)个MCP服务器目录", "{mcp_total}个MCP服务器目录"),
        (r"(\d+) 个 MCP 服务器注册", "{mcp_total} 个 MCP 服务器注册"),
    ],
    # mcp_tools.mdc
    ".cursor/rules/mcp_tools.mdc": [
        (r"（(\d+)个目录服务器）", "（{mcp_total}个目录服务器）"),
    ],
}


def check_docs_current(ssot: dict) -> list[str]:
    """Check if docs match SSOT; return list of inconsistencies."""
    issues = []
    mcp = ssot["mcp"]
    econ = ssot["econometrics"]
    skills = ssot["skills"]
    testing = ssot["testing"]

    # Backward compat
    str(econ.get("total_method_modules") or econ.get("total_independent_implementations", 0))
    str(econ.get("total_individual_estimators") or 0)

    for filepath, patterns in REPLACEMENTS.items():
        path = ROOT / filepath
        if not path.exists():
            issues.append(f"  MISSING FILE: {filepath}")
            continue
        content = path.read_text()
        for pattern, _ in patterns:
            if "{mcp_total}" in pattern:
                str(mcp["total_directories"])
            elif "{econ_total}" in pattern:
                pass
            elif "{econ_estimators}" in pattern:
                pass
            elif "{skills_total}" in pattern:
                str(skills["total"])
            elif "{cov_gate}" in pattern:
                str(testing["ci_coverage_gate"])
            elif "{test_files}" in pattern:
                str(testing["test_files"])
            else:
                continue
            # Find the number this pattern would match
            m = re.search(pattern.replace("{mcp_total}", r"\d+").replace("{econ_total}", r"\d+").replace("{econ_estimators}", r"\d+").replace("{skills_total}", r"\d+").replace("{cov_gate}", r"\d+").replace("{test_files}", r"\d+"), content)
            if m:
                actual = m.group(0)
                issues.append(f"  {filepath}: found '{actual}', expected SSOT value")

    return issues


def apply_replacements(ssot: dict, dry_run: bool = True) -> dict[str, str]:
    """Apply all replacements from SSOT to docs. Returns {filepath: old→new}."""
    mcp = ssot["mcp"]
    econ = ssot["econometrics"]
    skills = ssot["skills"]
    testing = ssot["testing"]

    # Backward compat: support old/new key names
    ecom_total = str(econ.get("total_method_modules") or econ.get("total_independent_implementations", 0))
    ecom_estimators = str(econ.get("total_individual_estimators") or 0)

    subs = {
        "{mcp_total}": str(mcp["total_directories"]),
        "{econ_total}": ecom_total,
        "{econ_estimators}": ecom_estimators,
        "{skills_total}": str(skills["total"]),
        "{cov_gate}": str(testing["ci_coverage_gate"]),
        "{test_files}": str(testing["test_files"]),
    }

    results = {}
    for filepath, patterns in REPLACEMENTS.items():
        path = ROOT / filepath
        if not path.exists():
            continue
        original = path.read_text()
        updated = original
        for pattern, template in patterns:
            for old, new in subs.items():
                template = template.replace(old, new)
            updated = re.sub(pattern, template, updated)
        if updated != original:
            results[filepath] = f"OLD:\n{original[:200]}...\n\nNEW:\n{updated[:200]}..."
            if not dry_run:
                path.write_text(updated)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync project numbers from SSOT to docs")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument("--verify", action="store_true", help="Check current docs vs SSOT")
    args = parser.parse_args()

    ssot = load_ssot()
    print(f"SSOT loaded from {SSOT_PATH}")
    print(f"  MCP directories: {ssot['mcp']['total_directories']}")
    # Backward compatibility: support both old/new key names
    ecom = ssot['econometrics']
    ecom_total = ecom.get('total_method_modules') or ecom.get('total_independent_implementations', 0)
    print(f"  Econometric methods: {ecom_total}")
    print(f"  Skills: {ssot['skills']['total']}")
    print(f"  Coverage gate: {ssot['testing']['ci_coverage_gate']}%")
    print()

    if args.verify:
        issues = check_docs_current(ssot)
        if issues:
            print("INCONSISTENCIES FOUND:")
            for issue in issues:
                print(issue)
            print(f"\nRun `python scripts/sync_numbers.py --apply` to fix.")
            return 1
        else:
            print("All documented numbers match SSOT.")
            return 0

    results = apply_replacements(ssot, dry_run=not args.apply)
    if not results:
        print("No changes needed.")
        return 0

    print(f"Changes {'would be' if not args.apply else 'written to'}:")
    for path, diff in results.items():
        print(f"  {path}")
    print()

    if not args.apply:
        print("Dry run. Run with --apply to write changes.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
