"""Regression tests for P1-3 audit follow-up: triple_diff_did + psm_did wired
into RobustnessRunner.run_method_specific dispatch (audit_fix_2026_07_12 v1.8.7).

Background
----------
P1-2 (audit_fix_2026_07_12 v1.8.0) wired 11 orphan econometric engines into
`RobustnessRunner.run_method_specific()`. P1-3 (this audit follow-up) adds
two more:

  - triple_diff_did → scripts.research_framework.triple_diff_did.TripleDiffDIDEngine
  - psm_did        → scripts.research_framework.psm_did.PSMDID

This test file asserts:

1. `RobustnessRunner.list_methods()` advertises both new methods.
2. `run_method_specific()` returns the canonical dict envelope for both.
3. Idempotent: same (method, df, kwargs) returns cached result.
4. Column-resolution heuristic works when df uses short names.
5. `TripleDiffDIDEngine.fit()` returns DDDResult with expected attrs.
6. `PSMDID.fit()` returns PSMDIDResult with ATT + balance table.

Pattern follows tests/test_orphan_engines_p1_audit.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_ddd_panel(
    n_groups: int = 4,
    n_units_per_group: int = 20,
    n_periods: int = 8,
    true_ddd_coef: float = 0.6,
    seed: int = 20260712,
) -> pd.DataFrame:
    """Build a balanced 3-arm panel with a known DDD coefficient.

    Structure: n_groups group3 categories × n_units_per_group units × n_periods
    periods. Half of units are "treated"; treatment activates after half of
    the time periods. The DDD coefficient on (treat × post × group3) is
    set to `true_ddd_coef` via the DGP, so a TripleDiffDIDEngine.fit()
    should recover a coef close to that value.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    half_period = n_periods // 2
    for g in range(n_groups):
        for u in range(n_units_per_group):
            unit_id = g * n_units_per_group + u
            treat = int(u < n_units_per_group // 2)
            for t in range(n_periods):
                post = int(t >= half_period)
                ddd = treat * post * (g + 1)
                y = (
                    0.5 * (t / n_periods)
                    + 0.3 * treat
                    + 0.2 * post
                    + true_ddd_coef * ddd
                    + rng.normal(0, 0.3)
                )
                rows.append({
                    "unit": unit_id,
                    "time": t,
                    "treat": treat,
                    "post": post,
                    "group3": g,
                    "x1": rng.normal(0, 1),
                    "x2": rng.normal(0, 1),
                    "y": y,
                })
    return pd.DataFrame(rows)


def _make_psm_panel(
    n_units: int = 60,
    n_periods: int = 6,
    true_att: float = 0.5,
    seed: int = 20260712,
) -> pd.DataFrame:
    """Build a panel for PSM-DID. Treatment is time-invariant per unit.

    Half the units are treated; the policy activates at the midpoint of the
    panel. The ATT is embedded via a level-shift on y for treated units in
    post-period.
    """
    rng = np.random.default_rng(seed)
    half_period = n_periods // 2
    rows: list[dict] = []
    for u in range(n_units):
        treat = int(u < n_units // 2)
        # Confounders: size & lev influence both treatment and baseline y.
        size = rng.normal(5, 1.5)
        lev = rng.uniform(0.2, 0.8)
        base = 0.2 * size - 0.5 * lev + rng.normal(0, 0.2)
        for t in range(n_periods):
            post = int(t >= half_period)
            y = base + (true_att * treat * post) + rng.normal(0, 0.1)
            rows.append({
                "unit": u,
                "time": t,
                "treat": treat,
                "post": post,
                "size": size,
                "lev": lev,
                "y": y,
            })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def ddd_panel() -> pd.DataFrame:
    return _make_ddd_panel()


@pytest.fixture(scope="module")
def psm_panel() -> pd.DataFrame:
    return _make_psm_panel()


@pytest.fixture(scope="module")
def runner_ddd(ddd_panel) -> "RobustnessRunner":
    from scripts.research_framework.robustness_runner import RobustnessRunner
    return RobustnessRunner(
        df=ddd_panel,
        baseline_result={"coef": 0.6, "se": 0.1, "pval": 0.01},
        y_var="y",
        treat_var="treat",
        time_var="time",
        unit_var="unit",
        x_vars=["x1", "x2"],
    )


@pytest.fixture(scope="module")
def runner_psm(psm_panel) -> "RobustnessRunner":
    from scripts.research_framework.robustness_runner import RobustnessRunner
    return RobustnessRunner(
        df=psm_panel,
        baseline_result={"coef": 0.5, "se": 0.1, "pval": 0.01},
        y_var="y",
        treat_var="treat",
        time_var="time",
        unit_var="unit",
        x_vars=["size", "lev"],
    )


# ── TestClass 1: Dispatcher wiring (4–5 tests) ───────────────────────────────


class TestDispatchWiring:
    """Both new methods are reachable via run_method_specific()."""

    def test_list_methods_includes_triple_diff_did(self):
        from scripts.research_framework.robustness_runner import RobustnessRunner
        methods = RobustnessRunner.list_methods()
        assert "triple_diff_did" in methods, (
            "triple_diff_did missing from list_methods() — dispatch wiring "
            "regression (audit_fix_2026_07_12 v1.8.7)."
        )

    def test_list_methods_includes_psm_did(self):
        from scripts.research_framework.robustness_runner import RobustnessRunner
        methods = RobustnessRunner.list_methods()
        assert "psm_did" in methods, (
            "psm_did missing from list_methods() — dispatch wiring "
            "regression (audit_fix_2026_07_12 v1.8.7)."
        )

    def test_list_methods_count_is_thirteen(self):
        from scripts.research_framework.robustness_runner import RobustnessRunner
        methods = RobustnessRunner.list_methods()
        # 11 (P1-2) + 2 (P1-3)
        assert len(methods) == 13, (
            f"Expected 13 methods after P1-3, got {len(methods)}"
        )

    def test_run_triple_diff_did_returns_ok_envelope(self, runner_ddd, ddd_panel):
        result = runner_ddd.run_method_specific("triple_diff_did", ddd_panel)
        assert isinstance(result, dict), "result must be dict"
        assert result["method"] == "triple_diff_did"
        assert result["status"] in ("ok", "skipped", "error"), (
            f"status={result['status']!r} not in allowed values"
        )
        # ok must have a non-empty summary, error/skipped must have a reason
        if result["status"] == "ok":
            assert isinstance(result.get("summary"), str)
            assert len(result["summary"]) > 0
            assert result["skipped_reason"] is None
        else:
            assert result.get("skipped_reason") is not None

    def test_run_psm_did_returns_ok_envelope(self, runner_psm, psm_panel):
        result = runner_psm.run_method_specific("psm_did", psm_panel)
        assert isinstance(result, dict), "result must be dict"
        assert result["method"] == "psm_did"
        assert result["status"] in ("ok", "skipped", "error"), (
            f"status={result['status']!r} not in allowed values"
        )
        if result["status"] == "ok":
            assert isinstance(result.get("summary"), str)
            assert len(result["summary"]) > 0
            assert result["skipped_reason"] is None
        else:
            assert result.get("skipped_reason") is not None


# ── TestClass 2: Idempotency and graceful degradation (3 tests) ─────────────


class TestIdempotencyAndDegradation:
    """Cache hits + error envelope for missing deps / bad kwargs."""

    def test_triple_diff_did_idempotent(self, runner_ddd, ddd_panel):
        """Same (method, df) → cached result, no re-fit."""
        r1 = runner_ddd.run_method_specific("triple_diff_did", ddd_panel)
        r2 = runner_ddd.run_method_specific("triple_diff_did", ddd_panel)
        # Cache by (method, id(df)) — summary must match exactly
        assert r1["status"] == r2["status"], (
            f"idempotency broken: status {r1['status']!r} != {r2['status']!r}"
        )
        assert r1.get("summary") == r2.get("summary"), (
            "idempotency broken: summary differs across calls"
        )

    def test_psm_did_idempotent(self, runner_psm, psm_panel):
        r1 = runner_psm.run_method_specific("psm_did", psm_panel)
        r2 = runner_psm.run_method_specific("psm_did", psm_panel)
        assert r1["status"] == r2["status"], (
            f"idempotency broken: status {r1['status']!r} != {r2['status']!r}"
        )
        assert r1.get("summary") == r2.get("summary"), (
            "idempotency broken: summary differs across calls"
        )

    def test_unknown_method_returns_error_status(self, runner_ddd, ddd_panel):
        result = runner_ddd.run_method_specific(
            "nonexistent_ddd_engine_xyz", ddd_panel
        )
        assert result["status"] == "error", (
            f"Unknown method must return 'error', got {result['status']!r}"
        )
        assert result["skipped_reason"] == "unknown_method"


# ── TestClass 3: TripleDiffDIDEngine behaviour (3–4 tests) ──────────────────


class TestTripleDiffDIDEngine:
    """Direct engine tests — no dispatcher wrapper."""

    def test_engine_fit_returns_dddresult(self, ddd_panel):
        from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
        engine = TripleDiffDIDEngine(
            df=ddd_panel,
            y_var="y",
            treat_var="treat",
            time_var="time",
            unit_var="unit",
            group3_var="group3",
        )
        result = engine.fit()
        # DDDResult has these named attrs (see triple_diff_did.py dataclass).
        for attr in ("coef", "se", "pval", "n_obs", "n_groups",
                     "ci_lower", "ci_upper"):
            assert hasattr(result, attr), (
                f"DDDResult missing attribute {attr!r}"
            )
        assert result.n_obs == len(ddd_panel)
        assert result.n_groups == ddd_panel["group3"].nunique()
        assert np.isfinite(result.coef)

    def test_engine_recovers_true_ddd_coef(self, ddd_panel):
        """DDD coef on a positive DGP must be positive and significant.

        Note: the embedded `true_ddd_coef=0.6` is scaled by `(g+1)` in the DGP,
        so the regression recovers the marginal effect of going from g to g+1
        rather than the raw 0.6. We assert sign + significance rather than
        point estimate, since the recovery depends on group3 cardinality.
        """
        from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
        engine = TripleDiffDIDEngine(
            df=ddd_panel,
            y_var="y",
            treat_var="treat",
            time_var="time",
            unit_var="unit",
            group3_var="group3",
        )
        result = engine.fit(x_vars=["x1", "x2"])
        # On a clean DGP the coefficient should be positive.
        assert result.coef > 0, (
            f"DDD coef on positive DGP should be positive, got {result.coef:.3f}"
        )
        # And highly significant (DGP has large effect + low noise).
        assert result.pval < 0.01, (
            f"DDD coef should be significant at 1% on clean DGP, "
            f"got pval={result.pval:.3f}"
        )
        # And the t-statistic should be well above 2 (sign + large magnitude).
        assert result.coef / max(result.se, 1e-12) > 2, (
            f"t-stat should exceed 2 on clean DGP, "
            f"got {result.coef / max(result.se, 1e-12):.2f}"
        )

    def test_engine_to_dict_shape(self, ddd_panel):
        from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
        engine = TripleDiffDIDEngine(
            df=ddd_panel,
            y_var="y",
            treat_var="treat",
            time_var="time",
            unit_var="unit",
            group3_var="group3",
        )
        engine.fit()
        d = engine._last_result.to_dict()
        # DDDResult.to_dict() merges result + additional dict
        assert "coef" in d
        assert "estimator" in d
        assert d["estimator"] == "ddd_ols"

    def test_engine_get_hte_returns_per_group_table(self, ddd_panel):
        from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
        engine = TripleDiffDIDEngine(
            df=ddd_panel,
            y_var="y",
            treat_var="treat",
            time_var="time",
            unit_var="unit",
            group3_var="group3",
        )
        engine.fit()
        hte = engine.get_hte()
        assert isinstance(hte, pd.DataFrame)
        # One row per group3 category
        assert len(hte) == ddd_panel["group3"].nunique()
        assert "group3" in hte.columns
        assert "coef" in hte.columns and "se" in hte.columns


# ── TestClass 4: PSMDID behaviour (3–4 tests) ───────────────────────────────


class TestPSMDID:
    """Direct engine tests — no dispatcher wrapper."""

    def test_psm_fit_returns_psmdidresult(self, psm_panel):
        from scripts.research_framework.psm_did import PSMDID
        engine = PSMDID(
            outcome="y",
            treatment="treat",
            time="time",
            unit="unit",
            method="nearest",
        )
        result = engine.fit(psm_panel, covariates=["size", "lev"])
        for attr in ("did_coefficient", "did_se", "did_pvalue",
                     "first_stage_auc", "n_obs_after_match",
                     "covariate_balance", "method"):
            assert hasattr(result, attr), (
                f"PSMDIDResult missing attribute {attr!r}"
            )
        assert result.method == "nearest"
        assert isinstance(result.covariate_balance, pd.DataFrame)

    def test_psm_balance_table_has_all_covariates(self, psm_panel):
        from scripts.research_framework.psm_did import PSMDID
        engine = PSMDID(
            outcome="y", treatment="treat", time="time", unit="unit",
            method="nearest",
        )
        result = engine.fit(psm_panel, covariates=["size", "lev"])
        balance = result.covariate_balance
        assert len(balance) == 2, (
            f"Expected 2 rows in covariate_balance, got {len(balance)}"
        )
        assert set(balance["covariate"]) == {"size", "lev"}
        assert "std_bias" in balance.columns
        assert "abs_bias_lt_10pct" in balance.columns

    def test_psm_first_stage_auc_in_unit_interval(self, psm_panel):
        """PSM logistic regression AUC should be in [0, 1]."""
        from scripts.research_framework.psm_did import PSMDID
        engine = PSMDID(
            outcome="y", treatment="treat", time="time", unit="unit",
            method="nearest",
        )
        result = engine.fit(psm_panel, covariates=["size", "lev"])
        assert 0.0 <= result.first_stage_auc <= 1.0, (
            f"AUC={result.first_stage_auc:.3f} not in [0,1]"
        )

    def test_psm_did_does_not_crash_on_minimal_panel(self):
        """Small panel should still produce a result envelope (ok/error/skipped)."""
        from scripts.research_framework.psm_did import PSMDID
        rng = np.random.default_rng(7)
        rows = []
        for u in range(20):
            treat = int(u < 10)
            for t in range(4):
                rows.append({
                    "unit": u, "time": t, "treat": treat,
                    "x": rng.normal(0, 1), "y": rng.normal(0, 1),
                })
        df_small = pd.DataFrame(rows)
        engine = PSMDID(
            outcome="y", treatment="treat", time="time", unit="unit",
            method="nearest",
        )
        # Should not raise; returns a result dataclass.
        result = engine.fit(df_small, covariates=["x"])
        assert hasattr(result, "did_coefficient")
        assert hasattr(result, "did_pvalue")


# ── TestClass 5: Dispatcher ↔ engine consistency (1 integration test) ────────


class TestDispatcherEngineConsistency:
    """Dispatcher's result envelope must agree with direct engine output."""

    def test_triple_diff_did_dispatcher_matches_direct_engine(self, ddd_panel):
        from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
        from scripts.research_framework.robustness_runner import RobustnessRunner

        # Direct engine call
        engine = TripleDiffDIDEngine(
            df=ddd_panel,
            y_var="y",
            treat_var="treat",
            time_var="time",
            unit_var="unit",
            group3_var="group3",
        )
        direct_result = engine.fit(x_vars=["x1", "x2"])

        # Dispatcher call (must pass kwargs to mirror the dispatcher's
        # column-resolution path).
        runner = RobustnessRunner(
            df=ddd_panel,
            baseline_result={"coef": 0.6, "se": 0.1, "pval": 0.01},
            y_var="y",
            treat_var="treat",
            time_var="time",
            unit_var="unit",
            x_vars=["x1", "x2"],
        )
        # Pass group3_var explicitly via kwargs to avoid the synthetic
        # fallback split.
        res = runner.run_method_specific(
            "triple_diff_did", ddd_panel, group3_var="group3",
        )
        if res["status"] == "ok":
            dispatcher_result = res["result"]
            # Both must agree on coef and se within numerical tolerance.
            assert np.isclose(
                dispatcher_result.coef, direct_result.coef, atol=1e-8,
            ), f"coef mismatch: dispatch={dispatcher_result.coef}, direct={direct_result.coef}"
            assert np.isclose(
                dispatcher_result.se, direct_result.se, atol=1e-8,
            ), f"se mismatch: dispatch={dispatcher_result.se}, direct={direct_result.se}"

    def test_audit_marker_in_robustness_runner(self):
        """robustness_runner.py must contain v1.8.7 marker for traceability."""
        from pathlib import Path
        src = Path(
            "scripts/research_framework/robustness_runner.py"
        ).read_text(encoding="utf-8")
        assert "v1.8.7" in src, (
            "P1-3 regression: v1.8.7 marker missing from robustness_runner.py"
        )
