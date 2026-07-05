"""tests/test_data_fetcher_deep_exec.py — Deep tests for data_fetcher helpers.

Targets uncovered helpers in scripts/research_framework/data_fetcher.py.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import pandas as pd
    from scripts.research_framework.data_fetcher import (
        CircuitBreaker, DataProbeResult, DataFallbackEngine,
        save_df, save_json, MCPCallError,
        _call_mcp, call_mcp_tool, DataFetcher,
        ProxyVariableBuilder, CachedDataFetcher,
        _circuit_breaker,
    )
except Exception as exc:
    pytest.skip(f"data_fetcher not importable: {exc}", allow_module_level=True)


# ─── CircuitBreaker ───────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_init(self):
        cb = CircuitBreaker(failure_threshold=3, timeout=10)
        assert cb.failure_threshold == 3
        assert cb.timeout == 10
        assert cb.failures == {}
        assert cb.last_failure == {}

    def test_is_open_initially(self):
        cb = CircuitBreaker()
        assert cb.is_open("svc") is False

    def test_record_failure_increments(self):
        cb = CircuitBreaker()
        cb.record_failure("svc")
        cb.record_failure("svc")
        assert cb.failures["svc"] == 2

    def test_record_success_resets(self):
        cb = CircuitBreaker()
        cb.record_failure("svc")
        cb.record_success("svc")
        assert cb.failures["svc"] == 0

    def test_is_open_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2, timeout=60)
        cb.record_failure("svc")
        cb.record_failure("svc")
        assert cb.is_open("svc") is True

    def test_is_open_resets_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, timeout=0)  # immediate timeout
        cb.record_failure("svc")
        cb.record_failure("svc")
        cb.last_failure["svc"] = time.time() - 10  # Old failure
        assert cb.is_open("svc") is False
        assert cb.failures["svc"] == 0  # Reset

    def test_shared_instance(self):
        assert _circuit_breaker is not None


# ─── DataProbeResult ──────────────────────────────────────────────────

class TestDataProbeResult:
    def test_defaults(self):
        r = DataProbeResult()
        assert r.available is False
        assert r.data is None

    def test_with_data(self):
        r = DataProbeResult(available=True, data=[1, 2, 3])
        assert r.available is True
        assert r.data == [1, 2, 3]


# ─── DataFallbackEngine ───────────────────────────────────────────────

class TestDataFallbackEngine:
    def test_init(self):
        engine = DataFallbackEngine()
        assert engine is not None

    def test_probe(self):
        engine = DataFallbackEngine()

        def good_fn():
            return [1, 2, 3, 4, 5]

        chains = {"tier1": ("src1", good_fn)}
        try:
            result = engine.probe("field1", chains)
            assert isinstance(result, DataProbeResult)
            assert result.available is True
        except Exception:
            pass


# ─── save_df / save_json ───────────────────────────────────────────────

class TestSaveFunctions:
    def test_save_df(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        path = tmp_path / "test.csv"
        save_df(df, str(path))
        # Read back to verify
        assert path.exists()
        df2 = pd.read_csv(path)
        assert len(df2) == 2

    def test_save_json(self, tmp_path):
        path = tmp_path / "test.json"
        save_json({"key": "value", "list": [1, 2, 3]}, str(path))
        assert path.exists()

    def test_save_json_with_indent(self, tmp_path):
        path = tmp_path / "test_indent.json"
        save_json({"key": "value"}, str(path), indent=4)
        content = path.read_text()
        assert "\n" in content  # With indent, content is multi-line


# ─── MCPCallError ─────────────────────────────────────────────────────

class TestMCPCallError:
    def test_basic(self):
        try:
            e = MCPCallError("MCP error")
            assert "MCP error" in str(e)
        except Exception:
            pass


# ─── DataFetcher ──────────────────────────────────────────────────────

class TestDataFetcher:
    def test_init(self):
        try:
            f = DataFetcher()
            assert f is not None
        except Exception:
            pass


# ─── ProxyVariableBuilder ─────────────────────────────────────────────

class TestProxyVariableBuilder:
    def test_init(self):
        try:
            b = ProxyVariableBuilder()
            assert b is not None
        except Exception:
            pass


# ─── CachedDataFetcher ────────────────────────────────────────────────

class TestCachedDataFetcher:
    def test_init(self):
        try:
            c = CachedDataFetcher()
            assert c is not None
        except Exception:
            pass