"""Unit tests for scripts/enhanced_workflow.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ew():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import enhanced_workflow as e
    yield e
    if _p in sys.path:
        sys.path.remove(_p)


class TestWorkflowMode:
    def test_modes(self, ew):
        assert ew.WorkflowMode.FULL in ew.WorkflowMode
        assert ew.WorkflowMode.RESEARCH in ew.WorkflowMode


class TestPaperType:
    def test_types(self, ew):
        assert ew.PaperType.EMPIRICAL_PAPER in ew.PaperType
        assert ew.PaperType.FINANCE_REPORT in ew.PaperType


class TestWorkflowConfig:
    def test_init(self, ew):
        cfg = ew.WorkflowConfig(
            mode=ew.WorkflowMode.FULL,
            paper_type=ew.PaperType.EMPIRICAL_PAPER,
            auto_approve=False,
            enable_evolution=True,
            enable_parliament=True,
            citation_verification=True,
            halt_rules_check=True,
            output_dir=None,
        )
        assert cfg.auto_approve is False
        assert cfg.output_dir is not None


class TestCitationCheckResult:
    def test_init(self, ew):
        r = ew.CitationCheckResult(
            total_citations=100,
            verified=85,
            unverified=15,
            context_issues=[],
            intent_distribution={"support": 50},
            freshness_scores=[0.9, 0.85],
            overall_quality=0.85,
        )
        assert r.total_citations == 100
        assert r.verified == 85


class TestWorkflowResult:
    def test_init(self, ew):
        r = ew.WorkflowResult(
            success=True,
            workflow_type="FULL",
            duration_ms=5000,
            results={},
        )
        assert r.success is True
        assert r.errors == []
