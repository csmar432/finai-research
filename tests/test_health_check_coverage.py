"""Deterministic branch tests for health_check without external services."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import health_check as hc


class Response:
    status = 200

    def __init__(self, body=b'{}'):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_env_mask_and_platform_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-key")
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nDEEPSEEK_API_KEY=file-key\nIGNORED=x=y\n", encoding="utf-8")
    values = hc._read_env(env_file)
    assert values["DEEPSEEK_API_KEY"] == "file-key"
    assert hc._mask("1234567890") == "1234**7890"
    assert hc._mask("short") == "*****"
    monkeypatch.setenv("CURSOR", "cursor")
    assert hc._detect_platform() == "cursor"
    monkeypatch.delenv("CURSOR")
    monkeypatch.setenv("CLAUDE_CODE", "claude_code")
    assert hc._detect_platform() == "claude_code"
    monkeypatch.delenv("CLAUDE_CODE")
    monkeypatch.setenv("AGENT_ID", "codex-session")
    assert hc._detect_platform() == "codex"


@pytest.mark.parametrize("error, expected", [
    (urllib.error.HTTPError("u", 401, "unauthorized", {}, None), (True, "HTTP 401")),
    (urllib.error.HTTPError("u", 500, "server", {}, None), (False, "HTTP 500")),
    (urllib.error.URLError("offline"), (False, "连接失败")),
    (RuntimeError("boom"), (False, "boom")),
])
def test_probe_url_error_classes(monkeypatch, error, expected):
    monkeypatch.setattr(hc.urllib.request, "urlopen", Mock(side_effect=error))
    result = hc._probe_url("https://example.test")
    assert result[0] is expected[0]
    assert expected[1] in result[1]


def test_llm_completion_success_json_and_failures(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
    monkeypatch.setattr(hc.urllib.request, "urlopen", lambda *a, **k: Response(body))
    ok, message = hc._llm_chat_completion("https://example.test", "key", "model")
    assert ok and "response_len=5" in message

    monkeypatch.setattr(hc.urllib.request, "urlopen", lambda *a, **k: Response(b"not-json"))
    ok, message = hc._llm_chat_completion("https://example.test", "key", "model")
    assert not ok and "JSON decode error" in message

    error = urllib.error.HTTPError("u", 400, "bad", {}, None)
    error.read = lambda: b'{"error":{"message":"invalid key"}}'
    monkeypatch.setattr(hc.urllib.request, "urlopen", Mock(side_effect=error))
    ok, message = hc._llm_chat_completion("https://example.test", "key", "model")
    assert not ok and message == "invalid key"


def test_check_dependencies_reports_import_error(monkeypatch):
    real_import = hc.importlib.import_module

    def fake_import(name):
        if name in {"requests", "dotenv"}:
            raise ImportError(name)
        return real_import(name)

    monkeypatch.setattr(hc.importlib, "import_module", fake_import)
    problems, ok = hc._check_dependencies()
    assert any(p.name == "requests" and p.severity == "high" for p in problems)
    assert any(p.name == "dotenv" and p.severity == "medium" for p in problems)
    assert any(item.startswith("numpy ") for item in ok)


def test_platform_fixes_and_grouping():
    assert "Cursor" in hc._platform_fixes("cursor")["restart_hint"] or "重启" in hc._platform_fixes("cursor")["restart_hint"]
    assert "Claude" in hc._platform_fixes("claude_code")["restart_hint"]
    assert "重新加载" in hc._platform_fixes("codex")["restart_hint"]
    assert hc._platform_fixes("unknown")["env_hint"]
    item = hc.ProblemItem(hc.ProblemCategory.NETWORK, "n", "N", "m", [])
    groups = hc._group_by_category([item, item])
    assert groups[hc.ProblemCategory.NETWORK] == [item, item]


def test_verify_mcp_server_missing_and_popen_error(tmp_path, monkeypatch):
    missing = hc._verify_mcp_server_stdio(tmp_path / "missing.py")
    assert missing == (False, "server.py 不存在")
    server = tmp_path / "server.py"
    server.write_text("", encoding="utf-8")
    monkeypatch.setattr(hc.subprocess, "Popen", Mock(side_effect=OSError("cannot spawn")))
    ok, message = hc._verify_mcp_server_stdio(server)
    assert not ok and message == "cannot spawn"


def test_check_mcp_scans_local_servers_and_missing_keys(tmp_path, monkeypatch):
    servers = tmp_path / "mcp_servers" / "user_tushare"
    servers.mkdir(parents=True)
    (servers / "server.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(hc, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / ".cursor").mkdir()
    (tmp_path / "home" / ".cursor" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"tushare": {}}}), encoding="utf-8"
    )
    enabled, verified, problems, ok = hc._check_mcp(verify=False)
    assert enabled == 1 and verified == 0
    assert any(p.name == "mcp_missing_api_keys" for p in problems)
    assert ok == []
