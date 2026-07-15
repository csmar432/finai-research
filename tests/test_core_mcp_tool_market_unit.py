"""Unit tests for scripts/core/mcp_tool_market.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def mm():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import mcp_tool_market as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestToolMetadata:
    def test_class_exists(self, mm):
        assert hasattr(mm, "ToolMetadata")


class TestMCPToolRegistry:
    def test_class_exists(self, mm):
        assert hasattr(mm, "MCPToolRegistry")

    def test_init(self, mm):
        registry = mm.MCPToolRegistry()
        assert registry is not None
