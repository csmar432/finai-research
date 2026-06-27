"""time_varying_models 单元测试 (P0-D, audit 2026-06-27).

覆盖 TVPVAR + DCCGARCH。
"""

from __future__ import annotations

import numpy as np
import pytest


def test_module_imports():
    from scripts.research_framework.time_varying_models import (
        TVPVAR, DCCGARCH, DCCGARCHResult, Path, Any,
    )
    assert TVPVAR is not None
    assert DCCGARCH is not None


def test_tvp_var_init():
    """TVPVAR 模型必须能初始化。"""
    from scripts.research_framework.time_varying_models import TVPVAR
    m = TVPVAR(p=1, sv=True, keep_posterior_draws=False)
    assert m.p == 1
    assert m.sv is True


def test_tvp_var_init_no_sv():
    """TVPVAR (无随机波动) 也必须能初始化。"""
    from scripts.research_framework.time_varying_models import TVPVAR
    m = TVPVAR(p=2, sv=False, keep_posterior_draws=False)
    assert m.p == 2


def test_dcc_garch_init():
    """DCCGARCH 模型必须能初始化。"""
    from scripts.research_framework.time_varying_models import DCCGARCH
    m = DCCGARCH()
    assert m is not None


def test_dcc_garch_result_dataclass():
    """DCCGARCHResult 必须是 dataclass。"""
    from scripts.research_framework.time_varying_models import DCCGARCHResult
    import dataclasses
    assert dataclasses.is_dataclass(DCCGARCHResult)
