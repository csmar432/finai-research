"""Tests for scripts/core/sandbox_executor.py — DependencyAnalyzer and ExecutionResult.

These tests cover the pure-logic portions of FullSandboxExecutor that can be
unit-tested without actually executing sandboxed Python code.
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
    from scripts.core.sandbox_executor import DependencyAnalyzer, ExecutionResult, FullSandboxExecutor
except Exception as _exc:
    pytest.skip(f"sandbox_executor not importable: {_exc}", allow_module_level=True)


# ─── DependencyAnalyzer ────────────────────────────────────────────────────────


class TestDependencyAnalyzer:
    def test_analyze_stdlib_import(self):
        """stdlib imports must be excluded from the result list."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze("import os\nimport sys\nimport collections")
        for dep in deps:
            assert dep not in ("os", "sys", "collections"), f"stdlib {dep!r} leaked into deps"

    def test_analyze_third_party_import(self):
        """Third-party packages must appear in the result list."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze("import pandas\nimport numpy")
        assert "pandas" in deps
        assert "numpy" in deps

    def test_analyze_from_import(self):
        """from X import Y must extract X as the package."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze("from sklearn import linear_model\nfrom scipy import stats")
        assert "sklearn" in deps
        assert "scipy" in deps

    def test_analyze_nested_package(self):
        """import a.b.c must record only the top-level package."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze("import pandas.core.frame")
        assert "pandas" in deps
        assert "pandas.core.frame" not in deps

    def test_analyze_mixed(self):
        """Mixture of stdlib, third-party, and from-imports."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze(
            "import os\nimport pandas as pd\nfrom numpy import array\nfrom collections import Counter"
        )
        assert "os" not in deps
        assert "pd" not in deps       # alias, not top-level
        assert "pandas" in deps
        assert "numpy" in deps
        assert "collections" not in deps

    def test_analyze_syntax_error(self):
        """SyntaxError in the code must return empty list, not raise."""
        analyzer = DependencyAnalyzer()
        # Real syntax error: incomplete code
        result = analyzer.analyze("import pandas  ?")
        assert result == []

    def test_analyze_empty_code(self):
        """Empty code must return empty list."""
        analyzer = DependencyAnalyzer()
        assert analyzer.analyze("") == []

    def test_analyze_alias(self):
        """import X as Y must record X, not Y."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze("import pandas as pd\nimport numpy as np")
        assert "pandas" in deps
        assert "numpy" in deps
        assert "pd" not in deps
        assert "np" not in deps

    def test_analyze_relative_import(self):
        """Relative imports (from . import x) must be ignored."""
        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze("from . import utils\nfrom .. import models")
        assert "." not in deps
        assert ".." not in deps


# ─── ExecutionResult ──────────────────────────────────────────────────────────


class TestExecutionResult:
    def test_to_dict_basic(self):
        """to_dict() must serialize all fields correctly."""
        result = ExecutionResult(
            success=True,
            stdout="hello",
            stderr="",
            return_value=42,
            execution_time_ms=100.5,
            plots=[],
            dependencies_installed=["pandas"],
            memory_mb=50.0,
            error_type=None,
            error_message=None,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "hello"
        assert d["return_value"] == 42
        assert d["execution_time_ms"] == 100.5
        assert d["dependencies_installed"] == ["pandas"]
        assert d["memory_mb"] == 50.0
        assert d["error_type"] is None
        assert d["error_message"] is None

    def test_to_dict_plots_paths_serialized(self):
        """to_dict() must convert Path plots to strings."""
        result = ExecutionResult(
            success=True,
            stdout="",
            stderr="",
            return_value=None,
            execution_time_ms=0.0,
            plots=[Path("/tmp/plot.png"), Path("/tmp/chart.pdf")],
            dependencies_installed=[],
            memory_mb=0.0,
            error_type=None,
            error_message=None,
        )
        d = result.to_dict()
        assert d["plots"] == ["/tmp/plot.png", "/tmp/chart.pdf"]

    def test_to_dict_failure_fields(self):
        """error_type and error_message must be present on failure."""
        result = ExecutionResult(
            success=False,
            stdout="",
            stderr="ZeroDivisionError",
            return_value=None,
            execution_time_ms=10.0,
            plots=[],
            dependencies_installed=[],
            memory_mb=0.0,
            error_type="ZeroDivisionError",
            error_message="division by zero",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error_type"] == "ZeroDivisionError"
        assert d["error_message"] == "division by zero"


# ─── FullSandboxExecutor helper methods ───────────────────────────────────────


class TestSandboxExecutorTruncateOutput:
    def test_truncate_output_under_limit(self):
        """Short output must not be truncated."""
        executor = FullSandboxExecutor(timeout_seconds=10, max_output_lines=100)
        text = "hello\nworld"
        result = executor._truncate_output(text)
        assert result == text

    def test_truncate_output_over_limit(self):
        """Output exceeding max_output_lines must include truncation notice."""
        executor = FullSandboxExecutor(timeout_seconds=10, max_output_lines=3)
        lines = "\n".join(f"line {i}" for i in range(10))
        result = executor._truncate_output(lines)
        # Should keep first 3 lines
        assert "line 0" in result
        assert "line 9" not in result
        # Should indicate truncation
        assert "truncated" in result.lower()

    def test_truncate_output_exact_limit(self):
        """Output with exactly max_output_lines must be unchanged."""
        executor = FullSandboxExecutor(timeout_seconds=10, max_output_lines=5)
        lines = "\n".join(f"line {i}" for i in range(5))
        result = executor._truncate_output(lines)
        assert result == lines


class TestSandboxExecutorInit:
    def test_init_defaults(self):
        """FullSandboxExecutor must initialize with sensible defaults."""
        ex = FullSandboxExecutor()
        assert ex.timeout_seconds == 30.0
        assert ex.max_memory_mb == 512
        assert ex.max_output_lines == 1000
        assert ex.sandbox_dir is None

    def test_init_custom(self):
        """Custom parameters must be accepted."""
        ex = FullSandboxExecutor(
            timeout_seconds=60,
            max_memory_mb=1024,
            max_output_lines=500,
            allowed_packages=["pandas", "numpy"],
        )
        assert ex.timeout_seconds == 60
        assert ex.max_memory_mb == 1024
        assert ex.allowed_packages == {"pandas", "numpy"}

    def test_history_starts_empty(self):
        """_history must be initialised as an empty list."""
        ex = FullSandboxExecutor()
        assert ex._history == []

    def test_get_execution_history(self):
        """get_history() must return the history list."""
        ex = FullSandboxExecutor()
        assert ex.get_history() == []


# ─── E2B Executor (health check paths) ────────────────────────────────────────


class TestE2BExecutor:
    def test_init_defaults(self):
        """E2BExecutor must accept api_key=None and use env var."""
        from scripts.core.sandbox_executor import E2BExecutor
        # Without env var, api_key should be empty string
        with patch.dict(os.environ, {}, clear=True):
            ex = E2BExecutor(api_key=None)
            assert ex.api_key == ""

    def test_init_with_env_var(self):
        """E2BExecutor should read E2B_API_KEY from env when api_key is None."""
        from scripts.core.sandbox_executor import E2BExecutor
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key-123"}):
            ex = E2BExecutor(api_key=None)
            assert ex.api_key == "test-key-123"

    def test_health_check_no_key(self):
        """health_check() must return healthy=False when no E2B_API_KEY."""
        from scripts.core.sandbox_executor import E2BExecutor
        with patch.dict(os.environ, {}, clear=True):
            ex = E2BExecutor(api_key="")
            result = ex.health_check()
            assert result["healthy"] is False
            assert "not set" in str(result).lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
