"""Unit tests for scripts/count_mcp.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.count_mcp import (
    CACHE_DIR,
    CACHE_FILE,
    MCP_ROOT,
    PROJECT_ROOT,
    count_mcp_directories,
    write_cache,
)


class TestConstants:
    """Module constants."""

    def test_project_root_is_path(self):
        assert isinstance(PROJECT_ROOT, Path)

    def test_mcp_root_under_project(self):
        assert MCP_ROOT.parent == PROJECT_ROOT

    def test_mcp_root_name(self):
        assert MCP_ROOT.name == "mcp_servers"

    def test_cache_dir_name(self):
        assert CACHE_DIR.name == ".docs-cache"

    def test_cache_file_name(self):
        assert CACHE_FILE.name == "MCP_COUNT.txt"


class TestCountMcpDirectories:
    """count_mcp_directories() function."""

    def test_returns_int(self):
        result = count_mcp_directories()
        assert isinstance(result, int)

    def test_returns_non_negative(self):
        result = count_mcp_directories()
        assert result >= 0

    def test_with_fake_dir(self, tmp_path):
        """Count MCPs in a temp directory."""
        mcp_root = tmp_path / "mcp_servers"
        mcp_root.mkdir()
        # Add a fake MCP server
        (mcp_root / "user_test1").mkdir()
        (mcp_root / "user_test1" / "server.py").write_text("# fake")
        result = count_mcp_directories(mcp_root=mcp_root)
        assert result == 1

    def test_skips_dirs_without_server(self, tmp_path):
        """Dirs without server.py are not counted."""
        mcp_root = tmp_path / "mcp_servers"
        mcp_root.mkdir()
        (mcp_root / "user_test1").mkdir()  # No server.py
        result = count_mcp_directories(mcp_root=mcp_root)
        assert result == 0

    def test_skips_non_user_dirs(self, tmp_path):
        """Dirs not starting with user_ are not counted."""
        mcp_root = tmp_path / "mcp_servers"
        mcp_root.mkdir()
        (mcp_root / "notuser").mkdir()
        (mcp_root / "notuser" / "server.py").write_text("# fake")
        result = count_mcp_directories(mcp_root=mcp_root)
        assert result == 0

    def test_nonexistent_dir_returns_zero(self, tmp_path):
        result = count_mcp_directories(mcp_root=tmp_path / "nonexistent")
        assert result == 0

    def test_multiple_servers(self, tmp_path):
        mcp_root = tmp_path / "mcp_servers"
        mcp_root.mkdir()
        for i in range(3):
            d = mcp_root / f"user_server{i}"
            d.mkdir()
            (d / "server.py").write_text("# fake")
        result = count_mcp_directories(mcp_root=mcp_root)
        assert result == 3


class TestWriteCache:
    """write_cache() function."""

    def test_writes_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("scripts.count_mcp.CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr(
            "scripts.count_mcp.CACHE_FILE",
            tmp_path / "cache" / "MCP_COUNT.txt",
        )
        write_cache(42)
        assert (tmp_path / "cache" / "MCP_COUNT.txt").exists()
        assert (tmp_path / "cache" / "MCP_COUNT.txt").read_text() == "42\n"

    def test_creates_dir(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "new_cache"
        monkeypatch.setattr("scripts.count_mcp.CACHE_DIR", cache_dir)
        monkeypatch.setattr(
            "scripts.count_mcp.CACHE_FILE",
            cache_dir / "MCP_COUNT.txt",
        )
        write_cache(10)
        assert cache_dir.exists()
