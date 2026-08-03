"""Deterministic coverage for MCP filesystem health reporting."""

from __future__ import annotations

import json
import sys

import pytest

from scripts import health_check_mcp as mod


def make_server(root, name, source="print('ok')", docker=False, metadata=False, tools=False):
    path = root / name
    path.mkdir()
    (path / "server.py").write_text(source, encoding="utf-8")
    if docker:
        (path / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
    if metadata:
        (path / "SERVER_METADATA.json").write_text("{}", encoding="utf-8")
    if tools:
        (path / "tools").mkdir()
        (path / "tools" / "search.json").write_text("{}", encoding="utf-8")
    return path


def test_check_server_all_statuses_and_normalization(tmp_path):
    missing = mod.check_server(tmp_path / "missing")
    assert missing.status == "missing" and missing.error
    no_py = tmp_path / "no_py"
    no_py.mkdir()
    assert mod.check_server(no_py).status == "incomplete"
    no_docker = make_server(tmp_path, "no_docker")
    result = mod.check_server(no_docker)
    assert result.status == "compile_ok_no_docker" and result.compile_ok
    ready = make_server(tmp_path, "ready", docker=True, metadata=True, tools=True)
    result = mod.check_server(ready)
    assert result.status == "ready" and result.tool_count == 1
    broken = make_server(tmp_path, "broken", source="def broken(:\n")
    result = mod.check_server(broken)
    assert result.status == "compile_error" and result.compile_error
    assert mod._normalize_name("User-East_Money") == "usereastmoney"


def test_reports_and_formatters(tmp_path, capsys):
    mcp = tmp_path / "mcp_servers"
    mcp.mkdir()
    make_server(mcp, "user-yfinance", docker=True, tools=True)
    make_server(mcp, "user_openalex")
    make_server(mcp, "broken", source="x = (")
    report = mod.check_all_servers(mcp)
    assert report["total_servers"] == 3
    assert report["servers_with_server_py"] == 3
    assert report["servers_with_dockerfile"] == 1
    assert report["summary"]["compile_error_count"] == 1
    priority = mod.get_priority_servers_report(mcp)
    assert priority["priority_count"] == 2
    single = mod.get_single_server_report(mcp, "user-yfinance")
    assert single["status"] == "ready"
    mod.print_summary_line(report)
    mod.print_json_report(report)
    mod.print_human_report(report)
    mod.print_single_server_report(single)
    output = capsys.readouterr().out
    assert "MCP Health:" in output and "user-yfinance" in output
    json.loads(mod.json.dumps(report))


def test_main_modes(tmp_path, monkeypatch, capsys):
    project = tmp_path
    mcp = project / "mcp_servers"
    mcp.mkdir()
    make_server(mcp, "user-yfinance", docker=True)

    for args in (
        ["health_check_mcp.py", "--summary", "--project-root", str(project)],
        ["health_check_mcp.py", "--json", "--project-root", str(project)],
        ["health_check_mcp.py", "--server", "user-yfinance", "--project-root", str(project)],
        ["health_check_mcp.py", "--server", "missing", "--project-root", str(project)],
        ["health_check_mcp.py", "--priority-only", "--summary", "--project-root", str(project)],
    ):
        monkeypatch.setattr(sys, "argv", args)
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 0
    assert "MCP Health" in capsys.readouterr().out
