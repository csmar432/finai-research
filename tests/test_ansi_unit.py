"""Unit tests for scripts/core/ansi.py."""

from __future__ import annotations

import sys
from unittest.mock import patch

from scripts.core import ansi
from scripts.core.ansi import (
    _ansi,
    blue,
    bold,
    cyan,
    dim,
    green,
    magenta,
    red,
    yellow,
)


class TestANSIBasics:
    """When stdout is not a TTY (most CI), helpers return text unchanged."""

    def test_ansi_returns_plain_text_when_not_tty(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            assert _ansi("1", "hello") == "hello"

    def test_ansi_returns_colored_when_tty(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            result = _ansi("1", "hello")
            assert "\033[" in result
            assert "hello" in result
            assert "1" in result

    def test_ansi_preserves_text_content(self):
        out = _ansi("31", "warning text")
        assert "warning text" in out


class TestColorFunctions:
    """All exported color functions exist and return strings."""

    def test_bold_returns_str(self):
        out = bold("x")
        assert isinstance(out, str)
        assert "x" in out

    def test_dim_returns_str(self):
        out = dim("x")
        assert isinstance(out, str)

    def test_cyan_returns_str(self):
        out = cyan("x")
        assert isinstance(out, str)

    def test_yellow_returns_str(self):
        out = yellow("x")
        assert isinstance(out, str)

    def test_red_returns_str(self):
        out = red("x")
        assert isinstance(out, str)

    def test_green_returns_str(self):
        out = green("x")
        assert isinstance(out, str)

    def test_blue_returns_str(self):
        out = blue("x")
        assert isinstance(out, str)

    def test_magenta_returns_str(self):
        out = magenta("x")
        assert isinstance(out, str)


class TestColorCodes:
    """Each color uses the correct ANSI code when TTY."""

    def test_bold_uses_code_1(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[1m" in bold("x")

    def test_dim_uses_code_2(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[2m" in dim("x")

    def test_cyan_uses_code_36(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[36m" in cyan("x")

    def test_yellow_uses_code_33(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[33m" in yellow("x")

    def test_red_uses_code_31(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[31m" in red("x")

    def test_green_uses_code_32(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[32m" in green("x")

    def test_blue_uses_code_34(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[34m" in blue("x")

    def test_magenta_uses_code_35(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert "\033[35m" in magenta("x")


class TestExportList:
    """Module __all__ defines the public API."""

    def test_all_contains_expected_colors(self):
        expected = {"bold", "dim", "cyan", "yellow", "red", "green", "blue", "magenta"}
        assert expected.issubset(set(ansi.__all__))

    def test_all_does_not_include_private(self):
        assert "_ansi" not in ansi.__all__

    def test_all_size(self):
        assert len(ansi.__all__) >= 8


class TestNestedCalls:
    """Helpers compose well — nested color calls work."""

    def test_bold_cyan_nested(self):
        out = bold(cyan("x"))
        assert "x" in out

    def test_red_bold_double(self):
        out = red(bold("error"))
        assert "error" in out
