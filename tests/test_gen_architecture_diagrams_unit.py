"""Unit tests for scripts/gen_architecture_diagrams.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture(autouse=True)
def setup_path():
    sys.path.insert(0, str(SCRIPTS_DIR))
    yield
    if str(SCRIPTS_DIR) in sys.path:
        sys.path.remove(str(SCRIPTS_DIR))


class TestEsc:
    """_esc() escapes XML special characters."""

    def test_escapes_ampersand(self):
        from gen_architecture_diagrams import _esc
        assert _esc("A & B") == "A &amp; B"

    def test_escapes_less_than(self):
        from gen_architecture_diagrams import _esc
        assert _esc("a < b") == "a &lt; b"

    def test_escapes_greater_than(self):
        from gen_architecture_diagrams import _esc
        assert _esc("x > y") == "x &gt; y"

    def test_escapes_all_three(self):
        from gen_architecture_diagrams import _esc
        assert _esc("<A & B>") == "&lt;A &amp; B&gt;"

    def test_passthrough_clean_text(self):
        from gen_architecture_diagrams import _esc
        assert _esc("Normal Text 123") == "Normal Text 123"


class TestHeader:
    """header() generates SVG page header."""

    def test_contains_svg_defs(self):
        from gen_architecture_diagrams import header
        result = header("Test Title", "Test Subtitle")
        assert "<defs>" in result
        assert "bgGrad" in result
        assert "grid" in result

    def test_contains_background_rect(self):
        from gen_architecture_diagrams import header
        result = header("My Title", "My Subtitle")
        assert 'fill="url(#bgGrad)"' in result

    def test_title_in_output(self):
        from gen_architecture_diagrams import header
        result = header("My Title", "My Subtitle")
        assert "My Title" in result
        assert "My Subtitle" in result

    def test_version_in_output(self):
        from gen_architecture_diagrams import header
        result = header("T", "S", version="v1.2.3")
        assert "v1.2.3" in result


class TestFooter:
    """footer() generates SVG page footer."""

    def test_contains_line(self):
        from gen_architecture_diagrams import footer
        result = footer(1, 5)
        assert "line" in result.lower()

    def test_shows_index(self):
        from gen_architecture_diagrams import footer
        result = footer(3, 5)
        assert "FIGURE 03 / 05" in result

    def test_mit_license(self):
        from gen_architecture_diagrams import footer
        result = footer(1)
        assert "MIT" in result or "开源" in result


class TestNode:
    """node() generates SVG rounded-rectangle node."""

    def test_contains_rect(self):
        from gen_architecture_diagrams import node
        result = node(100, 100, 200, 60, "Test Node")
        assert "<rect" in result

    def test_contains_text(self):
        from gen_architecture_diagrams import node
        result = node(100, 100, 200, 60, "Node Title")
        assert "Node Title" in result

    def test_with_description(self):
        from gen_architecture_diagrams import node
        result = node(100, 100, 200, 60, "Title", "Description")
        assert "Description" in result

    def test_without_description(self):
        from gen_architecture_diagrams import node
        result = node(100, 100, 200, 60, "Title", "")
        assert result.count("<text") == 1  # Only title text, no desc

    def test_different_colors(self):
        from gen_architecture_diagrams import node, COL_INTERFACE, COL_DATA
        r1 = node(100, 100, 200, 60, "A", col=COL_INTERFACE)
        r2 = node(100, 100, 200, 60, "B", col=COL_DATA)
        # Colors differ
        assert r1 != r2


class TestArrow:
    """arrow() generates SVG arrow connector."""

    def test_contains_line(self):
        from gen_architecture_diagrams import arrow
        result = arrow(0, 0, 100, 100)
        assert "<line" in result

    def test_contains_marker(self):
        from gen_architecture_diagrams import arrow
        result = arrow(0, 0, 100, 100)
        assert "marker" in result.lower()

    def test_with_label(self):
        from gen_architecture_diagrams import arrow
        result = arrow(0, 0, 100, 100, label="uses")
        assert "uses" in result

    def test_dashed(self):
        from gen_architecture_diagrams import arrow
        result = arrow(0, 0, 100, 100, dashed=True)
        assert "stroke-dasharray" in result


class TestSection:
    """section() generates SVG grouping rectangle."""

    def test_contains_rect(self):
        from gen_architecture_diagrams import section
        result = section(50, 100, 300, 500, "Group Label")
        assert "<rect" in result

    def test_contains_label(self):
        from gen_architecture_diagrams import section
        result = section(50, 100, 300, 500, "Group Label")
        assert "Group Label" in result

    def test_custom_color(self):
        from gen_architecture_diagrams import section
        result = section(50, 100, 300, 500, "Label", color="#ff0000")
        assert "#ff0000" in result


class TestWrap:
    """wrap() is a passthrough function."""

    def test_passthrough(self):
        from gen_architecture_diagrams import wrap
        text = "some text with\nnewlines"
        assert wrap(text) == text


class TestModuleConstants:
    """Module-level constants are defined correctly."""

    def test_mcp_count_is_integer(self):
        from gen_architecture_diagrams import MCP_COUNT
        assert isinstance(MCP_COUNT, int)
        assert MCP_COUNT > 0

    def test_dimensions_are_integers(self):
        from gen_architecture_diagrams import WIDTH, HEIGHT
        assert isinstance(WIDTH, int)
        assert isinstance(HEIGHT, int)
        assert WIDTH > 0
        assert HEIGHT > 0

    def test_color_tuples_length(self):
        from gen_architecture_diagrams import (
            COL_INTERFACE, COL_DATA, COL_PROCESS, COL_CONTROL, COL_USER
        )
        for col in [COL_INTERFACE, COL_DATA, COL_PROCESS, COL_CONTROL, COL_USER]:
            assert isinstance(col, tuple)
            assert len(col) == 2

    def test_fonts_are_strings(self):
        from gen_architecture_diagrams import FONT, MONO
        assert isinstance(FONT, str)
        assert isinstance(MONO, str)


class TestGenArchitectureOverview:
    """gen_01_architecture_overview() generates valid SVG."""

    def test_returns_svg_string(self):
        from gen_architecture_diagrams import gen_01_architecture_overview
        result = gen_01_architecture_overview()
        assert result.startswith("<svg")
        assert "</svg>" in result

    def test_contains_all_layers(self):
        from gen_architecture_diagrams import gen_01_architecture_overview
        result = gen_01_architecture_overview()
        assert "INPUTS" in result
        assert "WRITING TRACK" in result
        assert "EMPIRICAL TRACK" in result
        assert "DELIVERY" in result
        assert "Local data" in result

    def test_contains_mcp_count(self):
        from gen_architecture_diagrams import gen_01_architecture_overview, MCP_COUNT
        result = gen_01_architecture_overview()
        assert str(MCP_COUNT) in result
