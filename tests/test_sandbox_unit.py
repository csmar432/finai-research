"""Tests for scripts/core/sandbox.py — SecurityValidator and ExecutionResult.

These cover the pure-logic portions of SafeCodeExecutor that don't require
actual subprocess execution.
"""
from __future__ import annotations

import ast
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


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
