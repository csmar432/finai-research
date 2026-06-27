"""Smoke tests for all 6 PRs (PR6, Audit 2026-06-27).

验证所有 PR 的关键功能在单次运行中无回归。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# ─── PR1: NORA ────────────────────────────────────────────────────────────────


def test_pr1_nora_orchestrator_import():
    from scripts.core.nora_orchestrator import (
        NoraOrchestrator,
        NoraStage,
        ResearchProfile,
        VariableCandidate,
    )
    assert NoraOrchestrator is not None
    assert NoraStage.QUESTION_TYPE.value == "question_type"
    profile = ResearchProfile(topic="test")
    assert hasattr(profile, "locked_at")


# ─── PR2: VariableRedundancy + DataGate ────────────────────────────────────────


def test_pr2_variable_redundancy_resolver():
    from scripts.core.variable_redundancy import VariableRedundancyResolver
    from scripts.core.nora_orchestrator import ResearchProfile

    profile = ResearchProfile(topic="碳排放权交易对绿色创新的影响", identification="DID")
    resolver = VariableRedundancyResolver(output_dir=Path("/tmp/pr6_test"))
    report = resolver.resolve(profile)
    # 碳排放主题只触发部分变量模板，关键是因变量/自变量必须有
    assert len(report.dependent_candidates) >= 1
    assert len(report.independent_candidates) >= 1


def test_pr2_data_gate_blocks_without_session(tmp_path):
    from scripts.core.data_gate import DataGate, DataGateLevel

    gate = DataGate(session_dir=tmp_path, level=DataGateLevel.FULL)
    result = gate.check()
    assert result.is_ready is False
    assert any("session_state" in m for m in result.missing)


# ─── PR3: LLM Multi-backend ───────────────────────────────────────────────────────


def test_pr3_mock_template_engine():
    from scripts.core.mock_template_engine import MockTemplateEngine, MockTask

    engine = MockTemplateEngine()
    result = engine.generate(task=MockTask.OUTLINE, topic="测试", venue="经济研究")
    assert "[MOCK" in result.content
    assert "经济研究" in result.content
    assert result.model == "mock_template"


def test_pr3_airouter_has_mock_fallback():
    from scripts.ai_router import AIRouter

    router = AIRouter(use_cache=False)
    router._lazy_init()
    assert hasattr(router, "_mock_fallback")
    assert router._mock_fallback is not None
    assert "mock_template" in router.status()


# ─── PR4: LaTeX Multi-backend ────────────────────────────────────────────────


def test_pr4_latex_auto_detect():
    import shutil
    from scripts.journal_template import JournalTemplate

    jt = JournalTemplate.__new__(JournalTemplate)
    backend = jt._detect_best_backend()
    assert backend in ("tectonic", "xelatex", "pdflatex", "lualatex", None)


def test_pr4_tectonic_compiles_minimal():
    from scripts.journal_template import JournalTemplate

    jt = JournalTemplate.__new__(JournalTemplate)
    tex = Path("/tmp/pr6_minimal.tex")
    tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Smoke test\n"
        "\\end{document}\n"
    )
    result = jt.compile(str(tex), engine="tectonic")
    assert result is True
    assert tex.with_suffix(".pdf").exists()


# ─── PR5: DID Audit Guard ────────────────────────────────────────────────────


def test_pr5_audit_blocks_synthetic_data():
    import pandas as pd
    from scripts.core.did_audit_guard import assert_real_data, MockDataError

    df = pd.DataFrame({
        "firm": ["A"],
        "year": [2020],
        "y": [1.0],
        "_synthetic": [True],
    })
    with pytest.raises(MockDataError):
        assert_real_data(df, "test")


def test_pr5_audit_allows_real_data():
    import pandas as pd
    from scripts.core.did_audit_guard import assert_real_data

    df = pd.DataFrame({
        "firm": ["A"],
        "year": [2020],
        "y": [1.0],
        "provenance_id": ["prov-001"],
    })
    result = assert_real_data(df, "test")
    assert result.is_real is True


# ─── PR6: Startup Check ──────────────────────────────────────────────────────


def test_pr6_startup_check_script_exists():
    from scripts import startup_check
    assert Path(__file__).parent.parent / "scripts" / "startup_check.py"
    # Should run without error
    items = startup_check.run_all_checks()
    assert len(items) >= 5


# ─── Integration: full flow ──────────────────────────────────────────────────────


def test_full_flow_nora_to_datagate():
    """端到端：NORA 完成 → 变量冗余 → DataGate 通过。"""
    import json
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 1. NORA 完成
        (tmp_path / "session_state.json").write_text(json.dumps({
            "topic": "数字金融对创新的影响",
            "current_stage": "venue",
            "answers": {},
            "is_complete": True,
        }))

        # 2. 变量冗余
        from scripts.core.variable_redundancy import VariableRedundancyResolver
        resolver = VariableRedundancyResolver(output_dir=tmp_path)
        report = resolver.resolve_by_topic("数字金融对创新的影响", identification="DID")
        assert report.has_minimum_redundancy is True

        # 3. DataGate
        from scripts.core.data_gate import DataGate, DataGateLevel
        gate = DataGate(session_dir=tmp_path, level=DataGateLevel.PROVENANCE)
        result = gate.check()
        assert result.is_ready is True
