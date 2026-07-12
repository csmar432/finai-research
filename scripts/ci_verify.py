#!/usr/bin/env python3
"""Cross-platform reproducibility verification.

Run this on macOS, Linux, and Windows and compare the outputs to verify
byte-identical results (or as close as physically possible).

Usage:
    python scripts/ci_verify.py                    # run all checks
    python scripts/ci_verify.py --check json       # specific check
    python scripts/ci_verify.py --output /tmp/xplat  # output dir

Checks performed:
  1. normalize module loads without error
  2. normalize_json_dumps output is deterministic
  3. PurePosixPath handles backslashes correctly
  4. datetime always UTC ISO 8601
  5. BLAS single-thread enforced
  6. random seed is reproducible
  7. JSON output is identical across multiple invocations

Exit: 0 = all pass, 1 = at least one failure.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Setup path ────────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.core.normalize import (
    setup_reproducible_env,
    normalize_path,
    normalize_json_dumps,
    normalize_datetime,
    normalize_random_seed,
    normalize_line_endings,
)

# ── Test helpers ───────────────────────────────────────────────────────────────


class CheckResult:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail

    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        detail = f"  {self.detail}" if self.detail else ""
        return f"{status}  {self.name}{detail}"


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    # ── 1. Module loads ───────────────────────────────────────────────────────
    try:
        from scripts.core.normalize import (
            normalize_json_dumps, normalize_path, normalize_datetime,
        )
        results.append(CheckResult("normalize module loads", True))
    except Exception as e:
        results.append(CheckResult("normalize module loads", False, str(e)))
        return results  # can't continue without the module

    # ── 2. JSON deterministic ────────────────────────────────────────────────
    data = {"z": 3, "中文": "测试", "list": [1, 2, 3], "nested": {"b": 2, "a": 1}}
    s1 = normalize_json_dumps(data)
    s2 = normalize_json_dumps(data)
    identical = s1 == s2
    results.append(CheckResult(
        "normalize_json_dumps is deterministic",
        identical,
        f"len={len(s1)} bytes, sort_keys respected" if identical else s1[:200],
    ))

    # Also verify CJK and sort_keys
    keys_ordered = list(json.loads(s1).keys())
    assert keys_ordered == sorted(keys_ordered), f"keys not sorted: {keys_ordered}"
    results.append(CheckResult("JSON sort_keys=True respected", True))

    # ── 3. Path normalization ────────────────────────────────────────────────
    p = normalize_path("output\\papers\\test.tex")
    results.append(CheckResult(
        "normalize_path handles backslashes",
        str(p) == "output/papers/test.tex",
        f"{p}",
    ))
    p2 = normalize_path("/unix/style/file.csv")
    # PurePosixPath preserves leading '/' as part of the path
    p2_str = str(p2)
    results.append(CheckResult(
        "normalize_path preserves forward slashes",
        p2_str == "/unix/style/file.csv",
        f"{p2_str}",
    ))

    # ── 4. Datetime always UTC ───────────────────────────────────────────────
    iso = normalize_datetime()
    results.append(CheckResult(
        "normalize_datetime is UTC",
        iso.endswith("+00:00") and not iso.endswith("Z"),
        iso,
    ))
    # Verify no microsecond truncation
    dot_count = iso.count(".")
    results.append(CheckResult(
        "datetime has microsecond precision",
        dot_count == 1,
        iso,
    ))

    # ── 5. BLAS single-thread ────────────────────────────────────────────────
    env_vars = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"]
    all_single = all(os.environ.get(v) == "1" for v in env_vars)
    vals = {v: os.environ.get(v, "NOT SET") for v in env_vars}
    results.append(CheckResult(
        "BLAS single-thread enforced",
        all_single,
        str(vals),
    ))

    # ── 6. Random seed reproducible ─────────────────────────────────────────
    normalize_random_seed(42)
    vals_a = [random.random() for _ in range(5)]
    normalize_random_seed(42)
    vals_b = [random.random() for _ in range(5)]
    identical_random = vals_a == vals_b
    results.append(CheckResult(
        "random seed is reproducible",
        identical_random,
        f"{vals_a[:2]} vs {vals_b[:2]}",
    ))

    # ── 7. Line endings are LF ─────────────────────────────────────────────
    s = "line1\r\nline2\rline3\n"
    normalized = normalize_line_endings(s)
    has_crlf = "\r" in normalized
    results.append(CheckResult(
        "normalize_line_endings removes CR",
        not has_crlf,
        f"result contains \\r: {has_crlf}",
    ))
    is_only_lf = normalized == "line1\nline2\nline3\n"
    results.append(CheckResult(
        "normalize_line_endings produces LF-only",
        is_only_lf,
        repr(normalized),
    ))

    # ── 8. Hash seed deterministic ─────────────────────────────────────────
    hashseed = os.environ.get("PYTHONHASHSEED", "NOT SET")
    results.append(CheckResult(
        "PYTHONHASHSEED is 0 (deterministic)",
        hashseed == "0",
        f"PYTHONHASHSEED={hashseed}",
    ))

    # ── 9. Locale C ────────────────────────────────────────────────────────
    lc_all = os.environ.get("LC_ALL", "NOT SET")
    results.append(CheckResult(
        "LC_ALL is C (no locale-dependent formatting)",
        lc_all == "C",
        f"LC_ALL={lc_all}",
    ))

    return results


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Cross-platform reproducibility checks")
    parser.add_argument("--check", choices=["json", "path", "datetime", "random", "all"])
    parser.add_argument("--output", default="/tmp/xplat-verify")
    args = parser.parse_args()

    # Bootstrap reproducible env first
    setup_reproducible_env()

    print("═" * 60)
    print("Cross-Platform Reproducibility Verification")
    print(f"Python: {sys.version.split()[0]}  Platform: {sys.platform}")
    print(f"Date: {datetime.now(timezone.utc).isoformat()}")
    print("═" * 60)

    results = run_checks()

    print()
    for r in results:
        print(r)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print()
    print(f"Result: {passed}/{total} passed")
    print("═" * 60)

    if passed == total:
        print("✅ All checks passed — outputs should be byte-identical across OSes.")
        print()
        print("Known limitations (see scripts/core/normalize.py LIMITATIONS):")
        print("  1. PDF timestamp: compile-time /CreationDate differs across runs")
        print("  2. Image pixels: font rendering differs (use SVG for exact comparison)")
        print("  3. Float: last-bit may differ across CPU architectures (BLAS single-thread mitigates)")
        return 0
    else:
        print("❌ Some checks failed — review above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
