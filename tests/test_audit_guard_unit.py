"""Unit tests for scripts/audit_guard.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ag():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import audit_guard as a
    yield a
    if _p in sys.path:
        sys.path.remove(_p)


class TestAuditCheck:
    def test_init(self, ag):
        check = ag.AuditCheck(
            id="c1",
            title="Test check",
            description="Verifies X",
            run=lambda: True,
        )
        assert check.id == "c1"
        assert check.title == "Test check"


class TestCheckResult:
    def test_init(self, ag):
        result = ag.CheckResult(
            passed=True,
            actual="100 tests pass",
            expected="100 tests",
            evidence=["file:test.py"],
        )
        assert result.passed is True
        assert "file:test.py" in result.evidence


class TestChecksList:
    def test_checks_list_exists(self, ag):
        assert hasattr(ag, "CHECKS")
        assert isinstance(ag.CHECKS, list)
