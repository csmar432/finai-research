"""run_did's within-transform must reproduce the dummy-variable (LSDV) TWFE estimate.

Regression guard for the Frisch–Waugh–Lovell bug where y and the controls were
demeaned but the DID interaction stayed on its original scale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from scripts.research_framework.pipeline import run_did


def _panel(n_firms: int = 40, n_years: int = 6, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    firms = np.repeat(np.arange(n_firms), n_years)
    years = np.tile(np.arange(2015, 2015 + n_years), n_firms)
    treat = (firms % 2 == 0).astype(float)
    post = (years >= 2018).astype(float)
    firm_fe = rng.normal(size=n_firms)[firms]
    year_fe = np.linspace(0, 1, n_years)[years - 2015]
    x1 = rng.normal(size=len(firms)) + 0.5 * firm_fe
    y = 2.0 * treat * post + 0.7 * x1 + firm_fe + year_fe + rng.normal(scale=0.3, size=len(firms))
    return pd.DataFrame(
        {"ticker": firms.astype(str), "year": years, "treat": treat, "post": post, "x1": x1, "y": y}
    )


def _lsdv(df: pd.DataFrame, fe_cols: list[str]) -> float:
    X = pd.DataFrame({"did": df["treat"] * df["post"], "x1": df["x1"]})
    for col in fe_cols:
        X = pd.concat([X, pd.get_dummies(df[col], prefix=col, drop_first=True).astype(float)], axis=1)
    X = sm.add_constant(X)
    return float(sm.OLS(df["y"].values, X.values).fit().params[1])


def test_two_way_within_matches_lsdv_on_balanced_panel():
    df = _panel()
    res = run_did(df, "y", "treat", "post", ["x1"], firm_col="ticker", year_col="year")
    assert abs(res["did_coef"] - _lsdv(df, ["ticker", "year"])) < 1e-8
    assert abs(res["did_coef"] - 2.0) < 0.15


def test_one_way_within_matches_lsdv_on_unbalanced_panel():
    df = _panel().sample(frac=0.8, random_state=1)
    res = run_did(
        df, "y", "treat", "post", ["x1"], firm_col="ticker", year_col="year", use_year_fe=False
    )
    assert abs(res["did_coef"] - _lsdv(df, ["ticker"])) < 1e-8


def test_pooled_ols_has_an_intercept():
    df = _panel()
    res = run_did(
        df, "y", "treat", "post", ["x1"], firm_col="ticker", year_col="year",
        use_firm_fe=False, use_year_fe=False,
    )
    assert "const" in res["all_coefs"]
    assert abs(res["did_coef"] - _lsdv(df, [])) < 1e-8
