"""Unit tests for scripts/core/formatters.py."""
from __future__ import annotations

import math
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys_path_inserted = False
if str(SCRIPTS_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPTS_DIR))
    sys_path_inserted = True

import scripts.core.formatters as f

import sys as _sys
if sys_path_inserted:
    _sys.path.remove(str(SCRIPTS_DIR))


class TestSignificanceMark:
    def test_pval_below_001(self):
        assert f.significance_mark(0.0001) == "***"
        assert f.significance_mark(0.000) == "***"

    def test_pval_below_01(self):
        assert f.significance_mark(0.001) == "**"
        assert f.significance_mark(0.005) == "**"
        assert f.significance_mark(0.009) == "**"

    def test_pval_below_05(self):
        assert f.significance_mark(0.01) == "*"
        assert f.significance_mark(0.025) == "*"
        assert f.significance_mark(0.049) == "*"

    def test_pval_below_10(self):
        assert f.significance_mark(0.05) == "."
        assert f.significance_mark(0.075) == "."
        assert f.significance_mark(0.099) == "."

    def test_pval_above_10(self):
        assert f.significance_mark(0.10) == ""
        assert f.significance_mark(0.50) == ""
        assert f.significance_mark(1.0) == ""

    def test_nan_returns_empty(self):
        nan = float("nan")
        assert f.significance_mark(nan) == ""
        assert f.significance_mark(math.nan) == ""

    def test_exact_boundaries(self):
        assert f.significance_mark(0.001) == "**"
        assert f.significance_mark(0.01) == "*"
        assert f.significance_mark(0.05) == "."
        assert f.significance_mark(0.10) == ""

    def test_negative_pval(self):
        """Negative p-values are treated as zero significance."""
        assert f.significance_mark(-0.5) == "***"
        assert f.significance_mark(-0.0) == "***"


class TestAllExports:
    def test_all_significance_mark(self):
        assert "significance_mark" in f.__all__

