"""Tests for scripts/health_check.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest


class TestColorHelpers:
    def test_green(self):
        from scripts.health_check import green
        result = green("ok")
        assert "ok" in result
        assert "\033[92m" in result  # GREEN

    def test_red(self):
        from scripts.health_check import red
        result = red("error")
        assert "error" in result
        assert "\033[91m" in result  # RED

    def test_yellow(self):
        from scripts.health_check import yellow
        result = yellow("warn")
        assert "warn" in result
        assert "\033[93m" in result  # YELLOW

    def test_cyan(self):
        from scripts.health_check import cyan
        result = cyan("info")
        assert "info" in result

    def test_bold_dim(self):
        from scripts.health_check import bold, dim
        assert "\033[1m" in bold("x")
        assert "\033[2m" in dim("x")


class TestMask:
    def test_mask_short(self):
        from scripts.health_check import _mask
        # len <= 6: all asterisks, count == length
        assert _mask("") == ""
        assert _mask("abc") == "***"      # len=3
        assert _mask("abcde") == "*****"   # len=5
        assert _mask("abcdef") == "******" # len=6

    def test_mask_long(self):
        from scripts.health_check import _mask
        # len=21: first1 + mid(21-8=13 asterisks) + last4
        masked = _mask("abcdefghijk1234567890")  # 21 chars
        assert masked.startswith("a")
        assert masked.endswith("7890")
        assert masked.count("*") == 13  # 21-8=13
        assert len(masked) == 21


class TestReadEnv:
    def test_read_env_basic(self, tmp_path):
        from scripts.health_check import _read_env

        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n# comment\n FOO2 = spaced \n")

        env = _read_env(env_file)
        assert env["FOO"] == "bar"
        assert env["BAZ"] == "qux"
        assert env["FOO2"] == "spaced"

    def test_read_env_missing_file(self, tmp_path):
        from scripts.health_check import _read_env

        env = _read_env(tmp_path / "nonexistent")
        assert env == {}

    def test_read_env_comments_and_empty(self, tmp_path):
        from scripts.health_check import _read_env

        env_file = tmp_path / ".env"
        env_file.write_text("# only comment\n\nFOO=bar\n  \nBAZ=qux\n")
        env = _read_env(env_file)
        assert "FOO" in env
        assert "comment" not in env


class TestProbeUrl:
    def test_probe_url_success_localhost(self):
        """Test _probe_url return type and structure (mocked success)."""
        from scripts.health_check import _probe_url
        from unittest import mock

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock.MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
            mock_response.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            ok, msg = _probe_url("https://example.com", timeout=10)
            assert ok is True
            assert "200" in msg

    def test_probe_url_http_error_4xx(self):
        """Test _probe_url with HTTP 404 error."""
        from scripts.health_check import _probe_url
        from unittest import mock
        import urllib.error

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test", code=404, msg="Not Found", hdrs={}, fp=None
            )

            ok, msg = _probe_url("https://example.com", timeout=5)
            assert ok is False
            assert "404" in msg

    def test_probe_url_http_error_401(self):
        """HTTP 401/403 → network OK (auth issue only)."""
        from scripts.health_check import _probe_url
        from unittest import mock
        import urllib.error

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test", code=401, msg="Unauthorized", hdrs={}, fp=None
            )

            ok, msg = _probe_url("https://example.com", timeout=5)
            assert ok is True
            assert "401" in msg

    def test_probe_url_connection_error(self):
        """Connection error → ok is False."""
        from scripts.health_check import _probe_url
        from unittest import mock
        import urllib.error

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            ok, msg = _probe_url("https://example.com", timeout=5)
            assert ok is False
            assert isinstance(msg, str)


class TestLLMChatCompletion:
    def test_llm_chat_completion_connection_error(self):
        from scripts.health_check import _llm_chat_completion
        from unittest import mock
        import urllib.error

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            ok, msg = _llm_chat_completion(
                "https://fake-api.example.com/v1/chat/completions",
                "sk-test", "gpt-4o-mini", timeout=5,
            )
            assert ok is False
            assert "连接失败" in msg or "failed" in msg.lower()

    def test_llm_chat_completion_http_error(self):
        from scripts.health_check import _llm_chat_completion
        from unittest import mock
        import urllib.error

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test", code=401, msg="Unauthorized", hdrs={}, fp=None
            )
            ok, msg = _llm_chat_completion(
                "https://fake-api.example.com/v1/chat/completions",
                "sk-invalid-key", "gpt-4o-mini", timeout=5,
            )
            assert ok is False
            assert "401" in msg


class TestDetectPlatform:
    def test_detect_platform_cursor(self):
        from scripts.health_check import _detect_platform

        with mock.patch.dict("os.environ", {
            "CURSOR": "1", "CURSOR_SESSION_ID": "abc",
        }, clear=False):
            # Reload module to pick up env change
            import importlib
            import scripts.health_check as hc
            importlib.reload(hc)
            platform = hc._detect_platform()
            assert platform == "cursor"
            importlib.reload(hc)  # restore

    def test_detect_platform_claude_code(self):
        from scripts.health_check import _detect_platform

        mock_parent = mock.MagicMock()
        mock_parent.name.return_value = "claude_desktop"
        mock_process = mock.MagicMock()
        mock_process.parents.return_value = [mock_parent]

        with mock.patch.dict("os.environ", {"CLAUDE_CODE": "1"}, clear=True):
            with mock.patch("psutil.Process", return_value=mock_process):
                platform = _detect_platform()
                assert platform == "claude_code"


class TestPlatformFixes:
    def test_platform_fixes_cursor(self):
        from scripts.health_check import _platform_fixes

        fixes = _platform_fixes("cursor")
        assert "env_hint" in fixes
        assert "restart_hint" in fixes

    def test_platform_fixes_claude_code(self):
        from scripts.health_check import _platform_fixes

        fixes = _platform_fixes("claude_code")
        assert "env_hint" in fixes
        assert "restart_hint" in fixes

    def test_platform_fixes_unknown(self):
        from scripts.health_check import _platform_fixes

        fixes = _platform_fixes("unknown")
        assert "env_hint" in fixes


class TestDiagnosticResult:
    def test_to_dict(self):
        from scripts.health_check import DiagnosticResult, ProblemCategory, ProblemItem

        problem = ProblemItem(
            category=ProblemCategory.API_KEY,
            name="DEEPSEEK_API_KEY",
            name_zh="DeepSeek API Key",
            message="Missing",
            fix_steps=["Step 1"],
        )
        result = DiagnosticResult(
            timestamp="2026-01-01 00:00:00",
            platform="cursor",
            llm_available=False,
            llm_status="no key",
            mcp_enabled_count=10,
            mcp_verified_count=0,
            problem_counts={"api_key": 1},
            problems=[problem],
            system_ready=False,
            recommendations=["Fix it"],
        )

        d = result.to_dict()
        assert d["timestamp"] == "2026-01-01 00:00:00"
        assert d["platform"] == "cursor"
        assert d["llm_available"] is False
        assert d["system_ready"] is False
        assert len(d["problems"]) == 1
        assert d["problems"][0]["name"] == "DEEPSEEK_API_KEY"

    def test_to_json(self):
        from scripts.health_check import DiagnosticResult

        result = DiagnosticResult(
            timestamp="2026-01-01 00:00:00",
            platform="cursor",
            llm_available=True,
            llm_status="ok",
            mcp_enabled_count=5,
            mcp_verified_count=0,
            problem_counts={},
            problems=[],
            system_ready=True,
            recommendations=[],
        )
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["system_ready"] is True


class TestGroupByCategory:
    def test_group_by_category(self):
        from scripts.health_check import (
            ProblemCategory, ProblemItem, _group_by_category,
        )

        items = [
            ProblemItem(ProblemCategory.API_KEY, "k1", "k1", "msg", []),
            ProblemItem(ProblemCategory.API_KEY, "k2", "k2", "msg", []),
            ProblemItem(ProblemCategory.NETWORK, "n1", "n1", "msg", []),
        ]
        groups = _group_by_category(items)
        assert ProblemCategory.API_KEY in groups
        assert ProblemCategory.NETWORK in groups
        assert len(groups[ProblemCategory.API_KEY]) == 2
        assert len(groups[ProblemCategory.NETWORK]) == 1

    def test_group_by_category_string(self):
        from scripts.health_check import ProblemCategory, ProblemItem, _group_by_category

        items = [
            ProblemItem("api_key", "k1", "k1", "msg", []),
        ]
        groups = _group_by_category(items)
        assert ProblemCategory.API_KEY in groups


class TestCatLabels:
    def test_cat_labels_all_present(self):
        from scripts.health_check import _CAT_LABELS, ProblemCategory

        for cat in ProblemCategory:
            assert cat in _CAT_LABELS


class TestProblemItem:
    def test_problem_item_to_dict(self):
        from scripts.health_check import ProblemCategory, ProblemItem

        item = ProblemItem(
            category=ProblemCategory.DEPENDENCY,
            name="numpy",
            name_zh="NumPy",
            message="not installed",
            fix_steps=["pip install numpy"],
            severity="high",
            details={"version": None},
        )
        d = item.to_dict()
        assert d["category"] == "dependency"
        assert d["name"] == "numpy"
        assert d["severity"] == "high"


class TestMCPVerifyStdio:
    def test_verify_server_nonexistent_path(self):
        from scripts.health_check import _verify_mcp_server_stdio

        ok, msg = _verify_mcp_server_stdio(Path("/nonexistent/server.py"))
        assert ok is False
        assert "不存在" in msg


class TestCheckDependencies:
    def test_check_dependencies_all_critical_present(self):
        from scripts.health_check import _check_dependencies

        problems, ok_list = _check_dependencies()
        # On a properly configured machine, critical deps should be present
        # We only assert structure, not specific results (depends on environment)
        assert isinstance(problems, list)
        assert isinstance(ok_list, list)
        for p in problems:
            assert p.category == "dependency"


class TestCheckLLMNoKey:
    def test_check_llm_reports_missing_key(self):
        from scripts.health_check import _check_llm

        # Mock env to have no keys
        with mock.patch("scripts.health_check._read_env", return_value={}):
            available, status, problems = _check_llm(verify=False)

        assert available is False
        assert any(p.name == "DEEPSEEK_API_KEY" for p in problems)


class TestDiagnosticResultRoundTrip:
    def test_result_json_roundtrip(self):
        from scripts.health_check import DiagnosticResult

        result = DiagnosticResult(
            timestamp="2026-06-23 12:00:00",
            platform="cursor",
            llm_available=True,
            llm_status="DeepSeek (****1234) OK",
            mcp_enabled_count=20,
            mcp_verified_count=5,
            problem_counts={"network": 0, "api_key": 0, "dependency": 0, "mcp": 0, "data_source": 0},
            problems=[],
            system_ready=True,
            recommendations=["All good!"],
            verify_mode=False,
        )

        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["system_ready"] is True
        assert parsed["llm_available"] is True
        assert parsed["mcp_enabled_count"] == 20


class TestCatLabelsCoverage:
    def test_all_problem_categories_in_labels(self):
        from scripts.health_check import _CAT_LABELS, ProblemCategory

        for cat in ProblemCategory:
            assert cat in _CAT_LABELS, f"Missing label for {cat}"


class TestProjectRoot:
    def test_project_root_returns_path(self):
        from scripts.health_check import _project_root

        root = _project_root()
        assert isinstance(root, Path)
        assert root.name == "论文-研报工作流"


class TestRunDiagnosticBasic:
    def test_run_diagnostic_returns_diagnostic_result(self):
        from scripts.health_check import run_diagnostic

        # Mock network/MCP parts to avoid external calls
        with mock.patch("scripts.health_check._check_llm", return_value=(False, "no key", [])):
            with mock.patch("scripts.health_check._check_dependencies", return_value=([], [])):
                with mock.patch("scripts.health_check._check_mcp", return_value=(0, 0, [], [])):
                    # DataSourceChecker is imported inside run_diagnostic, so patch where it's used
                    with mock.patch("scripts.data_source_checker.DataSourceChecker") as MockChecker:
                        mock_instance = mock.MagicMock()
                        mock_instance.run.return_value = mock.MagicMock(
                            source_results={}
                        )
                        MockChecker.return_value = mock_instance

                        result = run_diagnostic(verify=False)

        assert hasattr(result, "timestamp")
        assert hasattr(result, "platform")
        assert hasattr(result, "llm_available")
        assert hasattr(result, "system_ready")
        assert hasattr(result, "recommendations")
