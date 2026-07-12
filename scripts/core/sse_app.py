"""FastAPI SSE Streaming Server for Research Pipeline.

Production-quality FastAPI app that exposes SSE endpoints for real-time
pipeline execution. Integrates StreamingPipeline with AgentOrchestrator
to stream events as Server-Sent Events.

Usage:
    uvicorn scripts.core.sse_app:app --reload --port 8000

Endpoints:
    GET  /health                          — Health check
    GET  /pipeline/stream/{pipeline_name} — Stream pipeline as SSE
    GET  /pipeline/presets               — List available pipeline presets
    POST /pipeline/hitl/approve          — Approve HITL gate
    POST /pipeline/hitl/reject           — Reject HITL gate
"""

from __future__ import annotations

__all__ = [
    "PipelinePreset",
    "HITLGateState",
    "HITLActionRequest",
    "get_paper_pipeline_steps",
    "get_research_pipeline_steps",
    "get_financial_report_steps",
]

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from scripts.core.orchestrator import AgentOrchestrator, PipelineStage, PipelineStep
from scripts.core.streaming import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)

# ─── App Setup ───────────────────────────────────────────────────────────────


app = FastAPI(
    title="Research Pipeline SSE API",
    version="1.0.0",
    description=(
        "Real-time streaming API for the paper/research pipeline. "
        "Streams SSE events as pipeline stages execute, enabling live "
        "frontend updates without polling."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pipeline Presets ────────────────────────────────────────────────────────


class PipelinePreset(str, Enum):
    PAPER = "paper"
    RESEARCH = "research"
    FINANCIAL_REPORT = "financial_report"
    EMPIRICAL = "empirical"


def get_paper_pipeline_steps() -> list[PipelineStep]:
    """Paper pipeline: outline → literature → plotting → writing → refinement."""
    return [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline"),
        PipelineStep(stage=PipelineStage.LITERATURE, agent_name="literature"),
        PipelineStep(stage=PipelineStage.PLOTTING, agent_name="plotting"),
        PipelineStep(stage=PipelineStage.WRITING, agent_name="writing"),
        PipelineStep(
            stage=PipelineStage.REFINEMENT,
            agent_name="refinement",
            hitl_gate=True,  # Final review gate
        ),
    ]


def get_research_pipeline_steps() -> list[PipelineStep]:
    """Research pipeline: outline → literature → writing → refinement."""
    return [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline"),
        PipelineStep(stage=PipelineStage.LITERATURE, agent_name="literature"),
        PipelineStep(stage=PipelineStage.WRITING, agent_name="writing"),
        PipelineStep(stage=PipelineStage.REFINEMENT, agent_name="refinement"),
    ]


def get_financial_report_steps() -> list[PipelineStep]:
    """Financial report pipeline: financial_analysis → report_writing."""
    return [
        PipelineStep(stage=PipelineStage.FINANCIAL_ANALYSIS, agent_name="financial_analysis"),
        PipelineStep(stage=PipelineStage.REPORT_WRITING, agent_name="report_writing"),
    ]


def get_pipeline_steps(preset: PipelinePreset) -> list[PipelineStep]:
    """Get pipeline steps for a given preset."""
    mapping = {
        PipelinePreset.PAPER: get_paper_pipeline_steps,
        PipelinePreset.RESEARCH: get_research_pipeline_steps,
        PipelinePreset.FINANCIAL_REPORT: get_financial_report_steps,
        PipelinePreset.EMPIRICAL: get_research_pipeline_steps,  # Reuse research for now
    }
    return mapping[preset]()


PIPELINE_PRESETS = {
    PipelinePreset.PAPER: {
        "name": "论文写作",
        "description": "完整论文流程：大纲 → 文献 → 图表 → 写作 → 审稿",
        "stages": ["outline", "literature", "plotting", "writing", "refinement"],
        "hitl_gates": ["refinement"],
    },
    PipelinePreset.RESEARCH: {
        "name": "研究调研",
        "description": "精简流程：大纲 → 文献 → 写作 → 审稿",
        "stages": ["outline", "literature", "writing", "refinement"],
        "hitl_gates": [],
    },
    PipelinePreset.FINANCIAL_REPORT: {
        "name": "金融研报",
        "description": "财务分析 → 研报撰写",
        "stages": ["financial_analysis", "report_writing"],
        "hitl_gates": [],
    },
    PipelinePreset.EMPIRICAL: {
        "name": "实证研究",
        "description": "实证分析流程（待完整实现）",
        "stages": ["outline", "literature", "writing", "refinement"],
        "hitl_gates": [],
    },
}


# ─── HITL State (in-memory, production should use Redis/DB) ─────────────────


@dataclass
class HITLGateState:
    """In-memory HITL gate state for SSE streaming."""
    gate_id: str
    stage: str
    content_preview: str
    created_at: float = field(default_factory=time.time)
    approved: bool | None = None
    feedback: str = ""


_hitl_gates: dict[str, HITLGateState] = {}
_awaiting_approval: dict[str, asyncio.Event] = {}


# ─── SSE Event Generator ─────────────────────────────────────────────────────


async def _run_pipeline_streaming(
    pipeline_name: str,
    steps: list[PipelineStep],
    input_data: dict[str, Any],
) -> AsyncGenerator[StreamEvent, None]:
    """
    Streaming pipeline executor that yields SSE events for each stage.

    This bridges AgentOrchestrator's synchronous execution with the async
    StreamingResponse by running agents in a thread pool and emitting
    structured StreamEvent objects.
    """
    from scripts.core.llm_gateway import LLMGateway

    # Initialize gateway and orchestrator
    gateway = LLMGateway(memory=None)
    orchestrator = AgentOrchestrator(gateway)
    orchestrator.register_default_agents()

    # Emit pipeline start
    yield StreamEvent(
        event_type=StreamEventType.PIPELINE_START,
        data={
            "pipeline": pipeline_name,
            "input": str(input_data)[:200],
            "total_steps": len([s for s in steps if not s.skip]),
        },
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
                "step_index": completed,
            },
        )

        # Check HITL gate
        hitl_gate = getattr(step, "hitl_gate", False)
        if hitl_gate:
            gate_id = f"{pipeline_name}_{step.stage.value}_{int(time.time())}"
            _hitl_gates[gate_id] = HITLGateState(
                gate_id=gate_id,
                stage=step.stage.value,
                content_preview=str(context)[:500],
            )
            _awaiting_approval[gate_id] = asyncio.Event()

            yield StreamEvent(
                event_type=StreamEventType.HITL_PAUSE,
                data={
                    "gate_id": gate_id,
                    "stage": stage_name.value if stage_name else agent_name,
                    "content_preview": str(context)[:500],
                    "question": f"请审核 {step.stage.value} 阶段的输出并决定是否继续。",
                },
            )

            # Wait for approval/rejection (non-blocking)
            try:
                await asyncio.wait_for(
                    _awaiting_approval[gate_id].wait(),
                    timeout=3600,  # 1 hour timeout
                )
            except asyncio.TimeoutError:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={"error": "HITL approval timeout (1 hour)"},
                )
                break

            gate_state = _hitl_gates.get(gate_id)
            if gate_state is None or gate_state.approved is False:
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={
                        "agent": agent_name,
                        "error": f"Rejected at {step.stage.value}: {gate_state.feedback if gate_state else 'unknown'}",
                    },
                )
                break

            yield StreamEvent(
                event_type=StreamEventType.HITL_RESUME,
                data={"gate_id": gate_id, "feedback": gate_state.feedback},
            )

        # Execute agent in thread pool (it's synchronous)
        agent = orchestrator.get_agent(agent_name)
        if not agent:
            yield StreamEvent(
                event_type=StreamEventType.AGENT_ERROR,
                data={"error": f"Agent '{agent_name}' not found"},
            )
            continue

        # Run agent in executor to avoid blocking
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, agent.run, context)
            # Update context with stage result
            if hasattr(result, "output"):
                context[f"{step.stage.value}_result"] = result.output

            yield StreamEvent(
                event_type=StreamEventType.AGENT_END,
                data={
                    "agent": agent_name,
                    "stage": stage_name.value if stage_name else agent_name,
                    "status": result.status if hasattr(result, "status") else "completed",
                    "iterations": result.iterations if hasattr(result, "iterations") else 0,
                    "latency_ms": result.latency_ms if hasattr(result, "latency_ms") else 0,
                    "feedback": (result.feedback[:200] if hasattr(result, "feedback") and result.feedback else ""),
                },
            )

            if result.status == "error":
                yield StreamEvent(
                    event_type=StreamEventType.AGENT_ERROR,
                    data={
                        "agent": agent_name,
                        "error": str(getattr(result, "feedback", "Unknown error"))[:500],
                    },
                )
                break

        except Exception as exc:
            logger.exception(f"Agent '{agent_name}' failed")
            yield StreamEvent(
                event_type=StreamEventType.AGENT_ERROR,
                data={"agent": agent_name, "error": str(exc)[:500]},
            )
            break

        completed += 1

        # Emit progress
        yield StreamEvent(
            event_type=StreamEventType.PROGRESS,
            data={
                "completed": completed,
                "total": total_steps,
                "percent": int(completed / total_steps * 100) if total_steps > 0 else 100,
            },
        )

    # Emit pipeline end
    yield StreamEvent(
        event_type=StreamEventType.PIPELINE_END,
        data={
            "pipeline": pipeline_name,
            "completed": completed,
            "total": total_steps,
            "success": completed == total_steps,
        },
    )


# ─── SSE Response Helper ──────────────────────────────────────────────────────


async def _sse_response(
    pipeline_name: str,
    steps: list[PipelineStep],
    input_data: dict[str, Any],
) -> AsyncGenerator[bytes, None]:
    """Convert StreamEvents to SSE-formatted HTTP chunks."""
    try:
        async for event in _run_pipeline_streaming(pipeline_name, steps, input_data):
            sse_data = event.to_sse()
            yield sse_data.encode("utf-8")
    except Exception as exc:
        logger.exception("SSE stream error")
        error_event = StreamEvent(
            event_type=StreamEventType.AGENT_ERROR,
            data={"error": f"Stream error: {str(exc)[:200]}"},
        )
        yield error_event.to_sse().encode("utf-8")


# ─── API Endpoints ───────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        content={
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": time.time(),
        }
    )


@app.get("/pipeline/presets")
async def list_presets() -> JSONResponse:
    """List available pipeline presets."""
    return JSONResponse(content={"presets": PIPELINE_PRESETS})


@app.get("/pipeline/stream/{pipeline_name}")
async def stream_pipeline(
    pipeline_name: str,
    topic: str = "",
    venue: str = "arxiv",
    preset: PipelinePreset = PipelinePreset.PAPER,
    request: Request = None,
) -> StreamingResponse:
    """
    Stream pipeline execution as SSE events.

    Parameters
    ----------
    pipeline_name : str
        Human-readable name for this pipeline run.
    topic : str
        Research topic or title.
    venue : str
        Target venue (arxiv, cvpr, icml, etc.).
    preset : PipelinePreset
        Which pipeline preset to run (paper, research, financial_report, empirical).
    request : Request
        FastAPI request object (used for client disconnect detection).

    Returns
    -------
    StreamingResponse
        text/event-stream response with pipeline events.

    SSE Events
    ----------
    pipeline_start  — Pipeline initialization complete
    agent_start     — Agent execution starting
    chunk           — Incremental output chunk (if streaming available)
    agent_end       — Agent execution complete
    hitl_pause      — Waiting for human approval
    hitl_resume     — Human approved, continuing
    progress        — Pipeline progress update
    agent_error     — Error occurred
    pipeline_end    — Pipeline complete (success or failure)
    """
    # Validate preset
    if preset not in PIPELINE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown preset: {preset}. Available: {list(PIPELINE_PRESETS.keys())}",
        )

    # Build input data
    input_data = {
        "topic": topic,
        "venue": venue,
        "client_ip": request.client.host if request and request.client else "unknown",
    }

    # Get pipeline steps for preset
    steps = get_pipeline_steps(preset)

    logger.info(
        f"SSE stream started: pipeline={pipeline_name}, preset={preset.value}, "
        f"topic={topic[:50]}, steps={len(steps)}"
    )

    return StreamingResponse(
        _sse_response(pipeline_name, steps, input_data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ─── HITL Approval Endpoints ──────────────────────────────────────────────────


class HITLActionRequest(BaseModel):
    gate_id: str
    feedback: str = ""


@app.post("/pipeline/hitl/approve")
async def hitl_approve(body: HITLActionRequest) -> JSONResponse:
    """
    Approve a HITL gate and resume pipeline execution.

    Parameters
    ----------
    gate_id : str
        The gate_id from the hitl_pause event.
    feedback : str
        Optional feedback for the agent.
    """
    gate_id = body.gate_id
    feedback = body.feedback

    if gate_id not in _hitl_gates:
        raise HTTPException(status_code=404, detail=f"HITL gate not found: {gate_id}")

    gate = _hitl_gates[gate_id]
    gate.approved = True
    gate.feedback = feedback

    # Signal the waiting coroutine
    if gate_id in _awaiting_approval:
        _awaiting_approval[gate_id].set()

    logger.info(f"HITL approved: gate_id={gate_id}, feedback={feedback[:50]}")

    return JSONResponse(content={
        "success": True,
        "gate_id": gate_id,
        "action": "approved",
        "feedback": feedback,
    })


@app.post("/pipeline/hitl/reject")
async def hitl_reject(body: HITLActionRequest) -> JSONResponse:
    """
    Reject a HITL gate and abort pipeline execution.

    Parameters
    ----------
    gate_id : str
        The gate_id from the hitl_pause event.
    feedback : str
        Reason for rejection (required).
    """
    gate_id = body.gate_id
    feedback = body.feedback

    if gate_id not in _hitl_gates:
        raise HTTPException(status_code=404, detail=f"HITL gate not found: {gate_id}")

    if not feedback:
        raise HTTPException(status_code=400, detail="Feedback is required for rejection")

    gate = _hitl_gates[gate_id]
    gate.approved = False
    gate.feedback = feedback

    # Signal the waiting coroutine
    if gate_id in _awaiting_approval:
        _awaiting_approval[gate_id].set()

    logger.info(f"HITL rejected: gate_id={gate_id}, feedback={feedback[:50]}")

    return JSONResponse(content={
        "success": True,
        "gate_id": gate_id,
        "action": "rejected",
        "feedback": feedback,
    })


@app.get("/pipeline/hitl/status/{gate_id}")
async def hitl_status(gate_id: str) -> JSONResponse:
    """Get status of a specific HITL gate."""
    if gate_id not in _hitl_gates:
        raise HTTPException(status_code=404, detail=f"HITL gate not found: {gate_id}")

    gate = _hitl_gates[gate_id]
    return JSONResponse(content={
        "gate_id": gate.gate_id,
        "stage": gate.stage,
        "approved": gate.approved,
        "feedback": gate.feedback,
        "created_at": gate.created_at,
        "awaiting": not gate.approved if gate.approved is not None else True,
    })


# ─── Run Server ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    uvicorn.run(
        "scripts.core.sse_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
