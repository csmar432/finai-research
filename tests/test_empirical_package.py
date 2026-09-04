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
        "mechanism_channels": ["批发零售新注册", "居民服务新注册"],
        "mechanism_methods": ["jiangting", "sobel"],
        "mechanism_lock": ["信息化"],
        "mechanism_theory": "示范改变流通进入 → 批发零售新注册上升 → 县域贷款对数因此上升",
        "framework": "基于信息不对称下的金融中介框架，处理通过流通进入改变县域信贷",
        "policy_type": "mixed",
        "policy_type_basis": "商务部示范名单叠加财政专项资金到县",
        "figure_gate": {
            "event_post_n": 4,
            "event_post_cross0_n": 0,
            "placebo_true_outside_mass": True,
            "event0_job": "名单公布年，资金同步下达所以 0 点最高",
        },
        "story": {
            "question": "那么，电商示范名单能否提高县域贷款对数？",
            "tension": "示范既可能引入真实信贷需求，也可能只是把已有网点的业务换个统计口径。",
            "answer": "名单县的流通进入上升，并带动县域信贷相对扩张",
            "pitch": (
                "问题是示范名单有没有把信贷做厚。难处在于名单县本来条件更好，"
                "对照并不干净，也说不清扩张来自真实需求还是统计口径。我们用县年"
                "双重差分，先看贷款相对变化，再看流通进入这条独立于控制的渠道。"
                "发现名单县信贷相对扩张，说明示范不只是换统计口径，而是把可贷"
                "需求做厚了。这意味着县域信贷政策要把流通进入当作可核对的中间站，"
                "而不是只看年末贷款余额本身。"
            ),
            "beats": [
                {"section": "基准", "asks": "Y相对变了吗", "tables": [2], "answer": "相对扩张"},
                {"section": "识别", "asks": "是不是选择", "tables": [3], "answer": "站住了"},
                {"section": "机制", "asks": "流通进入动了吗", "tables": [4], "answer": "动了"},
                {"section": "异质", "asks": "哪里更强", "tables": [5], "answer": "中西部更强"},
            ],
            "story_numbers": ["主效应实物量级"],
        },
    }


def test_thinking_questions_are_reusable_not_a_menu():
    assert len(THINKING_QUESTIONS) >= 10
    assert any("观察点" in q for q in THINKING_QUESTIONS)
    assert any("贴纸" in q for q in THINKING_QUESTIONS)
    assert any("故事页" in q for q in THINKING_QUESTIONS)
    assert any("推断家族" in q for q in THINKING_QUESTIONS)


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


def test_same_family_methods_count_as_one():
    from scripts.core.empirical_package import method_families, validate_package

    pkg = _ok_core()
    pkg["mechanism_methods"] = ["sobel", "bootstrap"]
    assert method_families(pkg["mechanism_methods"]) == ["stepwise_indirect"]
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "mechanism_methods" in codes


def test_underscored_aliases_stay_in_the_same_family():
    from scripts.core.empirical_package import method_families

    assert method_families(["did_x_base_m", "moderation", "treat_x_baseline"]) == [
        "moderation"
    ]
    assert method_families(["jiangting", "two_step", "did_on_m"]) == ["twostep"]
    assert method_families(["m_in_y", "four_step"]) == ["stepwise_indirect"]


def test_duplicate_channels_do_not_count_as_two_paths():
    pkg = _ok_core()
    pkg["mechanism_channels"] = ["批发零售新注册", "批发零售新注册"]
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "mechanism_channels" in codes


def test_gold_mode_does_not_require_story_or_policy_type():
    from scripts.core.empirical_package import GOLD_SLOTS

    pkg = empty_package(mode="gold", unit="firm")
    pkg["y_construct"] = "绿色专利"
    pkg["x_construct"] = "碳交易"
    pkg["battery"] = ["规模", "杠杆", "成长"]
    pkg["variable_jobs"] = [
        {
            "name": name,
            "table_row": f"{name}水平",
            "construct": name,
            "job": f"挡绿色专利的事前{name}",
            "basis": f"接到本题绿色专利的事前{name}，不是年鉴有",
        }
        for name in pkg["battery"]
    ]
    pkg["slots"] = {name: f"T{i}" for i, name in enumerate(GOLD_SLOTS, 1)}
    pkg["main_col"] = "(1)"
    pkg["main_p"] = 0.01
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "story" not in codes
    assert "policy_type" not in codes
    assert "mechanism_channels" not in codes
    assert codes == set()


def test_mechanism_cannot_be_the_outcome():
    pkg = _ok_core()
    pkg["mechanism_channels"] = ["县域贷款对数", "批发零售新注册"]
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "mechanism_is_y" in codes


def test_core_needs_a_story_page():
    pkg = _ok_core()
    pkg["story"] = {}
    codes = {f.code for f in validate_package(pkg) if f.severity == "error"}
    assert "story" in codes


def test_h1_rejected_is_a_rewrite_not_a_finding():
    text = "结论：假说H1被拒绝，政策没有提高贷款。\n前站没有接上后站。"
    codes = {f.code for f in audit_manuscript(text, _ok_core())}
    assert "h1_rejected" in codes
    assert "work_language" in codes


def test_h1_possibility_and_published_words_are_not_workspace_voice():
    text = "我们讨论 H1被拒绝的可能性，并回顾文献中的名单效应。"
    codes = {f.code for f in audit_manuscript(text, _ok_core())}
    assert "h1_rejected" not in codes
    assert "work_language" not in codes


def test_manuscript_memo_voice_and_doi():
    text = (
        "摘要：本文不是估计 ATT，不应解释为因果。"
        "名单县的流通进入上升，并带动县域信贷相对扩张。\n"
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


def test_writing_pre_gate_searches_where_empirics_writes_the_package(tmp_path: Path):
    """Stage 6 → Stage 7 contract: the gate must look where empirics drops it."""
    from scripts.core.empirical_package import EmpiricalPackageReport
    from scripts.research_framework.enhanced_pipeline import EnhancedPipeline

    written = EnhancedPipeline(
        topic="ESG", output_dir=tmp_path / "run", enable_hitl=False
    )._write_empirical_package()
    assert written is not None, "empirics must emit a package after DID + robustness"

    cfg = AgentPipelineConfig(topic="t")
    pipeline = AgentPipeline(cfg)
    result = AgentPipelineResult(config=cfg, success=True)
    seen: dict = {}

    def _check(**kwargs):
        seen["dirs"] = [Path(p) for p in (kwargs.get("search_dirs") or [])]
        return EmpiricalPackageReport(passed=True, skipped=True, summary_message="skip")

    with patch(
        "scripts.core.empirical_package.check_empirical_package",
        side_effect=_check,
    ), patch(
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

    # enhanced_pipeline defaults to output/; the default gate must cover that dir.
    import inspect

    default_out = Path(
        str(inspect.signature(EnhancedPipeline.__init__).parameters["output_dir"].default)
    )
    assert written.name == "empirical_package.json"
    assert (default_out / written.name) in {
        d / written.name for d in seen.get("dirs", [])
    }
    assert result.quality_reports["writing_pre_gate"]["passed"] is True


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
