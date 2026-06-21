"""SelfEvolutionEngine: Agent self-evolution via SEPL protocol.

DeepResearchAgent SEPL (Self Evolution Protocol Layer):
    1. Propose  — Analyze execution history, suggest improvements
    2. Assess   — Evaluate proposal on test data
    3. Commit   — Apply approved improvements to agent configs
    4. Remember — Store evolution history in long-term memory

Reference: https://github.com/SkyworkAI/DeepResearchAgent
"""

from __future__ import annotations

__all__ = [
    "EvolutionEvent",
    "SelfEvolutionEngine",
    "SelfEvolutionAutoTrigger",
]

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.core.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)


@dataclass
class EvolutionEvent:
    """A single evolution event in the history."""
    timestamp: float
    agent_name: str
    proposal: dict
    assessment: dict
    committed: bool
    commit_message: str = ""


class SelfEvolutionEngine:
    """
    Self-evolution engine implementing the SEPL protocol.

    DeepResearchAgent design:
        - Act → Observe → Optimize → Remember loop per execution
        - Propose: LLM analyzes execution history and suggests config changes
        - Assess: Run candidate configs on test data, measure quality delta
        - Commit: Apply winning changes, record lineage
        - Remember: Persist evolution history, support rollback

    Usage:
        engine = SelfEvolutionEngine(memory, gateway)
        engine.record_and_assess("outline", result, context)
        engine.propose_improvements()
        engine.commit(assessment_id="...")
    """

    def __init__(self, memory, gateway: LLMGateway):
        self.memory = memory
        self.gateway = gateway
        self._history: list[EvolutionEvent] = []
        self._proposals: list[dict] = []
        self._assessments: list[dict] = []
        self._golden_config: dict[str, Any] = {}  # Backup of original configs
        self._quality_baseline: float = 0.7  # Minimum acceptable quality
        self._agents: dict[str, Any] = {}  # Registered agents for config patching
        self._is_active: bool = False       # 引擎激活状态
        self._activation_time: float | None = None
        self._evolution_log_path: str | None = None

    def activate(
        self,
        evolution_log_path: str | None = None,
        quality_baseline: float | None = None,
    ) -> dict[str, Any]:
        """
        激活自进化引擎，建立与研究工作流的连接。

        必须在研究会话启动前调用，激活后将：
        1. 记录当前 agent 配置作为 golden config（回滚基准）
        2. 初始化进化事件日志
        3. 启用自动监听（AutoTrigger）
        4. 注册到 ResearchSession（如果可用）

        Parameters
        ----------
        evolution_log_path : str | None
            进化历史日志路径（用于持久化）。默认 .cache/evolution_log.jsonl。
        quality_baseline : float | None
            质量基准线（0-1），低于此值触发进化。默认 0.7。

        Returns
        -------
        dict[str, Any]
            激活状态摘要。
        """
        if self._is_active:
            return {
                "status": "already_active",
                "activation_time": self._activation_time,
                "registered_agents": list(self._agents.keys()),
            }

        # 备份 golden config
        self._golden_config = {
            name: getattr(agent, "config", {}) or {}
            for name, agent in self._agents.items()
        }

        # 设置基准线
        if quality_baseline is not None:
            self._quality_baseline = quality_baseline

        # 日志路径
        if evolution_log_path is None:
            import os
            os.makedirs(".cache", exist_ok=True)
            evolution_log_path = ".cache/evolution_log.jsonl"
        self._evolution_log_path = evolution_log_path

        self._is_active = True
        self._activation_time = time.time()

        # 注册 AutoTrigger
        if hasattr(self, "auto_trigger") and self.auto_trigger is not None:
            self.auto_trigger.enabled = True

        # 通知已注册的 agent
        for name, agent in self._agents.items():
            if hasattr(agent, "on_evolution_activated"):
                try:
                    agent.on_evolution_activated(self)
                except Exception as exc:
                    logger.debug("[SelfEvolutionEngine] on_evolution_activated failed for agent %s: %s", name, exc)

        logger.info(
            f"Evolution activated: quality_baseline={self._quality_baseline}, "
            f"agents={list(self._agents.keys())}, "
            f"history_size={len(self._history)}, "
            f"log_path={self._evolution_log_path}"
        )

        return {
            "status": "activated",
            "activation_time": self._activation_time,
            "quality_baseline": self._quality_baseline,
            "log_path": self._evolution_log_path,
            "registered_agents": list(self._agents.keys()),
            "golden_config_backup": {
                name: len(cfg) for name, cfg in self._golden_config.items()
            },
        }

    def deactivate(self) -> dict[str, Any]:
        """
        停用自进化引擎，保留进化历史。

        Returns
        -------
        dict[str, Any]
            停用摘要，包含进化事件总数。
        """
        if not self._is_active:
            return {"status": "not_active"}

        # 关闭 AutoTrigger
        if hasattr(self, "auto_trigger") and self.auto_trigger is not None:
            self.auto_trigger.enabled = False

        self._is_active = False

        logger.info(
            f"Evolution deactivated: "
            f"events_recorded={len(self._history)}, "
            f"proposals_generated={len(self._proposals)}, "
            f"assessments_run={len(self._assessments)}"
        )

        return {
            "status": "deactivated",
            "events_recorded": len(self._history),
            "proposals_generated": len(self._proposals),
            "assessments_run": len(self._assessments),
        }

    def is_active(self) -> bool:
        """返回引擎是否已激活。"""
        return self._is_active

    def record_and_assess(
        self,
        agent_name: str,
        result: Any,
        context: dict,
    ) -> dict | None:
        """
        Record an execution result and immediately assess whether
        an evolution proposal should be generated.

        Call this after each agent.run() completes.

        Returns
        -------
        dict | None
            Evolution event if a proposal was generated and assessed.
        """
        # Extract quality score from result
        quality_score = self._extract_quality(result)

        # Check if quality is below baseline
        if quality_score >= self._quality_baseline:
            return None

        # Generate a proposal
        proposal = self._propose(agent_name, result, context, quality_score)
        if not proposal.get("proposals"):
            return None

        best_proposal = proposal["proposals"][0]
        self._proposals.append({
            "agent_name": agent_name,
            "proposal": best_proposal,
            "quality_score": quality_score,
            "timestamp": time.time(),
        })

        # Auto-assess (lightweight — no test run, just severity check)
        assessment = self._assess_lightweight(best_proposal, quality_score)

        event = EvolutionEvent(
            timestamp=time.time(),
            agent_name=agent_name,
            proposal=best_proposal,
            assessment=assessment,
            committed=False,
        )

        self._history.append(event)

        return {
            "proposal": best_proposal,
            "assessment": assessment,
            "should_commit": assessment.get("commit", False),
        }

    def _extract_quality(self, result: Any) -> float:
        """Extract quality score from agent result."""
        if hasattr(result, "score"):
            return getattr(result, "score", 0.5)
        if hasattr(result, "output") and isinstance(result.output, dict):
            return result.output.get("score", 0.5)
        return 0.5

    def propose_improvements(self, context: dict) -> dict:
        """
        Propose configuration improvements based on full execution history.

        This is a heavy operation — uses LLM to analyze all past executions
        and generate targeted improvement suggestions.
        """
        # Build history summary
        history_summary = self._build_history_summary()

        prompt = f"""作为一位 AI Agent 配置优化专家，请分析以下执行历史，提出具体的配置改进建议。

## 执行历史摘要
{history_summary}

## 当前上下文
{json.dumps(context, ensure_ascii=False, indent=2)[:1000]}

## 任务
分析历史数据，找出表现不佳的根本原因，提出具体、可执行的改进建议。

请从以下维度分析：
1. Prompt 改进：哪些指令不够清晰或缺少约束？
2. 工具配置：哪些工具组合效果不佳？
3. 迭代次数：max_iterations 是否合理？
4. 温度参数：当前 temperature 是否导致输出不稳定？
5. 输出格式：output_format 是否合适？

## 输出格式
必须为有效 JSON：
```json
{{
  "proposals": [
    {{
      "agent_name": "具体agent名称",
      "target": "prompt|temperature|max_iterations|tools|output_format",
      "issue": "当前问题描述",
      "suggestion": "具体改进建议",
      "expected_impact": "low|medium|high",
      "confidence": 0.0-1.0
    }}
  ],
  "overall_assessment": "总体评价",
  "priority_order": ["agent_name1", "agent_name2"]
}}
```"""

        try:
            response = self.gateway.generate(prompt, format_json=True)
            try:
                data = json.loads(response.response)
            except json.JSONDecodeError as e:
                logger.warning(f"propose_improvements: JSON decode error: {e}")
                return {"proposals": [], "error": str(e)}
            self._proposals.extend([
                {
                    "proposal": p,
                    "timestamp": time.time(),
                    "source": "llm_analysis",
                }
                for p in data.get("proposals", [])
            ])
            return data
        except Exception as exc:
            return {"proposals": [], "error": str(exc)}

    def assess_on_tests(
        self,
        proposal: dict,
        test_data: list[dict],
    ) -> dict:
        """
        Heavy assessment: run the proposal on test data and measure quality delta.

        Parameters
        ----------
        proposal : dict
            The proposal dict with agent_name and suggestion.
        test_data : list[dict]
            List of test cases with ground truth.

        Returns
        -------
        dict
            Assessment result with quality_delta, commit recommendation.
        """
        agent_name = proposal.get("agent_name", "")
        suggestion = proposal.get("suggestion", "")

        # Apply the proposal temporarily
        original_config = self._apply_proposal(agent_name, suggestion)

        # Run tests
        test_scores = []
        for test in test_data:
            try:
                agent = self._get_agent(agent_name)
                if agent:
                    result = agent.run(test)
                    score = self._extract_quality(result)
                    test_scores.append(score)
            except Exception:
                test_scores.append(0.0)

        # Restore original config
        if original_config:
            self._restore_config(agent_name, original_config)

        avg_score = sum(test_scores) / len(test_scores) if test_scores else 0.0
        delta = avg_score - self._quality_baseline

        assessment = {
            "proposal": proposal,
            "test_count": len(test_scores),
            "avg_score": avg_score,
            "quality_delta": delta,
            "commit": delta > 0.1,  # Commit if >10% improvement
            "confidence": len(test_scores) / 10.0,  # More tests = higher confidence
        }

        self._assessments.append(assessment)
        return assessment

    def commit(
        self,
        proposal: dict,
        assessment: dict,
        message: str = "",
    ) -> dict:
        """
        Commit an approved proposal to the agent's config.

        Stores the change in evolution history and long-term memory.

        Parameters
        ----------
        proposal : dict
            The proposal to commit.
        assessment : dict
            The assessment result (must have commit=True).
        message : str
            Optional commit message.

        Returns
        -------
        dict
            Committed configuration change.
        """
        if not assessment.get("commit", False):
            return {"error": "Assessment does not recommend committing"}

        agent_name = proposal.get("agent_name", "")
        suggestion = proposal.get("suggestion", "")

        # Backup current config before committing
        if agent_name not in self._golden_config:
            self._golden_config[agent_name] = self._get_agent_config_snapshot(agent_name)

        # Apply the change
        committed = self._apply_proposal(agent_name, suggestion)

        # If agent was not found (not registered), commit is not possible
        if committed is None:
            return {
                "error": f"Agent '{agent_name}' not found or not registered. "
                          "Call register_agent() first before committing.",
                "agent_name": agent_name,
            }

        # Record in history
        event = EvolutionEvent(
            timestamp=time.time(),
            agent_name=agent_name,
            proposal=proposal,
            assessment=assessment,
            committed=True,
            commit_message=message or f"Committed improvement: {suggestion[:50]}",
        )
        self._history.append(event)

        # Persist to long-term memory
        self.memory.store_knowledge(
            key=f"evolution:committed:{agent_name}:{len(self._history)}",
            value={
                "proposal": proposal,
                "assessment": assessment,
                "message": message,
                "timestamp": time.time(),
            },
            tags=["evolution", agent_name, "committed"],
        )

        logger.info(
            f"Evolution committed: agent={agent_name}, "
            f"proposal={proposal.get('suggestion', proposal.get('target', ''))[:50]}, "
            f"history_size={len(self._history)}"
        )

        return {
            "committed": True,
            "agent_name": agent_name,
            "change": committed,
            "event_id": len(self._history) - 1,
        }

    def rollback(self, agent_name: str, to_version: int | None = None) -> dict:
        """
        Rollback an agent to its golden config or a specific version.

        Parameters
        ----------
        agent_name : str
            The agent to rollback.
        to_version : int | None
            Rollback to a specific evolution event index.
            If None, rollback to golden config.

        Returns
        -------
        dict
            Rollback result.
        """
        if agent_name not in self._golden_config:
            return {"error": f"No golden config for agent '{agent_name}'"}

        target = (
            self._golden_config[agent_name]
            if to_version is None
            else self._get_event_snapshot(agent_name, to_version)
        )

        if target is None:
            return {"error": f"Cannot find version {to_version}"}

        self._restore_config(agent_name, target)

        # Record rollback
        rollback_event = EvolutionEvent(
            timestamp=time.time(),
            agent_name=agent_name,
            proposal={"action": "rollback"},
            assessment={"to_version": to_version},
            committed=True,
            commit_message=f"Rolled back to {'golden' if to_version is None else f'version {to_version}'}",
        )
        self._history.append(rollback_event)

        return {
            "rolled_back": True,
            "agent_name": agent_name,
            "to_version": to_version or "golden",
        }

    def get_history(self, agent_name: str | None = None) -> list[dict]:
        """Get evolution history, optionally filtered by agent."""
        if agent_name:
            return [
                {
                    "timestamp": e.timestamp,
                    "agent_name": e.agent_name,
                    "proposal": e.proposal,
                    "assessment": e.assessment,
                    "committed": e.committed,
                    "message": e.commit_message,
                }
                for e in self._history
                if e.agent_name == agent_name
            ]
        return [
            {
                "timestamp": e.timestamp,
                "agent_name": e.agent_name,
                "proposal": e.proposal,
                "assessment": e.assessment,
                "committed": e.committed,
            }
            for e in self._history
        ]

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_proposals(self, path: str | Path | None = None) -> Path:
        """Save all evolution proposals to a JSONL file."""
        from pathlib import Path

        if path is None:
            path = Path(f".cache/evolution_proposals_{self._agent_name}.jsonl")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for p in self._proposals:
                f.write(json.dumps(p) + "\n")
        logger.info(f"Saved {len(self._proposals)} proposals to {path}")
        return path

    def load_proposals(self, path: str | Path) -> int:
        """Load evolution proposals from a JSONL file."""
        from pathlib import Path

        path = Path(path)
        if not path.exists():
            logger.warning(f"Proposal file not found: {path}")
            return 0
        loaded = 0
        with open(path) as f:
            for line in f:
                try:
                    self._proposals.append(json.loads(line))
                    loaded += 1
                except json.JSONDecodeError:
                    continue
        logger.info(f"Loaded {loaded} proposals from {path}")
        return loaded

    # ── Evolution Hooks ───────────────────────────────────────────────────────

    def on_feedback_received(self, agent_name: str, feedback_text: str) -> None:
        """Hook called when human feedback is received."""
        logger.info(f"Feedback received for {agent_name}: {feedback_text[:100]}...")

    def on_checkpoint_restored(self, agent_name: str, checkpoint_id: str) -> None:
        """Hook called when a checkpoint is restored."""
        logger.info(f"Checkpoint {checkpoint_id} restored for {agent_name}")

    def stream_events(self):
        """Generator that yields EvolutionEvent objects for monitoring."""
        for event in self._history:
            yield event

    # ── Private Helpers ────────────────────────────────────────────────

    def _build_history_summary(self) -> str:
        """Build a text summary of recent evolution history."""
        recent = self._history[-10:]  # Last 10 events
        lines = []
        for e in recent:
            status = "✅ 采纳" if e.committed else "❌ 拒绝"
            lines.append(
                f"[{time.strftime('%m-%d %H:%M', time.localtime(e.timestamp))}] "
                f"{e.agent_name}: {e.proposal.get('suggestion', e.proposal.get('action', ''))[:50]} "
                f"{status}"
            )
        return "\n".join(lines) if lines else "（暂无历史记录）"

    def _propose(
        self,
        agent_name: str,
        result: Any,
        context: dict,
        quality_score: float,
    ) -> dict:
        """Generate a lightweight proposal from a failed execution."""
        quality = "差" if quality_score < 0.3 else "一般"
        feedback = getattr(result, "feedback", str(result)[:200])

        prompt = f"""分析以下 Agent 执行失败的原因，提出改进建议。

Agent: {agent_name}
质量得分: {quality} ({quality_score:.2f})
反馈信息: {feedback}

上下文: {str(context)[:500]}

请提出一条具体的改进建议（prompt/工具/参数），以 JSON 格式输出：
{{"proposals": [{{"agent_name": "{agent_name}", "target": "...", "issue": "...", "suggestion": "...", "expected_impact": "medium"}}]}}"""

        try:
            response = self.gateway.generate(prompt, format_json=True)
            return json.loads(response.response)
        except json.JSONDecodeError as e:
            logger.warning("[SelfEvolutionEngine] _propose: JSON decode error: %s", e)
            return {"proposals": []}
        except Exception as exc:
            logger.warning("[SelfEvolutionEngine] _propose: unexpected error (returning empty proposals): %s", exc)
            return {"proposals": []}

    def _assess_lightweight(self, proposal: dict, quality_score: float) -> dict:
        """
        Lightweight assessment without running tests.

        Makes a heuristic decision based on severity.
        """
        target = proposal.get("target", "")
        severity = {
            "prompt": 0.8,
            "temperature": 0.5,
            "max_iterations": 0.3,
            "tools": 0.6,
            "output_format": 0.4,
        }.get(target, 0.5)

        should_commit = (
            quality_score < 0.3 and severity >= 0.6
        ) or (
            quality_score < 0.5 and severity >= 0.8
        )

        return {
            "commit": should_commit,
            "severity": severity,
            "confidence": 0.5,  # Low confidence for lightweight
            "method": "heuristic",
        }

    def _apply_proposal(self, agent_name: str, suggestion: str) -> dict | None:
        """Apply a proposal to an agent's config. Returns backup."""
        agent = self._get_agent(agent_name)
        if not agent:
            return None

        # Snapshot original config before patching
        original = {
            "temperature": agent.config.temperature,
            "max_iterations": agent.config.max_iterations,
            "max_time_seconds": agent.config.max_time_seconds,
            "output_format": agent.config.output_format,
        }

        suggestion_lower = suggestion.lower()

        # Temperature adjustments
        if "降低温度" in suggestion or "lower temperature" in suggestion_lower:
            agent.config.temperature = max(0.1, agent.config.temperature - 0.1)
        elif "提高温度" in suggestion or "higher temperature" in suggestion_lower:
            agent.config.temperature = min(1.0, agent.config.temperature + 0.1)

        # Max iterations
        if "增加迭代" in suggestion or "more iterations" in suggestion_lower:
            agent.config.max_iterations += 1
        elif "减少迭代" in suggestion or "fewer iterations" in suggestion_lower:
            agent.config.max_iterations = max(1, agent.config.max_iterations - 1)

        # Max time seconds
        if "增加超时" in suggestion or "increase timeout" in suggestion_lower:
            agent.config.max_time_seconds = min(600, agent.config.max_time_seconds * 1.5)
        elif "减少超时" in suggestion or "decrease timeout" in suggestion_lower:
            agent.config.max_time_seconds = max(10, agent.config.max_time_seconds / 1.5)

        # Output format
        for fmt in ("json", "markdown", "text"):
            if fmt in suggestion_lower and agent.config.output_format != fmt:
                agent.config.output_format = fmt

        return original

    def _restore_config(self, agent_name: str, snapshot: dict) -> None:
        """Restore an agent's config from a snapshot."""
        agent = self._get_agent(agent_name)
        if not agent or not snapshot:
            return
        if "temperature" in snapshot:
            agent.config.temperature = snapshot["temperature"]
        if "max_iterations" in snapshot:
            agent.config.max_iterations = snapshot["max_iterations"]
        if "max_time_seconds" in snapshot:
            agent.config.max_time_seconds = snapshot["max_time_seconds"]
        if "output_format" in snapshot:
            agent.config.output_format = snapshot["output_format"]

    def _get_agent(self, name: str):
        """Get a registered agent by name. Returns None if not found."""
        return self._agents.get(name)

    def register_agent(self, name: str, agent: Any) -> None:
        """
        Register an agent for this evolution engine.

        This should be called by the orchestrator after initialization
        to avoid circular import issues.

        Parameters
        ----------
        name : str
            Agent name
        agent : Any
            Agent instance
        """
        if not hasattr(self, "_agents"):
            self._agents: dict[str, Any] = {}
        self._agents[name] = agent
        if self._is_active:
            self._golden_config[name] = getattr(agent, "config", {}) or {}

    def _get_agent_config_snapshot(self, agent_name: str) -> dict:
        """Get a snapshot of agent config for rollback."""
        agent = self._get_agent(agent_name)
        if not agent:
            return {}
        return {
            "temperature": agent.config.temperature,
            "max_iterations": agent.config.max_iterations,
            "output_format": agent.config.output_format,
        }

    def _get_event_snapshot(self, agent_name: str, event_index: int) -> dict | None:
        """Get config snapshot from a specific history event."""
        if 0 <= event_index < len(self._history):
            event = self._history[event_index]
            return self._get_agent_config_snapshot(event.agent_name)
        return None


# ════════════════════════════════════════════════════════════════════════════════════════
# P1-2: Self-Evolution Auto-Trigger Integration
# ════════════════════════════════════════════════════════════════════════════════════════


class SelfEvolutionAutoTrigger:
    """
    自我进化自动触发器

    功能：
    1. 自动监听会话执行事件
    2. 根据质量阈值自动触发进化评估
    3. 支持连续失败后自动回滚
    4. 与 ResearchSession 深度集成

    使用方法：
        trigger = SelfEvolutionAutoTrigger(evolution_engine)
        # 在任务执行后自动调用
        trigger.on_task_complete(agent_name, result, context)
    """

    def __init__(
        self,
        evolution_engine: SelfEvolutionEngine,
        quality_threshold: float = 0.7,
        consecutive_fail_threshold: int = 3,
        auto_rollback_threshold: int = 5,
    ):
        self.engine = evolution_engine
        self.quality_threshold = quality_threshold
        self.consecutive_fail_threshold = consecutive_fail_threshold
        self.auto_rollback_threshold = auto_rollback_threshold

        # 连续失败计数器（带锁保护）
        import threading
        self._lock = threading.Lock()
        self._consecutive_fails: dict[str, int] = {}
        self._total_tasks: dict[str, int] = {}

    def on_task_complete(
        self,
        agent_name: str,
        result: Any,
        context: dict,
    ) -> dict | None:
        """
        任务完成回调 - 自动触发进化评估（线程安全）

        Parameters
        ----------
        agent_name : str
            执行的Agent名称
        result : Any
            Agent执行结果
        context : dict
            执行上下文

        Returns
        -------
        dict | None
            进化事件（如果有）
        """
        # 提取质量分数（在锁外执行，减少锁持有时间）
        quality_score = self.engine._extract_quality(result)
        is_success = quality_score >= self.quality_threshold

        evolution_event = None

        with self._lock:
            # 更新计数器
            self._total_tasks[agent_name] = self._total_tasks.get(agent_name, 0) + 1

            # 更新连续失败计数
            if is_success:
                self._consecutive_fails[agent_name] = 0
            else:
                self._consecutive_fails[agent_name] = self._consecutive_fails.get(agent_name, 0) + 1

            # 检查是否需要自动回滚
            if self._consecutive_fails.get(agent_name, 0) >= self.auto_rollback_threshold:
                self._consecutive_fails[agent_name] = 0  # 重置计数
                rollback_result = self.engine.rollback(agent_name)
                evolution_event = {
                    "type": "auto_rollback",
                    "agent_name": agent_name,
                    "consecutive_fails": self.auto_rollback_threshold,
                    "rollback_result": rollback_result,
                }
            elif not is_success:
                # 触发进化评估
                evolution_event = self.engine.record_and_assess(agent_name, result, context)

                if evolution_event and evolution_event.get("should_commit"):
                    # 自动提交改进建议（在锁外执行，避免长时间持有锁）
                    evolution_event["_pending_commit"] = True

        # 在锁外执行可能导致长时间阻塞的操作
        if evolution_event and evolution_event.get("_pending_commit"):
            del evolution_event["_pending_commit"]
            commit_result = self.engine.commit(
                proposal=evolution_event.get("proposal"),
                assessment=evolution_event.get("assessment"),
                message=f"Auto-evolved from task completion. Quality: {quality_score:.2f}",
            )
            evolution_event["commit_result"] = commit_result

        return evolution_event

    def on_session_complete(
        self,
        session_id: str,
        results: list[dict],
    ) -> dict:
        """
        会话完成回调 - 汇总进化统计

        Parameters
        ----------
        session_id : str
            会话ID
        results : list[dict]
            所有任务执行结果

        Returns
        -------
        dict
            进化统计摘要
        """
        evolution_stats = {
            "session_id": session_id,
            "total_tasks": len(results),
            "agent_stats": {},
            "evolution_events": [],
        }

        for result in results:
            agent_name = result.get("agent_name", "unknown")
            if agent_name not in evolution_stats["agent_stats"]:
                evolution_stats["agent_stats"][agent_name] = {
                    "total": 0,
                    "failed": 0,
                    "evolved": 0,
                }

            evolution_stats["agent_stats"][agent_name]["total"] += 1
            if not result.get("success", True):
                evolution_stats["agent_stats"][agent_name]["failed"] += 1
            if result.get("evolved", False):
                evolution_stats["agent_stats"][agent_name]["evolved"] += 1
                evolution_stats["evolution_events"].append({
                    "agent": agent_name,
                    "proposal": result.get("proposal", {}),
                })

        return evolution_stats

    def get_stats(self) -> dict:
        """获取当前进化统计"""
        return {
            "total_agents": len(self._total_tasks),
            "consecutive_fails": self._consecutive_fails.copy(),
            "history_count": len(self.engine._history),
            "committed_count": sum(1 for e in self.engine._history if e.committed),
            "proposals_count": len(self.engine._proposals),
        }


class SessionEvolutionIntegration:
    """
    ResearchSession 与 SelfEvolutionEngine 的集成

    在 ResearchSession 执行任务后自动调用进化评估
    """

    def __init__(self, session, evolution_engine: SelfEvolutionEngine):
        self.session = session
        self.engine = evolution_engine
        self.auto_trigger = SelfEvolutionAutoTrigger(evolution_engine)

    def wrap_execute_task(self, original_execute_task):
        """
        包装 ResearchSession._execute_single_task 方法

        使用方法：
            integration = SessionEvolutionIntegration(session, evolution_engine)
            integration.wrap_execute_task()
        """
        def wrapped_execute(*args, **kwargs):
            # 执行原始方法
            result = original_execute_task(*args, **kwargs)

            # 自动触发进化评估
            if hasattr(result, "output") and hasattr(result, "iterations"):
                agent_name = kwargs.get("agent_name", "unknown")
                evolution_event = self.auto_trigger.on_task_complete(
                    agent_name=agent_name,
                    result=result,
                    context=kwargs.get("context", {}),
                )

                if evolution_event:
                    # 记录进化事件到session
                    self.session.memory.push(
                        task=f"evolution_event:{agent_name}",
                        result=evolution_event,
                        metadata={"agent_name": agent_name, "unit_type": "evolution"},
                    )

            return result

        return wrapped_execute
