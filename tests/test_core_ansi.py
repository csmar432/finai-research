"""Unit tests for scripts.core.ansi color helpers.

P3 2026-06-29: Added to keep coverage >= 30% after scripts/core/ansi.py was
extracted from scripts/mcp_diagnostic.py (used by agent_pipeline).

ansi._ansi() returns plain text when stdout is not a TTY (e.g. under pytest),
so we monkeypatch sys.stdout.isatty to True to exercise the ANSI branch.
"""
from __future__ import annotations

import sys

import pytest

from scripts.core import ansi


@pytest.fixture
def force_color(monkeypatch):
    """Make _ansi() think it is writing to a TTY so it emits ANSI codes."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)


def test_bold_wraps_text_in_ansi_escape(force_color):
    out = ansi.bold("hello")
    assert out.startswith("\033[1m")
    assert out.endswith("\033[0m")
    assert "hello" in out


def test_dim_wraps_text(force_color):
    out = ansi.dim("x")
    assert out.startswith("\033[2m")
    assert out.endswith("\033[0m")


def test_known_colors_wrap_correctly(force_color):
    assert ansi.cyan("c").startswith("\033[36m")
    assert ansi.yellow("y").startswith("\033[33m")
    assert ansi.red("r").startswith("\033[31m")
    assert ansi.green("g").startswith("\033[32m")
    assert ansi.blue("b").startswith("\033[34m")
    assert ansi.magenta("m").startswith("\033[35m")


def test_non_tty_returns_plain_text():
    # When stdout is not a TTY, _ansi should be a no-op
    out = ansi.bold("plain")
    assert out == "plain"


def test_all_exports():
    # __all__ should expose every helper so test_type_audit.py is happy
    assert hasattr(ansi, "__all__")
    for name in ansi.__all__:
        assert callable(getattr(ansi, name))
