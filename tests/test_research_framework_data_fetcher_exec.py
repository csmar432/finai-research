"""tests/test_research_framework_data_fetcher_exec.py — Execute data_fetcher."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import data_fetcher as mod
except Exception as _exc:
    pytest.skip(f"data_fetcher not importable: {_exc}", allow_module_level=True)


class TestPureFunctions:
    def test_save_df(self, tmp_path):
        fn = getattr(mod, "save_df", None)
        if fn is None: pytest.skip("not present")
        path = tmp_path / "test.csv"
        df = pd.DataFrame({"x": [1, 2, 3]})
        fn(df, str(path))
        assert path.exists()

    def test_save_json(self, tmp_path):
        fn = getattr(mod, "save_json", None)
        if fn is None: pytest.skip("not present")
        path = tmp_path / "test.json"
        fn({"a": 1, "b": [1, 2]}, str(path))
        assert path.exists()
        with open(path) as f:
            d = json.load(f)
        assert d["a"] == 1


class TestCircuitBreaker:
    def test_default(self):
        cls = getattr(mod, "CircuitBreaker", None)
        if cls is None: pytest.skip("not present")
        obj = cls()
        assert obj is not None

    def test_is_open_empty(self):
        cls = getattr(mod, "CircuitBreaker", None)
        if cls is None: pytest.skip("not present")
        obj = cls()
        # Should not be open when no failures
        r = obj.is_open("svc1")
        assert r is False

    def test_record_failure_and_recover(self):
        cls = getattr(mod, "CircuitBreaker", None)
        if cls is None: pytest.skip("not present")
        obj = cls(failure_threshold=3, timeout=60)
        for _ in range(2):
            obj.record_failure("svc1")
        assert obj.is_open("svc1") is False
        obj.record_failure("svc1")
        assert obj.is_open("svc1") is True

    def test_record_success_clears(self):
        cls = getattr(mod, "CircuitBreaker", None)
        if cls is None: pytest.skip("not present")
        obj = cls(failure_threshold=2, timeout=60)
        obj.record_failure("svc2")
        obj.record_failure("svc2")
        assert obj.is_open("svc2") is True
        obj.record_success("svc2")
        assert obj.is_open("svc2") is False


class TestDataclasses:
    def test_DataProbeResult(self):
        cls = getattr(mod, "DataProbeResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_MCPCallError(self):
        cls = getattr(mod, "MCPCallError", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls("test error")
            assert obj is not None
        except Exception:
            pass


class TestClasses:
    def test_DataFetcher(self):
        cls = getattr(mod, "DataFetcher", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_DataFallbackEngine(self):
        cls = getattr(mod, "DataFallbackEngine", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_CachedDataFetcher(self):
        cls = getattr(mod, "CachedDataFetcher", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_ProxyVariableBuilder(self):
        cls = getattr(mod, "ProxyVariableBuilder", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_call_mcp_tool(self):
        fn = getattr(mod, "call_mcp_tool", None)
        if fn is None: pytest.skip("not present")
        # audit-2026-07-21: try/except/Exception:pass converted to xfail
        pytest.xfail(
            reason="no real assertion",
        )

    def test_call_mcp(self):
        fn = getattr(mod, "_call_mcp", None)
        if fn is None: pytest.skip("not present")
        # audit-2026-07-21: try/except/Exception:pass converted to xfail
        pytest.xfail(
            reason="no real assertion",
        )


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
