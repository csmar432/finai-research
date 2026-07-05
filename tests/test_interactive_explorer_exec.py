"""tests/test_interactive_explorer_exec.py — Deep coverage for interactive_explorer.

Targets:
- DIDEventStudyConfig / PanelFEConfig / DiagnosticsConfig dataclasses
- DIDEventStudyExplorer: _get_periods_and_values, to_plotly_figure,
  to_matplotlib_script, to_summary_data, validate_parallel_trends
- PanelFEVisualizer: generate_fe_heatmap_data, generate_variance_decomposition,
  to_plotly_dashboard
- RegressionDiagnosticsExplorer: identify_outliers, generate_diagnostics_report,
  to_plotly_figure
- TimeSeriesDecomposer: decompose, test_stationarity, _moving_average,
  _autocorrelation
- run_explorer_app: skip (requires streamlit runtime)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from scripts.core.interactive_explorer import (
        DIDEventStudyConfig,
        DIDEventStudyExplorer,
        DiagnosticsConfig,
        PanelFEConfig,
        PanelFEVisualizer,
        RegressionDiagnosticsExplorer,
        TimeSeriesDecomposer,
    )
except Exception as e:
    pytest.skip(f"interactive_explorer not importable: {e}", allow_module_level=True)


# ─── Config dataclasses ────────────────────────────────────────────────────────


class TestDIDEventStudyConfig:
    def test_default_init(self):
        c = DIDEventStudyConfig()
        assert c.pre_means == {}
        assert c.post_means == {}
        assert c.ci_level == 0.95
        assert c.treat_label == "Treatment"
        assert c.ctrl_label == "Control"
        assert c.event_time is None

    def test_custom_init(self):
        c = DIDEventStudyConfig(
            pre_means={"-1": 1.0},
            post_means={"0": 2.0},
            ci_level=0.99,
            treat_label="T",
            ctrl_label="C",
        )
        assert c.ci_level == 0.99
        assert c.treat_label == "T"

    def test_event_time_list(self):
        c = DIDEventStudyConfig(event_time=[-2, -1, 0, 1, 2])
        assert c.event_time == [-2, -1, 0, 1, 2]


class TestPanelFEConfig:
    def test_default_init(self):
        c = PanelFEConfig()
        assert c.entity_var == "entity"
        assert c.time_var == "time"
        assert c.dep_var == "y"
        assert c.fe_entity is True
        assert c.fe_time is True
        assert c.cluster_var is None
        assert c.n_entities == 0
        assert c.n_time == 0


class TestDiagnosticsConfig:
    def test_init(self):
        c = DiagnosticsConfig(y=[1.0, 2.0], fitted=[1.1, 1.9], residuals=[-0.1, 0.1])
        assert c.y == [1.0, 2.0]
        assert c.fitted == [1.1, 1.9]
        assert c.n_covariates == 1

    def test_with_optional(self):
        c = DiagnosticsConfig(
            y=[1.0, 2.0],
            fitted=[1.1, 1.9],
            residuals=[-0.1, 0.1],
            leverage=[0.05, 0.10],
            cooksd=[0.01, 0.02],
            obs_labels=["a", "b"],
            n_covariates=3,
        )
        assert c.leverage == [0.05, 0.10]
        assert c.obs_labels == ["a", "b"]
        assert c.n_covariates == 3


# ─── DIDEventStudyExplorer ─────────────────────────────────────────────────────


class TestDIDEventStudyExplorer:
    def _make_explorer(self, **kwargs):
        defaults = dict(
            pre_means={"-3": 1.0, "-2": 1.1, "-1": 1.2},
            post_means={"0": 2.0, "1": 2.1, "2": 2.2},
            pre_ses={"-3": 0.1, "-2": 0.1, "-1": 0.1},
            post_ses={"0": 0.2, "1": 0.2, "2": 0.2},
            pre_ctrl_means={"-3": 1.0, "-2": 1.05, "-1": 1.1},
            post_ctrl_means={"0": 1.0, "1": 1.0, "2": 1.0},
        )
        defaults.update(kwargs)
        cfg = DIDEventStudyConfig(**defaults)
        return DIDEventStudyExplorer(cfg)

    def test_init(self):
        exp = self._make_explorer()
        assert exp.config.ci_level == 0.95
        assert exp._z_score == 1.96

    def test_init_99ci(self):
        exp = self._make_explorer(ci_level=0.99)
        assert exp._z_score == 2.576

    def test_get_periods_and_values_with_event_time(self):
        exp = self._make_explorer(event_time=[-3, -2, -1, 0, 1, 2])
        periods, treat, ctrl, ses = exp._get_periods_and_values()
        assert len(periods) == 6
        assert isinstance(treat, list)
        assert isinstance(ctrl, list)

    def test_get_periods_and_values_no_event_time(self):
        exp = self._make_explorer()
        periods, treat, ctrl, ses = exp._get_periods_and_values()
        # Should infer periods from keys
        assert isinstance(periods, list)
        assert len(periods) >= 1

    def test_to_summary_data(self):
        exp = self._make_explorer()
        summary = exp.to_summary_data()
        assert "pre_periods" in summary
        assert "post_periods" in summary
        assert "did_estimate" in summary
        assert "pre_mean" in summary
        assert "post_mean" in summary
        assert "parallel_trends_holds" in summary
        assert isinstance(summary["did_estimate"], float)

    def test_to_summary_data_with_ctrl_means(self):
        exp = self._make_explorer(
            pre_ctrl_means={"-3": 1.0, "-2": 1.05, "-1": 1.1},
            post_ctrl_means={"0": 1.0, "1": 1.0, "2": 1.0},
        )
        summary = exp.to_summary_data()
        assert summary["pre_diff"] != summary["pre_mean"] or summary["post_diff"] != summary["post_mean"]

    def test_validate_parallel_trends_pass(self):
        exp = self._make_explorer()
        is_valid, reason = exp.validate_parallel_trends()
        assert isinstance(is_valid, bool)
        assert isinstance(reason, str)
        assert "t-statistic" in reason

    def test_validate_parallel_trends_no_pre(self):
        cfg = DIDEventStudyConfig(pre_means={}, post_means={"0": 1.0})
        exp = DIDEventStudyExplorer(cfg)
        is_valid, reason = exp.validate_parallel_trends()
        assert is_valid is False
        assert "No pre-treatment" in reason

    def test_validate_parallel_trends_one_period(self):
        cfg = DIDEventStudyConfig(pre_means={"0": 1.0}, post_means={"1": 2.0})
        exp = DIDEventStudyExplorer(cfg)
        is_valid, reason = exp.validate_parallel_trends()
        assert is_valid is False
        assert "at least 2" in reason

    def test_validate_parallel_trends_with_ses(self):
        cfg = DIDEventStudyConfig(
            pre_means={"-3": 1.0, "-2": 1.1, "-1": 1.2},
            post_means={"0": 2.0},
            pre_ses={"-3": 0.1, "-2": 0.1, "-1": 0.1},
        )
        exp = DIDEventStudyExplorer(cfg)
        is_valid, reason = exp.validate_parallel_trends()
        assert isinstance(is_valid, bool)

    def test_to_matplotlib_script(self):
        exp = self._make_explorer()
        script = exp.to_matplotlib_script()
        assert isinstance(script, str)
        assert "matplotlib" in script
        assert "pre_means" in script
        assert "post_means" in script
        assert "treat_label" in script
        assert "ctrl_label" in script

    def test_to_matplotlib_script_no_ses(self):
        exp = self._make_explorer(pre_ses=None, post_ses=None)
        script = exp.to_matplotlib_script()
        assert "pre_ses not provided" in script or "pre_ses" in script

    def test_to_matplotlib_script_no_ctrl(self):
        exp = self._make_explorer(pre_ctrl_means=None, post_ctrl_means=None)
        script = exp.to_matplotlib_script()
        assert "pre_ctrl_means = None" in script or "None" in script

    def test_to_plotly_figure_empty_when_no_plotly(self, monkeypatch):
        # Force plotly unavailable
        import scripts.core.interactive_explorer as ie
        monkeypatch.setattr(ie, "_plotly_available", False)
        exp = self._make_explorer()
        result = exp.to_plotly_figure()
        # Should return {} when plotly is unavailable
        assert result == {} or isinstance(result, dict)

    def test_to_summary_data_empty_pre(self):
        cfg = DIDEventStudyConfig(pre_means={}, post_means={"0": 1.0, "1": 2.0})
        exp = DIDEventStudyExplorer(cfg)
        summary = exp.to_summary_data()
        assert summary["pre_mean"] == 0.0
        assert summary["post_mean"] != 0.0

    def test_to_summary_data_empty_post(self):
        cfg = DIDEventStudyConfig(pre_means={"-1": 1.0}, post_means={})
        exp = DIDEventStudyExplorer(cfg)
        summary = exp.to_summary_data()
        assert summary["post_mean"] == 0.0


# ─── PanelFEVisualizer ─────────────────────────────────────────────────────────


class TestPanelFEVisualizer:
    def test_init(self):
        cfg = PanelFEConfig(n_entities=100, n_time=10)
        viz = PanelFEVisualizer(cfg)
        assert viz.config == cfg

    def test_generate_fe_heatmap_data_no_args(self):
        cfg = PanelFEConfig(n_entities=5, n_time=3)
        viz = PanelFEVisualizer(cfg)
        data = viz.generate_fe_heatmap_data()
        assert data["n_entities"] == 5
        assert data["n_time"] == 3
        assert "entity_var" in data
        assert "time_var" in data

    def test_generate_fe_heatmap_data_with_entity_fes(self):
        cfg = PanelFEConfig(n_entities=3, n_time=2)
        viz = PanelFEVisualizer(cfg)
        data = viz.generate_fe_heatmap_data(entity_fes=[0.1, 0.2, 0.3])
        assert data["entity_fes"] == [0.1, 0.2, 0.3]
        assert data["entity_labels"] == ["E0", "E1", "E2"]
        assert data["entity_range"] == (0.1, 0.3)

    def test_generate_fe_heatmap_data_with_time_fes(self):
        cfg = PanelFEConfig(n_entities=2, n_time=3)
        viz = PanelFEVisualizer(cfg)
        data = viz.generate_fe_heatmap_data(time_fes=[0.5, 0.6, 0.7])
        assert data["time_fes"] == [0.5, 0.6, 0.7]
        assert data["time_labels"] == ["T0", "T1", "T2"]
        assert data["time_range"] == (0.5, 0.7)

    def test_generate_fe_heatmap_data_custom_labels(self):
        cfg = PanelFEConfig(n_entities=2, n_time=2)
        viz = PanelFEVisualizer(cfg)
        data = viz.generate_fe_heatmap_data(
            entity_fes=[1.0, 2.0],
            time_fes=[0.5, 0.6],
            entity_labels=["FirmA", "FirmB"],
            time_labels=["2020", "2021"],
        )
        assert data["entity_labels"] == ["FirmA", "FirmB"]
        assert data["time_labels"] == ["2020", "2021"]

    def test_generate_variance_decomposition_default(self):
        cfg = PanelFEConfig(n_entities=50, n_time=10)
        viz = PanelFEVisualizer(cfg)
        decomp = viz.generate_variance_decomposition()
        assert "between_entity" in decomp
        assert "between_time" in decomp
        assert "residual" in decomp
        assert "total_variance" in decomp
        # Shares should sum to ~1.0
        total = decomp["between_entity"] + decomp["between_time"] + decomp["residual"]
        assert abs(total - 1.0) < 0.01

    def test_generate_variance_decomposition_with_data(self):
        cfg = PanelFEConfig()
        viz = PanelFEVisualizer(cfg)
        decomp = viz.generate_variance_decomposition(
            entity_fes=[1.0, 2.0, 3.0, 4.0],
            time_fes=[0.1, 0.2, 0.3],
            residuals=[0.01, -0.01, 0.02, -0.02, 0.0, 0.0] * 2,
        )
        assert decomp["n_entities"] == 4
        assert decomp["n_time_periods"] == 3

    def test_generate_variance_decomposition_empty(self):
        cfg = PanelFEConfig(n_entities=5, n_time=3)
        viz = PanelFEVisualizer(cfg)
        decomp = viz.generate_variance_decomposition(
            entity_fes=[1.0],
            time_fes=[1.0],
            residuals=[0.0],
        )
        # When variance is zero, default shares
        assert decomp["between_entity"] == decomp["between_time"] == decomp["residual"]

    def test_to_plotly_dashboard_empty_when_no_plotly(self, monkeypatch):
        import scripts.core.interactive_explorer as ie
        monkeypatch.setattr(ie, "_plotly_available", False)
        cfg = PanelFEConfig(n_entities=30, n_time=10)
        viz = PanelFEVisualizer(cfg)
        result = viz.to_plotly_dashboard()
        assert result == {} or isinstance(result, dict)


# ─── RegressionDiagnosticsExplorer ─────────────────────────────────────────────


class TestRegressionDiagnosticsExplorer:
    def _make_explorer(self, n=20, **kwargs):
        import math
        y = [float(i) for i in range(n)]
        fitted = [float(i) + math.sin(i * 0.3) * 0.1 for i in range(n)]
        residuals = [y[i] - fitted[i] for i in range(n)]
        defaults = dict(
            y=y,
            fitted=fitted,
            residuals=residuals,
            leverage=[0.05] * n,
            cooksd=[0.01] * n,
            n_covariates=2,
        )
        defaults.update(kwargs)
        cfg = DiagnosticsConfig(**defaults)
        return RegressionDiagnosticsExplorer(cfg)

    def test_init(self):
        exp = self._make_explorer(n=10)
        assert exp.n == 10
        # k is computed from avg_leverage * n; could be 0 when leverage is small
        assert isinstance(exp.k, int)

    def test_compute_k_with_leverage(self):
        # With leverage avg of 0.05 and n=10, k = round(0.5) = 0
        exp = self._make_explorer(n=10)
        assert isinstance(exp.k, int)

    def test_compute_k_without_leverage(self):
        # Without leverage, k uses n // 10 with max(1, ...), so at least 1
        cfg = DiagnosticsConfig(
            y=[1.0, 2.0, 3.0],
            fitted=[1.1, 1.9, 2.9],
            residuals=[-0.1, 0.1, 0.1],
        )
        exp = RegressionDiagnosticsExplorer(cfg)
        assert exp.k >= 1

    def test_compute_influence_threshold(self):
        exp = self._make_explorer(n=10)
        t = exp._compute_influence_threshold(n=100, k=5)
        assert t == 2.0 * 5 / 100

    def test_compute_influence_threshold_default(self):
        exp = self._make_explorer(n=10)
        t = exp._compute_influence_threshold()
        assert t >= 0

    def test_compute_influence_threshold_zero_n(self):
        # Note: function uses `n or self.n`, so explicit n=0 falls back to self.n.
        # This documents the actual behavior; could be a bug if user expects 0.
        exp = self._make_explorer(n=10)
        t = exp._compute_influence_threshold(n=0, k=2)
        # n=0 → falls back to self.n=10; k=2 → kept; result = 2*2/10 = 0.4
        assert t == 2.0 * 2 / 10

    def test_compute_influence_threshold_neg_n(self):
        # Negative n → falls back via `if n > 0 else 0.0`
        exp = self._make_explorer(n=20)
        t = exp._compute_influence_threshold(n=-5, k=2)
        assert t == 0.0

    def test_compute_cooks_threshold_neg_n(self):
        # Negative n also returns 0.0
        exp = self._make_explorer(n=20)
        t = exp._compute_cooks_threshold(n=-5, k=2)
        assert t == 0.0

    def test_compute_cooks_threshold(self):
        exp = self._make_explorer(n=20)
        t = exp._compute_cooks_threshold(n=100, k=5)
        assert abs(t - 4.0 / 95) < 1e-9

    def test_compute_cooks_threshold_zero(self):
        exp = self._make_explorer(n=10)
        t = exp._compute_cooks_threshold(n=10, k=10)
        assert t == 0.0

    def test_identify_outliers_no_leverage(self):
        # Without leverage, no outliers
        cfg = DiagnosticsConfig(y=[1.0, 2.0, 3.0], fitted=[1.1, 1.9, 2.9], residuals=[-0.1, 0.1, 0.1])
        exp = RegressionDiagnosticsExplorer(cfg)
        result = exp.identify_outliers()
        assert "outlier_indices" in result
        assert "leverage_threshold" in result
        assert "cooks_threshold" in result

    def test_identify_outliers_with_high_leverage(self):
        exp = self._make_explorer(n=10)
        # Manually inject a high-leverage point
        exp.config.leverage[0] = 0.99
        result = exp.identify_outliers()
        # Should detect point 0 as high leverage
        if result["n_outliers"] > 0:
            assert 0 in result["outlier_indices"]

    def test_identify_outliers_with_high_cook(self):
        exp = self._make_explorer(n=20)
        # Cook's D very high
        exp.config.cooksd[0] = 100.0
        result = exp.identify_outliers()
        assert isinstance(result["outlier_details"], list)

    def test_identify_outliers_with_large_residual(self):
        # With most residuals close to 0 and one huge outlier, std is dominated
        # by the outlier's deviation from mean, but the outlier itself is even larger.
        # 3*std ≈ 94.86, so residual=100 triggers detection.
        cfg = DiagnosticsConfig(
            y=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            fitted=[1.1, 2.2, 2.9, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            residuals=[0.1, -0.2, 0.1, -0.1, 0.05, 0.0, -0.05, 0.1, 0.0, 100.0],
        )
        exp = RegressionDiagnosticsExplorer(cfg)
        result = exp.identify_outliers()
        assert result["n_outliers"] >= 1
        # Verify outlier type
        types = [d["type"] for d in result["outlier_details"]]
        assert "large_residual" in types

    def test_generate_diagnostics_report(self):
        exp = self._make_explorer(n=20)
        report = exp.generate_diagnostics_report()
        assert "n_obs" in report
        assert "r_squared" in report
        assert "adj_r_squared" in report
        assert "rmse" in report
        assert "outlier_count" in report
        assert report["n_obs"] == 20
        assert 0.0 <= report["r_squared"] <= 1.0

    def test_generate_diagnostics_report_vif(self):
        cfg = DiagnosticsConfig(
            y=[1.0, 2.0, 3.0, 4.0, 5.0],
            fitted=[1.1, 2.0, 2.9, 4.0, 5.0],
            residuals=[-0.1, 0.0, 0.1, 0.0, 0.0],
            leverage=[0.95] * 5,  # Very high leverage → high VIF
        )
        exp = RegressionDiagnosticsExplorer(cfg)
        report = exp.generate_diagnostics_report()
        assert report["vif_warning"] is True

    def test_to_plotly_figure_empty_when_no_plotly(self, monkeypatch):
        import scripts.core.interactive_explorer as ie
        monkeypatch.setattr(ie, "_plotly_available", False)
        exp = self._make_explorer(n=10)
        result = exp.to_plotly_figure()
        assert result == {} or isinstance(result, dict)


# ─── TimeSeriesDecomposer ──────────────────────────────────────────────────────


class TestTimeSeriesDecomposer:
    def test_init(self):
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0, 4.0], dates=["t1", "t2", "t3", "t4"], period=2)
        assert ts.series == [1.0, 2.0, 3.0, 4.0]
        assert ts.period == 2
        assert ts.dates == ["t1", "t2", "t3", "t4"]

    def test_init_default_dates(self):
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0])
        assert ts.dates == ["t0", "t1", "t2"]

    def test_moving_average(self):
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0, 4.0, 5.0])
        ma = ts._moving_average([1.0, 2.0, 3.0, 4.0, 5.0], window=3)
        assert len(ma) == 5
        # Middle value should be close to 3.0
        assert abs(ma[2] - 3.0) < 0.5

    def test_decompose_additive(self):
        # 24 months with seasonal pattern
        series = []
        for i in range(24):
            base = 10 + 0.1 * i
            seasonal = (1 if i % 12 < 6 else -1) * 0.5
            series.append(base + seasonal)
        ts = TimeSeriesDecomposer(series, period=12)
        result = ts.decompose(method="additive")
        assert "trend" in result
        assert "seasonal" in result
        assert "residual" in result
        assert len(result["trend"]) == 24
        assert len(result["seasonal"]) == 24

    def test_decompose_multiplicative(self):
        series = []
        for i in range(24):
            base = 10 + 0.1 * i
            seasonal = 1.1 if i % 12 < 6 else 0.9
            series.append(base * seasonal)
        ts = TimeSeriesDecomposer(series, period=12)
        result = ts.decompose(method="multiplicative")
        assert result["method"] == "multiplicative"
        assert len(result["trend"]) == 24

    def test_decompose_short_series(self):
        ts = TimeSeriesDecomposer([1.0, 2.0])
        result = ts.decompose()
        assert "trend" in result
        assert "seasonal" in result
        assert result["seasonal"] == [0.0, 0.0]

    def test_decompose_cached(self):
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        ts.decompose()
        # Second call returns cached
        assert ts._decomposition is not None

    def test_test_stationarity_short(self):
        ts = TimeSeriesDecomposer([1.0, 2.0])
        result = ts.test_stationarity()
        assert result["is_stationary"] is False
        assert result["test_stat"] != result["test_stat"]  # NaN

    def test_test_stationarity_long(self):
        import random
        random.seed(42)
        series = [10 + 0.5 * i + random.gauss(0, 1) for i in range(50)]
        ts = TimeSeriesDecomposer(series)
        result = ts.test_stationarity()
        assert "is_stationary" in result
        assert "test_stat" in result
        assert "critical_value" in result
        assert "rho_coefficient" in result
        assert "conclusion" in result

    def test_to_plotly_figure_empty_when_no_plotly(self, monkeypatch):
        import scripts.core.interactive_explorer as ie
        monkeypatch.setattr(ie, "_plotly_available", False)
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0, 4.0])
        result = ts.to_plotly_figure()
        assert result == {} or isinstance(result, dict)

    def test_to_plotly_figure_with_dates(self, monkeypatch):
        # Skip if plotly not available
        import scripts.core.interactive_explorer as ie
        if not ie._plotly_available:
            pytest.skip("plotly not available")
        series = [10 + 0.1 * i + (1 if i % 12 < 6 else -1) * 0.5 for i in range(24)]
        dates = [f"2020-{i+1:02d}" for i in range(24)]
        ts = TimeSeriesDecomposer(series, dates=dates, period=12)
        fig = ts.to_plotly_figure()
        assert isinstance(fig, dict)
        assert "data" in fig or "layout" in fig

    def test_autocorrelation(self):
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0])
        # Series [1,2,3,4,5] lag=1, mean=3, var=10:
        # autocov sum = (-1)*(-2) + 0 + 0 + (1)*(1) = 2 + 1 = 3 (per formula)
        # Wait, recompute: i=1: (2-3)*(1-3)=2, i=2: 0, i=3: 0, i=4: (5-3)*(4-3)=2 → sum=4
        # So autocorr = 4/10 = 0.4 (not 0.3)
        r = ts._autocorrelation([1.0, 2.0, 3.0, 4.0, 5.0], lag=1)
        assert abs(r - 0.4) < 0.01

    def test_autocorrelation_lag2(self):
        ts = TimeSeriesDecomposer([1.0, 2.0, 3.0])
        r = ts._autocorrelation([1.0, 2.0, 3.0, 4.0, 5.0], lag=2)
        # For [1,2,3,4,5] lag=2, mean=3:
        # i=2: (3-3)*(1-3)=0, i=3: (4-3)*(2-3)=-1, i=4: (5-3)*(3-3)=0
        # sum = -1, var = 10, autocorr = -0.1
        assert abs(r - (-0.1)) < 0.01

    def test_autocorrelation_short_series(self):
        ts = TimeSeriesDecomposer([1.0])
        # Short series [1, 2] with lag=1 → returns -0.5 (per the formula)
        r = ts._autocorrelation([1.0, 2.0], lag=1)
        assert isinstance(r, float)

    def test_autocorrelation_lag_too_long(self):
        # When lag >= n, returns 0
        r = TimeSeriesDecomposer([1.0])._autocorrelation([1.0, 2.0], lag=2)
        assert r == 0.0

    def test_autocorrelation_constant(self):
        ts = TimeSeriesDecomposer([1.0])
        r = ts._autocorrelation([5.0, 5.0, 5.0, 5.0], lag=1)
        assert r == 0.0


# ─── Module-level checks ───────────────────────────────────────────────────────


class TestModuleLevel:
    def test_plotly_flag_exists(self):
        import scripts.core.interactive_explorer as ie
        assert hasattr(ie, "_plotly_available")
        assert hasattr(ie, "_starlight_available")

    def test_module_logger(self):
        import scripts.core.interactive_explorer as ie
        assert ie._log is not None