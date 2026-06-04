"""Platform detection and path resolution for multi-IDE compatibility.

Detects the current runtime environment (Cursor, Claude Code, VS Code, etc.)
and provides appropriate paths for MCP config, Canvas files, and project roots.

Usage:
    from scripts.core.platform import (
        PROJECT_ROOT,
        MCP_CONFIG_PATHS,
        get_canvas_path,
        detect_platform,
        IS_CURSOR,
        IS_CLAUDE_CODE,
        IS_VSCODE,
    )
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

# ─── Platform Detection ───────────────────────────────────────────────────────

def _detect_platform() -> str:
    """Detect the current IDE/runtime environment."""
    env_vars = (
        os.environ.get("CURSOR") or
        os.environ.get("CURSOR_SESSION_ID") or
        os.environ.get("VSCODE_RESOLVING_ENVIRONMENT") or
        os.environ.get("CLAUDE_CODE") or
        os.environ.get("AGENT_ID") or
        os.environ.get("CODY_DEBUG")
    )

    # Check parent processes
    try:
        import psutil
        parent_names = set()
        try:
            for p in psutil.Process().parents():
                parent_names.add(p.name())
        except (psutil.AccessDenied, PermissionError, OSError):
            # macOS沙盒或无root权限时无法枚举进程，降级处理
            pass
        if "Cursor" in parent_names or "cursor" in parent_names:
            return "cursor"
        if "Code" in parent_names or "cursor" in parent_names:
            return "cursor"
    except ImportError:
        pass

    # Check environment variable indicators
    if env_vars:
        if "cursor" in str(env_vars).lower():
            return "cursor"
        if "claude" in str(env_vars).lower():
            return "claude_code"
        if "vscode" in str(env_vars).lower():
            return "vscode"

    # Heuristic: check if we're in a Cursor-managed project
    home = Path.home()
    cursor_project = home / ".cursor" / "projects"
    if cursor_project.exists():
        # Check if current cwd is under a known Cursor project
        try:
            cwd = Path.cwd()
            for p in cursor_project.iterdir():
                if p.is_dir() and str(cwd).startswith(str(p)):
                    return "cursor"
        except Exception:
            pass

    # Default: check environment markers
    if os.environ.get("CLAUDE_DESKTOP_SESSION"):
        return "claude_code"

    # Check if MCP config exists in Cursor location (implies Cursor context)
    cursor_mcp = home / ".cursor" / "mcp.json"
    if cursor_mcp.exists():
        return "cursor"

    return "generic"


PLATFORM = _detect_platform()
IS_CURSOR = PLATFORM == "cursor"
IS_CLAUDE_CODE = PLATFORM in ("claude_code", "claude_desktop")
IS_VSCODE = PLATFORM == "vscode"
IS_GENERIC = PLATFORM == "generic"


# ─── Project Root ─────────────────────────────────────────────────────────────

# Resolve project root from this file's location:
#   scripts/core/platform.py → PROJECT_ROOT = <repo_root>
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if not _PROJECT_ROOT.exists():
    # Fallback: use environment variable or cwd
    _PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path.cwd()))


def get_project_root() -> Path:
    """Return the project root directory."""
    explicit = os.environ.get("PROJECT_ROOT")
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
    return _PROJECT_ROOT


PROJECT_ROOT = get_project_root()


# ─── MCP Config Paths ─────────────────────────────────────────────────────────

def get_mcp_config_paths() -> list[Path]:
    """Return ordered list of MCP config file paths to search.

    Priority (first match wins):
    1. Environment variable RESEARCH_MCP_CONFIG
    2. Cursor: ~/.cursor/mcp.json
    3. Claude Code: ~/.claude/mcp.json
    4. VS Code: ~/.config/Code/User/globalStorage/salaun.plasticity-mcp/*/mcp.json
    5. Project-local: PROJECT_ROOT/.mcp.json
    6. Project-local: PROJECT_ROOT/.cursor/mcp.json (for migrated setups)
    """
    home = Path.home()
    paths = []

    # 1. Explicit override
    explicit = os.environ.get("RESEARCH_MCP_CONFIG")
    if explicit:
        p = Path(explicit)
        if p.exists():
            paths.append(p)

    # 2. Cursor
    if IS_CURSOR or not paths:
        cursor_path = home / ".cursor" / "mcp.json"
        if cursor_path.exists():
            paths.append(cursor_path)

    # 3. Claude Code / Claude Desktop
    if IS_CLAUDE_CODE or not paths:
        for candidate in [
            home / ".claude" / "mcp.json",
            home / ".config" / "claude" / "mcp.json",
            home / "Library" / "Application Support" / "Claude" / "mcp.json",
        ]:
            if candidate.exists():
                paths.append(candidate)
                break

    # 4. VS Code Copilot / other
    if IS_VSCODE or not paths:
        for candidate in [
            home / ".config" / "Code" / "User" / "globalStorage" / "salaun.plasticity-mcp" / "mcp.json",
        ]:
            if candidate.exists():
                paths.append(candidate)

    # 5. Project-local (works everywhere)
    project_mcp = PROJECT_ROOT / ".mcp.json"
    if project_mcp.exists():
        paths.append(project_mcp)

    # 6. Legacy project-local cursor path
    legacy_cursor = PROJECT_ROOT / ".cursor" / "mcp.json"
    if legacy_cursor.exists() and legacy_cursor not in paths:
        paths.append(legacy_cursor)

    return paths


def get_mcp_config() -> dict:
    """Load MCP config from the first available path."""
    for path in get_mcp_config_paths():
        try:
            import json
            return json.loads(path.read_text())
        except Exception:
            continue
    return {"mcpServers": {}}


# ─── Canvas Path ──────────────────────────────────────────────────────────────

def get_canvas_file_path(filename: str = "workflow-progress.canvas.tsx") -> Path | None:
    """Return the path to the Canvas file, or None if Canvas is not available.

    Resolves the path based on the current platform:
    - Cursor:     ~/.cursor/projects/<hash>/<repo>/canvases/...
    - Claude Code: PROJECT_ROOT/canvases/...
    - Generic:    PROJECT_ROOT/canvases/...
    """
    # Allow override via environment variable
    explicit = os.environ.get("RESEARCH_CANVAS_PATH")
    if explicit:
        p = Path(explicit)
        if p.exists() or os.environ.get("RESEARCH_CANVAS_PATH") == "disabled":
            return p if os.environ.get("RESEARCH_CANVAS_PATH") != "disabled" else None

    # Canvas is a Cursor-only feature
    if not IS_CURSOR:
        # Still return the project-local path if it exists
        project_canvas = PROJECT_ROOT / "canvases" / filename
        if project_canvas.exists():
            return project_canvas
        return None

    # Cursor: try to find Canvas in project
    cursor_projects = Path.home() / ".cursor" / "projects"
    if cursor_projects.exists():
        try:
            cwd = Path.cwd()
            for project_dir in cursor_projects.iterdir():
                if project_dir.is_dir() and str(cwd).startswith(str(project_dir)):
                    canvas = project_dir / "canvases" / filename
                    if canvas.exists():
                        return canvas
                    # Also check if canvases are at repo root level
                    # (e.g. project_dir/<repo_name>/canvases/)
                    for sub in project_dir.iterdir():
                        if sub.is_dir():
                            canvas = sub / "canvases" / filename
                            if canvas.exists():
                                return canvas
        except Exception:
            pass

    # Fallback: project-local canvases directory
    project_canvas = PROJECT_ROOT / "canvases" / filename
    if project_canvas.exists():
        return project_canvas

    return None


def is_canvas_available() -> bool:
    """Return True if Canvas visualization is available."""
    return get_canvas_file_path() is not None


# ─── MCP Server Discovery ─────────────────────────────────────────────────────

def get_mcp_servers_root() -> Path:
    """Return the directory containing MCP server packages."""
    return PROJECT_ROOT / "mcp_servers"


def discover_mcp_servers() -> list[Path]:
    """Return all MCP server directories under the project."""
    root = get_mcp_servers_root()
    if not root.exists():
        return []
    return sorted(root.glob("user_*/"))


# ─── Summary ─────────────────────────────────────────────────────────────────

class PlatformInfo(NamedTuple):
    platform: str
    is_cursor: bool
    is_claude_code: bool
    is_vscode: bool
    is_generic: bool
    project_root: Path
    mcp_config_paths: list[Path]
    canvas_available: bool


def get_platform_info() -> PlatformInfo:
    """Return a summary of platform detection results."""
    return PlatformInfo(
        platform=PLATFORM,
        is_cursor=IS_CURSOR,
        is_claude_code=IS_CLAUDE_CODE,
        is_vscode=IS_VSCODE,
        is_generic=IS_GENERIC,
        project_root=PROJECT_ROOT,
        mcp_config_paths=get_mcp_config_paths(),
        canvas_available=is_canvas_available(),
    )
