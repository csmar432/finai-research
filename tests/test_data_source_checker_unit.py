"""Unit tests for scripts/data_source_checker.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def dsc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import data_source_checker as d
    yield d
    if _p in sys.path:
        sys.path.remove(_p)


class TestDataSource:
    def test_sources(self, dsc):
        assert dsc.DataSource.TUSHARE in dsc.DataSource
        assert dsc.DataSource.WIND in dsc.DataSource


class TestDataSourceChecker:
    def test_class_exists(self, dsc):
        assert hasattr(dsc, "DataSourceChecker")

    def test_init(self, dsc):
        checker = dsc.DataSourceChecker(requirements=[])
        assert checker is not None
