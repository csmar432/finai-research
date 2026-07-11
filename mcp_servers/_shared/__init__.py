"""mcp_servers/_shared — Shared utilities for MCP server entry points.

This package centralizes cross-cutting concerns so each user_* server only
contains tool handlers and transport setup:

  _version.py  - Single source of truth for APP_VERSION / APP_NAME
                 (reads pyproject.toml at runtime, no hardcoded drift)
"""
