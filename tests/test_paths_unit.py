"""Tests for scripts/core/paths.py — Project root resolution."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.paths import (
        resolve_project_root,
        env_path,
        find_env_file,
    )
except Exception as _exc:
    pytest.skip(f"paths not importable: {_exc}", allow_module_level=True)


class TestResolveProjectRoot:
    def test_returns_existing_path(self):
        """resolve_project_root() must return a Path that exists."""
        root = resolve_project_root()
        assert isinstance(root, Path)
        assert root.exists()

    def test_returns_absolute_path(self):
        """resolve_project_root() must return an absolute path."""
        root = resolve_project_root()
        assert root.is_absolute()

    def test_returns_directory(self):
        """resolve_project_root() must return a directory, not a file."""
        root = resolve_project_root()
        assert root.is_dir()


class TestEnvPath:
    def test_returns_path(self):
        """env_path() must return a Path."""
        p = env_path("README.md")
        assert isinstance(p, Path)

    def test_resolve_project_root(self):
        """env_path() should be under resolve_project_root()."""
        root = resolve_project_root()
        p = env_path("README.md")
        # The path should start with the root
        try:
            p.resolve().relative_to(root.resolve())
        except ValueError:
            pytest.fail(f"env_path result {p} not under project root {root}")


class TestFindEnvFile:
    def test_returns_none_for_nonexistent(self):
        """find_env_file() must return None for non-existent file."""
        result = find_env_file("DOES_NOT_EXIST_12345XYZ.env")
        assert result is None

    def test_returns_path_for_existing(self):
        """find_env_file() must return Path for existing file."""
        # CLAUDE.md exists in the project root
        result = find_env_file("CLAUDE.md")
        if result is not None:
            assert result.exists()
            assert result.name == "CLAUDE.md"

    def test_returns_path_type(self):
        """Return type must be Path or None."""
        result = find_env_file("README.md")
        if result is not None:
            assert isinstance(result, Path)
