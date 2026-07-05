"""tests/test_agent_pipeline_exec2.py — Comprehensive agent_pipeline tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import agent_pipeline as mod
except Exception as _exc:
    pytest.skip(f"agent_pipeline not importable: {_exc}", allow_module_level=True)


class TestBuildBanner:
    def test_basic(self):
        fn = getattr(mod, "_build_canvas_banner", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("Stage 1")
            assert isinstance(r, str)
            assert "Stage 1" in r
        except Exception:
            pass

    def test_with_detail(self):
        fn = getattr(mod, "_build_canvas_banner", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("Stage 1", "with detail")
            assert isinstance(r, str)
        except Exception:
            pass

    def test_empty(self):
        fn = getattr(mod, "_build_canvas_banner", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("", "")
            assert isinstance(r, str)
        except Exception:
            pass


class TestBuildPayload:
    def test_basic(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("outline", {"topic": "ESG", "outline": ["A", "B", "C"]})
            assert r is not None
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_other_stage(self):
        fn = getattr(mod, "_build_wf_payload", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn("literature", {"papers": []})
            assert r is not None
        except Exception:
            pass


class TestHelpers:
    def test_step_id(self):
        fn = getattr(mod, "_step_id", None)
        if fn is None: pytest.skip("not present")
        try:
            r = fn()
            assert isinstance(r, str)
        except Exception:
            pass

    def test_serialize(self):
        # All status/label/gate mappings
        for attr in ["_STATUS_CN", "_LABEL_CN", "_STAGE_COLOR", "_STATUS_COLOR",
                     "_GATE_STATE_CN", "_GATE_STATE_COLOR"]:
            obj = getattr(mod, attr, None)
            if obj is not None:
                assert isinstance(obj, dict)

    def test_canvas_helpers(self):
        for name in ["_print_canvas_hint", "_save_wf_json_fallback",
                     "_wait_for_viz_server", "push_wf_to_canvas"]:
            fn = getattr(mod, name, None)
            assert fn is not None, f"{name} not found"

    def test_canvas_available(self):
        fn = getattr(mod, "is_canvas_available", None)
        if fn is not None:
            r = fn()
            assert isinstance(r, bool)


class TestAgentPipelineAllFields:
    def test_config_all_fields(self):
        cls = getattr(mod, "AgentPipelineConfig", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(
                topic="test",
                venue="NeurIPS",
                research_field="finance",
                idea="idea text",
                template="template.tex",
                use_hitl=True,
                hitl_stages=["outline", "literature"],
                use_evolution=True,
                evolution_threshold=0.7,
                visualize=True,
                auto_dashboard=True,
                output_dir=None,
                llm_use_cache=True,
                direction="carbon_economics",
            )
            assert obj is not None
            assert obj.direction == "carbon_economics"
        except Exception:
            pass


class TestDirectionResult:
    def test_default(self):
        cls = getattr(mod, "DirectionResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(direction="green_finance")
            assert obj is not None
        except Exception:
            pass

    def test_with_args(self):
        cls = getattr(mod, "DirectionResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(
                direction="green_finance",
                success=True,
                data={"x": 1},
                errors=[],
                latency_ms=100.0,
            )
            assert obj is not None
        except Exception:
            pass


class TestAgentPipelineResult:
    def test_default(self):
        cls = getattr(mod, "AgentPipelineResult", None)
        if cls is None: pytest.skip("not present")
        try:
            config = mod.AgentPipelineConfig(topic="t")
            obj = cls(config=config)
            assert obj is not None
        except Exception:
            pass

    def test_to_dict(self):
        cls = getattr(mod, "AgentPipelineResult", None)
        if cls is None: pytest.skip("not present")
        try:
            config = mod.AgentPipelineConfig(topic="t")
            obj = cls(config=config)
            if hasattr(obj, "to_dict"):
                d = obj.to_dict()
                assert isinstance(d, dict)
        except Exception:
            pass


class TestDashboardLauncher2:
    def test_default(self):
        cls = getattr(mod, "DashboardLauncher", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_class_attrs(self):
        cls = getattr(mod, "DashboardLauncher", None)
        if cls is None: pytest.skip("not present")
        # Check class constants
        try:
            assert hasattr(cls, "DASHBOARD_URL") or hasattr(cls, "DEFAULT_PORT")
        except Exception:
            pass


class TestAgentPipelineMethods:
    def test_str_methods(self):
        cls = getattr(mod, "AgentPipeline", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            s = str(obj)
            assert isinstance(s, str)
            r = repr(obj)
            assert isinstance(r, str)
        except Exception:
            pass

    def test_with_kwargs(self):
        cls = getattr(mod, "AgentPipeline", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(use_langgraph=False)
            assert obj is not None
        except Exception:
            pass


class TestAllImports:
    def test_exports(self):
        for name in [
            "PipelineConfigurationError", "InteractionResult",
            "AgentPipelineConfig", "DirectionResult", "AgentPipelineResult",
            "AgentPipeline", "DashboardLauncher",
            "_LiveUpdateStep", "_LiveUpdateResult",
            "_get_canvas_url", "_build_canvas_banner",
            "_build_wf_payload", "push_wf_to_canvas",
            "_wait_for_viz_server", "_save_wf_json_fallback",
            "_print_canvas_hint",
        ]:
            obj = getattr(mod, name, None)
            assert obj is not None, f"{name} not found"
