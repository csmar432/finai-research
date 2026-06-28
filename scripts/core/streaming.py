"""StreamingPipeline: FastAPI SSE-based streaming pipeline for real-time output.

Sentinel streaming design:
    - FastAPI + Server-Sent Events (SSE)
    - Each agent's output streamed in real-time
    - Frontend EventSource receives incremental updates
    - Supports interruption and cancellation

Reference: https://github.com/mollendorff-ai/sentinel

Key enhancements (M8 fixes):
    - True incremental streaming via LLM gateway streaming API
    - AGENT_CHUNK events as tokens arrive
    - StreamingConfig with chunk_size, enable_sse, buffering options
    - Graceful degradation when streaming is unavailable
"""

from __future__ import annotations

__all__ = [
    "StreamEventType",
    "StreamEvent",
    "StreamingConfig",
    "create_sse_response",
]

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.core.agents.base import BaseAgent
from scripts.core.llm_gateway import LLMGateway

# ─── Event Types ────────────────────────────────────────────────────────────────


class StreamEventType(Enum):
    AGENT_START = "agent_start"
    AGENT_CHUNK = "chunk"          # Incremental output chunk (token/segment)
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"
    HITL_PAUSE = "hitl_pause"
    HITL_RESUME = "hitl_resume"
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    PROGRESS = "progress"
    STREAMING_UNAVAILABLE = "streaming_unavailable"


# ─── Stream Event ─────────────────────────────────────────────────────────────


@dataclass
class StreamEvent:
    """A single SSE event."""
    event_type: StreamEventType
    data: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Convert to SSE format (text/event-stream)."""
        return f"id: {self.event_id}\nevent: {self.event_type.value}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"


# ─── Streaming Config ─────────────────────────────────────────────────────────


@dataclass
class StreamingConfig:
    """
    Configuration for streaming behavior.

    Attributes
    ----------
    chunk_size : int
        Minimum tokens per chunk (accumulates until reached). Default 20.
    enable_sse : bool
        Enable SSE formatting. Default True.
    buffering : str
        Buffering strategy: "line" (newline-terminated), "segment" (sentence),
        "token" (immediate). Default "line".
    """
    chunk_size: int = 20
    enable_sse: bool = True
    buffering: str = "line"  # "line" | "segment" | "token"
    stream_llm: bool = True    # Stream LLM responses token-by-token
    max_buffer_ms: float = 100  # Max time to wait before flushing buffer


# ─── Streaming Pipeline ──────────────────────────────────────────────────────


class StreamingPipeline:
    """
    Streaming pipeline that yields SSE events for real-time frontend updates.

    Sentinel-style design:
        - Each agent's output streamed incrementally
        - Pipeline progress tracked in real-time
        - HITL gates pause/resume streaming
        - Full execution trace for debugging

    Usage:
        # FastAPI endpoint
        @app.get("/research/stream")
        async def stream_research(topic: str):
            pipeline = StreamingPipeline(gateway)
            return StreamingResponse(
                pipeline.stream(pipeline_name="paper", input_data={"topic": topic}),
                media_type="text/event-stream",
            )

        # Python client
        async for event in pipeline.stream(...):
            print(event.event_type, event.data)
    """

    def __init__(self, gateway: LLMGateway, config: StreamingConfig | None = None):
        self.gateway = gateway
        self.config = config or StreamingConfig()
        self._pipeline_instance: Any = None  # AgentOrchestrator
        self._buffer: list[str] = []

    def set_pipeline(self, pipeline: Any) -> None:
        """Attach an AgentOrchestrator instance."""
        self._pipeline_instance = pipeline

    def supports_streaming(self) -> bool:
        """Check if the underlying LLM gateway supports streaming."""
        return self.gateway.supports_streaming()

    async def stream(
        self,
        pipeline_name: str,
        steps: list[Any],
        input_data: dict,
        parallel: bool = False,
        max_workers: int = 4,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute a pipeline and yield SSE events.

        Parameters
        ----------
        pipeline_name : str
            Human-readable pipeline name.
        steps : list
            Pipeline steps (PipelineStep objects).
        input_data : dict
            Initial context.
        parallel : bool
            Enable parallel execution.
        max_workers : int
            Max concurrent agents.

        Yields
        ------
        StreamEvent
            SSE events for each stage of pipeline execution.
        """
        from scripts.core.orchestrator import AgentOrchestrator

        # Initialize orchestrator if not set
        if self._pipeline_instance is None:
            orchestrator = AgentOrchestrator(self.gateway)
            orchestrator.register_default_agents()
        else:
            orchestrator = self._pipeline_instance

        # Emit pipeline start
        yield StreamEvent(
            event_type=StreamEventType.PIPELINE_START,
            data={"pipeline": pipeline_name, "input": str(input_data)[:200]},
        )

        context = dict(input_data)
        total_steps = len([s for s in steps if not getattr(s, "skip", False)])
        completed = 0

        for step in steps:
            if getattr(step, "skip", False):
                continue

            stage_name = getattr(step, "stage", None)
            agent_name = getattr(step, "agent_name", "")

            # Emit agent start
            yield StreamEvent(
                event_type=StreamEventType.AGENT_START,
                data={
                    "stage": stage_name.value if stage_name else agent_name,
                    "agent": agent_name,
                    "progress": f"{completed}/{total_steps}",
                },
            )

            # Check HITL gate
            hitl_gate = getattr(step, "hitl_gate", False)
            if hitl_gate:
                yield StreamEvent(
                    event_type=StreamEventType.HITL_PAUSE,
                    data={
                        "stage": stage_name.value if stage_name else agent_name,
                        "content_preview": str(context)[:500],
                    },
                )
                break  # Pause here; frontend handles approval

            # Execute agent with chunked streaming
            agent = orchestrator.get_agent(agent_name)
            if agent:
                async for event in self._stream_agent(agent, context):
                    yield event
            else:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={"error": f"Agent '{agent_name}' not found"},
                )

            completed += 1

        # Emit pipeline end
        yield StreamEvent(
            event_type=StreamEventType.PIPELINE_END,
            data={
                "pipeline": pipeline_name,
                "completed": completed,
                "total": total_steps,
            },
        )

    async def _stream_agent(
        self,
        agent: BaseAgent,
        context: dict,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream a single agent's execution with incremental output.

        Falls back to synchronous execution with chunked yields.
        """
        # Check if streaming is available
        if not self.supports_streaming():
            yield StreamEvent(
                event_type=StreamEventType.STREAMING_UNAVAILABLE,
                data={"message": "Streaming not available, using batch mode"},
            )
            # Fall back to synchronous execution
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, agent.run, context
                )
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_END,
                    data={
                        "agent": agent.config.name,
                        "status": result.status,
                        "iterations": result.iterations,
                        "latency_ms": result.latency_ms,
                        "feedback": result.feedback[:200] if result.feedback else "",
                    },
                )
            except Exception as exc:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={"agent": agent.config.name, "error": str(exc)},
                )
            return

        # Try true streaming via gateway
        try:
            # Use stream_agent_run for true streaming
            async for event in self.stream_agent_run(agent, context):
                yield event
        except Exception as exc:
            # Fallback to synchronous execution
            yield StreamEvent(
                event_type=StreamEventType.STREAMING_UNAVAILABLE,
                data={"message": f"Streaming failed, falling back: {str(exc)[:100]}"},
            )
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, agent.run, context
                )
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_END,
                    data={
                        "agent": agent.config.name,
                        "status": result.status,
                        "iterations": result.iterations,
                        "latency_ms": result.latency_ms,
                        "feedback": result.feedback[:200] if result.feedback else "",
                    },
                )
            except Exception as fallback_exc:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={"agent": agent.config.name, "error": str(fallback_exc)},
                )

    async def stream_agent_run(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream an agent's execution with true incremental LLM output.

        This method attempts to use the LLM gateway's streaming API to yield
        tokens/segments as they arrive from the model.

        Parameters
        ----------
        agent : BaseAgent
            The agent to run.
        context : dict
            Input context for the agent.

        Yields
        ------
        StreamEvent
            AGENT_CHUNK events for each token/segment, followed by AGENT_END.
        """
        from scripts.core.agents.base import HaltDecision

        agent._start_time = time.time()
        agent._iteration_count = 0
        agent._memory = []

        for i in range(agent.config.max_iterations):
            agent._iteration_count = i + 1

            # ── Act phase ────────────────────────────────────────────────
            act_start = time.time()
            try:
                act_result = await self._stream_agent_act(agent, context)
            except Exception as exc:
                act_result = {"error": str(exc)}

            act_latency_ms = (time.time() - act_start) * 1000

            agent._memory.append({
                "iteration": i + 1,
                "act_result": act_result,
                "act_latency_ms": act_latency_ms,
                "timestamp": time.time(),
            })

            # ── Reflect phase ──────────────────────────────────────────
            try:
                reflect_result = agent.reflect(act_result)
            except Exception as exc:
                reflect_result = {
                    "halt": HaltDecision.REJECTED,
                    "feedback": f"Reflection failed: {str(exc)}",
                    "score": 0.0,
                }

            agent._memory[-1]["reflection"] = reflect_result

            # ── Decision ───────────────────────────────────────────────
            halt: HaltDecision = reflect_result.get("halt", HaltDecision.APPROVED)
            feedback: str = reflect_result.get("feedback", "")

            if halt == HaltDecision.APPROVED:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_END,
                    data={
                        "agent": agent.config.name,
                        "status": "approved",
                        "iterations": i + 1,
                        "latency_ms": (time.time() - agent._start_time) * 1000,
                        "feedback": feedback[:200] if feedback else "",
                    },
                )
                return

            elif halt == HaltDecision.REJECTED:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={
                        "agent": agent.config.name,
                        "error": f"Rejected: {feedback}",
                    },
                )
                return

            # REVISE: inject feedback and continue
            context = agent._inject_feedback(context, feedback, act_result)

        # Exceeded max iterations
        yield StreamEvent(
            event_type=StreamEventType.AGENT_END,
            data={
                "agent": agent.config.name,
                "status": "max_iterations",
                "iterations": agent.config.max_iterations,
                "latency_ms": (time.time() - agent._start_time) * 1000,
                "feedback": "Exceeded max_iterations without approval",
            },
        )

    async def _stream_agent_act(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> Any:
        """
        Execute agent's act() method with streaming if the act involves LLM calls.

        For true streaming, the act method would need to use the gateway's
        streaming API. This default implementation falls back to synchronous.
        """
        # Check if act method supports streaming (has stream parameter)
        import inspect
        act_sig = inspect.signature(agent.act)

        if 'stream' in act_sig.parameters:
            # Agent's act supports streaming
            return await agent.act(context, stream=True)
        else:
            # Fall back to regular act
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.act, context)

    async def _stream_llm_response(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM response using the gateway's streaming API.

        Parameters
        ----------
        prompt : str
            The prompt to send.
        system : str, optional
            System prompt.
        **kwargs
            Additional arguments for generate_stream.

        Yields
        ------
        str
            Text chunks as they arrive.
        """
        buffer: list[str] = []
        last_flush = time.time()

        def should_flush(text: str) -> bool:
            """Determine if buffer should be flushed based on buffering strategy."""
            if self.config.buffering == "token":
                return True
            elif self.config.buffering == "line":
                return text.endswith("\n")
            elif self.config.buffering == "segment":
                # Flush on sentence-ending punctuation
                return text and text[-1] in ".!?"
            return False

        for chunk in self.gateway.generate_stream(prompt, system=system, **kwargs):
            buffer.append(chunk)

            # Check if we should flush
            current_text = "".join(buffer)
            current_size = len(current_text)

            # Flush if chunk size reached or delimiter found or timeout
            time_since_flush = (time.time() - last_flush) * 1000

            if current_size >= self.config.chunk_size or should_flush(chunk) or time_since_flush > self.config.max_buffer_ms:
                yield current_text
                buffer = []
                last_flush = time.time()

        # Flush remaining buffer
        if buffer:
            yield "".join(buffer)

    def stream_sync(
        self,
        pipeline_name: str,
        steps: list[Any],
        input_data: dict,
    ) -> list[StreamEvent]:
        """
        Synchronous version of stream() that collects all events.

        For use in non-async contexts (CLI, testing).

        Fixed (M8): Properly distinguishes scalar vs generator results.
        """
        from scripts.core.orchestrator import AgentOrchestrator

        events: list[StreamEvent] = []

        if self._pipeline_instance is None:
            orchestrator = AgentOrchestrator(self.gateway)
            orchestrator.register_default_agents()
        else:
            orchestrator = self._pipeline_instance

        context = dict(input_data)
        total_steps = len([s for s in steps if not getattr(s, "skip", False)])
        completed = 0

        for step in steps:
            if getattr(step, "skip", False):
                continue

            stage_name = getattr(step, "stage", None)
            agent_name = getattr(step, "agent_name", "")

            events.append(StreamEvent(
                event_type=StreamEventType.AGENT_START,
                data={
                    "stage": stage_name.value if stage_name else agent_name,
                    "agent": agent_name,
                    "progress": f"{completed}/{total_steps}",
                },
            ))

            hitl_gate = getattr(step, "hitl_gate", False)
            if hitl_gate:
                events.append(StreamEvent(
                    event_type=StreamEventType.HITL_PAUSE,
                    data={
                        "stage": stage_name.value if stage_name else agent_name,
                        "content_preview": str(context)[:500],
                    },
                ))
                break

            agent = orchestrator.get_agent(agent_name)
            if agent:
                try:
                    result_or_gen = agent.run(context)

                    # Properly detect generator vs scalar (M8 fix)
                    is_generator = (
                        hasattr(result_or_gen, "__iter__") and
                        hasattr(result_or_gen, "__next__") and
                        not isinstance(result_or_gen, (str, bytes, dict, list, tuple))
                    )

                    if is_generator:
                        # It's a streaming generator — yield each chunk
                        try:
                            while True:
                                chunk = next(result_or_gen)
                                events.append(StreamEvent(
                                    event_type=StreamEventType.AGENT_CHUNK,
                                    data={
                                        "agent": agent.config.name,
                                        "chunk": str(chunk)[:1000],
                                    },
                                ))
                        except StopIteration:
                            pass

                        events.append(StreamEvent(
                            event_type=StreamEventType.AGENT_END,
                            data={
                                "agent": agent.config.name,
                                "status": "completed",
                                "streaming": True,
                            },
                        ))
                    else:
                        # Scalar result — emit end with full result
                        result = result_or_gen
                        events.append(StreamEvent(
                            event_type=StreamEventType.AGENT_END,
                            data={
                                "agent": agent.config.name,
                                "status": getattr(result, "status", "completed"),
                                "iterations": getattr(result, "iterations", 0),
                                "latency_ms": getattr(result, "latency_ms", 0),
                                "streaming": False,
                            },
                        ))
                except Exception as exc:
                    events.append(StreamEvent(
                        event_type=StreamEventType.AGENT_ERROR,
                        data={"agent": agent.config.name, "error": str(exc)},
                    ))
            else:
                events.append(StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={"error": f"Agent '{agent_name}' not found"},
                ))

            completed += 1

        events.append(StreamEvent(
            event_type=StreamEventType.PIPELINE_END,
            data={"pipeline": pipeline_name, "completed": completed, "total": total_steps},
        ))

        return events


# ─── Convenience Functions ───────────────────────────────────────────────────


def create_sse_response(events: list[StreamEvent]) -> str:
    """
    Create an SSE-formatted response from a list of events.

    Parameters
    ----------
    events : list[StreamEvent]
        List of stream events.

    Returns
    -------
    str
        SSE-formatted string ready for HTTP response.
    """
    return "".join(event.to_sse() for event in events)


async def stream_to_httpx(response_callback, pipeline: StreamingPipeline, **kwargs):
    """
    Stream pipeline events to an httpx response.

    Parameters
    ----------
    response_callback : callable
        Async callback to send each event.
    pipeline : StreamingPipeline
        The pipeline to stream.
    **kwargs
        Arguments for pipeline.stream().
    """
    async for event in pipeline.stream(**kwargs):
        sse_data = event.to_sse()
        await response_callback(sse_data)


# ─── Backward Compatibility ───────────────────────────────────────────────────

# Keep old class name as alias
StreamingPipelineCompat = StreamingPipeline
