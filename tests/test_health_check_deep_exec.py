"""tests/test_health_check_deep_exec.py — Deep tests for health_check helpers.

Targets uncovered helpers in scripts/health_check.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.health_check import (
        ProblemCategory,
        ProblemItem,
        DiagnosticResult,
        _detect_platform,
        _c, green, red, yellow, cyan, bold, dim,
    )
except Exception as exc:
    pytest.skip(f"health_check not importable: {exc}", allow_module_level=True)


# ─── ANSI color functions ─────────────────────────────────────────────

class TestAnsiColors:
    def test_red(self):
        result = red("test")
        assert isinstance(result, str)
        assert "test" in result
        assert "\033[91m" in result

    def test_green(self):
        result = green("ok")
        assert "\033[92m" in result
        assert "ok" in result

    def test_yellow(self):
        result = yellow("warn")
        assert "\033[93m" in result

    def test_cyan(self):
        result = cyan("info")
        assert "\033[96m" in result

    def test_bold(self):
        result = bold("title")
        assert "\033[1m" in result

    def test_dim(self):
        result = dim("subtle")
        assert "\033[2m" in result

    def test_c_internal(self):
        result = _c("text", "\033[91m")
        assert "text" in result
        assert "\033[91m" in result
        assert "\033[0m" in result


# ─── ProblemCategory ──────────────────────────────────────────────────

class TestProblemCategory:
    def test_values(self):
        vals = [p.value for p in ProblemCategory]
        assert "network" in vals
        assert "api_key" in vals
        assert "dependency" in vals
        assert "mcp" in vals
        assert "data_source" in vals
        assert "ok" in vals

    def test_count(self):
        assert len(list(ProblemCategory)) >= 6

    def test_is_string_enum(self):
        assert isinstance(ProblemCategory.NETWORK, str)


# ─── ProblemItem ────────────────────────────────────────────────────

class TestProblemItem:
    def test_init(self):
        item = ProblemItem(
            category=ProblemCategory.NETWORK,
            name="test_service",
            name_zh="测试服务",
            message="Connection failed",
            fix_steps=["Step 1", "Step 2"],
            severity="high",
        )
        assert item.category == ProblemCategory.NETWORK
        assert item.name == "test_service"
        assert item.name_zh == "测试服务"
        assert item.severity == "high"
        assert len(item.fix_steps) == 2

    def test_to_dict(self):
        item = ProblemItem(
            category=ProblemCategory.API_KEY,
            name="deepseek",
            name_zh="DeepSeek",
            message="Key missing",
            fix_steps=["Add key"],
            details={"key_name": "DEEPSEEK_API_KEY"},
        )
        d = item.to_dict()
        assert isinstance(d, dict)
        assert d["category"] == "api_key"
        assert d["name"] == "deepseek"
        assert d["details"]["key_name"] == "DEEPSEEK_API_KEY"

    def test_default_severity(self):
        item = ProblemItem(
            category=ProblemCategory.DEPENDENCY,
            name="module",
            name_zh="模块",
            message="Import failed",
            fix_steps=[],
        )
        assert item.severity == "high"

    def test_default_details(self):
        item = ProblemItem(
            category=ProblemCategory.MCP,
            name="server",
            name_zh="服务器",
            message="Not running",
            fix_steps=[],
        )
        assert item.details == {}


# ─── DiagnosticResult ───────────────────────────────────────────────

class TestDiagnosticResult:
    def test_init(self):
        result = DiagnosticResult(
            timestamp="2026-01-01",
            platform="cursor",
            llm_available=True,
            llm_status="ok",
            mcp_enabled_count=10,
            mcp_verified_count=8,
            problem_counts={"network": 1, "api_key": 2},
            problems=[],
            system_ready=False,
            recommendations=["Fix network"],
        )
        assert result.timestamp == "2026-01-01"
        assert result.platform == "cursor"
        assert result.llm_available is True
        assert result.mcp_enabled_count == 10
        assert result.mcp_verified_count == 8
        assert result.system_ready is False
        assert len(result.recommendations) == 1

    def test_to_dict(self):
        result = DiagnosticResult(
            timestamp="2026-07-06",
            platform="claude_code",
            llm_available=False,
            llm_status="no_key",
            mcp_enabled_count=0,
            mcp_verified_count=0,
            problem_counts={},
            problems=[],
            system_ready=False,
            recommendations=[],
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["platform"] == "claude_code"
        assert d["llm_available"] is False
        assert d["system_ready"] is False

    def test_to_json(self):
        result = DiagnosticResult(
            timestamp="2026-07-06",
            platform="cursor",
            llm_available=True,
            llm_status="ok",
            mcp_enabled_count=5,
            mcp_verified_count=5,
            problem_counts={},
            problems=[],
            system_ready=True,
            recommendations=[],
        )
        j = result.to_json()
        assert isinstance(j, str)
        assert '"platform": "cursor"' in j
        assert '"system_ready": true' in j

    def test_verify_mode_default(self):
        result = DiagnosticResult(
            timestamp="2026-07-06",
            platform="cursor",
            llm_available=True,
            llm_status="ok",
            mcp_enabled_count=0,
            mcp_verified_count=0,
            problem_counts={},
            problems=[],
            system_ready=True,
            recommendations=[],
        )
        assert result.verify_mode is False

    def test_verify_mode_set(self):
        result = DiagnosticResult(
            timestamp="2026-07-06",
            platform="cursor",
            llm_available=True,
            llm_status="ok",
            mcp_enabled_count=0,
            mcp_verified_count=0,
            problem_counts={},
            problems=[],
            system_ready=True,
            recommendations=[],
            verify_mode=True,
        )
        assert result.verify_mode is True

    def test_with_problem_items(self):
        item = ProblemItem(
            category=ProblemCategory.API_KEY,
            name="tushare",
            name_zh="Tushare",
            message="Token missing",
            fix_steps=["Get token"],
        )
        result = DiagnosticResult(
            timestamp="2026-07-06",
            platform="cursor",
            llm_available=False,
            llm_status="no_key",
            mcp_enabled_count=0,
            mcp_verified_count=0,
            problem_counts={"api_key": 1},
            problems=[item],
            system_ready=False,
            recommendations=["Add TUSHARE_TOKEN"],
        )
        d = result.to_dict()
        assert len(d["problems"]) == 1
        assert d["problems"][0]["name"] == "tushare"


# ─── _detect_platform ───────────────────────────────────────────────

class TestDetectPlatform:
    def test_returns_string(self):
        platform = _detect_platform()
        assert isinstance(platform, str)

    def test_returns_known_platform(self):
        platform = _detect_platform()
        # Should return one of the known platform strings
        assert platform in ("cursor", "claude_code", "codex", "vscode", "unknown")

    def test_idempotent(self):
        p1 = _detect_platform()
        p2 = _detect_platform()
        assert p1 == p2
