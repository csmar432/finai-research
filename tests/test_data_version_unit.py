"""Unit tests for scripts/data_version.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def dv():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import data_version as d
    yield d
    if _p in sys.path:
        sys.path.remove(_p)


class TestDataSnapshot:
    def test_init(self, dv):
        snap = dv.DataSnapshot(
            version_id="v1",
            ticker="000001.SZ",
            data_type="daily_quote",
            data_hash="abc123",
            row_count=1000,
            columns=["open", "close"],
            date_range=("2024-01-01", "2024-12-31"),
            fetched_at="2024-12-31",
            source="tushare",
            file_path="/data/v1.parquet",
        )
        assert snap.version_id == "v1"
        assert snap.row_count == 1000


class TestDataDiff:
    def test_init(self, dv):
        diff = dv.DataDiff(
            ticker="000001.SZ",
            version1="v1",
            version2="v2",
            row_count_diff=100,
            column_diff=[],
            value_changes={},
            summary="+100 rows",
        )
        assert diff.summary == "+100 rows"


class TestDataVersionManager:
    def test_init(self, dv):
        mgr = dv.DataVersionManager()
        assert mgr is not None
