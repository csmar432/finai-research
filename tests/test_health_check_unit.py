"""Unit tests for scripts/health_check.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def hc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import health_check as h
    yield h
    if _p in sys.path:
        sys.path.remove(_p)


class TestProblemCategory:
    def test_categories(self, hc):
        assert hc.ProblemCategory.NETWORK in hc.ProblemCategory
        assert hc.ProblemCategory.API_KEY in hc.ProblemCategory
        assert hc.ProblemCategory.OK in hc.ProblemCategory


class TestProblemItem:
    def test_init(self, hc):
        item = hc.ProblemItem(
            category=hc.ProblemCategory.API_KEY,
            name="Tushare",
            name_zh="Tushare Token",
            message="Missing TUSHARE_TOKEN",
            fix_steps=["Register at tushare.pro", "Set TUSHARE_TOKEN env"],
        )
        assert item.name == "Tushare"
        assert item.severity == "high"
        assert item.details == {}


class TestDiagnosticResult:
    def test_init(self, hc):
        result = hc.DiagnosticResult(
            timestamp="2024-01-01T00:00:00",
            platform="darwin",
            llm_available=True,
            llm_status="OK",
            mcp_enabled_count=43,
            mcp_verified_count=40,
            problem_counts={"API_KEY": 2},
            problems=[],
            system_ready=True,
            recommendations=[],
        )
        assert result.llm_available is True
        assert result.verify_mode is False
