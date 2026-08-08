"""Regression: HITL holds AFTER agent.run, approve advances, reject re-runs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.core.agents.base import AgentResult
from scripts.core.hitl_gate import GateState, HITLGate
from scripts.core.orchestrator import (
    AgentOrchestrator,
    PipelineStage,
    PipelineStep,
)


def _make_agent(name: str, output: dict, call_log: list[str]):
    agent = MagicMock()
    agent.config = MagicMock()
    agent.config.name = name

    def _run(ctx, cancel_token=None):
        call_log.append(name)
        # Capture rejection feedback when present (reject→rerun path).
        if ctx.get("prior_rejection_feedback"):
            call_log.append(f"feedback:{ctx['prior_rejection_feedback']}")
        return AgentResult(status="approved", output=dict(output), stage=name)

    agent.run = _run
    return agent


@pytest.fixture
def orch(tmp_path):
    with patch("scripts.core.orchestrator.LLMGateway"):
        o = AgentOrchestrator(gateway=None)
    o.set_hitl_gate(HITLGate(db_path=str(tmp_path / "hitl.db")))
    return o


def test_hitl_runs_agent_before_hold(orch):
    """Gate must see real agent output — not pause before execution."""
    calls: list[str] = []
    orch._agents["outline"] = _make_agent("outline", {"title": "T"}, calls)
    orch._agents["writing"] = _make_agent("writing", {"body": "B"}, calls)

    steps = [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline", hitl_gate=True),
        PipelineStep(
            stage=PipelineStage.WRITING,
            agent_name="writing",
            depends_on=[PipelineStage.OUTLINE],
            hitl_gate=False,
        ),
    ]
    result = orch.run_pipeline("t", steps, {"topic": "x"})

    assert calls == ["outline"]
    assert result.hitl_paused_at == PipelineStage.OUTLINE
    assert result.success is False
    assert PipelineStage.OUTLINE in result.stage_results
    assert result.stage_results[PipelineStage.OUTLINE].output["title"] == "T"
    pending = orch._hitl_gate.get_pending()
    assert len(pending) == 1
    assert pending[0].content.get("stage_result", {}).get("title") == "T"


def test_approve_then_resume_skips_rerun_and_continues(orch):
    calls: list[str] = []
    orch._agents["outline"] = _make_agent("outline", {"title": "T"}, calls)
    orch._agents["writing"] = _make_agent("writing", {"body": "B"}, calls)

    steps = [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline", hitl_gate=True),
        PipelineStep(
            stage=PipelineStage.WRITING,
            agent_name="writing",
            depends_on=[PipelineStage.OUTLINE],
            hitl_gate=False,
        ),
    ]
    paused = orch.run_pipeline("t", steps, {"topic": "x"})
    assert paused.hitl_paused_at == PipelineStage.OUTLINE

    orch.approve_step(PipelineStage.OUTLINE, feedback="ok")
    resumed = orch.resume_pipeline(paused, steps)

    assert calls == ["outline", "writing"]  # outline not re-run
    assert resumed.hitl_paused_at is None
    assert resumed.success is True
    assert resumed.stage_results[PipelineStage.OUTLINE].output["title"] == "T"
    assert resumed.stage_results[PipelineStage.WRITING].output["body"] == "B"


def test_reject_then_resume_reruns_same_stage_with_feedback(orch):
    calls: list[str] = []
    orch._agents["outline"] = _make_agent("outline", {"title": "v2"}, calls)
    orch._agents["writing"] = _make_agent("writing", {"body": "B"}, calls)

    steps = [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline", hitl_gate=True),
        PipelineStep(
            stage=PipelineStage.WRITING,
            agent_name="writing",
            depends_on=[PipelineStage.OUTLINE],
            hitl_gate=False,
        ),
    ]
    paused = orch.run_pipeline("t", steps, {"topic": "x"})
    orch.reject_step(PipelineStage.OUTLINE, feedback="add methods chapter")

    # Still paused until resume; decision is REJECTED.
    hist = orch._hitl_gate.get_history(stage="outline", limit=1)
    assert hist and hist[-1].state == GateState.REJECTED

    resumed = orch.resume_pipeline(paused, steps)

    # outline ran twice; second call received rejection feedback.
    assert calls[0] == "outline"
    assert "feedback:add methods chapter" in calls
    assert calls.count("outline") == 2
    assert resumed.hitl_paused_at == PipelineStage.OUTLINE  # HITL again after re-run
    assert PipelineStage.OUTLINE in resumed.stage_results


def test_resume_while_pending_is_noop(orch):
    calls: list[str] = []
    orch._agents["outline"] = _make_agent("outline", {"title": "T"}, calls)
    steps = [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline", hitl_gate=True),
    ]
    paused = orch.run_pipeline("t", steps, {"topic": "x"})
    again = orch.resume_pipeline(paused, steps)
    assert again is paused or again.hitl_paused_at == PipelineStage.OUTLINE
    assert calls == ["outline"]  # no second run


def test_approve_final_stage_completes_without_rerun(orch):
    calls: list[str] = []
    orch._agents["outline"] = _make_agent("outline", {"title": "T"}, calls)
    steps = [
        PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline", hitl_gate=True),
    ]
    paused = orch.run_pipeline("t", steps, {"topic": "x"})
    orch.approve_step(PipelineStage.OUTLINE)
    done = orch.resume_pipeline(paused, steps)
    assert done.success is True
    assert done.hitl_paused_at is None
    assert calls == ["outline"]
    assert any(
        e.get("type") == "hitl_resume_complete" for e in done.trace
    )
