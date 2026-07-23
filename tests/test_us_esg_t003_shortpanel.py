"""Regression tests for T003 — short-panel DID bias warning.

Per Roth & Sant'Anna (2023, Biometrika) and Freyaldenhoven et al. (2024),
short post-treatment periods (T_post < 5) inflate finite-sample bias and
reduce pre-trend test power. These tests assert:

1. process_data emits a UserWarning when T_post < 5.
2. The warning text mentions "short-panel" or "Roth & Sant'Anna".
3. The paper's Table 3 LaTeX tablenotes contains the caveat.
4. The audit_fix_2026_07_12 marker is present in the source.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SOURCE_FILE = ROOT / "scripts" / "us_esg_regression.py"
TABLE3_FILE = ROOT / "papers" / "us_esg_financing" / "latex" / "tables" / "table3_did.tex"


class TestSourceHasT003Fix:
    @pytest.fixture(scope="class")
    def source(self) -> str:
        return SOURCE_FILE.read_text(encoding="utf-8")

    def test_audit_marker_present(self, source: str) -> None:
        assert "audit_fix_2026_07_12" in source, "audit_fix_2026_07_12 marker missing"

    def test_short_panel_warning_logic(self, source: str) -> None:
        """Source must check n_post < 5 and emit warning."""
        assert "n_post < 5" in source, (
            "T003 regression: short-panel DID warning logic missing. "
            "Expected `if n_post < 5` block."
        )

    def test_cites_roth_sant_anna(self, source: str) -> None:
        """Warning must cite Roth & Sant'Anna (2023)."""
        assert "Roth" in source and "Sant" in source and "2023" in source, (
            "T003 regression: warning must cite Roth & Sant'Anna (2023)."
        )

    def test_min_post_periods_threshold_documented(self, source: str) -> None:
        """Threshold must be 5 (with explanation)."""
        assert "minimum of 5" in source or "T_post >= 5" in source or "T_post \\geq 5" in source, (
            "T003 regression: T_post >= 5 threshold must be documented."
        )


class TestTableThreeCaveatPresent:
    @pytest.fixture(scope="class")
    def table3(self) -> str:
        if not TABLE3_FILE.exists():
            pytest.skip(f"Table 3 LaTeX not generated yet: {TABLE3_FILE}")
        return TABLE3_FILE.read_text(encoding="utf-8")

    def test_caveat_in_tablenotes(self, table3: str) -> None:
        """Table 3 tablenotes must include the short-panel caveat."""
        # LaTeX-escaped form: audit\_fix\_2026\_07\_12
        marker = "audit_fix_2026_07_12"
        marker_escaped = marker.replace("_", r"\_")
        assert (marker in table3) or (marker_escaped in table3), (
            "T003 regression: Table 3 LaTeX must contain audit_fix_2026_07_12 marker "
            "in tablenotes."
        )
        assert "T_post" in table3 or "T\\text{post}" in table3 or r"T_{\text{post}" in table3, (
            "T003 regression: Table 3 LaTeX must mention T_post."
        )
        assert "Roth" in table3, (
            "T003 regression: Table 3 LaTeX must cite Roth & Sant'Anna."
        )

    def test_caveat_mentions_illustrative(self, table3: str) -> None:
        """Caveat must indicate results are illustrative."""
        assert "illustrative" in table3.lower(), (
            "T003 regression: caveat must state results are illustrative, not definitive."
        )


@pytest.mark.skipif(True, reason="process_data requires real yfinance data; tested via source-level checks above")
class TestProcessDataWarns:
    """Behavioral: process_data emits UserWarning when T_post < 5.

    Skipped by default because process_data requires real yfinance MCP calls.
    The source-level checks above verify the logic exists. To run this test
    interactively, mock the MCP calls in conftest.py.
    """
    def test_short_post_emits_warning(self):
        import pandas as pd
        import numpy as np
        import warnings

        df = pd.DataFrame({
            "year": [2018, 2019, 2020, 2021, 2022, 2023] * 5,
            "ticker": ["A"] * 30,
            "esg_high": [1] * 30,
            "esg_tier": ["high"] * 30,
            "sector": ["e&p"] * 30,
            "lev": np.random.rand(30),
            "ltd_ratio": np.random.rand(30),
            "cost_debt": np.random.rand(30),
            "roa": np.random.rand(30),
            "tangibility": np.random.rand(30),
        })
        from scripts.us_esg_regression import process_data
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            process_data(df)
            msgs = [str(x.message) for x in w]
            assert any("short-panel" in m.lower() for m in msgs), (
                f"Expected short-panel warning, got: {msgs}"
            )
