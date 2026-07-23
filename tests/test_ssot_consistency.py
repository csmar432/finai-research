"""scripts/count_assets.py --sync-ssot 和 PROJECT_NUMBERS.json 一致性测试."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "count_assets.py"
SSOT = PROJECT_ROOT / "scripts" / "PROJECT_NUMBERS.json"


def test_sync_ssot_works():
    """--sync-ssot 必须能写 PROJECT_NUMBERS.json."""
    import os
    env = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "SHELL": os.environ.get("SHELL", "/bin/zsh"),
        "USER": os.environ.get("USER", ""),
        "PYTHONPATH": str(PROJECT_ROOT),  # 让 `from scripts.count_mcp import` 工作
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--sync-ssot"],
        capture_output=True, text=True, timeout=30,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"sync-ssot failed: {result.stderr}"
    assert "Synced" in result.stdout


def test_ssot_mcp_free_matches_disk():
    """PROJECT_NUMBERS.json 中 MCP free 必须与 count_assets 一致."""
    from scripts.count_assets import count_mcp_servers
    disk_free = count_mcp_servers()["free_no_key"]

    ssot = json.loads(SSOT.read_text())
    ssot_free = ssot["mcp"]["breakdown"]["fully_free"]

    assert disk_free == ssot_free, (
        f"SSOT says {ssot_free} free, disk says {disk_free}. "
        "Run `python scripts/count_assets.py --sync-ssot` to fix."
    )


def test_ssot_test_files_matches_disk():
    """SSOT test_files 必须与 count_assets 一致."""
    from scripts.count_assets import count_test_files
    disk = count_test_files()

    ssot = json.loads(SSOT.read_text())
    ssot_files = ssot["testing"]["test_files"]

    assert disk["files"] == ssot_files, (
        f"SSOT says {ssot_files} files, disk says {disk['files']}"
    )


def test_ssot_method_modules_matches_disk():
    """SSOT method_modules 必须与 count_assets 一致."""
    from scripts.count_assets import count_econometric_methods
    disk = count_econometric_methods()

    ssot = json.loads(SSOT.read_text())
    ssot_total = ssot["econometrics"]["total_method_modules"]

    assert disk == ssot_total, (
        f"SSOT says {ssot_total} method modules, disk says {disk}"
    )


def test_ssot_has_required_fields():
    """SSOT 必须包含所有必需字段。"""
    ssot = json.loads(SSOT.read_text())
    assert "mcp" in ssot
    assert "breakdown" in ssot["mcp"]
    assert "fully_free" in ssot["mcp"]["breakdown"]
    assert "econometrics" in ssot
    assert "testing" in ssot
    assert "test_files" in ssot["testing"]
    assert "last_verified" in ssot


def test_no_legacy_field_in_ssot():
    """SSOT 不应再有旧字段名 total_independent_implementations。

    Bug 历史：2026-06-26 的 SSOT 用旧字段名，sync_numbers.py 读不到
    新字段（total_method_modules）。修复时同时保留两套字段名作为兼容。
    """
    ssot = json.loads(SSOT.read_text())
    # 检查没有把旧字段保留在不该保留的位置
    econ = ssot.get("econometrics", {})
    assert "total_independent_implementations" not in econ, (
        "PROJECT_NUMBERS.json econometrics 中不应再保留旧字段 total_independent_implementations"
    )


def test_sync_apply_no_markdown_bold_breakage():
    r"""回归测试：sync_numbers.py --apply 不能产生 *** (三个星号) markdown 错误。

    Bug 历史：第一次同步时第一个 pattern `\*(\d+)` 与第二个 pattern `\*\*(\d+)`
    顺序错乱，导致 `**43` 被两次替换为 `***43`。
    """
    import subprocess
    import os
    env = os.environ.copy()
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "scripts/sync_numbers.py", "--apply"],
        capture_output=True, text=True, timeout=30,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"sync --apply failed: {result.stderr}"

    # 检查所有 .md 不含 ***
    for md_file in ["README.md", "README_EN.md", "CLAUDE.md"]:
        path = PROJECT_ROOT / md_file
        if path.exists():
            content = path.read_text()
            # 找异常的 "***"（中间不是空格）—— markdown 加粗最多用 **
            import re
            matches = re.findall(r"\*\*\*[^*]", content)
            assert len(matches) == 0, (
                f"{md_file} 含 *** markdown 异常（sync_numbers.py bug 复发）: {matches[:3]}"
            )


def test_ssot_zero_stub_servers():
    """回归测试：SSOT 中 stub_servers 应为空列表。

    2026-06-26 旧 SSOT 错误地把 chinese_customs/cnrd/sipo/third_party_esg
    标记为 stub，但实测它们都有完整实现（仅在无 API key 时返回 mock）。
    """
    ssot = json.loads(SSOT.read_text())
    assert ssot["mcp"]["stub_servers"] == [], (
        f"SSOT stub_servers 应为空（无真正的 stub），实际: {ssot['mcp']['stub_servers']}"
    )


def test_ssot_zero_test_modules_matches_disk():
    """回归测试：SSOT zero_test_modules 必须 = 磁盘独立验证。

    Bug 历史（2026-06-28 深度核验）：
    SSOT 手写 zero_test_modules = [Triple Diff, Local Projections, Mediation,
    KOB Decomposition, Vuong Test] 5 个，但实际磁盘验证 16 个零测试模块。
    count_assets 现在自动同步，应永不再误。

    本测试用独立 AST 方式验证（非 count_assets）以避免递归依赖。
    多命名约定支持（与 scripts/count_assets.py 一致）：
      - test_<module>.py
      - test_<module>_*.py (deep_exec / smoke 变体)
      - test_research_framework_<module>.py (旧风格)
      - test_research_framework_<module>_*.py (旧风格变体)
    """
    ssot = json.loads(SSOT.read_text())
    reported = set(ssot["econometrics"].get("zero_test_modules", []))

    # 独立磁盘验证（多命名约定，与 count_assets.py 保持一致）
    rf = Path("scripts/research_framework")
    tests = Path("tests")
    actual = set()
    for m in rf.glob("*.py"):
        if m.name.startswith("_"):
            continue
        mod = m.stem
        if (tests / f"test_{mod}.py").exists():
            continue
        if list(tests.glob(f"test_{mod}_*.py")):
            continue
        if (tests / f"test_research_framework_{mod}.py").exists():
            continue
        if list(tests.glob(f"test_research_framework_{mod}_*.py")):
            continue
        actual.add(mod)

    assert reported == actual, (
        f"SSOT zero_test_modules 漂移: 报告 {len(reported)} 个, 实际 {len(actual)} 个.\n"
        f"  差集: {reported ^ actual}\n"
        f"  修复方法: `python scripts/count_assets.py --sync-ssot`"
    )
