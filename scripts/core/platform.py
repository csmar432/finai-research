"""Backwards-compat shim. The real module is scripts.core.ide_platform.

Historically this module lived at scripts.core.platform and was renamed.
This re-export preserves the old import path so that
`from scripts.core.platform import ...` still works.
"""
from scripts.core.ide_platform import (  # noqa: F401
    PROJECT_ROOT,
    PlatformInfo,
    _detect_platform,
    get_canvas_file_path,
    get_mcp_config_paths,
    get_mcp_config,
    get_mcp_servers_root,
    get_platform_info,
    get_project_root,
    is_canvas_available,
    discover_mcp_servers,
)
