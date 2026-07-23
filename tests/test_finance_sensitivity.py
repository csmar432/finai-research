"""finance_sensitivity 单元测试 (P0-D, audit 2026-06-27)."""

from __future__ import annotations



def test_module_imports():
    from scripts.research_framework.finance_sensitivity import (
        ContagionTest, CreditRiskSensitivity,
    )
    assert ContagionTest is not None
    assert CreditRiskSensitivity is not None


def test_contagion_test_init():
    from scripts.research_framework.finance_sensitivity import ContagionTest
    m = ContagionTest()
    assert m is not None


def test_credit_risk_sensitivity_init():
    from scripts.research_framework.finance_sensitivity import CreditRiskSensitivity
    m = CreditRiskSensitivity()
    assert m is not None


def test_eberstein_magnac_result_is_dataclass():
    from scripts.research_framework.finance_sensitivity import EbersteinMagnacResult
    import dataclasses
    assert dataclasses.is_dataclass(EbersteinMagnacResult)


def test_levinsohn_petrin_estimator_init():
    from scripts.research_framework.finance_sensitivity import LevinsohnPetrinEstimator
    m = LevinsohnPetrinEstimator()
    assert m is not None
