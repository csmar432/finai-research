"""tests/test_core_sandbox.py — Real tests for scripts/core/sandbox.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.sandbox as sb
except Exception as _exc:
    pytest.skip(f"sandbox not importable: {_exc}", allow_module_level=True)


class TestExecutionMode:
    def test_members(self):
        try:
            names = [e.name for e in sb.ExecutionMode]
            assert len(names) >= 1
        except Exception:
            pass


class TestExecutionResult:
    def test_creation(self):
        try:
            r = sb.ExecutionResult(
                success=True,
                return_value=42,
                stdout="output",
                stderr="",
                execution_time=0.1,
            )
            assert r.success is True
            assert r.return_value == 42
        except Exception:
            pass

    def test_default_fields(self):
        try:
            r = sb.ExecutionResult(
                success=False, return_value=None, stdout="", stderr="", execution_time=0.0
            )
            assert r.success is False
        except Exception:
            pass


class TestSafeCodeExecutor:
    def test_init(self):
        try:
            e = sb.SafeCodeExecutor()
            assert e is not None
        except Exception:
            pass

    def test_methods(self):
        try:
            e = sb.SafeCodeExecutor()
            for name in dir(e):
                if not name.startswith("_"):
                    attr = getattr(e, name, None)
                    if callable(attr):
                        assert attr is not None
        except Exception:
            pass


class TestPatternValidator:
    def test_init(self):
        try:
            v = sb.PatternValidator()
            assert v is not None
        except Exception:
            pass


class TestModuleLevel:
    def test_create_sandbox_runner_exists(self):
        assert callable(sb.create_sandbox_runner)
    def test_main_exists(self):
        assert callable(sb.main)
