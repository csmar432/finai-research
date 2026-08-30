"""Gold-slot tables must actually run, and refuse contract-violating input."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.gold_tables import (
    build_gold_tables,
    figure_gate_from_event_study,
)


def _panel(n_firms: int = 40, effect: float = 0.05) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for i in range(n_firms):
        treat = int(i % 2 == 0)
        for year in range(2016, 2022):
            post = int(year >= 2019)
            rows.append(
                {
                    "ticker": f"F{i:03d}",
                    "year": year,
                    "esg_high": treat,
                    "post": post,
                    "roa": 0.03 + effect * treat * post + rng.normal(0, 0.01),
                    "lev": rng.normal(0.35, 0.1),
                    "size": rng.normal(21.0, 1.0),
                    "cash_ratio": 0.1 + 0.04 * treat * post + rng.normal(0, 0.01),
                }
            )
    return pd.DataFrame(rows)


def _build(**kw):
    return build_gold_tables(
        _panel(),
        y_var="roa",
        treat_var="esg_high",
        time_var="post",
        unit_col="ticker",
        year_col="year",
        **kw,
    )


def test_sample_flow_records_n_at_every_step():
    t = _build(x_vars=["lev", "size"])
    steps = [r["step"] for r in t.sample_flow]
    assert steps[0] == "原始面板"
    assert steps[-1] == "估计样本"
    assert all(r["n_obs"] > 0 for r in t.sample_flow)
    assert t.sample_flow[0]["n_units"] == 40


def test_structure_facts_are_a_2x2_with_raw_did():
    t = _build(x_vars=["lev"])
    assert len(t.facts_before_reg) == 4
    assert {(r["treat"], r["post"]) for r in t.facts_before_reg} == {
        (0, 0), (0, 1), (1, 0), (1, 1)
    }
    # Planted effect is +0.05; the unadjusted 2x2 difference must recover it.
    assert t.raw_did == pytest.approx(0.05, abs=0.01)


def test_stepwise_ladder_adds_information_column_by_column():
    t = _build(x_vars=["lev", "size"])
    labels = [c.label for c in t.stepwise]
    assert labels[0] == "裸估计"
    assert "+ 控制变量" in labels
    assert t.tighter is not None
    assert t.tighter.unit_fe and t.tighter.time_fe
    assert t.tighter.controls
    # The tighter column is the last one, i.e. the main column.
    assert t.main_column is t.tighter
    assert t.main_column.coef == pytest.approx(0.05, abs=0.02)
    assert t.main_column.pval < 0.05


def test_slots_only_claim_what_ran():
    t = _build(x_vars=["lev"])
    slots = t.to_slots()
    for name in ("desc", "facts_before_reg", "baseline_stepwise", "tighter_compare", "sample_flow"):
        assert name in slots
    assert "mechanism" not in slots, "no named M means no mechanism slot"


def test_named_mechanism_produces_a_t_to_m_table():
    t = _build(x_vars=["lev", "size"], mechanism_vars=["cash_ratio"])
    assert [m.channel for m in t.mechanism] == ["cash_ratio"]
    assert t.mechanism[0].coef == pytest.approx(0.04, abs=0.02)
    assert "mechanism" in t.to_slots()


def test_mechanism_cannot_double_as_a_control():
    with pytest.raises(ValueError, match="同构念"):
        _build(x_vars=["lev", "cash_ratio"], mechanism_vars=["cash_ratio"])


def test_missing_required_column_is_refused():
    with pytest.raises(ValueError, match="缺少必需列"):
        build_gold_tables(
            _panel().drop(columns=["post"]),
            y_var="roa",
            treat_var="esg_high",
            time_var="post",
        )


def test_markdown_prints_tables_and_the_human_todo():
    md = _build(x_vars=["lev"], mechanism_vars=["cash_ratio"]).to_markdown()
    assert "## A1 样本流" in md
    assert "## T3 逐步加信息" in md
    assert "## T4 处理→机制变量" in md
    assert "仍须人工补" in md


def test_figure_gate_counts_post_period_ci_crossings():
    rows = [
        {"horizon": -2, "ci_lower": -0.01, "ci_upper": 0.01, "pval": 0.8},
        {"horizon": 1, "ci_lower": 0.01, "ci_upper": 0.05, "pval": 0.01},
        {"horizon": 2, "ci_lower": -0.01, "ci_upper": 0.06, "pval": 0.20},
    ]
    gate = figure_gate_from_event_study(rows, placebo_tail_p=0.02)
    assert gate["event_post_n"] == 2
    assert gate["event_post_cross0_n"] == 1
    assert gate["placebo_true_outside_mass"] is True
    assert gate["event_pre_min_p"] == pytest.approx(0.8)


def test_figure_gate_tolerates_garbage_rows():
    gate = figure_gate_from_event_study([{"horizon": "x"}, "junk", {}])
    assert gate == {"event_post_n": 0, "event_post_cross0_n": 0}
