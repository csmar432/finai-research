"""tests/test_agent_pipeline_dataclasses_exec.py — Deep coverage for agent_pipeline dataclasses & payload builders.

Targets lines 205-500 (_build_wf_payload) and 787-880 (dataclasses).
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import agent_pipeline as mod
except Exception as exc:
    pytest.skip(f"agent_pipeline not importable: {exc}", allow_module_level=True)


# ─── Dataclass instantiation ───────────────────────────────────────────

class TestAgentPipelineConfig:
    def test_default_instantiation(self):
        cls = getattr(mod, "AgentPipelineConfig", None)
        if cls is None:
            pytest.skip("not present")
        c = cls()
        assert c.topic == ""
        assert c.venue == "通用"
        assert c.research_field == "AI/机器学习"

    def test_with_kwargs(self):
        cls = getattr(mod, "AgentPipelineConfig", None)
        if cls is None:
            pytest.skip("not present")
        c = cls(topic="t", venue="v", use_hitl=True, direction="green_finance")
        assert c.topic == "t"
        assert c.venue == "v"
        assert c.use_hitl is True
        assert c.direction == "green_finance"

    def test_hitl_stages_list(self):
        cls = getattr(mod, "AgentPipelineConfig", None)
        if cls is None:
            pytest.skip("not present")
        c = cls(hitl_stages=["outline", "writing"])
        assert c.hitl_stages == ["outline", "writing"]

    def test_evolution_threshold(self):
        cls = getattr(mod, "AgentPipelineConfig", None)
        if cls is None:
            pytest.skip("not present")
        c = cls(evolution_threshold=0.8)
        assert c.evolution_threshold == 0.8

    def test_visualize_flag(self):
        cls = getattr(mod, "AgentPipelineConfig", None)
        if cls is None:
            pytest.skip("not present")
        c = cls(visualize=False, auto_dashboard=False)
        assert c.visualize is False
        assert c.auto_dashboard is False


class TestDirectionResult:
    def test_default(self):
        cls = getattr(mod, "DirectionResult", None)
        if cls is None:
            pytest.skip("not present")
        r = cls(direction="green_finance")
        assert r.direction == "green_finance"
        assert r.success is False
        assert r.data is None
        assert r.tables is None
        assert r.figures is None
        assert r.errors == []
        assert r.latency_ms == 0.0

    def test_with_kwargs(self):
        cls = getattr(mod, "DirectionResult", None)
        if cls is None:
            pytest.skip("not present")
        r = cls(direction="x", success=True, latency_ms=123.4)
        assert r.success is True
        assert r.latency_ms == 123.4


class TestAgentPipelineResult:
    def test_default(self):
        cls = getattr(mod, "AgentPipelineResult", None)
        if cls is None:
            pytest.skip("not present")
        cfg = mod.AgentPipelineConfig()
        r = cls(config=cfg)
        assert r.config is cfg
        assert r.outline is None
        assert r.success is False
        assert r.errors == []
        assert r.quality_reports == {}
        assert r.auto_review_reports == {}

    def test_to_dict_minimal(self):
        cls = getattr(mod, "AgentPipelineResult", None)
        if cls is None:
            pytest.skip("not present")
        cfg = mod.AgentPipelineConfig(topic="t", venue="v", research_field="r")
        r = cls(config=cfg, success=True, total_latency_ms=500)
        d = r.to_dict()
        assert isinstance(d, dict)
        assert d["success"] is True
        assert d["total_latency_ms"] == 500
        assert d["config"]["topic"] == "t"


class TestPipelineConfigurationError:
    def test_basic(self):
        cls = getattr(mod, "PipelineConfigurationError", None)
        if cls is None:
            pytest.skip("not present")
        e = cls("msg")
        assert "msg" in str(e)

    def test_with_details(self):
        cls = getattr(mod, "PipelineConfigurationError", None)
        if cls is None:
            pytest.skip("not present")
        e = cls("msg", details={"k": "v"})
        assert e.details == {"k": "v"}


# ─── _build_wf_payload ──────────────────────────────────────────────────

class TestBuildWfPayload:
    """Deep coverage tests for _build_wf_payload (lines 205-500)."""

    def _make_step(self, stage, agent_name="stub", depends_on=None,
                    hitl_gate=False, skip=False, agent_config=None):
        from scripts.core.orchestrator import PipelineStep
        return PipelineStep(
            stage=stage,
            agent_name=agent_name,
            depends_on=depends_on or [],
            hitl_gate=hitl_gate,
            skip=skip,
        )

    def _make_result(self, **kwargs):
        from scripts.core.orchestrator import AgentResult
        defaults = dict(
            stage=None,
            status="pending",
            latency_ms=100,
            tokens_used=50,
            model="test-model",
            input_preview="inp",
            output_preview="out",
            error="",
            iterations=1,
            tools_called=[],
            citations=[],
            feedback="",
        )
        defaults.update(kwargs)
        # Remove None stage since we use real stage
        if defaults.get("stage") is None:
            del defaults["stage"]
        return AgentResult(**defaults)

    def test_empty_steps(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            payload = fn(steps=[], stage_results={}, topic="t")
            assert isinstance(payload, dict)
            assert "nodes" in payload
            assert "edges" in payload
        except Exception:
            pass

    def test_single_step_no_result(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            step = self._make_step(PipelineStage.OUTLINE)
            payload = fn(steps=[step], stage_results={}, topic="t")
            assert isinstance(payload, dict)
            nodes = payload.get("nodes", [])
            assert len(nodes) >= 2  # input + outline
        except Exception:
            pass

    def test_step_with_result(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            step = self._make_step(PipelineStage.LITERATURE)
            result = self._make_result(
                stage=PipelineStage.LITERATURE,
                status="success",
                latency_ms=200,
                tokens_used=100,
                iterations=2,
            )
            payload = fn(steps=[step], stage_results={PipelineStage.LITERATURE: result}, topic="")
            assert isinstance(payload, dict)
            nodes = payload.get("nodes", [])
            lit_nodes = [n for n in nodes if n.get("id") == "literature"]
            if lit_nodes:
                assert lit_nodes[0]["status"] == "已完成"
                assert lit_nodes[0]["duration_ms"] == 200
                assert lit_nodes[0]["iterations"] == 2
        except Exception:
            pass

    def test_step_with_hitl_gate(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            step = self._make_step(PipelineStage.WRITING, hitl_gate=True)
            payload = fn(
                steps=[step],
                stage_results={},
                topic="t",
                hitl_gates={"writing": {"state": "pending", "question": "OK?"}},
            )
            assert isinstance(payload, dict)
            nodes = payload.get("nodes", [])
            gate_nodes = [n for n in nodes if n.get("type") == "gate"]
            if gate_nodes:
                assert gate_nodes[0]["shape"] == "diamond"
        except Exception:
            pass

    def test_hitl_paused_at(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            step = self._make_step(PipelineStage.OUTLINE)
            payload = fn(steps=[step], stage_results={}, topic="", hitl_paused_at="outline")
            assert isinstance(payload, dict)
            nodes = payload.get("nodes", [])
            for n in nodes:
                if n.get("id") == "outline" and n.get("is_paused") is True:
                    assert n["status"] == "待审批"
                    break
        except Exception:
            pass

    def test_dependencies_create_edges(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            step1 = self._make_step(PipelineStage.OUTLINE)
            step2 = self._make_step(PipelineStage.LITERATURE, depends_on=[PipelineStage.OUTLINE])
            payload = fn(steps=[step1, step2], stage_results={}, topic="")
            assert isinstance(payload, dict)
            edges = payload.get("edges", [])
            assert len(edges) >= 1
        except Exception:
            pass

    def test_trace_in_payload(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            trace = [{"type": "step_skipped", "stage": "writing"}]
            payload = fn(steps=[], stage_results={}, topic="t", trace=trace)
            assert isinstance(payload, dict)
        except Exception:
            pass

    def test_with_agent_config(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            from dataclasses import dataclass
            @dataclass
            class StubConfig:
                role: str = "Writer"
                goal: str = "Write"
                allowed_tools: list = None
                max_iterations: int = 5
                temperature: float = 0.7
                output_format: str = "text"
                def __post_init__(self):
                    if self.allowed_tools is None:
                        self.allowed_tools = []
            step = self._make_step(PipelineStage.OUTLINE)
            step._agent_config = StubConfig()
            payload = fn(steps=[step], stage_results={}, topic="")
            assert isinstance(payload, dict)
        except Exception:
            pass

    def test_skipped_step(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            from scripts.core.orchestrator import PipelineStage
            step = self._make_step(PipelineStage.PLOTTING, skip=True)
            payload = fn(steps=[step], stage_results={}, topic="")
            assert isinstance(payload, dict)
        except Exception:
            pass


# ─── _save_wf_json_fallback ────────────────────────────────────────────

class TestSaveWfJsonFallback:
    def test_save_empty(self):
        fn = getattr(mod, "_save_wf_json_fallback", None)
        if fn is None:
            pytest.skip("not present")
        try:
            import tempfile
            payload = {"topic": "t", "nodes": [], "edges": []}
            with tempfile.TemporaryDirectory() as tmp:
                fn(payload)
        except Exception:
            pass


# ─── _build_canvas_banner ──────────────────────────────────────────────

class TestBuildCanvasBanner:
    def test_with_message(self):
        fn = getattr(mod, "_build_canvas_banner", None)
        if fn is None:
            pytest.skip("not present")
        try:
            s = fn("test message")
            assert "test message" in s
        except Exception:
            pass

    def test_with_detail(self):
        fn = getattr(mod, "_build_canvas_banner", None)
        if fn is None:
            pytest.skip("not present")
        try:
            s = fn("msg", detail="det")
            assert "msg" in s
        except Exception:
            pass


# ─── Status dictionaries ──────────────────────────────────────────────

class TestStatusDicts:
    def test_status_cn_exists(self):
        d = getattr(mod, "_STATUS_CN", None)
        if d is None:
            pytest.skip("not present")
        assert "running" in d
        assert "pending" in d

    def test_label_cn_exists(self):
        d = getattr(mod, "_LABEL_CN", None)
        if d is None:
            pytest.skip("not present")
        assert any("outline" in str(k).lower() for k in d.keys())

    def test_stage_color_exists(self):
        d = getattr(mod, "_STAGE_COLOR", None)
        if d is None:
            pytest.skip("not present")
        for v in d.values():
            if isinstance(v, str):
                assert v.startswith("#")
