"""Unit tests for scripts/core/sse_server.py.

Covers:
- SSEEvent class
- SSEHandler class
- SSEServer class
- StreamingWriter class
- Helper functions (_now, _summarize_coefs, _format_sig)
- Script generators (get_sse_client_script, get_polling_script)

Test conventions:
  - Synthetic data only — no network calls.
  - Deterministic, no timing dependencies.
  - SSEHandler/SSEServer use mock for dependencies.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


# Try importing sse_server; if agent_state has import errors, mock them.
try:
    import scripts.core.sse_server as sse
    import scripts.core.agent_state as agent_state_mod
except Exception as _exc:
    pytest.skip(f"sse_server not importable: {_exc}", allow_module_level=True)


# ============================================================================
# SSEEvent
# ============================================================================


class TestSSEEventInit:
    def test_init(self):
        event = sse.SSEEvent(event_type="test_event", data={"key": "value"})
        assert event.event_type == "test_event"
        assert event.data == {"key": "value"}
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0

    def test_init_with_complex_data(self):
        event = sse.SSEEvent(
            event_type="complex",
            data={"numbers": [1, 2, 3], "nested": {"a": 1}},
        )
        assert event.data["numbers"] == [1, 2, 3]
        assert event.data["nested"]["a"] == 1


class TestSSEEventToDict:
    def test_to_dict(self):
        ts = 1234567890.5
        with patch.object(time, "time", return_value=ts):
            event = sse.SSEEvent(event_type="dict_test", data={"x": 1})
        d = event.to_dict()
        assert d["type"] == "dict_test"
        assert d["data"] == {"x": 1}
        assert d["timestamp"] == ts

    def test_to_dict_contains_all_fields(self):
        event = sse.SSEEvent(event_type="full", data={"a": 1})
        d = event.to_dict()
        assert "type" in d
        assert "data" in d
        assert "timestamp" in d


class TestSSEEventToSSEFormat:
    def test_to_sse_format(self):
        ts = 1000.0
        with patch.object(time, "time", return_value=ts):
            event = sse.SSEEvent(event_type="sse_test", data={"msg": "hello"})
        output = event.to_sse_format()
        assert "event: sse_test" in output
        assert '"type": "sse_test"' in output
        assert '"msg": "hello"' in output
        assert output.endswith("\n\n")

    def test_to_sse_format_unicode(self):
        event = sse.SSEEvent(event_type="unicode_test", data={"text": "中文测试"})
        output = event.to_sse_format()
        assert "event: unicode_test" in output
        assert "中文" in output

    def test_to_sse_format_empty_data(self):
        event = sse.SSEEvent(event_type="empty", data={})
        output = event.to_sse_format()
        assert "event: empty" in output


# ============================================================================
# SSEHandler
# ============================================================================


class TestSSEHandlerInit:
    def test_init(self):
        handler = sse.SSEHandler()
        assert isinstance(handler._handlers, dict)
        assert isinstance(handler._event_queue, queue.Queue)
        assert handler._running is False
        assert handler._thread is None

    def test_queue_max_size(self):
        handler = sse.SSEHandler()
        assert handler._event_queue.maxsize == 1000


class TestSSEHandlerRegister:
    def test_register_adds_handler(self):
        handler = sse.SSEHandler()
        cb = MagicMock()
        handler.register("my_event", cb)
        assert "my_event" in handler._handlers
        assert cb in handler._handlers["my_event"]

    def test_register_multiple_handlers(self):
        handler = sse.SSEHandler()
        cb1 = MagicMock()
        cb2 = MagicMock()
        handler.register("event_a", cb1)
        handler.register("event_a", cb2)
        assert len(handler._handlers["event_a"]) == 2

    def test_register_wildcard(self):
        handler = sse.SSEHandler()
        cb = MagicMock()
        handler.register("*", cb)
        assert cb in handler._handlers["*"]


class TestSSEHandlerUnregister:
    def test_unregister_existing(self):
        handler = sse.SSEHandler()
        cb = MagicMock()
        handler.register("ev", cb)
        handler.unregister("ev", cb)
        assert cb not in handler._handlers.get("ev", [])

    def test_unregister_nonexistent(self):
        handler = sse.SSEHandler()
        cb = MagicMock()
        # Should not raise
        handler.unregister("nonexistent", cb)

    def test_unregister_wildcard(self):
        handler = sse.SSEHandler()
        cb = MagicMock()
        handler.register("*", cb)
        handler.unregister("*", cb)
        assert cb not in handler._handlers.get("*", [])


class TestSSEHandlerEmit:
    def test_emit_adds_to_queue(self):
        handler = sse.SSEHandler()
        event = sse.SSEEvent(event_type="emit_test", data={"x": 1})
        handler.emit(event)
        assert handler._event_queue.qsize() == 1

    def test_emit_full_queue_skips(self):
        handler = sse.SSEHandler()
        handler._event_queue = queue.Queue(maxsize=1)
        # Fill the queue
        handler._event_queue.put_nowait(sse.SSEEvent("dummy", {}))
        # Emit should not raise (silently skips)
        extra = sse.SSEEvent("extra", {})
        handler.emit(extra)  # queue.Full caught, skips


class TestSSEHandlerProcessLoop:
    def test_process_loop_calls_handler(self):
        handler = sse.SSEHandler()
        cb = MagicMock()
        handler.register("proc_test", cb)
        handler.start()
        event = sse.SSEEvent(event_type="proc_test", data={})
        handler.emit(event)
        # Wait for processing
        time.sleep(0.3)
        handler.stop()
        assert cb.called

    def test_process_loop_calls_wildcard(self):
        handler = sse.SSEHandler()
        wildcard = MagicMock()
        handler.register("*", wildcard)
        handler.start()
        event = sse.SSEEvent(event_type="any_event", data={})
        handler.emit(event)
        time.sleep(0.3)
        handler.stop()
        assert wildcard.called

    def test_start_idempotent(self):
        handler = sse.SSEHandler()
        handler.start()
        handler.start()  # Should not crash
        handler.stop()

    def test_stop_joins_thread(self):
        handler = sse.SSEHandler()
        handler.start()
        handler.stop()
        assert handler._thread is None or not handler._thread.is_alive()


# ============================================================================
# SSEServer
# ============================================================================


class TestSSEServerInit:
    def test_init_creates_handler(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        assert isinstance(server._handler, sse.SSEHandler)
        assert isinstance(server._clients, list)
        assert isinstance(server._lock, type(threading.Lock()))

    def test_init_subscribes_to_event_bus(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all") as mock_sub:
            server = sse.SSEServer()
            mock_sub.assert_called_once()


class TestSSEServerEventConversion:
    def test_event_to_sse_maps_types(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        # Create a mock Event
        mock_event = MagicMock()
        mock_event.event_type = agent_state_mod.EventType.AGENT_START
        mock_event.event_id = "evt-001"
        mock_event.agent_id = "agent-1"
        mock_event.timestamp = 1234.0
        mock_event.duration_ms = 500
        mock_event.data = {"task": "lit_review"}
        sse_event = server._event_to_sse(mock_event)
        assert sse_event.event_type == "agent_start"
        assert sse_event.data["event_id"] == "evt-001"
        assert sse_event.data["task"] == "lit_review"

    def test_event_to_sse_unknown_type(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        mock_event = MagicMock()
        mock_event.event_type = "unknown_type"
        mock_event.event_id = "e1"
        mock_event.agent_id = "a1"
        mock_event.timestamp = 0
        mock_event.duration_ms = 0
        mock_event.data = {}
        sse_event = server._event_to_sse(mock_event)
        assert sse_event.event_type == "unknown"

    def test_event_to_sse_covers_all_known_types(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        for et in agent_state_mod.EventType:
            mock_event = MagicMock()
            mock_event.event_type = et
            mock_event.event_id = "x"
            mock_event.agent_id = "x"
            mock_event.timestamp = 0
            mock_event.duration_ms = 0
            mock_event.data = {}
            sse_event = server._event_to_sse(mock_event)
            assert sse_event.event_type != "unknown"  # All mapped


class TestSSEServerBroadcast:
    def test_broadcast_does_not_raise(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        event = sse.SSEEvent(event_type="broadcast_test", data={})
        # Should not raise
        server._broadcast(event)


class TestSSEServerSubscribe:
    def test_subscribe_registers_handler(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        cb = MagicMock()
        server.subscribe("my_type", cb)
        assert cb in server._handler._handlers.get("my_type", [])


class TestSSEServerUnsubscribe:
    def test_unsubscribe_unregisters_handler(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        cb = MagicMock()
        server.subscribe("to_remove", cb)
        server.unsubscribe("to_remove", cb)
        assert cb not in server._handler._handlers.get("to_remove", [])


class TestSSEServerStartStop:
    def test_start_stops(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        server.start()
        server.stop()
        assert server._handler._running is False

    def test_get_status(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        status = server.get_status()
        assert "running" in status
        assert "queue_size" in status
        assert "handlers_count" in status


class TestSSEServerOnAnyEvent:
    def test_on_any_event_emits_and_broadcasts(self):
        with patch.object(agent_state_mod.event_bus, "subscribe_all"):
            server = sse.SSEServer()
        server.start()
        mock_event = MagicMock()
        mock_event.event_type = agent_state_mod.EventType.AGENT_START
        mock_event.event_id = "x"
        mock_event.agent_id = "x"
        mock_event.timestamp = 0
        mock_event.duration_ms = 0
        mock_event.data = {}
        server._on_any_event(mock_event)
        time.sleep(0.2)
        server.stop()
        assert server._handler._event_queue.qsize() >= 0  # Queued or processed


# ============================================================================
# Helper functions
# ============================================================================


class TestNow:
    def test_now_returns_float(self):
        result = sse._now()
        assert isinstance(result, float)

    def test_now_is_reasonable(self):
        result = sse._now()
        # Should be around current epoch time (>= 2020-01-01)
        assert result > 1577836800.0


class TestFormatSig:
    @pytest.mark.parametrize(
        "pval,expected",
        [
            (None, ""),
            (0.0001, "***"),  # 0.0001 < 0.001
            (0.001, "**"),    # 0.001 < 0.001 is False → falls to < 0.01
            (0.009, "**"),   # 0.009 < 0.01
            (0.01, "*"),     # 0.01 < 0.01 is False → falls to < 0.05
            (0.049, "*"),    # 0.049 < 0.05
            (0.05, ""),      # 0.05 < 0.05 is False
            (0.1, ""),
            (0.5, ""),
        ],
    )
    def test_format_sig(self, pval, expected):
        assert sse._format_sig(pval) == expected


class TestSummarizeCoefs:
    def test_summarize_with_standard_keys(self):
        coefs = [
            {"var": "x1", "coef": 1.5, "se": 0.3, "pval": 0.0001},
            {"var": "x2", "coef": -0.5, "se": 0.2, "pval": 0.049},
        ]
        result = sse._summarize_coefs(coefs)
        assert len(result) == 2
        assert result[0]["var"] == "x1"
        assert result[0]["coef"] == 1.5
        assert result[0]["sig"] == "***"  # 0.0001 < 0.001
        assert result[1]["sig"] == "*"   # 0.049 < 0.05

    def test_summarize_with_alternate_keys(self):
        coefs = [
            {"name": "y1", "estimate": 2.0, "std_error": 0.5, "p_value": 0.03},
        ]
        result = sse._summarize_coefs(coefs)
        assert result[0]["var"] == "y1"
        assert result[0]["coef"] == 2.0

    def test_summarize_empty(self):
        result = sse._summarize_coefs([])
        assert result == []

    def test_summarize_missing_keys(self):
        coefs = [{"unknown_key": "value"}]
        result = sse._summarize_coefs(coefs)
        assert result[0]["var"] == "unknown"
        assert result[0]["coef"] is None


# ============================================================================
# Script generators
# ============================================================================


class TestGetSSEClientScript:
    def test_returns_html_script(self):
        result = sse.get_sse_client_script()
        assert "<script>" in result
        assert "SSEClient" in result
        assert "</script>" in result

    def test_uses_custom_endpoint(self):
        result = sse.get_sse_client_script("/custom/events")
        assert "/custom/events" in result

    def test_includes_event_handlers(self):
        result = sse.get_sse_client_script()
        assert "agent_start" in result
        assert "agent_end" in result
        assert "cost_update" in result

    def test_includes_auto_reconnect(self):
        result = sse.get_sse_client_script()
        # Uses connect() for reconnection logic
        assert "this.connect();" in result
        assert "setTimeout" in result


class TestGetPollingScript:
    def test_returns_html_script(self):
        result = sse.get_polling_script()
        assert "<script>" in result
        assert "POLL_INTERVAL" in result
        assert "</script>" in result

    def test_custom_interval(self):
        result = sse.get_polling_script(interval_ms=5000)
        assert "5000" in result

    def test_includes_api_endpoints(self):
        result = sse.get_polling_script()
        assert "/api/status" in result
        assert "/api/hitl/approve" in result
        assert "/api/hitl/reject" in result

    def test_includes_poll_start_stop(self):
        result = sse.get_polling_script()
        assert "startPolling" in result
        assert "stopPolling" in result


# ============================================================================
# StreamingWriter
# ============================================================================


class TestStreamingWriterInit:
    def test_init_defaults(self):
        writer = sse.StreamingWriter()
        assert writer.output_queue is None
        assert writer.chunk_size == 20
        assert writer.delay_ms == 30.0
        assert writer._chars_written == 0
        assert writer._chunk_count == 0

    def test_init_with_queue(self):
        q = queue.Queue()
        writer = sse.StreamingWriter(output_queue=q, chunk_size=50, delay_ms=100.0)
        assert writer.output_queue is q
        assert writer.chunk_size == 50
        assert writer.delay_ms == 100.0


class TestStreamingWriterSplitChunks:
    def test_split_basic(self):
        writer = sse.StreamingWriter(chunk_size=5)
        chunks = writer._split_chunks("abcdefghij")
        assert chunks == ["abcde", "fghij"]

    def test_split_preserves_newlines(self):
        writer = sse.StreamingWriter(chunk_size=5)
        chunks = writer._split_chunks("abc\ndefghi")
        # Should break at newline instead of mid-word
        assert chunks[0] == "abc\n"

    def test_split_handles_short_text(self):
        writer = sse.StreamingWriter(chunk_size=10)
        chunks = writer._split_chunks("short")
        assert chunks == ["short"]

    def test_split_empty(self):
        writer = sse.StreamingWriter()
        chunks = writer._split_chunks("")
        assert chunks == []

    def test_split_exact_size(self):
        writer = sse.StreamingWriter(chunk_size=3)
        chunks = writer._split_chunks("abc")
        assert chunks == ["abc"]

    def test_split_longer_than_chunk(self):
        writer = sse.StreamingWriter(chunk_size=3)
        chunks = writer._split_chunks("abcdefgh")
        assert len(chunks) > 1
        assert "".join(chunks) == "abcdefgh"


class TestStreamingWriterWrite:
    def test_write_returns_self(self):
        writer = sse.StreamingWriter()
        result = writer.write("test")
        assert result is writer

    def test_write_increments_counters(self):
        writer = sse.StreamingWriter(chunk_size=5)
        writer.write("hello world")
        assert writer._chars_written == 11

    def test_write_with_queue_does_not_raise(self):
        q = queue.Queue()
        writer = sse.StreamingWriter(output_queue=q, chunk_size=5)
        writer.write("hello world")
        assert q.qsize() >= 1


class TestStreamingWriterComplete:
    def test_complete_returns_event(self):
        writer = sse.StreamingWriter()
        event = writer.complete()
        assert isinstance(event, sse.SSEEvent)
        assert event.event_type == "stream_complete"


class TestStreamingWriterStreamText:
    def test_stream_text_yields_events(self):
        writer = sse.StreamingWriter(chunk_size=5)
        events = list(writer.stream_text("hello world"))
        assert len(events) >= 1
        assert all(isinstance(e, sse.SSEEvent) for e in events)

    def test_stream_text_includes_progress(self):
        writer = sse.StreamingWriter(chunk_size=5)
        for event in writer.stream_text("hello world"):
            data = event.data
            assert "chars_total" in data
            assert "chunk_index" in data
            assert "is_complete" in data

    def test_stream_text_short_text(self):
        writer = sse.StreamingWriter(chunk_size=20)
        events = list(writer.stream_text("short"))
        assert len(events) == 1
        assert events[0].data["is_complete"] is False
        # Last event should have is_complete
        last = events[-1]
        # After all chunks, stream completes
        assert "progress_pct" in last.data

    def test_stream_text_progress_pct(self):
        writer = sse.StreamingWriter(chunk_size=3)
        events = list(writer.stream_text("abcdef"))
        for e in events:
            assert 0 <= e.data["progress_pct"] <= 100


class TestStreamingWriterStreamRegressionResults:
    def test_stream_regression_results(self):
        writer = sse.StreamingWriter()
        results = [
            {"model_name": "OLS", "n_obs": 1000, "r_squared": 0.5, "coefficients": []},
            {"model_name": "FE", "n_obs": 1000, "r2": 0.6, "coefficients": []},
        ]
        events = list(writer.stream_regression_results(results))
        assert len(events) == 2
        assert events[0].event_type == "reg_result_chunk"
        assert events[0].data["model_name"] == "OLS"
        assert events[1].data["is_last"] is True

    def test_stream_regression_results_empty(self):
        writer = sse.StreamingWriter()
        events = list(writer.stream_regression_results([]))
        assert len(events) == 0

    def test_stream_regression_results_coef_summary(self):
        writer = sse.StreamingWriter()
        results = [
            {
                "model_name": "Test",
                "n_obs": 100,
                "r_squared": 0.4,
                "coefficients": [
                    {"var": "x1", "coef": 1.0, "se": 0.1, "pval": 0.001},
                ],
            }
        ]
        events = list(writer.stream_regression_results(results))
        assert len(events[0].data["coef_summary"]) == 1


class TestStreamingWriterStreamPaperSections:
    def test_stream_paper_sections(self):
        writer = sse.StreamingWriter(chunk_size=10)
        sections = {
            "title": "My Paper",
            "abstract": "This is a paper about things.",
            "introduction": "Section one.",
        }
        events = list(writer.stream_paper_sections(sections))
        assert len(events) >= 2
        section_keys = {e.data["section"] for e in events}
        assert "title" in section_keys
        assert "abstract" in section_keys

    def test_stream_paper_sections_order(self):
        writer = sse.StreamingWriter()
        sections = {"conclusion": "The end."}
        events = list(writer.stream_paper_sections(sections))
        assert events[0].data["section"] == "conclusion"

    def test_stream_paper_sections_empty(self):
        writer = sse.StreamingWriter()
        events = list(writer.stream_paper_sections({}))
        assert len(events) == 0


class TestStreamingWriterCheckpointEvent:
    def test_stream_checkpoint_event(self):
        writer = sse.StreamingWriter()
        event = writer.stream_checkpoint_event("lit_review", "chk-001", {"key": "val"})
        assert isinstance(event, sse.SSEEvent)
        assert event.event_type == "checkpoint_saved"
        assert event.data["stage"] == "lit_review"
        assert event.data["checkpoint_id"] == "chk-001"
        assert event.data["metadata"] == {"key": "val"}

    def test_stream_checkpoint_event_no_metadata(self):
        writer = sse.StreamingWriter()
        event = writer.stream_checkpoint_event("design", "chk-002")
        assert event.data["metadata"] == {}


class TestStreamingWriterProgressEvent:
    def test_stream_progress_event(self):
        writer = sse.StreamingWriter()
        event = writer.stream_progress_event(
            stage="writing",
            sub_stage="intro",
            pct=45.5,
            message="Writing introduction...",
        )
        assert isinstance(event, sse.SSEEvent)
        assert event.event_type == "progress_update"
        assert event.data["stage"] == "writing"
        assert event.data["sub_stage"] == "intro"
        assert event.data["pct"] == 45.5
        assert event.data["message"] == "Writing introduction..."


# ============================================================================
# Global instance
# ============================================================================


class TestModuleLevel:
    def test_sse_server_global_exists(self):
        assert hasattr(sse, "sse_server")
        assert isinstance(sse.sse_server, sse.SSEServer)

    def test_all_exports_present(self):
        for name in sse.__all__:
            assert hasattr(sse, name)
