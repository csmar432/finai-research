"""Regression tests for P1-2: orphan engines wired into RobustnessRunner (audit_fix_2026_07_12).

11 orphan econometric engines have been wired into RobustnessRunner:
- rdd (sharp/fuzzy RDD)
- lp_did (Local Projections DiD)
- ife (Bai 2009 Interactive Fixed Effects)
- synthetic_did (Arkhangelsky 2021)
- panel_quantile (Canay 2011)
- panel_threshold (Hansen 2000)
- spatial (LeSage-Pace 2009)
- panel_var (Abrigo-Love 2016)
- garch (Bollerslev 1986)
- tvp_var (Nakajima 2010)
- cox_ph (Cox 1972)

This test asserts:
1. `RobustnessRunner.list_methods()` returns all 11
2. `run_method_specific()` returns the right dict shape for each
3. Idempotency: repeated calls return the same result
4. Graceful degradation when deps are missing (status='skipped', not crash)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def synthetic_panel() -> pd.DataFrame:
    """Build a minimal panel for smoke tests."""
    rng = np.random.default_rng(42)
    rows = []
    for unit in ["a", "b", "c"]:
        for t in range(5):
            treat = int(unit == "a" and t >= 2)
            post = int(t >= 2)
            did = treat * post
            rows.append({
                "unit": unit, "time": t, "post": post,
                "treat": treat, "did": did,
                "y": 1.0 + 0.1 * t + (0.5 * did) + rng.normal(0, 0.1),
            })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def runner(synthetic_panel):
    from scripts.research_framework.robustness_runner import RobustnessRunner
    return RobustnessRunner(
        df=synthetic_panel,
        baseline_result={"coef": 0.5, "se": 0.1, "pval": 0.01},
    )


class TestOrphanEnginesWired:
    """P1-2: orphan engines are reachable via RobustnessRunner."""

    EXPECTED_METHODS = {
        "rdd", "lp_did", "ife", "synthetic_did", "panel_quantile",
        "panel_threshold", "spatial", "panel_var", "garch", "tvp_var", "cox_ph",
        # v1.8.7 additions (P1-3, P1-4): wire TripleDiffDID + PSMDID
        "triple_diff_did", "psm_did",
    }

    def test_list_methods_returns_all_thirteen(self, runner):
        methods = runner.list_methods()
        assert isinstance(methods, list), "list_methods must return list"
        assert set(methods) == self.EXPECTED_METHODS, (
            f"Expected {self.EXPECTED_METHODS}, got {set(methods)}"
        )

    def test_list_methods_count_is_thirteen(self, runner):
        methods = runner.list_methods()
        assert len(methods) == 13, f"Expected 13 methods, got {len(methods)}"

    @pytest.mark.parametrize("method", sorted(EXPECTED_METHODS))
    def test_run_method_specific_returns_correct_shape(self, runner, synthetic_panel, method):
        """Each method returns dict with status/summary/skipped_reason/result."""
        result = runner.run_method_specific(method, synthetic_panel)
        assert isinstance(result, dict), f"{method}: result must be dict, got {type(result)}"
        assert "status" in result, f"{method}: missing 'status' key"
        assert result["status"] in ("ok", "skipped", "error"), (
            f"{method}: status={result['status']!r} not in allowed values"
        )
        # Skipped/error must have a reason
        if result["status"] in ("skipped", "error"):
            assert "skipped_reason" in result or "error" in result, (
                f"{method}: skipped/error must have a reason field"
            )

    @pytest.mark.parametrize("method", sorted({"rdd", "lp_did"}))  # just 2 for speed
    def test_run_method_specific_idempotent(self, runner, synthetic_panel, method):
        """Calling twice with same input returns the same result (cache hit)."""
        r1 = runner.run_method_specific(method, synthetic_panel)
        r2 = runner.run_method_specific(method, synthetic_panel)
        # Cache by (method, id(df)) — should be same
        # The summary should match
        assert r1["status"] == r2["status"], (
            f"{method}: idempotent — status mismatch between runs"
        )
        assert r1.get("summary") == r2.get("summary"), (
            f"{method}: idempotent — summary mismatch between runs"
        )

    def test_unknown_method_returns_error_status(self, runner, synthetic_panel):
        result = runner.run_method_specific("nonexistent_method_xyz", synthetic_panel)
        assert result["status"] == "error", (
            f"Unknown method must return 'error' status, got {result['status']!r}"
        )

    def test_audit_marker_present(self):
        """robustness_runner.py must contain the audit_fix marker for traceability."""
        from pathlib import Path
        src = Path("scripts/research_framework/robustness_runner.py").read_text(encoding="utf-8")
        assert "audit_fix_2026_07_12" in src, (
            "P1-2 regression: audit_fix_2026_07_12 marker missing from robustness_runner.py"
        )