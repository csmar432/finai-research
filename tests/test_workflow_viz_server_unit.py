"""Unit tests for scripts/workflow_viz_server.py.

Covers: read_queue, write_queue, pop_queue, push_queue, load_data,
save_data, get_html, WFHandler, VisualizationServer, main, DEFAULT_NODES,
DEFAULT_DATA, CACHE_FILE, QUEUE_FILE, HTML_FILE, PROJECT_ROOT,
_state_lock, _server_start_time, _current_data.
"""
from __future__ import annotations

import inspect
import json
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def wvs():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import workflow_viz_server as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


# ═══════════════════════════════════════════════════════════════════════════
# Module constants and defaults
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleConstants:
    def test_project_root_is_path(self, wvs):
        assert isinstance(wvs.PROJECT_ROOT, Path)

    def test_html_file_is_path(self, wvs):
        assert isinstance(wvs.HTML_FILE, Path)

    def test_cache_file_is_path(self, wvs):
        assert isinstance(wvs.CACHE_FILE, Path)

    def test_queue_file_is_path(self, wvs):
        assert isinstance(wvs.QUEUE_FILE, Path)

    def test_default_nodes_nonempty_list(self, wvs):
        assert isinstance(wvs.DEFAULT_NODES, list)
        assert len(wvs.DEFAULT_NODES) >= 1
        # Each node has expected keys
        node = wvs.DEFAULT_NODES[0]
        assert "id" in node
        assert "type" in node
        assert "label" in node

    def test_default_node_metadata_has_keys(self, wvs):
        node = wvs.DEFAULT_NODES[0]
        assert "metadata" in node
        md = node["metadata"]
        assert "stage" in md
        assert "agent_role" in md

    def test_default_data_has_keys(self, wvs):
        assert isinstance(wvs.DEFAULT_DATA, dict)
        assert "nodes" in wvs.DEFAULT_DATA
        assert "edges" in wvs.DEFAULT_DATA
        assert "meta" in wvs.DEFAULT_DATA

    def test_default_data_meta_has_keys(self, wvs):
        meta = wvs.DEFAULT_DATA["meta"]
        assert "topic" in meta
        assert "total_stages" in meta
        assert "total_gates" in meta

    def test_state_lock_is_lock(self, wvs):
        assert isinstance(wvs._state_lock, type(threading.Lock()))

    def test_server_start_time_is_float(self, wvs):
        assert isinstance(wvs._server_start_time, float)


# ═══════════════════════════════════════════════════════════════════════════
# Queue management functions
# ═══════════════════════════════════════════════════════════════════════════


class TestQueueFunctions:
    def test_read_queue_returns_list(self, wvs):
        result = wvs.read_queue()
        assert isinstance(result, list)

    def test_read_queue_when_missing_returns_empty(self, wvs, tmp_path, monkeypatch):
        # Point at a non-existent file
        missing = tmp_path / "missing.json"
        monkeypatch.setattr(wvs, "QUEUE_FILE", missing)
        result = wvs.read_queue()
        assert result == []

    def test_write_read_roundtrip(self, wvs, tmp_path, monkeypatch):
        # Redirect QUEUE_FILE to a temp location
        tmp_q = tmp_path / "queue.json"
        monkeypatch.setattr(wvs, "QUEUE_FILE", tmp_q)
        items = [{"id": 1, "topic": "test"}, {"id": 2, "topic": "demo"}]
        wvs.write_queue(items)
        loaded = wvs.read_queue()
        assert loaded == items

    def test_write_queue_creates_parent_dir(self, wvs, tmp_path, monkeypatch):
        nested = tmp_path / "subdir" / "queue.json"
        monkeypatch.setattr(wvs, "QUEUE_FILE", nested)
        wvs.write_queue([{"id": 1}])
        assert nested.exists()
        assert nested.parent.is_dir()

    def test_pop_queue_returns_first(self, wvs, tmp_path, monkeypatch):
        tmp_q = tmp_path / "queue.json"
        monkeypatch.setattr(wvs, "QUEUE_FILE", tmp_q)
        wvs.write_queue([{"id": 1}, {"id": 2}, {"id": 3}])
        first = wvs.pop_queue()
        assert first == {"id": 1}
        assert len(wvs.read_queue()) == 2

    def test_pop_empty_returns_none(self, wvs, tmp_path, monkeypatch):
        tmp_q = tmp_path / "queue.json"
        monkeypatch.setattr(wvs, "QUEUE_FILE", tmp_q)
        # Ensure file does not exist
        tmp_q.unlink(missing_ok=True)
        assert wvs.pop_queue() is None

    def test_push_queue_appends(self, wvs, tmp_path, monkeypatch):
        tmp_q = tmp_path / "queue.json"
        monkeypatch.setattr(wvs, "QUEUE_FILE", tmp_q)
        wvs.push_queue({"id": 1, "topic": "foo"})
        wvs.push_queue({"id": 2, "topic": "bar"})
        items = wvs.read_queue()
        assert len(items) == 2
        assert items[0]["topic"] == "foo"
        assert items[1]["topic"] == "bar"


# ═══════════════════════════════════════════════════════════════════════════
# load_data / save_data
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadSaveData:
    def test_save_load_roundtrip(self, wvs, tmp_path, monkeypatch):
        # Redirect CACHE_FILE to tmp
        tmp_c = tmp_path / "cache.json"
        monkeypatch.setattr(wvs, "CACHE_FILE", tmp_c)
        # Also clear in-memory state to a known baseline
        monkeypatch.setattr(wvs, "_current_data", dict(wvs.DEFAULT_DATA))
        payload = {
            "nodes": [{"id": "n1", "label": "test"}],
            "edges": [],
            "meta": {"topic": "abc"},
        }
        wvs.save_data(payload)
        loaded = wvs.load_data()
        assert loaded["meta"]["topic"] == "abc"
        assert loaded["nodes"][0]["id"] == "n1"

    def test_load_data_returns_dict(self, wvs):
        result = wvs.load_data()
        assert isinstance(result, dict)
        assert "nodes" in result

    def test_save_data_creates_parent_dir(self, wvs, tmp_path, monkeypatch):
        nested = tmp_path / "sub" / "cache.json"
        monkeypatch.setattr(wvs, "CACHE_FILE", nested)
        monkeypatch.setattr(wvs, "_current_data", dict(wvs.DEFAULT_DATA))
        wvs.save_data({"nodes": [], "edges": []})
        assert nested.exists()


# ═══════════════════════════════════════════════════════════════════════════
# get_html
# ═══════════════════════════════════════════════════════════════════════════


class TestGetHtml:
    def test_returns_bytes(self, wvs, tmp_path, monkeypatch):
        # Create a fake HTML file
        fake_html = tmp_path / "workflow_demo.html"
        fake_html.write_bytes(b"<html><body>hi</body></html>")
        monkeypatch.setattr(wvs, "HTML_FILE", fake_html)
        content = wvs.get_html()
        assert isinstance(content, bytes)
        assert b"<html>" in content

    def test_returns_fallback_when_missing(self, wvs, tmp_path, monkeypatch):
        missing_html = tmp_path / "missing.html"
        monkeypatch.setattr(wvs, "HTML_FILE", missing_html)
        content = wvs.get_html()
        assert isinstance(content, bytes)
        # Fallback mentions missing file
        assert b"workflow_demo.html" in content or b"not found" in content.lower()


# ═══════════════════════════════════════════════════════════════════════════
# WFHandler HTTP request handler
# ═══════════════════════════════════════════════════════════════════════════


class TestWFHandler:
    def test_class_exists(self, wvs):
        assert hasattr(wvs, "WFHandler")
        assert inspect.isclass(wvs.WFHandler)

    def test_inherits_base_http_handler(self, wvs):
        from http.server import BaseHTTPRequestHandler
        assert issubclass(wvs.WFHandler, BaseHTTPRequestHandler)

    def test_has_do_get(self, wvs):
        assert hasattr(wvs.WFHandler, "do_GET")

    def test_has_do_post(self, wvs):
        assert hasattr(wvs.WFHandler, "do_POST")

    def test_has_do_options(self, wvs):
        assert hasattr(wvs.WFHandler, "do_OPTIONS")

    def test_has_send_json(self, wvs):
        assert hasattr(wvs.WFHandler, "send_json")

    def test_has_send_html(self, wvs):
        assert hasattr(wvs.WFHandler, "send_html")

    def test_log_message_silenced(self, wvs):
        # log_message is overridden to pass (silence access logs)
        handler = wvs.WFHandler
        assert callable(handler.log_message)


# ═══════════════════════════════════════════════════════════════════════════
# VisualizationServer lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestVisualizationServer:
    def test_class_exists(self, wvs):
        assert hasattr(wvs, "VisualizationServer")
        assert inspect.isclass(wvs.VisualizationServer)

    def test_port_constant(self, wvs):
        assert isinstance(wvs.VisualizationServer.PORT, int)
        assert wvs.VisualizationServer.PORT > 0
        assert wvs.VisualizationServer.PORT == 8502

    def test_base_url_constant(self, wvs):
        url = wvs.VisualizationServer.BASE_URL
        assert isinstance(url, str)
        assert "localhost" in url
        assert str(wvs.VisualizationServer.PORT) in url

    def test_init(self, wvs):
        srv = wvs.VisualizationServer()
        assert srv is not None
        assert srv._running is False
        assert srv._server is None
        assert srv._thread is None

    def test_is_running_returns_bool(self, wvs):
        srv = wvs.VisualizationServer()
        # May be True if a server is running on PORT — just check return is bool
        assert isinstance(srv.is_running(), bool)

    def test_url_property(self, wvs):
        srv = wvs.VisualizationServer()
        assert srv.url == wvs.VisualizationServer.BASE_URL

    def test_has_start_method(self, wvs):
        srv = wvs.VisualizationServer()
        assert callable(srv.start)

    def test_has_stop_method(self, wvs):
        srv = wvs.VisualizationServer()
        assert callable(srv.stop)


# ═══════════════════════════════════════════════════════════════════════════
# CLI entrypoint
# ═══════════════════════════════════════════════════════════════════════════


class TestMain:
    def test_function_exists(self, wvs):
        assert callable(wvs.main)

    def test_main_signature(self, wvs):
        sig = inspect.signature(wvs.main)
        required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
        assert len(required) == 0