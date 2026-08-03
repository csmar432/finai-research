"""Behavior coverage for the interactive project entry helper."""

from __future__ import annotations

import importlib.util
import builtins
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "on_enter.py"


def load_module():
    spec = importlib.util.spec_from_file_location("finai_on_enter", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_calendar_covers_month_boundaries_and_release_windows(monkeypatch):
    module = load_module()
    seen = set()
    for current in (date(2026, 1, 2), date(2026, 1, 12), date(2026, 1, 20), date(2026, 12, 31)):
        monkeypatch.setattr(module, "date", type("FixedDate", (date,), {"today": classmethod(lambda cls, d=current: d)}))
        events = module._get_macro_today()
        assert events
        seen.update(event["name"] for event in events)
    assert seen >= {"US NFP", "US CPI", "CN PMI"}


def test_state_helpers_handle_missing_malformed_and_valid_state(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    assert module._check_daemon()["daemon_running"] is False
    assert module._get_pending_approvals() == 0

    data = tmp_path / "data"
    data.mkdir()
    (data / "event_monitor.pid").write_text("not-a-pid")
    (data / "event_trigger_state.json").write_text('{"pending": {"a": {}}, "run": {"timestamp": "now"}}')
    status = module._check_daemon()
    assert status["last_run"] == "now"
    assert module._get_pending_approvals() == 1

    (data / "event_trigger_state.json").write_text("{")
    assert module._check_daemon()["last_run"] is None
    assert module._get_pending_approvals() == 0
    monkeypatch.setattr(module, "_get_running_pipelines", lambda: ["a", "b"])
    assert module._get_running_pipelines() == ["a", "b"]


def test_render_helpers_and_actions(monkeypatch, tmp_path, capsys):
    module = load_module()
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "_get_running_pipelines", lambda: 2)
    monkeypatch.setattr(module, "_get_pending_approvals", lambda: 1)
    module.print_banner()
    module.print_macro_calendar([
        {"name": "A", "date": "today", "days": 0, "status": "TODAY"},
        {"name": "B", "date": "soon", "days": 2, "status": "upcoming"},
        {"name": "C", "date": "later", "days": "next month", "status": "upcoming"},
    ])
    module.print_status({"daemon_running": True, "pid": 12, "last_run": "now"})
    module.print_menu()
    output = capsys.readouterr().out
    assert "FinResearch" in output and "待审批" in output

    monkeypatch.setattr(module, "_check_daemon", lambda: {})
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "")
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(module, "_get_pending_approvals", lambda: 0)
    for choice in ("1", "2", "3", "4", "5", "7", "9", "invalid"):
        assert module.run_action(choice) is True
    assert len(calls) >= 6
    assert module.run_action("0") is False


def test_action_setup_and_approval_paths(monkeypatch, tmp_path):
    module = load_module()
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "_check_daemon", lambda: {})
    monkeypatch.setattr(module, "_get_pending_approvals", lambda: 1)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "run-1")
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda args, **kwargs: calls.append(args))
    (tmp_path / "config" / "daemon").mkdir(parents=True)
    (tmp_path / "config" / "daemon" / "setup-daemon.sh").write_text("#!/bin/sh\n")
    for choice in ("6", "8"):
        assert module.run_action(choice) is True
    assert any("--approve" in args for args in calls)


def test_research_prompt_and_main_exit(monkeypatch, tmp_path):
    module = load_module()
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "_check_daemon", lambda: {"daemon_running": False, "pid": None, "last_run": None})
    monkeypatch.setattr(module, "_get_running_pipelines", lambda: 0)
    monkeypatch.setattr(module, "_get_pending_approvals", lambda: 0)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: None)
    inputs = iter(["carbon pricing", ""])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(inputs))
    assert module.run_action("R") is True

    def end_input(_prompt=""):
        raise EOFError

    monkeypatch.setattr(builtins, "input", end_input)
    module.main()


def test_running_pipeline_fallback(monkeypatch):
    module = load_module()
    monkeypatch.setitem(__import__("sys").modules, "scripts.event_monitor", None)
    assert module._get_running_pipelines() == 0
