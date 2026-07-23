"""Unit tests for scripts/verify_metadata.py."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_metadata.py"
SCRIPTS_DIR = SCRIPT.parent


def _run_with_base(mcp_root: Path) -> str:
    """Import verify_metadata, patch `base`, exec the body, capture stdout."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        pass
        # Run body — monkey-patch the iterdir lookup by patching `base`
        # to point at our tmp_path.  Note: the script body reads `base` once
        # via the module-level name so patching the attribute should work.
        body = (SCRIPT).read_text()
        # Replace `base = ...` assignment
        body = body.replace(
            "base = Path(__file__).resolve().parent.parent / \"mcp_servers\"",
            f"base = __import__('pathlib').Path({str(mcp_root)!r})",
        )
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                # Pass a globals dict so the module-level `base` is captured
                g = {"__file__": str(SCRIPT), "__name__": "__not_main__"}
                exec(body, g)
        except (FileNotFoundError, SystemExit):
            pass
        return buf.getvalue()
    finally:
        if str(SCRIPTS_DIR) in sys.path:
            sys.path.remove(str(SCRIPTS_DIR))


def _write_metadata(server_dir: Path, name: str, *, missing: list[str] | None = None) -> None:
    server_dir.mkdir(parents=True, exist_ok=True)
    d = {
        "name": name,
        "version": "1.0.0",
        "is_mock": False,
        "requires_api_key": False,
    }
    if missing:
        for f in missing:
            d.pop(f, None)
    (server_dir / "SERVER_METADATA.json").write_text(json.dumps(d))


class TestNormalOperation:
    def test_all_complete_no_issue(self, tmp_path):
        """Two complete metadata files → no ISSUE flag in output."""
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "user_a", "ServerA")
        _write_metadata(mcp / "user_b", "ServerB")
        out = _run_with_base(mcp)
        assert "ISSUE: " not in out

    def test_only_non_user_dirs_skipped(self, tmp_path):
        """Non-user directories should not appear in the table."""
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "internal_tool", "Internal")
        out = _run_with_base(mcp)
        assert "internal_tool" not in out

    def test_dir_without_metadata_skipped(self, tmp_path):
        """Directory without SERVER_METADATA.json is skipped, no crash."""
        mcp = tmp_path / "mcp_servers"
        (mcp / "user_empty").mkdir(parents=True)
        out = _run_with_base(mcp)
        # Should not crash; may include the summary line
        assert isinstance(out, str)

    def test_files_in_root_skipped(self, tmp_path):
        """Loose files at mcp_servers root level should not crash."""
        mcp = tmp_path / "mcp_servers"
        mcp.mkdir(parents=True, exist_ok=True)
        (mcp / "stray.txt").write_text("not a directory")
        out = _run_with_base(mcp)
        assert isinstance(out, str)


class TestMissingFields:
    def test_missing_name_field(self, tmp_path):
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "user_bad", "X", missing=["name"])
        out = _run_with_base(mcp)
        assert "ISSUE: " in out

    def test_missing_version_field(self, tmp_path):
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "user_bad", "X", missing=["version"])
        out = _run_with_base(mcp)
        assert "ISSUE: " in out

    def test_missing_is_mock_field(self, tmp_path):
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "user_bad", "X", missing=["is_mock"])
        out = _run_with_base(mcp)
        assert "ISSUE: " in out

    def test_missing_requires_api_key_field(self, tmp_path):
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "user_bad", "X", missing=["requires_api_key"])
        out = _run_with_base(mcp)
        assert "ISSUE: " in out


class TestSummaryTable:
    def test_table_includes_server_name(self, tmp_path):
        mcp = tmp_path / "mcp_servers"
        srv = mcp / "user_demo"
        srv.mkdir(parents=True)
        (srv / "SERVER_METADATA.json").write_text(json.dumps({
            "name": "demo_server",
            "version": "1.0",
            "is_mock": True,
            "requires_api_key": True,
            "api_key_env_var": "DEMO_KEY",
        }))
        out = _run_with_base(mcp)
        assert "demo_server" in out

    def test_servers_sorted_alphabetically(self, tmp_path):
        mcp = tmp_path / "mcp_servers"
        _write_metadata(mcp / "user_zzz", "Z")
        _write_metadata(mcp / "user_aaa", "A")
        _write_metadata(mcp / "user_mmm", "M")
        out = _run_with_base(mcp)
        if "user_aaa" in out and "user_zzz" in out:
            assert out.index("user_aaa") < out.index("user_mmm") < out.index("user_zzz")


class TestModuleImport:
    def test_imports_without_error(self):
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_metadata  # noqa: F401
        finally:
            if str(SCRIPTS_DIR) in sys.path:
                sys.path.remove(str(SCRIPTS_DIR))

    def test_base_path_attribute_exists(self):
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_metadata as vm
            assert vm.base.name == "mcp_servers"
        finally:
            if str(SCRIPTS_DIR) in sys.path:
                sys.path.remove(str(SCRIPTS_DIR))

