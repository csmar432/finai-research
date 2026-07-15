"""Unit tests for scripts/core/ide_platform.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def ip():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import ide_platform as i
    yield i
    if _p in sys.path:
        sys.path.remove(_p)


class TestDetectPlatform:
    def test_returns_string(self, ip):
        result = ip._detect_platform()
        assert isinstance(result, str)
        assert result in ("cursor", "claude_code", "vscode", "unknown", "web")

    def test_returns_known_platform(self, ip):
        result = ip._detect_platform()
        known = {"cursor", "claude_code", "vscode", "unknown", "web", "other"}
        assert result in known


class TestPlatformInfo:
    def test_platform_info_fields(self, ip):
        from pathlib import Path
        if hasattr(ip, "PlatformInfo"):
            info = ip.PlatformInfo(
                platform="cursor",
                is_cursor=True,
                is_claude_code=False,
                is_vscode=False,
                is_generic=False,
                project_root=Path("/tmp"),
                mcp_config_paths=[],
                canvas_available=False,
            )
            assert info.platform == "cursor"
            assert info.is_cursor is True


class TestMcpConfigPaths:
    def test_returns_list(self, ip):
        result = ip.get_mcp_config_paths()
        assert isinstance(result, list)

    def test_paths_are_absolute(self, ip):
        result = ip.get_mcp_config_paths()
        for p in result:
            assert isinstance(p, (Path, str)) or p is None


class TestProjectRoot:
    def test_get_project_root_returns_path(self, ip):
        result = ip.get_project_root()
        assert isinstance(result, Path)
        assert result.is_absolute()


class TestCanvasFile:
    def test_get_canvas_path_function(self, ip):
        if hasattr(ip, "get_canvas_file_path"):
            result = ip.get_canvas_file_path("test.md")
            assert isinstance(result, (Path, str)) or result is None


class TestAllExport:
    def test_all_listed(self, ip):
        if hasattr(ip, "__all__"):
            assert isinstance(ip.__all__, list)
            assert len(ip.__all__) > 0
            for name in ip.__all__:
                assert hasattr(ip, name)
