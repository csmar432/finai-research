"""Unit tests for scripts/green_credit_regression.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def gcr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import green_credit_regression as g
    yield g
    if _p in sys.path:
        sys.path.remove(_p)


class TestDIDRegression:
    def test_init(self, gcr):
        did = gcr.DIDRegression()
        assert did.data is None


class TestOLSRegression:
    def test_init(self, gcr):
        ols = gcr.OLSRegression()
        assert ols.data is None


class TestRegressionTable:
    def test_init(self, gcr):
        tbl = gcr.RegressionTable()
        assert tbl.data is None
