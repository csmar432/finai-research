"""Tests for scripts/research_framework/fin_charts.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from scripts.research_framework.fin_charts import ChartConfig, FinancialChartFactory, CHART_PRESETS

class TestChartConfig:
    def test_chart_config_defaults(self):
        cfg = ChartConfig()
        assert cfg.figsize == (8, 5.5)
        assert cfg.dpi == 300
        assert cfg.font_family == "Times New Roman"
        assert cfg.output_formats == ["pdf", "png"]

    def test_chart_config_custom(self):
        cfg = ChartConfig(dpi=150, font_size=12, output_formats=["png"])
        assert cfg.dpi == 150
        assert cfg.font_size == 12
        assert cfg.output_formats == ["png"]

class TestFinancialChartFactoryInit:
    def test_init_with_defaults(self):

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(output_dir=tmpdir)
            assert factory.output_dir == Path(tmpdir)
            assert factory.config.dpi == 300
            assert Path(tmpdir).exists()

    def test_init_with_custom_config(self):
        cfg = ChartConfig(dpi=100, font_size=8, output_formats=["pdf"])
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(output_dir=tmpdir, config=cfg)
            assert factory.config.dpi == 100
            assert factory.config.font_size == 8

class TestChartPresets:
    def test_charts_preset_keys(self):
        
        required_presets = [
            "parallel_trends", "placebo_distribution", "robustness_summary",
            "psm_distribution", "correlation_heatmap", "descriptive_bar",
            "did_coef_timeline", "cumulative_effect", "residual_qq",
            "residual_distribution", "factor_returns", "stock_return_dist",
            "rolling_correlation", "heterogeneity_bar", "marginal_effects",
            "synthetic_control", "rdd_plot", "geographic_heatmap",
            "analyst_forecast", "credit_spread",
        ]
        for key in required_presets:
            assert key in CHART_PRESETS, f"Missing preset: {key}"
            p = CHART_PRESETS[key]
            assert "name" in p
            assert "required_cols" in p

class TestParallelTrends:
    def test_parallel_trends_basic(self):

        rng = np.random.default_rng(42)
        n = 200
        records = []
        for i in range(n):
            for t in range(-3, 5):
                D = 1 if i < n // 2 else 0
                y = 0.5 * t + (0.3 if D == 1 and t >= 0 else 0) + rng.normal(0, 0.1)
                records.append({"firm_id": i, "year": t, "D": D, "y": y})
        df = pd.DataFrame(records)

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_parallel_trends(
                df, time_var="year", treat_var="D", y_var="y",
                output_name="pt_test",
            )
            assert fig is not None
            assert (Path(tmpdir) / "pt_test.pdf").exists()

class TestRobustnessSummary:
    def test_robustness_summary_list_of_dicts(self):

        report = [
            {"test_name": "基准回归", "coef": 0.52, "se": 0.10, "lower_ci": 0.32, "upper_ci": 0.72},
            {"test_name": "缩尾处理", "coef": 0.49, "se": 0.11, "lower_ci": 0.27, "upper_ci": 0.71},
            {"test_name": "替换变量", "coef": 0.55, "se": 0.12, "lower_ci": 0.31, "upper_ci": 0.79},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_robustness_summary(report, output_name="robust_test")
            assert fig is not None
            assert (Path(tmpdir) / "robust_test.pdf").exists()

    def test_robustness_summary_dataframe(self):

        df = pd.DataFrame([
            {"test_name": "基准", "coef": 0.5, "se": 0.1, "lower_ci": 0.3, "upper_ci": 0.7},
            {"test_name": "不含北京", "coef": 0.48, "se": 0.11, "lower_ci": 0.26, "upper_ci": 0.70},
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_robustness_summary(df, output_name="robust_df_test")
            assert fig is not None

class TestCorrelationHeatmap:
    def test_correlation_heatmap(self):

        rng = np.random.default_rng(42)
        df = pd.DataFrame(rng.normal(0, 1, (200, 5)), columns=["y", "x1", "x2", "x3", "x4"])

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_correlation_matrix(
                df, var_cols=["y", "x1", "x2", "x3"],
                output_name="corr_test",
            )
            assert fig is not None
            assert (Path(tmpdir) / "corr_test.pdf").exists()

class TestFactorReturns:
    def test_factor_returns(self):

        rng = np.random.default_rng(42)
        dates = pd.date_range("2018-01-01", periods=60, freq="ME")
        df = pd.DataFrame({
            "date": dates,
            "mkt_rf": rng.normal(0.5, 2, 60),
            "smb": rng.normal(0.1, 1, 60),
            "hml": rng.normal(0.2, 1, 60),
            "rmw": rng.normal(0.15, 1, 60),
            "cma": rng.normal(0.1, 0.8, 60),
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_factor_returns(df, output_name="ff_test")
            assert fig is not None
            assert (Path(tmpdir) / "ff_test.pdf").exists()

class TestResidualDiagnostics:
    def test_residual_diagnostics(self):

        rng = np.random.default_rng(42)
        residuals = rng.normal(0, 1, 500)

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_residual_diagnostics(residuals, output_name="resid_test")
            assert fig is not None
            assert (Path(tmpdir) / "resid_test.pdf").exists()

class TestHeterogeneity:
    def test_heterogeneity_bar(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "industry": ["Tech", "Finance", "Energy", "Retail"],
            "y": rng.normal(0.5, 0.2, 4),
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning)
                fig = factory.plot_heterogeneity(df, group_col="industry", y_var="y",
                                                  output_name="het_test")
            assert fig is not None

class TestRDDPlot:
    def test_rdd_plot(self):

        rng = np.random.default_rng(42)
        n = 500
        df = pd.DataFrame({
            "score": rng.uniform(-1, 1, n),
            "outcome": rng.normal(0, 0.5, n) + (rng.uniform(0, 1, n) > 0.5).astype(float) * 0.3,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_rdd(df, running_var="score", outcome="outcome",
                                    cutoff=0.0, output_name="rdd_test")
            assert fig is not None

class TestCumulativeEffect:
    def test_cumulative_effect(self):

        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "event_window": list(range(-5, 6)),
            "car": [rng.normal(0.0, 0.1) if w < 0 else rng.normal(0.3 + 0.05 * w, 0.1)
                    for w in range(-5, 6)],
            "car_se": [0.1] * 11,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_cumulative_effect(
                df, window_col="event_window", car_col="car",
                se_col="car_se", output_name="car_test",
            )
            assert fig is not None

class TestPlaceboDistribution:
    def test_placebo_distribution(self):

        rng = np.random.default_rng(42)
        placebo_coefs = rng.normal(0.0, 0.1, 300)

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_placebo_distribution(
                placebo_coefs, baseline_coef=0.52,
                output_name="placebo_test",
            )
            assert fig is not None

class TestSyntheticControl:
    def test_synthetic_control(self):

        rng = np.random.default_rng(42)
        years = list(range(2010, 2022))
        df = pd.DataFrame({
            "time": years,
            "treated": [rng.normal(1.0, 0.1) + (0.2 if y >= 2016 else 0) for y in years],
            "synthetic": [rng.normal(1.0, 0.1) for y in years],
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_synthetic_control(
                df, time_col="time", treated_col="treated",
                synthetic_col="synthetic", treatment_time=2016,
                output_name="sc_test",
            )
            assert fig is not None

class TestPSMDistribution:
    def test_psm_distribution(self):

        rng = np.random.default_rng(42)
        treated_ps = rng.beta(4, 2, 200)
        control_ps = rng.beta(2, 4, 300)
        df = pd.DataFrame({
            "propensity_score": list(treated_ps) + list(control_ps),
            "D": [1] * 200 + [0] * 300,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_psm_distribution(
                df, propensity_col="propensity_score", treat_col="D",
                output_name="psm_test",
            )
            assert fig is not None

class TestTimeseries:
    def test_timeseries(self):

        rng = np.random.default_rng(42)
        dates = pd.date_range("2018-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "value": rng.normal(0, 1, 100).cumsum(),
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_timeseries(df, date_col="date", value_col="value",
                                           output_name="ts_test")
            assert fig is not None

class TestEventStudy:
    def test_event_study(self):

        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "period": list(range(-5, 6)),
            "coef": [0.01, 0.02, -0.01, 0.0, 0.0,
                     0.52, 0.55, 0.50, 0.53, 0.49, 0.51],
            "se": [0.10] * 11,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_event_study(df, output_name="event_study_test")
            assert fig is not None

class TestHeterogeneityForest:
    def test_heterogeneity_forest(self):

        results = {
            "东部": (0.62, 0.12),
            "中部": (0.48, 0.14),
            "西部": (0.35, 0.15),
            "东北": (0.55, 0.18),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_heterogeneity_forest(results, output_name="het_forest_test")
            assert fig is not None

class TestSensitivityTornado:
    def test_sensitivity_tornado(self):

        perturbs = {
            "排除北京上海": (0.38, 0.62),
            "缩尾1%": (0.45, 0.58),
            "替换因变量": (0.41, 0.55),
            "延长窗口": (0.44, 0.60),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_sensitivity_tornado(
                baseline=0.52, perturbations=perturbs,
                output_name="tornado_test",
            )
            assert fig is not None

class TestCoefficientEvolution:
    def test_coefficient_evolution(self):

        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "year": list(range(2010, 2021)),
            "coef": [0.3 + rng.normal(0, 0.05) for _ in range(11)],
            "se": [0.10] * 11,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_coefficient_evolution(
                df, time_col="year", coef_col="coef", se_col="se",
                output_name="coef_evo_test",
            )
            assert fig is not None

class TestDoseResponse:
    def test_dose_response(self):

        rng = np.random.default_rng(42)
        n = 500
        df = pd.DataFrame({
            "dose": rng.beta(2, 5, n) * 10,
            "outcome": rng.normal(0.5, 0.2, n),
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_dose_response(
                df, dose_col="dose", outcome_col="outcome",
                n_bins=8, output_name="dose_test",
            )
            assert fig is not None

class TestBalanceTable:
    def test_balance_table(self):

        before = pd.Series({"size": 0.35, "leverage": 0.28, "roa": 0.22, "tangibility": 0.19})
        after = pd.Series({"size": 0.05, "leverage": 0.04, "roa": 0.03, "tangibility": 0.02})

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_balance_table(before, after, output_name="balance_test")
            assert fig is not None

class TestEventTimeline:
    def test_event_timeline(self):

        events = [
            ("研究启动", "2018-01-15"),
            ("数据采集", "2018-06-01"),
            ("实证分析", "2019-03-01"),
            ("论文撰写", "2019-09-01"),
            ("投稿", "2020-01-15"),
            ("接收发表", "2020-06-01"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot_event_timeline(events, output_name="timeline_test")
            assert fig is not None

    def test_event_timeline_unparseable_raises(self):

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            with pytest.raises(ValueError, match="no parseable"):
                factory.plot_event_timeline(
                    [("研究启动", "invalid-date")], output_name="tl_bad",
                )

class TestGenericPlotDispatcher:
    def test_dispatch_parallel_trends(self):

        rng = np.random.default_rng(42)
        n = 100
        records = []
        for i in range(n):
            for t in range(-2, 4):
                D = 1 if i < n // 2 else 0
                y = t + (0.5 if D == 1 and t >= 0 else 0) + rng.normal(0, 0.2)
                records.append({"firm": i, "year": t, "D": D, "y": y})
        df = pd.DataFrame(records)

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig = factory.plot("parallel_trends", df, output_name="dispatch_test",
                                time_var="year", treat_var="D", y_var="y")
            assert fig is not None

    def test_dispatch_unknown_type_raises(self):

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            with pytest.raises(ValueError, match="Unknown chart type"):
                factory.plot("nonexistent_chart", pd.DataFrame(), output_name="bad_dispatch")

class TestNewFig:
    def test_new_fig_custom_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            factory = FinancialChartFactory(
                output_dir=tmpdir,
                config=ChartConfig(output_formats=["pdf"]),
            )
            fig, ax = factory._new_fig(figsize=(6, 4))
            assert fig is not None
            assert ax is not None
            plt.close(fig)
