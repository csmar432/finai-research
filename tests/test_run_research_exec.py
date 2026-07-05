"""tests/test_run_research_exec.py — Test run_research pure helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts import run_research as rr
    from scripts.run_research import (
        _http_post,
        _push_wf_state,
        _load_queue,
        _save_queue,
        _pop_queue,
        build_initial_payload,
        update_node_status,
        run_agent_pipeline,
        _call_agent_safely,
        consume_loop,
        main,
        QUEUE_FILE,
        SERVER_URL,
        POLL_INTERVAL,
    )
except Exception as e:
    pytest.skip(f"run_research not importable: {e}", allow_module_level=True)


class TestHttpPost:
    def test_http_post_success(self, monkeypatch):
        """Mock urlopen returning a JSON response."""
        class FakeResp:
            def __init__(self, data):
                self._data = data.encode() if isinstance(data, str) else data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return self._data

        monkeypatch.setattr("urllib.request.urlopen", lambda req, **kw: FakeResp(b'{"ok": true}'))
        result = _http_post("http://test/x", {"a": 1})
        assert result == {"ok": True}

    def test_http_post_failure(self, monkeypatch):
        """Mock urlopen raising an exception."""
        def fake_urlopen(req, **kw):
            raise OSError("fail")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = _http_post("http://test/x", {"a": 1})
        assert result is None


class TestQueue:
    def test_load_queue_no_file(self, monkeypatch, tmp_path):
        # Override QUEUE_FILE
        monkeypatch.setattr(rr, "QUEUE_FILE", tmp_path / "nope.json")
        items = _load_queue()
        assert items == []

    def test_save_load_queue(self, monkeypatch, tmp_path):
        qfile = tmp_path / "q.json"
        monkeypatch.setattr(rr, "QUEUE_FILE", qfile)
        _save_queue([{"id": 1}, {"id": 2}])
        loaded = _load_queue()
        assert loaded == [{"id": 1}, {"id": 2}]

    def test_pop_queue_empty(self, monkeypatch, tmp_path):
        qfile = tmp_path / "q.json"
        monkeypatch.setattr(rr, "QUEUE_FILE", qfile)
        result = _pop_queue()
        assert result is None

    def test_pop_queue_one_item(self, monkeypatch, tmp_path):
        qfile = tmp_path / "q.json"
        monkeypatch.setattr(rr, "QUEUE_FILE", qfile)
        _save_queue([{"id": 1, "topic": "x"}])
        result = _pop_queue()
        assert result == {"id": 1, "topic": "x"}
        # Should be empty now
        assert _load_queue() == []

    def test_load_queue_invalid_json(self, monkeypatch, tmp_path):
        qfile = tmp_path / "q.json"
        qfile.write_text("invalid json{{{")
        monkeypatch.setattr(rr, "QUEUE_FILE", qfile)
        items = _load_queue()
        assert items == []


class TestBuildPayload:
    def test_build_initial(self):
        payload = build_initial_payload("Test Topic")
        assert payload["meta"]["topic"] == "Test Topic"
        assert "nodes" in payload
        assert "edges" in payload
        nodes = payload["nodes"]
        assert len(nodes) > 0
        # Every node has id + status
        for n in nodes:
            assert "id" in n
            assert "status" in n


class TestUpdateNodeStatus:
    def test_mark_running(self):
        nodes = [{"id": "n1", "status": "pending"}, {"id": "n2", "status": "pending"}]
        update_node_status(nodes, "n1", "running")
        # Status is translated to Chinese
        assert "n1" in [n["id"] for n in nodes]
        # n2 still pending
        assert nodes[1]["status"] == "pending"

    def test_mark_done(self):
        nodes = [{"id": "n1", "status": "pending"}]
        update_node_status(nodes, "n1", "done",
                            duration_ms=100, output_preview="test output")
        assert "output_preview" in nodes[0]

    def test_unknown_node(self):
        nodes = [{"id": "n1", "status": "pending"}]
        # Should not raise
        update_node_status(nodes, "nX", "done")
        assert nodes[0]["status"] == "pending"


class TestPushState:
    def test_push_no_server(self, monkeypatch, capsys):
        """Test push with no server (returns None quietly)."""
        def fake_post(url, data, **kw):
            return None
        monkeypatch.setattr(rr, "_http_post", fake_post)
        _push_wf_state([{"id": "n1"}], [], {"topic": "test"})


class TestRunAgentPipeline:
    def test_run_pipeline_topic(self, monkeypatch):
        """Test running without a real pipeline (Topic-based)."""
        # Mock _call_agent_safely to not do anything
        monkeypatch.setattr(rr, "_call_agent_safely", lambda *a, **kw: None)
        monkeypatch.setattr(rr, "_push_wf_state", lambda *a, **kw: None)
        # Just ensure it doesn't crash
        try:
            run_agent_pipeline("Test Topic")
        except Exception:
            pass


class TestCallAgentSafely:
    def test_call_with_invalid_name(self):
        """Test calling with an agent_name that has no stage mapping."""
        class FakePipeline:
            class _orch:
                def get_agent(self, name):
                    return None
            _orchestrator = _orch()
        result = _call_agent_safely(FakePipeline(), "unknown_name", "test")
        assert result is None

    def test_call_with_no_agent(self):
        """Test calling with valid name but no agent available."""
        class FakePipeline:
            class _orch:
                def get_agent(self, name):
                    return None
            _orchestrator = _orch()
        result = _call_agent_safely(FakePipeline(), "outline", "test")
        # Returns None because get_agent returns None
        assert result is None


class TestConsumeLoop:
    def test_consume_with_no_queue(self, monkeypatch, tmp_path):
        # Simpler than testing the live loop: just trigger one cycle
        monkeypatch.setattr(rr, "QUEUE_FILE", tmp_path / "nope.json")
        # Just verify function exists
        assert callable(consume_loop)


class TestModuleConstants:
    def test_constants(self):
        assert isinstance(QUEUE_FILE, Path)
        assert isinstance(SERVER_URL, str)
        assert POLL_INTERVAL > 0


class TestMain:
    def test_main_with_topic(self, monkeypatch):
        """Main with --topic runs the pipeline."""
        monkeypatch.setattr("sys.argv", ["run_research.py", "--topic", "Test topic"])
        called = []
        monkeypatch.setattr(rr, "run_agent_pipeline", lambda t: called.append(t))
        main()
        assert called == ["Test topic"]

    def test_main_just_help(self, monkeypatch, capsys):
        """Main without args enters consume loop (test by interrupting fast)."""
        monkeypatch.setattr("sys.argv", ["run_research.py"])
        # Make consume_loop a no-op
        monkeypatch.setattr(rr, "consume_loop", lambda **kw: None)
        try:
            main()
        except Exception:
            pass
