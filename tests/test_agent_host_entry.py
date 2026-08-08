"""Tests for agent-host fail-closed entry and skip reports."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_write_blocked_run_creates_artifacts(tmp_path: Path):
    from scripts.core.agent_host_report import SkipItem, write_blocked_run

    report = write_blocked_run(
        topic="carbon trading",
        output_dir=tmp_path,
        skipped=[
            SkipItem(
                name="LLM",
                reason="no key",
                fix_hint="set DEEPSEEK_API_KEY",
            )
        ],
        exit_code=4,
    )
    assert report.skipped_path.is_file()
    assert report.final_path.is_file()
    skipped = report.skipped_path.read_text(encoding="utf-8")
    final = report.final_path.read_text(encoding="utf-8")
    assert "SKIPPED_CONFIG" in skipped
    assert "no key" in skipped
    assert "DEEPSEEK_API_KEY" in skipped
    assert "carbon trading" in final
    assert "blocked" in final
    assert "No Mock" in final


def test_agent_host_entry_missing_topic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    from scripts.agent_host_entry import main

    code = main(["--output-dir", str(tmp_path / "output")])
    assert code == 2
    assert (tmp_path / "output" / "SKIPPED_CONFIG.md").is_file()
    assert (tmp_path / "output" / "FINAL.md").is_file()
    assert "Topic" in (tmp_path / "output" / "SKIPPED_CONFIG.md").read_text()


def test_agent_host_entry_reads_topic_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "TOPIC.md").write_text("# T\n\nAJR institutions and growth\n", encoding="utf-8")
    from scripts.agent_host_entry import main

    with patch("scripts.health_check.run_diagnostic") as diag:
        diag.return_value = MagicMock(llm_available=False, llm_status="no llm")
        code = main(["--output-dir", str(tmp_path / "output"), "--dry-run-preflight"])
    assert code == 4
    text = (tmp_path / "output" / "SKIPPED_CONFIG.md").read_text(encoding="utf-8")
    assert "AJR institutions" in text or "LLM" in text
    assert "FINAL.md" in (tmp_path / "output" / "FINAL.md").name


def test_agent_host_entry_preflight_ok_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    from scripts.agent_host_entry import main

    with patch("scripts.health_check.run_diagnostic") as diag:
        diag.return_value = MagicMock(llm_available=True, llm_status="ok")
        code = main(
            [
                "--topic",
                "test topic",
                "--output-dir",
                str(tmp_path / "output"),
                "--dry-run-preflight",
            ]
        )
    assert code == 0
    final = (tmp_path / "output" / "FINAL.md").read_text(encoding="utf-8")
    assert "partial" in final
    assert "Preflight" in final or "dry-run" in final


def test_agent_pipeline_exit4_writes_skip_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """CLI exit 4 path must leave SKIPPED_CONFIG.md for host agents."""
    from scripts.agent_pipeline import (
        AgentPipelineConfig,
        AgentPipelineResult,
        InteractionResult,
    )
    import scripts.agent_pipeline as ap

    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = AgentPipelineResult(
        config=AgentPipelineConfig(topic="t"),
        success=False,
        errors=["no llm"],
        interaction=InteractionResult(
            needs_input=True,
            action_needed="ask_llm_confirm",
            llm_available=False,
        ),
    )
    monkeypatch.setattr(ap, "AgentPipeline", lambda *a, **k: mock_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "agent_pipeline.py",
            "--topic",
            "t",
            "--output-dir",
            str(tmp_path),
        ],
    )
    code = ap.main()
    assert code == 4
    assert (tmp_path / "SKIPPED_CONFIG.md").is_file()
    assert (tmp_path / "FINAL.md").is_file()
