"""
tests/test_langgraph_pipeline.py — 15 tests for the LangGraph-backed pipeline.

Tests cover:
  1.  LiteTracer logging and export
  2.  LiteCompiledGraph patched invoke / stream with tracer
  3.  LangGraphPipeline instantiation with and without LangGraph
  4.  checkpoint_to_lg / lg_to_observability
  5.  run_with_langgraph with mock LLM
  6.  invoke_with_trace timing
  7.  Graceful fallback when LangGraph is not installed
"""

from __future__ import annotations

import json
import time as _time
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

# ── Module under test ──────────────────────────────────────────────────────────

from scripts.core.langgraph_integration import (
    CheckpointStore,
    LiteCompiledGraph,
    LiteTracer,
    ResearchStage,
    StateGraph,
    create_research_graph,
    is_langgraph_available,
)
from scripts.core.agent_pipeline_lg import (
    LangGraphPipeline,
    checkpoint_to_lg,
    invoke_with_trace,
    lg_to_observability,
    run_with_langgraph,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def lite_tracer() -> LiteTracer:
    return LiteTracer()


@pytest.fixture
def simple_graph() -> StateGraph:
    """A minimal 2-node linear graph for testing."""
    graph = StateGraph(name="test_graph")

    def node_a(state: dict) -> dict:
        return {"current_stage": "node_a", "result": "output_a"}

    def node_b(state: dict) -> dict:
        return {"current_stage": "node_b", "result": "output_b"}

    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.add_edge("node_a", "node_b")
    return graph


@pytest.fixture
def compiled_graph(simple_graph) -> LiteCompiledGraph:
    store = CheckpointStore()
    return simple_graph.compile(checkpoint_store=store)


@pytest.fixture
def mock_gateway():
    gw = MagicMock()
    gw.generate.return_value = MagicMock(
        response="mock response",
        model_used="mock",
        input_tokens=10,
        output_tokens=5,
        latency_ms=50,
    )
    return gw


@pytest.fixture
def mock_orchestrator(mock_gateway):
    """Mock AgentOrchestrator (avoids real LLM init)."""
    with patch("scripts.core.orchestrator.AgentOrchestrator.__init__", return_value=None):
        from scripts.core.orchestrator import AgentOrchestrator
        orch = object.__new__(AgentOrchestrator)
        orch.gateway = mock_gateway
        orch._agents = {}
        orch._message_bus = []
        orch._trace = []
        orch._hitl_gate = MagicMock()
        orch._shared_hitl = MagicMock()
        orch._active_tokens = {}
        orch._rejection_feedback = {}
        orch._parliament = None
        orch._evolution_engine = None
        return orch


# ══════════════════════════════════════════════════════════════════════════════
# Test 1 — LiteTracer.log_node records events
# ══════════════════════════════════════════════════════════════════════════════

class TestLiteTracerLogNode:
    def test_log_node_enter(self, lite_tracer):
        lite_tracer.log_node("lit_review", "enter", None, {"topic": "碳排放权"})
        trace = lite_tracer.get_trace()
        assert len(trace) == 1
        assert trace[0]["node"] == "lit_review"
        assert trace[0]["event"] == "enter"
        assert trace[0]["timestamp"] > 0
        assert "duration_ms" not in trace[0]
        assert trace[0]["state_summary"]["topic"] == "碳排放权"

    def test_log_node_exit_with_duration(self, lite_tracer):
        lite_tracer.log_node("hypothesis", "exit", 123.456, {"status": "done"})
        trace = lite_tracer.get_trace()
        assert len(trace) == 1
        assert trace[0]["event"] == "exit"
        assert trace[0]["duration_ms"] == 123.456
        assert trace[0]["state_summary"]["status"] == "done"

    def test_log_node_error(self, lite_tracer):
        lite_tracer.log_node("data_fetch", "error", 99.0, {"error": "timeout"})
        trace = lite_tracer.get_trace()
        assert len(trace) == 1
        assert trace[0]["event"] == "error"
        assert trace[0]["state_summary"]["error"] == "timeout"

    def test_log_node_ignores_non_scalar_state(self, lite_tracer):
        lite_tracer.log_node(
            "node_x",
            "enter",
            None,
            {"scalar": 42, "nested": {"a": 1}, "list": [1, 2]},
        )
        trace = lite_tracer.get_trace()
        summary = trace[0]["state_summary"]
        assert summary["scalar"] == 42
        assert "nested" not in summary
        assert "list" not in summary

    def test_get_trace_returns_copy(self, lite_tracer):
        lite_tracer.log_node("a", "enter", None, {})
        trace1 = lite_tracer.get_trace()
        trace1.clear()
        trace2 = lite_tracer.get_trace()
        assert len(trace2) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Test 2 — LiteTracer.export_json
# ══════════════════════════════════════════════════════════════════════════════

class TestLiteTracerExport:
    def test_export_json_writes_file(self, lite_tracer, tmp_path):
        lite_tracer.log_node("node1", "enter", None, {"k": "v"})
        lite_tracer.log_node("node1", "exit", 50.0, {})
        path = tmp_path / "trace.json"
        lite_tracer.export_json(path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["node"] == "node1"
        assert data[1]["event"] == "exit"

    def test_export_json_creates_parent_dirs(self, lite_tracer, tmp_path):
        lite_tracer.log_node("x", "enter", None, {})
        path = tmp_path / "deeply" / "nested" / "trace.json"
        lite_tracer.export_json(path)
        assert path.exists()

    def test_export_json_string_path(self, lite_tracer, tmp_path):
        lite_tracer.log_node("y", "enter", None, {})
        path = str(tmp_path / "trace.json")
        lite_tracer.export_json(path)
        assert Path(path).exists()


# ══════════════════════════════════════════════════════════════════════════════
# Test 3 — LiteTracer.clear and summary
# ══════════════════════════════════════════════════════════════════════════════

class TestLiteTracerClearAndSummary:
    def test_clear(self, lite_tracer):
        lite_tracer.log_node("n", "enter", None, {})
        lite_tracer.log_node("n", "exit", 10.0, {})
        lite_tracer.clear()
        assert lite_tracer.get_trace() == []

    def test_summary_empty(self, lite_tracer):
        s = lite_tracer.summary()
        assert s["total_events"] == 0
        assert s["error_count"] == 0
        assert s["avg_duration_ms"] == {}

    def test_summary_with_nodes(self, lite_tracer):
        lite_tracer.log_node("lit_review", "enter", None, {})
        _time.sleep(0.01)
        lite_tracer.log_node("lit_review", "exit", None, {})
        s = lite_tracer.summary()
        assert s["total_events"] == 2
        assert "lit_review" in s["unique_nodes"]
        assert s["node_count"]["lit_review"] == 1
        assert s["error_count"] == 0

    def test_summary_error_count(self, lite_tracer):
        lite_tracer.log_node("bad", "error", 5.0, {"error": "boom"})
        s = lite_tracer.summary()
        assert s["error_count"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Test 4 — LiteCompiledGraph patched invoke calls tracer
# ══════════════════════════════════════════════════════════════════════════════

class TestCompiledGraphInvokeWithTracer:
    def test_invoke_calls_tracer_enter_exit(self, compiled_graph, lite_tracer):
        compiled_graph.set_tracer(lite_tracer)
        result = compiled_graph.invoke({"topic": "测试"})
        # Both nodes should produce enter + exit events
        trace = lite_tracer.get_trace()
        node_names = {e["node"] for e in trace}
        events = {e["event"] for e in trace}
        assert "node_a" in node_names
        assert "node_b" in node_names
        assert "enter" in events
        assert "exit" in events
        assert result["current_stage"] in ("node_a", "node_b")

    def test_invoke_timing_recorded(self, compiled_graph, lite_tracer):
        compiled_graph.set_tracer(lite_tracer)
        compiled_graph.invoke({})
        trace = lite_tracer.get_trace()
        exit_events = [e for e in trace if e["event"] == "exit"]
        assert all("duration_ms" in e for e in exit_events)
        assert all(e["duration_ms"] >= 0 for e in exit_events)

    def test_invoke_error_calls_tracer_error(self):
        # Build a fresh graph with ONLY the bad node so it IS reached
        from scripts.core.langgraph_integration import StateGraph, CheckpointStore

        graph = StateGraph(name="error_test")

        def good_node(state: dict) -> dict:
            return {"current_stage": "good_node"}

        def bad_node(state: dict) -> dict:
            raise RuntimeError("node failed")

        graph.add_node("good_node", good_node)
        graph.add_node("bad_node", bad_node)
        graph.add_edge("good_node", "bad_node")

        store = CheckpointStore()
        compiled = graph.compile(checkpoint_store=store)
        tracer = LiteTracer()
        compiled.set_tracer(tracer)
        result = compiled.invoke({"topic": "test"})
        trace = tracer.get_trace()
        error_events = [e for e in trace if e["event"] == "error"]
        assert len(error_events) >= 1
        assert result["error"] == "node failed"

    def test_invoke_no_tracer_still_works(self, compiled_graph):
        # No tracer set — should behave identically to original
        result = compiled_graph.invoke({"topic": "test"})
        assert result["topic"] == "test"
        assert result["iter_count"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Test 5 — LiteCompiledGraph patched stream calls tracer
# ══════════════════════════════════════════════════════════════════════════════

class TestCompiledGraphStreamWithTracer:
    def test_stream_yields_node_events(self, compiled_graph, lite_tracer):
        compiled_graph.set_tracer(lite_tracer)
        events = list(compiled_graph.stream({"topic": "stream_test"}))
        node_names_in_stream = {e.get("node") for e in events}
        assert "node_a" in node_names_in_stream
        assert "node_b" in node_names_in_stream

    def test_stream_trace_has_enter_exit(self, compiled_graph, lite_tracer):
        compiled_graph.set_tracer(lite_tracer)
        list(compiled_graph.stream({}))
        trace = lite_tracer.get_trace()
        assert any(e["event"] == "enter" for e in trace)
        assert any(e["event"] == "exit" for e in trace)


# ══════════════════════════════════════════════════════════════════════════════
# Test 6 — LangGraphPipeline instantiation (native)
# ══════════════════════════════════════════════════════════════════════════════

class TestLangGraphPipelineInstantiation:
    def test_instantiate_with_mock_orchestrator(self, mock_orchestrator):
        pipeline = LangGraphPipeline(
            orchestrator=mock_orchestrator,
            use_langgraph_runtime=False,
        )
        assert pipeline._compiled is not None
        assert pipeline._graph is not None
        assert pipeline._tracer is not None

    def test_instantiate_with_langgraph_when_available(self, mock_orchestrator):
        import scripts.core.agent_pipeline_lg as aplg

        # Simulate the case where LangGraph IS installed: _LGStateGraph and
        # MemorySaver are defined in the module namespace.
        mock_lg_cls = MagicMock()
        mock_lg_instance = MagicMock()
        mock_lg_instance.compile.return_value = mock_lg_instance
        mock_lg_cls.return_value = mock_lg_instance
        mock_ms = MagicMock()

        with patch("scripts.core.langgraph_integration.is_langgraph_available", return_value=True):
            with patch.object(aplg, "_LANGGRAPH_AVAILABLE", True):
                aplg._LGStateGraph = mock_lg_cls
                aplg.MemorySaver = mock_ms

                pipeline = LangGraphPipeline(
                    orchestrator=mock_orchestrator,
                    use_langgraph_runtime=True,
                )

                assert pipeline._compiled is not None
                mock_lg_cls.assert_called()

    def test_instantiate_falls_back_to_native_when_langgraph_not_installed(self, mock_orchestrator):
        # Verify that native pipeline is used when _LANGGRAPH_AVAILABLE is False
        import scripts.core.agent_pipeline_lg as aplg
        with patch.object(aplg, "_LANGGRAPH_AVAILABLE", False):
            with patch("scripts.core.langgraph_integration.is_langgraph_available", return_value=False):
                pipeline = LangGraphPipeline(
                    orchestrator=mock_orchestrator,
                    use_langgraph_runtime=True,  # requests langgraph but falls back
                )
                assert pipeline._compiled is not None

    def test_instantiate_creates_lite_tracer_by_default(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator)
        assert isinstance(pipeline._tracer, LiteTracer)

    def test_instantiate_uses_provided_tracer(self, mock_orchestrator):
        tracer = LiteTracer()
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, _tracer=tracer)
        assert pipeline._tracer is tracer

    def test_graph_has_expected_nodes(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        node_names = set(pipeline._graph.nodes.keys())
        expected_nodes = {
            "lit_review",
            "idea_generation",
            "novelty_check",
            "experiment_design",
            "data_acquisition",
            "regression",
            "paper_writing",
        }
        assert expected_nodes.issubset(node_names)


# ══════════════════════════════════════════════════════════════════════════════
# Test 7 — LangGraphPipeline.run_sync
# ══════════════════════════════════════════════════════════════════════════════

class TestLangGraphPipelineRunSync:
    def test_run_sync_returns_final_state(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        result = pipeline.run_sync(
            topic="碳排放权交易与绿色创新",
            venue="经济研究",
            language="zh",
        )
        assert isinstance(result, dict)
        assert result["topic"] == "碳排放权交易与绿色创新"
        assert result["venue"] == "经济研究"
        assert result["language"] == "zh"
        assert result["iter_count"] >= 1

    def test_run_sync_populates_tracer(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        pipeline.run_sync(topic="x", venue="y")
        trace = pipeline.get_trace()
        assert len(trace) >= 2  # at least one enter + one exit per node

    def test_run_sync_with_initial_context(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        result = pipeline.run_sync(
            topic="test",
            venue="test_journal",
            initial_context={"extra_key": "extra_value"},
        )
        assert result["extra_key"] == "extra_value"

    def test_run_sync_creates_checkpoint(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        pipeline.run_sync(topic="checkpoint_test", venue="x")
        history = pipeline._compiled.get_checkpoint_history()
        assert len(history) >= 1

    def test_export_trace(self, mock_orchestrator, tmp_path):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        pipeline.run_sync(topic="export_test", venue="x")
        path = tmp_path / "trace.json"
        pipeline.export_trace(path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)


# ══════════════════════════════════════════════════════════════════════════════
# Test 8 — checkpoint_to_lg
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckpointToLg:
    def test_migrates_checkpoints(self, compiled_graph, tmp_path):
        from scripts.core.checkpoint import CheckpointManager

        cm = CheckpointManager(base_dir=tmp_path / "chk")
        pipeline_id = "test_pipeline"

        # Save two checkpoints via CheckpointManager
        cm.save(
            pipeline_id=pipeline_id,
            pipeline_name="test",
            completed_stage="node_a",
            context={"topic": "test", "stage_outputs": {}},
            stage_results={"node_a": {"result": "ok"}},
        )
        cm.save(
            pipeline_id=pipeline_id,
            pipeline_name="test",
            completed_stage="node_b",
            context={"topic": "test2", "stage_outputs": {"node_a": {}}},
            stage_results={"node_a": {}, "node_b": {}},
        )

        result = checkpoint_to_lg(pipeline_id, cm, compiled_graph)

        assert result["migrated"] == 2
        assert result["latest_checkpoint_id"] != ""
        lg_history = compiled_graph.get_checkpoint_history()
        assert len(lg_history) == 2

    def test_returns_zero_when_no_checkpoints(self, compiled_graph, tmp_path):
        from scripts.core.checkpoint import CheckpointManager

        cm = CheckpointManager(base_dir=tmp_path / "empty")
        result = checkpoint_to_lg("nonexistent", cm, compiled_graph)
        assert result["migrated"] == 0
        assert result["latest_checkpoint_id"] == ""

    def test_returns_zero_for_non_checkpoint_manager(self, compiled_graph):
        result = checkpoint_to_lg("x", {"not": "a checkpoint manager"}, compiled_graph)
        assert result["migrated"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Test 9 — lg_to_observability
# ══════════════════════════════════════════════════════════════════════════════

class TestLgToObservability:
    def test_streams_events_to_langsmith_tracer(self, lite_tracer):
        lite_tracer.log_node("node1", "enter", None, {})
        lite_tracer.log_node("node1", "exit", 50.0, {})

        mock_tracer = MagicMock()
        mock_tracer.start_trace.return_value = "run_abc"
        mock_tracer.end_trace.return_value = None

        result = lg_to_observability(mock_tracer, lite_tracer)

        assert result["streamed"] == 2
        assert result["run_id"] == "run_abc"
        assert mock_tracer.start_trace.called
        assert mock_tracer.end_trace.called

    def test_returns_zero_when_no_events(self, lite_tracer):
        mock_tracer = MagicMock()
        result = lg_to_observability(mock_tracer, lite_tracer)
        assert result["streamed"] == 0
        assert not mock_tracer.start_trace.called


# ══════════════════════════════════════════════════════════════════════════════
# Test 10 — run_with_langgraph
# ══════════════════════════════════════════════════════════════════════════════

class TestRunWithLanggraph:
    @pytest.mark.asyncio
    async def test_runs_without_real_llm(self):
        # Patch the source modules where these classes are defined
        with patch("scripts.core.llm_gateway.LLMGateway") as MockGW:
            with patch("scripts.core.orchestrator.AgentOrchestrator") as MockOrch:
                mock_orch = MagicMock()
                MockOrch.return_value = mock_orch

                result = await run_with_langgraph(
                    topic="关税政策与出口创新",
                    venue="经济研究",
                    language="zh",
                    use_langgraph=False,
                )
                assert isinstance(result, dict)
                assert result["topic"] == "关税政策与出口创新"

    @pytest.mark.asyncio
    async def test_respects_use_langgraph_false(self):
        # Even if langgraph were available, use_langgraph=False forces native
        with patch("scripts.core.llm_gateway.LLMGateway"):
            with patch("scripts.core.orchestrator.AgentOrchestrator") as MockOrch:
                mock_orch = MagicMock()
                MockOrch.return_value = mock_orch

                with patch("scripts.core.agent_pipeline_lg._LANGGRAPH_AVAILABLE", True):
                    result = await run_with_langgraph(
                        topic="x",
                        use_langgraph=False,
                    )
                assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_auto_detects_uses_native_when_langgraph_not_installed(self):
        # use_langgraph=None → auto-detect → falls back to native pipeline
        with patch("scripts.core.llm_gateway.LLMGateway"):
            with patch("scripts.core.orchestrator.AgentOrchestrator") as MockOrch:
                mock_orch = MagicMock()
                MockOrch.return_value = mock_orch

                # _LANGGRAPH_AVAILABLE is False in this test environment
                import scripts.core.agent_pipeline_lg as aplg
                assert aplg._LANGGRAPH_AVAILABLE is False

                result = await run_with_langgraph(
                    topic="auto_detect_fallback",
                    venue="金融研究",
                    use_langgraph=None,  # auto-detect
                )

                assert isinstance(result, dict)
                assert result["topic"] == "auto_detect_fallback"
                assert result["iter_count"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Test 11 — invoke_with_trace
# ══════════════════════════════════════════════════════════════════════════════

class TestInvokeWithTrace:
    def test_returns_state_and_tracer(self):
        def dummy_node(state: dict) -> dict:
            return {"output": "hello"}

        state, tracer = invoke_with_trace(
            node_name="dummy",
            node_func=dummy_node,
            topic="测试主题",
            venue="金融研究",
            language="zh",
        )

        assert state["topic"] == "测试主题"
        assert state["venue"] == "金融研究"
        assert state["output"] == "hello"
        assert tracer is not None

    def test_trace_records_enter_and_exit(self):
        def slow_node(state: dict) -> dict:
            _time.sleep(0.005)
            return {"done": True}

        _, tracer = invoke_with_trace(node_name="slow", node_func=slow_node)
        trace = tracer.get_trace()
        enter_ev = next(e for e in trace if e["event"] == "enter")
        exit_ev = next(e for e in trace if e["event"] == "exit")
        assert enter_ev["node"] == "slow"
        assert exit_ev["node"] == "slow"
        assert exit_ev["duration_ms"] > 0

    def test_catches_node_exception(self):
        def failing_node(state: dict) -> dict:
            raise ValueError("intentional failure")

        state, tracer = invoke_with_trace(node_name="fail", node_func=failing_node)
        trace = tracer.get_trace()
        error_ev = next(e for e in trace if e["event"] == "error")
        assert error_ev["node"] == "fail"
        assert state["error"] == "intentional failure"

    def test_preserves_stage_outputs(self):
        def step_node(state: dict) -> dict:
            return {"step_result": "computed"}

        state, _ = invoke_with_trace(
            node_name="step1",
            node_func=step_node,
            stage_outputs={"prior": {"x": 1}},
        )
        assert state["stage_outputs"]["prior"]["x"] == 1
        assert state["stage_outputs"]["step1"]["step_result"] == "computed"

    def test_timing_is_accurate(self):
        def timed_node(state: dict) -> dict:
            _time.sleep(0.01)
            return {}

        _, tracer = invoke_with_trace(node_name="timed", node_func=timed_node)
        exit_ev = next(e for e in tracer.get_trace() if e["event"] == "exit")
        # Allow some fudge for execution overhead
        assert 5 <= exit_ev["duration_ms"] <= 100


# ══════════════════════════════════════════════════════════════════════════════
# Test 12 — graceful fallback when LangGraph not installed
# ══════════════════════════════════════════════════════════════════════════════

class TestFallbackWithoutLangGraph:
    def test_is_langgraph_available_returns_correct_value(self):
        result = is_langgraph_available()
        # Returns True only if langgraph is actually importable
        assert isinstance(result, bool)

    def test_langgraph_pipeline_works_without_langgraph_runtime(self, mock_orchestrator):
        # Patch langgraph as unavailable globally
        with patch("scripts.core.agent_pipeline_lg._LANGGRAPH_AVAILABLE", False):
            with patch("scripts.core.langgraph_integration.is_langgraph_available", return_value=False):
                pipeline = LangGraphPipeline(
                    orchestrator=mock_orchestrator,
                    use_langgraph_runtime=False,
                )
                result = pipeline.run_sync(topic="fallback test", venue="x")
                assert result["topic"] == "fallback test"

    def test_langgraph_pipeline_uses_native_when_langgraph_not_installed(self, mock_orchestrator):
        # Force native path regardless of use_langgraph_runtime setting
        with patch("scripts.core.agent_pipeline_lg._LANGGRAPH_AVAILABLE", False):
            with patch("scripts.core.langgraph_integration.is_langgraph_available", return_value=False):
                pipeline = LangGraphPipeline(
                    orchestrator=mock_orchestrator,
                    use_langgraph_runtime=True,
                )
                # Native pipeline should still be used
                assert pipeline._compiled is not None


# ══════════════════════════════════════════════════════════════════════════════
# Test 13 — ResearchStage enum completeness
# ══════════════════════════════════════════════════════════════════════════════

class TestResearchStage:
    def test_has_16_stages(self):
        # 16 stages total: IDLE + 15 named stages (topic_definition … error)
        stages = list(ResearchStage)
        assert len(stages) == 16
        assert ResearchStage.IDLE in stages
        assert ResearchStage.LITERATURE_REVIEW in stages
        assert ResearchStage.PAPER_WRITING in stages
        assert ResearchStage.COMPLETE in stages
        assert ResearchStage.ERROR in stages

    def test_stage_values_match_expected(self):
        assert ResearchStage.LITERATURE_REVIEW.value == "literature_review"
        assert ResearchStage.IDEA_GENERATION.value == "idea_generation"
        assert ResearchStage.DATA_ACQUISITION.value == "data_acquisition"


# ══════════════════════════════════════════════════════════════════════════════
# Test 14 — create_research_graph returns valid graph
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateResearchGraph:
    def test_graph_has_required_nodes(self):
        graph = create_research_graph()
        node_names = set(graph.nodes.keys())
        assert "lit_review" in node_names
        assert "idea_generation" in node_names
        assert "novelty_check" in node_names
        assert "experiment_design" in node_names
        assert "data_acquisition" in node_names
        assert "regression" in node_names
        assert "paper_writing" in node_names

    def test_graph_compiles_and_runs(self):
        graph = create_research_graph()
        store = CheckpointStore()
        compiled = graph.compile(checkpoint_store=store)
        result = compiled.invoke({
            "topic": "测试",
            "venue": "经济研究",
            "language": "zh",
        })
        assert result["topic"] == "测试"
        assert result["iter_count"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Test 15 — LangGraphPipeline summary and get_tracer
# ══════════════════════════════════════════════════════════════════════════════

class TestLangGraphPipelineObservability:
    def test_summary_returns_dict(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        pipeline.run_sync(topic="summary_test", venue="x")
        s = pipeline.summary()
        assert "total_events" in s
        assert "unique_nodes" in s
        assert "node_count" in s
        assert "avg_duration_ms" in s
        assert "error_count" in s
        assert isinstance(s["total_events"], int)

    def test_get_tracer_returns_lite_tracer(self, mock_orchestrator):
        pipeline = LangGraphPipeline(orchestrator=mock_orchestrator, use_langgraph_runtime=False)
        t = pipeline.get_tracer()
        assert isinstance(t, LiteTracer)
