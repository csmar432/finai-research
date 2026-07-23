"""Unit tests for scripts/core/mock_template_engine.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def mte():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import mock_template_engine as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestMockResult:
    def test_init(self, mte):
        r = mte.MockResult(
            content="Mock content",
            latency_ms=10,
        )
        assert r.content == "Mock content"
        assert r.model == "mock_template"
        assert r.provider == "template"
        assert r.is_mock is True
        assert r.error is None
