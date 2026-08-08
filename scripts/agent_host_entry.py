#!/usr/bin/env python3
"""Agent-host / isolation-slot entry (non-interactive, fail-closed).

Use when the host agent must:
  - not ask the user
  - not use Mock for research conclusions
  - write output/SKIPPED_CONFIG.md + output/FINAL.md on blockers
  - avoid inventing a parallel pipeline outside FinAI

Examples:
  python scripts/agent_host_entry.py
  python scripts/agent_host_entry.py --topic "..." --output-dir output
  FINAI_NO_HITL=1 python scripts/agent_host_entry.py --topic "..."
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.core.agent_host_report import (  # noqa: E402
    SkipItem,
    blockers_from_diag,
    write_blocked_run,
)


def _read_topic_md(cwd: Path) -> str:
    for name in ("TOPIC.md", "topic.md"):
        p = cwd / name
        if p.is_file():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                # First non-empty, non-heading line as short topic; keep full text in report via file
                for line in text.splitlines():
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    return s[:300]
                return text[:300]
    return ""


def _resolve_topic(arg_topic: str | None, cwd: Path) -> str:
    if arg_topic and arg_topic.strip():
        return arg_topic.strip()
    from_md = _read_topic_md(cwd)
    if from_md:
        return from_md
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FinAI agent-host entry: fail-closed, writes SKIPPED_CONFIG.md / FINAL.md",
    )
    parser.add_argument("--topic", default="", help="Research topic (else read TOPIC.md)")
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory for SKIPPED_CONFIG.md / FINAL.md / pipeline artifacts",
    )
    parser.add_argument(
        "--venue",
        default="",
        help="Optional journal venue passed to agent_pipeline",
    )
    parser.add_argument(
        "--allow-mock",
        action="store_true",
        help="Explicitly allow Mock (demo only; forbidden for real research isolation slots)",
    )
    parser.add_argument(
        "--use-hitl",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="HITL gates (default off for agent-host batch; use --use-hitl to enable)",
    )
    parser.add_argument(
        "--dry-run-preflight",
        action="store_true",
        help="Only run health/preflight and write skip/final reports; do not start writing pipeline",
    )
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    topic = _resolve_topic(args.topic or None, cwd)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    completed = ["Resolved working directory", f"Output dir → {output_dir}"]
    if topic:
        completed.append(f"Topic resolved → {topic[:120]}")
    else:
        write_blocked_run(
            topic="",
            output_dir=output_dir,
            skipped=[
                SkipItem(
                    name="Topic",
                    reason="No --topic and no TOPIC.md with usable content.",
                    fix_hint="Pass --topic or create TOPIC.md in the working directory.",
                )
            ],
            completed_steps=completed,
            exit_code=2,
        )
        print("ERROR: missing topic (use --topic or TOPIC.md)", file=sys.stderr)
        print(f"Wrote {output_dir / 'SKIPPED_CONFIG.md'} and {output_dir / 'FINAL.md'}")
        return 2

    # Health / LLM preflight (no MCP server start)
    llm_available = False
    llm_status = ""
    try:
        from scripts.health_check import run_diagnostic

        diag = run_diagnostic()
        llm_available = bool(diag.llm_available)
        llm_status = getattr(diag, "llm_status", "") or ""
        completed.append(
            f"Health check → llm_available={llm_available}"
        )
    except Exception as exc:  # pragma: no cover - defensive
        llm_available = False
        llm_status = f"health_check failed: {exc}"
        completed.append(llm_status)

    allow_mock = bool(args.allow_mock) or os.environ.get("FINAI_ALLOW_MOCK") == "1"
    skipped = blockers_from_diag(
        llm_available=llm_available,
        llm_status=llm_status,
        allow_mock=allow_mock,
    )

    if skipped or args.dry_run_preflight:
        # dry-run with healthy LLM still writes a progress FINAL (not blocked)
        if args.dry_run_preflight and not skipped:
            from scripts.core.agent_host_report import HostRunReport, write_host_reports

            write_host_reports(
                HostRunReport(
                    topic=topic,
                    output_dir=output_dir,
                    status="partial",
                    skipped=[],
                    completed_steps=completed + ["dry-run-preflight: pipeline not started"],
                    boundaries=[
                        "Preflight only; writing/empirical pipeline not executed.",
                    ],
                    exit_code=0,
                )
            )
            print(f"Preflight OK. Reports in {output_dir}")
            return 0

        write_blocked_run(
            topic=topic,
            output_dir=output_dir,
            skipped=skipped
            or [
                SkipItem(
                    name="dry-run",
                    reason="--dry-run-preflight set",
                    fix_hint="Omit --dry-run-preflight to run the writing pipeline.",
                )
            ],
            completed_steps=completed,
            exit_code=4 if skipped else 0,
        )
        print(
            f"Blocked or dry-run. See {output_dir / 'SKIPPED_CONFIG.md'} "
            f"and {output_dir / 'FINAL.md'}",
            file=sys.stderr,
        )
        return 4 if skipped else 0

    # Proceed with official writing pipeline (batch defaults)
    from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

    if args.use_hitl:
        os.environ.pop("FINAI_NO_HITL", None)
    else:
        os.environ.setdefault("FINAI_NO_HITL", "1")

    config = AgentPipelineConfig(
        topic=topic,
        venue=args.venue or "通用",
        use_hitl=bool(args.use_hitl),
        hitl_stages=["outline", "literature", "draft"] if args.use_hitl else [],
        allow_mock=allow_mock,
        strict_llm=True,
    )
    pipeline = AgentPipeline(config=config)
    result = pipeline.run(topic=topic, output_dir=str(output_dir / "fin-manuscript"))

    interaction = getattr(result, "interaction", None)
    if interaction is not None and not result.success and not getattr(
        interaction, "llm_available", True
    ):
        write_blocked_run(
            topic=topic,
            output_dir=output_dir,
            skipped=blockers_from_diag(
                llm_available=False,
                llm_status="agent_pipeline refused to start without LLM",
                allow_mock=allow_mock,
            ),
            completed_steps=completed + ["agent_pipeline preflight refused run"],
            exit_code=4,
        )
        return 4

    if not result.success:
        write_blocked_run(
            topic=topic,
            output_dir=output_dir,
            skipped=[
                SkipItem(
                    name="agent_pipeline",
                    reason="; ".join(result.errors[:5]) or "pipeline returned success=False",
                    fix_hint="Inspect output/fin-manuscript and re-run with LLM configured.",
                )
            ],
            completed_steps=completed + ["agent_pipeline started but did not fully succeed"],
            exit_code=1,
        )
        return 1

    from scripts.core.agent_host_report import HostRunReport, write_host_reports

    write_host_reports(
        HostRunReport(
            topic=topic,
            output_dir=output_dir,
            status="completed",
            skipped=[],
            completed_steps=completed + ["agent_pipeline finished successfully"],
            boundaries=[
                "Writing pipeline artifacts are under output/fin-manuscript/.",
                "Empirical DID/IV stages remain a separate hand-off "
                "(research_framework / universal_data_fetcher).",
            ],
            exit_code=0,
        )
    )
    print(f"✅ Agent-host run completed. See {output_dir / 'FINAL.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
