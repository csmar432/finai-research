"""Sync skill docs across IDE target directories.

SSOT (single source of truth): knowledge/skills/  (legacy docs)
   and .cursor/skills/        (canonical operational SKILL.md format)
Mirrors:
  - .claude/skills/      (Claude Code — flat .md docs)
  - .github/skills/      (GitHub Copilot — flat .md docs)
  - .agents/skills/      (OpenAI Codex — operational SKILL.md folders)

Why three targets? Each AI tool has its own discovery convention:
  - Claude Code: reads .claude/skills/ — flat .md files, no frontmatter.
  - GitHub Copilot: reads .github/skills/ — same flat format.
  - OpenAI Codex: reads .agents/skills/<name>/SKILL.md — directory per skill
    with YAML frontmatter (name + description).

The Codex format is the strictest because it requires:
  - SKILL.md (capital S, capital M, lowercase d)
  - YAML frontmatter with `name` and `description`
  - Directory per skill, not flat files
The Cursor `.cursor/skills/<name>/SKILL.md` format already matches this — we
mirror that exactly to .agents/skills/.

Run manually:  python scripts/sync_skills.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SSOT_DOCS = PROJECT_ROOT / "knowledge" / "skills"            # flat .md docs (Claude/Copilot)
SSOT_OPS = PROJECT_ROOT / ".cursor" / "skills"               # operational SKILL.md (Codex)
DOC_MIRRORS = [                                              # flat .md targets
    PROJECT_ROOT / ".claude" / "skills",
    PROJECT_ROOT / ".github" / "skills",
]
OP_MIRRORS = [                                               # SKILL.md folder targets
    PROJECT_ROOT / ".agents" / "skills",  # Codex
]


def sync_docs(mirror: Path) -> tuple[int, int, int]:
    """Sync knowledge/skills/*.md → <mirror>/*.md. Returns (copied, updated, removed)."""
    if not SSOT_DOCS.exists():
        print(f"ERROR: SSOT_DOCS not found: {SSOT_DOCS}", file=sys.stderr)
        return (0, 0, 0)
    mirror.mkdir(parents=True, exist_ok=True)
    copied = updated = removed = 0
    src_files = {p.name: p for p in SSOT_DOCS.glob("*.md")}
    dst_files = {p.name: p for p in mirror.glob("*.md")}
    for name, src in src_files.items():
        dst = mirror / name
        if not dst.exists():
            shutil.copy(src, dst); copied += 1
        elif src.read_bytes() != dst.read_bytes():
            shutil.copy(src, dst); updated += 1
    for name in dst_files.keys() - src_files.keys():
        (mirror / name).unlink(); removed += 1
    return (copied, updated, removed)


def sync_ops(mirror: Path) -> tuple[int, int, int]:
    """Sync .cursor/skills/<name>/SKILL.md → <mirror>/<name>/SKILL.md (Codex format)."""
    if not SSOT_OPS.exists():
        print(f"ERROR: SSOT_OPS not found: {SSOT_OPS}", file=sys.stderr)
        return (0, 0, 0)
    mirror.mkdir(parents=True, exist_ok=True)
    copied = updated = removed = 0
    src_skill_dirs = {p.name: p for p in SSOT_OPS.iterdir() if p.is_dir() and (p / "SKILL.md").exists()}
    dst_skill_dirs = {p.name: p for p in mirror.iterdir() if p.is_dir()}
    for name, src_dir in src_skill_dirs.items():
        dst_dir = mirror / name
        dst_dir.mkdir(parents=True, exist_ok=True)
        # Copy entire directory contents
        for src_file in src_dir.iterdir():
            dst_file = dst_dir / src_file.name
            if src_file.is_file():
                if not dst_file.exists():
                    shutil.copy(src_file, dst_file); copied += 1
                elif src_file.read_bytes() != dst_file.read_bytes():
                    shutil.copy(src_file, dst_file); updated += 1
    for name in dst_skill_dirs.keys() - src_skill_dirs.keys():
        shutil.rmtree(mirror / name); removed += 1
    return (copied, updated, removed)


def main() -> int:
    rc = 0
    total = 0
    print(f"SSOT_DOCS = {SSOT_DOCS.relative_to(PROJECT_ROOT)}")
    print(f"SSOT_OPS  = {SSOT_OPS.relative_to(PROJECT_ROOT)}")
    print()
    for m in DOC_MIRRORS:
        c, u, r = sync_docs(m)
        rel = m.relative_to(PROJECT_ROOT)
        if c or u or r:
            print(f"  {rel}: +{c} copied, ~{u} updated, -{r} removed")
            total += c + u + r
        else:
            print(f"  {rel}: in sync")
    for m in OP_MIRRORS:
        c, u, r = sync_ops(m)
        rel = m.relative_to(PROJECT_ROOT)
        if c or u or r:
            print(f"  {rel}: +{c} copied, ~{u} updated, -{r} removed (Codex format)")
            total += c + u + r
        else:
            print(f"  {rel}: in sync (Codex format)")
    if total == 0:
        print("\nOK: all skill mirrors in sync with knowledge/skills/ + .cursor/skills/")
    else:
        print(f"\nOK: synced ({total} file changes)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
