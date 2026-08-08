#!/usr/bin/env python3
"""Agent-host / isolation-slot entry (non-interactive, fail-closed).

Use when the host agent must:
  - not ask the user
  - not use Mock for research conclusions
  - write output/SKIPPED_CONFIG.md + output/FINAL.md on blockers
  - avoid inventing a parallel pipeline outside FinAI
  - check FINAI_EMPIRICAL_DATA_ROOT and TOPIC hard requirements before
    claiming causal empirics

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


def _read_topic_md_full(cwd: Path) -> str:
    for name in ("TOPIC.md", "topic.md"):
        p = cwd / name
        if p.is_file():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return text
    return ""


def _short_topic(text: str) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return s[:300]
    return text[:300]


def _resolve_topic(arg_topic: str | None, cwd: Path) -> tuple[str, str]:
    """Return (short_topic, full_text_for_integrity)."""
    if arg_topic and arg_topic.strip():
        t = arg_topic.strip()
        full = _read_topic_md_full(cwd)
        # Prefer full TOPIC.md for integrity when present; short topic for reports
        return t[:300], full or t
    full = _read_topic_md_full(cwd)
    if full:
        return _short_topic(full), full
    return "", ""


def _assess_host_context(
    topic_full: str,
    completed: list[str],
) -> tuple[list[SkipItem], list[str], object | None]:
    """Empirical root + TOPIC integrity → skip items and boundaries."""
    skipped: list[SkipItem] = []
    boundaries: list[str] = []
    integrity = None

    try:
        from scripts.core.empirical_data_root import resolve_empirical_data_root

        root = resolve_empirical_data_root()
        if root.available:
            completed.append(
                f"Empirical data root → {root.path} (source={root.source})"
            )
        else:
            completed.append(
                f"Empirical data root unavailable "
                f"(source={root.source}, path={root.path})"
            )
            skipped.append(
                SkipItem(
                    name="FINAI_EMPIRICAL_DATA_ROOT",
                    reason=(
                        "Shared empirical data directory not found/readable. "
                        "Isolation agents must check local panels before remote fetch "
                        "or proxy substitution."
                    ),
                    fix_hint=(
                        "export FINAI_EMPIRICAL_DATA_ROOT=/data/实证分析 "
                        "(or your panel directory) before empirics."
                    ),
                )
            )
            boundaries.append(
                "No local empirical root — do not freestyle proxy DID/IV; "
                "writing may still proceed."
            )
    except Exception as exc:  # pragma: no cover
        completed.append(f"empirical_data_root failed: {exc}")

    try:
        from scripts.core.topic_integrity import assess_topic_integrity

        integrity = assess_topic_integrity(topic_full)
        completed.append(
            f"TOPIC integrity → requirements={integrity.requirements} "
            f"gaps={integrity.hard_gaps} proxies={len(integrity.proxy_warnings)}"
        )
        for item in integrity.to_skipped_items():
            skipped.append(
                SkipItem(
                    name=item["item"],
                    reason=item["reason"],
                    fix_hint=item.get("fix_hint", ""),
                )
            )
        for w in integrity.proxy_warnings:
            skipped.append(
                SkipItem(
                    name=f"proxy_warning:{w.split(':')[0]}",
                    reason=w,
                    fix_hint=(
                        "Remove proxy-laundered empirics; obtain the required panel "
                        "or narrow TOPIC."
                    ),
                )
            )
        if integrity.hard_gaps:
            boundaries.append(
                "TOPIC hard-gaps present — writing OK with explicit non-claims; "
                "causal empirics / journal-ready causal PDF forbidden until gaps close."
            )
    except Exception as exc:  # pragma: no cover
        completed.append(f"topic_integrity failed: {exc}")

    return skipped, boundaries, integrity


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
    parser.add_argument(
        "--block-on-topic-gaps",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "If TOPIC hard empirics requirements lack local panels, block the whole run "
            "(default: record skips, allow writing with non-claims)"
        ),
    )
    parser.add_argument(
        "--check-delivery",
        action="store_true",
        help="After run (or alone with --dry-run-preflight), validate delivery contract",
    )
    args = parser.parse_args(argv)

    # Isolation default: autopilot wording in FINAL.md
    os.environ.setdefault("FINAI_AUTOPILOT", "1")

    cwd = Path.cwd()
    topic, topic_full = _resolve_topic(args.topic or None, cwd)
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

    context_skips, context_bounds, integrity = _assess_host_context(
        topic_full or topic, completed
    )

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

    hard_empirics_gaps = bool(
        integrity and getattr(integrity, "hard_gaps", None)
    )
    if args.block_on_topic_gaps and hard_empirics_gaps:
        for s in context_skips:
            if s.name.startswith("empirics:") or s.name.startswith("proxy_warning:"):
                skipped.append(s)

    if skipped or args.dry_run_preflight:
        # dry-run with healthy LLM still writes a progress FINAL (not blocked)
        if args.dry_run_preflight and not skipped:
            from scripts.core.agent_host_report import HostRunReport, write_host_reports

            # Still surface non-blocking context skips (data root / soft gaps)
            soft = [
                s
                for s in context_skips
                if not s.name.startswith("LLM")
            ]
            write_host_reports(
                HostRunReport(
                    topic=topic,
                    output_dir=output_dir,
                    status="partial",
                    skipped=soft,
                    completed_steps=completed + ["dry-run-preflight: pipeline not started"],
                    boundaries=context_bounds
                    + [
                        "Preflight only; writing/empirical pipeline not executed.",
                    ],
                    exit_code=0,
                )
            )
            if args.check_delivery:
                from scripts.core.delivery_contract import validate_delivery

                rep = validate_delivery(output_dir)
                (output_dir / "DELIVERY.md").write_text(rep.to_markdown(), encoding="utf-8")
            print(f"Preflight OK. Reports in {output_dir}")
            return 0

        merged = list(skipped)
        seen = {s.name for s in merged}
        for s in context_skips:
            if s.name not in seen:
                merged.append(s)
                seen.add(s.name)
        write_blocked_run(
            topic=topic,
            output_dir=output_dir,
            skipped=merged
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
        if args.check_delivery:
            from scripts.core.delivery_contract import validate_delivery

            rep = validate_delivery(output_dir)
            (output_dir / "DELIVERY.md").write_text(rep.to_markdown(), encoding="utf-8")
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
            )
            + context_skips,
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
            ]
            + context_skips,
            completed_steps=completed + ["agent_pipeline started but did not fully succeed"],
            exit_code=1,
        )
        return 1

    from scripts.core.agent_host_report import HostRunReport, write_host_reports

    # Writing success + empirics hard-gaps → partial (not "completed" causal paper)
    status = "partial" if context_skips else "completed"
    bounds = list(context_bounds) + [
        "Writing pipeline artifacts are under output/fin-manuscript/.",
        "Empirical DID/IV stages remain a separate hand-off "
        "(research_framework / universal_data_fetcher + FINAI_EMPIRICAL_DATA_ROOT).",
    ]
    write_host_reports(
        HostRunReport(
            topic=topic,
            output_dir=output_dir,
            status=status,
            skipped=context_skips,
            completed_steps=completed + ["agent_pipeline finished successfully"],
            boundaries=bounds,
            exit_code=0,
        )
    )
    if args.check_delivery:
        from scripts.core.delivery_contract import validate_delivery

        rep = validate_delivery(output_dir)
        (output_dir / "DELIVERY.md").write_text(rep.to_markdown(), encoding="utf-8")
    print(
        f"{'⚠️ Partial' if status == 'partial' else '✅'} Agent-host run finished. "
        f"See {output_dir / 'FINAL.md'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
