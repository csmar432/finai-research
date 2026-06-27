"""scripts/econometrics.py stub 模块测试.

历史：原 scripts/econometrics.py 在 528e17b (2026-06-19) 被删除。
9 个文件仍 try/except ImportError 兜底，但 empirical_agent.py 的
class body 引用 EvaluationResult 触发 NameError。

本测试验证 stub 模块恢复后：
  1. 9 个引用方模块全部能 import
  2. stub 提供的所有符号可访问
  3. STUB 警告正常工作
"""

from __future__ import annotations

import importlib
import warnings

import pytest


# 9 个引用 scripts.econometrics 的模块
USERS = [
    "scripts.econometrics_extended",
    "scripts.empirical_agent",
    "scripts.generate_empirical_tables",
    "scripts.green_credit_regression",
    "scripts.interactive_paper_pipeline",
    "scripts.research_directions.carbon_economics",
    "scripts.research_directions.political_economy_finance",
    "scripts.research_directions.fintech_innovation",
    "scripts.research_directions.real_estate_finance",
]


@pytest.mark.parametrize("module_name", USERS)
def test_econometrics_user_module_importable(module_name):
    """每个引用 scripts.econometrics 的模块必须能 import（不再 ModuleNotFoundError）。"""
    importlib.import_module(module_name)


def test_stub_module_importable():
    """scripts.econometrics stub 必须能 import。"""
    mod = importlib.import_module("scripts.econometrics")
    assert mod is not None


def test_stub_exposes_required_types():
    """stub 必须提供 empirical_agent class body 引用的所有类型。"""
    from scripts import econometrics
    for name in [
        "EvaluationResult",
        "AdjustmentAction",
        "AdjustmentStrategy",
        "DiagnosticResult",
        "EmpiricalAdvisor",
        "ModelSwitch",
    ]:
        assert hasattr(econometrics, name), f"scripts.econometrics 缺 {name}"


def test_stub_exposes_required_functions():
    """stub 必须提供诊断和工具函数。"""
    from scripts import econometrics
    for name in [
        "breusch_pagan_test",
        "durban_watson_test" if False else "durbin_watson_test",
        "vif_test",
        "white_test",
        "descriptive_stats",
        "table_to_markdown",
        "winsorize_all",
    ]:
        assert hasattr(econometrics, name), f"scripts.econometrics 缺 {name}"


def test_empirical_agent_does_not_raise_name_error():
    """关键回归测试：scripts.empirical_agent.py 导入时不应 NameError。

    Bug 历史：empirical_agent.py:168 有
        class EmpiricalAgentResult:
            advisor_evaluation: EvaluationResult | None = None
    当 EvaluationResult 未导入时，class body 解析时 NameError。
    """
    # 重置 import 缓存
    import sys
    for k in list(sys.modules.keys()):
        if "empirical_agent" in k or "econometrics" in k:
            del sys.modules[k]
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        importlib.import_module("scripts.empirical_agent")


def test_stub_warning_emitted():
    """import stub 模块应触发 DeprecationWarning。"""
    # 强制重新导入
    import sys
    if "scripts.econometrics" in sys.modules:
        del sys.modules["scripts.econometrics"]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        importlib.import_module("scripts.econometrics")
        deprecation = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation) >= 1, "scripts.econometrics 应发出 DeprecationWarning"