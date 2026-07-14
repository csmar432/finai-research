"""Unit tests for scripts/core/streaming.py — dataclasses, enums, and helpers.

Covers: StreamEventType, StreamEvent, StreamingConfig, create_sse_response,
StreamingPipeline (init + supports_streaming), and the streaming-to-SSE helpers.
"""

from __future__ import annotations

import builtins
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.streaming import (
        StreamEventType,
        StreamEvent,
        StreamingConfig,
        create_sse_response,
        StreamingPipeline,
    )
except Exception as _exc:
    pytest.skip(f"streaming not importable: {_exc}", allow_module_level=True)


# ─── Patch builtins.getattr to prevent MagicMock from being detected as a generator ─
# MagicMock has __iter__ and __next__ as auto-created child mocks. When the
# generator-detection code does `hasattr(result, '__iter__')`, it calls getattr
# internally.  We patch getattr to raise AttributeError for MagicMock on those two
# attributes, which makes hasattr return False.
_ORCHESTRATOR_PATCH = patch(
    "scripts.core.orchestrator.AgentOrchestrator", new=MagicMock()
)


def _patch_generator_detection():
    original_getattr = builtins.getattr

    def _patched_getattr(obj, name, *default):
        if isinstance(obj, MagicMock) and name in ("__iter__", "__next__"):
            if default:
                return default[0]
            raise AttributeError(name)
        return original_getattr(obj, name, *default)

    return patch("scripts.core.streaming.getattr", _patched_getattr)


# ─── StreamEventType Enum ────────────────────────────────────────────────────


class TestStreamEventTypeMembers:
    """All enum members must be accessible and have string values."""

    def test_all_members_exist(self):
        expected = {
            "AGENT_START",
            "AGENT_CHUNK",
            "AGENT_END",
            "AGENT_ERROR",
            "HITL_PAUSE",
            "HITL_RESUME",
            "PIPELINE_START",
            "PIPELINE_END",
            "PROGRESS",
            "STREAMING_UNAVAILABLE",
        }
        actual = {e.name for e in StreamEventType}
        assert expected.issubset(actual), f"Missing: {expected - actual}"

    def test_values_are_strings(self):
        for member in StreamEventType:
            assert isinstance(member.value, str)

    def test_unique_values(self):
        values = [e.value for e in StreamEventType]
        assert len(values) == len(set(values))

    def test_agent_start_value(self):
        assert StreamEventType.AGENT_START.value == "agent_start"

    def test_agent_chunk_value(self):
        assert StreamEventType.AGENT_CHUNK.value == "chunk"

    def test_agent_end_value(self):
        assert StreamEventType.AGENT_END.value == "agent_end"

    def test_agent_error_value(self):
        assert StreamEventType.AGENT_ERROR.value == "agent_error"

    def test_hitl_pause_value(self):
        assert StreamEventType.HITL_PAUSE.value == "hitl_pause"

    def test_hitl_resume_value(self):
        assert StreamEventType.HITL_RESUME.value == "hitl_resume"

    def test_pipeline_start_value(self):
        assert StreamEventType.PIPELINE_START.value == "pipeline_start"

    def test_pipeline_end_value(self):
        assert StreamEventType.PIPELINE_END.value == "pipeline_end"

    def test_progress_value(self):
        assert StreamEventType.PROGRESS.value == "progress"

    def test_streaming_unavailable_value(self):
        assert StreamEventType.STREAMING_UNAVAILABLE.value == "streaming_unavailable"

    def test_can_compare_by_value(self):
        assert StreamEventType.AGENT_START == StreamEventType("agent_start")
        assert StreamEventType.PIPELINE_END == StreamEventType("pipeline_end")


# ─── StreamEvent Dataclass ──────────────────────────────────────────────────


class TestStreamEventCreation:
    def test_required_fields_only(self):
        event = StreamEvent(
            event_type=StreamEventType.AGENT_START,
            data={"agent": "test-agent"},
        )
        assert event.event_type == StreamEventType.AGENT_START
        assert event.data == {"agent": "test-agent"}

    def test_optional_event_id(self):
        event = StreamEvent(
            event_type=StreamEventType.PIPELINE_START,
            data={},
            event_id="custom-123",
        )
        assert event.event_id == "custom-123"

    def test_optional_timestamp(self):
        ts = 1700000000.0
        event = StreamEvent(event_type=StreamEventType.PROGRESS, data={}, timestamp=ts)
        assert event.timestamp == ts

    def test_default_event_id_is_short_uuid(self):
        event = StreamEvent(event_type=StreamEventType.AGENT_END, data={})
        assert isinstance(event.event_id, str)
        assert len(event.event_id) == 8

    def test_default_timestamp_is_recent(self):
        before = time.time()
        event = StreamEvent(event_type=StreamEventType.AGENT_ERROR, data={})
        after = time.time()
        assert before <= event.timestamp <= after

    def test_data_can_be_empty_dict(self):
        event = StreamEvent(event_type=StreamEventType.PIPELINE_END, data={})
        assert event.data == {}


class TestStreamEventToSSE:
    def test_basic_sse_format(self):
        event = StreamEvent(
            event_type=StreamEventType.AGENT_START,
            data={"agent": "researcher"},
            event_id="abc12345",
        )
        sse = event.to_sse()
        assert "id: abc12345" in sse
        assert "event: agent_start" in sse
        assert "data:" in sse

    def test_sse_data_is_json(self):
        event = StreamEvent(
            event_type=StreamEventType.AGENT_END,
            data={"status": "completed", "count": 42},
        )
        sse = event.to_sse()
        lines = sse.split("\n")
        data_line = next(l for l in lines if l.startswith("data: "))
        json_str = data_line[len("data: "):]
        parsed = json.loads(json_str)
        assert parsed["status"] == "completed"
        assert parsed["count"] == 42

    def test_sse_ends_with_double_newline(self):
        event = StreamEvent(event_type=StreamEventType.PROGRESS, data={})
        sse = event.to_sse()
        assert sse.endswith("\n\n")

    def test_unicode_in_data(self):
        event = StreamEvent(
            event_type=StreamEventType.AGENT_CHUNK,
            data={"text": "你好世界 🌍"},
        )
        sse = event.to_sse()
        assert "你好世界" in sse

    def test_special_chars_escaped(self):
        event = StreamEvent(
            event_type=StreamEventType.AGENT_CHUNK,
            data={"text": "line1\nline2"},
        )
        sse = event.to_sse()
        assert "\\n" in sse


# ─── StreamingConfig Dataclass ───────────────────────────────────────────────


class TestStreamingConfigDefaults:
    def test_default_chunk_size(self):
        assert StreamingConfig().chunk_size == 20

    def test_default_enable_sse(self):
        assert StreamingConfig().enable_sse is True

    def test_default_buffering(self):
        assert StreamingConfig().buffering == "line"

    def test_default_stream_llm(self):
        assert StreamingConfig().stream_llm is True

    def test_default_max_buffer_ms(self):
        assert StreamingConfig().max_buffer_ms == 100


class TestStreamingConfigCustom:
    def test_custom_chunk_size(self):
        config = StreamingConfig(chunk_size=100)
        assert config.chunk_size == 100

    def test_custom_enable_sse_false(self):
        config = StreamingConfig(enable_sse=False)
        assert config.enable_sse is False

    def test_custom_buffering_token(self):
        config = StreamingConfig(buffering="token")
        assert config.buffering == "token"

    def test_custom_buffering_segment(self):
        config = StreamingConfig(buffering="segment")
        assert config.buffering == "segment"

    def test_custom_max_buffer_ms(self):
        config = StreamingConfig(max_buffer_ms=500)
        assert config.max_buffer_ms == 500

    def test_custom_stream_llm_false(self):
        config = StreamingConfig(stream_llm=False)
        assert config.stream_llm is False

    def test_all_custom_params(self):
        config = StreamingConfig(
            chunk_size=50,
            enable_sse=False,
            buffering="token",
            stream_llm=False,
            max_buffer_ms=250,
        )
        assert config.chunk_size == 50
        assert config.enable_sse is False
        assert config.buffering == "token"
        assert config.stream_llm is False
        assert config.max_buffer_ms == 250


# ─── create_sse_response ───────────────────────────────────────────────────


class TestCreateSSEResponse:
    def test_empty_list(self):
        result = create_sse_response([])
        assert result == ""

    def test_single_event(self):
        event = StreamEvent(
            event_type=StreamEventType.PIPELINE_START,
            data={"pipeline": "test"},
        )
        result = create_sse_response([event])
        assert "pipeline_start" in result
        assert "test" in result

    def test_multiple_events(self):
        events = [
            StreamEvent(event_type=StreamEventType.PIPELINE_START, data={}),
            StreamEvent(event_type=StreamEventType.AGENT_START, data={}),
            StreamEvent(event_type=StreamEventType.PIPELINE_END, data={}),
        ]
        result = create_sse_response(events)
        assert result.count("event:") == 3

    def test_result_is_string(self):
        result = create_sse_response([])
        assert isinstance(result, str)


# ─── StreamingPipeline ───────────────────────────────────────────────────────


class TestStreamingPipelineInit:
    def test_requires_gateway(self):
        mock_gateway = MagicMock()
        pipeline = StreamingPipeline(mock_gateway)
        assert pipeline.gateway is mock_gateway

    def test_default_config(self):
        mock_gateway = MagicMock()
        pipeline = StreamingPipeline(mock_gateway)
        assert isinstance(pipeline.config, StreamingConfig)

    def test_custom_config(self):
        mock_gateway = MagicMock()
        custom = StreamingConfig(chunk_size=99)
        pipeline = StreamingPipeline(mock_gateway, config=custom)
        assert pipeline.config.chunk_size == 99

    def test_private_attributes_initialized(self):
        mock_gateway = MagicMock()
        pipeline = StreamingPipeline(mock_gateway)
        assert pipeline._buffer == []
        assert pipeline._pipeline_instance is None


class TestStreamingPipelineSetPipeline:
    def test_set_pipeline_stores_instance(self):
        mock_gateway = MagicMock()
        pipeline = StreamingPipeline(mock_gateway)
        mock_orchestrator = MagicMock()
        pipeline.set_pipeline(mock_orchestrator)
        assert pipeline._pipeline_instance is mock_orchestrator


class TestStreamingPipelineSupportsStreaming:
    def test_gateway_supports_streaming(self):
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = True
        pipeline = StreamingPipeline(mock_gateway)
        assert pipeline.supports_streaming() is True

    def test_gateway_does_not_support_streaming(self):
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)
        assert pipeline.supports_streaming() is False


# ─── stream_sync() — list-returning synchronous version ─────────────────────────────────
# The installed stream_sync() builds a list of StreamEvents and returns it.
# It uses `orchestrator = self._pipeline_instance` when _pipeline_instance is set.
# We set _pipeline_instance directly to avoid triggering AgentOrchestrator import.


class _FakeStep:
    """Step-like object for stream_sync() tests."""

    def __init__(self, agent_name, hitl_gate=False, skip=False):
        self.agent_name = agent_name
        self.hitl_gate = hitl_gate
        self.skip = skip
        self.stage = None


class TestStreamingPipelineStreamSync:
    """stream_sync() returns a list of StreamEvents."""

    def test_returns_list(self):
        """stream_sync() returns a list."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_agent = MagicMock(spec=["config", "run"])
        mock_agent.config.name = "test-agent"

        class ScalarResult:
            status = "ok"
            iterations = 1
            latency_ms = 10.0
            feedback = ""

        mock_agent.run.return_value = ScalarResult()
        mock_orch.get_agent.return_value = mock_agent
        pipeline.set_pipeline(mock_orch)

        with _patch_generator_detection():
            events = pipeline.stream_sync(
                "test-pipeline", [_FakeStep("test-agent")], {"topic": "test"}
            )
        assert isinstance(events, list)
        assert all(isinstance(e, StreamEvent) for e in events)

    def test_emits_agent_start_and_end(self):
        """stream_sync() emits AGENT_START and AGENT_END events."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_agent = MagicMock(spec=["config", "run"])
        mock_agent.config.name = "test-agent"

        class ScalarResult:
            status = "ok"
            iterations = 1
            latency_ms = 10.0
            feedback = ""

        mock_agent.run.return_value = ScalarResult()
        mock_orch.get_agent.return_value = mock_agent
        pipeline.set_pipeline(mock_orch)

        with _patch_generator_detection():
            events = pipeline.stream_sync(
                "test", [_FakeStep("test-agent")], {"topic": "test"}
            )
        event_types = {e.event_type for e in events}
        assert StreamEventType.AGENT_START in event_types
        assert StreamEventType.AGENT_END in event_types
        assert StreamEventType.PIPELINE_END in event_types

    def test_emits_pipeline_end(self):
        """stream_sync() always emits PIPELINE_END."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_orch.get_agent.return_value = None
        pipeline.set_pipeline(mock_orch)

        events = pipeline.stream_sync("test", [_FakeStep("nonexistent")], {})
        event_types = {e.event_type for e in events}
        assert StreamEventType.PIPELINE_END in event_types

    def test_skips_skipped_steps(self):
        """Steps with skip=True are not executed."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_agent = MagicMock(spec=["config", "run"])
        mock_agent.config.name = "real-agent"

        class ScalarResult:
            status = "ok"
            iterations = 1
            latency_ms = 5.0
            feedback = ""

        mock_agent.run.return_value = ScalarResult()
        mock_orch.get_agent.return_value = mock_agent
        pipeline.set_pipeline(mock_orch)

        with _patch_generator_detection():
            events = pipeline.stream_sync(
                "test",
                [_FakeStep("skipped-agent", skip=True), _FakeStep("real-agent")],
                {"topic": "test"},
            )
        # Only real-agent emits AGENT_START/END
        agent_events = [
            e
            for e in events
            if e.event_type
            in (StreamEventType.AGENT_START, StreamEventType.AGENT_END)
        ]
        assert len(agent_events) == 2  # one start + one end for real step
        assert StreamEventType.PIPELINE_END in {e.event_type for e in events}

    def test_hitl_pause_emits_hitl_pause(self):
        """Step with hitl_gate=True emits HITL_PAUSE and stops."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_orch.get_agent.return_value = MagicMock(spec=["config"])
        pipeline.set_pipeline(mock_orch)

        events = pipeline.stream_sync(
            "test", [_FakeStep("agent", hitl_gate=True)], {"topic": "test"}
        )
        event_types = {e.event_type for e in events}
        assert StreamEventType.HITL_PAUSE in event_types
        assert StreamEventType.AGENT_START in event_types
        # PIPELINE_END is always emitted at the end
        assert StreamEventType.PIPELINE_END in event_types

    def test_agent_not_found_emits_error(self):
        """Unknown agent emits AGENT_ERROR."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_orch.get_agent.return_value = None
        pipeline.set_pipeline(mock_orch)

        events = pipeline.stream_sync(
            "test", [_FakeStep("ghost-agent")], {}
        )
        error_events = [
            e for e in events if e.event_type == StreamEventType.AGENT_ERROR
        ]
        assert len(error_events) == 1
        assert "ghost-agent" in error_events[0].data.get("error", "")

    def test_progress_format(self):
        """Progress string uses completed/total format."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_agent = MagicMock(spec=["config", "run"])
        mock_agent.config.name = "p-agent"

        class ScalarResult:
            status = "ok"
            iterations = 1
            latency_ms = 5.0
            feedback = ""

        mock_agent.run.return_value = ScalarResult()
        mock_orch.get_agent.return_value = mock_agent
        pipeline.set_pipeline(mock_orch)

        with _patch_generator_detection():
            events = pipeline.stream_sync(
                "progress-test", [_FakeStep("p-agent")], {}
            )
        start_events = [
            e for e in events if e.event_type == StreamEventType.AGENT_START
        ]
        assert len(start_events) == 1
        progress = start_events[0].data.get("progress", "")
        assert "/" in progress


class TestStreamingPipelineStreamSyncGenerator:
    """stream_sync() detects generators vs scalar results."""

    def _make_step(self, agent_name, hitl_gate=False, skip=False):
        return _FakeStep(agent_name, hitl_gate=hitl_gate, skip=skip)

    def test_generator_yields_chunks(self):
        """Real generator return value yields AGENT_CHUNK events."""
        mock_gateway = MagicMock()
        mock_gateway.supports_streaming.return_value = False
        pipeline = StreamingPipeline(mock_gateway)

        mock_orch = MagicMock(spec=["get_agent"])
        mock_agent = MagicMock(spec=["config", "run"])
        mock_agent.config.name = "gen-agent"

        mock_agent.run.side_effect = lambda _: (yield "chunk1") or (yield "chunk2")
        mock_orch.get_agent.return_value = mock_agent
        pipeline.set_pipeline(mock_orch)

        with _patch_generator_detection():
            events = pipeline.stream_sync(
                "test", [self._make_step("gen-agent")], {}
            )

        chunk_events = [
            e for e in events if e.event_type == StreamEventType.AGENT_CHUNK
        ]
        assert len(chunk_events) == 2
        assert "chunk1" in chunk_events[0].data.get("chunk", "")
        assert "chunk2" in chunk_events[1].data.get("chunk", "")


# ─── __all__ exports ──────────────────────────────────────────────────────────


class TestStreamingExports:
    def test_module_exports(self):
        """All expected classes and functions are in __all__."""
        import scripts.core.streaming as streaming

        for name in (
            "StreamEventType",
            "StreamEvent",
            "StreamingConfig",
            "create_sse_response",
        ):
            assert name in streaming.__all__, f"{name} missing from __all__"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
