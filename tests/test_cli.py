"""Tests for scripts.cli — finai-pipeline / finai-doctor entry points.

PR-1 added ``pipeline_cmd_wrapper`` (real argparse + agent_pipeline delegation)
and ``doctor_cmd`` (env / .env / llm_config.json source tracing).  These tests
exercise the new entry points without making real LLM or network calls.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path


from scripts.cli import (
    _mask,
    _read_dotenv_value,
    pipeline_cmd_wrapper,
)


# ── _mask ──────────────────────────────────────────────────────────────────


def test_mask_short_value():
    assert _mask("") == "***"
    assert _mask("a") == "***"
    assert _mask("abcd") == "***"


def test_mask_long_value_shows_head_and_tail():
    masked = _mask("sk-1234567890abcdef")
    assert masked.startswith("sk-1")
    assert masked.endswith("cdef")
    assert "..." in masked


# ── _read_dotenv_value ──────────────────────────────────────────────────────


def test_read_dotenv_value_handles_quotes_and_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment line\n"
        "DEEPSEEK_API_KEY=\"sk-abc\"\n"
        "EMPTY=\n"
        "PLAIN=value-no-quotes\n",
        encoding="utf-8",
    )
    assert _read_dotenv_value(env, "DEEPSEEK_API_KEY") == "sk-abc"
    assert _read_dotenv_value(env, "PLAIN") == "value-no-quotes"
    assert _read_dotenv_value(env, "EMPTY") == ""
    assert _read_dotenv_value(env, "MISSING") == ""


# ── pipeline_cmd_wrapper ───────────────────────────────────────────────────


def test_pipeline_cmd_wrapper_no_args_prints_help(capsys):
    rc = pipeline_cmd_wrapper([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "finai-pipeline" in out
    assert "--topic" in out


def test_pipeline_cmd_wrapper_help_flag(capsys):
    """``--help`` exits via argparse — accept either rc=0 or SystemExit."""
    with contextlib.suppress(SystemExit):
        pipeline_cmd_wrapper(["--help"])
    out = capsys.readouterr().out
    assert "finai-pipeline" in out or "topic" in out


# ── doctor_cmd ─────────────────────────────────────────────────────────────


def test_doctor_cmd_runs_without_llm(tmp_path, monkeypatch, capsys):
    """finai-doctor must work even with no DEEPSEEK_API_KEY configured.

    We isolate from the host environment by stripping every known LLM
    key and rebinding ``paths._candidate_roots`` so the resolver only
    sees the empty tmp dir.
    """
    keys = (
        "DEEPSEEK_API_KEY", "RELAY_API_KEY", "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", "TUSHARE_TOKEN", "EODHD_API_KEY",
        "FRED_API_KEY", "BRAVE_SEARCH_API_KEY", "NEWSAPI_API_KEY",
        "E2B_API_KEY",
    )
    for k in keys:
        monkeypatch.delenv(k, raising=False)
        os.environ.pop(k, None)
    monkeypatch.setenv("FINAI_PROJECT_ROOT", str(tmp_path))

    from scripts.core import paths as _paths
    from scripts.core.paths import resolve_project_root

    original = _paths._candidate_roots
    monkeypatch.setattr(
        _paths, "_candidate_roots",
        lambda: [Path(str(tmp_path)).resolve()],
    )
    resolve_project_root.cache_clear()
    try:
        from scripts.cli import doctor_cmd
        rc = doctor_cmd([])
    finally:
        resolve_project_root.cache_clear()
        monkeypatch.setattr(_paths, "_candidate_roots", original)

    out = capsys.readouterr().out
    assert "FinAI Doctor" in out
    # No LLM key configured → returns 4 (user-actionable exit code).
    assert rc == 4
    assert "DEEPSEEK_API_KEY" in out
