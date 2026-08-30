"""Write-gate + empirical package contract (portable, not paper-specific)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from scripts.core.empirical_package import (
    THINKING_QUESTIONS,
    audit_manuscript,
    check_empirical_package,
    empty_package,
    package_from_pipeline_ctx,
    validate_package,
    write_gate,
)
from scripts.data_source_checker import DataSourceGateReport
from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig, AgentPipelineResult


def _ok_core() -> dict:
    return {
        "mode": "core",
        "unit": "county",
        "y_construct": "县域贷款对数",
        "x_construct": "电商示范名单",
        "battery": ["产业", "财政", "信息化"],
        "variable_jobs": [
            {
                "name": "产业",
                "table_row": "第三产业比重",
                "construct": "产业结构",
                "job": "挡县域贷款对数的事前产业结构",
                "basis": "申报材料要求填写产业结构，接到本题县域贷款对数",
            },
            {
                "name": "财政",
                "table_row": "财政支出",
                "construct": "财政",
                "job": "挡名单选择中的财政能力",
                "basis": "申报看财政支出份额，接到本题县域贷款对数",
            },
            {
                "name": "信息化",
                "table_row": "信息化程度",
                "construct": "信息成本",
                "job": "挡本题县域贷款展业的信息成本",
                "basis": "电话普及接到本题县域贷款对数的信息成本，不是年鉴有",
            },
        ],
        "slots": {
            "desc": "T1",
            "facts_before_reg": "T2",
            "baseline_stepwise": "T3",
            "tighter_compare": "T4",
            "robust_matrix": "T5",
            "mechanism": "T6",
            "sample_flow": "A1",
            "parallel_trends": "fig1",
            "placebo": "fig2",
            "exclusive": "T7",
            "psm": "T8",
            "hetero": "T9",
        },
        "main_col": "(4)",
        "main_p": 0.01,
        "mechanism_channels": ["批发零售新注册"],
        "mechanism_methods": ["jiangting", "sobel"],
        "mechanism_lock": ["信息化"],
        "mechanism_theory": "示范改变流通进入 → 批发零售新注册上升 → 县域贷款对数因此上升",
        "figure_gate": {
            "event_post_n": 4,
            "event_post_cross0_n": 0,
            "placebo_true_outside_mass": True,
            "event0_job": "名单公布年，资金同步下达所以 0 点最高",
        },
    }


def test_thinking_questions_are_reusable_not_a_menu():
    assert len(THINKING_QUESTIONS) == 10
    assert any("观察点" in q for q in THINKING_QUESTIONS)
    assert any("贴纸" in q for q in THINKING_QUESTIONS)


def test_ok_core_package_passes_write_gate():
    findings = write_gate(_ok_core())
    assert [f for f in findings if f.severity == "error"] == []


def test_old_scores_wrapper_style_overlap_fails():
    pkg = _ok_core()
    pkg["mechanism_channels"] = ["信息化"]
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "mechanism_overlap" in codes


def test_sticker_basis_and_code_table_row_fail():
    pkg = _ok_core()
    pkg["variable_jobs"][0]["basis"] = "借鉴唐跃桓"
    pkg["variable_jobs"][0]["table_row"] = "Phone"
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "basis" in codes
    assert "table_row" in codes


def test_core_cannot_drop_mechanism():
    pkg = _ok_core()
    pkg["slots"]["mechanism"] = ""
    pkg["dropped"] = [{"slot": "mechanism", "reason": "无户级微观"}]
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "mechanism_required" in codes


def test_insignificant_main_cannot_be_a_finding():
    pkg = _ok_core()
    pkg["main_p"] = 0.42
    codes = {f.code for f in write_gate(pkg) if f.severity == "error"}
    assert "main_insignificant" in codes


def test_dirty_event_study_blocks_even_if_twfe_is_starred():
    pkg = _ok_core()
    pkg["figure_gate"]["event_post_cross0_n"] = 3
    pkg["figure_gate"]["placebo_true_outside_mass"] = False
    codes = {f.code for f in write_gate(pkg) if f.severity == "error"}
    assert "figure_gate" in codes
    assert "placebo_figure" in codes


def test_manuscript_memo_voice_and_doi():
    text = (
        "摘要：本文不是估计 ATT，不应解释为因果。\n"
        "研究发现平行趋势、安慰剂后依然成立。\n"
        "H1：平行趋势成立。\n"
        "参考文献\n"
        "张三, 2024, 经济研究, doi:10.1111/example\n"
    )
    pkg = _ok_core()
    pkg["figure_gate"]["event_post_cross0_n"] = 2
    codes = {f.code for f in audit_manuscript(text, pkg)}
    assert "memo_voice" in codes
    assert "bib_doi" in codes
    assert "hypothesis_diagnostic" in codes
    assert "still_holds" in codes


def test_check_skips_without_package(tmp_path: Path):
    report = check_empirical_package(search_dirs=[tmp_path])
    assert report.passed is True
    assert report.skipped is True


def test_check_blocks_incomplete_package_file(tmp_path: Path):
    path = tmp_path / "empirical_package.json"
    path.write_text(
        '{"mode":"core","unit":"firm","battery":[],"slots":{},"main_col":""}',
        encoding="utf-8",
    )
    report = check_empirical_package(search_dirs=[tmp_path], manuscript="研究发现显著促进。")
    assert report.passed is False
    assert report.skipped is False


def test_pipeline_scaffold_is_honest_about_missing_mechanism():
    @dataclass
    class _Ctx:
        topic: str = "绿色专利与融资约束"
        modern_did_results: dict = None
        robustness_report: list = None
        parallel_trends_method: str = "event_study"

        def __post_init__(self):
            self.modern_did_results = {"did_2x2": {"coef": 0.05, "pval": 0.02}}
            self.robustness_report = ["a"]

    pkg = package_from_pipeline_ctx(_Ctx())
    codes = {f.code for f in write_gate(pkg) if f.severity == "error"}
    assert "mechanism_required" in codes
    assert pkg["main_p"] == 0.02


def test_empty_scaffold_cli_shape():
    pkg = empty_package(mode="gold", unit="city")
    assert pkg["mode"] == "gold"
    assert "baseline_stepwise" in pkg["slots"]
    assert "placebo" not in pkg["slots"]


def test_writing_pre_gate_blocks_when_package_fails(tmp_path: Path):
    (tmp_path / "empirical_package.json").write_text(
        '{"mode":"core","unit":"firm","y_construct":"Y","x_construct":"X",'
        '"battery":["a","b","c"],"slots":{},"main_col":"1","main_p":0.8}',
        encoding="utf-8",
    )
    cfg = AgentPipelineConfig(topic="t", output_dir=str(tmp_path))
    pipeline = AgentPipeline(cfg)
    result = AgentPipelineResult(config=cfg, success=True)
    with patch(
        "scripts.research_framework.manuscript_quality_gate.check_manuscript",
        return_value=DataSourceGateReport(passed=True, summary_message="mq"),
    ), patch(
        "scripts.research_framework.reference_validator.validate_references",
        return_value=DataSourceGateReport(passed=True, summary_message="ref"),
    ), patch(
        "scripts.data_source_checker.check_data_sources",
        return_value=DataSourceGateReport(passed=True, summary_message="ds"),
    ):
        pipeline._run_writing_pre_gate(result, "理论综述，无回归结果。")

    ep = result.quality_reports["writing_pre_gate/empirical_package"]
    assert ep["passed"] is False
    assert result.quality_reports["writing_pre_gate"]["passed"] is False
