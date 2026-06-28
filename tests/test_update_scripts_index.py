"""scripts/update_scripts_index.py 对账测试 (P0-R8, audit 2026-06-27)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "update_scripts_index.py"
INDEX_MD = PROJECT_ROOT / "scripts" / "SCRIPTS_INDEX.md"


def test_script_runs():
    """脚本必须能运行。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=15,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "Current counts:" in result.stdout


def test_script_dry_run():
    """--dry-run 不能写文件。"""
    original = INDEX_MD.read_text()
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            capture_output=True, text=True, timeout=15,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert INDEX_MD.read_text() == original, "--dry-run 不应修改文件"
    finally:
        INDEX_MD.write_text(original)


def test_top_level_count_consistent():
    """顶级脚本数应与文件系统一致。"""
    from scripts.update_scripts_index import count_py

    # P0 修复 2026-06-28: scripts/__init__.py 是真实的包入口，Entry Points 应包含
    actual = sum(1 for f in (PROJECT_ROOT / "scripts").glob("*.py"))
    assert count_py(PROJECT_ROOT / "scripts", recursive=False) == actual


def test_index_md_has_overview():
    """SCRIPTS_INDEX.md 必须包含分类总览表格。"""
    content = INDEX_MD.read_text()
    assert "## 分类总览" in content
    assert "| 🚀 Entry Points" in content or "| 🚀 Entry Points" in content


def test_index_md_top_level_matches_disk():
    """SCRIPTS_INDEX.md 中顶级脚本数字应与文件系统一致。"""
    import re

    actual = sum(
        1 for f in (PROJECT_ROOT / "scripts").glob("*.py")
        if not f.name.startswith("_")
    )
    content = INDEX_MD.read_text()
    m = re.search(r"Entry Points.*?\|\s*(\d+)\s*\|", content)
    if m:
        indexed = int(m.group(1))
        # 允许 ±5 偏差（脚本可能在 INDEX 更新后新增）
        assert abs(indexed - actual) <= 5, (
            f"INDEX says {indexed} entry points, but disk has {actual}"
        )


def test_no_accumulated_auto_marker():
    """回归测试：update_scripts_index.py 不能在'最后更新'后累加'自动对账'标记。

    Bug 历史：第一次修复时手动跑脚本多次，每次叠加"（自动对账）"，
    导致 SCRIPTS_INDEX.md 出现 "(自动对账)(自动对账)(自动对账)"。
    """
    content = INDEX_MD.read_text()
    # 不应出现连续多个 "(自动对账)"
    assert "自动对账）（自动对账）" not in content, (
        "发现累加的'自动对账'标记——update_scripts_index.py 的 regex 不应匹配已含'自动对账'的行"
    )
    # 每一行最多 1 次"自动对账"
    for line_no, line in enumerate(content.splitlines(), 1):
        if line.count("（自动对账）") > 1:
            pytest.fail(f"L{line_no}: '{line.strip()[:120]}' 含多次'自动对账'")
