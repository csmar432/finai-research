"""Shared empirical data root (FINAI_EMPIRICAL_DATA_ROOT).

Isolation agents repeatedly skipped local panels under ``/data/实证分析``
because fetchers never consulted this env. This module is the single resolver.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "EmpiricalDataRoot",
    "resolve_empirical_data_root",
    "scan_empirical_root",
    "find_candidate_files",
]

_DEFAULT_CANDIDATES = (
    "/data/实证分析",
    str(Path.home() / "data" / "实证分析"),
    "data/实证分析",
    "data",
)


@dataclass(frozen=True)
class EmpiricalDataRoot:
    path: Path | None
    source: str  # env | default | missing
    exists: bool
    readable: bool

    @property
    def available(self) -> bool:
        return bool(self.path and self.exists and self.readable)


def resolve_empirical_data_root(
    explicit: str | Path | None = None,
    *,
    env_var: str = "FINAI_EMPIRICAL_DATA_ROOT",
) -> EmpiricalDataRoot:
    """Resolve the shared empirical data directory (read-only usage)."""
    candidates: list[tuple[str, str]] = []
    if explicit:
        candidates.append((str(explicit), "explicit"))
    env_val = (os.environ.get(env_var) or "").strip()
    if env_val:
        candidates.append((env_val, "env"))
    for c in _DEFAULT_CANDIDATES:
        candidates.append((c, "default"))

    seen: set[str] = set()
    for raw, source in candidates:
        key = os.path.abspath(os.path.expanduser(raw))
        if key in seen:
            continue
        seen.add(key)
        p = Path(key)
        if p.is_dir():
            readable = os.access(p, os.R_OK)
            return EmpiricalDataRoot(path=p, source=source, exists=True, readable=readable)

    # Prefer env path even if missing (so reports show the intended root)
    if env_val:
        p = Path(os.path.expanduser(env_val)).resolve()
        return EmpiricalDataRoot(path=p, source="env", exists=False, readable=False)
    return EmpiricalDataRoot(path=None, source="missing", exists=False, readable=False)


def scan_empirical_root(
    root: EmpiricalDataRoot | Path | None = None,
    *,
    max_files: int = 200,
) -> list[Path]:
    """List data-like files under the empirical root (csv/parquet/dta/xlsx)."""
    if isinstance(root, EmpiricalDataRoot):
        base = root.path if root.available else None
    else:
        base = Path(root) if root else resolve_empirical_data_root().path
    if base is None or not base.is_dir():
        return []
    exts = {".csv", ".parquet", ".pq", ".dta", ".xlsx", ".xls", ".feather", ".pkl"}
    out: list[Path] = []
    try:
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() in exts and "__pycache__" not in p.parts:
                out.append(p)
                if len(out) >= max_files:
                    break
    except OSError:
        return []
    return out


def find_candidate_files(
    keywords: list[str],
    root: EmpiricalDataRoot | Path | None = None,
    *,
    limit: int = 20,
) -> list[Path]:
    """Find files whose path/name contains any keyword (case-insensitive)."""
    keys = [k.lower() for k in keywords if k]
    if not keys:
        return []
    hits: list[Path] = []
    for p in scan_empirical_root(root):
        hay = str(p).lower()
        if any(k in hay for k in keys):
            hits.append(p)
            if len(hits) >= limit:
                break
    return hits
