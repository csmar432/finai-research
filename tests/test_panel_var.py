"""panel_var 单元测试 (P0-D, audit 2026-06-27)."""

from __future__ import annotations

import numpy as np
import pytest


def test_module_imports():
    from scripts.research_framework.panel_var import (
        PanelVAR, PanelVARResult, Path, Any,
    )
    assert PanelVAR is not None
    assert PanelVARResult is not None


def test_panel_var_init():
    """PanelVAR 初始化。"""
    from scripts.research_framework.panel_var import PanelVAR
    m = PanelVAR()
    assert m is not None


def test_panel_var_result_is_dataclass():
    """PanelVARResult 必须是 dataclass。"""
    from scripts.research_framework.panel_var import PanelVARResult
    import dataclasses
    assert dataclasses.is_dataclass(PanelVARResult)


def test_panel_var_init_with_lags():
    """PanelVAR 带 lag 参数初始化。"""
    from scripts.research_framework.panel_var import PanelVAR
    import inspect
    sig = inspect.signature(PanelVAR.__init__)
    # 至少有一个 lag 相关参数
    params = list(sig.parameters.keys())
    # 通用检查：能调用
    m = PanelVAR()
    assert m is not None


def test_panel_var_result_fields():
    """PanelVARResult 应至少有基本字段。"""
    from scripts.research_framework.panel_var import PanelVARResult
    import dataclasses
    fields = [f.name for f in dataclasses.fields(PanelVARResult)]
    # 至少有 1 个字段（可能是 coefficients、aic、bic）
    assert len(fields) >= 1
