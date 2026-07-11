"""test_version_drift.py — Regression tests for hardcoded version drift.

Defense:
  - 2026-07-11 audit: scripts/cli.py had v1.0.0 in banner, 3 MCP servers had
    APP_VERSION = "1.0.0", gen_architecture_diagrams.py header() defaulted to
    v1.0.0. All hardcoded values must be removed to prevent drift.

These tests ensure:
  1. cli.py banner reflects current pyproject version (not hardcoded)
  2. _read_pyproject_version() prefers top-level pyproject over mcp_servers sub-pyproject
  3. 3 MCP servers read APP_VERSION from shared source, not hardcoded
  4. gen_architecture_diagrams.py header() uses dynamic version
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ────────────────────────────────────────────────────────────────────
# 1. CLI banner regression
# ────────────────────────────────────────────────────────────────────


class TestCliBannerVersion:
    """Defense: cli.py banner must NOT hardcode 'v1.0.0' or 'v0.1.0'."""

    def test_banner_uses_dynamic_version(self):
        cli_path = ROOT / "scripts" / "cli.py"
        text = cli_path.read_text(encoding="utf-8")
        # Read BANNER constant — should NOT contain literal "v1.0.0"
        # (it's an f-string with {_read_pyproject_version()}).
        match = re.search(r'BANNER\s*=\s*f?"""(.*?)"""', text, re.DOTALL)
        assert match, "BANNER constant not found"
        banner_template = match.group(1)
        # Must NOT contain hardcoded version literals
        assert "v1.0.0" not in banner_template, (
            "Found hardcoded 'v1.0.0' in CLI banner — should use dynamic version"
        )
        assert "v0.1.0" not in banner_template, (
            "Found hardcoded 'v0.1.0' in CLI banner — should use dynamic version"
        )

    def test_banner_includes_dynamic_call(self):
        cli_path = ROOT / "scripts" / "cli.py"
        text = cli_path.read_text(encoding="utf-8")
        assert "_read_pyproject_version" in text, (
            "Expected _read_pyproject_version() call in banner f-string"
        )

    def test_version_cmd_uses_dynamic(self):
        cli_path = ROOT / "scripts" / "cli.py"
        text = cli_path.read_text(encoding="utf-8")
        # version_cmd should NOT have a hardcoded fallback to "1.0.0"
        assert 'version = "1.0.0"' not in text, (
            "Found hardcoded fallback version='1.0.0' in cli.py"
        )


# ────────────────────────────────────────────────────────────────────
# 2. Shared version utility
# ────────────────────────────────────────────────────────────────────


class TestSharedVersionUtility:
    """Defense: mcp_servers/_shared/_version.py must return top-level version."""

    def test_shared_module_imports(self):
        try:
            from mcp_servers._shared._version import (  # type: ignore
                APP_VERSION,
                APP_NAME,
                get_app_version,
            )

            assert APP_NAME, "APP_NAME empty"
            assert APP_VERSION, "APP_VERSION empty"
        except ImportError as _exc:
            pytest.skip(f"_shared._version not available: {_exc}")

    def test_version_matches_top_level_pyproject(self):
        """APP_VERSION must come from finai-research-workflow (NOT paper-workflow-mcp)."""
        try:
            from mcp_servers._shared._version import _read_pyproject_version  # type: ignore

            v = _read_pyproject_version()
            assert v is not None, "Failed to read pyproject version"

            # Compare with the canonical top-level pyproject.toml
            text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
            m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            assert m, "Top-level pyproject.toml has no version"
            assert v == m.group(1), (
                f"mcp_servers version={v} != top-level pyproject version={m.group(1)}"
            )
        except ImportError:
            pytest.skip("_shared._version not available")

    def test_does_not_pick_up_mcp_servers_sub_pyproject(self):
        """Make sure walk-up logic doesn't grab mcp_servers/pyproject.toml
        which is a separate sub-package (paper-workflow-mcp v1.0.0)."""
        try:
            from mcp_servers._shared._version import _read_pyproject_version  # type: ignore

            v = _read_pyproject_version()
            # If we accidentally picked up mcp_servers/pyproject.toml, v would be "1.0.0"
            assert v != "1.0.0", (
                "Version reader picked up mcp_servers/pyproject.toml (paper-workflow-mcp v1.0.0) "
                "instead of top-level finai-research-workflow. This is a regression."
            )
        except ImportError:
            pytest.skip("_shared._version not available")


# ────────────────────────────────────────────────────────────────────
# 3. MCP server regression
# ────────────────────────────────────────────────────────────────────


class TestMcpServerVersionNotHardcoded:
    """Defense: 3 MCP servers must NOT hardcode APP_VERSION = "1.0.0"."""

    MCP_FILES = [
        "mcp_servers/user_sec_edgar/server.py",
        "mcp_servers/user_cryptocompare/server.py",
        "mcp_servers/user_newsapi/server.py",
    ]

    @pytest.mark.parametrize("rel_path", MCP_FILES)
    def test_no_hardcoded_app_version(self, rel_path):
        path = ROOT / rel_path
        if not path.exists():
            pytest.skip(f"{rel_path} not found")
        text = path.read_text(encoding="utf-8")
        # The only acceptable assignment is the fallback in the except clause.
        # We accept ONLY:    APP_VERSION = "0.0.0+unknown"
        # or f-strings containing APP_VERSION (not assignments).
        assignment_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            # Find ASSIGNMENT lines (have = and APP_VERSION on LHS)
            if re.match(r"APP_VERSION\s*=", stripped):
                assignment_lines.append(stripped)

        # Allowable hardcoded fallback: "0.0.0+unknown"
        bad = [l for l in assignment_lines if "0.0.0+unknown" not in l and "from mcp_servers" not in l]
        assert len(bad) == 0, (
            f"{rel_path}: unexpected hardcoded APP_VERSION assignment:\n"
            + "\n".join(bad)
        )

    @pytest.mark.parametrize("rel_path", MCP_FILES)
    def test_imports_shared_version(self, rel_path):
        path = ROOT / rel_path
        if not path.exists():
            pytest.skip(f"{rel_path} not found")
        text = path.read_text(encoding="utf-8")
        assert "from mcp_servers._shared._version" in text, (
            f"{rel_path} does not import shared version utility"
        )


# ────────────────────────────────────────────────────────────────────
# 4. gen_architecture_diagrams regression
# ────────────────────────────────────────────────────────────────────


class TestArchitectureDiagramsVersion:
    """Defense: gen_architecture_diagrams.py header() must not hardcode v1.0.0."""

    def test_header_signature_has_dynamic_default(self):
        path = ROOT / "scripts" / "gen_architecture_diagrams.py"
        if not path.exists():
            pytest.skip("gen_architecture_diagrams.py not found")
        text = path.read_text(encoding="utf-8")
        # Find def header(...) signature
        m = re.search(r'def\s+header\s*\([^)]*version[^)]*\)\s*->\s*str', text)
        assert m, "header() signature not found"
        sig = m.group(0)
        # Must NOT have default value 'v1.0.0'
        assert '="v1.0.0"' not in sig, (
            f"header() default version still hardcoded:\n  {sig}"
        )
        assert "= 'v1.0.0'" not in sig, (
            f"header() default version still hardcoded:\n  {sig}"
        )

    def test_no_v1_0_0_string_literal(self):
        path = ROOT / "scripts" / "gen_architecture_diagrams.py"
        if not path.exists():
            pytest.skip("gen_architecture_diagrams.py not found")
        text = path.read_text(encoding="utf-8")
        # The only "v1.0.0" should be inside a docstring example or comment,
        # not as a live default. Look for assignment-default patterns.
        bad_patterns = [
            '= "v1.0.0"',
            "= 'v1.0.0'",
            '"v1.0.0 标签"',  # the original literal in release diagram
        ]
        for pat in bad_patterns:
            if pat in text:
                # Allow inside docstring/comments only — look at the context
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if pat in line and not line.strip().startswith("#"):
                        # Check if the line is inside a function default
                        # (heuristic: it contains 'def' nearby)
                        pytest.fail(
                            f"Hardcoded version pattern '{pat}' on line {i+1}:\n  {line.strip()}"
                        )
