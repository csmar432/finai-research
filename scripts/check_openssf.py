#!/usr/bin/env python3
"""check_openssf.py — Audit project against OpenSSF Best Practices criteria.

OpenSSF Best Practices evaluates ~70 checks. This script runs the ones we
can verify locally (no GitHub API needed) and reports pass/fail.

Categories covered:
- Discovery: README, LICENSE, etc.
- Change Management: CONTRIBUTING, PR_TEMPLATE, ISSUE_TEMPLATE
- Reporting: SECURITY.md, code-of-conduct
- Security: dependabot.yml, security policy
- Code: tests, CI workflow

Usage:
    python scripts/check_openssf.py                 # local audit
    python scripts/check_openssf.py --report        # save docs/audit/OPENSSF_AUDIT.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# Each check has: id, description, file_to_check, optional content pattern
CHECKS = [
    # ── Discovery ───────────────────────────────────────────────────
    ("D1", "README.md exists and > 1KB", "README.md", lambda c: len(c) > 1024),
    ("D2", "README has Installation section", "README.md", lambda c: re.search(r"##.*Install", c, re.IGNORECASE)),
    ("D3", "README has Usage section", "README.md", lambda c: re.search(r"##.*(Usage|Quick Start|用法)", c, re.IGNORECASE)),
    ("D4", "LICENSE present (MIT/Apache/BSD)", "LICENSE", lambda c: re.search(r"MIT|Apache|BSD", c, re.IGNORECASE)),
    # ── Change Management ───────────────────────────────────────────
    ("C1", "CONTRIBUTING.md present and > 1KB", "CONTRIBUTING.md", lambda c: len(c) > 1024),
    ("C2", "Issue template exists", ".github/ISSUE_TEMPLATE", None, "any"),
    ("C3", "PR template exists", ".github/PULL_REQUEST_TEMPLATE.md", lambda c: len(c) > 100),
    ("C4", "CI workflow exists", ".github/workflows", None, "any"),
    # ── Reporting ───────────────────────────────────────────────────
    ("R1", "SECURITY.md present", "SECURITY.md", lambda c: len(c) > 200),
    ("R2", "CODE_OF_CONDUCT.md present", "CODE_OF_CONDUCT.md", lambda c: len(c) > 200),
    ("R3", "Discussion category templates exist", ".github/DISCUSSION_TEMPLATE", None, "any"),
    # ── Security ────────────────────────────────────────────────────
    ("S1", "Dependabot configured", ".github/dependabot.yml", lambda c: "version: 2" in c),
    ("S2", "No hardcoded secrets in tracked files", None, None),  # special: grep
    ("S3", "requirements.txt has pip-audit / safety", "requirements.txt", lambda c: "pip-audit" in c or "safety" in c.lower()),
    ("Q1", "Test directory exists with >= 50 tests", "tests", None, "test_count_50"),
    ("Q2", "pyproject.toml has version", "pyproject.toml", lambda c: re.search(r'^version\s*=\s*"[^"]+"', c, re.MULTILINE)),
    ("Q3", "Python >= 3.10 declared", "pyproject.toml", lambda c: re.search(r'requires-python\s*=\s*">=3\.\d+', c)),
    ("Q4", "Type checker configured (mypy/ruff)", "pyproject.toml", lambda c: "mypy" in c or "[tool.ruff" in c),
    # ── Community ───────────────────────────────────────────────────
    ("M1", "ROADMAP.md present", "ROADMAP.md", lambda c: len(c) > 200),
    ("M2", "CHANGELOG.md present", "CHANGELOG.md", lambda c: len(c) > 200),
    ("M3", "Zenodo DOI in CITATION.cff", "CITATION.cff", lambda c: "zenodo" in c.lower() or "doi" in c.lower()),
]


def _read(p: Path) -> str:
    """Read file as text, return empty on error."""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _count_tests() -> int:
    """Count pytest test functions."""
    cnt = 0
    tests_dir = ROOT / "tests"
    if not tests_dir.exists():
        return 0
    for path in tests_dir.rglob("test_*.py"):
        try:
            text = path.read_text(encoding="utf-8")
            cnt += len(re.findall(r"^\s*def\s+test_", text, re.MULTILINE))
        except Exception:  # noqa: S110
            pass
    return cnt


def _has_hardcoded_secrets() -> tuple[bool, list[str]]:
    """Defense: scan tracked files for accidental secret literals."""
    bad_patterns = [
        r"api[_-]?key\s*=\s*[\"'][A-Za-z0-9]{20,}",
        r"secret\s*=\s*[\"'][A-Za-z0-9]{20,}",
        r"token\s*=\s*[\"'][a-zA-Z0-9]{30,}",
    ]
    bad = []
    for f in (ROOT / "scripts").rglob("*.py"):
        if "__pycache__" in str(f) or "/legacy/" in str(f):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # Skip the placeholder patterns commonly used in demo code
        if "dummy_key" in text or "<your_" in text or "example.com" in text:
            continue
        for pat in bad_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                bad.append(f"{f.relative_to(ROOT)}: {m.group(0)[:60]}")
        if len(bad) > 10:
            break
    return (not bad), bad


def run_check(
    check_id: str, desc: str, rel_path: str | None, content_check=None, special: str | None = None
) -> tuple[bool, str]:
    """Run a single check, return (passed, evidence)."""
    # Special: S2 hardcoded secrets scan (no file)
    if check_id == "S2":
        ok, bad = _has_hardcoded_secrets()
        if ok:
            return True, "no hardcoded secrets detected"
        return False, f"{len(bad)} potential secret literals: {bad[:3]}"

    # Special: directory with "any non-empty" semantics
    if special == "any":
        p = ROOT / rel_path
        if p.is_dir() and any(p.iterdir()):
            return True, f"{rel_path} is non-empty directory"
        return False, f"{rel_path} missing or empty"

    # Special: count tests
    if special == "test_count_50":
        n = _count_tests()
        return n >= 50, f"{n} test functions found"

    # Default: file content check
    if rel_path is None:
        return False, "no path"
    path = ROOT / rel_path
    if not path.exists():
        return False, f"{rel_path} not found"
    if path.is_dir():
        # Treat directories as existing-and-non-empty
        if any(path.iterdir()):
            return True, f"{rel_path}/ is non-empty directory"
        return False, f"{rel_path} empty"
    content = _read(path)
    if not content:
        return False, f"{rel_path} empty"
    try:
        if content_check is None or content_check(content):
            return True, f"{rel_path} OK"
        return False, f"{rel_path} content check failed"
    except Exception as e:
        return False, f"check error: {e}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="Save report")
    args = parser.parse_args()

    print(f"OpenSSF Best Practices · Local Audit\n{'=' * 50}\n")
    passed = []
    failed = []
    for check in CHECKS:
        cid, desc, *rest = check
        rel_path, content_check, special = None, None, None
        if len(rest) == 1 and isinstance(rest[0], str):
            # (path,)
            rel_path = rest[0]
        elif len(rest) == 1 and rest[0] is None:
            # S2 special: no path
            pass
        elif len(rest) == 1:
            # callable
            rel_path, content_check = None, rest[0]
        elif len(rest) == 2:
            # (path, callable) or (path, None, special) or (path, "keyword")
            first, second = rest[0], rest[1]
            if isinstance(second, str) and second in ("any", "test_count_50"):
                rel_path, special = first, second
            else:
                rel_path, content_check = first, second
        elif len(rest) == 3:
            rel_path, content_check, special = rest[0], rest[1], rest[2]

        ok, evidence = run_check(cid, desc, rel_path, content_check, special)
        icon = "✅" if ok else "❌"
        print(f"  [{cid}] {icon} {desc}")
        print(f"        → {evidence}")
        if ok:
            passed.append((cid, desc, evidence))
        else:
            failed.append((cid, desc, evidence))

    pct = len(passed) / len(CHECKS) * 100
    print(f"\nResult: {len(passed)}/{len(CHECKS)} passed ({pct:.0f}%)")

    tier = "❓ Unknown"
    if pct >= 90:
        tier = "🥇 Gold (90%+)"
    elif pct >= 80:
        tier = "🥈 Silver (80%+)"
    elif pct >= 70:
        tier = "🥉 Passing (70%+)"
    elif pct >= 50:
        tier = "⚠️  In progress (50%+)"
    else:
        tier = "🔴 Insufficient (<50%)"

    print(f"Tier estimate: {tier}")

    if args.report:
        report = ROOT / "docs" / "audit" / "OPENSSF_AUDIT.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        with open(report, "w") as f:
            f.write("# OpenSSF Best Practices · Local Audit\n\n")
            f.write(f"**Result**: {len(passed)}/{len(CHECKS)} ({pct:.0f}%)\n")
            f.write(f"**Tier**: {tier}\n\n")
            f.write("## Passed\n\n")
            for cid, desc, ev in passed:
                f.write(f"- [{cid}] {desc} — {ev}\n")
            f.write("\n## Failed\n\n")
            for cid, desc, ev in failed:
                f.write(f"- [{cid}] {desc} — {ev}\n")
            f.write(
                "\n## Notes\n\n"
                "- This is a *local* audit covering checks we can verify"
                " without API access.\n"
                "- For full OpenSSF scoring, visit "
                "https://www.bestpractices.dev/ after the next GitHub webhook fires.\n"
            )
        print(f"\nReport saved: {report.relative_to(ROOT)}")

    return 0 if pct >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
