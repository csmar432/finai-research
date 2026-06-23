"""Tests for Kleibergen-Paap rk F and Anderson-Rubin F statistics.

These statistics are implemented in iv_panel.py. All tests use synthetic data
generated with a fixed random seed for reproducibility.
"""

import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.iv_panel import IVPanel


# ── Shared data fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def iv_data_strong():
    """Simple IV setup with strong instruments (F ≈ 25–40)."""
    np.random.seed(42)
    n = 200
    z1 = np.random.randn(n)          # instrument 1
    z2 = np.random.randn(n)          # instrument 2
    u  = np.random.randn(n)           # structural error
    v  = 0.5 * z1 + 0.3 * z2 + np.random.randn(n) * 0.2  # endogeneity
    x  = 1.0 + 0.8 * z1 + 0.5 * z2 + v                   # endogenous
    y  = 2.0 + 1.5 * x + u                                 # structural

    df = pd.DataFrame({
        "ticker": [f"i{i}" for i in range(n)],
        "year":   [2020] * n,
        "y":      y,
        "x":      x,
        "z1":     z1,
        "z2":     z2,
    })
    return df


@pytest.fixture
def iv_data_weak():
    """IV setup with weak instruments (F < 5)."""
    np.random.seed(7)
    n = 100
    z1 = np.random.randn(n)          # instrument barely correlated with x
    z2 = np.random.randn(n)
    u  = np.random.randn(n)
    # Instruments explain almost none of the variance in x
    v  = np.random.randn(n) * 3.0
    x  = 1.0 + 0.05 * z1 + 0.05 * z2 + v
    y  = 2.0 + 1.5 * x + u

    df = pd.DataFrame({
        "ticker": [f"i{i}" for i in range(n)],
        "year":   [2020] * n,
        "y":      y,
        "x":      x,
        "z1":     z1,
        "z2":     z2,
    })
    return df


@pytest.fixture
def iv_data_heteroskedastic():
    """IV data with known heteroskedasticity.

    Error variance increases with |z1|, so Stock-Yogo F is invalid and KP-F
    should be used instead.
    """
    np.random.seed(123)
    n = 300
    z1 = np.random.randn(n)
    z2 = np.random.randn(n)
    # Heteroskedastic structural error: variance scales with |z1|
    sigma = 0.5 + 1.5 * np.abs(z1)
    u = sigma * np.random.randn(n)
    v = 0.4 * z1 + 0.2 * z2 + np.random.randn(n) * 0.3
    x = 1.0 + 0.7 * z1 + 0.4 * z2 + v
    y = 2.0 + 1.5 * x + u

    df = pd.DataFrame({
        "ticker": [f"i{i}" for i in range(n)],
        "year":   [2020] * n,
        "y":      y,
        "x":      x,
        "z1":     z1,
        "z2":     z2,
    })
    return df


@pytest.fixture
def iv_data_multiple_endogenous():
    """IV with two endogenous regressors and three instruments."""
    np.random.seed(999)
    n = 250
    z1 = np.random.randn(n)
    z2 = np.random.randn(n)
    z3 = np.random.randn(n)
    u  = np.random.randn(n)
    # Two endogenous variables
    v1 = 0.4 * z1 + 0.3 * z2 + np.random.randn(n) * 0.4
    v2 = 0.3 * z2 + 0.2 * z3 + np.random.randn(n) * 0.4
    x1 = 1.0 + 0.7 * z1 + 0.5 * z2 + v1
    x2 = 0.5 + 0.4 * z2 + 0.3 * z3 + v2
    # Both x1 and x2 affect y
    y  = 2.0 + 1.5 * x1 + 0.8 * x2 + u

    df = pd.DataFrame({
        "ticker": [f"i{i}" for i in range(n)],
        "year":   [2020] * n,
        "y":      y,
        "x1":     x1,
        "x2":     x2,
        "z1":     z1,
        "z2":     z2,
        "z3":     z3,
    })
    return df


# ── KP-F unit tests ────────────────────────────────────────────────────────────


class TestKleibergenPaapF:
    """Unit tests for the raw KP-F computation (no linearmodels dependency)."""

    def test_kp_f_is_nan_when_fewer_instruments_than_endogenous(self):
        """KP-F should return NaN when k < l (under-identified)."""
        np.random.seed(0)
        n = 50
        y = np.random.randn(n)
        X = np.random.randn(n, 2)      # 2 endogenous
        Z = np.random.randn(n, 1)      # only 1 instrument → under-identified

        panel = IVPanel(
            df=pd.DataFrame({
                "ticker": [f"i{i}" for i in range(n)],
                "year": [2020] * n,
                "y": y, "x1": X[:, 0], "x2": X[:, 1],
                "z1": Z[:, 0],
            }),
            y_var="y",
            x_vars=["x1", "x2"],
            iv_vars=["z1"],
            unit_var="ticker",
            time_var="year",
        )
        # Manually call the internal method with the under-identified setup
        kp_f, kp_pval = panel._kleibergen_paap_rk_f(y, X, Z, None)
        assert np.isnan(kp_f), "KP-F should be NaN for under-identified IV"

    def test_kp_f_positive_for_valid_iv(self, iv_data_strong):
        """KP-F should be positive when instruments are valid."""
        df = iv_data_strong
        panel = IVPanel(
            df=df, y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        kp_f, kp_pval = panel._kleibergen_paap_rk_f(
            df["y"].values, df[["x"]].values,
            df[["z1", "z2"]].values, None,
        )
        assert kp_f > 0, f"KP-F should be positive, got {kp_f}"
        assert 0 <= kp_pval <= 1, f"KP-F p-value out of range: {kp_pval}"

    def test_kp_f_smaller_for_weak_instruments(self, iv_data_strong, iv_data_weak):
        """KP-F should be smaller for weak instruments than strong instruments."""
        panel_s = IVPanel(
            df=iv_data_strong, y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"], unit_var="ticker", time_var="year",
        )
        panel_w = IVPanel(
            df=iv_data_weak, y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"], unit_var="ticker", time_var="year",
        )

        y_s, X_s = iv_data_strong["y"].values, iv_data_strong[["x"]].values
        Z_s = iv_data_strong[["z1", "z2"]].values
        kp_f_strong, _ = panel_s._kleibergen_paap_rk_f(y_s, X_s, Z_s, None)

        y_w, X_w = iv_data_weak["y"].values, iv_data_weak[["x"]].values
        Z_w = iv_data_weak[["z1", "z2"]].values
        kp_f_weak, _ = panel_w._kleibergen_paap_rk_f(y_w, X_w, Z_w, None)

        assert kp_f_strong > kp_f_weak, (
            f"Strong-instrument KP-F ({kp_f_strong:.2f}) should exceed "
            f"weak-instrument KP-F ({kp_f_weak:.2f})"
        )

    def test_kp_f_with_exogenous_controls(self):
        """KP-F should handle exogenous control variables correctly."""
        np.random.seed(55)
        n = 200
        z1 = np.random.randn(n)
        u  = np.random.randn(n)
        v  = 0.5 * z1 + np.random.randn(n) * 0.3
        x  = 1.0 + 0.7 * z1 + v
        # Exogenous control: normally distributed, independent of errors
        w  = np.random.randn(n) * 2.0
        y  = 2.0 + 1.5 * x + 0.3 * w + u

        df = pd.DataFrame({
            "ticker": [f"i{i}" for i in range(n)],
            "year":   [2020] * n,
            "y": y, "x": x, "z1": z1, "w": w,
        })
        panel = IVPanel(
            df=df, y_var="y", x_vars=["x"],
            iv_vars=["z1"], w_vars=["w"],
            unit_var="ticker", time_var="year",
        )
        kp_f, kp_pval = panel._kleibergen_paap_rk_f(
            df["y"].values, df[["x"]].values,
            df[["z1"]].values, df[["w"]].values,
        )
        assert kp_f > 0
        assert 0 <= kp_pval <= 1


class TestAndersonRubinF:
    """Unit tests for the Anderson-Rubin F-statistic."""

    def test_ar_f_positive(self, iv_data_strong):
        """AR-F should be positive for valid IV with non-zero first stage."""
        df = iv_data_strong
        panel = IVPanel(
            df=df, y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"], unit_var="ticker", time_var="year",
        )
        y = df["y"].values
        X = df[["x"]].values
        Z = df[["z1", "z2"]].values
        beta_iv = np.array([1.5])   # close to true parameter

        ar_f = panel._anderson_rubin_f(y, X, Z, beta_iv, None)
        assert ar_f > 0, f"AR-F should be positive, got {ar_f}"

    def test_ar_f_rejects_false_h0(self, iv_data_strong):
        """AR-F should reject when H0 is far from the true parameter."""
        df = iv_data_strong
        panel = IVPanel(
            df=df, y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"], unit_var="ticker", time_var="year",
        )
        y = df["y"].values
        X = df[["x"]].values
        Z = df[["z1", "z2"]].values
        # True β ≈ 1.5; H0: β = 0 is clearly false
        ar_f = panel._anderson_rubin_f(y, X, Z, np.array([0.0]), None)

        dof1, dof2 = 1, max(len(y) - Z.shape[1], 1)
        pval = 1 - pytest.importorskip("scipy").stats.f.cdf(ar_f, dof1, dof2)
        assert pval < 0.05, (
            f"AR-F={ar_f:.2f} should reject H0: β=0 (p={pval:.4f})"
        )

    def test_ar_f_under_identified_returns_nan(self):
        """AR-F should return NaN when k < l (under-identified)."""
        np.random.seed(0)
        n = 50
        y  = np.random.randn(n)
        X  = np.random.randn(n, 2)   # 2 endogenous
        Z  = np.random.randn(n, 1)   # 1 instrument → under-identified
        panel = IVPanel(
            df=pd.DataFrame({
                "ticker": [f"i{i}" for i in range(n)],
                "year": [2020] * n,
                "y": y, "x1": X[:, 0], "x2": X[:, 1], "z1": Z[:, 0],
            }),
            y_var="y", x_vars=["x1", "x2"],
            iv_vars=["z1"], unit_var="ticker", time_var="year",
        )
        ar_f = panel._anderson_rubin_f(y, X, Z, np.array([0.0, 0.0]), None)
        assert np.isnan(ar_f)


# ── Integration tests (IVPanel.fit) ───────────────────────────────────────────


class TestIVPanelDiagnosticsIntegration:
    """Full integration tests: fit() should populate both Stock-Yogo and KP-F.

    These tests require linearmodels with a working libomp (OpenMP) installation.
    If libomp is missing the tests skip automatically rather than producing
    confusing assertion failures from an empty diagnostic list.
    """

    @classmethod
    def _skip_if_linearmodels_unavailable(cls):
        """Skip if linearmodels IV submodule is not available."""
        try:
            from linearmodels.iv.model import IV2SLS  # noqa: F401
        except Exception as exc:
            pytest.skip(f"linearmodels.iv not available: {exc}")

    def test_fit_returns_kp_diagnostic(self, iv_data_strong):
        """IVPanel.fit() should include Kleibergen-Paap in get_diagnostics()."""
        self._skip_if_linearmodels_unavailable()
        panel = IVPanel(
            df=iv_data_strong,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        names  = [d.test_name for d in diags]
        has_kp = any("Kleibergen" in n or "KP" in n for n in names)
        assert has_kp, f"Expected KP diagnostic in {names}"

    def test_fit_diagnostic_names_distinct(self, iv_data_strong):
        """Stock-Yogo and KP-F diagnostics should have clearly different names."""
        panel = IVPanel(
            df=iv_data_strong,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        names  = [d.test_name for d in diags]
        has_sy = any("Stock-Yogo" in n or "F-stat" in n for n in names)
        assert has_sy, f"Expected Stock-Yogo diagnostic in {names}"
        has_kp = any("Kleibergen" in n or "KP" in n for n in names)
        assert has_kp, f"Expected Kleibergen-Paap diagnostic in {names}"

    def test_weak_instruments_correctly_classified(self, iv_data_weak):
        """Weak instruments should produce a KP-F < 10 (FAIL/WARN)."""
        panel = IVPanel(
            df=iv_data_weak,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        kp_diags = [d for d in diags if "Kleibergen" in d.test_name]
        assert len(kp_diags) > 0, "KP diagnostic not generated"
        kp = kp_diags[0]
        assert kp.statistic < 10, (
            f"Weak instrument KP-F should be < 10, got {kp.statistic:.2f}"
        )
        assert kp.conclusion in ("fail_to_reject_H0", "inconclusive"), (
            f"Weak instruments should not reject H0, got {kp.conclusion}"
        )

    def test_strong_instruments_correctly_classified(self, iv_data_strong):
        """Strong instruments should produce a positive KP-F."""
        panel = IVPanel(
            df=iv_data_strong,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        kp_diags = [d for d in diags if "Kleibergen" in d.test_name]
        assert len(kp_diags) > 0, "KP diagnostic not generated"
        kp = kp_diags[0]
        assert kp.statistic > 0, f"KP-F should be positive, got {kp.statistic}"

    def test_heteroskedastic_data_computes_kp_f(self, iv_data_heteroskedastic):
        """KP-F should be computable even with known heteroskedasticity."""
        panel = IVPanel(
            df=iv_data_heteroskedastic,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        kp_diags = [d for d in diags if "Kleibergen" in d.test_name]
        assert len(kp_diags) > 0, "KP-F diagnostic missing for heteroskedastic data"
        kp = kp_diags[0]
        assert not np.isnan(kp.statistic), "KP-F should not be NaN"
        assert kp.statistic > 0, f"KP-F should be positive, got {kp.statistic}"

    def test_multiple_endogenous_computes_kp_f(self, iv_data_multiple_endogenous):
        """KP-F should handle multiple endogenous variables."""
        panel = IVPanel(
            df=iv_data_multiple_endogenous,
            y_var="y", x_vars=["x1", "x2"],
            iv_vars=["z1", "z2", "z3"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        kp_diags = [d for d in diags if "Kleibergen" in d.test_name]
        assert len(kp_diags) > 0, "KP-F diagnostic missing for multi-endogenous"
        kp = kp_diags[0]
        assert kp.statistic > 0, f"KP-F should be positive, got {kp.statistic}"

    def test_anderson_rubin_diagnostic_present(self, iv_data_strong):
        """IVPanel should include an Anderson-Rubin diagnostic."""
        panel = IVPanel(
            df=iv_data_strong,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        names  = [d.test_name for d in diags]
        has_ar = any("Anderson-Rubin" in n or "AR" in n for n in names)
        assert has_ar, f"Expected Anderson-Rubin diagnostic in {names}"

    def test_kp_f_and_ar_f_details_are_informative(self, iv_data_strong):
        """KP-F and AR-F diagnostics should include informative details dict."""
        panel = IVPanel(
            df=iv_data_strong,
            y_var="y", x_vars=["x"],
            iv_vars=["z1", "z2"],
            unit_var="ticker", time_var="year",
        )
        panel.fit()

        diags = panel.get_diagnostics()
        found = False
        for d in diags:
            if "Kleibergen" in d.test_name or "Anderson-Rubin" in d.test_name:
                found = True
                assert "rule" in d.details, f"Missing 'rule' in {d.test_name} details"
                assert "note" in d.details, f"Missing 'note' in {d.test_name} details"
                assert "reference" in d.details, (
                    f"Missing 'reference' in {d.test_name} details"
                )
        assert found, "No KP or AR diagnostics were generated"


# ── Compilation check ──────────────────────────────────────────────────────────


def test_module_compiles():
    """iv_panel.py should pass Python compilation without errors."""
    import py_compile
    import tempfile
    import os

    src = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "research_framework", "iv_panel.py"
    )
    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=False) as f:
        tmp = f.name
    try:
        py_compile.compile(src, cfile=tmp, doraise=True)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def test_diagnostic_reporter_compiles():
    """diagnostic_reporter.py should pass Python compilation without errors."""
    import py_compile
    import tempfile
    import os

    src = os.path.join(
        os.path.dirname(__file__), "..",
        "scripts", "research_framework", "diagnostic_reporter.py",
    )
    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=False) as f:
        tmp = f.name
    try:
        py_compile.compile(src, cfile=tmp, doraise=True)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
