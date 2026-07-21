"""
checkpoint_pipeline_integration.py — Checkpoint 系统与主 Pipeline 的集成

将 CheckpointableOrchestrator 接入 EnhancedPipeline 和 ResearchSession，
实现：
1. 每次 stage 完成后自动保存 checkpoint
2. 崩溃后自动恢复
3. HITL gate 状态序列化与恢复
4. CLI 断点续传命令

Usage:
    # 在 EnhancedPipeline 中启用 checkpoint
    from scripts.core.checkpoint_pipeline_integration import CheckpointedEnhancedPipeline

    pipeline = CheckpointedEnhancedPipeline(
        config=project_config,
        enable_checkpoint=True,
        checkpoint_dir="data/checkpoints",
    )

    # 自动从上次断点继续（如果存在）
    pipeline.run_from_checkpoint(
        pipeline_name="my_research",
        topic="关税政策对创新的影响",
    )
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CheckpointedEnhancedPipeline",
    "CheckpointCLI",
    "checkpoint_resume",
]


# ─── CheckpointedEnhancedPipeline ───────────────────────────────────────────

class CheckpointedEnhancedPipeline:
    """
    带 Checkpoint 功能的 EnhancedPipeline 包装器。

    自动在每个 stage 完成时保存 checkpoint，
    支持崩溃恢复和手动断点续传。

    Usage:
        pipeline = CheckpointedEnhancedPipeline(
            config=project_config,
            enable_checkpoint=True,
            checkpoint_dir="data/checkpoints",
        )

        # 正常执行（每次 stage 后自动 checkpoint）
        result = pipeline.run("my_pipeline", topic="...")

        # 从断点恢复
        result = pipeline.run_from_checkpoint("my_pipeline", topic="...")
    """

    def __init__(
        self,
        config: dict | None = None,
        enable_checkpoint: bool = True,
        checkpoint_dir: str = "data/checkpoints",
        checkpoint_every: int = 1,
        auto_resume: bool = True,
        on_gate_approved: callable | None = None,
    ):
        self.config = config or {}
        self.enable_checkpoint = enable_checkpoint
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_every = checkpoint_every
        self.auto_resume = auto_resume
        # 可视化审批回调：在 HITL gate 审批通过后触发可视化推送
        self._on_gate_approved = on_gate_approved

        # Lazy import to avoid circular dependencies
        self._checkpoint_manager = None
        self._pipeline = None

    @property
    def checkpoint_manager(self):
        if self._checkpoint_manager is None:
            from scripts.core.checkpoint import CheckpointManager
            self._checkpoint_manager = CheckpointManager(base_dir=self.checkpoint_dir)
        return self._checkpoint_manager

    @property
    def pipeline(self):
        if self._pipeline is None:
            from scripts.research_framework.enhanced_pipeline import EnhancedPipeline
            cfg = self.config or {}
            self._pipeline = EnhancedPipeline(
                topic=cfg.get("topic", ""),
                language=cfg.get("language", "zh"),
                output_dir=cfg.get("output_dir", "output/"),
                enable_modern_did=cfg.get("enable_modern_did", True),
                enable_validation_gates=cfg.get("enable_validation_gates", True),
                enable_latex_lint=cfg.get("enable_latex_lint", True),
                enable_latex_diff=cfg.get("enable_latex_diff", True),
                enable_pdf_vision=cfg.get("enable_pdf_vision", False),
                enable_sandbox=cfg.get("enable_sandbox", True),
                enable_self_evolution=cfg.get("enable_self_evolution", False),
                enable_hitl=cfg.get("enable_hitl", True),
                hitl_timeout=cfg.get("hitl_timeout", 600),
                on_gate_approved=self._on_gate_approved,
            )
        return self._pipeline

    def run(
        self,
        pipeline_name: str,
        topic: str,
        steps: list | None = None,
        force_restart: bool = False,
        **kwargs,
    ):
        """
        执行 pipeline，带自动 checkpoint。

        Args:
            pipeline_name: 唯一标识符
            topic: 研究主题
            steps: 可选，手动指定 pipeline steps
            force_restart: True = 忽略已有 checkpoint，从头开始
            **kwargs: 传递给 EnhancedPipeline 的参数
        """
        pipeline_id = self._sanitise_id(pipeline_name)

        # 检查是否从 checkpoint 恢复
        if self.enable_checkpoint and self.auto_resume and not force_restart:
            latest = self.checkpoint_manager.load_latest(pipeline_id)
            if latest and latest.completed_stage_index >= 0:
                logger.info(
                    "[CheckpointPipeline] Found checkpoint for '%s': "
                    "stage %d/%s completed. Use run_from_checkpoint() to resume.",
                    pipeline_name, latest.completed_stage_index + 1,
                    latest.completed_stages[-1] if latest.completed_stages else "?",
                )

        return self._run_with_checkpoints(pipeline_name, topic, steps, **kwargs)

    def run_from_checkpoint(
        self,
        pipeline_name: str,
        topic: str | None = None,
        steps: list | None = None,
        **kwargs,
    ):
        """
        从上次 checkpoint 恢复执行。

        自动加载最新 checkpoint，恢复 context 和 HITL 状态，
        从中断的 stage 继续。
        """
        pipeline_id = self._sanitise_id(pipeline_name)

        latest = self.checkpoint_manager.load_latest(pipeline_id)
        if not latest:
            logger.warning(
                "[CheckpointPipeline] No checkpoint found for '%s'. Starting fresh.",
                pipeline_name,
            )
            return self.run(pipeline_name, topic or "", steps, force_restart=True, **kwargs)

        # 验证配置一致性
        is_safe, reason = self.checkpoint_manager.validate_resume(latest, self.config)
        if not is_safe:
            logger.warning(
                "[CheckpointPipeline] Config changed since checkpoint: %s. "
                "Starting fresh (force_restart=True).",
                reason,
            )
            return self.run(pipeline_name, topic or "", steps, force_restart=True, **kwargs)

        # 恢复 context
        context = self.checkpoint_manager.restore_context(latest)
        next_stage_idx = latest.completed_stage_index + 1

        logger.info(
            "[CheckpointPipeline] Resuming '%s' from stage %d (%s). "
            "Completed: %s",
            pipeline_name,
            next_stage_idx,
            latest.completed_stages[-1] if latest.completed_stages else "?",
            latest.completed_stages,
        )

        # 恢复 HITL 状态（pending 请求）
        if latest.hitl_state:
            restored_count = 0
            try:
                from scripts.core.agent_state import HITLManager
                hm = HITLManager()
                restored_count = hm.restore_from_checkpoint(latest.hitl_state)
                if restored_count > 0:
                    logger.info(
                        "[CheckpointPipeline] Restored %d HITL pending requests from checkpoint",
                        restored_count,
                    )
            except Exception as e:
                logger.warning(
                    "[CheckpointPipeline] Failed to restore HITL state: %s",
                    e,
                )

        # 恢复 topic（如果未指定）
        if topic is None:
            topic = context.get("topic", "")

        return self._run_with_checkpoints(
            pipeline_name, topic, steps,
            resume_from=next_stage_idx,
            restored_context=context,
            restored_checkpoint=latest,
            **kwargs,
        )

    def _run_with_checkpoints(
        self,
        pipeline_name: str,
        topic: str,
        steps: list | None,
        resume_from: int = 0,
        restored_context: dict | None = None,
        restored_checkpoint: Any | None = None,
        **kwargs,
    ):
        """内部：带 checkpoint 的执行循环。"""
        pipeline_id = self._sanitise_id(pipeline_name)
        config_hash = self.checkpoint_manager.compute_config_hash(self.config)

        context = restored_context or {"topic": topic}
        stage_results: dict[str, Any] = {}

        # 获取 pipeline steps
        if steps is None:
            steps = self._get_default_steps(topic)

        offset = resume_from
        remaining_steps = steps[offset:]

        if not remaining_steps:
            logger.info("[CheckpointPipeline] No remaining steps for '%s'", pipeline_name)
            return self._make_result(context, stage_results, pipeline_name)

        logger.info(
            "[CheckpointPipeline] Starting '%s': %d steps (offset=%d)",
            pipeline_name, len(remaining_steps), offset,
        )

        for i, step in enumerate(remaining_steps):
            step_name = step if isinstance(step, str) else getattr(step, "value", str(step))
            step_idx = offset + i

            logger.info(
                "[CheckpointPipeline] Stage %d/%d: %s",
                step_idx + 1, len(steps), step_name,
            )

            # 执行 stage
            try:
                stage_output = self._execute_stage(step_name, context, **kwargs)
            except Exception as e:
                logger.error("[CheckpointPipeline] Stage %s failed: %s", step_name, e)
                stage_output = {"error": str(e), "stage": step_name}

            # 更新状态
            context[f"{step_name}_result"] = stage_output
            context[f"{step_name}_completed_at"] = time.time()
            stage_results[step_name] = stage_output

            # 收集 HITL 状态（来自全局 HITLManager）
            hitl_state = self._collect_hitl_state()

            # Checkpoint
            if self.enable_checkpoint:
                self.checkpoint_manager.save(
                    pipeline_id=pipeline_id,
                    pipeline_name=pipeline_name,
                    completed_stage=step_name,
                    context=context,
                    stage_results=dict(stage_results),
                    hitl_state=hitl_state,
                    config_hash=config_hash,
                    metadata={
                        "topic": topic,
                        "total_stages": len(steps),
                        "current_stage": step_idx + 1,
                        "offset": offset,
                    },
                )

        logger.info("[CheckpointPipeline] Completed '%s': all %d stages done", pipeline_name, len(steps))
        return self._make_result(context, stage_results, pipeline_name)

    def _collect_hitl_state(self) -> dict | None:
        """
        从全局 HITLManager 收集当前的 HITL 状态。

        用于在 checkpoint 时序列化所有待处理的 HITL 请求，
        以便 resume 时能正确恢复交互状态。
        """
        try:
            from scripts.core.agent_state import HITLManager
            hm = HITLManager()
            pending = hm.get_pending()
            if not pending:
                return None
            return {
                "pending_requests": [
                    {
                        # Use getattr with fallbacks to handle potential field name variations
                        "request_id": r.request_id,
                        "agent_name": getattr(r, "agent_name", r.agent_id),
                        "task_id": getattr(r, "task_id", ""),
                        "step_name": getattr(r, "step_name", getattr(r, "decision_point", "")),
                        "created_at": r.created_at,
                        # Persist full context so resume can reconstruct intent
                        "context_summary": str(getattr(r, "context", {}))[:500],
                    }
                    for r in pending
                ],
                "collected_at": time.time(),
            }
        except Exception:
            return None

    def _execute_stage(self, step_name: str, context: dict, **kwargs) -> dict:
        """
        执行单个 stage，委托给真实的 pipeline。

        调度策略：
        1. Resume 场景（context 中有缓存结果）→ 直接返回
        2. step_name == "full_run" → 调用 pipeline.run()（继承全部 HITL gates）
        3. 否则调用单个具名 step（需要显式创建 HITL gate）

        注意：CheckpointedEnhancedPipeline 应优先使用 full_run 模式，
        以获得 EnhancedPipeline.run() 中嵌入的 ④ 个经济学专属 HITL gates。
        """
        # 1. Resume 场景：复用已缓存结果
        result = context.get(f"{step_name}_result")
        if result is not None:
            return result

        pipeline = self.pipeline
        topic = context.get("topic", "")
        stage_output = None
        dispatch_source = None

        # 2. Full pipeline run: inherit all 4 HITL gates from EnhancedPipeline.run()
        if step_name == "full_run":
            dispatch_source = "EnhancedPipeline.run()"
            try:
                stage_output = pipeline.run()
                # PipelineContext may not be imported at module level
                try:
                    if isinstance(stage_output, PipelineContext):
                        stage_output = stage_output.to_dict()
                except NameError:
                    if hasattr(stage_output, "to_dict"):
                        stage_output = stage_output.to_dict()
            except Exception as e:
                stage_output = {"error": str(e), "stage": step_name}
            dispatch_source = "EnhancedPipeline.run()"

        # 3. Individual step: wrap with local HITL gate
        else:
            enhanced_step_map = {
                "load_data": "step1_load_data",
                "modern_did": "step2_modern_did",
                "robustness": "step3_robustness",
                "validation_gates": "step4_validation_gates",
                "latex_and_validation": "step5_latex_and_validation",
                "pdf_vision": "step6_pdf_vision_check",
            }

            method_name = enhanced_step_map.get(step_name)
            if method_name and hasattr(pipeline, method_name):
                method = getattr(pipeline, method_name)
                dispatch_source = "EnhancedPipeline.step"

                # 创建局部 HITL gate（经济学专属问题）
                hitl_content = self._build_step_content(step_name, context, pipeline)
                hitl_question = self._get_econ_gate_question(step_name)
                gate_result = self._hitl_hold(step_name, hitl_content, hitl_question)

                # 若 gate 拒绝，直接返回
                if gate_result and gate_result.get("decision") == "rejected":
                    return {
                        "stage": step_name,
                        "status": "hitl_rejected",
                        "feedback": gate_result.get("feedback", ""),
                        "_dispatched_via": dispatch_source,
                    }

                try:
                    stage_output = method(topic=topic, context=context, **kwargs)
                except TypeError:
                    try:
                        stage_output = method(topic=topic, context=context)
                    except TypeError:
                        try:
                            stage_output = method(topic=topic)
                        except TypeError:
                            stage_output = method()
                except Exception as e:
                    stage_output = {"error": str(e), "stage": step_name}
            else:
                # 4. 兜底：AgentOrchestrator
                dispatch_source = "AgentOrchestrator"
                try:
                    from scripts.core.orchestrator import AgentOrchestrator
                    orch = AgentOrchestrator()
                    orch_result = orch.run(topic=topic, steps=[step_name])
                    stage_output = {"orchestrator_result": orch_result, "step": step_name, "topic": topic}
                except Exception:
                    stage_output = {
                        "stage": step_name,
                        "status": "skipped",
                        "timestamp": time.time(),
                        "message": f"Stage '{step_name}' could not be dispatched. Topic: {topic}",
                        "context_keys": list(context.keys()),
                    }

        # 统一打包结果
        if isinstance(stage_output, dict) and "stage" not in stage_output:
            stage_output["stage"] = step_name
        if isinstance(stage_output, dict):
            stage_output["_dispatched_via"] = dispatch_source or "fallback"
        return stage_output

    def _hitl_hold(self, stage_name: str, content: dict, question: str) -> dict | None:
        """
        在 CheckpointedEnhancedPipeline 层面创建 HITL gate。

        若 enable_hitl=False 或 HITLGate 不可用，自动跳过（返回 None）。
        """
        if not getattr(self, "enable_checkpoint", True):
            return None
        try:
            from scripts.core.hitl_gate import HITLGate, GateState
            gate = HITLGate()
            record = gate.hold(stage=stage_name, content=content, question=question)
            return {
                "gate_id": record.gate_id,
                "state": record.state.value,          # Bug fix: ApprovalRecord has `state`, not `status`
                "feedback": record.feedback or "",
                "decision": record.state.value,       # GateState value: "pending"/"approved"/"rejected"
            }
        except Exception:
            return None

    def _get_econ_gate_question(self, step_name: str) -> str:
        """返回经济学实证各步骤的专属审核问题。"""
        questions = {
            "load_data": (
                "【数据质量审核】请确认：样本量是否充足？N/A 比例是否合理？"
                "处理组/控制组划分是否符合研究设计？"
            ),
            "modern_did": (
                "【DID 识别策略审核】请确认：处理变量定义是否合理？"
                "控制组选择是否恰当？平行趋势假设是否可检验？"
            ),
            "robustness": (
                "【稳健性检验审核】请确认稳健性检验计划：① 是否覆盖核心识别威胁？"
                "② 是否防止 p-hacking？③ 是否有遗漏的关键检验？"
            ),
            "validation_gates": (
                "【Validation Gate 审核】算法评估结果：新颖性/可行性/质量评分是否可接受？"
            ),
            "latex_and_validation": (
                "【LaTeX 草稿审核】请在生成最终草稿前确认实证结果：主系数、稳健性、异质性是否可接受？"
            ),
            "pdf_vision": (
                "【PDF 视觉检查审核】图表/表格排版是否符合期刊要求？"
            ),
        }
        return questions.get(step_name, f"请审核 step '{step_name}' 的结果。")

    def _build_step_content(self, step_name: str, context: dict, pipeline) -> dict:
        """构建各步骤的审核内容摘要。"""
        ctx = getattr(pipeline, "ctx", None)
        if ctx is None:
            return {"step": step_name, "topic": context.get("topic", "")}
        return {
            "step": step_name,
            "topic": context.get("topic", ""),
            "n_obs": len(ctx.df) if ctx.df is not None else 0,
            "n_did_results": len(ctx.modern_did_results) if ctx.modern_did_results else 0,
            "n_robustness": len(ctx.robustness_report) if ctx.robustness_report else 0,
        }

    def _get_default_steps(self, topic: str) -> list[str]:
        """获取默认的 pipeline steps。"""
        return [
            "literature_review",
            "hypothesis_generation",
            "novelty_check",
            "experiment_design",
            "data_acquisition",
            "paper_outline",
            "paper_draft",
        ]

    def _make_result(self, context: dict, stage_results: dict, pipeline_name: str) -> dict:
        return {
            "pipeline_name": pipeline_name,
            "context": context,
            "stage_results": stage_results,
            "completed": True,
            "timestamp": time.time(),
        }

    def _sanitise_id(self, name: str) -> str:
        import re
        return re.sub(r"[^\w\-_.]", "_", name)


# ─── Checkpoint CLI ─────────────────────────────────────────────────────────

class CheckpointCLI:
    """
    Checkpoint 命令行工具。

    提供交互式断点续传管理：
    - 列出已有 checkpoint
    - 查看 checkpoint 详情
    - 删除 checkpoint
    - 续传执行
    """

    def __init__(self, checkpoint_dir: str = "data/checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        self._init_manager()

    def _init_manager(self):
        from scripts.core.checkpoint import CheckpointManager
        self.manager = CheckpointManager(base_dir=self.checkpoint_dir)

    def list(self, pipeline_name: str | None = None) -> list[dict]:
        """列出所有 pipeline 或特定 pipeline 的 checkpoint。"""
        if pipeline_name:
            chks = self.manager.list_checkpoints(self._sanitise(pipeline_name), limit=20)
            return [self._summarize(c) for c in chks]

        # 列出所有 pipeline
        index_dir = Path(self.checkpoint_dir)
        if not index_dir.exists():
            return []

        pipelines: dict[str, dict] = {}
        for idx_file in index_dir.glob("index_*.json"):
            pid = idx_file.stem.replace("index_", "")
            stats = self.manager.stats(pid)
            pipelines[pid] = stats

        return list(pipelines.values())

    def show(self, pipeline_name: str, checkpoint_id: str | None = None) -> dict:
        """显示 checkpoint 详情。"""
        pid = self._sanitise(pipeline_name)
        chk = self.manager.load(pid, checkpoint_id)
        if not chk:
            return {"error": f"No checkpoint found for '{pipeline_name}'"}

        return {
            "pipeline_id": chk.pipeline_id,
            "pipeline_name": chk.pipeline_name,
            "timestamp": chk.timestamp,
            "datetime": self._format_time(chk.timestamp),
            "completed_stage_index": chk.completed_stage_index,
            "completed_stages": chk.completed_stages,
            "metadata": chk.metadata,
            "has_hitl_state": chk.hitl_state is not None,
            "config_hash": chk.config_hash or "(none)",
        }

    def delete(self, pipeline_name: str, checkpoint_id: str) -> bool:
        """删除指定 checkpoint。"""
        pid = self._sanitise(pipeline_name)
        return self.manager.delete(pid, checkpoint_id)

    def prune(self, pipeline_name: str, keep: int = 3) -> int:
        """删除旧 checkpoint，只保留最近的 N 个。"""
        pid = self._sanitise(pipeline_name)
        return self.manager.prune(pid, keep=keep)

    def resume(self, pipeline_name: str, topic: str | None = None, **kwargs):
        """从最新 checkpoint 恢复执行。"""
        pipeline = CheckpointedEnhancedPipeline(
            enable_checkpoint=True,
            checkpoint_dir=self.checkpoint_dir,
            on_gate_approved=self._on_gate_approved,
        )
        return pipeline.run_from_checkpoint(pipeline_name, topic=topic, **kwargs)

    def _summarize(self, chk) -> dict:
        return {
            "checkpoint_id": chk.checkpoint_id,
            "pipeline_name": chk.pipeline_name,
            "timestamp": chk.timestamp,
            "datetime": self._format_time(chk.timestamp),
            "completed_stage": chk.completed_stages[-1] if chk.completed_stages else "(none)",
            "stage_index": chk.completed_stage_index,
            "total_stages": chk.metadata.get("total_stages", "?"),
        }

    def _format_time(self, ts: float) -> str:
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    def _sanitise(self, name: str) -> str:
        import re
        return re.sub(r"[^\w\-_.]", "_", name)


# ─── 便捷函数 ───────────────────────────────────────────────────────────────

def checkpoint_resume(pipeline_name: str, topic: str | None = None) -> dict:
    """
    一行命令续传：
        checkpoint_resume("my_paper", "关税政策与ESG")
    """
    cli = CheckpointCLI()
    return cli.resume(pipeline_name, topic=topic)


def checkpoint_list(pipeline_name: str | None = None) -> list[dict]:
    """列出 checkpoint。"""
    cli = CheckpointCLI()
    return cli.list(pipeline_name)
