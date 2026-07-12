"""Sync skill docs across IDE target directories.

SSOT (single source of truth): knowledge/skills/
Mirrors:
  - .claude/skills/      (Claude Code)
  - .github/skills/      (GitHub Copilot, previously a hardcoded path)

Why three copies? Each AI tool has its own discovery convention:
  - Claude Code: reads .claude/skills/ (or the symlink we previously used).
    The symlink broke on Windows; this script ensures a real directory.
  - GitHub Copilot: reads .github/skills/ (some setups)
  - Cursor: reads .cursor/skills/ (separate, populated manually)

Run manually:  python scripts/sync_skills.py
CI:           enforced by scripts/audit_guard.py T006
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SSOT = PROJECT_ROOT / "knowledge" / "skills"
MIRRORS = [
    PROJECT_ROOT / ".claude" / "skills",
    PROJECT_ROOT / ".github" / "skills",
]


def sync_one(mirror: Path) -> tuple[int, int, int]:
    """Sync SSOT → mirror. Returns (copied, updated, removed)."""
    if not SSOT.exists():
        print(f"ERROR: SSOT not found: {SSOT}", file=sys.stderr)
        return (0, 0, 0)

    mirror.mkdir(parents=True, exist_ok=True)
    copied = updated = removed = 0

    src_files = {p.name: p for p in SSOT.glob("*.md")}
    dst_files = {p.name: p for p in mirror.glob("*.md")}

    # Copy / update files in SSOT
    for name, src in src_files.items():
        dst = mirror / name
        if not dst.exists():
            shutil.copy(src, dst)
            copied += 1
        elif src.read_bytes() != dst.read_bytes():
            shutil.copy(src, dst)
            updated += 1

    # Remove files in mirror that no longer exist in SSOT
    for name in dst_files.keys() - src_files.keys():
        (mirror / name).unlink()
        removed += 1

    return (copied, updated, removed)


def main() -> int:
    if not SSOT.exists():
        print(f"SSOT missing: {SSOT}", file=sys.stderr)
        return 1

    total_issues = 0
    for mirror in MIRRORS:
        copied, updated, removed = sync_one(mirror)
        rel = mirror.relative_to(PROJECT_ROOT)
        if copied or updated or removed:
            print(
                f"  {rel}: +{copied} copied, ~{updated} updated, -{removed} removed"
            )
            total_issues += copied + updated + removed
        else:
            print(f"  {rel}: in sync")

    if total_issues == 0:
        print("OK: all skill mirrors in sync with knowledge/skills/")
        return 0
    print(f"OK: synced ({total_issues} file changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())