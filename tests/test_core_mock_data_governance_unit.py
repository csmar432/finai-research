"""Unit tests for scripts/core/mock_data_governance.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def mdg():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import mock_data_governance as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestMockDataPolicy:
    def test_exists(self, mdg):
        assert hasattr(mdg, "MockDataPolicy")


class TestMockDataRegistry:
    def test_init(self, mdg):
        r = mdg.MockDataRegistry()
        assert r is not None