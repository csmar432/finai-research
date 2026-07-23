"""Unit tests for scripts/core/platform.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def p():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import platform as pl
    yield pl
    if _p in sys.path:
        sys.path.remove(_p)


class TestPlatformInfo:
    def test_class_exists(self, p):
        assert hasattr(p, "PlatformInfo")


class TestFunctions:
    def test_get_mcp_config(self, p):
        assert callable(p.get_mcp_config)

    def test_get_canvas_file_path(self, p):
        assert callable(p.get_canvas_file_path)

    def test_get_mcp_servers_root(self, p):
        assert callable(p.get_mcp_servers_root)

    def test_get_mcp_config_paths(self, p):
        assert callable(p.get_mcp_config_paths)

    def test_discover_mcp_servers(self, p):
        assert callable(p.discover_mcp_servers)
