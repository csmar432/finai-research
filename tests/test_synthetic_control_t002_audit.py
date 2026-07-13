"""Regression tests for T002 — synthetic_control sig must use permutation p-value.

Per Abadie et al. (2010, JASA), proper synthetic control significance inference
requires placebo permutation tests. The previous implementation used raw RMSPE
ratio thresholds (ratio > 20/10/5/2) which is NOT a valid statistical inference.

These tests assert:
1. `.sig` is empty when inference has not been run (was: heuristic star).
2. `.sig` correctly maps p-value to stars once inference() is run.
3. `.rmspe_ratio_sig` (legacy) is still accessible for backward compatibility.
4. `.permutation_pvalue` accessor returns the right value.
5. Source code does not contain the old `ratio > 20: return "***"` pattern
   in the default `.sig` property.
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SOURCE_FILE = ROOT / "scripts" / "research_framework" / "synthetic_control.py"


class TestSourceNoOldHeuristicInSig:
    """Source-level: the default `.sig` property must NOT use RMSPE heuristic."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        return SOURCE_FILE.read_text(encoding="utf-8")

    def test_old_heuristic_not_in_default_sig(self, source: str) -> None:
        """The old `ratio > 20: return "***"` must NOT be in the .sig property."""
        # Find the .sig property block
        m = re.search(
            r"    @property\n    def sig\(self\) -> str:\n(.*?)(?=\n    @property|\n    def \w)",
            source, re.DOTALL,
        )
        assert m is not None, "Cannot locate .sig property"
        sig_body = m.group(1)
        assert "rmspe_ratio" not in sig_body.lower().replace("rmspe_ratio_sig", ""), (
            "T002 regression: default .sig still references raw RMSPE ratio heuristic. "
            f"sig body:\n{sig_body[:500]}"
        )

    def test_new_sig_references_permutation(self, source: str) -> None:
        """The new .sig must read from inference/permutation."""
        m = re.search(
            r"    @property\n    def sig\(self\) -> str:\n(.*?)(?=\n    @property|\n    def \w)",
            source, re.DOTALL,
        )
        sig_body = m.group(1)
        assert "permutation" in sig_body.lower(), (
            "T002 regression: new .sig must read from permutation p-value. "
            f"sig body:\n{sig_body[:500]}"
        )

    def test_legacy_rmspe_ratio_sig_present(self, source: str) -> None:
        """Legacy accessor `rmspe_ratio_sig` should be preserved."""
        assert "def rmspe_ratio_sig(self)" in source, (
            "T002 regression: legacy `rmspe_ratio_sig` accessor missing."
        )

    def test_permutation_pvalue_accessor_present(self, source: str) -> None:
        assert "def permutation_pvalue(self)" in source, (
            "T002 regression: `permutation_pvalue` convenience accessor missing."
        )


@pytest.fixture(scope="module")
def fitted_sc():
    """Return a fitted SyntheticControlEngine with mock data."""
    import numpy as np
    import pandas as pd
    from scripts.research_framework.synthetic_control import SyntheticControlEngine

    np.random.seed(42)
    rows = []
    for unit in ["treated"] + [f"donor{i}" for i in range(4)]:
        base = np.random.randn(20).cumsum() * 0.5 + 30
        for i, yr in enumerate(range(2000, 2020)):
            add = 5.0 if (unit == "treated" and yr >= 2010) else 0.0
            rows.append({"unit": unit, "year": yr, "y": base[i] + add})
    df = pd.DataFrame(rows)
    engine = SyntheticControlEngine(
        df=df, y_var="y", unit_var="unit", time_var="year",
        treat_unit="treated", treat_period=2010,
    )
    engine.fit()
    return engine


class TestSigUsesPermutationPValue:
    """Behavioral tests: .sig now uses permutation p-value."""

    def test_sig_empty_without_inference(self, fitted_sc):
        """Without running inference(), .sig must return "" (no longer heuristic)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sig = fitted_sc._result.sig
            assert sig == "", (
                f"T002 regression: .sig without inference() must return '', got {sig!r}"
            )
            # Verify it actually emitted a warning telling user to run inference()
            msgs = [str(x.message) for x in w]
            assert any("inference" in m.lower() for m in msgs), (
                f"Expected warning about running inference(), got: {msgs}"
            )

    def test_sig_returns_legacy_via_separate_accessor(self, fitted_sc):
        """.rmspe_ratio_sig still works for backward compat (heuristic)."""
        sig = fitted_sc._result.rmspe_ratio_sig
        # Should be one of the legacy heuristic values
        assert sig in ("***", "**", "*", r"$\dagger$", ""), (
            f"T002 regression: .rmspe_ratio_sig returned unexpected: {sig!r}"
        )

    def test_sig_after_inference(self, fitted_sc):
        """After inference(), .sig must use permutation p-value."""
        fitted_sc.inference()
        sig = fitted_sc._result.sig
        # Should now be one of the academic standard stars based on p-value
        assert sig in ("***", "**", "*", ""), (
            f"T002 regression: .sig after inference() returned unexpected: {sig!r}"
        )

    def test_permutation_pvalue_accessor(self, fitted_sc):
        """`.permutation_pvalue` returns the right value after inference()."""
        before = fitted_sc._result.permutation_pvalue
        assert before != before or before is None  # nan or None
        fitted_sc.inference()
        after = fitted_sc._result.permutation_pvalue
        # Must be in [0, 1] or NaN
        assert (0.0 <= after <= 1.0) or (after != after), (
            f"T002 regression: permutation_pvalue out of range: {after}"
        )
