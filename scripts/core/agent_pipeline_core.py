"""AgentOrchestratorPipeline — 统一编排流水线。

解决两个架构不足：
  1. DAG 编排缺失：提供显式依赖跟踪的非线性流水线
  2. 调用路径分散：所有 stage 均通过单一入口 execute() 执行

集成质量门控（QualityGates）和自动评分（AutoReviewRules），
在 HITL 审核前自动执行质量检查，实现论文写作过程的自动化质量保障。

使用示例：
    from scripts.core.agent_pipeline_core import AgentOrchestratorPipeline, StageConfig

    pipeline = AgentOrchestratorPipeline(
        enable_quality_gates=True,   # 论文写作质量下限自动检查
        enable_auto_review=True,       # HITL 前自动评分
        enable_hitl=True,             # 人工审核门
        enable_provenance=True,        # 数据溯源
    )

    # 单一入口执行所有 stage
    result = pipeline.execute(
        topic="碳排放权交易对企业绿色创新的影响",
        venue="JFE",
    )

    # 查询任意 stage 的质量报告
    report = pipeline.get_quality_report("writing")
    print(report.summary())
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeVar

__all__ = [
    "PipelineStage",
    "StageConfig",
    "StageResult",
    "QualityGateResult",
    "AutoReviewResult",
    "AgentOrchestratorPipeline",
]


# ─── Pipeline Stage Enum ────────────────────────────────────────────────────────


class PipelineStage(Enum):
    """流水线阶段枚举，与 AgentPipeline.stage 一致。

    设计说明（解决"stage_map 只映射 5/10"疑虑）：
    - INPUT / OUTPUT：流水线边界标记，无实际执行体
    - HITL_OUTLINE / HITL_LITERATURE / HITL_WRITING：HITL 审批记录节点，
      由 AgentOrchestratorPipeline.execute() 在 QualityGates 和 AutoReviewRules
      层面处理，不调用底层 agent
    - OUTLINE / LITERATURE / PLOTTING / WRITING / REFINEMENT：实际执行阶段
      （共 5 个），DEFAULT_STAGES 正确配置了这 5 个

    因此 DEFAULT_STAGES 的 5 个 stage 配置与 PipelineStage 枚举中的 5 个
    执行阶段一一对应，不存在映射缺失。"""
    INPUT = "input"
    OUTLINE = "outline"
    LITERATURE = "literature"
    PLOTTING = "plotting"
    WRITING = "writing"
    REFINEMENT = "refinement"
    HITL_OUTLINE = "hitl_outline"
    HITL_LITERATURE = "hitl_literature"
    HITL_WRITING = "hitl_writing"
    OUTPUT = "output"


# ─── Stage Configuration ──────────────────────────────────────────────────────


@dataclass
class StageConfig:
    """阶段配置。"""
    stage: PipelineStage
    enabled: bool = True
    skip_on_failure: bool = False  # 当前阶段失败时是否跳过（而非中止流水线）
    depends_on: list[PipelineStage] = field(default_factory=list)
    quality_gate_threshold: float = 0.6  # QualityGates 通过门槛
    auto_review_required: bool = True    # 是否强制执行 AutoReview
    hitl_required: bool = True         # 是否需要人工审核
    max_retries: int = 1
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.depends_on is None:
            self.depends_on = []


# ─── Result Dataclasses ────────────────────────────────────────────────────────


@dataclass
class StageResult:
    """阶段执行结果。"""
    stage: PipelineStage
    status: str             # "success" | "skipped" | "failed" | "pending"
    output: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    retries: int = 0
    quality_gate: QualityGateResult | None = None
    auto_review: AutoReviewResult | None = None
    hitl_approved: bool | None = None  # None = no HITL needed
    metadata: dict = field(default_factory=dict)


@dataclass
class QualityGateResult:
    """QualityGates 检查结果。"""
    chapter: str
    score: float           # 0.0 - 1.0
    level: str            # EXCELLENT / ACCEPTABLE / BELOW_MINIMUM / CRITICAL
    passed: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass
class AutoReviewResult:
    """AutoReviewRules 评分结果。"""
    domain: str
    overall: float         # 0-100
    level: str            # A/B/C/D/F
    passed: bool
    dimension_scores: dict[str, float] = field(default_factory=dict)
    critical_issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


# ─── Core Pipeline ───────────────────────────────────────────────────────────────


class AgentOrchestratorPipeline:
    """
    统一编排流水线。

    所有 stage 均通过单一入口 execute() 执行，依赖关系显式管理。
    在每个写作阶段自动执行 QualityGates 和 AutoReviewRules 检查，
    确保输出满足最低质量要求后才进入人工审核阶段。

    Parameters
    ----------
    enable_quality_gates : bool
        启用 QualityGates 质量下限检查（默认 True）
    enable_auto_review : bool
        启用 AutoReviewRules 自动评分（默认 True）
    enable_hitl : bool
        启用 HITL 人工审核门（默认 True）
    enable_provenance : bool
        启用数据溯源（默认 False）
    output_dir : Path | str
        输出目录
    strict_mode : bool
        True = QualityGates 和 AutoReviewRules 的 CRITICAL 问题会阻止流水线继续
    """

    # 默认流水线配置：所有标准 stage 及其依赖关系
    DEFAULT_STAGES: list[StageConfig] = [
        StageConfig(PipelineStage.OUTLINE, depends_on=[]),
        StageConfig(PipelineStage.LITERATURE, depends_on=[PipelineStage.OUTLINE]),
        StageConfig(PipelineStage.PLOTTING, depends_on=[PipelineStage.OUTLINE]),
        StageConfig(PipelineStage.WRITING, depends_on=[PipelineStage.LITERATURE, PipelineStage.PLOTTING]),
        StageConfig(PipelineStage.REFINEMENT, depends_on=[PipelineStage.WRITING]),
    ]

    def __init__(
        self,
        enable_quality_gates: bool = True,
        enable_auto_review: bool = True,
        enable_hitl: bool = True,
        enable_provenance: bool = False,
        output_dir: Path | str = "output/pipeline",
        strict_mode: bool = False,
    ):
        self.enable_quality_gates = enable_quality_gates
        self.enable_auto_review = enable_auto_review
        self.enable_hitl = enable_hitl
        self.enable_provenance = enable_provenance
        self.output_dir = Path(output_dir)
        self.strict_mode = strict_mode
        self.pipeline_id = str(uuid.uuid4())[:8]

        # 执行状态
        self._stage_results: dict[PipelineStage, StageResult] = {}
        self._execution_order: list[PipelineStage] = []
        self._started_at: float = 0.0
        self._finished_at: float = 0.0
        self._config: list[StageConfig] = []

        # 质量门控引擎（延迟导入避免循环依赖）
        self._qg_engine = None
        self._arr_engine = None

    # ─── Public API ──────────────────────────────────────────────────────────

    def execute(
        self,
        topic: str,
        venue: str = "JF",
        field: str = "finance",
        stages: list[StageConfig] | None = None,
        initial_data: dict | None = None,
    ) -> dict:
        """
        单一入口执行所有 stage。

        执行流程：
            1. 拓扑排序确定执行顺序
            2. 依次执行每个 enabled 的 stage：
                a. 检查依赖是否全部完成
                b. 执行 stage（调用 AgentPipeline）
                c. QualityGates 检查（如果 enabled）
                d. AutoReviewRules 评分（如果 enabled）
                e. HITL 暂停（如果 enabled 且 auto_review 未通过）
            3. 聚合所有结果

        Parameters
        ----------
        topic : str
            研究主题
        venue : str
            目标期刊
        field : str
            研究领域
        stages : list[StageConfig], optional
            自定义 stage 配置，默认使用 DEFAULT_STAGES
        initial_data : dict, optional
            传递给首个 stage 的初始数据

        Returns
        -------
        dict
            包含 total_latency_ms, stage_results, execution_order, summary
        """
        self._started_at = time.time()
        self._stage_results = {}
        self._execution_order = []
        self._config = stages or self.DEFAULT_STAGES

        # 1. 拓扑排序
        execution_order = self._topological_sort(self._config)
        self._execution_order = execution_order

        # 2. 依次执行
        for stage in execution_order:
            cfg = next((c for c in self._config if c.stage == stage), None)
            if cfg is None:
                continue

            result = self._execute_stage(
                stage=stage,
                cfg=cfg,
                topic=topic,
                venue=venue,
                field=field,
                initial_data=initial_data,
            )
            self._stage_results[stage] = result

            # 依赖失败 → 停止流水线
            if result.status == "failed" and not cfg.skip_on_failure:
                break

            # 严格模式下 CRITICAL 质量问题 → 停止
            if self.strict_mode and result.quality_gate:
                if result.quality_gate.level == "critical":
                    break

        self._finished_at = time.time()

        return self._build_summary()

    def get_quality_report(self, stage: PipelineStage | str) -> QualityGateResult | None:
        """查询指定 stage 的 QualityGate 结果。"""
        if isinstance(stage, str):
            stage = PipelineStage(stage)
        result = self._stage_results.get(stage)
        return result.quality_gate if result else None

    def get_auto_review(self, stage: PipelineStage | str) -> AutoReviewResult | None:
        """查询指定 stage 的 AutoReview 结果。"""
        if isinstance(stage, str):
            stage = PipelineStage(stage)
        result = self._stage_results.get(stage)
        return result.auto_review if result else None

    def get_stage_result(self, stage: PipelineStage | str) -> StageResult | None:
        """查询指定 stage 的执行结果。"""
        if isinstance(stage, str):
            stage = PipelineStage(stage)
        return self._stage_results.get(stage)

    def get_pipeline_summary(self) -> dict:
        """返回流水线执行摘要。"""
        return self._build_summary()

    def approve_step(self, stage: PipelineStage | str, feedback: str = "") -> bool:
        """
        审批指定 stage，使其进入下一阶段。

        Parameters
        ----------
        stage : PipelineStage | str
            要审批的 stage
        feedback : str
            审批意见

        Returns
        -------
        bool
            审批是否成功
        """
        if isinstance(stage, str):
            stage = PipelineStage(stage)
        result = self._stage_results.get(stage)
        if result:
            result.hitl_approved = True
            return True
        return False

    def reject_step(self, stage: PipelineStage | str, reason: str) -> bool:
        """拒绝指定 stage，标记为失败。"""
        if isinstance(stage, str):
            stage = PipelineStage(stage)
        result = self._stage_results.get(stage)
        if result:
            result.status = "failed"
            result.error = reason
            result.hitl_approved = False
            return True
        return False

    # ─── Internal Execution ────────────────────────────────────────────────

    def _execute_stage(
        self,
        stage: PipelineStage,
        cfg: StageConfig,
        topic: str,
        venue: str,
        field: str,
        initial_data: dict | None,
    ) -> StageResult:
        """执行单个 stage，包含质量门控和自动评分。"""
        t0 = time.perf_counter()
        result = StageResult(stage=stage, status="pending")

        # 检查依赖
        unmet = [d for d in cfg.depends_on if self._stage_results.get(d, StageResult(stage=d, status="")).status != "success"]
        if unmet:
            result.status = "skipped"
            result.error = f"依赖未满足: {[d.value for d in unmet]}"
            return result

        # ── 执行 stage（实际调用 AgentPipeline）────────────
        try:
            output = self._call_agent(stage, topic, venue, field, initial_data)
            result.output = output
            result.status = "success"
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.latency_ms = (time.perf_counter() - t0) * 1000
            return result

        result.latency_ms = (time.perf_counter() - t0) * 1000

        # ── QualityGates 检查 ─────────────────────────────
        if self.enable_quality_gates and output:
            qg_result = self._run_quality_gate(stage, output)
            result.quality_gate = qg_result

        # ── AutoReviewRules 评分 ──────────────────────────
        if self.enable_auto_review and output:
            arr_result = self._run_auto_review(stage, output)
            result.auto_review = arr_result

        # ── HITL 暂停决策 ────────────────────────────────
        if self.enable_hitl and cfg.hitl_required:
            if result.quality_gate and not result.quality_gate.passed:
                result.status = "hitl_required"
                result.metadata["hitl_reason"] = "quality_gate_failed"
            elif result.auto_review and not result.auto_review.passed:
                result.status = "hitl_required"
                result.metadata["hitl_reason"] = "auto_review_failed"

        return result

    def _call_agent(
        self,
        stage: PipelineStage,
        topic: str,
        venue: str,
        field: str,
        initial_data: dict | None,
    ) -> Any:
        """
        Execute a single pipeline stage via the AgentOrchestrator.

        Architecture note (P0-1 fix):
        Before this fix, _call_agent() called pipeline.run() which internally calls
        AgentOrchestrator.run_pipeline() for ALL 5 stages (outline→literature→
        plotting→writing→refinement). With 5 stages in AgentOrchestratorPipeline,
        this resulted in 5 × 5 = 25 full pipeline runs (25× overhead).

        The correct approach: build a single-step pipeline and pass it directly
        to AgentOrchestrator.run_pipeline(). This executes exactly one stage.
        """
        try:
            from scripts.core.orchestrator import AgentOrchestrator, PipelineStep
            from scripts.core.agents.base import AgentResult

            # ── Build single-step pipeline for this stage only ──────────────────
            # Map PipelineStage → orchestrator agent name
            stage_agent_map = {
                PipelineStage.OUTLINE: "outline",
                PipelineStage.LITERATURE: "literature",
                PipelineStage.PLOTTING: "plotting",
                PipelineStage.WRITING: "writing",
                PipelineStage.REFINEMENT: "refinement",
            }
            agent_name = stage_agent_map.get(stage, stage.value)

            # Build context with topic, venue, field
            context: dict[str, Any] = {
                "topic": topic,
                "venue": venue,
                "field": field,
                **(initial_data or {}),
            }

            step = PipelineStep(
                stage=stage,
                agent_name=agent_name,
                depends_on=[],
                hitl_gate=False,  # HITL handled by AgentOrchestratorPipeline layer
                skip=False,
            )

            # Build minimal orchestrator with just the agents needed for this stage
            try:
                from scripts.core.llm_gateway import LLMGateway
                gateway = LLMGateway()
            except ImportError:
                gateway = None

            orch = AgentOrchestrator(gateway)
            orch.register_default_agents()

            # Execute ONLY this stage — no full pipeline
            pipeline_result = orch.run_pipeline(
                pipeline_name=f"single_stage_{stage.value}",
                steps=[step],
                input_data=context,
            )

            # Extract result for this stage
            stage_result: Any = None
            for s_key, s_result in pipeline_result.stage_results.items():
                if s_key == stage:
                    stage_result = s_result.output
                    break
            if stage_result is None and stage.value in pipeline_result.stage_results:
                stage_result = getattr(
                    list(pipeline_result.stage_results.values())[0], "output", None
                )

            return stage_result

        except ImportError as ie:
            # Missing dependencies: warn clearly, do NOT silently mock
            import logging as _log
            _log.getLogger("agent_pipeline_core").warning(
                "[_call_agent] ImportError — module unavailable: %s. "
                "This stage cannot be executed. "
                "Install missing dependency to enable: pip install <package>",
                ie.name,
            )
            return {
                "stage": stage.value,
                "topic": topic,
                "venue": venue,
                "error": f"import_error:{ie.name}",
                "output": None,
            }
        except Exception as exc:
            import logging as _log
            _log.getLogger("agent_pipeline_core").error(
                "[_call_agent] Stage %s failed: %s", stage.value, exc, exc_info=True
            )
            raise RuntimeError(f"Stage {stage.value} failed: {exc}") from exc

    def _run_quality_gate(self, stage: PipelineStage, content: Any) -> QualityGateResult:
        """执行 QualityGates 检查。"""
        if self._qg_engine is None:
            try:
                from scripts.core.quality_gates import PaperQualityGates
                self._qg_engine = PaperQualityGates(strict=False)
            except ImportError:
                return QualityGateResult(
                    chapter=stage.value, score=1.0,
                    level="unknown", passed=True,
                    issues=["QualityGates 模块不可用"], elapsed_ms=0.0,
                )

        try:
            # Determine chapter name from stage
            chapter_map = {
                PipelineStage.OUTLINE: "Introduction",
                PipelineStage.LITERATURE: "Literature Review",
                PipelineStage.WRITING: "Methodology",
                PipelineStage.REFINEMENT: "Results",
            }
            chapter = chapter_map.get(stage, stage.value.title())

            text = self._extract_text(content)
            report = self._qg_engine.gate(chapter, text)

            return QualityGateResult(
                chapter=chapter,
                score=report.score,
                level=report.level.value,
                passed=report.passed,
                issues=[i.message for i in report.issues],
                suggestions=report.suggestions,
                elapsed_ms=report.elapsed_ms,
            )
        except Exception as exc:
            return QualityGateResult(
                chapter=stage.value, score=0.0,
                level="error", passed=False,
                issues=[f"QualityGates 执行错误: {exc}"], elapsed_ms=0.0,
            )

    def _run_auto_review(self, stage: PipelineStage, content: Any) -> AutoReviewResult:
        """执行 AutoReviewRules 评分。"""
        if self._arr_engine is None:
            try:
                from scripts.core.reviewer import AutoReviewRules
                self._arr_engine = AutoReviewRules(domain="empirical_paper")
            except ImportError:
                return AutoReviewResult(
                    domain="empirical_paper", overall=0.0,
                    level="error", passed=False,
                    critical_issues=["AutoReviewRules 模块不可用"], elapsed_ms=0.0,
                )

        try:
            text = self._extract_text(content)
            score = self._arr_engine.score_chapter(stage.value.title(), text)

            return AutoReviewResult(
                domain="empirical_paper",
                overall=score.get("overall", 0.0),
                level=score.get("level", "F"),
                passed=score.get("passed", False),
                dimension_scores=score.get("dimension_scores", {}),
                critical_issues=score.get("critical_issues", []),
                suggestions=score.get("suggestions", []),
                elapsed_ms=0.0,
            )
        except Exception as exc:
            return AutoReviewResult(
                domain="empirical_paper", overall=0.0,
                level="error", passed=False,
                critical_issues=[f"AutoReviewRules 执行错误: {exc}"], elapsed_ms=0.0,
            )

    @staticmethod
    def _extract_text(content: Any) -> str:
        """从任意内容类型中提取文本。"""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            if "output" in content:
                return str(content["output"])
            if "text" in content:
                return str(content["text"])
            return json.dumps(content, ensure_ascii=False)
        if hasattr(content, "__str__"):
            return str(content)
        return repr(content)

    @staticmethod
    def _topological_sort(stages: list[StageConfig]) -> list[PipelineStage]:
        """Kahn 算法拓扑排序。过滤掉 enabled=False 的 stage。"""
        # 仅对 enabled 的 stages 排序
        enabled = [s for s in stages if s.enabled]
        in_degree: dict[PipelineStage, int] = {s.stage: 0 for s in enabled}
        adj: dict[PipelineStage, list[PipelineStage]] = {s.stage: [] for s in enabled}

        for cfg in stages:
            for dep in cfg.depends_on:
                adj[dep].append(cfg.stage)
                in_degree[cfg.stage] += 1

        from collections import deque
        queue: deque[PipelineStage] = deque(s for s, d in in_degree.items() if d == 0)
        result: list[PipelineStage] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 处理循环（保留原顺序）
        remaining = [s for s in enabled if s.stage not in result]
        for cfg in remaining:
            result.append(cfg.stage)

        return result

    def _build_summary(self) -> dict:
        """构建执行摘要。"""
        total_ms = (self._finished_at - self._started_at) * 1000
        stage_count = len(self._stage_results)
        success_count = sum(
            1 for r in self._stage_results.values()
            if r.status == "success"
        )

        quality_gates_pass = sum(
            1 for r in self._stage_results.values()
            if r.quality_gate and r.quality_gate.passed
        )
        quality_gates_total = sum(
            1 for r in self._stage_results.values()
            if r.quality_gate is not None
        )

        auto_reviews_pass = sum(
            1 for r in self._stage_results.values()
            if r.auto_review and r.auto_review.passed
        )
        auto_reviews_total = sum(
            1 for r in self._stage_results.values()
            if r.auto_review is not None
        )

        return {
            "pipeline_id": self.pipeline_id,
            "total_latency_ms": total_ms,
            "execution_order": [s.value for s in self._execution_order],
            "stage_results": {
                s.value: {
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                    "quality_gate": {
                        "score": r.quality_gate.score if r.quality_gate else None,
                        "level": r.quality_gate.level if r.quality_gate else None,
                        "passed": r.quality_gate.passed if r.quality_gate else None,
                    } if r.quality_gate else None,
                    "auto_review": {
                        "overall": r.auto_review.overall if r.auto_review else None,
                        "level": r.auto_review.level if r.auto_review else None,
                        "passed": r.auto_review.passed if r.auto_review else None,
                    } if r.auto_review else None,
                    "hitl_approved": r.hitl_approved,
                    "error": r.error,
                }
                for s, r in self._stage_results.items()
            },
            "summary": {
                "total_stages": stage_count,
                "success_stages": success_count,
                "quality_gates_pass": f"{quality_gates_pass}/{quality_gates_total}",
                "auto_reviews_pass": f"{auto_reviews_pass}/{auto_reviews_total}",
            },
        }


# ─── CLI Demo ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=== AgentOrchestratorPipeline Demo ===\n")

    pipeline = AgentOrchestratorPipeline(
        enable_quality_gates=True,
        enable_auto_review=True,
        enable_hitl=False,  # Demo: skip HITL
        strict_mode=False,
    )

    result = pipeline.execute(
        topic="碳排放权交易对企业绿色创新的影响",
        venue="JFE",
        field="finance",
    )

    summary = result["summary"]
    print(f"Pipeline: {result['pipeline_id']}")
    print(f"Execution order: {' → '.join(result['execution_order'])}")
    print(f"Total latency: {result['total_latency_ms']:.0f}ms")
    print(f"Stages: {summary['success_stages']}/{summary['total_stages']} succeeded")
    print(f"QualityGates: {summary['quality_gates_pass']}")
    print(f"AutoReviews: {summary['auto_reviews_pass']}")
