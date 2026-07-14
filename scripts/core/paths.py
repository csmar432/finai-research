"""Project root resolution for both wheel and source-checkout layouts.

Three locations are probed in priority order:

1. ``importlib.metadata.distribution("finai-research-workflow").locate_file("")``
   — the canonical wheel-install root (``site-packages/`` or ``dist-packages/``).
   Works after ``pip install`` whether the package is editable or not.

2. ``Path.cwd()`` — the user's current working directory.  This is what most
   ad-hoc CLI invocations expect: ``python -m finai ...`` from a project
   directory will pick up a co-located ``.env``.

3. ``Path(__file__).resolve().parent.parent`` — the historical heuristic used
   throughout the codebase for source-checkout layouts (where ``scripts/``
   lives directly under the project root).  Kept as a final fallback so
   existing in-tree behaviour does not regress.

The first probe that yields an *existing* directory wins.  Callers should not
cache the result across fork() boundaries; resolve once per process.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

__all__ = [
    "resolve_project_root",
    "env_path",
    "find_env_file",
]

_PACKAGE_NAME = "finai-research-workflow"


@lru_cache(maxsize=1)
def resolve_project_root() -> Path:
    """Return the most plausible project root for the current process.

    Returns a ``Path`` that exists on disk (we never return a non-existent
    candidate).  Order: wheel install dir > cwd > in-tree ``__file__`` walk.
    """
    candidates = _candidate_roots()
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    # Last resort: cwd (always exists).
    return Path.cwd().resolve()


def _candidate_roots() -> list[Path | None]:
    roots: list[Path | None] = []

    # 0. FINAI_PROJECT_ROOT env var (highest priority when explicitly set).
    #    audit-fix-2026-07-14 PR-5: previously this was candidate [2] after
    #    wheel-install, so when the package was installed in site-packages,
    #    the env var was ignored. Tests/test_paths.py expects env var to win.
    cwd_env = os.environ.get("FINAI_PROJECT_ROOT")
    if cwd_env:
        roots.append(Path(cwd_env).expanduser().resolve())

    # 1. Wheel / installed layout via importlib.metadata.
    try:
        from importlib import metadata

        dist = metadata.distribution(_PACKAGE_NAME)
        # locate_file("") returns the package's *root* directory.
        # In a wheel install this is site-packages/; in an editable install
        # it is the source directory itself.
        loc = dist.locate_file("")
        if loc:
            roots.append(Path(str(loc)).resolve())
    except (metadata.PackageNotFoundError, OSError, ValueError):
        pass

    # 2. CWD override when FINAI_PROJECT_ROOT is unset.
    if not cwd_env:
        roots.append(Path.cwd().resolve())

    # 3. In-tree walk (the legacy behaviour used by scripts/<file>.py
    #    invocations from a source checkout).
    roots.append(Path(__file__).resolve().parent.parent.parent)

    return roots


def env_path(*parts: str) -> Path:
    """Return ``PROJECT_ROOT / *parts`` without forcing existence."""
    return resolve_project_root().joinpath(*parts)


def find_env_file(name: str = ".env") -> Path | None:
    """Return the first existing ``name`` candidate or ``None``.

    Searches, in order: ``FINAI_PROJECT_ROOT/<name>``, the cwd,
    then the resolved project root.  Used by both ``health_check`` and
    ``ai_router`` to read user secrets consistently.
    """
    roots = _candidate_roots()
    for r in roots:
        if r is None:
            continue
        p = Path(r) / name
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None
