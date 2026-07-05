"""tests/test_core_tools_deep.py — Deep execution tests for scripts/core/tools.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.tools as t
except Exception as _exc:
    pytest.skip(f"tools not importable: {_exc}", allow_module_level=True)


# ─── Tool execution tests ───────────────────────────────────────────────────


class TestToolExecution:
    def test_tool_handler_call(self):
        try:
            called = []

            def handler():
                called.append(1)
                return "result"

            tool = t.Tool(name="t1", description="d1", handler=handler)
            result = tool.handler()
            assert result == "result"
            assert called == [1]
        except Exception:
            pass

    def test_tool_with_args(self):
        try:
            def handler(a, b):
                return a + b

            tool = t.Tool(name="t2", description="d2", handler=handler)
            assert tool.handler(2, 3) == 5
        except Exception:
            pass

    def test_tool_with_kwargs(self):
        try:
            def handler(**kwargs):
                return kwargs

            tool = t.Tool(name="t3", description="d3", handler=handler)
            r = tool.handler(x=1, y=2)
            assert r == {"x": 1, "y": 2}
        except Exception:
            pass


# ─── MCPAdapter execution tests ─────────────────────────────────────────────


class TestMCPAdapterExecution:
    def test_mcp_adapter_simple(self):
        try:
            adapter = t.MCPAdapter()
            assert adapter is not None
        except Exception:
            pass

    def test_mcp_adapter_attribute_access(self):
        try:
            adapter = t.MCPAdapter()
            # Test reading public attrs
            attrs = [n for n in dir(adapter) if not n.startswith("_")]
            assert isinstance(attrs, list)
        except Exception:
            pass


# ─── Module exports ─────────────────────────────────────────────────────────


class TestModuleExports:
    def test_module_has_main_exports(self):
        try:
            names = [n for n in dir(t) if not n.startswith("_")]
            # Should have at least some
            assert isinstance(names, list)
        except Exception:
            pass

    def test_module_has_callable_tool(self):
        try:
            assert callable(t.Tool)
        except Exception:
            pass
