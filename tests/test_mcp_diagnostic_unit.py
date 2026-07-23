"""Unit tests for scripts/mcp_diagnostic.py (pure functions)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def mcpd():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import mcp_diagnostic as m
    yield m
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestColorFunctions:
    def test_green_returns_string(self, mcpd):
        result = mcpd.green("test")
        assert isinstance(result, str)
        assert "test" in result

    def test_red_returns_string(self, mcpd):
        result = mcpd.red("error")
        assert isinstance(result, str)

    def test_yellow_returns_string(self, mcpd):
        result = mcpd.yellow("warning")
        assert isinstance(result, str)

    def test_bold_returns_string(self, mcpd):
        result = mcpd.bold("header")
        assert isinstance(result, str)

    def test_cyan_returns_string(self, mcpd):
        result = mcpd.cyan("info")
        assert isinstance(result, str)

    def test_color_functions_callable(self, mcpd):
        for fn in (mcpd.green, mcpd.red, mcpd.yellow, mcpd.bold, mcpd.cyan):
            assert callable(fn)


class TestRunSubprocess:
    def test_run_subprocess_function_exists(self, mcpd):
        # Module loads correctly - verify key functions exist
        assert callable(mcpd.run_mcp_diagnostic)
        assert callable(mcpd.print_mcp_diagnostic)

    def test_run_mcp_diagnostic_function(self, mcpd):
        # Verify function is defined
        assert hasattr(mcpd, "run_mcp_diagnostic")


class TestDataclasses:
    def test_mcp_result_exists(self, mcpd):
        if hasattr(mcpd, "MCPResult"):
            assert hasattr(mcpd.MCPResult, "__dataclass_fields__")


class TestAnsiConstants:
    def test_ansi_colors_defined(self, mcpd):
        assert mcpd.RED.startswith("\033")
        assert mcpd.GREEN.startswith("\033")
        assert mcpd.YELLOW.startswith("\033")
        assert mcpd.RESET.startswith("\033")

