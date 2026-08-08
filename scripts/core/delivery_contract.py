"""Canonical delivery package for isolation / agent-host runs.

Test agents wrote CODEX_FINAL.md, scattered figures, or only main.pdf without
SKIPPED_CONFIG / FINAL. This module validates the contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "DeliveryReport",
    "validate_delivery",
    "canonical_delivery_paths",
]

_REQUIRED = ("FINAL.md", "SKIPPED_CONFIG.md")
_OPTIONAL_PDF = ("main.pdf", "paper.pdf", "manuscript.pdf")


@dataclass
class DeliveryReport:
    ok: bool
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    found: dict[str, str] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = ["# Delivery contract", ""]
        lines.append(f"- status: {'OK' if self.ok else 'INCOMPLETE'}")
        if self.found:
            lines.append("- found:")
            for k, v in self.found.items():
                lines.append(f"  - {k}: `{v}`")
        if self.missing:
            lines.append("- missing:")
            for m in self.missing:
                lines.append(f"  - {m}")
        if self.warnings:
            lines.append("- warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        return "\n".join(lines)


def canonical_delivery_paths(output_dir: Path) -> dict[str, Path]:
    out = Path(output_dir)
    return {
        "FINAL.md": out / "FINAL.md",
        "SKIPPED_CONFIG.md": out / "SKIPPED_CONFIG.md",
        "DELIVERY.md": out / "DELIVERY.md",
    }


def validate_delivery(
    output_dir: str | Path,
    *,
    require_pdf: bool = False,
    allow_alias_final: bool = False,
) -> DeliveryReport:
    """Validate isolation delivery under output_dir."""
    root = Path(output_dir)
    missing: list[str] = []
    warnings: list[str] = []
    found: dict[str, str] = {}

    for name in _REQUIRED:
        p = root / name
        if p.is_file() and p.stat().st_size > 0:
            found[name] = str(p)
        else:
            # Common misuse: CODEX_FINAL.md instead of FINAL.md
            alias = root / "CODEX_FINAL.md"
            if name == "FINAL.md" and allow_alias_final and alias.is_file():
                warnings.append(
                    "Found CODEX_FINAL.md but contract requires FINAL.md; "
                    "copy/rename to FINAL.md."
                )
                found["CODEX_FINAL.md"] = str(alias)
                missing.append("FINAL.md")
            else:
                missing.append(name)

    pdf_hit = None
    for name in _OPTIONAL_PDF:
        # search shallow + one level
        for cand in [root / name, *root.glob(f"*/{name}"), *root.glob(f"**/{name}")]:
            if cand.is_file() and cand.stat().st_size > 0:
                pdf_hit = cand
                break
        if pdf_hit:
            break
    if pdf_hit:
        found["pdf"] = str(pdf_hit)
    elif require_pdf:
        missing.append("main.pdf (or paper.pdf)")
    else:
        warnings.append("No PDF found (optional unless require_pdf=True)")

    # Soft signal: figures directory empty while PDF claims charts
    fig_dirs = [root / "figures", root / "figs", *root.glob("*/figures")]
    if any(d.is_dir() and not any(d.iterdir()) for d in fig_dirs if d.is_dir()):
        warnings.append("Empty figures/ directory present")

    ok = not missing
    return DeliveryReport(ok=ok, missing=missing, warnings=warnings, found=found)
