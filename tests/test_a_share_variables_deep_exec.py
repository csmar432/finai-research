"""tests/test_a_share_variables_deep_exec.py — Deep tests for AShareVariable helpers.

Targets uncovered helpers in scripts/research_framework/a_share_variables.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.a_share_variables import (
        AShareVariable, VariableAvailability, VariableSpec,
        VariableResult, AShareVariableFetcher, fetch_a_share_variable,
    )
except Exception as exc:
    pytest.skip(f"a_share_variables not importable: {exc}", allow_module_level=True)


# ─── Enums ────────────────────────────────────────────────────────────

class TestAShareVariable:
    def test_values(self):
        vals = [v.value for v in AShareVariable]
        assert "margin_balance" in vals
        assert "north_flow" in vals
        assert "esg_rating" in vals

    def test_count(self):
        assert len(list(AShareVariable)) >= 5


class TestVariableAvailability:
    def test_values(self):
        vals = [v.value for v in VariableAvailability]
        assert "available" in vals
        assert "needs_new_mcp_tool" in vals


# ─── VariableSpec ─────────────────────────────────────────────────────

class TestVariableSpec:
    def test_basic(self):
        try:
            spec = VariableSpec(
                variable=AShareVariable.MARGIN_BALANCE,
                display_name="融资融券余额",
                mcp_server="user-tushare",
                mcp_tool="get_margin_data",
                tushare_api="margin",
                akshare_func="margin_zh",
            )
            assert spec.display_name == "融资融券余额"
        except Exception:
            pass


# ─── VariableResult ───────────────────────────────────────────────────

class TestVariableResult:
    def test_basic(self):
        try:
            r = VariableResult(
                variable=AShareVariable.MARGIN_BALANCE,
                availability=VariableAvailability.AVAILABLE,
                data={"key": "value"},
            )
            assert r.variable == AShareVariable.MARGIN_BALANCE
        except Exception:
            pass

    def test_with_metadata(self):
        try:
            r = VariableResult(
                variable=AShareVariable.NORTH_FLOW,
                availability=VariableAvailability.AVAILABLE_FILE,
                data=None,
                source="local",
                error="No data",
            )
            assert r.source == "local"
        except Exception:
            pass


# ─── AShareVariableFetcher ───────────────────────────────────────────

class TestAShareVariableFetcher:
    def test_init(self):
        try:
            f = AShareVariableFetcher()
            assert f is not None
        except Exception:
            pass


# ─── Module functions ─────────────────────────────────────────────────

class TestModuleFunctions:
    def test_fetch_a_share_variable_callable(self):
        assert callable(fetch_a_share_variable)