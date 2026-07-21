"""Runtime bootstrap for entry-point scripts.

This module ensures that:
  1. The project root is on ``sys.path`` so ``from scripts.xxx import ...`` works
     without requiring ``pip install -e .`` first.
  2. The stdlib ``platform`` module is not shadowed by ``scripts/core/platform.py``
     when an entry script is invoked directly (e.g. ``python scripts/agent_pipeline.py``).

Import this module FIRST in any entry-point script that lives in ``scripts/`` or
``scripts/<subdir>/``::

    from _bootstrap import bootstrap
    bootstrap()  # idempotent
"""
from __future__ import annotations

import sys
from pathlib import Path


_BOOTSTRAPPED = False


def bootstrap() -> None:
    """Insert project root into ``sys.path`` and clear shadowing entries.

    Idempotent — safe to call multiple times. Must be invoked before any
    ``from scripts.xxx import ...`` statement.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    # Project root is two levels up from this file: scripts/core/_bootstrap.py
    here = Path(__file__).resolve()
    project_root = here.parent.parent.parent
    project_root_str = str(project_root)
    scripts_core_dir = str(here.parent)

    # Remove any sys.path entries that would shadow stdlib ``platform``.
    # Specifically: when a script in scripts/ is run directly, Python prepends
    # the script's directory to sys.path. That makes scripts/core/ reachable
    # as a top-level package, which means ``import platform`` inside transitive
    # deps may resolve to scripts/core/platform.py instead of the stdlib.
    cleaned = []
    for entry in sys.path:
        if entry in (scripts_core_dir, str(here.parent.parent)):
            # Will be re-inserted via project_root below
            continue
        cleaned.append(entry)
    sys.path[:] = cleaned

    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    _BOOTSTRAPPED = True


# Eager-bootstrap on import so callers can simply do ``import _bootstrap``.
bootstrap()


def is_venv_active() -> bool:
    """Return True if a virtualenv is active (sys.prefix != base_prefix)."""
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)
