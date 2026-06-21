"""AgentOrchestrator: Professional agent orchestration engine.

PaperOrchestra / DeepResearchAgent / Sentinel style orchestrator:

Key capabilities:
    1. Agent Registry — Dynamic registration of specialized agents
    2. Message Bus — Agent-to-agent communication
    3. Pipeline Builder — Define and execute multi-stage workflows
    4. Parallel Execution — Run dependency-free agents concurrently
    5. Self-Evolution Integration — Hooks into SelfEvolutionEngine
    6. HITL Integration — Pause at approval gates for human review
    7. Tracing — Full execution traces for debugging

Pipeline reference (PaperOrchestra):
    outline → literature → plotting → writing → refinement

Sentinel pipeline:
    research → retrieve → model → risk → scenario → synthesize
        (with HITL gate before synthesize)

Reference:
    - https://github.com/google-research/paper-orchestra
    - https://github.com/SkyworkAI/DeepResearchAgent
"""

from __future__ import annotations

__all__ = [
    "PipelineStage",
    "PipelineStep",
    "PipelineResult",
    "AgentOrchestrator",
]

import concurrent.futures
import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.core.agents.base import (
    AgentCancelledError,
    AgentConfig,
    AgentResult,
    BaseAgent,
    CancellationToken,
    HaltDecision,
)
from scripts.core.hitl_gate import HITLGate
from scripts.core.agent_state import hitl_manager
from scripts.core.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)


# ─── Pipeline Stage ─────────────────────────────────────────────────────────────


class PipelineStage(Enum):
    """Standard pipeline stages."""
    OUTLINE = "outline"
    LITERATURE = "literature"
    PLOTTING = "plotting"
    WRITING = "writing"
    REFINEMENT = "refinement"
    EVALUATION = "evaluation"
    # ── Report-specific stages ──────────────────────────────────────────────
    FINANCIAL_ANALYSIS = "financial_analysis"
    REPORT_WRITING = "report_writing"


# ─── Pipeline Step ─────────────────────────────────────────────────────────────


@dataclass
class PipelineStep:
    """A single step in a pipeline."""
    stage: PipelineStage
    agent_name: str
    depends_on: list[PipelineStage] = field(default_factory=list)
    hitl_gate: bool = False  # Pause for human approval
    skip: bool = False       # Conditionally skip this step
    condition: Callable[[dict], bool] | None = None  # Skip condition

    def should_run(self, context: dict) -> bool:
        if self.skip:
            return False
        if self.condition:
            return self.condition(context)
        return True


@dataclass
class PipelineResult:
    """Result of a complete pipeline run."""
    pipeline_name: str
    success: bool
    stage_results: dict[PipelineStage, AgentResult]
    final_context: dict[str, Any]
    total_latency_ms: float
    hitl_paused_at: PipelineStage | None = None
    evolution_events: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ─── AgentOrchestrator ────────────────────────────────────────────────────────


class AgentOrchestrator:
    """
    Professional agent orchestrator with pipeline execution.

    Architecture (3-tier):
        Tier 1 — Pipeline Orchestration  [AgentOrchestrator]
            Orchestrates the paper pipeline (outline → literature → plotting
            → writing → refinement) via registered BaseAgent instances.
        Tier 2 — Parallel Analyst Team  [ParallelAnalystOrchestrator]
            Handles 6 simultaneous financial analyst agents (fundamental,
            competitive, risk, valuation, earnings quality). Integrated via
            register_financial_agents().
        Tier 3 — Multi-Agent Coordination [MultiAgentOrchestrator]
            Task-distribution layer for general multi-agent workflows.
            Accessed independently; not wired into AgentOrchestrator.

    HITL Integration:
        All approval state is managed exclusively by HITLGate (the single
        source of truth). approve_step() and reject_step() delegate to
        HITLGate. The legacy _pending_approvals dict has been removed.

    Features:
        - Dynamic agent registration (DeepResearchAgent Agent Registry pattern)
        - Message bus for agent-to-agent communication
        - Pipeline builder for multi-stage workflows
        - Parallel execution for independent stages
        - HITL gates at approval checkpoints
        - Full execution tracing

    Usage:
        orchestrator = AgentOrchestrator(gateway)
        orchestrator.register_default_agents()

        # Sequential pipeline
        result = orchestrator.run_pipeline(
            pipeline_name="paper_pipeline",
            steps=[...],
            input_data={"topic": "...", "venue": "..."},
        )

        # Parallel execution
        results = orchestrator.run_parallel(
            agent_names=["outline", "literature"],
            input_data={...},
        )
    """

    def __init__(self, gateway: LLMGateway):
        self.gateway = gateway
        self._agents: dict[str, BaseAgent] = {}
        self._message_bus: list[dict] = []
        self._trace: list[dict] = []
        self._evolution_engine: Any = None  # Optional: SelfEvolutionEngine

        # HITL gate — single source of truth for approval state
        self._hitl_gate = HITLGate()

        # Wire into the shared HITLManager so that HITL events
        # (create_request/approve/reject) are tracked globally
        self._shared_hitl = hitl_manager

        # Cancellation token registry: agent_name -> CancellationToken
        self._active_tokens: dict[str, CancellationToken] = {}

        # Rejection feedback injection: stage → feedback string
        # When reject_step() is called, feedback is stored here.
        # The next run_pipeline() reads from here and injects into agent context.
        self._rejection_feedback: dict[str, str] = {}

        # AI Parliament instance (injected via set_parliament or wire from AgentPipeline)
        self._parliament: Any = None


    def cancel_agent(self, agent_name: str,
                     reason: str = "orchestrator requested") -> bool:
        """
        Cancel a running agent by name.

        The agent must be currently executing inside a pipeline or parallel run
        started by this orchestrator. Cancellation is cooperative — the agent
        checks its CancellationToken at iteration start and after each
        act+reflect cycle, and will raise AgentCancelledError.

        Parameters
        ----------
        agent_name : str
            Name of the agent to cancel (as registered via register()).
        reason : str
            Human-readable cancellation reason.

        Returns
        -------
        bool
            True if the agent was found and cancellation was requested,
            False if the agent is not currently running.
        """
        if agent_name in self._active_tokens:
            self._active_tokens[agent_name].cancel(reason)
            logger.info(f"Cancellation requested for agent '{agent_name}': {reason}")
            return True
        return False

    def is_agent_active(self, agent_name: str) -> bool:
        """Return True if the named agent is currently running."""
        return agent_name in self._active_tokens

    # ── Agent Registry ─────────────────────────────────────────────────────

    def register(self, agent: BaseAgent) -> None:
        """
        Register a professional agent (DeepResearchAgent Agent Registry pattern).

        Agents are registered by name and can be retrieved and run by the pipeline.
        """
        self._agents[agent.config.name] = agent
        self._trace.append({
            "type": "agent_registered",
            "agent_name": agent.config.name,
            "timestamp": time.time(),
        })
        # Also register with gateway's tool-whitelist registry so that
        # allowed_tools enforcement is active for all tool calls made by this agent.
        self.gateway.register_agent(agent.config.name, agent.config.allowed_tools)

    def unregister(self, agent_name: str) -> None:
        """Remove an agent from the registry."""
        if agent_name in self._agents:
            del self._agents[agent_name]

    def get_agent(self, name: str) -> BaseAgent | None:
        """Get a registered agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    def register_default_agents(self, citation_verifier=None):
        """
        Register PaperOrchestra's standard 5-agent pipeline.

        Agents:
            1. outline — OutlineAgent
            2. literature — LiteratureReviewAgent
            3. plotting — PlottingAgent
            4. writing — SectionWritingAgent
            5. refinement — ContentRefinementAgent
        """
        from scripts.core.agents.paper_agents import (
            ContentRefinementAgent,
            DataFetchAgent,
            LiteratureReviewAgent,
            OutlineAgent,
            PlottingAgent,
            SectionWritingAgent,
        )

        # Outline Agent
        self.register(OutlineAgent(AgentConfig(
            name="outline",
            role="论文大纲设计专家",
            goal="将研究想法转化为结构化论文大纲",
            backstory=(
                "你是一位有10年经验的学术论文写作教练，擅长为机器学习、"
                "人工智能、金融工程等领域的论文设计清晰、有说服力的结构。"
                "你对CVPR、ICML、NeurIPS、ACL、IEEE等顶会的论文格式有深入了解。"
            ),
            allowed_tools=["arxiv", "brave_search", "fetch"],
            max_iterations=3,
            output_format="json",
        ), self.gateway))

        # Literature Review Agent
        self.register(LiteratureReviewAgent(AgentConfig(
            name="literature",
            role="文献综述专家",
            goal="检索、验证和综合相关文献，确保≥90%引用覆盖率",
            backstory=(
                "你是一位专业的学术文献综述专家，精通 Semantic Scholar、"
                "ArXiv、CrossRef 等文献数据库。你擅长识别核心文献、"
                "追踪研究脉络，并对引用真实性进行严格验证。"
            ),
            allowed_tools=["arxiv", "brave_search", "fetch", "context7"],
            max_iterations=5,
            output_format="json",
        ), self.gateway, citation_verifier=citation_verifier))

        # Plotting Agent
        self.register(PlottingAgent(AgentConfig(
            name="plotting",
            role="数据可视化专家",
            goal="根据图表计划生成高质量的matplotlib图表",
            backstory=(
                "你是一位数据可视化专家，擅长使用 matplotlib、seaborn、"
                "plotly 等工具生成学术级别的图表。"
                "你熟悉顶会对图表的质量要求（DPI≥300，字体Times New Roman）。"
            ),
            allowed_tools=[],
            max_iterations=2,
        ), self.gateway))

        # Section Writing Agent
        self.register(SectionWritingAgent(AgentConfig(
            name="writing",
            role="学术论文写作专家",
            goal="根据大纲和数据撰写完整的论文章节",
            backstory=(
                "你是一位顶尖的学术论文写作者，精通中英文学术写作。"
                "你对论文各部分的写作规范有深入了解，能够在创新性、"
                "技术深度和可读性之间取得平衡。"
            ),
            allowed_tools=["arxiv", "context7", "province_indicator", "province_rankings"],
            max_iterations=3,
            temperature=0.7,
        ), self.gateway))

        # Content Refinement Agent
        self.register(ContentRefinementAgent(AgentConfig(
            name="refinement",
            role="模拟同行评审专家",
            goal="基于 halt rules 判断论文是否达到投稿标准",
            backstory=(
                "你是一位严厉但公正的学术期刊审稿人，对顶会论文有严格要求。"
                "你的审稿意见具体、可操作，帮助作者真正提升论文质量。"
            ),
            allowed_tools=[],
            max_iterations=5,
        ), self.gateway))

        # Data Fetch Agent — province/macro data collection
        # Tool names here match ToolSelector.TOOL_REGISTRY_BASE keys (not MCP tool names).
        # ToolSelector maps these to MCP server:tool pairs via MCP_TOOL_SERVER_MAP.
        self.register(DataFetchAgent(AgentConfig(
            name="data_fetch",
            role="数据获取专家",
            goal="通过 province-stats MCP 获取全国31省科技创新数据，"
                 "包括GDP/R&D/高校/高新企业/技术合同/数字经济等9大类指标，"
                 "并自动进行数据溯源和质量评估",
            backstory=(
                "你是一位专业的数据采集与验证专家，精通中国各省统计公报、"
                "科技年鉴、科技部公报等权威数据源的检索与整理。"
                "你能够根据研究需求，自动选择合适的省数据工具进行批量查询，"
                "并对估算值、缺失数据给出明确的标注。"
                "你熟悉以下数据分类标准："
                "  A类（verification=full）：各省统计公报官方数据，来源完整"
                "  B类（verification=partial）：核心指标有官方来源，IND/AI/FIN类为估算（标注*）"
                "  C类（verification=minimal）：仅核心GDP/R&D指标有来源"
            ),
            allowed_tools=[
                "province_indicator",    # → user-province-stats.get_province_indicator
                "province_timeseries",   # → user-province-stats.get_province_timeseries
                "province_rankings",     # → user-province-stats.get_province_rankings
                "province_summary",      # → user-province-stats.get_all_provinces_summary
            ],
            max_iterations=2,
            output_format="json",
        ), self.gateway))

        # Update LiteratureReviewAgent to also be able to cite provincial data
        self._agents["literature"].config.allowed_tools.extend([
            "province_indicator",
            "province_rankings",
        ])

    def register_financial_agents(self) -> ParallelAnalystOrchestrator:
        """
        Register financial analyst agents for research report generation.

        Registers:
            - ParallelAnalystOrchestrator (handles all 6 analyst agents internally)
            - ResearchReportAgent (writes the final financial report)
        """
        from scripts.core.analyst_agents import (
            ParallelAnalystOrchestrator,
        )
        self._analyst_orchestrator = ParallelAnalystOrchestrator(gateway=self.gateway)
        return self._analyst_orchestrator

    # ── Message Bus ──────────────────────────────────────────────────────

    def broadcast(self, message: dict) -> None:
        """
        Broadcast a message to the message bus.

        Agents can use the bus to share intermediate results,
        warnings, or requests for other agents.
        """
        message["_bus_timestamp"] = time.time()
        self._message_bus.append(message)
        # Evict messages older than 1 hour — keep bus bounded
        if len(self._message_bus) > 1000:
            cutoff = time.time() - 3600
            evicted = len(self._message_bus) - sum(
                1 for m in self._message_bus if m["_bus_timestamp"] >= cutoff
            )
            self._message_bus[:] = [m for m in self._message_bus if m["_bus_timestamp"] >= cutoff]
            logger.warning(
                "[MessageBus] Evicted %d stale messages (bus was at %d). "
                "Consider reducing bus size or increasing eviction frequency.",
                evicted, len(self._message_bus) + evicted,
            )

    def get_messages(self, agent_name: str | None = None) -> list[dict]:
        """
        Get messages from the bus, optionally filtered by recipient.
        """
        if agent_name:
            return [
                m for m in self._message_bus
                if m.get("recipient") == agent_name or m.get("recipient") == "*"
            ]
        return list(self._message_bus)

    def get_snapshot(self, limit: int = 100, since: float | None = None) -> list[dict]:
        """
        Get a snapshot of recent bus messages.

        Parameters
        ----------
        limit : int
            Maximum messages to return (newest first).
        since : float | None
            Unix timestamp filter — only return messages after this time.
        """
        messages = self._message_bus
        if since is not None:
            messages = [m for m in messages if m["_bus_timestamp"] >= since]
        return list(reversed(messages[-limit:]))

    def export_to_json(self, path: str | Path) -> None:
        """
        Export the full message bus to a JSON file.

        Useful for debugging, audit trails, and replaying conversations.
        """
        import json
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"messages": self._message_bus, "count": len(self._message_bus)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_bus_stats(self) -> dict:
        """Return bus health statistics."""
        count = len(self._message_bus)
        now = time.time()
        by_type: dict = defaultdict(int)
        for m in self._message_bus:
            by_type[m.get("type", "unknown")] += 1
        return {
            "total_messages": count,
            "capacity_pct": min(round(count / 1000 * 100, 1), 999.9),
            "near_capacity": count > 800,
            "messages_by_type": dict(by_type),
            "oldest_message_age_seconds": round(now - self._message_bus[0]["_bus_timestamp"], 1) if self._message_bus else None,
            "newest_message_age_seconds": round(now - self._message_bus[-1]["_bus_timestamp"], 1) if self._message_bus else None,
        }

    def clear_bus(self) -> None:
        """Clear all messages from the bus."""
        self._message_bus.clear()

    # ── Pipeline Execution ───────────────────────────────────────────────

    def run_pipeline(
        self,
        pipeline_name: str,
        steps: list[PipelineStep],
        input_data: dict[str, Any],
        parallel: bool = False,
        max_workers: int = 4,
    ) -> PipelineResult:
        """
        Execute a multi-stage pipeline.

        Parameters
        ----------
        pipeline_name : str
            Human-readable name for this pipeline run.
        steps : list[PipelineStep]
            Ordered list of pipeline stages.
        input_data : dict
            Initial context passed to the first agent.
        parallel : bool
            If True, run dependency-free stages concurrently.
        max_workers : int
            Max concurrent agents in parallel mode.

        Returns
        -------
        PipelineResult
            Full pipeline result with all stage outputs and trace.
        """
        # Inject rejection feedback for any stage that was previously rejected
        # This ensures the agent improves based on human feedback before retrying
        enriched_input = input_data.copy()
        for stage_value, feedback in self._rejection_feedback.items():
            enriched_input[f"rejection_feedback_{stage_value}"] = feedback
        return self._run_pipeline_impl(
            pipeline_name=pipeline_name,
            steps=steps,
            input_data=enriched_input,
            parallel=parallel,
            max_workers=max_workers,
        )

    def resume_pipeline(
        self,
        paused_result: PipelineResult,
        steps: list[PipelineStep],
    ) -> PipelineResult:
        """
        Resume a HITL-paused pipeline after approval or rejection.

        Parameters
        ----------
        paused_result : PipelineResult
            The PipelineResult returned when run_pipeline() hit a HITL gate.
        steps : list[PipelineStep]
            The same steps list passed to the original run_pipeline() call.

        Returns
        -------
        PipelineResult
            Full pipeline result from the resume point.
        """
        if paused_result.hitl_paused_at is None:
            logger.warning("resume_pipeline called but no HITL pause found")
            return paused_result

        paused_stage = paused_result.hitl_paused_at

        # Build context carrying over completed stage results
        resume_context = dict(paused_result.final_context)
        # Inject completed stage outputs so downstream stages can access them
        for stage, result in paused_result.stage_results.items():
            resume_context[f"{stage.value}_result"] = result.output

        # Find index of the paused stage and resume from the next one
        resume_idx = 0
        for i, step in enumerate(steps):
            if step.stage == paused_stage:
                resume_idx = i + 1  # skip the paused stage itself, resume from next
                break

        # Clamp to valid range
        resume_idx = min(resume_idx, len(steps) - 1)
        if resume_idx >= len(steps):
            logger.warning(
                f"resume_pipeline: all steps completed (resume_idx={resume_idx} >= len(steps)={len(steps)}), "
                "returning existing paused_result"
            )
            return paused_result

        logger.info(
            f"Resuming pipeline '{paused_result.pipeline_name}' "
            f"from step {resume_idx} ({paused_stage.value} approved)"
        )

        return self._run_pipeline_impl(
            pipeline_name=paused_result.pipeline_name,
            steps=steps,
            input_data=resume_context,
            parallel=False,
            max_workers=4,
            _resume_from_step=resume_idx,
            _resume_context=resume_context,
        )

    def run_parallel(
        self,
        agent_names: list[str],
        input_data: dict[str, Any],
        max_workers: int = 4,
    ) -> dict[str, AgentResult]:
        """
        Run multiple agents in parallel (independent stages only).

        PaperOrchestra: literature review and plotting can run in parallel
        after the outline is finalized.

        Usage:
            results = orchestrator.run_parallel(
                agent_names=["literature", "plotting"],
                input_data={"outline": outline_result, ...},
            )
        """
        results: dict[str, AgentResult] = {}
        errors: dict[str, str] = {}

        def run_single(agent_name: str) -> tuple[str, AgentResult | Exception]:
            agent = self._agents.get(agent_name)
            if not agent:
                return agent_name, ValueError(f"Agent '{agent_name}' not registered")
            token = CancellationToken()
            self._active_tokens[agent_name] = token
            try:
                result = agent.run(input_data, cancel_token=token)
                return agent_name, result
            except AgentCancelledError as exc:
                return agent_name, AgentResult(
                    status="cancelled",
                    output={"cancelled": True},
                    feedback=f"Agent cancelled: {exc}",
                )
            except Exception as exc:
                return agent_name, exc
            finally:
                self._active_tokens.pop(agent_name, None)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_single, name): name
                for name in agent_names
            }

            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    name, result = future.result()
                    if isinstance(result, Exception):
                        results[name] = AgentResult(
                            status="error",
                            output={"error": str(result)},
                            feedback=f"Execution error: {result}",
                        )
                    else:
                        results[name] = result
                except Exception as exc:
                    results[agent_name] = AgentResult(
                        status="error",
                        output={"error": str(exc)},
                        feedback=f"Future error: {exc}",
                    )

        return results

    # ── HITL Integration ─────────────────────────────────────────────────

    def set_hitl_gate(self, gate: HITLGate) -> None:
        """Replace the internal HITL gate with an externally-provided one."""
        self._hitl_gate = gate

    def _gate_id_for_stage(self, stage: PipelineStage) -> str | None:
        """Find the gate_id for a pending HITL gate at the given stage."""
        # Use public API to avoid accessing _pending dict directly (thread-safe)
        for rec in self._hitl_gate.get_pending():
            if rec.stage == stage.value:
                return rec.gate_id
        return None

    def approve_step(self, stage: PipelineStage, feedback: str = "") -> dict:
        """
        Approve a HITL-paused pipeline step and resume execution.

        Delegates to the attached HITLGate as the single source of truth,
        and also dispatches to the shared HITLManager for global tracking.
        """
        gate_id = self._gate_id_for_stage(stage)
        if gate_id:
            record = self._hitl_gate.approve(gate_id, feedback=feedback)
            # Also record in global HITLManager
            self._shared_hitl.create_request(
                agent_id=stage.value,
                task_id=gate_id,
                decision_point=f"approve_{stage.value}",
                context={"record": record, "feedback": feedback}
            )
            return {"approved": True, "feedback": feedback, "record": record, "gate_id": gate_id}
        return {}

    def reject_step(self, stage: PipelineStage, feedback: str) -> dict:
        """
        Reject a HITL-paused step and trigger rollback.

        Delegates to the attached HITLGate. Stores rejection feedback so the next
        pipeline run can inject it into the agent's context for improvement.
        """
        gate_id = self._gate_id_for_stage(stage)
        if gate_id:
            record = self._hitl_gate.reject(gate_id, feedback=feedback)
            # Also record in global HITLManager
            self._shared_hitl.create_request(
                agent_id=stage.value,
                task_id=gate_id,
                decision_point=f"reject_{stage.value}",
                context={"record": record, "feedback": feedback}
            )
            # Inject feedback so the next run_pipeline() can improve automatically
            self._rejection_feedback[stage.value] = feedback
            return {"approved": False, "feedback": feedback, "record": record, "gate_id": gate_id}
        return {}

    # ── Pipeline Execution Impl ───────────────────────────────────────────────

    def _run_pipeline_impl(
        self,
        pipeline_name: str,
        steps: list[PipelineStep],
        input_data: dict[str, Any],
        parallel: bool = False,
        max_workers: int = 4,
        _resume_from_step: int = 0,
        _resume_context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """
        Internal pipeline execution (also used for HITL resume).

        Parameters
        ----------
        _resume_from_step : int
            Index of the step to resume from (used after HITL approval).
        _resume_context : dict | None
            Pre-built context to continue from (replaces rebuilding from input_data).
        """
        # Check if parliament integration is available
        _has_parliament = False
        _parliament = None
        try:
            if (hasattr(self, "_parliament") and self._parliament is not None):
                _has_parliament = True
                _parliament = self._parliament
        except Exception as exc:
            logger.debug("[AgentOrchestrator] Parliament check failed (skipping parliament review): %s", exc)

        start_time = time.time()
        if _resume_context is not None:
            context = dict(_resume_context)
        else:
            context = dict(input_data)

        stage_results: dict[PipelineStage, AgentResult] = {}
        hitl_paused_at: PipelineStage | None = None

        for step in steps[_resume_from_step:]:
            if not step.should_run(context):
                self._trace.append({
                    "type": "step_skipped",
                    "stage": step.stage.value,
                    "timestamp": time.time(),
                })
                continue

            agent = self._agents.get(step.agent_name)
            if not agent:
                self._trace.append({
                    "type": "agent_not_found",
                    "stage": step.stage.value,
                    "agent_name": step.agent_name,
                    "timestamp": time.time(),
                })
                stage_results[step.stage] = AgentResult(
                    stage=step.stage.value,
                    status="error",
                    output={},
                    halted_by=HaltDecision.REJECTED,
                )
                continue

            deps_satisfied = all(
                stage_results.get(dep) is not None
                for dep in step.depends_on
            )
            if not deps_satisfied:
                self._trace.append({
                    "type": "deps_not_satisfied",
                    "stage": step.stage.value,
                    "dependencies": [d.value for d in step.depends_on],
                    "timestamp": time.time(),
                })
                stage_results[step.stage] = AgentResult(
                    stage=step.stage.value,
                    status="error",
                    output={},
                    halted_by=HaltDecision.REJECTED,
                )
                continue

            # Build agent_context BEFORE the HITL gate so it is in scope
            # Inject any prior rejection feedback so the agent can improve
            agent_context = {
                **context,
                "messages": self.get_messages(step.agent_name),
            }
            # Inject rejection feedback from previous rejection
            if step.stage.value in self._rejection_feedback:
                prior_feedback = self._rejection_feedback.pop(step.stage.value)
                agent_context["prior_rejection_feedback"] = prior_feedback
                agent_context["messages"].append({
                    "role": "system",
                    "content": f"[审核反馈] 上一轮审核未通过，请根据以下反馈改进：{prior_feedback}",
                })

            # ── HITL Gate ─────────────────────────────────────────────────
            if step.hitl_gate:
                # Build enriched gate content with parliament verdict
                gate_content = {
                    "context": agent_context,
                    "result_preview": str(context)[:500],
                    "stage_result": result.output,
                }
                if hasattr(self, "_pending_parliament_verdict"):
                    gate_content["parliament_verdict"] = self._pending_parliament_verdict
                gate_id = self._hitl_gate.hold(
                    stage=step.stage.value,
                    content=gate_content,
                    question=f"请审核 {step.stage.value} 阶段的输出并决定是否继续。",
                )
                hitl_paused_at = step.stage
                # Also register globally so SSE/web UI can see it
                self._shared_hitl.create_request(
                    agent_id=step.agent_name,
                    task_id=gate_id,
                    decision_point=step.stage.value,
                    context={"context": agent_context, "result_preview": str(context)[:500]},
                )
                self._trace.append({
                    "type": "hitl_pause",
                    "stage": step.stage.value,
                    "context_preview": str(context)[:200],
                    "timestamp": time.time(),
                })
                return PipelineResult(
                    pipeline_name=pipeline_name,
                    success=False,
                    stage_results=stage_results,
                    final_context=context,
                    total_latency_ms=(time.time() - start_time) * 1000,
                    hitl_paused_at=hitl_paused_at,
                    trace=self._trace,
                )

            # ── Execute Agent ───────────────────────────────────────────────
            self._trace.append({
                "type": "agent_start",
                "stage": step.stage.value,
                "agent_name": step.agent_name,
                "timestamp": time.time(),
            })

            token = CancellationToken()
            self._active_tokens[step.agent_name] = token

            try:
                result = agent.run(agent_context, cancel_token=token)
            except AgentCancelledError as exc:
                result = AgentResult(
                    status="cancelled",
                    output={"cancelled": True},
                    feedback=f"Agent cancelled: {exc}",
                )
            except Exception as exc:
                result = AgentResult(
                    status="error",
                    output={"error": str(exc)},
                    feedback=f"Agent execution error: {exc}",
                )
            finally:
                self._active_tokens.pop(step.agent_name, None)

            stage_results[step.stage] = result
            context[f"{step.stage.value}_result"] = result.output

            self.broadcast({
                "type": "agent_result",
                "stage": step.stage.value,
                "sender": step.agent_name,
                "result": result.output,
                "status": result.status,
            })

            # ── Parliament Review (before HITL gate) ─────────────────────────
            # Run AI parliament review AFTER stage execution but BEFORE the
            # HITL approval gate is created, so the verdict is available to
            # the human reviewer.
            if _has_parliament and step.hitl_gate:
                try:
                    import asyncio as _asyncio
                    verdict = _asyncio.run(
                        _parliament._parliament_review({
                            "text": str(result.output)[:2000],
                            "stage": step.stage.value,
                        })
                    )
                    self._pending_parliament_verdict = verdict
                    logger.info(
                        "Parliament verdict for %s: score=%s, disputed=%s",
                        step.stage.value,
                        verdict.get("score", "N/A"),
                        verdict.get("disputed", False),
                    )
                except Exception as exc:
                    logger.warning(
                        "Parliament review skipped for %s: %s",
                        step.stage.value, exc,
                    )
                    self._pending_parliament_verdict = {}

            # ── Evolution Hook ──────────────────────────────────────────────
            if self._evolution_engine and result.status in ("approved", "max_iterations"):
                try:
                    evolution_event = self._evolution_engine.record_and_assess(
                        agent_name=step.agent_name,
                        result=result,
                        context=context,
                    )
                    if evolution_event:
                        self._trace.append({
                            "type": "evolution",
                            "agent_name": step.agent_name,
                            "event": evolution_event,
                            "timestamp": time.time(),
                        })
                except Exception as exc:
                    logger.warning("[AgentOrchestrator] Evolution hook failed for %s (proceeding without evolution record): %s", step.agent_name, exc)

            self._trace.append({
                "type": "agent_end",
                "stage": step.stage.value,
                "agent_name": step.agent_name,
                "status": result.status,
                "iterations": result.iterations,
                "latency_ms": result.latency_ms,
                "timestamp": time.time(),
            })

            if result.status == "error":
                break

        total_latency_ms = (time.time() - start_time) * 1000

        return PipelineResult(
            pipeline_name=pipeline_name,
            success=hitl_paused_at is None
            and len(stage_results) == len([s for s in steps if not s.skip])
            and all(r.status != "error" for r in stage_results.values()),
            stage_results=stage_results,
            final_context=context,
            total_latency_ms=total_latency_ms,
            hitl_paused_at=hitl_paused_at,
            trace=self._trace,
        )

    # ── Evolution Integration ───────────────────────────────────────────────

    def set_evolution_engine(self, engine: Any) -> None:
        """Attach a self-evolution engine for continuous improvement.

        Also registers all currently loaded agents with the evolution engine.
        """
        self._evolution_engine = engine

        # Register all agents with the evolution engine
        if engine is not None and hasattr(engine, 'register_agent'):
            for agent_name, agent in self._agents.items():
                engine.register_agent(agent_name, agent)
            logger.info(f"Registered {len(self._agents)} agents with evolution engine")

    def set_parliament(self, parliament: Any) -> None:
        """Attach an AIParliamentHITLIntegration instance for machine review before HITL gates."""
        self._parliament = parliament
        logger.info("AIParliament attached for HITL pre-review")

    # ── Tracing ─────────────────────────────────────────────────────────

    def get_trace(self) -> list[dict]:
        """Return the full execution trace."""
        return list(self._trace)

    def save_trace(self, path: str | Path) -> None:
        """Save execution trace to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear_trace(self) -> None:
        """Clear the execution trace."""
        self._trace.clear()

    def run_with_checkpoint(
        self,
        task: str,
        steps: list[PipelineStep],
        input_data: dict[str, Any],
        checkpoint_id: str | None = None,
        checkpoint_every: int = 1,
    ) -> PipelineResult:
        """
        Run a pipeline with checkpointing enabled.

        Saves a checkpoint after each completed stage (controlled by ``checkpoint_every``).
        On crash, call again with the same ``task`` name and it resumes from the latest
        checkpoint automatically.

        Parameters
        ----------
        task : str
            Unique identifier for this pipeline run (used as pipeline_id).
        steps : list[PipelineStep]
            Ordered list of pipeline stages.
        input_data : dict
            Initial context passed to the first stage.
        checkpoint_id : str | None
            Specific checkpoint to resume from. If None, resumes from the latest
            checkpoint for ``task``.
        checkpoint_every : int
            Save a checkpoint every ``checkpoint_every`` stages (default 1 = every stage).

        Returns
        -------
        PipelineResult
            Full pipeline result.
        """
        try:
            from scripts.core.checkpoint import CheckpointManager, PipelineCheckpoint
        except ImportError:
            # Fallback: plain run without checkpointing
            return self.run_pipeline(
                pipeline_name=task,
                steps=steps,
                input_data=input_data,
            )

        manager = CheckpointManager()
        pipeline_id = task.replace(" ", "_")

        context: dict[str, Any] = dict(input_data)
        stage_results: dict[str, Any] = {}

        # Resume from checkpoint if available
        if checkpoint_id:
            cp = manager.load(pipeline_id, checkpoint_id)
        else:
            cp = manager.load_latest(pipeline_id)

        if cp is not None:
            context = manager.restore_context(cp)
            # Reconstruct completed stage results from checkpoint context
            for stage_key in cp.completed_stages:
                result_key = f"{stage_key}_result"
                if result_key in context:
                    stage_results[stage_key] = context[result_key]
            print(f"[run_with_checkpoint] Resuming '{pipeline_id}' from stage index {cp.completed_stage_index + 1}")

        # Determine starting index
        latest = manager.load_latest(pipeline_id)
        offset = (latest.completed_stage_index + 1) if latest else 0

        for i, step in enumerate(steps):
            current_idx = offset + i

            result = self.run_pipeline(
                pipeline_name=pipeline_id,
                steps=[step],
                input_data=context,
            )

            # Accumulate state
            context[f"{step.stage.value}_result"] = result.final_context.get(
                f"{step.stage.value}_result", {}
            )
            stage_results[step.stage.value] = result.final_context.get(
                f"{step.stage.value}_result", {}
            )

            # Save checkpoint
            if checkpoint_every > 0 and (current_idx + 1) % checkpoint_every == 0:
                hitl_state = None
                if self._hitl_gate:
                    try:
                        pending = [
                            {"gate_id": r.gate_id, "stage": r.stage, "state": r.state.value,
                             "content": r.content, "question": r.question}
                            for r in self._hitl_gate.get_pending()
                        ]
                        hitl_state = {"pending": pending, "history": [], "stats": self._hitl_gate.stats()}
                    except Exception:
                        pass

                manager.save(
                    pipeline_id=pipeline_id,
                    pipeline_name=task,
                    completed_stage=step.stage.value,
                    context=context,
                    stage_results=dict(stage_results),
                    hitl_state=hitl_state,
                    metadata={"total_steps": len(steps), "current_step": i + 1},
                )

            # Stop on HITL pause
            if result.hitl_paused_at is not None:
                return result

        return result

    def __repr__(self) -> str:
        return f"AgentOrchestrator(agents={len(self._agents)}, trace={len(self._trace)})"
