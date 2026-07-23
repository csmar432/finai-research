"""vuong_test 单元测试 (P0-D, audit 2026-06-27).

Vuong 模型选择检验 + Clarke 检验。
"""

from __future__ import annotations



def test_module_imports():
    from scripts.research_framework.vuong_test import (
        VuongTest, VuongResult,
    )
    assert VuongTest is not None
    assert VuongResult is not None


def test_vuong_test_init():
    from scripts.research_framework.vuong_test import VuongTest
    m = VuongTest(name1="Linear", name2="Logit")
    assert m.name1 == "Linear"


def test_vuong_result_is_dataclass():
    from scripts.research_framework.vuong_test import VuongResult
    import dataclasses
    assert dataclasses.is_dataclass(VuongResult)
    fields = {f.name for f in dataclasses.fields(VuongResult)}
    assert "vuong_stat" in fields
    assert "pval" in fields
    assert "recommendation" in fields


def test_clarke_test_imports():
    from scripts.research_framework.vuong_test import ClarkeTest, ClarkeTestEN
    assert ClarkeTest is not None
    assert ClarkeTestEN is not None


def test_vuong_helper_functions_exist():
    """vuong_did_vs_rdd 等辅助函数必须存在。"""
    import scripts.research_framework.vuong_test as vt
    for fname in ["vuong_did_vs_rdd", "vuong_different_controls", "vuong_different_samples", "vuong_linear_vs_logit"]:
        assert hasattr(vt, fname), f"Missing {fname}"
        assert callable(getattr(vt, fname))
