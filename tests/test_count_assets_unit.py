"""Unit tests for scripts/count_assets.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ca():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import count_assets as c
    yield c
    if _p in sys.path:
        sys.path.remove(_p)


class TestCountFunctions:
    def test_count_all_returns_dict(self, ca):
        result = ca.count_all()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_count_econometric_methods_returns_int(self, ca):
        count = ca.count_econometric_methods()
        assert isinstance(count, int)
        assert count >= 0

    def test_count_journal_templates_returns_dict(self, ca):
        result = ca.count_journal_templates()
        assert isinstance(result, dict)

    def test_count_mcp_servers_returns_dict(self, ca):
        result = ca.count_mcp_servers()
        assert isinstance(result, dict)

    def test_project_root_path(self, ca):
        assert isinstance(ca.PROJECT_ROOT, Path)
        assert ca.PROJECT_ROOT.exists()
