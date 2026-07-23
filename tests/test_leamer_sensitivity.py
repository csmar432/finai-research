"""leamer_sensitivity 单元测试 (P0-D, audit 2026-06-27)."""

from __future__ import annotations



def test_module_imports():
    from scripts.research_framework.leamer_sensitivity import (
        BoundingResult, LeamerSensitivity,
    )
    assert LeamerSensitivity is not None
    assert BoundingResult is not None


def test_leamer_sensitivity_init():
    from scripts.research_framework.leamer_sensitivity import LeamerSensitivity
    m = LeamerSensitivity()
    assert m is not None


def test_leamer_result_is_dataclass():
    from scripts.research_framework.leamer_sensitivity import LeamerResult
    import dataclasses
    assert dataclasses.is_dataclass(LeamerResult)
    # 验证必要字段
    fields = {f.name for f in dataclasses.fields(LeamerResult)}
    assert "baseline_coef" in fields
    assert "extreme_bounds" in fields


def test_bounding_result_is_dataclass():
    from scripts.research_framework.leamer_sensitivity import BoundingResult
    import dataclasses
    assert dataclasses.is_dataclass(BoundingResult)


def test_dynamic_panel_diagnostics_is_dataclass():
    from scripts.research_framework.leamer_sensitivity import DynamicPanelDiagnostics
    import dataclasses
    assert dataclasses.is_dataclass(DynamicPanelDiagnostics)
    fields = {f.name for f in dataclasses.fields(DynamicPanelDiagnostics)}
    assert "ar1_stat" in fields
    assert "sargan_stat" in fields
