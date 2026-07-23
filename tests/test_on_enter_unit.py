"""Unit tests for scripts/on_enter.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def oe():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import on_enter as o
    yield o
    if _p in sys.path:
        sys.path.remove(_p)


class TestFunctions:
    def test_print_banner(self, oe):
        assert callable(oe.print_banner)

    def test_print_macro_calendar(self, oe):
        assert callable(oe.print_macro_calendar)

    def test_print_menu(self, oe):
        assert callable(oe.print_menu)

    def test_print_status(self, oe):
        assert callable(oe.print_status)

    def test_main(self, oe):
        assert callable(oe.main)
