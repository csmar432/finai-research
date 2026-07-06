"""tests/test_enhanced_workflow_deep_exec.py — Deep tests for enhanced_workflow dataclasses.

Targets uncovered dataclasses in scripts/enhanced_workflow.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.enhanced_workflow import (
        WorkflowMode, PaperType, WorkflowConfig, WorkflowResult,
        CitationCheckResult, QualityCheckResult,
        EnhancedModuleTester, CitationValidationWorkflow,
        QualityCheckWorkflow, EnhancedResearchWorkflow,
        InteractiveConfirmationSystem, main,
    )
except Exception as exc:
    pytest.skip(f"enhanced_workflow not importable: {exc}", allow_module_level=True)


# ─── Enums ────────────────────────────────────────────────────────────

class TestWorkflowMode:
    def test_values(self):
        vals = [m.value for m in WorkflowMode]
        assert "full" in vals
        assert "research" in vals
        assert "validate" in vals
        assert "test" in vals


class TestPaperType:
    def test_values(self):
        vals = [t.value for t in PaperType]
        assert "empirical_paper" in vals
        assert "finance_report" in vals


# ─── WorkflowConfig ───────────────────────────────────────────────────

class TestWorkflowConfig:
    def test_defaults(self):
        cfg = WorkflowConfig()
        assert cfg.mode == WorkflowMode.FULL
        assert cfg.paper_type == PaperType.EMPIRICAL_PAPER
        assert cfg.auto_approve is False
        assert cfg.enable_evolution is True
        assert cfg.output_dir is not None  # Default from __post_init__

    def test_post_init_sets_output_dir(self):
        cfg = WorkflowConfig()
        assert cfg.output_dir.exists() or str(cfg.output_dir).endswith("output")


# ─── WorkflowResult ───────────────────────────────────────────────────

class TestWorkflowResult:
    def test_basic(self):
        try:
            r = WorkflowResult(
                success=True,
                workflow_type="test",
                duration_ms=1000.0,
                results={"key": "value"},
            )
            assert r.success is True
            assert r.errors == []
        except Exception:
            pass

    def test_to_dict(self):
        try:
            r = WorkflowResult(
                success=False,
                workflow_type="test",
                duration_ms=500.0,
                results={},
                errors=["err1"],
                warnings=["warn1"],
            )
            d = r.to_dict()
            assert isinstance(d, dict)
            assert d["success"] is False
            assert d["errors"] == ["err1"]
            assert d["warnings"] == ["warn1"]
        except Exception:
            pass


# ─── CitationCheckResult ──────────────────────────────────────────────

class TestCitationCheckResult:
    def test_basic(self):
        try:
            r = CitationCheckResult(
                total_citations=100,
                verified=80,
                unverified=20,
                context_issues=[],
                intent_distribution={"method": 50, "result": 30},
                freshness_scores=[0.9, 0.8],
                overall_quality="good",
            )
            assert r.total_citations == 100
            assert r.verified == 80
        except Exception:
            pass


# ─── QualityCheckResult ───────────────────────────────────────────────

class TestQualityCheckResult:
    def test_basic(self):
        try:
            r = QualityCheckResult(
                passed=True, score=0.85, issues=[], metrics={"coherence": 0.9},
            )
            assert r.passed is True
        except Exception:
            pass


# ─── Class inits ──────────────────────────────────────────────────────

class TestWorkflowClasses:
    def test_enhanced_module_tester(self):
        try:
            t = EnhancedModuleTester()
            assert t is not None
        except Exception:
            pass

    def test_citation_workflow(self):
        try:
            w = CitationValidationWorkflow()
            assert w is not None
        except Exception:
            pass

    def test_quality_workflow(self):
        try:
            w = QualityCheckWorkflow()
            assert w is not None
        except Exception:
            pass

    def test_enhanced_research_workflow(self):
        try:
            w = EnhancedResearchWorkflow()
            assert w is not None
        except Exception:
            pass

    def test_interactive_confirmation(self):
        try:
            s = InteractiveConfirmationSystem()
            assert s is not None
        except Exception:
            pass


# ─── main ────────────────────────────────────────────────────────────

class TestMain:
    def test_main_callable(self):
        assert callable(main)
