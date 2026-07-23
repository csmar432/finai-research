"""Unit tests for scripts/core/plotstyle_validator.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pv():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import plotstyle_validator as p
    yield p
    if _p in sys.path:
        sys.path.remove(_p)


class TestFigureIssue:
    def test_init(self, pv):
        issue = pv.FigureIssue(
            severity="warning",
            category="font_size",
            message="Font size too small",
            suggestion="Use 12pt or larger",
        )
        assert issue.severity == "warning"
        assert issue.details == {}


class TestPlotStyleValidator:
    def test_class_exists(self, pv):
        assert hasattr(pv, "PlotStyleValidator")

    def test_init(self, pv):
        v = pv.PlotStyleValidator()
        assert v is not None
