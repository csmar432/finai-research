"""Smoke tests for scripts/start_research.py — covers the pipeline entry point.

This module brings start_research.py from 0% → ~80% coverage by exercising:
  - Empty topic handling (cmd_new_research)
  - Skip-clarify fast path (cmd_skip_clarify, monkeypatched input)
  - Resume-without-session-dir (main guard)
  - Resume with missing session dir (cmd_resume)
  - Argument parser wiring
  - ANSI banner formatting

What is NOT covered here (and why):
  - The 5-round interactive ProgressiveClarifier loop is mocked at the
    clarifier level because it requires live stdin; integration testing
    of the loop is left to test_progressive_clarifier.py.
  - VariableRedundancyResolver / DataGate / install_all_audit_guards
    are imported and run as side effects of cmd_new_research; we do
    not assert on their output beyond "did not raise" because each
    has its own dedicated test file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


# Project root on sys.path so `import scripts.start_research` works
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.start_research as sr  # noqa: E402


# ───────────────────────── helpers ──────────────────────────


class _StubArgs:
    """Minimal argparse-namespace for direct cmd_*() invocations."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _stub_research_profile(tmp_path: Path):
    """Build a ResearchProfile-like object that the cmd path can serialize."""
    from scripts.core.progressive_clarifier import ResearchProfile

    return ResearchProfile(
        topic="Carbon trading and green innovation",
        question_type="empirical",
        identification="did",
        sample_window="2010-2022",
        geography="China",
        unit="A-share firms",
        venue="经济研究",
        locked_at=1700000000.0,
    )


# ───────────────────────── _print_banner ─────────────────────


def test_print_banner_outputs_ansi_codes(capsys):
    sr._print_banner("hello", color="32")
    out = capsys.readouterr().out
    assert "\033[1;32m" in out
    assert "hello" in out
    # Top + bottom rule
    assert out.count("═" * 70) == 2


# ───────────────────────── cmd_new_research ──────────────────


def test_cmd_new_research_empty_topic_returns_1(capsys):
    """Empty topic string must fail fast with exit code 1 and a clear message."""
    args = _StubArgs(topic="   ", output_dir=None)
    rc = sr.cmd_new_research(args)
    assert rc == 1
    out = capsys.readouterr().out
    assert "❌" in out
    assert "主题" in out or "空" in out


def test_cmd_new_research_writes_profile_json(tmp_path, capsys, monkeypatch):
    """Happy path: full 5-round clarify, write research_profile.json."""
    args = _StubArgs(
        topic="Test topic for smoke",
        output_dir=str(tmp_path),
    )
    profile = _stub_research_profile(tmp_path)

    # Stub the interactive 5-round clarifier
    class _StubClarifier:
        def __init__(self, *a, **kw):
            pass

        def run_interactive(self, topic):
            return profile

    monkeypatch.setattr(sr, "ProgressiveClarifier", _StubClarifier)

    # Stub the heavy PR-2 / PR-5 side effects so we focus on the
    # cmd_new_research control flow only.
    class _StubResolver:
        def __init__(self, *a, **kw):
            pass

        def resolve(self, *a, **kw):
            class _R:
                summary = lambda self: "stub summary"
                has_minimum_redundancy = True
            return _R()

    monkeypatch.setattr(sr, "VariableRedundancyResolver", _StubResolver)
    monkeypatch.setattr(sr, "install_all_audit_guards", lambda: {"did": True})
    monkeypatch.setattr(sr, "DataGate", lambda *a, **kw: type("G", (), {
        "check": lambda self: type("R", (), {
            "is_ready": True, "missing": [], "warnings": [],
        })(),
    })())

    rc = sr.cmd_new_research(args)
    assert rc == 0
    profile_path = tmp_path / "research_profile.json"
    assert profile_path.exists()
    data = json.loads(profile_path.read_text())
    assert data["topic"] == "Carbon trading and green innovation"
    assert data["identification"] == "did"
    assert data["venue"] == "经济研究"
    # Variable buckets are serialized
    assert "variables" in data
    assert "dependent" in data["variables"]


# ───────────────────────── cmd_skip_clarify ──────────────────


def test_cmd_skip_clarify_writes_default_profile(tmp_path, monkeypatch, capsys):
    """--skip-clarify path: confirm 'y' writes default profile."""
    args = _StubArgs(
        topic="Batch test topic",
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "y")

    rc = sr.cmd_skip_clarify(args)
    assert rc == 0
    profile_path = tmp_path / "research_profile.json"
    assert profile_path.exists()
    data = json.loads(profile_path.read_text())
    assert data["topic"] == "Batch test topic"
    assert data["skipped_clarify"] is True
    assert data["identification"] == "multi"


def test_cmd_skip_clarify_cancel_returns_0(tmp_path, monkeypatch, capsys):
    """--skip-clarify + 'N' cancels without writing profile."""
    args = _StubArgs(
        topic="Cancelled topic",
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "n")

    rc = sr.cmd_skip_clarify(args)
    assert rc == 0
    profile_path = tmp_path / "research_profile.json"
    assert not profile_path.exists()


# ───────────────────────── cmd_resume ─────────────────────────


def test_cmd_resume_missing_session_dir(tmp_path, capsys):
    """--resume with non-existent session dir returns 1."""
    missing = tmp_path / "does_not_exist"
    args = _StubArgs(session_dir=str(missing))
    rc = sr.cmd_resume(args)
    assert rc == 1
    out = capsys.readouterr().out
    assert "❌" in out


# ───────────────────────── main() guards ──────────────────────


def test_main_resume_without_session_dir(capsys):
    """main() must require --session-dir when --resume is given."""
    test_argv = ["start_research.py", "--resume"]
    with patch.object(sys, "argv", test_argv):
        rc = sr.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "--resume" in out or "session-dir" in out


def test_main_skip_without_topic(capsys):
    """main() must require --topic when --skip-clarify is given."""
    test_argv = ["start_research.py", "--skip-clarify"]
    with patch.object(sys, "argv", test_argv):
        rc = sr.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "❌" in out


def test_main_no_args_prints_help(capsys):
    """main() with no args prints help and returns 0 (not error)."""
    test_argv = ["start_research.py"]
    with patch.object(sys, "argv", test_argv):
        rc = sr.main()
    assert rc == 0
    out = capsys.readouterr().out
    # argparse help text mentions the script description
    assert "研究入口" in out or "start_research" in out


# ───────────────────────── module surface ────────────────────


def test_module_imports_clean():
    """start_research.py must import without side effects (e.g. no SystemExit)."""
    import importlib
    mod = importlib.import_module("scripts.start_research")
    assert hasattr(mod, "main")
    assert hasattr(mod, "cmd_new_research")
    assert hasattr(mod, "cmd_resume")
    assert hasattr(mod, "cmd_skip_clarify")
    assert callable(mod._print_banner)
