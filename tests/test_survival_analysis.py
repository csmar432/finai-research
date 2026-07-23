"""survival_analysis 单元测试 (P0-D, audit 2026-06-27)."""

from __future__ import annotations



def test_module_imports():
    from scripts.research_framework.survival_analysis import (
        CoxPHModel, KaplanMeier,
    )
    assert CoxPHModel is not None
    assert KaplanMeier is not None


def test_kaplan_meier_init():
    """KaplanMeier 估计器。"""
    from scripts.research_framework.survival_analysis import KaplanMeier
    km = KaplanMeier()
    assert km is not None


def test_nelson_aalen_init():
    """NelsonAalen 累积风险估计器。"""
    from scripts.research_framework.survival_analysis import NelsonAalen
    na = NelsonAalen()
    assert na is not None


def test_cox_ph_init():
    """CoxPHModel 半参数 Cox 回归。"""
    from scripts.research_framework.survival_analysis import CoxPHModel
    m = CoxPHModel()
    assert m is not None


def test_competing_risks_init():
    """CompetingRisks 多风险模型。"""
    from scripts.research_framework.survival_analysis import CompetingRisks
    m = CompetingRisks()
    assert m is not None
