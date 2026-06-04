"""BaseAgent: Abstract base class for all professional agents.

Follows the PaperOrchestra / DeepResearchAgent pattern:
    act() → reflect() → (revise) → act() ... → output

The run() method implements the standard agent loop:
    1. Act: Execute the agent's primary behavior
    2. Reflect: Evaluate output quality, decide if revision is needed
    3. Revise: Apply feedback and re-act if needed
    4. Remember: Store results in memory

Each agent is a role-specialized unit with:
    - config: AgentConfig (name, role, goal, backstory, allowed_tools)
    - gateway: LLMGateway for LLM calls
    - _iteration_count: Tracks iterations to prevent infinite loops
    - _memory: Session-level memory of all attempts
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.core.llm_gateway import LLMCallResult, LLMGateway

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────────


class HaltDecision(Enum):
    """
    Result of reflect() — determines what happens next in the agent loop.

    APPROVED: Output is good enough, proceed to next stage
    REVISE: Output needs revision, apply feedback and re-act
    REJECTED: Critical failure, abort or escalate
    """
    APPROVED = "approved"
    REVISE = "revise"
    REJECTED = "rejected"


# ─── Config ───────────────────────────────────────────────────────────────────


@dataclass
class AgentConfig:
    """
    Configuration for a single professional agent.

    PaperOrchestra-style role definition — each agent has a distinct
    identity that shapes its behavior across all interactions.
    """
    name: str                          # Unique identifier: "outline", "lit_review"
    role: str                          # Role title: "论文大纲设计专家"
    goal: str                          # Primary objective
    backstory: str                      # Detailed background for LLM context
    allowed_tools: list[str] = field(default_factory=list)  # Tool whitelist
    max_iterations: int = 5           # Hard limit to prevent infinite loops
    max_time_seconds: float = 120.0   # Global time limit to prevent runaway agents
    max_memory_entries: int = 20     # Cap on _memory entries; oldest are pruned
    temperature: float = 0.7          # LLM sampling temperature
    llm_model: str | None = None   # Override default model
    output_format: str = "text"       # "text" | "json" | "markdown"


@dataclass
class AgentResult:
    """
    Structured output from an agent's act() or run() call.

    Attributes
    ----------
    status : str
        "success" | "approved" | "revised" | "max_iterations" | "error"
    output : Any
        The agent's output (text, dict, etc.)
    stage : PipelineStage | None
        The pipeline stage this result belongs to (used by orchestrator)
    iterations : int
        Number of act() calls made
    latency_ms : float
        Total execution time
    halted_by : HaltDecision | None
        Why the agent stopped (if applicable)
    feedback : str
        Natural language feedback from reflect()
    reflections : list[dict]
        All reflect() results across iterations
    timestamp : float
        Unix timestamp of completion
    """
    status: str
    output: Any = None
    stage: str | None = None
    iterations: int = 0
    latency_ms: float = 0.0
    halted_by: HaltDecision | None = None
    feedback: str = ""
    reflections: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    tokens_used: int = 0


@dataclass
class CancellationToken:
    """
    Cancellation token for agent run() cancellation.

    Usage:
        token = CancellationToken()
        agent.run(input_data, cancel_token=token)
        # In another thread:
        token.cancel("user requested stop")
    """
    cancelled: bool = False
    reason: str = ""

    def cancel(self, reason: str = ""):
        self.cancelled = True
        self.reason = reason

    def raise_if_cancelled(self):
        if self.cancelled:
            raise AgentCancelledError(f"Agent cancelled: {self.reason}")


class AgentCancelledError(Exception):
    """Raised when an agent run() is cancelled via CancellationToken."""
    pass


# ─── BaseAgent ─────────────────────────────────────────────────────────────────


class BaseAgent(ABC):
    """
    Abstract base class for all professional agents.

    Subclasses must implement:
        act(context)     — Primary agent behavior
        reflect(result)  — Evaluate output and decide next step

    The run() method implements the standard PaperOrchestra-style loop:
        act → reflect → (revise) → act → ... → approved

    Example:
        config = AgentConfig(name="outline", role="...", goal="...", backstory="...")
        agent = OutlineAgent(config, gateway)
        result = agent.run({"topic": "LLM在金融中的应用", "venue": "JFE"})
        print(result.output)  # Structured outline JSON
    """

    def __init__(self, config: AgentConfig, gateway: LLMGateway):
        self.config = config
        self.gateway = gateway
        self._iteration_count = 0
        self._memory: list[dict] = []
        self._start_time: float = 0.0

        # Register this agent with the gateway's tool-whitelist registry so that
        # allowed_tools enforcement is active for all tool calls made by this agent.
        self.gateway.register_agent(config.name, config.allowed_tools)

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any],
            cancel_token: CancellationToken | None = None) -> AgentResult:
        """
        Execute the standard agent loop: act → reflect → (revise) → output.

        Parameters
        ----------
        input_data : dict
            Input context passed to act(). Typical keys:
            - topic, venue, template, idea, experimental_log, draft, ...
        cancel_token : CancellationToken | None
            Optional cancellation token to allow external cancellation of the run.
            Checked at iteration start and again after each act+reflect cycle.

        Returns
        -------
        AgentResult
            Structured result with status, output, iterations, and feedback.
        """
        cancel_token = cancel_token if cancel_token is not None else CancellationToken()
        self._start_time = time.time()
        self._iteration_count = 0
        self._memory = []
        self._total_tokens = 0

        for i in range(self.config.max_iterations):
            self._iteration_count = i + 1

            # Check cancellation at iteration start
            cancel_token.raise_if_cancelled()

            # Check global time limit
            elapsed = time.time() - self._start_time
            if elapsed >= self.config.max_time_seconds:
                latency_ms = elapsed * 1000
                return AgentResult(
                    status="timeout",
                    output=self._memory[-1]["act_result"] if self._memory else None,
                    iterations=i + 1,
                    latency_ms=latency_ms,
                    halted_by=HaltDecision.REVISE,
                    feedback=f"Agent exceeded max time ({self.config.max_time_seconds}s)",
                    reflections=[self._memory[j]["reflection"] for j in range(len(self._memory))],
                    tokens_used=self._total_tokens,
                )

            # ── Act ──────────────────────────────────────────────────────
            act_start = time.time()
            try:
                act_result = self.act(input_data)
            except Exception as exc:
                logger.error(f"{self.config.name} act() failed: {exc}")
                act_result = {"error": str(exc)}

            act_latency_ms = (time.time() - act_start) * 1000

            # Accumulate tokens from act result if available
            if isinstance(act_result, dict) and "tokens_used" in act_result:
                self._total_tokens += act_result["tokens_used"]
            elif hasattr(act_result, "tokens_used"):
                self._total_tokens += act_result.tokens_used

            # Store in memory
            self._memory.append({
                "iteration": i + 1,
                "act_result": act_result,
                "act_latency_ms": act_latency_ms,
                "timestamp": time.time(),
            })
            # Prune oldest entries if memory exceeds cap
            if len(self._memory) > self.config.max_memory_entries:
                self._memory = self._memory[-self.config.max_memory_entries:]

            # ── Reflect ────────────────────────────────────────────────
            try:
                reflect_result = self.reflect(act_result)
            except Exception as exc:
                logger.error(f"{self.config.name} reflect() failed: {exc}")
                # Return a default rejection if reflection fails
                reflect_result = {
                    "halt": HaltDecision.REJECTED,
                    "feedback": f"Reflection failed: {str(exc)}",
                    "score": 0.0,
                }

            # Store reflection
            self._memory[-1]["reflection"] = reflect_result

            # Check cancellation after act+reflect (allows at least one meaningful step)
            cancel_token.raise_if_cancelled()

            # ── Decision ────────────────────────────────────────────────
            halt: HaltDecision = reflect_result.get("halt", HaltDecision.APPROVED)
            feedback: str = reflect_result.get("feedback", "")

            if halt == HaltDecision.APPROVED:
                latency_ms = (time.time() - self._start_time) * 1000
                return AgentResult(
                    status="approved",
                    output=act_result,
                    iterations=i + 1,
                    latency_ms=latency_ms,
                    halted_by=HaltDecision.APPROVED,
                    feedback=feedback,
                    tokens_used=self._total_tokens,
                )

            elif halt == HaltDecision.REJECTED:
                latency_ms = (time.time() - self._start_time) * 1000
                return AgentResult(
                    status="error",
                    output=act_result,
                    iterations=i + 1,
                    latency_ms=latency_ms,
                    halted_by=HaltDecision.REJECTED,
                    feedback=feedback,
                    reflections=[self._memory[j]["reflection"] for j in range(len(self._memory))],
                    tokens_used=self._total_tokens,
                )

            # REVISE: inject feedback and continue
            input_data = self._inject_feedback(input_data, feedback, act_result)

        # Exceeded max iterations
        latency_ms = (time.time() - self._start_time) * 1000
        return AgentResult(
            status="max_iterations",
            output=self._memory[-1]["act_result"] if self._memory else None,
            iterations=self.config.max_iterations,
            latency_ms=latency_ms,
            halted_by=HaltDecision.REVISE,
            feedback="Exceeded max_iterations without approval",
            reflections=[self._memory[j]["reflection"] for j in range(len(self._memory))],
            tokens_used=self._total_tokens,
        )

    @abstractmethod
    def act(self, context: dict[str, Any]) -> Any:
        """
        Execute the agent's primary behavior.

        Parameters
        ----------
        context : dict
            Input context (topic, venue, previous results, feedback, etc.)

        Returns
        -------
        Any
            Agent output (typically dict or str).
        """
        ...

    @abstractmethod
    def reflect(self, act_result: Any) -> dict[str, Any]:
        """
        Evaluate act() output and decide next step.

        Parameters
        ----------
        act_result : Any
            Output from the most recent act() call.

        Returns
        -------
        dict
            {
                "halt": HaltDecision.APPROVED | REVISE | REJECTED,
                "feedback": str,          # Natural language feedback
                "score": float | None,   # Optional quality score 0-1
                "flags": list[str],       # Quality flags (e.g. "missing_citations")
            }
        """
        ...

    # ── Internal Helpers ───────────────────────────────────────────────────

    def _inject_feedback(self, context: dict, feedback: str, act_result: Any) -> dict:
        """
        Inject reflection feedback into context for the next act() call.

        Default implementation adds "feedback" and "previous_output" keys.
        Keeps only the last 5 feedback entries to prevent unbounded context growth.
        Subclasses can override for domain-specific injection logic.
        """
        # Prune feedback history if it exceeds 5 entries to prevent unbounded growth
        history: list = context.get("_feedback_history", [])
        history.append({"feedback": feedback, "output": str(act_result)[:500]})
        if len(history) > 5:
            history = history[-5:]
        return {
            **context,
            "_feedback_history": history,
            "feedback": feedback,
            "previous_output": act_result,
        }

    def _generate(
        self,
        prompt: str,
        system: str | None = None,
        format_json: bool = False,
    ) -> LLMCallResult:
        """
        Convenience wrapper around gateway.generate().

        Applies agent's config (temperature, model, tools) and optionally
        forces JSON format.
        """
        system_prompt = system or self.config.backstory

        if format_json or self.config.output_format == "json":
            prompt = f"{prompt}\n\n请以 JSON 格式输出，不要包含 Markdown 代码块标记。"

        return self.gateway.generate(
            prompt=prompt,
            system=system_prompt,
            model=self.config.llm_model,
            temperature=self.config.temperature,
        )

    def _parse_json_response(self, response: str) -> dict | list:
        """
        Parse JSON from LLM response, handling common formatting issues.
        """
        text = response.strip()

        # Remove markdown code fences
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find the first JSON object/list in the text
            start = text.find("{")
            if start == -1:
                start = text.find("[")
            if start != -1:
                # Find matching close brace/bracket
                bracket = text[start]
                close = "}" if bracket == "{" else "]"
                depth = 0
                for i, ch in enumerate(text[start:], start):
                    if ch == bracket:
                        depth += 1
                    elif ch == close:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start:i + 1])
                            except json.JSONDecodeError:
                                pass
            raise ValueError(f"Cannot parse JSON from response: {response[:200]}")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.config.name!r}, iterations={self._iteration_count})"
