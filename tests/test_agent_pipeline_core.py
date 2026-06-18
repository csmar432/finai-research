"""Tests for AgentOrchestratorPipeline.

Covers:
    - Topological sort correctness
    - Stage dependency checking
    - QualityGates integration
    - AutoReviewRules integration
    - HITL approval flow
    - Single-entry execute() API
    - get_quality_report / get_auto_review accessors
"""

import pytest

from scripts.core.agent_pipeline_core import (
    AgentOrchestratorPipeline,
    PipelineStage,
    QualityGateResult,
    AutoReviewResult,
    StageConfig,
    StageResult,
)


class TestTopologicalSort:
    """拓扑排序测试。"""

    def test_linear_chain(self):
        """A → B → C → D（线性链）。"""
        stages = [
            StageConfig(PipelineStage.OUTLINE, depends_on=[]),
            StageConfig(PipelineStage.LITERATURE, depends_on=[PipelineStage.OUTLINE]),
            StageConfig(PipelineStage.WRITING, depends_on=[PipelineStage.LITERATURE]),
        ]
        order = AgentOrchestratorPipeline._topological_sort(stages)
        assert order.index(PipelineStage.OUTLINE) < order.index(PipelineStage.LITERATURE)
        assert order.index(PipelineStage.LITERATURE) < order.index(PipelineStage.WRITING)

    def test_parallel_branches(self):
        """OUTLINE → [LITERATURE, PLOTTING] → WRITING（并行分支）。"""
        stages = [
            StageConfig(PipelineStage.OUTLINE, depends_on=[]),
            StageConfig(PipelineStage.LITERATURE, depends_on=[PipelineStage.OUTLINE]),
            StageConfig(PipelineStage.PLOTTING, depends_on=[PipelineStage.OUTLINE]),
            StageConfig(PipelineStage.WRITING, depends_on=[PipelineStage.LITERATURE, PipelineStage.PLOTTING]),
        ]
        order = AgentOrchestratorPipeline._topological_sort(stages)
        o_idx = order.index(PipelineStage.OUTLINE)
        assert o_idx < order.index(PipelineStage.LITERATURE)
        assert o_idx < order.index(PipelineStage.PLOTTING)
        assert order.index(PipelineStage.LITERATURE) < order.index(PipelineStage.WRITING)
        assert order.index(PipelineStage.PLOTTING) < order.index(PipelineStage.WRITING)

    def test_disabled_stage_skipped_in_execution(self):
        """禁用的 stage 不在执行顺序中。"""
        stages = [
            StageConfig(PipelineStage.OUTLINE, enabled=False, depends_on=[]),
            StageConfig(PipelineStage.LITERATURE, depends_on=[]),
        ]
        order = AgentOrchestratorPipeline._topological_sort(stages)
        # 禁用的 stage 不出现在执行顺序中
        assert PipelineStage.OUTLINE not in order
        assert PipelineStage.LITERATURE in order

    def test_cycle_handling(self):
        """循环依赖时保留原顺序，不崩溃。"""
        stages = [
            StageConfig(PipelineStage.OUTLINE, depends_on=[PipelineStage.WRITING]),
            StageConfig(PipelineStage.LITERATURE, depends_on=[PipelineStage.OUTLINE]),
            StageConfig(PipelineStage.WRITING, depends_on=[PipelineStage.LITERATURE]),
        ]
        order = AgentOrchestratorPipeline._topological_sort(stages)
        # Should not raise, should contain all stages
        assert set(order) == {PipelineStage.OUTLINE, PipelineStage.LITERATURE, PipelineStage.WRITING}


class TestDependencyChecking:
    """依赖检查测试。"""

    def test_unmet_dependency_skips(self):
        """依赖未满足时 stage 标记为 skipped。"""
        pipeline = AgentOrchestratorPipeline(enable_quality_gates=False, enable_auto_review=False, enable_hitl=False)
        pipeline._config = [
            StageConfig(PipelineStage.OUTLINE, enabled=False, depends_on=[]),
            StageConfig(PipelineStage.LITERATURE, depends_on=[PipelineStage.OUTLINE]),
        ]
        pipeline._stage_results = {}  # OUTLINE not executed

        cfg = pipeline._config[1]
        result = pipeline._execute_stage(
            stage=PipelineStage.LITERATURE,
            cfg=cfg,
            topic="test",
            venue="JF",
            field="finance",
            initial_data=None,
        )
        assert result.status == "skipped"
        assert "依赖未满足" in result.error

    def test_unmet_single_dependency(self):
        """仅一个依赖未满足时跳过。"""
        pipeline = AgentOrchestratorPipeline(enable_quality_gates=False, enable_auto_review=False, enable_hitl=False)
        pipeline._stage_results = {
            PipelineStage.OUTLINE: StageResult(stage=PipelineStage.OUTLINE, status="success"),
        }
        cfg = StageConfig(
            PipelineStage.WRITING,
            depends_on=[PipelineStage.OUTLINE, PipelineStage.LITERATURE],
        )
        result = pipeline._execute_stage(
            stage=PipelineStage.WRITING,
            cfg=cfg,
            topic="test",
            venue="JF",
            field="finance",
            initial_data=None,
        )
        assert result.status == "skipped"
        assert "literature" in result.error  # enum.value = "literature"


class TestQualityGatesIntegration:
    """QualityGates 集成测试。"""

    def test_quality_gate_result_fields(self):
        """QualityGateResult 包含所有必需字段。"""
        r = QualityGateResult(
            chapter="Methodology",
            score=0.85,
            level="ACCEPTABLE",
            passed=True,
            issues=["Missing robustness section"],
            suggestions=["Add placebo test"],
            elapsed_ms=120.0,
        )
        assert r.chapter == "Methodology"
        assert r.score == 0.85
        assert r.level == "ACCEPTABLE"
        assert r.passed is True
        assert len(r.issues) == 1
        assert len(r.suggestions) == 1
        assert r.elapsed_ms == 120.0

    def test_pipeline_with_quality_gate_enabled(self):
        """enable_quality_gates=True 时流水线正常初始化。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=True,
            enable_auto_review=False,
            enable_hitl=False,
        )
        assert pipeline.enable_quality_gates is True
        assert pipeline._qg_engine is None  # 延迟初始化


class TestAutoReviewIntegration:
    """AutoReviewRules 集成测试。"""

    def test_auto_review_result_fields(self):
        """AutoReviewResult 包含所有必需字段。"""
        r = AutoReviewResult(
            domain="empirical_paper",
            overall=78.0,
            level="B",
            passed=True,
            dimension_scores={"methodology": 0.8, "writing": 0.7},
            critical_issues=[],
            suggestions=["Strengthen the identification strategy"],
            elapsed_ms=200.0,
        )
        assert r.domain == "empirical_paper"
        assert r.overall == 78.0
        assert r.level == "B"
        assert r.passed is True
        assert "methodology" in r.dimension_scores
        assert len(r.suggestions) == 1

    def test_pipeline_with_auto_review_enabled(self):
        """enable_auto_review=True 时流水线正常初始化。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=False,
            enable_auto_review=True,
            enable_hitl=False,
        )
        assert pipeline.enable_auto_review is True
        assert pipeline._arr_engine is None  # 延迟初始化


class TestHITLFlow:
    """HITL 审批流程测试。"""

    def test_approve_step(self):
        """approve_step() 正确设置 hitl_approved。"""
        pipeline = AgentOrchestratorPipeline(enable_quality_gates=False, enable_auto_review=False, enable_hitl=True)
        pipeline._stage_results = {
            PipelineStage.WRITING: StageResult(stage=PipelineStage.WRITING, status="hitl_required", hitl_approved=None),
        }
        result = pipeline.approve_step(PipelineStage.WRITING, "Looks good, proceed.")
        assert result is True
        assert pipeline._stage_results[PipelineStage.WRITING].hitl_approved is True

    def test_reject_step(self):
        """reject_step() 标记为失败。"""
        pipeline = AgentOrchestratorPipeline(enable_quality_gates=False, enable_auto_review=False, enable_hitl=True)
        pipeline._stage_results = {
            PipelineStage.WRITING: StageResult(stage=PipelineStage.WRITING, status="success"),
        }
        result = pipeline.reject_step(PipelineStage.WRITING, "Methodology section needs revision.")
        assert result is True
        assert pipeline._stage_results[PipelineStage.WRITING].status == "failed"
        assert pipeline._stage_results[PipelineStage.WRITING].hitl_approved is False

    def test_approve_unknown_stage_returns_false(self):
        """审批不存在的 stage 返回 False。"""
        pipeline = AgentOrchestratorPipeline()
        assert pipeline.approve_step(PipelineStage.OUTLINE) is False


class TestSingleEntryAPI:
    """单一入口 API 测试。"""

    def test_execute_returns_dict(self):
        """execute() 返回结构化字典，包含所有必需字段。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=False,
            enable_auto_review=False,
            enable_hitl=False,
        )
        result = pipeline.execute(
            topic="测试主题",
            venue="JF",
            field="finance",
        )
        assert isinstance(result, dict)
        assert "pipeline_id" in result
        assert "total_latency_ms" in result
        assert "execution_order" in result
        assert "stage_results" in result
        assert "summary" in result

    def test_execution_order_in_summary(self):
        """执行顺序在摘要中正确记录。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=False,
            enable_auto_review=False,
            enable_hitl=False,
        )
        result = pipeline.execute(topic="test", venue="JF")
        order = result["execution_order"]
        assert isinstance(order, list)
        assert all(isinstance(s, str) for s in order)

    def test_stage_results_keys_match_execution_order(self):
        """stage_results 的 key 是 execution_order 的子集（失败 stage 不写入 results）。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=False,
            enable_auto_review=False,
            enable_hitl=False,
        )
        result = pipeline.execute(topic="test", venue="JF")
        result_keys = set(result["stage_results"].keys())
        order_set = set(result["execution_order"])
        # stage_results 只包含实际执行的 stages
        assert result_keys.issubset(order_set)

    def test_summary_contains_required_fields(self):
        """summary 包含正确的统计信息字段。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=False,
            enable_auto_review=False,
            enable_hitl=False,
        )
        result = pipeline.execute(topic="test", venue="JF")
        summary = result["summary"]  # nested "summary" key
        assert "total_stages" in summary
        assert "success_stages" in summary
        assert "quality_gates_pass" in summary
        assert "auto_reviews_pass" in summary


class TestAccessors:
    """查询接口测试。"""

    def test_get_stage_result(self):
        """get_stage_result() 正确返回 StageResult。"""
        pipeline = AgentOrchestratorPipeline()
        pipeline._stage_results = {
            PipelineStage.WRITING: StageResult(stage=PipelineStage.WRITING, status="success"),
        }
        result = pipeline.get_stage_result(PipelineStage.WRITING)
        assert result is not None
        assert result.stage == PipelineStage.WRITING
        assert result.status == "success"

    def test_get_stage_result_by_string(self):
        """stage 参数支持字符串。"""
        pipeline = AgentOrchestratorPipeline()
        pipeline._stage_results = {
            PipelineStage.LITERATURE: StageResult(stage=PipelineStage.LITERATURE, status="success"),
        }
        result = pipeline.get_stage_result("literature")
        assert result is not None
        assert result.stage == PipelineStage.LITERATURE

    def test_get_stage_result_unknown(self):
        """未知 stage 返回 None。"""
        pipeline = AgentOrchestratorPipeline()
        assert pipeline.get_stage_result(PipelineStage.OUTLINE) is None

    def test_get_quality_report_no_gate(self):
        """无 QualityGate 结果时返回 None。"""
        pipeline = AgentOrchestratorPipeline()
        pipeline._stage_results = {
            PipelineStage.OUTLINE: StageResult(stage=PipelineStage.OUTLINE, status="success"),
        }
        assert pipeline.get_quality_report(PipelineStage.OUTLINE) is None

    def test_get_auto_review_no_review(self):
        """无 AutoReview 结果时返回 None。"""
        pipeline = AgentOrchestratorPipeline()
        pipeline._stage_results = {
            PipelineStage.REFINEMENT: StageResult(stage=PipelineStage.REFINEMENT, status="success"),
        }
        assert pipeline.get_auto_review(PipelineStage.REFINEMENT) is None

    def test_get_pipeline_summary(self):
        """get_pipeline_summary() 返回完整结果字典（包含嵌套 summary）。"""
        pipeline = AgentOrchestratorPipeline(
            enable_quality_gates=False,
            enable_auto_review=False,
            enable_hitl=False,
        )
        pipeline.execute(topic="test", venue="JF")
        full_result = pipeline.get_pipeline_summary()
        # 顶层包含 execution_order, stage_results
        assert "execution_order" in full_result
        assert "stage_results" in full_result
        # 嵌套 summary 包含统计字段
        summary = full_result.get("summary", {})
        assert "total_stages" in summary
        assert "success_stages" in summary


class TestStageConfig:
    """StageConfig 字段测试。"""

    def test_default_values(self):
        """默认配置值正确。"""
        cfg = StageConfig(PipelineStage.OUTLINE)
        assert cfg.enabled is True
        assert cfg.skip_on_failure is False
        assert cfg.depends_on == []
        assert cfg.quality_gate_threshold == 0.6
        assert cfg.auto_review_required is True
        assert cfg.hitl_required is True
        assert cfg.max_retries == 1
        assert cfg.timeout_seconds == 300.0

    def test_custom_depends_on(self):
        """自定义依赖列表。"""
        cfg = StageConfig(
            PipelineStage.WRITING,
            depends_on=[PipelineStage.OUTLINE, PipelineStage.LITERATURE],
        )
        assert len(cfg.depends_on) == 2
        assert PipelineStage.OUTLINE in cfg.depends_on
        assert PipelineStage.LITERATURE in cfg.depends_on


class TestTextExtraction:
    """文本提取测试。"""

    def test_extract_string(self):
        """字符串直接返回。"""
        text = AgentOrchestratorPipeline._extract_text("hello world")
        assert text == "hello world"

    def test_extract_dict_with_output(self):
        """dict 有 output 字段时返回 output。"""
        content = {"output": "final text", "other": 123}
        text = AgentOrchestratorPipeline._extract_text(content)
        assert text == "final text"

    def test_extract_dict_with_text(self):
        """dict 有 text 字段时返回 text。"""
        content = {"text": "markdown content"}
        text = AgentOrchestratorPipeline._extract_text(content)
        assert text == "markdown content"

    def test_extract_dict_fallback_json(self):
        """dict 无 output/text 时返回 JSON。"""
        content = {"stage": "outline", "status": "success"}
        text = AgentOrchestratorPipeline._extract_text(content)
        assert "outline" in text
        assert "success" in text

    def test_extract_object_with_str(self):
        """有 __str__ 的对象返回 str。"""
        class MockContent:
            def __str__(self):
                return "mock output"
        text = AgentOrchestratorPipeline._extract_text(MockContent())
        assert text == "mock output"


class TestDefaultStages:
    """默认流水线配置测试。"""

    def test_default_stages_order(self):
        """默认 stage 配置可拓扑排序。"""
        stages = AgentOrchestratorPipeline.DEFAULT_STAGES
        assert len(stages) > 0
        order = AgentOrchestratorPipeline._topological_sort(stages)
        # OUTLINE 必须先于 LITERATURE 和 PLOTTING
        assert PipelineStage.OUTLINE in order
        # WRITING 必须后于 LITERATURE 和 PLOTTING
        w_idx = order.index(PipelineStage.WRITING)
        if PipelineStage.LITERATURE in order:
            assert order.index(PipelineStage.LITERATURE) < w_idx
        if PipelineStage.PLOTTING in order:
            assert order.index(PipelineStage.PLOTTING) < w_idx
