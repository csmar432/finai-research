"""mcp_servers/_shared/_version.py — Single source of truth for FinAI version.

Shared by all MCP server entry points to avoid hardcoded APP_VERSION drift.
When pyproject.toml bumps 0.2.0-alpha → 0.3.0, MCP servers auto-read the new
version on next start (no per-server edit required).

Usage:
    from mcp_servers._shared._version import APP_VERSION, APP_NAME
    server = Server(APP_NAME)
    logger.info(f"{APP_NAME} v{APP_VERSION} starting")

Design notes
------------
We use 5-tier fallback because MCP servers can be launched from:
  1. repo checkout (pyproject.toml exists)
  2. installed wheel (importlib.metadata)
  3. isolated PyPI env (no pyproject.toml, no metadata) → fallback to "0.0.0"
"""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

_APP_VERSION_CACHE: str | None = None


def _read_pyproject_version() -> str | None:
    """Try to read version from the TOP-LEVEL pyproject.toml (single source of truth).

    Walks up from this file looking for a pyproject.toml whose [project].name
    matches our top-level package name. This is important because
    mcp_servers/ has its OWN pyproject.toml (paper-workflow-mcp v1.0.0)
    which would otherwise be picked up first and cause version drift.

    Returns None if not found or mismatched.
    """
    try:
        cur = Path(__file__).resolve().parent
        for _ in range(8):  # at most 8 levels up
            candidate = cur / "pyproject.toml"
            if candidate.exists():
                text = candidate.read_text(encoding="utf-8")
                # ONLY accept files that declare our top-level package name.
                # This avoids the mcp_servers/pyproject.toml (paper-workflow-mcp)
                # which is a separate sub-package with its own version line.
                if 'name = "finai-research-workflow"' not in text and \
                   "name = 'finai-research-workflow'" not in text:
                    cur = cur.parent
                    continue
                # Found the correct top-level pyproject.toml
                try:
                    import tomllib  # py3.11+

                    with open(candidate, "rb") as f:
                        data = tomllib.load(f)
                    v = data.get("project", {}).get("version")
                    if v:
                        return str(v)
                except ImportError:
                    pass
                # Regex fallback (no tomllib)
                m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
                if m:
                    return m.group(1)
                return None
            cur = cur.parent
    except Exception:
        return None
    return None


def _read_metadata_version() -> str | None:
    """Try to read version from installed package metadata."""
    for pkg in ("finai-research-workflow", "finai_research_workflow"):
        try:
            return metadata.version(pkg)
        except metadata.PackageNotFoundError:
            continue
        except Exception:
            continue
    return None


def get_app_version() -> str:
    """Resolve FinAI package version with 3-tier fallback.

    Order:
      1. pyproject.toml (repo checkout)
      2. installed package metadata (pip install)
      3. "0.0.0+unknown" (last resort)
    """
    global _APP_VERSION_CACHE
    if _APP_VERSION_CACHE is not None:
        return _APP_VERSION_CACHE

    v = _read_pyproject_version() or _read_metadata_version() or "0.0.0+unknown"
    _APP_VERSION_CACHE = v
    return v


def get_app_name() -> str:
    """Project display name (immutable)."""
    return "FinAI Research Workflow"


# Public aliases (callers should use these)
APP_VERSION: str = get_app_version()
APP_NAME: str = get_app_name()


__all__ = ["APP_VERSION", "APP_NAME", "get_app_version", "get_app_name"]
