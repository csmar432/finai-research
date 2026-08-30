"""Canonical skip / progress reports for agent-host (non-interactive) runs.

Isolation slots often require: no questions, no mock, write SKIPPED_CONFIG.md /
FINAL.md, and stop cleanly when FinAI cannot proceed. Without these artifacts,
host agents freestyle outside the official pipeline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

__all__ = [
    "SkipItem",
    "HostRunReport",
    "write_host_reports",
    "blockers_from_diag",
    "write_blocked_run",
]


@dataclass
class SkipItem:
    name: str
    reason: str
    fix_hint: str = ""


@dataclass
class HostRunReport:
    topic: str
    output_dir: Path
    status: str  # "blocked" | "partial" | "completed"
    skipped: list[SkipItem] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    entry: str = "scripts/agent_host_entry.py"
    exit_code: int = 4

    @property
    def skipped_path(self) -> Path:
        return self.output_dir / "SKIPPED_CONFIG.md"

    @property
    def final_path(self) -> Path:
        return self.output_dir / "FINAL.md"


def write_host_reports(report: HostRunReport) -> tuple[Path, Path]:
    """Write SKIPPED_CONFIG.md and FINAL.md under output_dir. Returns paths."""
    out = Path(report.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    skipped_lines = [
        "# SKIPPED_CONFIG",
        "",
        f"> Generated: {ts}",
        f"> Entry: `{report.entry}`",
        f"> Topic: {report.topic or '(empty)'}",
        f"> Status: **{report.status}**",
        "",
        "FinAI refused to invent Mock data, fake citations, or a parallel pipeline.",
        "Items below were skipped because required configuration or tools are unavailable.",
        "",
    ]
    if report.skipped:
        skipped_lines += ["## Skipped items", ""]
        for i, item in enumerate(report.skipped, 1):
            skipped_lines.append(f"### {i}. {item.name}")
            skipped_lines.append(f"- **Reason**: {item.reason}")
            if item.fix_hint:
                skipped_lines.append(f"- **Fix**: {item.fix_hint}")
            skipped_lines.append("")
    else:
        skipped_lines += ["## Skipped items", "", "_None._", ""]

    final_lines = [
        "# FINAL — research progress report",
        "",
        f"> Generated: {ts}",
        f"> Entry: `{report.entry}`",
        f"> Topic: {report.topic or '(empty)'}",
        f"> Status: **{report.status}**",
        f"> Exit code: `{report.exit_code}`",
        "",
        "## Completed steps",
        "",
    ]
    if report.completed_steps:
        final_lines += [f"- {s}" for s in report.completed_steps]
    else:
        final_lines.append("- _(none — run blocked before research stages)_")
    final_lines += ["", "## Boundaries / non-claims", ""]
    bounds = list(report.boundaries) or [
        "No Mock / synthetic research conclusions were produced.",
        "No fabricated literature, coefficients, or citations were written.",
        "Official FinAI writing pipeline was not started while blockers remain.",
    ]
    final_lines += [f"- {b}" for b in bounds]
    final_lines += [
        "",
        "## Artifacts",
        "",
        f"- Skip log: `{report.skipped_path.name}`",
        f"- This report: `{report.final_path.name}`",
        "",
        "## Next actions",
        "",
    ]
    # Autopilot / isolation: do not imply chat confirmation or freestyle empirics.
    autopilot = os.environ.get("FINAI_AUTOPILOT", "").strip() in {"1", "true", "yes"}
    if autopilot or report.entry.endswith("agent_host_entry.py"):
        final_lines += [
            "1. If blocked: fix SKIPPED items, then re-run "
            "python scripts/agent_host_entry.py. Prefer official FinAI entrypoints.",
            "2. If partial with empirics hard-gaps: writing may exist; "
            "do not claim causal DID/IV or substitute proxy outcomes "
            "(city patents / overseas revenue / interest coverage).",
            "3. Empirics: set FINAI_EMPIRICAL_DATA_ROOT, then deepen inside FinAI via "
            "python -m scripts.research_framework.enhanced_pipeline --explore --panel <path> "
            "(local->MCP redundancy + multi-estimator suite). "
            "Do not invent a second stack outside FinAI APIs.",
            "4. Delivery contract requires FINAL.md + SKIPPED_CONFIG.md "
            "(not CODEX_FINAL.md alone).",
            "",
        ]
    else:
        final_lines += [
            "1. Configure at least one LLM (DEEPSEEK_API_KEY or RELAY_API_KEY or Ollama).",
            "2. Re-run: python scripts/agent_host_entry.py --topic '...'",
            "3. Interactive path (human TTY): python scripts/start_research.py --topic '...'",
            "",
        ]

    skipped_path = report.skipped_path
    final_path = report.final_path
    skipped_path.write_text("\n".join(skipped_lines), encoding="utf-8")
    final_path.write_text("\n".join(final_lines), encoding="utf-8")
    return skipped_path, final_path


def blockers_from_diag(
    *,
    llm_available: bool,
    llm_status: str = "",
    allow_mock: bool = False,
) -> list[SkipItem]:
    """Map health/preflight signals to skip items."""
    items: list[SkipItem] = []
    if not llm_available and not allow_mock:
        items.append(
            SkipItem(
                name="LLM / writing pipeline",
                reason=llm_status
                or "No external LLM configured and Ollama is not running; mock is disabled.",
                fix_hint=(
                    "Set DEEPSEEK_API_KEY or RELAY_API_KEY in .env.local, "
                    "or run `ollama serve`. Do not use --allow-mock for real research."
                ),
            )
        )
    return items


def write_blocked_run(
    *,
    topic: str,
    output_dir: str | Path,
    skipped: Sequence[SkipItem],
    completed_steps: Sequence[str] | None = None,
    entry: str = "scripts/agent_host_entry.py",
    exit_code: int = 4,
) -> HostRunReport:
    report = HostRunReport(
        topic=topic,
        output_dir=Path(output_dir),
        status="blocked",
        skipped=list(skipped),
        completed_steps=list(completed_steps or []),
        entry=entry,
        exit_code=exit_code,
    )
    write_host_reports(report)
    return report
