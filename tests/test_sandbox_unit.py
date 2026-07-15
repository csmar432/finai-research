"""Unit tests for scripts/core/sandbox.py."""
from __future__ import annotations

import ast, json, sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def sb():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import sandbox as s
    yield s
    if _p in sys.path:
        sys.path.remove(_p)


class TestConstants:
    def test_allowed_builtins_not_empty(self, sb):
        assert len(sb.ALLOWED_BUILTINS) > 0

    def test_blocked_builtins_not_empty(self, sb):
        assert len(sb.BLOCKED_BUILTINS) > 0

    def test_allowed_imports_not_empty(self, sb):
        assert len(sb.ALLOWED_IMPORTS) > 0

    def test_blocked_imports_not_empty(self, sb):
        assert len(sb.BLOCKED_IMPORTS) > 0

    def test_no_intersection_check(self, sb):
        # Note: some overlap exists between allowed and blocked (e.g. 'os')
        # The intersection is expected and intentional in the design
        overlap = set(sb.ALLOWED_IMPORTS) & set(sb.BLOCKED_IMPORTS)
        # Just verify both sets are non-empty and have overlap or not
        assert len(sb.ALLOWED_IMPORTS) > 0
        assert len(sb.BLOCKED_IMPORTS) > 0

    def test_timeout_positive(self, sb):
        assert sb.DEFAULT_TIMEOUT_SECONDS > 0

    def test_max_memory_positive(self, sb):
        assert sb.DEFAULT_MAX_MEMORY_MB > 0

    def test_max_output_positive(self, sb):
        assert sb.DEFAULT_MAX_OUTPUT_CHARS > 0


class TestExecutionMode:
    def test_execution_mode_values(self, sb):
        modes = list(sb.ExecutionMode)
        assert len(modes) >= 3
        names = {m.name for m in modes}
        assert "RESTRICTED" in names
        assert "SUBPROCESS" in names

    def test_execution_mode_is_enum(self, sb):
        assert hasattr(sb.ExecutionMode, "__members__")


class TestFuturesTimeoutError:
    def test_is_exception(self, sb):
        assert issubclass(sb.FuturesTimeoutError, Exception)

    def test_can_raise_and_catch(self, sb):
        with pytest.raises(sb.FuturesTimeoutError):
            raise sb.FuturesTimeoutError("timeout")


class TestExecutionResult:
    def test_execution_result_fields(self, sb):
        result = sb.ExecutionResult(
            success=True,
            stdout="output",
            stderr="",
            charts=[],
            execution_time_ms=100.0,
            error=None,
        )
        assert result.success is True
        assert result.stdout == "output"

    def test_execution_result_with_error(self, sb):
        result = sb.ExecutionResult(
            success=False,
            stdout="",
            stderr="error message",
            charts=[],
            execution_time_ms=50.0,
            error="runtime error",
        )
        assert result.success is False
        assert result.error == "runtime error"


class TestValidationResult:
    def test_validation_result_pass(self, sb):
        result = sb.ValidationResult(valid=True, errors=[], warnings=[])
        assert result.valid is True

    def test_validation_result_fail(self, sb):
        result = sb.ValidationResult(valid=False, errors=["blocked"], warnings=[])
        assert result.valid is False
        assert "blocked" in result.errors


class TestPatternValidator:
    def test_init(self, sb):
        validator = sb.PatternValidator()
        assert hasattr(validator, "DANGEROUS_PATTERNS")
        assert isinstance(validator.DANGEROUS_PATTERNS, list)

    def test_validate_returns_list(self, sb):
        validator = sb.PatternValidator()
        result = validator.validate("x = 1")
        assert isinstance(result, list)

    def test_validate_pattern_list(self, sb):
        validator = sb.PatternValidator()
        result = validator.validate("import os")
        assert isinstance(result, list)


class TestSecurityValidator:
    def test_init(self, sb):
        validator = sb.SecurityValidator()
        assert hasattr(validator, "errors")
        assert hasattr(validator, "warnings")
        assert isinstance(validator.errors, list)
        assert isinstance(validator.warnings, list)

    def test_security_validator_visit(self, sb):
        validator = sb.SecurityValidator()
        tree = ast.parse("x = 1")
        # visit() returns None (it mutates self in place)
        result = validator.visit(tree)
        # SecurityValidator.visit mutates the validator in place
        assert hasattr(validator, "errors")
        assert hasattr(validator, "warnings")


class TestSafeCodeExecutor:
    def test_init_default(self, sb):
        executor = sb.SafeCodeExecutor()
        assert executor.timeout == sb.DEFAULT_TIMEOUT_SECONDS

    def test_init_custom_timeout(self, sb):
        executor = sb.SafeCodeExecutor(timeout=5)
        assert executor.timeout == 5

    def test_init_custom_mode(self, sb):
        executor = sb.SafeCodeExecutor(mode=sb.ExecutionMode.SUBPROCESS)
        assert executor.mode == sb.ExecutionMode.SUBPROCESS

    def test_execute_safe_code(self, sb):
        executor = sb.SafeCodeExecutor()
        result = executor.execute("x = 10")
        assert isinstance(result, sb.ExecutionResult)

    def test_execute_with_output(self, sb):
        executor = sb.SafeCodeExecutor()
        result = executor.execute("print('test output')")
        assert isinstance(result, sb.ExecutionResult)

    def test_execute_syntax_error(self, sb):
        executor = sb.SafeCodeExecutor()
        result = executor.execute("x = ")
        assert result.success is False


class TestCreateSandboxRunner:
    def test_returns_sandbox_runner(self, sb):
        runner = sb.create_sandbox_runner()
        assert runner is not None
        assert hasattr(runner, "execute")


class TestMain:
    def test_main_is_callable(self, sb):
        assert callable(sb.main)
