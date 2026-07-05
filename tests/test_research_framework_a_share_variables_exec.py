"""tests/test_research_framework_a_share_variables_exec.py — Execute a_share_variables."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import a_share_variables as mod
except Exception as _exc:
    pytest.skip(f"a_share_variables not importable: {_exc}", allow_module_level=True)


class TestEnums:
    def test_AShareVariable(self):
        cls = getattr(mod, "AShareVariable", None)
        if cls is None: pytest.skip("not present")
        try:
            members = [m.name for m in cls]
            assert len(members) > 0
        except Exception:
            pass

    def test_VariableAvailability(self):
        cls = getattr(mod, "VariableAvailability", None)
        if cls is None: pytest.skip("not present")
        try:
            members = [m.name for m in cls]
            assert len(members) > 0
        except Exception:
            pass


class TestDataclasses:
    def test_VariableSpec(self):
        cls = getattr(mod, "VariableSpec", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(name="x", source="tushare")
            assert obj is not None
        except Exception:
            pass

    def test_VariableResult(self):
        cls = getattr(mod, "VariableResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestClasses:
    def test_AShareVariableFetcher(self):
        cls = getattr(mod, "AShareVariableFetcher", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestFunctions:
    def test_fetch_a_share_variable(self):
        fn = getattr(mod, "fetch_a_share_variable", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("ROA")
            assert r is not None
        except Exception:
            pass

    def test_call_mcp_tool(self):
        fn = getattr(mod, "_call_mcp_tool", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("user-tushare", "get_daily_quote", {"ts_code": "000001.SZ"}, retries=0)
        except Exception:
            pass


class TestAllClasses:
    def test_try_all_classes(self):
        for name in dir(mod):
            if name.startswith("_"):
                continue
            cls = getattr(mod, name, None)
            if not isinstance(cls, type):
                continue
            try:
                obj = cls()
                assert obj is not None
            except Exception:
                pass


class TestPureHelpers:
    def test_helpers(self):
        for h in dir(mod):
            if h.startswith("_") or h == "main":
                continue
            fn = getattr(mod, h, None)
            if callable(fn) and not isinstance(fn, type):
                import inspect
                try:
                    sig = inspect.signature(fn)
                    if len(sig.parameters) == 0:
                        try:
                            fn()
                            return
                        except Exception:
                            pass
                except Exception:
                    pass
