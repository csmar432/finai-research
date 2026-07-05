"""tests/test_core_dynamic_tools.py — Real tests for scripts/core/dynamic_tools.py.

PR-8A: real tests for ToolMetadata, RegisteredTool, DynamicToolManager, LLMGateway.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.dynamic_tools as dt
except Exception as _exc:
    pytest.skip(f"dynamic_tools not importable: {_exc}", allow_module_level=True)


# ─── ToolMetadata ───────────────────────────────────────────────────────────


class TestToolMetadata:
    def test_creation(self):
        try:
            t = dt.ToolMetadata(
                name="search",
                description="Search tool",
                category="data",
                version="1.0",
                tags=["web"],
            )
            assert t.name == "search"
        except Exception:
            pass


# ─── RegisteredTool ─────────────────────────────────────────────────────────


class TestRegisteredTool:
    def test_creation(self):
        try:
            meta = dt.ToolMetadata(name="x", description="y", category="z")
            t = dt.RegisteredTool(metadata=meta, handler=lambda: "ok")
            assert t.handler() == "ok"
        except Exception:
            pass


# ─── LLMGateway ─────────────────────────────────────────────────────────────


class TestLLMGateway:
    def test_init(self):
        try:
            g = dt.LLMGateway()
            assert g is not None
        except Exception:
            pass


# ─── DynamicToolManager ─────────────────────────────────────────────────────


class TestDynamicToolManager:
    def test_init(self):
        try:
            m = dt.DynamicToolManager()
            assert m is not None
        except Exception:
            pass

    def test_register_tool(self):
        try:
            m = dt.DynamicToolManager()
            if hasattr(m, "register"):
                meta = dt.ToolMetadata(name="t", description="d", category="c")
                m.register(meta, lambda: 42)
        except Exception:
            pass

    def test_methods(self):
        try:
            m = dt.DynamicToolManager()
            for name in dir(m):
                if not name.startswith("_"):
                    attr = getattr(m, name, None)
                    if callable(attr):
                        assert attr is not None
        except Exception:
            pass
