"""Tests for PR-3 method parity: exact_permutation / event_study_extensions / calendar_qualifier."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.exact_permutation import (
    _enumerate_multinomial_labels,
    exact_permutation_test,
)
from scripts.research_framework.event_study_extensions import (
    bmp_standardise,
    generalized_sign_test,
    kolari_pynnonen_adjust,
    rank_test,
)
from scripts.research_framework.calendar_qualifier import (
    _cn_holidays,
    aggregate_qualifications,
    qualify_firm_events,
)


# ── exact_permutation ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "group_sizes,n_total,expected",
    [
        ([3, 3, 2], 8, 560),   # CBAM: 8 events 3/3/2
        ([3, 5], 8, 56),
        ([4, 4], 8, 70),
        ([8], 8, 1),
        ([2, 2, 2], 6, 90),
        ([1, 1, 1, 1], 4, 24),
    ],
)
def test_multinomial_enumeration_count(group_sizes, n_total, expected):
    count = sum(1 for _ in _enumerate_multinomial_labels(n_total, group_sizes))
    assert count == expected, f"group_sizes={group_sizes}: expected {expected}, got {count}"


def test_exact_permutation_560_cases():
    per_event = np.array([1.2, 0.8, 1.5, -0.5, -0.3, -1.1, 0.2, 0.4])
    labels = np.array([0, 0, 0, 1, 1, 1, 2, 2])
    res = exact_permutation_test(per_event, labels, group_a=1, group_b=0)
    assert res.perm_count == 560
    assert -2.0 < res.observed_stat < -1.5
    assert 0 < res.p_two_sided < 1
    assert 0 <= res.p_one_sided_greater <= 1


def test_exact_permutation_known_insignificant():
    """All-zero CARs → observed stat 0 → p=1."""
    per_event = np.zeros(8)
    labels = np.array([0, 0, 0, 1, 1, 1, 2, 2])
    res = exact_permutation_test(per_event, labels, group_a=1, group_b=0)
    assert res.observed_stat == 0.0
    assert res.p_two_sided == 1.0


# ── event_study_extensions ──────────────────────────────────────────────


def test_bmp_standardise():
    cars = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
    stds = np.array([0.01, 0.02, 0.03, 0.01, 0.02])
    res = bmp_standardise(cars, stds)
    assert isinstance(res.standardised_car, np.ndarray)
    assert res.standardised_car.shape == cars.shape
    assert not np.isnan(res.t_stat) or cars.std() == 0


def test_bmp_stds_all_zeros_falls_back_to_nan():
    cars = np.array([1.0, 2.0])
    stds = np.array([0.0, 0.0])
    res = bmp_standardise(cars, stds)
    assert np.isnan(res.t_stat)


def test_generalized_sign_test():
    cars = np.array([1.0, 2.0, -0.5, -0.3])
    res = generalized_sign_test(cars)
    assert isinstance(res.statistic, float)
    assert 0 <= res.p_value <= 1
    assert res.statistic == 2  # 2 positive out of 4


def test_rank_test_zeros():
    cars = np.array([0.0, 0.0, 0.0])
    res = rank_test(cars)
    assert res.p_value == 1.0


def test_kolari_pynnonen_shapes():
    cars = np.array([0.01, -0.02, 0.03, -0.01])
    resids = np.random.default_rng(42).standard_normal((4, 100))
    res = kolari_pynnonen_adjust(cars, resids)
    assert isinstance(res.t_stat_adjusted, float)
    assert 0 <= res.p_value <= 1


# ── calendar_qualifier ────────────────────────────────────────────────


def test_cn_holidays_includes_oct1():
    h = _cn_holidays()
    for y in range(2020, 2031):
        assert any(d.year == y and d.month == 10 and d.day == 1 for d in h)


def test_cn_holidays_includes_jan1():
    h = _cn_holidays()
    for y in range(2020, 2031):
        assert date(y, 1, 1) in h


def test_qualify_firm_events_holiday_flag():
    df = pd.DataFrame({
        "ticker": ["A", "B"],
        "event_date": [datetime(2023, 10, 1), datetime(2023, 6, 1)],
        "ret": [0.01, 0.02],
    })
    result = qualify_firm_events(df)
    assert result["qualified"].tolist() == [False, True]
    assert (result["disqualify_reason"] == "holiday_on_event_day").tolist() == [True, False]


def test_aggregate_qualifications():
    qual = pd.DataFrame({
        "qualified": [True, True, False, False],
        "disqualify_reason": ["", "", "holiday_on_event_day", "holiday_on_event_day"],
    })
    agg = aggregate_qualifications(qual)
    assert agg["n_total"] == 4
    assert agg["n_qualified"] == 2
    assert agg["n_disqualified"] == 2
    assert agg["disqualify_reasons"]["holiday_on_event_day"] == 2
