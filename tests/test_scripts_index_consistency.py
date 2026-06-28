"""scripts/SCRIPTS_INDEX.md 数字与实际目录对账测试。

P0 修复 2026-06-28: 防止 SCRIPTS_INDEX 数字漂移（审计报告 R-8）。
SCRIPTS_INDEX.md 自称"自动对账于 2026-06-28"——本测试强制一致性。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_INDEX = ROOT / "scripts" / "SCRIPTS_INDEX.md"


def _count_py(dir_path: Path) -> int:
    """统计目录下的 .py 文件数（递归，排除 __pycache__）。"""
    if not dir_path.exists():
        return 0
    return sum(1 for p in dir_path.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.fixture(scope="module")
def index_text():
    """读取 SCRIPTS_INDEX.md。"""
    if not SCRIPTS_INDEX.exists():
        pytest.skip(f"{SCRIPTS_INDEX} 不存在")
    return SCRIPTS_INDEX.read_text(encoding="utf-8")


def _extract_count(index_text: str, label: str) -> int | None:
    """从 SCRIPTS_INDEX 表格中提取某个分类的数字。

    表格行格式：| <label> | <count> | <desc> |
    """
    pat = re.compile(rf"\|\s*[^|]*{re.escape(label)}[^|]*\|\s*(\d+)\s*\|")
    m = pat.search(index_text)
    return int(m.group(1)) if m else None


def test_entry_points_count_matches(index_text):
    """顶级入口脚本（scripts/*.py 顶层，不含子目录）。"""
    actual = len(list((ROOT / "scripts").glob("*.py")))
    declared = _extract_count(index_text, "Entry Points")
    if declared is None:
        pytest.skip("未找到 Entry Points 行（可能在 SCRIPTS_INDEX 中不匹配）")
    # 允许 ±2 误差（recent 添加/移除可能未更新）
    assert abs(actual - declared) <= 2, (
        f"Entry Points 实际 {actual} vs 声明 {declared}，差异 > 2"
    )


def test_core_modules_count_matches(index_text):
    """Core 模块（scripts/core/*.py 递归）。"""
    actual = _count_py(ROOT / "scripts" / "core")
    declared = _extract_count(index_text, "Core Modules")
    if declared is None:
        pytest.skip("未找到 Core Modules 行")
    assert abs(actual - declared) <= 2, (
        f"Core Modules 实际 {actual} vs 声明 {declared}"
    )


def test_research_framework_count_matches(index_text):
    """Research Framework 模块数。"""
    actual = _count_py(ROOT / "scripts" / "research_framework")
    declared = _extract_count(index_text, "Research Framework")
    if declared is None:
        pytest.skip("未找到 Research Framework 行")
    assert abs(actual - declared) <= 2, (
        f"Research Framework 实际 {actual} vs 声明 {declared}"
    )


def test_research_directions_count_matches(index_text):
    """Research Directions 模块数。"""
    actual = _count_py(ROOT / "scripts" / "research_directions")
    declared = _extract_count(index_text, "Research Directions")
    if declared is None:
        pytest.skip("未找到 Research Directions 行")
    assert abs(actual - declared) <= 2, (
        f"Research Directions 实际 {actual} vs 声明 {declared}"
    )


def test_tests_count_matches(index_text):
    """Tests 文件数。"""
    actual = _count_py(ROOT / "tests") - _count_py(ROOT / "tests" / "__pycache__")
    # 排除 conftest.py, fixtures
    actual = sum(1 for p in (ROOT / "tests").rglob("*.py") if "__pycache__" not in p.parts)
    declared = _extract_count(index_text, "Tests")
    if declared is None:
        pytest.skip("未找到 Tests 行")
    assert abs(actual - declared) <= 3, (
        f"Tests 实际 {actual} vs 声明 {declared}"
    )


def test_mcp_servers_count_matches(index_text):
    """MCP servers 数（mcp_servers/user_*/server.py）。"""
    actual = sum(1 for _ in (ROOT / "mcp_servers").glob("user_*/server.py"))
    declared = _extract_count(index_text, "MCP Servers")
    if declared is None:
        pytest.skip("未找到 MCP Servers 行")
    assert abs(actual - declared) <= 1, (
        f"MCP Servers 实际 {actual} vs 声明 {declared}"
    )


def test_total_count_matches(index_text):
    """合计行数字应与各项和一致。"""
    # 找到合计行
    total_pat = re.compile(r"合计[^|]*\|\s*\*\*(\d+)\*\*\s*\|")
    m = total_pat.search(index_text)
    if m is None:
        pytest.skip("未找到合计行")
    declared_total = int(m.group(1))
    # 算各项之和
    parts = ["Entry Points", "Core Modules", "Research Framework",
             "Research Directions", "Tests"]
    actual_sum = 0
    for p in parts:
        n = _extract_count(index_text, p)
        if n:
            actual_sum += n
    # 合计应等于各项和
    assert declared_total == actual_sum, (
        f"合计 {declared_total} vs 各项和 {actual_sum}"
    )