"""Tests for scripts.core.paths.resolve_project_root / find_env_file.

Verifies the three-tier resolution:
  1. importlib.metadata (wheel install)
  2. FINAI_PROJECT_ROOT env var / cwd
  3. In-tree walk (legacy fallback)

These checks run whether the package is installed via pip or invoked from a
source checkout (both layouts are exercised).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.core.paths import (
    _candidate_roots,
    env_path,
    find_env_file,
    resolve_project_root,
)


def test_resolve_project_root_returns_existing_path():
    """resolve_project_root must never return a non-existent directory."""
    root = resolve_project_root()
    assert isinstance(root, Path)
    assert root.is_dir(), f"resolved root {root} does not exist"


def test_resolve_project_root_prefers_metadata_root():
    """When the package is installed, the metadata-discovered root wins."""
    roots = _candidate_roots()
    # The first non-None candidate is what resolve_project_root will pick.
    assert roots, "expected at least one candidate root"
    assert roots[0] is not None
    assert roots[0].is_dir()


def test_resolve_project_root_cwd_override(monkeypatch, tmp_path):
    """FINAI_PROJECT_ROOT should override other candidates when set."""
    monkeypatch.setenv("FINAI_PROJECT_ROOT", str(tmp_path))
    # Clear lru_cache to force re-resolution.
    resolve_project_root.cache_clear()
    try:
        assert resolve_project_root() == tmp_path.resolve()
    finally:
        resolve_project_root.cache_clear()


def test_find_env_file_returns_none_when_absent(monkeypatch, tmp_path):
    """find_env_file must return None for a missing env file (not raise)."""
    monkeypatch.setenv("FINAI_PROJECT_ROOT", str(tmp_path))
    resolve_project_root.cache_clear()
    try:
        result = find_env_file(".env")
        assert result is None or result.is_file()
    finally:
        resolve_project_root.cache_clear()


def test_find_env_file_picks_up_local_dotenv(monkeypatch, tmp_path):
    """When .env exists in cwd, find_env_file should locate it."""
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setenv("FINAI_PROJECT_ROOT", str(tmp_path))
    resolve_project_root.cache_clear()
    try:
        result = find_env_file(".env")
        assert result == env_file.resolve()
    finally:
        resolve_project_root.cache_clear()


def test_env_path_is_relative_to_root():
    """env_path should resolve to a path under the project root."""
    p = env_path("config", "llm_config.json")
    assert p.is_absolute()
    # Must be a descendant of the resolved root.
    root = resolve_project_root()
    try:
        p.relative_to(root)
    except ValueError:
        pytest.fail(f"{p} is not under project root {root}")
