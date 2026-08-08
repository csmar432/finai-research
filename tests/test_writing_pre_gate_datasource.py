"""Writing pre-gate must use scripts.data_source_checker and fail-closed on errors."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig, AgentPipelineResult
from scripts.data_source_checker import DataSourceGateReport, check_data_sources


def test_check_data_sources_no_claims_passes():
    report = check_data_sources("这是一篇纯理论讨论文章，不涉及任何微观数据。")
    assert report.passed is True
    assert "跳过" in report.summary_message or report.details.get("inferred") == 0


def test_check_data_sources_infers_a_share_and_reports():
    with patch("scripts.data_source_checker.DataSourceChecker") as MockChecker:
        inst = MockChecker.return_value
        result = MagicMock()
        result.requires_synthetic_data = True
        result.summary_message = "no sources"
        result.available_sources = []
        result.unavailable_sources = ["tushare"]
        inst.run.return_value = result

        report = check_data_sources("本文使用A股上市公司财务数据与 Tushare 接口。")

    assert report.passed is False
    assert report.details["requires_synthetic_data"] is True
    MockChecker.assert_called_once()


def test_as_gate_report_handles_dataclass_and_block_flag():
    @dataclass
    class _R:
        passed: bool
        summary_message: str

    d = AgentPipeline._as_gate_report(_R(passed=True, summary_message="ok"))
    assert d["passed"] is True

    @dataclass
    class _N:
        should_block_writing: bool
        summary_message: str

    d2 = AgentPipeline._as_gate_report(_N(should_block_writing=True, summary_message="block"))
    assert d2["passed"] is False


def test_writing_pre_gate_fail_closed_on_import_error():
    cfg = AgentPipelineConfig(topic="t")
    pipeline = AgentPipeline(cfg)
    # Avoid full init — call method with a minimal result object.
    result = AgentPipelineResult(config=cfg, success=True)

    with patch(
        "scripts.data_source_checker.check_data_sources",
        side_effect=RuntimeError("boom"),
    ), patch(
        "scripts.research_framework.manuscript_quality_gate.check_manuscript",
        return_value=DataSourceGateReport(passed=True, summary_message="mq ok"),
    ), patch(
        "scripts.research_framework.reference_validator.validate_references",
        return_value=DataSourceGateReport(passed=True, summary_message="ref ok"),
    ), patch(
        "scripts.research_framework.negative_result_handler.assess_result",
        return_value=DataSourceGateReport(passed=True, summary_message="nr"),
    ):
        pipeline._run_writing_pre_gate(result, "A股财务数据实证草稿")

    ds = result.quality_reports.get("writing_pre_gate/data_source_checker", {})
    assert ds.get("passed") is False
    assert "boom" in ds.get("summary_message", "")
    assert any("data_source_checker" in e for e in result.errors)


def test_writing_pre_gate_uses_correct_import_path():
    """Regression: must import scripts.data_source_checker, not research_framework.*."""
    cfg = AgentPipelineConfig(topic="t")
    pipeline = AgentPipeline(cfg)
    result = AgentPipelineResult(config=cfg, success=True)
    called = {}

    def _fake_check(writing_text, design_text=None):
        called["ok"] = True
        return DataSourceGateReport(passed=True, summary_message="ok", details={})

    with patch(
        "scripts.research_framework.manuscript_quality_gate.check_manuscript",
        return_value=DataSourceGateReport(passed=True, summary_message="mq"),
    ), patch(
        "scripts.research_framework.reference_validator.validate_references",
        return_value=DataSourceGateReport(passed=True, summary_message="ref"),
    ), patch(
        "scripts.data_source_checker.check_data_sources",
        side_effect=_fake_check,
    ), patch(
        "scripts.research_framework.negative_result_handler.assess_result",
        return_value=DataSourceGateReport(passed=True, summary_message="nr"),
    ):
        pipeline._run_writing_pre_gate(result, "理论综述，无面板回归。")

    assert called.get("ok") is True
    assert result.quality_reports["writing_pre_gate"]["passed"] is True