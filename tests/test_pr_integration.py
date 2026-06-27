"""集成测试：start_research.py + VariableRedundancyResolver + DataGate + DID Audit Guard.

验证 PR1/PR2/PR5 在真实流水线中的集成（不仅仅是单元测试）。

设计原则：
  - 不修改模块全局状态（不 install guard，避免污染其他测试）
  - 每个测试独立运行，不依赖执行顺序
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def test_pr5_did_audit_guard_intercepts_mock_data():
    """PR5 集成测试：DID 审计守卫拦截 mock 数据进入 ModernDiDEngine。"""
    from scripts.core.did_audit_guard import (
        install_audit_guard_into_modern_did,
        assert_real_data,
    )

    if not install_audit_guard_into_modern_did():
        pytest.skip("ModernDiDEngine 未找到（守卫未安装）")

    # 直接调用核心函数（不实例化引擎以避免污染其他测试）
    df = pd.DataFrame({
        "firm_id": ["F1", "F2"],
        "year": [2020, 2021],
        "y": [1.0, 2.0],
        "treat": [0, 1],
        "_synthetic": [True, True],
    })
    result = assert_real_data(df, context="test_mock_intercept", raise_on_mock=False)
    assert result.is_real is False
    assert len(result.sentinel_columns) > 0


def test_pr5_did_audit_guard_allows_real_data():
    """PR5 集成测试：真实数据可以通过守卫。"""
    from scripts.core.did_audit_guard import assert_real_data

    df = pd.DataFrame({
        "firm_id": ["F1", "F2"],
        "year": [2020, 2021],
        "y": [1.0, 2.0],
        "treat": [0, 1],
        "provenance_id": ["tushare:stock_basic", "tushare:stock_basic"],
    })
    result = assert_real_data(df, context="test_real_passes", raise_on_mock=False)
    assert result.is_real is True


def test_pr2_resolver_imports_correctly():
    """PR2 集成测试：VariableRedundancyResolver 可独立调用。"""
    from scripts.core.variable_redundancy import VariableRedundancyResolver

    resolver = VariableRedundancyResolver()
    report = resolver.resolve_by_topic(
        topic="碳排放权交易对企业绿色创新的影响", identification="DID"
    )
    assert report is not None
    # 验证 4 个候选变量类型都存在（用 PR2 实际字段名）
    assert hasattr(report, "dependent_candidates")
    assert hasattr(report, "independent_candidates")
    assert hasattr(report, "control_candidates")
    assert hasattr(report, "policy_candidates")


def test_pr2_data_gate_imports_correctly():
    """PR2 集成测试：DataGate 可独立调用。"""
    from scripts.core.data_gate import DataGate, DataGateLevel

    assert DataGate is not None
    assert DataGateLevel.PROVENANCE is not None


def test_start_research_imports_pr1_pr2_pr5():
    """PR1/PR2/PR5 集成测试：start_research.py 正确导入所有 PR 模块。"""
    import scripts.start_research as sr

    assert hasattr(sr, "NoraOrchestrator")
    assert hasattr(sr, "VariableRedundancyResolver")
    assert hasattr(sr, "DataGate")
    assert hasattr(sr, "DataGateLevel")
    assert hasattr(sr, "install_all_audit_guards")


def test_start_research_cli_help_works():
    """CLI 集成测试：start_research.py --help 可运行（不崩）。"""
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "start_research.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"--help 失败: {result.stderr}"
    assert "NORA" in result.stdout or "research" in result.stdout.lower()


def test_startup_check_cli_works():
    """PR6 集成测试：startup_check.py 可运行。"""
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "startup_check.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    assert "Traceback" not in result.stderr or result.returncode == 0, (
        f"startup_check.py 崩溃: {result.stderr[:500]}"
    )

