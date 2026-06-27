"""panel_cointegration 单元测试 (P0-D, audit 2026-06-27)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_module_imports():
    from scripts.research_framework.panel_cointegration import (
        PanelCointegrationTest, CointegrationResult,
        CrossSectionalDependence, ECMResult,
    )
    assert PanelCointegrationTest is not None
    assert CointegrationResult is not None


def test_panel_cointegration_init():
    """PanelCointegrationTest 初始化（带 trend 参数）。"""
    from scripts.research_framework.panel_cointegration import PanelCointegrationTest
    m = PanelCointegrationTest(trend="c", max_lags=4)
    assert m.trend == "c"
    assert m.max_lags == 4


def test_panel_cointegration_init_various_trends():
    """各种 trend 参数。"""
    from scripts.research_framework.panel_cointegration import PanelCointegrationTest
    for trend in ["c", "ct", "ctt", "none"]:
        m = PanelCointegrationTest(trend=trend, max_lags=2)
        assert m.trend == trend


def test_cointegration_result_is_dataclass():
    """CointegrationResult 必须是 dataclass。"""
    from scripts.research_framework.panel_cointegration import CointegrationResult
    import dataclasses
    assert dataclasses.is_dataclass(CointegrationResult)


def test_cross_sectional_dependence_init():
    """CrossSectionalDependence 测试类。"""
    from scripts.research_framework.panel_cointegration import CrossSectionalDependence
    obj = CrossSectionalDependence()
    assert obj is not None
