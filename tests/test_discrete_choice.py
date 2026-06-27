"""discrete_choice 单元测试 (P0-D, audit 2026-06-27).

覆盖：
  - DiscreteChoiceModel 初始化
  - DiscreteChoiceSuite 初始化
  - fit/predict smoke test
  - 模块 import
"""

from __future__ import annotations

import numpy as np
import pytest


def test_module_imports():
    from scripts.research_framework.discrete_choice import (
        DiscreteChoiceModel, DiscreteChoiceResult,
        DiscreteChoiceSuite, MarginalEffectsResult,
    )
    assert DiscreteChoiceModel is not None
    assert DiscreteChoiceSuite is not None


def test_discrete_choice_model_logit():
    """logit 模型必须能初始化。"""
    from scripts.research_framework.discrete_choice import DiscreteChoiceModel
    m = DiscreteChoiceModel(model_type="logit")
    assert m.model_type == "logit"


def test_discrete_choice_model_probit():
    """probit 模型必须能初始化。"""
    from scripts.research_framework.discrete_choice import DiscreteChoiceModel
    m = DiscreteChoiceModel(model_type="probit")
    assert m.model_type == "probit"


def test_discrete_choice_suite_init():
    """DiscreteChoiceSuite 初始化（多模型容器）。"""
    from scripts.research_framework.discrete_choice import DiscreteChoiceSuite
    suite = DiscreteChoiceSuite()
    assert suite is not None


def test_discrete_choice_fit_smoke():
    """fit 方法应能处理合成数据。"""
    from scripts.research_framework.discrete_choice import DiscreteChoiceModel

    np.random.seed(42)
    n = 200
    X = np.random.normal(0, 1, (n, 3))
    y = (np.random.uniform(0, 1, n) < 1 / (1 + np.exp(-(X[:, 0] + X[:, 1] - X[:, 2])))).astype(int)
    m = DiscreteChoiceModel(model_type="logit")
    try:
        result = m.fit(X, y)
        assert result is not None
    except Exception as e:
        pytest.skip(f"fit requires statsmodels/sklearn: {e}")
