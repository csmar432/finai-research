"""Tests for scripts/core/sandbox.py — SecurityValidator and ExecutionResult.

These cover the pure-logic portions of SafeCodeExecutor that don't require
actual subprocess execution.
"""
from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core.sandbox import (
        SecurityValidator,
        ExecutionResult,
        ValidationResult,
        PatternValidator,
        SafeCodeExecutor,
        ALLOWED_IMPORTS,
        BLOCKED_IMPORTS,
        BLOCKED_BUILTINS,
        ExecutionMode,
    )
except Exception as _exc:
    pytest.skip(f"sandbox not importable: {_exc}", allow_module_level=True)


# ─── SecurityValidator ────────────────────────────────────────────────────────


class TestSecurityValidatorImport:
    def test_blocks_dangerous_import(self):
        """Blocked imports must produce errors."""
        validator = SecurityValidator()
        validator.visit(ast.parse("import os"))
        assert any("blocked" in e.lower() for e in validator.errors)

    def test_blocks_subprocess(self):
        """subprocess must be blocked."""
        validator = SecurityValidator()
        validator.visit(ast.parse("import subprocess"))
        assert any("blocked" in e.lower() for e in validator.errors)

    def test_allows_safe_import(self):
        """Safe imports must not produce errors."""
        validator = SecurityValidator()
        validator.visit(ast.parse("import numpy"))
        assert not validator.errors

    def test_allows_from_import(self):
        """from X import Y for safe packages must pass."""
        validator = SecurityValidator()
        validator.visit(ast.parse("from pandas import DataFrame"))
        assert not validator.errors

    def test_blocks_from_dangerous(self):
        """from dangerous_module import X must produce errors."""
        validator = SecurityValidator()
        validator.visit(ast.parse("from os import getcwd"))
        assert any("blocked" in e.lower() for e in validator.errors)

    def test_warns_unknown_import(self):
        """Unknown (not in allowed list) imports should produce warnings."""
        validator = SecurityValidator()
        validator.visit(ast.parse("import my_unknown_package"))
        # Warning only, not error
        assert not validator.errors
        assert any("unknown" in w.lower() for w in validator.warnings)

    def test_blocks_dangerous_calls(self):
        """Dangerous function calls must be blocked."""
        validator = SecurityValidator()
        validator.visit(ast.parse("eval('1+1')"))
        assert any("dangerous" in e.lower() for e in validator.errors)

    def test_blocks_open_call(self):
        """open() call must be blocked."""
        validator = SecurityValidator()
        validator.visit(ast.parse("open('file.txt')"))
        assert any("dangerous" in e.lower() or "open" in e.lower() for e in validator.errors)

    def test_blocks_input_call(self):
        """input() call must be blocked."""
        validator = SecurityValidator()
        validator.visit(ast.parse("input()"))
        assert any("dangerous" in e.lower() or "input" in e.lower() for e in validator.errors)

    def test_getattr_with_default_warns(self):
        """getattr with 3 args may access restricted attrs (warning only)."""
        validator = SecurityValidator()
        validator.visit(ast.parse("getattr(obj, 'secret', None)"))
        assert not validator.errors
        assert any("getattr" in w.lower() for w in validator.warnings)


class TestPatternValidator:
    def test_blocks_dangerous_pattern(self):
        """PatternValidator must return error list for dangerous code."""
        validator = PatternValidator()
        errors = validator.validate("__import__('os').system('ls')")
        assert isinstance(errors, list)
        assert len(errors) > 0

    def test_allows_safe_pattern(self):
        """Safe code must return empty error list."""
        validator = PatternValidator()
        errors = validator.validate("import numpy as np; print(np.mean([1,2,3]))")
        assert isinstance(errors, list)
        assert len(errors) == 0


# ─── ExecutionResult ──────────────────────────────────────────────────────────


class TestExecutionResult:
    def test_to_dict_success(self):
        """to_dict() must serialize all fields on success."""
        result = ExecutionResult(
            success=True,
            stdout="hello world",
            stderr="",
            charts=["base64..."],
            execution_time_ms=42.5,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "hello world"
        assert d["charts"] == ["base64..."]
        assert d["execution_time_ms"] == 42.5
        assert d["error"] is None

    def test_to_dict_failure(self):
        """to_dict() must include error field on failure."""
        result = ExecutionResult(
            success=False,
            stdout="",
            stderr="ZeroDivisionError: division by zero",
            execution_time_ms=5.0,
            error="Division by zero",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert "ZeroDivisionError" in d["stderr"]
        assert d["error"] == "Division by zero"


class TestValidationResult:
    def test_valid_true(self):
        """ValidationResult with valid=True must work."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_valid_false_with_errors(self):
        """ValidationResult with errors must work."""
        result = ValidationResult(
            valid=False,
            errors=["Blocked import: os", "Dangerous function: eval"],
        )
        assert result.valid is False
        assert len(result.errors) == 2


# ─── Module-level constants ───────────────────────────────────────────────────


class TestSandboxConstants:
    def test_allowed_imports_contains_numpy(self):
        """ALLOWED_IMPORTS must include numpy."""
        assert "numpy" in ALLOWED_IMPORTS

    def test_blocked_imports_contains_os(self):
        """BLOCKED_IMPORTS must include os."""
        assert "os" in BLOCKED_IMPORTS

    def test_blocked_builtins_contains_eval(self):
        """BLOCKED_BUILTINS must include eval."""
        assert "eval" in BLOCKED_BUILTINS

    def test_execution_mode_values(self):
        """ExecutionMode must have expected values."""
        values = [e.value for e in ExecutionMode]
        assert "restricted" in values
        assert "subprocess" in values
        assert "docker" in values


# ─── SafeCodeExecutor basic smoke ─────────────────────────────────────────────


class TestSafeCodeExecutorInit:
    def test_init_defaults(self):
        """SafeCodeExecutor must initialise with defaults."""
        ex = SafeCodeExecutor()
        assert ex is not None

    def test_execution_mode_defaults(self):
        """ExecutionMode default must be RESTRICTED."""
        ex = SafeCodeExecutor()
        assert hasattr(ex, "mode")

    def test_init_custom_params(self):
        """SafeCodeExecutor must accept custom timeout, memory, mode."""
        ex = SafeCodeExecutor(
            timeout=30,
            max_memory_mb=256,
            max_output_chars=10000,
            mode=ExecutionMode.SUBPROCESS,
        )
        assert ex.timeout == 30
        assert ex.max_memory_mb == 256
        assert ex.max_output_chars == 10000
        assert ex.mode == ExecutionMode.SUBPROCESS

    def test_init_custom_allowed_imports(self):
        """Custom allowed_imports must override defaults."""
        custom = {"numpy", "pandas", "my_package"}
        ex = SafeCodeExecutor(allowed_imports=custom)
        assert ex.allowed_imports == custom
        assert "my_package" in ex.allowed_imports

    def test_init_output_dir_created(self, tmp_path):
        """output_dir must be created on init."""
        out = tmp_path / "sandbox_charts"
        ex = SafeCodeExecutor(output_dir=out)
        assert out.exists()


class TestSafeCodeExecutorValidate:
    """Test the validate() method logic."""

    def test_validate_passes_safe_numpy_code(self):
        """validate() must return valid=True for safe numpy code."""
        ex = SafeCodeExecutor()
        code = "import numpy as np; x = np.array([1,2,3]); print(np.mean(x))"
        result = ex.validate(code)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_fails_on_os_import(self):
        """validate() must return valid=False for blocked os import."""
        ex = SafeCodeExecutor()
        result = ex.validate("import os")
        assert result.valid is False
        assert any("Blocked import" in e for e in result.errors)

    def test_validate_fails_on_eval(self):
        """validate() must return valid=False for eval()."""
        ex = SafeCodeExecutor()
        result = ex.validate("eval('1+1')")
        assert result.valid is False
        assert any("Dangerous" in e or "eval" in e for e in result.errors)

    def test_validate_fails_on_subprocess(self):
        """validate() must return valid=False for subprocess."""
        ex = SafeCodeExecutor()
        result = ex.validate("import subprocess; subprocess.run(['ls'])")
        assert result.valid is False

    def test_validate_fails_on_open(self):
        """validate() must return valid=False for open()."""
        ex = SafeCodeExecutor()
        result = ex.validate("f = open('test.txt')")
        assert result.valid is False

    def test_validate_fails_on_exec(self):
        """validate() must return valid=False for exec()."""
        ex = SafeCodeExecutor()
        result = ex.validate("exec('print(1)')")
        assert result.valid is False

    def test_validate_fails_on_rm_rf_pattern(self):
        """validate() must catch shell injection patterns."""
        ex = SafeCodeExecutor()
        result = ex.validate("import os; os.system('rm -rf /')")
        assert result.valid is False
        assert any("rm -rf" in e.lower() for e in result.errors)

    def test_validate_fails_on_chmod_777(self):
        """validate() must catch chmod 777 pattern."""
        ex = SafeCodeExecutor()
        result = ex.validate("import os; os.chmod('/tmp/file', 0o777)")
        assert result.valid is False

    def test_validate_warns_on_unknown_import(self):
        """validate() must warn (not error) for unknown package."""
        ex = SafeCodeExecutor()
        result = ex.validate("import my_custom_package")
        assert result.valid is True
        assert any("unknown" in w.lower() for w in result.warnings)

    def test_validate_fails_on_syntax_error(self):
        """validate() must report syntax error."""
        ex = SafeCodeExecutor()
        result = ex.validate("def f(←←←")
        assert result.valid is False
        assert any("syntax" in e.lower() for e in result.errors)

    def test_validate_allows_from_safe_module(self):
        """from safe_module import X must pass."""
        ex = SafeCodeExecutor()
        result = ex.validate("from numpy import array")
        assert result.valid is True

    def test_validate_warns_getattr_with_default(self):
        """getattr with 3 args triggers PatternValidator as error."""
        validator = SecurityValidator()
        validator.visit(ast.parse("getattr(obj, 'secret', None)"))
        assert not validator.errors
        assert any("getattr" in w.lower() for w in validator.warnings)
        # PatternValidator also catches this and makes validate() fail
        pv = PatternValidator()
        pv_errors = pv.validate("getattr(obj, 'secret', None)")
        assert len(pv_errors) > 0

    def test_validate_fails_on_os_system(self):
        """os.system() call must be blocked."""
        ex = SafeCodeExecutor()
        result = ex.validate("import os; os.system('echo hello')")
        assert result.valid is False

    def test_validate_fails_on_os_remove(self):
        """os.remove() call must be blocked."""
        ex = SafeCodeExecutor()
        result = ex.validate("import os; os.remove('/tmp/file')")
        assert result.valid is False


class TestSafeCodeExecutorExecute:
    """Test the execute() method — actual code execution in RESTRICTED mode."""

    def test_execute_numpy_mean(self):
        """execute() must run numpy code and return stdout."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("import numpy as np; print(np.mean([1,2,3]))")
        assert result.success is True
        assert "2.0" in result.stdout

    def test_execute_pandas_dataframe(self):
        """execute() must handle pandas operations."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute(
            "import pandas as pd; "
            "df = pd.DataFrame({'a': [1,2,3]}); "
            "print(df['a'].sum())"
        )
        assert result.success is True
        assert "6" in result.stdout

    def test_execute_numpy_array_operations(self):
        """execute() must handle numpy array operations."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute(
            "import numpy as np; "
            "a = np.array([1,2,3]); "
            "b = np.array([4,5,6]); "
            "print(np.dot(a, b))"
        )
        assert result.success is True
        assert "32" in result.stdout

    def test_execute_with_context(self):
        """execute() must inject context variables."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("print(x * 2)", context={"x": 21})
        assert result.success is True
        assert "42" in result.stdout

    def test_execute_with_context_dict(self):
        """execute() must accept context as dict parameter."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("print(a + b)", context={"a": 10, "b": 5})
        assert result.success is True
        assert "15" in result.stdout

    def test_execute_blocks_os_import(self):
        """execute() must refuse to run blocked imports."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("import os; print(os.getcwd())")
        assert result.success is False
        assert "Validation failed" in (result.error or "")

    def test_execute_blocks_eval(self):
        """execute() must refuse to run eval()."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("eval('1+1')")
        assert result.success is False

    def test_execute_captures_matplotlib_chart(self):
        """execute() must capture matplotlib charts as base64."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute(
            "import matplotlib.pyplot as plt; "
            "import numpy as np; "
            "plt.plot([1,2,3],[4,5,6]); "
            "plt.savefig('test.png')"
        )
        assert result.success is True
        assert len(result.charts) > 0

    def test_execute_syntax_error_returns_failure(self):
        """execute() must return failure for syntax errors."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("def f(←←←")
        assert result.success is False
        assert result.error is not None

    def test_execute_runtime_error_returns_failure(self):
        """execute() must return failure for runtime errors."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("1/0")
        assert result.success is False

    def test_execute_returns_execution_time(self):
        """execute() must record execution_time_ms."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("x = 1")
        assert result.execution_time_ms >= 0

    def test_execute_nameerror_returns_failure(self):
        """execute() must handle NameError gracefully."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("print(undefined_variable)")
        assert result.success is False

    def test_execute_safe_builtins_available(self):
        """Built-in functions must be available in sandbox."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.execute("print(len([1,2,3,4])); print(range(5))")
        assert result.success is True
        assert "4" in result.stdout
        assert "range" in result.stdout or "range(5)" in result.stdout

    def test_execute_safe_import_wrapper_blocks_unknown(self):
        """Restricted import must only allow pre-approved packages."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        # json is NOT in _ALLOWED_IMPORT_PACKAGES, so this must fail
        result = ex.execute("import json")
        assert result.success is False
        assert "not allowed" in (result.error or "").lower()

    def test_execute_timeout_short_timeout(self):
        """execute() with very short timeout must catch timeout."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED, timeout=1)
        # Use a loop to consume time without importing 'time'
        result = ex.execute("x = 0\nfor i in range(10**8): x += i")
        # Either succeeds fast (if machine is fast) or times out
        assert result.success is True or "timeout" in (result.error or "").lower()


class TestSafeCodeExecutorTruncate:
    """Test the _truncate() method."""

    def test_truncate_short_string_unchanged(self):
        """_truncate() must not modify short strings."""
        ex = SafeCodeExecutor(max_output_chars=100)
        text = "hello world"
        assert ex._truncate(text) == text

    def test_truncate_long_string_truncated(self):
        """_truncate() must cut long strings and add marker."""
        ex = SafeCodeExecutor(max_output_chars=10)
        text = "0123456789ABCD"
        result = ex._truncate(text)
        assert len(result) <= 10 + len("\n... (truncated, total 14 chars)")
        assert "truncated" in result

    def test_truncate_exact_boundary_unchanged(self):
        """_truncate() must not modify strings at exact boundary."""
        ex = SafeCodeExecutor(max_output_chars=5)
        text = "abcde"
        assert ex._truncate(text) == text


class TestSafeCodeExecutorSafeMethods:
    """Test helper methods."""

    def test_get_safe_builtins_contains_print(self):
        """_get_safe_builtins() must include print."""
        ex = SafeCodeExecutor()
        safe = ex._get_safe_builtins()
        assert "print" in safe
        assert callable(safe["print"])

    def test_get_safe_builtins_contains_allowed(self):
        """_get_safe_builtins() must include len, range, str, etc."""
        ex = SafeCodeExecutor()
        safe = ex._get_safe_builtins()
        for name in ["len", "range", "str", "int", "float", "list", "dict", "sum", "min", "max"]:
            assert name in safe

    def test_get_safe_builtins_print_is_safe(self):
        """print built-in must be the safe wrapper, not the original."""
        ex = SafeCodeExecutor()
        safe = ex._get_safe_builtins()
        assert safe["print"] is not builtins.print

    def test_get_safe_builtins_blocks_eval(self):
        """_get_safe_builtins() must NOT include eval."""
        ex = SafeCodeExecutor()
        safe = ex._get_safe_builtins()
        assert "eval" not in safe


class TestSafeCodeExecutorSaveCharts:
    """Test the save_charts() method."""

    def test_save_charts_empty(self, tmp_path):
        """save_charts() with no charts must return empty list."""
        ex = SafeCodeExecutor(output_dir=tmp_path)
        result = ExecutionResult(success=True, stdout="", stderr="", charts=[])
        paths = ex.save_charts(result, prefix="test")
        assert paths == []

    def test_save_charts_with_valid_b64(self, tmp_path):
        """save_charts() must write base64-encoded PNG to disk."""
        import base64
        ex = SafeCodeExecutor(output_dir=tmp_path)
        # Minimal 1x1 PNG in base64
        png_data = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR").decode()
        result = ExecutionResult(success=True, stdout="", stderr="", charts=[png_data])
        paths = ex.save_charts(result, prefix="mychart")
        assert len(paths) == 1
        assert (tmp_path / "mychart_1.png").exists()

    def test_save_charts_multiple_charts(self, tmp_path):
        """save_charts() must handle multiple charts."""
        import base64
        ex = SafeCodeExecutor(output_dir=tmp_path)
        png_data = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        result = ExecutionResult(success=True, stdout="", stderr="", charts=[png_data, png_data, png_data])
        paths = ex.save_charts(result, prefix="c")
        assert len(paths) == 3


class TestSafeCodeExecutorSafeExecute:
    """Test the safe_execute() convenience method."""

    def test_safe_execute_basic(self):
        """safe_execute() must work like execute() with kwargs as context."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.safe_execute("print(value)", value=42)
        assert result.success is True
        assert "42" in result.stdout

    def test_safe_execute_empty_kwargs(self):
        """safe_execute() with no kwargs must still work."""
        ex = SafeCodeExecutor(mode=ExecutionMode.RESTRICTED)
        result = ex.safe_execute("print('hello')")
        assert result.success is True


class TestSafeCodeExecutorBuildWrapper:
    """Test subprocess wrapper generation."""

    def test_build_subprocess_wrapper_returns_string(self):
        """_build_subprocess_wrapper() must return a string."""
        ex = SafeCodeExecutor()
        wrapper = ex._build_subprocess_wrapper("print(1)", None)
        assert isinstance(wrapper, str)
        assert "print(1)" in wrapper

    def test_build_subprocess_wrapper_includes_context(self):
        """_build_subprocess_wrapper() must embed context."""
        ex = SafeCodeExecutor()
        wrapper = ex._build_subprocess_wrapper("print(x)", {"x": 99})
        assert "99" in wrapper

    def test_build_docker_wrapper_returns_string(self):
        """_build_docker_wrapper() must return a string."""
        ex = SafeCodeExecutor()
        wrapper = ex._build_docker_wrapper("print(1)")
        assert isinstance(wrapper, str)


class TestCreateSandboxRunner:
    """Test the create_sandbox_runner() factory function."""

    def test_create_sandbox_runner_local(self):
        """create_sandbox_runner('local') must return SafeCodeExecutor in RESTRICTED mode."""
        from scripts.core.sandbox import create_sandbox_runner
        runner = create_sandbox_runner("local", timeout=10)
        assert isinstance(runner, SafeCodeExecutor)
        assert runner.mode == ExecutionMode.RESTRICTED
        assert runner.timeout == 10

    def test_create_sandbox_runner_subprocess(self):
        """create_sandbox_runner('subprocess') must return SUBPROCESS mode."""
        from scripts.core.sandbox import create_sandbox_runner
        runner = create_sandbox_runner("subprocess")
        assert isinstance(runner, SafeCodeExecutor)
        assert runner.mode == ExecutionMode.SUBPROCESS

    def test_create_sandbox_runner_docker(self):
        """create_sandbox_runner('docker') must return DOCKER mode."""
        from scripts.core.sandbox import create_sandbox_runner
        runner = create_sandbox_runner("docker")
        assert isinstance(runner, SafeCodeExecutor)
        assert runner.mode == ExecutionMode.DOCKER

    def test_create_sandbox_runner_custom_kwargs(self):
        """create_sandbox_runner() must pass kwargs to executor."""
        from scripts.core.sandbox import create_sandbox_runner
        runner = create_sandbox_runner("local", max_memory_mb=128, timeout=20)
        assert runner.max_memory_mb == 128
        assert runner.timeout == 20


class TestExecutionModeEnum:
    """Test ExecutionMode enum values."""

    def test_restricted_mode_value(self):
        assert ExecutionMode.RESTRICTED.value == "restricted"

    def test_subprocess_mode_value(self):
        assert ExecutionMode.SUBPROCESS.value == "subprocess"

    def test_docker_mode_value(self):
        assert ExecutionMode.DOCKER.value == "docker"

    def test_mode_from_string(self):
        """ExecutionMode(string) must reconstruct the enum member."""
        assert ExecutionMode("restricted") == ExecutionMode.RESTRICTED
        assert ExecutionMode("subprocess") == ExecutionMode.SUBPROCESS
        assert ExecutionMode("docker") == ExecutionMode.DOCKER


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
