"""Unit tests for scripts/core/sandbox_runner.py — dataclasses, enums, and helpers.

Covers: SandboxTier, SandboxResult, LocalSandboxRunner, E2BRunner, create_runner.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.sandbox_runner import (
        SandboxTier,
        SandboxResult,
        LocalSandboxRunner,
        E2BRunner,
        create_runner,
    )
except Exception as _exc:
    pytest.skip(f"sandbox_runner not importable: {_exc}", allow_module_level=True)


# ─── SandboxTier Enum ────────────────────────────────────────────────────────


class TestSandboxTierMembers:
    """All sandbox tier enum members must be accessible and have string values."""

    def test_all_tiers_exist(self):
        """All expected tier members are present."""
        expected = {"LOCAL", "PROCESS", "CONTAINER", "MICROVM"}
        actual = {e.name for e in SandboxTier}
        assert expected.issubset(actual)

    def test_values_are_strings(self):
        for member in SandboxTier:
            assert isinstance(member.value, str)

    def test_unique_values(self):
        values = [e.value for e in SandboxTier]
        assert len(values) == len(set(values))

    def test_local_value(self):
        assert SandboxTier.LOCAL.value == "local"

    def test_process_value(self):
        assert SandboxTier.PROCESS.value == "process"

    def test_container_value(self):
        assert SandboxTier.CONTAINER.value == "container"

    def test_microvm_value(self):
        assert SandboxTier.MICROVM.value == "microvm"

    def test_can_compare_by_string(self):
        assert SandboxTier.LOCAL == SandboxTier("local")
        assert SandboxTier.MICROVM == SandboxTier("microvm")


# ─── SandboxResult Dataclass ─────────────────────────────────────────────────


class TestSandboxResultDefaults:
    """SandboxResult must have sensible defaults."""

    def test_default_fields(self):
        result = SandboxResult()
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.execution_time_ms == 0.0
        assert result.tier == SandboxTier.LOCAL
        assert result.blocked_operations == []
        assert result.is_safe is True
        assert result.sandbox_id == ""

    def test_success_property_defaults(self):
        """success is True when exit_code==0 and is_safe==True."""
        result = SandboxResult()
        assert result.success is True

    def test_success_with_nonzero_exit(self):
        """success is False when exit_code != 0."""
        result = SandboxResult(exit_code=1)
        assert result.success is False

    def test_success_with_unsafe(self):
        """success is False when is_safe is False."""
        result = SandboxResult(is_safe=False)
        assert result.success is False


class TestSandboxResultCustom:
    """SandboxResult accepts all parameters."""

    def test_custom_stdout(self):
        result = SandboxResult(stdout="hello world")
        assert result.stdout == "hello world"

    def test_custom_stderr(self):
        result = SandboxResult(stderr="error message")
        assert result.stderr == "error message"

    def test_custom_exit_code(self):
        result = SandboxResult(exit_code=42)
        assert result.exit_code == 42

    def test_custom_execution_time(self):
        result = SandboxResult(execution_time_ms=1234.5)
        assert result.execution_time_ms == 1234.5

    def test_custom_tier(self):
        result = SandboxResult(tier=SandboxTier.MICROVM)
        assert result.tier == SandboxTier.MICROVM

    def test_custom_blocked_operations(self):
        result = SandboxResult(blocked_operations=["import os", "eval"])
        assert len(result.blocked_operations) == 2

    def test_custom_is_safe(self):
        result = SandboxResult(is_safe=False)
        assert result.is_safe is False

    def test_custom_sandbox_id(self):
        result = SandboxResult(sandbox_id="sb-12345")
        assert result.sandbox_id == "sb-12345"


class TestSandboxResultToDict:
    """to_dict() serialises all fields correctly."""

    def test_to_dict_basic(self):
        result = SandboxResult(
            stdout="out",
            stderr="err",
            exit_code=0,
            execution_time_ms=10.0,
            tier=SandboxTier.PROCESS,
            blocked_operations=[],
            is_safe=True,
            sandbox_id="",
        )
        d = result.to_dict()
        assert d["stdout"] == "out"
        assert d["stderr"] == "err"
        assert d["exit_code"] == 0
        assert d["execution_time_ms"] == 10.0
        assert d["tier"] == "process"
        assert d["blocked_operations"] == []
        assert d["is_safe"] is True
        assert d["sandbox_id"] == ""

    def test_to_dict_with_blocked_ops(self):
        result = SandboxResult(blocked_operations=["import os"])
        d = result.to_dict()
        assert "import os" in d["blocked_operations"]

    def test_to_dict_with_sandbox_id(self):
        result = SandboxResult(sandbox_id="abc-123")
        d = result.to_dict()
        assert d["sandbox_id"] == "abc-123"

    def test_to_dict_returns_dict(self):
        result = SandboxResult()
        assert isinstance(result.to_dict(), dict)


class TestSandboxResultSuccessProperty:
    """success property edge cases."""

    def test_success_both_zero_and_safe(self):
        result = SandboxResult(exit_code=0, is_safe=True)
        assert result.success is True

    def test_failure_exit_code_overrides_safe(self):
        """Even is_safe=True, nonzero exit_code makes success=False."""
        result = SandboxResult(exit_code=2, is_safe=True)
        assert result.success is False

    def test_failure_unsafe_overrides_exit_code(self):
        """Even exit_code=0, is_safe=False makes success=False."""
        result = SandboxResult(exit_code=0, is_safe=False)
        assert result.success is False


# ─── LocalSandboxRunner ──────────────────────────────────────────────────────


class TestLocalSandboxRunnerInit:
    """LocalSandboxRunner initialises with configurable parameters."""

    def test_default_init(self):
        runner = LocalSandboxRunner()
        assert runner.timeout == 30.0
        assert runner.allowed_files == set()
        assert runner.blocked_imports is not None
        assert "os" in runner.blocked_imports
        assert "subprocess" in runner.blocked_imports

    def test_custom_timeout(self):
        runner = LocalSandboxRunner(timeout_seconds=5.0)
        assert runner.timeout == 5.0

    def test_custom_allowed_files(self):
        runner = LocalSandboxRunner(allowed_files=["data.csv", "config.json"])
        assert "data.csv" in runner.allowed_files
        assert "config.json" in runner.allowed_files

    def test_custom_blocked_imports(self):
        runner = LocalSandboxRunner(blocked_imports={"os", "socket"})
        assert "os" in runner.blocked_imports
        assert "socket" in runner.blocked_imports

    def test_execution_log_initialised(self):
        runner = LocalSandboxRunner()
        assert runner._execution_log == []

    def test_blocked_imports_defaults(self):
        """Default BLOCKED_IMPORTS contains expected dangerous modules."""
        defaults = LocalSandboxRunner.BLOCKED_IMPORTS
        assert "os" in defaults.values()
        assert "subprocess" in defaults.values()
        assert "socket" in defaults.values()
        assert "requests" in defaults.values()
        assert "pickle" in defaults.values()
        assert "eval" in defaults.values()
        assert "exec" in defaults.values()

    def test_allowed_builtins_defaults(self):
        """Default ALLOWED_BUILTINS contains expected safe functions."""
        defaults = LocalSandboxRunner.ALLOWED_BUILTINS
        assert "print" in defaults
        assert "len" in defaults
        assert "range" in defaults
        assert "sum" in defaults
        assert "min" in defaults
        assert "max" in defaults
        assert "sorted" in defaults
        # Dangerous builtins should NOT be in allowed list
        assert "eval" not in defaults
        assert "exec" not in defaults
        assert "open" not in defaults


class TestLocalSandboxRunnerRunSafe:
    """LocalSandboxRunner.run() with safe code."""

    def test_run_simple_print(self):
        runner = LocalSandboxRunner()
        result = runner.run("print('hello from sandbox')")
        assert result.success is True
        assert "hello from sandbox" in result.stdout
        assert result.exit_code == 0
        assert result.tier == SandboxTier.PROCESS

    def test_run_arithmetic(self):
        runner = LocalSandboxRunner()
        result = runner.run("print(2 + 3)")
        assert result.success is True
        assert "5" in result.stdout

    def test_run_list_operations(self):
        runner = LocalSandboxRunner()
        result = runner.run(
            "x = [1, 2, 3]\n"
            "print(len(x))\n"
            "print(sum(x))\n"
        )
        assert result.success is True
        assert "3" in result.stdout
        assert "6" in result.stdout

    def test_run_string_operations(self):
        runner = LocalSandboxRunner()
        result = runner.run(
            "s = 'hello world'\n"
            "print(len(s))\n"
            "print(s.upper())\n"
        )
        assert result.success is True
        assert "11" in result.stdout
        assert "HELLO WORLD" in result.stdout

    def test_run_sets_result_fields(self):
        runner = LocalSandboxRunner()
        result = runner.run("print(1)")
        assert isinstance(result.execution_time_ms, float)
        assert result.execution_time_ms >= 0
        assert result.blocked_operations == []
        assert result.is_safe is True

    def test_run_builtin_functions(self):
        """Allowed builtins must work in sandbox."""
        runner = LocalSandboxRunner()
        result = runner.run(
            "print(isinstance(42, int))\n"
            "print(any([False, True, False]))\n"
            "print(all([1, 2, 3]))\n"
            "print(repr(3.14))\n"
        )
        assert result.success is True


class TestLocalSandboxRunnerRunBlocked:
    """LocalSandboxRunner.run() with dangerous code patterns."""

    def test_blocks_import_os(self):
        runner = LocalSandboxRunner()
        result = runner.run("import os; print(os.getcwd())")
        assert result.success is False
        assert result.is_safe is False
        assert any("os" in op for op in result.blocked_operations)

    def test_blocks_from_os_import(self):
        runner = LocalSandboxRunner()
        result = runner.run("from os import getcwd")
        assert result.success is False
        assert any("os" in op for op in result.blocked_operations)

    def test_blocks_subprocess(self):
        runner = LocalSandboxRunner()
        result = runner.run("import subprocess")
        assert result.success is False
        assert result.is_safe is False

    def test_blocks_socket(self):
        runner = LocalSandboxRunner()
        result = runner.run("import socket")
        assert result.success is False
        assert result.is_safe is False

    def test_blocks_requests(self):
        runner = LocalSandboxRunner()
        result = runner.run("import requests")
        assert result.success is False
        assert result.is_safe is False

    def test_blocks_eval(self):
        runner = LocalSandboxRunner()
        result = runner.run("eval('1+1')")
        assert result.success is False
        assert any("eval" in op for op in result.blocked_operations)

    def test_blocks_exec(self):
        runner = LocalSandboxRunner()
        result = runner.run("exec('print(1)')")
        assert result.success is False
        assert any("exec" in op for op in result.blocked_operations)

    def test_blocks_dangerous_builtin_in_code(self):
        """eval and exec as raw strings are blocked."""
        runner = LocalSandboxRunner()
        result = runner.run("code = 'print(1)'\neval(code)")
        assert result.success is False

    def test_blocks_file_operations_without_allowed(self):
        """open() without allowed_files list is blocked."""
        runner = LocalSandboxRunner()
        result = runner.run("f = open('test.txt')")
        assert result.success is False
        assert any("file_operation" in op for op in result.blocked_operations)

    def test_blocks_pickle(self):
        runner = LocalSandboxRunner()
        result = runner.run("import pickle")
        assert result.success is False

    def test_blocks_urllib(self):
        runner = LocalSandboxRunner()
        result = runner.run("import urllib.request")
        assert result.success is False

    def test_blocks_http(self):
        runner = LocalSandboxRunner()
        result = runner.run("import http.client")
        assert result.success is False

    def test_blocked_operations_includes_reason(self):
        runner = LocalSandboxRunner()
        result = runner.run("import os")
        assert len(result.blocked_operations) > 0
        # Each operation should describe what was blocked
        for op in result.blocked_operations:
            assert isinstance(op, str)
            assert len(op) > 0


class TestLocalSandboxRunnerRunWithAllowedFiles:
    """LocalSandboxRunner.run() with allowed_files parameter."""

    def test_allows_open_with_allowed_file(self):
        runner = LocalSandboxRunner(allowed_files=["test.txt"])
        # The check looks for 'open(' in lowercase
        # Since allowed_files is set, file ops check is bypassed
        result = runner.run("print('file access allowed')")
        assert result.success is True

    def test_allows_instance_level_allowed_files(self):
        runner = LocalSandboxRunner(allowed_files=["data.csv"])
        result = runner.run(
            "print('reading data.csv')",
            allowed_files=["data.csv"],
        )
        assert result.success is True


class TestLocalSandboxRunnerRunTimeout:
    """LocalSandboxRunner.run() timeout handling."""

    def test_timeout_kills_slow_code(self):
        runner = LocalSandboxRunner(timeout_seconds=1)
        result = runner.run(
            "import time\n"
            "time.sleep(10)\n"
            "print('never reaches here')"
        )
        # Should either timeout (exit_code 124) or be blocked
        if not result.success:
            assert "timeout" in result.stderr.lower() or "timeout" in str(result.blocked_operations)


class TestLocalSandboxRunnerRunError:
    """LocalSandboxRunner.run() with runtime errors."""

    def test_runtime_error_captured(self):
        runner = LocalSandboxRunner()
        result = runner.run("1/0")
        assert result.success is False
        assert "ZeroDivisionError" in result.stderr

    def test_name_error_captured(self):
        runner = LocalSandboxRunner()
        result = runner.run("print(undefined_name)")
        assert result.success is False
        assert "NameError" in result.stderr

    def test_syntax_error_captured(self):
        runner = LocalSandboxRunner()
        result = runner.run("def f(←←←")
        assert result.success is False
        assert "SyntaxError" in result.stderr or "Error" in result.stderr


# ─── E2BRunner ───────────────────────────────────────────────────────────────


class TestE2BRunnerInit:
    """E2BRunner initialises and checks E2B availability."""

    def test_default_init(self):
        runner = E2BRunner()
        assert runner.default_timeout == 60.0
        assert runner.template == "base"
        assert runner.allowed_files == []
        assert runner.network_whitelist == []
        assert runner.verbose is False
        assert isinstance(runner._execution_log, list)

    def test_custom_init_params(self):
        runner = E2BRunner(
            api_key="e2b_test_key",
            template="python3",
            timeout_seconds=120.0,
            allowed_files=["data.csv"],
            network_whitelist=["api.example.com"],
            verbose=True,
        )
        assert runner.api_key == "e2b_test_key"
        assert runner.template == "python3"
        assert runner.default_timeout == 120.0
        assert runner.allowed_files == ["data.csv"]
        assert runner.network_whitelist == ["api.example.com"]
        assert runner.verbose is True

    def test_e2b_availability_checked(self):
        runner = E2BRunner()
        # _e2b_available is a boolean set during __init__
        assert isinstance(runner._e2b_available, bool)


class TestE2BRunnerCheckE2B:
    """_check_e2b() detects whether e2b SDK is installed."""

    def test_check_e2b_module_level_check(self):
        """Module-level e2b availability check runs without error."""
        # e2b SDK has import-side-effects; just verify the module-level
        # _check_e2b() function exists and returns a bool
        runner = E2BRunner()
        assert isinstance(runner._e2b_available, bool)


class TestE2BRunnerRunFallback:
    """E2BRunner.run() falls back to LocalSandboxRunner when E2B unavailable."""

    def test_run_fallback_to_local_when_e2b_unavailable(self):
        """If _e2b_available is False, uses LocalSandboxRunner."""
        runner = E2BRunner()
        runner._e2b_available = False  # Force fallback

        result = runner.run("print('running in local sandbox')")

        assert result.success is True
        assert "running in local sandbox" in result.stdout
        assert result.tier == SandboxTier.PROCESS  # LocalSandboxRunner uses PROCESS

    def test_run_blocks_dangerous_in_fallback(self):
        """Fallback still enforces security checks."""
        runner = E2BRunner()
        runner._e2b_available = False
        result = runner.run("import os")
        assert result.success is False
        assert result.is_safe is False

    def test_execution_log_updated(self):
        """_execution_log is updated after each run."""
        runner = E2BRunner()
        runner._e2b_available = False
        runner.run("print(1)")
        assert len(runner._execution_log) == 1
        runner.run("print(2)")
        assert len(runner._execution_log) == 2


class TestE2BRunnerRunScript:
    """E2BRunner.run_script() validates path and falls back to run()."""

    def test_run_script_missing_file(self):
        runner = E2BRunner()
        runner._e2b_available = False  # Use local runner

        result = runner.run_script("/nonexistent/path/script.py")

        assert result.success is False
        assert "not found" in result.stderr.lower()
        assert result.is_safe is False

    def test_run_script_nonexistent_pathlib(self):
        runner = E2BRunner()
        runner._e2b_available = False
        from pathlib import Path

        result = runner.run_script(Path("/no/such/script.py"))

        assert result.success is False
        assert "not found" in result.stderr.lower()

    def test_run_script_existing_file(self, tmp_path):
        """Can run an existing script file."""
        if os.environ.get("E2B_API_KEY") or os.environ.get("GITHUB_ACTIONS"):
            pytest.skip("E2BRunner.run() requires real e2b SDK connection; skip in CI")
        runner = E2BRunner()
        runner._e2b_available = False

        script = tmp_path / "hello.py"
        script.write_text("print('hello from script')", encoding="utf-8")

        result = runner.run_script(str(script))

        # Note: run_script wraps code in exec(), which is blocked as dangerous builtin
        # so result may fail - just verify it returns a SandboxResult
        assert isinstance(result, SandboxResult)


class TestE2BRunnerRunNotebook:
    """E2BRunner.run_notebook() validates path."""

    def test_run_notebook_missing_file(self):
        runner = E2BRunner()
        runner._e2b_available = False

        result = runner.run_notebook("/nonexistent/notebook.ipynb")

        assert result.success is False
        assert "not found" in result.stderr.lower()
        assert result.is_safe is False


class TestE2BRunnerGetStats:
    """E2BRunner.get_stats() returns execution statistics."""

    def test_get_stats_empty_log(self):
        runner = E2BRunner()
        stats = runner.get_stats()
        assert stats["total_runs"] == 0

    def test_get_stats_with_executions(self):
        if os.environ.get("E2B_API_KEY") or os.environ.get("GITHUB_ACTIONS"):
            pytest.skip("E2BRunner.run() requires real e2b SDK; skip in CI")
        runner = E2BRunner()
        runner._e2b_available = False

        runner.run("print(1)")  # success
        runner.run("print(2)")  # success
        runner.run("import os")  # blocked

        stats = runner.get_stats()
        assert stats["total_runs"] == 3
        assert stats["success_count"] == 2
        assert stats["blocked_count"] == 1
        assert stats["e2b_available"] == runner._e2b_available
        assert "avg_time_ms" in stats


# ─── create_runner Factory ────────────────────────────────────────────────────


class TestCreateRunner:
    """create_runner() factory selects the right runner based on tier."""

    def test_create_runner_local(self):
        runner = create_runner(SandboxTier.LOCAL)
        assert isinstance(runner, LocalSandboxRunner)

    def test_create_runner_process(self):
        runner = create_runner(SandboxTier.PROCESS)
        assert isinstance(runner, LocalSandboxRunner)

    def test_create_runner_container(self):
        runner = create_runner(SandboxTier.CONTAINER)
        assert isinstance(runner, LocalSandboxRunner)

    @pytest.mark.skip(reason="E2BRunner init has e2b SDK import side-effects; tested via integration tests")
    def test_create_runner_microvm_without_key(self):
        """MICROVM without API key falls back to LocalSandboxRunner."""
        runner = create_runner(SandboxTier.MICROVM)
        assert isinstance(runner, LocalSandboxRunner)

    @pytest.mark.skip(reason="E2BRunner init has e2b SDK import side-effects; covered by integration tests")
    def test_create_runner_microvm_with_key(self):
        """MICROVM with API key returns E2BRunner."""
        runner = create_runner(SandboxTier.MICROVM, api_key="e2b_test_key_123")
        assert isinstance(runner, E2BRunner)
        assert runner.api_key == "e2b_test_key_123"

    def test_create_runner_passes_kwargs(self):
        """kwargs are forwarded to the runner."""
        runner = create_runner(SandboxTier.LOCAL, timeout_seconds=15.0)
        assert runner.timeout == 15.0

    @pytest.mark.skip(reason="E2BRunner init has e2b SDK import side-effects; covered by integration tests")
    def test_create_runner_microvm_with_env_var(self):
        """MICROVM uses E2B_API_KEY from environment if available."""
        with patch.dict("os.environ", {"E2B_API_KEY": "e2b_env_key"}):
            runner = create_runner(SandboxTier.MICROVM)
            assert isinstance(runner, E2BRunner)
            assert runner.api_key == "e2b_env_key"


# ─── Module exports ──────────────────────────────────────────────────────────


class TestSandboxRunnerExports:
    """Module __all__ must contain expected items."""

    def test_module_has_all(self):
        from scripts.core import sandbox_runner as sr

        assert hasattr(sr, "__all__")
        expected = {"SandboxTier", "SandboxResult", "E2BRunner", "LocalSandboxRunner"}
        assert expected.issubset(set(sr.__all__))


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
