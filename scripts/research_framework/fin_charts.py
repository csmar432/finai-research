"""
fin_charts.py — 专业金融图表模板工厂

生成经济金融论文中最常用的20种标准图表，覆盖：
  - 实证结果可视化
  - 时间序列分析
  - 面板数据图表
  - 金融行情图表
  - 稳健性检验可视化
  - 因子分析图表

每个图表均为matplotlib/seaborn实现，输出≥300 DPI的PDF/SVG/PNG格式。
可直接插入LaTeX文档。

Usage:
    from scripts.research_framework.fin_charts import FinancialChartFactory, CHART_PRESETS

    factory = FinancialChartFactory(output_dir="output/figures", dpi=300)
    factory.plot_parallel_trends(df, treat_var, time_var, y_var)
    factory.plot_robustness_summary(robustness_report)
    factory.plot_factor_returns(factor_returns_df)
    factory.plot_citation_network(citation_data)
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
logging.getLogger("matplotlib").setLevel(logging.WARNING)

__all__ = [
    "FinancialChartFactory",
    "CHART_PRESETS",
    "ChartConfig",
]

_log = logging.getLogger("fin_charts")
_log.setLevel(logging.INFO)


# ─── Chart presets ────────────────────────────────────────────────────────────

@dataclass
class ChartConfig:
    """Chart configuration with defaults for academic papers."""
    figsize: tuple[float, float] = (8, 5.5)
    dpi: int = 300
    font_family: str = "Times New Roman"
    font_size: int = 10
    title_fontsize: int = 12
    label_fontsize: int = 10
    tick_fontsize: int = 9
    line_width: float = 1.5
    marker_size: float = 5.0
    grid_alpha: float = 0.3
    legend_fontsize: int = 9
    output_formats: list[str] = field(default_factory=lambda: ["pdf", "png"])
    style: str = "seaborn-v0_8-paper"
    color_palette: str = "colorblind"


CHART_PRESETS: dict[str, dict[str, Any]] = {
    # 1. 平行趋势图（事件研究）
    "parallel_trends": {
        "name": "平行趋势图",
        "name_en": "Parallel Trends / Event Study",
        "description": "处理组与对照组在政策前后的趋势对比",
        "required_cols": ["time", "treated_mean", "control_mean", "post"],
        "optional_cols": ["treated_se", "control_se", "lower_ci", "upper_ci"],
        "figsize": (7, 5),
        "style": "event_study",
    },
    # 2. 安慰剂检验分布图
    "placebo_distribution": {
        "name": "安慰剂检验分布图",
        "name_en": "Placebo Test Distribution",
        "description": "随机处理分配的系数分布与基准系数对比",
        "required_cols": ["coef"],
        "optional_cols": ["pval"],
        "figsize": (6, 4),
        "style": "histogram",
    },
    # 3. 稳健性检验汇总表（条形图）
    "robustness_summary": {
        "name": "稳健性检验汇总图",
        "name_en": "Robustness Test Summary",
        "description": "各稳健性检验的DID系数与基准系数对比",
        "required_cols": ["test_name", "coef", "lower_ci", "upper_ci"],
        "optional_cols": ["is_significant"],
        "figsize": (8, 5),
        "style": "forest_plot",
    },
    # 4. PSM倾向得分分布
    "psm_distribution": {
        "name": "PSM倾向得分分布",
        "name_en": "Propensity Score Distribution",
        "description": "匹配前后处理组与对照组的倾向得分分布对比",
        "required_cols": ["propensity_score", "treated"],
        "optional_cols": ["matched"],
        "figsize": (7, 4.5),
        "style": "overlapping_hist",
    },
    # 5. 相关性热力图
    "correlation_heatmap": {
        "name": "变量相关性热力图",
        "name_en": "Correlation Heatmap",
        "description": "主要回归变量间的Pearson相关系数矩阵",
        "required_cols": ["variable_pairs"],
        "optional_cols": ["p_values"],
        "figsize": (8, 7),
        "style": "heatmap",
    },
    # 6. 描述性统计条形图
    "descriptive_bar": {
        "name": "描述性统计对比图",
        "name_en": "Descriptive Statistics Comparison",
        "description": "处理组与对照组主要变量的均值差异",
        "required_cols": ["variable", "treated_mean", "control_mean"],
        "optional_cols": ["treated_sd", "control_sd"],
        "figsize": (8, 5),
        "style": "grouped_bar",
    },
    # 7. DID系数时序图
    "did_coef_timeline": {
        "name": "DID系数时序图",
        "name_en": "DID Coefficient Timeline",
        "description": "不同稳健性方法下DID系数的时序变化",
        "required_cols": ["period", "coef", "se"],
        "optional_cols": ["method", "lower", "upper"],
        "figsize": (9, 4.5),
        "style": "coef_line",
    },
    # 8. 累积处置效应图
    "cumulative_effect": {
        "name": "累积处置效应图",
        "name_en": "Cumulative Treatment Effect",
        "description": "事件研究法下的累积处置效应（CAR）",
        "required_cols": ["event_window", "car", "window_left", "window_right"],
        "optional_cols": ["car_se", "confidence_interval"],
        "figsize": (8, 5),
        "style": "event_study",
    },
    # 9. 残差 QQ 图
    "residual_qq": {
        "name": "残差QQ图",
        "name_en": "Residual Q-Q Plot",
        "description": "回归残差的正态性检验（分位数-分位数图）",
        "required_cols": ["residuals"],
        "optional_cols": ["theoretical_quantiles"],
        "figsize": (5, 5),
        "style": "qq_plot",
    },
    # 10. 残差分布图
    "residual_distribution": {
        "name": "残差分布图",
        "name_en": "Residual Distribution",
        "description": "回归残差的直方图与核密度估计",
        "required_cols": ["residuals"],
        "optional_cols": ["fitted_values"],
        "figsize": (6, 4),
        "style": "histogram_kde",
    },
    # 11. Fama-French 五因子收益率
    "factor_returns": {
        "name": "因子收益率时序图",
        "name_en": "Fama-French Factor Returns",
        "description": "Fama-French 五因子（或自定义因子）的月度收益率时序",
        "required_cols": ["date", "mkt_rf", "smb", "hml", "rmw", "cma"],
        "optional_cols": ["umd"],
        "figsize": (10, 6),
        "style": "factor_timeseries",
    },
    # 12. 股票收益率分布
    "stock_return_dist": {
        "name": "股票收益率分布",
        "name_en": "Stock Return Distribution",
        "description": "个股收益率的分布（正态 vs t分布对比）",
        "required_cols": ["returns"],
        "optional_cols": ["benchmark_returns"],
        "figsize": (7, 5),
        "style": "distribution_compare",
    },
    # 13. 滚动相关性图
    "rolling_correlation": {
        "name": "滚动相关性图",
        "name_en": "Rolling Correlation",
        "description": "两个变量的滚动窗口相关性时序",
        "required_cols": ["date", "rolling_corr"],
        "optional_cols": ["lower_ci", "upper_ci"],
        "figsize": (9, 4),
        "style": "rolling_line",
    },
    # 14. 分组柱状图（异质性分析）
    "heterogeneity_bar": {
        "name": "异质性分析分组图",
        "name_en": "Heterogeneity Analysis",
        "description": "不同子样本下DID系数的对比（行业/地区/规模分组）",
        "required_cols": ["group", "coef", "se"],
        "optional_cols": ["n_obs", "pval"],
        "figsize": (8, 5),
        "style": "grouped_coef",
    },
    # 15. 边际效应图
    "marginal_effects": {
        "name": "边际效应图",
        "name_en": "Marginal Effects Plot",
        "description": "连续变量在不同取值下的边际效应（非线性模型）",
        "required_cols": ["x_var", "marginal_effect", "se"],
        "optional_cols": ["lower_ci", "upper_ci"],
        "figsize": (7, 5),
        "style": "marginal_effect",
    },
    # 16. 合成控制法反事实图
    "synthetic_control": {
        "name": "合成控制反事实图",
        "name_en": "Synthetic Control",
        "description": "处理单元与合成对照的反事实对比",
        "required_cols": ["period", "treated", "synthetic"],
        "optional_cols": ["placebo_treated", "placebo_synthetic"],
        "figsize": (9, 5),
        "style": "sc_plot",
    },
    # 17. RDD断点图
    "rdd_plot": {
        "name": "RDD断点图",
        "name_en": "Regression Discontinuity",
        "description": "断点回归的散点图与拟合线",
        "required_cols": ["running_var", "outcome", "cutoff"],
        "optional_cols": ["fitted_line_left", "fitted_line_right"],
        "figsize": (8, 5),
        "style": "rdd",
    },
    # 18. 热力地图（地区异质性）
    "geographic_heatmap": {
        "name": "地区异质性热力图",
        "name_en": "Geographic Heterogeneity",
        "description": "省份/城市维度的处理效应空间分布",
        "required_cols": ["province_code", "coef"],
        "optional_cols": ["se", "n_obs"],
        "figsize": (10, 7),
        "style": "choropleth",
    },
    # 19. 分析师预测误差分布
    "analyst_forecast": {
        "name": "分析师预测误差分布",
        "name_en": "Analyst Forecast Error",
        "description": "分析师盈利预测误差的分布与精度",
        "required_cols": ["forecast_error"],
        "optional_cols": ["actual_eps", "forecast_eps"],
        "figsize": (7, 5),
        "style": "histogram_kde",
    },
    # 20. 信用利差与评级迁移
    "credit_spread": {
        "name": "信用利差时序图",
        "name_en": "Credit Spread Time Series",
        "description": "不同评级/行业的信用利差时序变化",
        "required_cols": ["date", "spread"],
        "optional_cols": ["rating", "industry"],
        "figsize": (9, 4.5),
        "style": "spread_timeseries",
    },
}


# ─── Main Chart Factory ──────────────────────────────────────────────────────

class FinancialChartFactory:
    """
    专业金融图表工厂。

    Attributes
    ----------
    output_dir : Path
        图表输出目录，默认 `output/figures`
    config : ChartConfig
        全局图表配置。

    Methods
    -------
    plot_parallel_trends(df, time_var, treat_var, y_var)
        平行趋势图（事件研究）
    plot_robustness_summary(report)
        稳健性检验汇总（森林图）
    plot_factor_returns(df, factor_cols)
        Fama-French 因子收益率
    plot_correlation_matrix(df, var_cols)
        相关性热力图
    plot_residual_diagnostics(df, residuals, fitted)
        残差诊断（QQ图+残差分布）
    plot_heterogeneity(df, group_col, y_var)
        异质性分析（分组系数图）
    plot_rdd(df, running_var, outcome, cutoff)
        RDD 断点图
    plot_synthetic_control(df, period, treated, synthetic)
        合成控制反事实图
    plot_cumulative_effect(df, event_window, car)
        累积处置效应（CAR）
    save(fig, name, formats)
        保存图表到文件
    """

    CHINESE_FONT_CANDIDATES = [
        "SimHei", "Microsoft YaHei", "PingFang SC", "Heiti SC",
        "STHeiti", "Noto Sans CJK SC", "Source Han Sans SC",
    ]
    ENGLISH_FONT = "Times New Roman"

    def __init__(
        self,
        output_dir: str | Path = "output/figures",
        config: ChartConfig | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or ChartConfig()
        self._setup_matplotlib()

    def _setup_matplotlib(self):
        """Configure matplotlib for academic paper standards.

        Font setup:
        - Chinese: try candidates in order; verify availability with font_manager
        - English: "Times New Roman" via font_manager (not hardcoded rcParam)
        - Final fallback: DejaVu Sans (matplotlib built-in, guaranteed available)
        """
        import matplotlib as mpl
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt

        mpl.use("Agg")  # Non-interactive backend
        plt.style.use(self.config.style)

        # Build font list: [Chinese candidates, ENGLISH_FONT, DejaVu Sans]
        chinese = self.CHINESE_FONT_CANDIDATES
        english = self.ENGLISH_FONT
        fallback = "DejaVu Sans"
        candidate_fonts = chinese + [english, fallback]

        # Verify each font is available before adding to rcParams
        available = {f.name for f in fm.fontManager.ttflist}
        font_list = [f for f in candidate_fonts if f in available]

        if font_list:
            plt.rcParams["font.sans-serif"] = font_list
        else:
            # Fallback: DejaVu Sans should always be available
            plt.rcParams["font.sans-serif"] = [fallback]

        plt.rcParams["axes.unicode_minus"] = False

        plt.rcParams.update({
            "font.family": "sans-serif",
            "font.size": self.config.font_size,
            "axes.labelsize": self.config.label_fontsize,
            "axes.titlesize": self.config.title_fontsize,
            "xtick.labelsize": self.config.tick_fontsize,
            "ytick.labelsize": self.config.tick_fontsize,
            "legend.fontsize": self.config.legend_fontsize,
            "figure.dpi": self.config.dpi,
            "savefig.dpi": self.config.dpi,
            "figure.figsize": self.config.figsize,
            "lines.linewidth": self.config.line_width,
            "lines.markersize": self.config.marker_size,
            "axes.grid": True,
            "grid.alpha": self.config.grid_alpha,
        })

    def _new_fig(self, figsize: tuple[float, float] | None = None) -> "plt.Figure":
        import matplotlib.pyplot as plt
        fig_size = figsize or self.config.figsize
        return plt.subplots(figsize=fig_size)

    def _palette(self, idx: int) -> tuple[float, float, float]:
        """Return a color from the configured palette by index."""
        import seaborn as sns
        return sns.color_palette(self.config.color_palette, idx + 1)[idx]

    def _save(self, fig: "plt.Figure", name: str, formats: list[str] | None = None):
        """Save figure to disk.

        T3 audit 2026-07-12: strip PNG metadata to remove DateTime / Software
        fields that vary by matplotlib version + OS, reducing cross-OS drift.
        PDF metadata is left intact (LaTeX embedders need it).
        """
        fmt_list = formats or self.config.output_formats
        for fmt in fmt_list:
            path = self.output_dir / f"{name}.{fmt}"
            # Strip OS-version-dependent metadata. Fields like DateTime and
            # Software change across matplotlib builds / OSes; clearing them
            # brings PNG/PDF metadata closer to byte-identity.
            md = {
                "Title": name,
                "Author": "",
                "Subject": "",
                "Keywords": "",
                "Creator": "",
                "Producer": "matplotlib (T3 audit normalized)",
                "CreationDate": "",
                "ModDate": "",
            }
            fig.savefig(
                path,
                bbox_inches="tight",
                dpi=self.config.dpi,
                metadata=md,
            )
            _log.info(f"Saved {path}")
        import matplotlib.pyplot as plt
        plt.close(fig)

    # ── Chart 1: Parallel Trends (Event Study) ─────────────────────────────────

    def plot_parallel_trends(
        self,
        df: pd.DataFrame,
        time_var: str,
        treat_var: str,
        y_var: str,
        output_name: str = "parallel_trends",
        figsize: tuple[float, float] = (7, 5),
    ) -> "plt.Figure":
        """
        Plot parallel trends / event study.

        Shows treated vs control group trends around policy implementation.
        Essential for DID validity assessment.
        """
        import seaborn as sns

        fig, ax = self._new_fig(figsize)

        # Compute group means by time
        df_ = df.copy()
        treated = df_[df_[treat_var] == 1].groupby(time_var)[y_var].agg(["mean", "std", "count"]).reset_index()
        control = df_[df_[treat_var] == 0].groupby(time_var)[y_var].agg(["mean", "std", "count"]).reset_index()

        ax.plot(treated[time_var], treated["mean"], "o-", label="处理组", linewidth=1.5, markersize=5)
        ax.plot(control[time_var], control["mean"], "s--", label="对照组", linewidth=1.5, markersize=5)

        # Shade pre-treatment period
        ax.axvline(x=0, color="red", linestyle=":", linewidth=1.5, alpha=0.7, label="政策实施")
        ax.axvspan(ax.get_xlim()[0], 0, alpha=0.05, color="gray", label="政策前期")

        ax.set_xlabel(f"时间 ({time_var})", fontsize=self.config.label_fontsize)
        ax.set_ylabel(y_var, fontsize=self.config.label_fontsize)
        ax.legend(fontsize=self.config.legend_fontsize, framealpha=0.9)
        ax.set_title("平行趋势检验", fontsize=self.config.title_fontsize, pad=12)
        sns.despine(ax=ax)
        ax.grid(True, alpha=self.config.grid_alpha)

        self._save(fig, output_name)
        return fig

    # ── Chart 2: Robustness Test Summary (Forest Plot) ──────────────────────

    def plot_robustness_summary(
        self,
        report: "RobustnessReport | pd.DataFrame | list[dict]",
        output_name: str = "robustness_summary",
        figsize: tuple[float, float] = (8, 5),
    ) -> "plt.Figure":
        """
        Plot robustness test results as a forest plot.

        Shows DID coefficient with 95% CI for each robustness test.
        Baseline coefficient is highlighted.
        """
        import seaborn as sns

        # Normalize input to DataFrame
        if hasattr(report, "to_dataframe"):
            df = report.to_dataframe()
        elif isinstance(report, pd.DataFrame):
            df = report
        else:
            df = pd.DataFrame(report)

        fig, ax = self._new_fig(figsize)

        y_pos = range(len(df))
        coefs = df["coef"].values
        lower = df.get("lower_ci", coefs - 1.96 * df.get("se", 0.1)).values
        upper = df.get("upper_ci", coefs + 1.96 * df.get("se", 0.1)).values
        names = df["test_name"].values if "test_name" in df.columns else df.index.values

        # Plot baseline as separate
        baseline_coef = coefs[0] if len(coefs) > 0 else 0

        # Horizontal forest plot
        ax.scatter(coefs, y_pos, s=60, zorder=3, color="steelblue")
        for i, (c, lo, hi) in enumerate(zip(coefs, lower, upper)):
            ax.plot([lo, hi], [i, i], "-", linewidth=1.5, color="steelblue", alpha=0.7)

        # Baseline: red diamond
        if len(coefs) > 0:
            ax.scatter([coefs[0]], [0], s=120, marker="D", color="red", zorder=4, label="基准回归")
        ax.axvline(x=baseline_coef, color="red", linestyle=":", alpha=0.5, linewidth=1)

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(names, fontsize=self.config.tick_fontsize)
        ax.set_xlabel("DID 系数", fontsize=self.config.label_fontsize)
        ax.set_title("稳健性检验汇总", fontsize=self.config.title_fontsize, pad=12)
        ax.grid(True, alpha=self.config.grid_alpha, axis="x")
        sns.despine(ax=ax)

        self._save(fig, output_name)
        return fig

    # ── Chart 3: Factor Returns ────────────────────────────────────────────────

    def plot_factor_returns(
        self,
        df: pd.DataFrame,
        date_col: str = "date",
        factor_cols: list[str] | None = None,
        output_name: str = "factor_returns",
        figsize: tuple[float, float] = (10, 6),
    ) -> "plt.Figure":
        """
        Plot Fama-French factor (or custom) returns over time.
        """
        import seaborn as sns

        if factor_cols is None:
            factor_cols = ["mkt_rf", "smb", "hml", "rmw", "cma"]

        fig, ax = self._new_fig(figsize)

        df_ = df.copy()
        df_[date_col] = pd.to_datetime(df_[date_col])
        df_ = df_.sort_values(date_col)

        colors = sns.color_palette(self.config.color_palette, len(factor_cols))

        for i, col in enumerate(factor_cols):
            if col in df_.columns:
                cumulative = (1 + df_[col] / 100).cumprod()
                ax.plot(df_[date_col], cumulative, "-", label=col, linewidth=1.2, color=colors[i])

        ax.set_xlabel("日期", fontsize=self.config.label_fontsize)
        ax.set_ylabel("累积收益 (初始=1)", fontsize=self.config.label_fontsize)
        ax.set_title("因子累积收益时序", fontsize=self.config.title_fontsize, pad=12)
        ax.legend(fontsize=self.config.legend_fontsize, ncol=min(len(factor_cols), 5), framealpha=0.9)
        ax.grid(True, alpha=self.config.grid_alpha)
        sns.despine(ax=ax)
        fig.autofmt_xdate()

        self._save(fig, output_name)
        return fig

    # ── Chart 4: Correlation Heatmap ──────────────────────────────────────────

    def plot_correlation_matrix(
        self,
        df: pd.DataFrame,
        var_cols: list[str] | None = None,
        output_name: str = "correlation_heatmap",
        figsize: tuple[float, float] = (8, 7),
        annot: bool = True,
    ) -> "plt.Figure":
        """Plot Pearson correlation matrix as a heatmap."""
        import matplotlib.pyplot as plt
        import seaborn as sns

        if var_cols:
            corr_df = df[var_cols].corr()
        else:
            corr_df = df.select_dtypes(include=[np.number]).corr()

        fig, ax = self._new_fig(figsize)

        mask = np.triu(np.ones_like(corr_df, dtype=bool), k=1)
        cmap = sns.diverging_palette(220, 10, as_cmap=True)

        sns.heatmap(
            corr_df, mask=mask,
            annot=annot, fmt=".2f", cmap=cmap,
            vmin=-1, vmax=1, center=0,
            square=True, linewidths=0.5,
            cbar_kws={"shrink": 0.8, "label": "Pearson r"},
            ax=ax,
            annot_kws={"size": self.config.tick_fontsize},
        )
        ax.set_title("变量相关性矩阵", fontsize=self.config.title_fontsize, pad=12)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=self.config.tick_fontsize)
        plt.setp(ax.get_yticklabels(), rotation=0, fontsize=self.config.tick_fontsize)

        self._save(fig, output_name)
        return fig

    # ── Chart 5: Residual Diagnostics ───────────────────────────────────────────

    def plot_residual_diagnostics(
        self,
        residuals: np.ndarray | pd.Series,
        fitted: np.ndarray | pd.Series | None = None,
        output_name: str = "residual_diagnostics",
        figsize: tuple[float, float] = (10, 4),
    ) -> "plt.Figure":
        """Plot residual diagnostics: QQ plot + residual distribution."""
        import matplotlib.pyplot as plt
        import seaborn as sns
        from scipy import stats

        fig, axes = plt.subplots(1, 2, figsize=figsize)

        res = np.array(residuals).flatten()

        # QQ Plot
        ax = axes[0]
        stats.probplot(res, dist="norm", plot=ax)
        ax.set_title("残差 Q-Q 图", fontsize=self.config.title_fontsize)
        ax.set_xlabel("理论分位数", fontsize=self.config.label_fontsize)
        ax.set_ylabel("样本分位数", fontsize=self.config.label_fontsize)
        sns.despine(ax=ax)

        # Residual histogram with KDE
        ax = axes[1]
        sns.histplot(res, kde=True, stat="density", ax=ax, color="steelblue", alpha=0.6)
        x_range = np.linspace(res.min(), res.max(), 200)
        ax.plot(x_range, stats.norm.pdf(x_range, float(res.mean()), float(res.std())),
                "r--", linewidth=1.5, label="正态分布")
        ax.set_title("残差分布", fontsize=self.config.title_fontsize)
        ax.set_xlabel("残差", fontsize=self.config.label_fontsize)
        ax.set_ylabel("密度", fontsize=self.config.label_fontsize)
        ax.legend(fontsize=self.config.legend_fontsize)
        sns.despine(ax=ax)

        fig.suptitle("残差诊断图", fontsize=self.config.title_fontsize + 1, y=1.02)
        plt.tight_layout()

        self._save(fig, output_name)
        return fig

    # ── Chart 6: Heterogeneity Bar ────────────────────────────────────────────

    def plot_heterogeneity(
        self,
        df: pd.DataFrame,
        group_col: str,
        y_var: str,
        output_name: str = "heterogeneity",
        figsize: tuple[float, float] = (8, 5),
    ) -> "plt.Figure":
        """Plot heterogeneity analysis as grouped bar chart."""
        import matplotlib.pyplot as plt
        import seaborn as sns

        fig, ax = self._new_fig(figsize)

        sns.barplot(data=df, x=group_col, y=y_var, ax=ax,
                    palette=self.config.color_palette, alpha=0.8,
                    errorbar="sd", capsize=0.1)

        ax.set_xlabel(group_col, fontsize=self.config.label_fontsize)
        ax.set_ylabel(y_var, fontsize=self.config.label_fontsize)
        ax.set_title(f"异质性分析：{group_col}", fontsize=self.config.title_fontsize, pad=12)
        ax.grid(True, alpha=self.config.grid_alpha, axis="y")
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=self.config.tick_fontsize)
        sns.despine(ax=ax)

        self._save(fig, output_name)
        return fig

    # ── Chart 7: RDD Plot ─────────────────────────────────────────────────────

    def plot_rdd(
        self,
        df: pd.DataFrame,
        running_var: str,
        outcome: str,
        cutoff: float,
        output_name: str = "rdd_plot",
        bandwidth: float | None = None,
        figsize: tuple[float, float] = (8, 5),
    ) -> "plt.Figure":
        """Plot Regression Discontinuity Design scatter with fitted lines."""
        import seaborn as sns

        fig, ax = self._new_fig(figsize)

        df_ = df.copy()
        ax.scatter(df_[running_var], df_[outcome], alpha=0.4, s=15, color="steelblue")

        left = df_[df_[running_var] < cutoff]
        right = df_[df_[running_var] >= cutoff]

        if len(left) > 2:
            z = np.polyfit(left[running_var], left[outcome], 1)
            p = np.poly1d(z)
            x_left = np.linspace(left[running_var].min(), cutoff, 100)
            ax.plot(x_left, p(x_left), "b-", linewidth=2, label="左侧拟合")

        if len(right) > 2:
            z = np.polyfit(right[running_var], right[outcome], 1)
            p = np.poly1d(z)
            x_right = np.linspace(cutoff, right[running_var].max(), 100)
            ax.plot(x_right, p(x_right), "r-", linewidth=2, label="右侧拟合")

        ax.axvline(x=cutoff, color="black", linestyle="--", linewidth=1.5, label=f"断点 (x={cutoff})")
        ax.set_xlabel(running_var, fontsize=self.config.label_fontsize)
        ax.set_ylabel(outcome, fontsize=self.config.label_fontsize)
        ax.set_title("断点回归设计 (RDD)", fontsize=self.config.title_fontsize, pad=12)
        ax.legend(fontsize=self.config.legend_fontsize)
        ax.grid(True, alpha=self.config.grid_alpha)
        sns.despine(ax=ax)

        self._save(fig, output_name)
        return fig

    # ── Chart 8: Cumulative Treatment Effect ──────────────────────────────────

    def plot_cumulative_effect(
        self,
        df: pd.DataFrame,
        window_col: str,
        car_col: str,
        output_name: str = "cumulative_effect",
        se_col: str | None = None,
        figsize: tuple[float, float] = (8, 5),
    ) -> "plt.Figure":
        """Plot cumulative treatment effect (CAR) with confidence interval."""
        import seaborn as sns

        fig, ax = self._new_fig(figsize)

        df_ = df.copy()
        df_ = df_.sort_values(window_col)

        ax.plot(df_[window_col], df_[car_col], "o-", linewidth=1.5, markersize=5, color="steelblue")

        if se_col and se_col in df_.columns:
            ax.fill_between(
                df_[window_col],
                df_[car_col] - 1.96 * df_[se_col],
                df_[car_col] + 1.96 * df_[se_col],
                alpha=0.2, color="steelblue", label="95% CI",
            )

        ax.axhline(y=0, color="black", linestyle="-", linewidth=0.8)
        ax.axvline(x=0, color="red", linestyle=":", linewidth=1.5, alpha=0.7, label="事件日")
        ax.axvspan(ax.get_xlim()[0], 0, alpha=0.05, color="gray")

        ax.set_xlabel("事件窗口", fontsize=self.config.label_fontsize)
        ax.set_ylabel("累积超额收益 (CAR)", fontsize=self.config.label_fontsize)
        ax.set_title("累积处置效应", fontsize=self.config.title_fontsize, pad=12)
        ax.legend(fontsize=self.config.legend_fontsize)
        ax.grid(True, alpha=self.config.grid_alpha)
        sns.despine(ax=ax)

        self._save(fig, output_name)
        return fig

    # ── Chart 9: Placebo Distribution ────────────────────────────────────────

    def plot_placebo_distribution(
        self,
        placebo_coefs: np.ndarray | list[float],
        baseline_coef: float,
        output_name: str = "placebo_distribution",
        figsize: tuple[float, float] = (6, 4),
    ) -> "plt.Figure":
        """Plot placebo test coefficient distribution."""
        import seaborn as sns
        from scipy import stats

        fig, ax = self._new_fig(figsize)

        coefs = np.array(placebo_coefs)
        sns.histplot(coefs, kde=True, stat="density", ax=ax, color="steelblue", alpha=0.6, bins=30)

        x_range = np.linspace(coefs.min(), coefs.max(), 200)
        ax.plot(x_range, stats.norm.pdf(x_range, coefs.mean(), coefs.std()),
                "r--", linewidth=1.5, label="正态拟合")

        ax.axvline(x=baseline_coef, color="red", linestyle="-", linewidth=2, label=f"基准系数={baseline_coef:.3f}")
        ax.axvline(x=0, color="black", linestyle=":", linewidth=1, alpha=0.5)

        p_val = np.mean(np.abs(coefs) >= np.abs(baseline_coef))
        ax.set_title(f"安慰剂检验 (p={p_val:.3f})", fontsize=self.config.title_fontsize, pad=12)
        ax.set_xlabel("DID 系数", fontsize=self.config.label_fontsize)
        ax.set_ylabel("密度", fontsize=self.config.label_fontsize)
        ax.legend(fontsize=self.config.legend_fontsize)
        sns.despine(ax=ax)

        self._save(fig, output_name)
        return fig

    # ── Chart 10: Synthetic Control ────────────────────────────────────────────

    def plot_synthetic_control(
        self,
        df: pd.DataFrame,
        time_col: str,
        treated_col: str,
        synthetic_col: str,
        output_name: str = "synthetic_control",
        treatment_time: float | None = None,
        figsize: tuple[float, float] = (9, 5),
    ) -> "plt.Figure":
        """Plot synthetic control: treated vs synthetic counterfactual."""
        import seaborn as sns

        fig, ax = self._new_fig(figsize)

        ax.plot(df[time_col], df[treated_col], "-", linewidth=1.5, color="blue", label="处理单元")
        ax.plot(df[time_col], df[synthetic_col], "--", linewidth=1.5, color="red", label="合成对照")

        if treatment_time is not None:
            ax.axvline(x=treatment_time, color="black", linestyle=":", linewidth=1.5,
                       label=f"政策时点", alpha=0.7)
            ax.axvspan(treatment_time, ax.get_xlim()[1], alpha=0.05, color="gray")

        ax.set_xlabel("时间", fontsize=self.config.label_fontsize)
        ax.set_ylabel("结果变量", fontsize=self.config.label_fontsize)
        ax.set_title("合成控制法：反事实对比", fontsize=self.config.title_fontsize, pad=12)
        ax.legend(fontsize=self.config.legend_fontsize, framealpha=0.9)
        ax.grid(True, alpha=self.config.grid_alpha)
        sns.despine(ax=ax)

        self._save(fig, output_name)
        return fig

    # ── Chart 11: PSM Distribution ─────────────────────────────────────────────

    def plot_psm_distribution(
        self,
        df: pd.DataFrame,
        propensity_col: str,
        treat_col: str,
        output_name: str = "psm_distribution",
        before_match_df: pd.DataFrame | None = None,
        figsize: tuple[float, float] = (7, 4.5),
    ) -> "plt.Figure":
        """Plot propensity score distribution before/after matching."""
        import matplotlib.pyplot as plt
        import seaborn as sns

        fig, axes = plt.subplots(1, 2, figsize=figsize)

        # After matching
        ax = axes[0]
        treated = df[df[treat_col] == 1][propensity_col]
        control = df[df[treat_col] == 0][propensity_col]

        ax.hist(treated, bins=30, alpha=0.6, label=f"处理组 (n={len(treated)})", color="steelblue", density=True)
        ax.hist(control, bins=30, alpha=0.6, label=f"对照组 (n={len(control)})", color="coral", density=True)
        ax.set_xlabel("倾向得分", fontsize=self.config.label_fontsize)
        ax.set_ylabel("密度", fontsize=self.config.label_fontsize)
        ax.set_title("匹配后：倾向得分分布", fontsize=self.config.title_fontsize)
        ax.legend(fontsize=self.config.legend_fontsize)
        sns.despine(ax=ax)

        # Common support
        if before_match_df is not None:
            ax = axes[1]
            treated_b = before_match_df[before_match_df[treat_col] == 1][propensity_col]
            control_b = before_match_df[before_match_df[treat_col] == 0][propensity_col]
            ax.hist(treated_b, bins=30, alpha=0.6, label="处理组（匹配前）", color="steelblue", density=True)
            ax.hist(control_b, bins=30, alpha=0.6, label="对照组（匹配前）", color="coral", density=True)
            ax.set_xlabel("倾向得分", fontsize=self.config.label_fontsize)
            ax.set_ylabel("密度", fontsize=self.config.label_fontsize)
            ax.set_title("匹配前：倾向得分分布", fontsize=self.config.title_fontsize)
            ax.legend(fontsize=self.config.legend_fontsize)
            sns.despine(ax=ax)

        plt.tight_layout()
        fig.suptitle("倾向得分匹配分布", fontsize=self.config.title_fontsize + 1, y=1.02)

        self._save(fig, output_name)
        return fig

    # ── Chart 12: Time Series (generic) ───────────────────────────────────────

    def plot_timeseries(
        self,
        df: pd.DataFrame,
        date_col: str,
        value_col: str,
        group_col: str | None = None,
        output_name: str = "timeseries",
        figsize: tuple[float, float] = (9, 4.5),
    ) -> "plt.Figure":
        """Generic time series plot with optional grouping."""
        import seaborn as sns

        fig, ax = self._new_fig(figsize)
        df_ = df.copy()
        df_[date_col] = pd.to_datetime(df_[date_col])
        df_ = df_.sort_values(date_col)

        if group_col:
            # Pre-aggregate: mean per (date, group) to avoid seaborn auto-aggregation
            # (which uses hue_stats_estimator and can produce unexpected confidence intervals)
            agg_col = df_.groupby([date_col, group_col])[value_col].mean().reset_index()
            sns.lineplot(data=agg_col, x=date_col, y=value_col, hue=group_col, ax=ax,
                         palette=self.config.color_palette, linewidth=1.2,
                         errorbar=None)   # no CI bands — already aggregated
        else:
            # Pre-aggregate: mean per date
            agg_col = df_.groupby(date_col)[value_col].mean().reset_index()
            sns.lineplot(data=agg_col, x=date_col, y=value_col, ax=ax,
                         color="steelblue", linewidth=1.5,
                         errorbar=None)

        ax.set_xlabel("日期", fontsize=self.config.label_fontsize)
        ax.set_ylabel(value_col, fontsize=self.config.label_fontsize)
        ax.set_title("时序图", fontsize=self.config.title_fontsize, pad=12)
        ax.grid(True, alpha=self.config.grid_alpha)
        sns.despine(ax=ax)
        fig.autofmt_xdate()

        self._save(fig, output_name)
        return fig

    # ── Additional 8 chart types (V2 extensions) ───────────────────────────────

    def plot_event_study(
        self,
        df: pd.DataFrame,
        coef_col: str = "coef",
        se_col: str = "se",
        period_col: str = "period",
        ref_period: int = -1,
        ci_level: float = 0.95,
        output_name: str = "event_study",
        **kwargs,
    ) -> "plt.Figure":
        """
        Event-study plot: lead/lag coefficients around a treatment event.

        Parameters
        ----------
        df : DataFrame with one row per event-time period
        coef_col : column with point estimates
        se_col : column with standard errors
        period_col : column with event-time integers (..., -2, -1, 0, 1, 2, ...)
        ref_period : omitted reference period (drawn as a dashed vertical line)
        ci_level : confidence level (default 0.95)
        """
        df = df.sort_values(period_col).reset_index(drop=True)
        z = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(ci_level, 1.96)
        df["lo"] = df[coef_col] - z * df[se_col]
        df["hi"] = df[coef_col] + z * df[se_col]

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.fill_between(df[period_col], df["lo"], df["hi"], alpha=0.2,
                        color=self._palette(0), label=f"{int(ci_level*100)}% CI")
        ax.plot(df[period_col], df[coef_col], "o-", color=self._palette(0),
                linewidth=2, markersize=6, label="Point estimate")
        ax.axhline(0, color="grey", linewidth=0.7, linestyle="--")
        ax.axvline(ref_period, color="red", linewidth=0.7, linestyle=":",
                   label=f"Reference period = {ref_period}")
        ax.set_xlabel("Event time (relative to treatment)")
        ax.set_ylabel("Coefficient")
        ax.set_title("Event Study")
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_did_scatter(
        self,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        treat_col: str,
        time_col: str,
        output_name: str = "did_scatter",
        **kwargs,
    ) -> "plt.Figure":
        """
        DID scatter: outcome vs time, treatment vs control groups, with two
        fitted lines drawn pre/post the treatment cut-off.
        """
        treat_period = df[time_col].median()
        pre = df[df[time_col] <= treat_period]
        post = df[df[time_col] > treat_period]

        fig, ax = plt.subplots(figsize=(8, 5))
        for label, subset, marker, color in [
            ("Control", df[df[treat_col] == 0], "o", self._palette(1)),
            ("Treated", df[df[treat_col] == 1], "s", self._palette(0)),
        ]:
            ax.scatter(subset[time_col], subset[y_col], alpha=0.5, s=18,
                       marker=marker, color=color, label=label)

        for label, color in [("Control", self._palette(1)), ("Treated", self._palette(0))]:
            for region, marker in [(pre, "pre"), (post, "post")]:
                sub = region[region[treat_col] == (1 if label == "Treated" else 0)]
                if len(sub) > 1:
                    coef = np.polyfit(sub[time_col], sub[y_col], 1)
                    xs = np.linspace(sub[time_col].min(), sub[time_col].max(), 50)
                    ax.plot(xs, np.polyval(coef, xs), "--", color=color, alpha=0.7,
                            linewidth=1.5)

        ax.axvline(treat_period, color="red", linestyle=":", linewidth=0.8,
                   label=f"Treatment onset ≈ {treat_period}")
        ax.set_xlabel(time_col)
        ax.set_ylabel(y_col)
        ax.set_title("Difference-in-Differences Scatter")
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_heterogeneity_forest(
        self,
        results: dict[str, tuple[float, float]],
        output_name: str = "heterogeneity_forest",
        **kwargs,
    ) -> "plt.Figure":
        """
        Forest plot of subgroup treatment effects.

        Parameters
        ----------
        results : mapping {subgroup_name: (coef, se)}
        """
        names = list(results.keys())
        coefs = np.array([results[k][0] for k in names])
        ses = np.array([results[k][1] for k in names])
        z = 1.96
        lo, hi = coefs - z * ses, coefs + z * ses
        y = np.arange(len(names))[::-1]

        fig, ax = plt.subplots(figsize=(8, max(3, 0.45 * len(names))))
        ax.errorbar(coefs, y, xerr=[coefs - lo, hi - coefs], fmt="o",
                    color=self._palette(0), ecolor="grey", capsize=3,
                    markersize=6, linewidth=1.5)
        ax.axvline(0, color="black", linewidth=0.7, linestyle="--")
        ax.set_yticks(y)
        ax.set_yticklabels(names)
        ax.set_xlabel("Treatment effect (95% CI)")
        ax.set_title("Heterogeneity — Forest Plot")
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_sensitivity_tornado(
        self,
        baseline: float,
        perturbations: dict[str, tuple[float, float]],
        output_name: str = "sensitivity_tornado",
        **kwargs,
    ) -> "plt.Figure":
        """
        Sensitivity tornado: one row per assumption, two horizontal bars for the
        resulting estimate (low / high), sorted by absolute swing.
        """
        items = sorted(perturbations.items(),
                       key=lambda kv: abs(kv[1][1] - kv[1][0]), reverse=True)
        names = [k for k, _ in items]
        y = np.arange(len(names))[::-1]
        lows = np.array([v[0] for _, v in items])
        highs = np.array([v[1] for _, v in items])

        fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(names))))
        for i, (lo, hi) in enumerate(zip(lows, highs)):
            ax.barh(y[i], hi - lo, left=lo, color=self._palette(0), alpha=0.7,
                    edgecolor="black", linewidth=0.4)
        ax.axvline(baseline, color="red", linewidth=0.8, linestyle="--",
                   label=f"Baseline = {baseline:.3f}")
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=9)
        ax.set_xlabel("Estimate")
        ax.set_title("Sensitivity Analysis (Tornado)")
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_coefficient_evolution(
        self,
        df: pd.DataFrame,
        time_col: str,
        coef_col: str,
        se_col: str,
        output_name: str = "coef_evolution",
        **kwargs,
    ) -> "plt.Figure":
        """
        Plot a coefficient's estimate ± 1.96 SE over time (rolling regressions,
        subsample splits, etc.).
        """
        df = df.sort_values(time_col)
        z = 1.96
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.fill_between(df[time_col],
                        df[coef_col] - z * df[se_col],
                        df[coef_col] + z * df[se_col],
                        alpha=0.2, color=self._palette(0), label="95% CI")
        ax.plot(df[time_col], df[coef_col], "o-", color=self._palette(0),
                linewidth=2, label="Estimate")
        ax.axhline(0, color="grey", linestyle="--", linewidth=0.7)
        ax.set_xlabel(time_col)
        ax.set_ylabel(coef_col)
        ax.set_title("Coefficient Evolution Over Time")
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_dose_response(
        self,
        df: pd.DataFrame,
        dose_col: str,
        outcome_col: str,
        bin_col: str | None = None,
        n_bins: int = 10,
        output_name: str = "dose_response",
        **kwargs,
    ) -> "plt.Figure":
        """
        Dose-response curve: bin a continuous treatment 'dose' and plot the
        mean outcome ± SE per bin. If ``bin_col`` is supplied, that is used
        directly; otherwise equal-width bins are derived from ``dose_col``.
        """
        work = df.copy()
        if bin_col is None:
            work["_bin"] = pd.cut(work[dose_col], bins=n_bins, include_lowest=True)
            bin_col = "_bin"

        grouped = work.groupby(bin_col, observed=True)[outcome_col].agg(["mean", "sem", "count"])
        grouped = grouped.dropna()
        x = np.arange(len(grouped))

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.errorbar(x, grouped["mean"], yerr=1.96 * grouped["sem"], fmt="o-",
                    color=self._palette(0), capsize=3, linewidth=1.5,
                    markersize=6)
        ax.set_xticks(x)
        ax.set_xticklabels([str(idx) for idx in grouped.index], rotation=30, ha="right",
                           fontsize=8)
        ax.set_xlabel(f"Bins of {dose_col}")
        ax.set_ylabel(f"Mean {outcome_col} (95% CI)")
        ax.set_title("Dose-Response Curve")
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_balance_table(
        self,
        before: pd.Series,
        after: pd.Series,
        var_names: list[str] | None = None,
        output_name: str = "balance_table",
        **kwargs,
    ) -> "plt.Figure":
        """
        Visualise standardised mean differences pre- and post-matching
        (or pre- and post-weighting). Horizontal bars per variable.
        """
        if var_names is None:
            var_names = list(before.index)
        before = before.reindex(var_names)
        after = after.reindex(var_names)
        y = np.arange(len(var_names))[::-1]

        fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(var_names))))
        ax.barh(y - 0.2, before.values, height=0.4, color=self._palette(1),
                label="Before", alpha=0.8)
        ax.barh(y + 0.2, after.values, height=0.4, color=self._palette(0),
                label="After", alpha=0.8)
        ax.axvline(0, color="black", linewidth=0.7)
        ax.axvline(0.1, color="grey", linewidth=0.5, linestyle="--",
                   label="|SMD| = 0.1 threshold")
        ax.axvline(-0.1, color="grey", linewidth=0.5, linestyle="--")
        ax.set_yticks(y)
        ax.set_yticklabels(var_names, fontsize=9)
        ax.set_xlabel("Standardised mean difference")
        ax.set_title("Covariate Balance — Before / After Matching")
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    def plot_event_timeline(
        self,
        events: list[tuple[str, str]],
        output_name: str = "event_timeline",
        **kwargs,
    ) -> "plt.Figure":
        """
        Gantt-style timeline of research milestones / regulatory events.

        Parameters
        ----------
        events : list of (label, ISO-date) or (label, 'YYYY-MM-DD')
        """
        from datetime import datetime
        parsed: list[tuple[str, datetime]] = []
        for label, date_str in events:
            try:
                parsed.append((label, datetime.fromisoformat(date_str)))
            except ValueError:
                continue
        if not parsed:
            raise ValueError("plot_event_timeline: no parseable events")
        parsed.sort(key=lambda x: x[1])
        y = np.arange(len(parsed))[::-1]
        fig, ax = plt.subplots(figsize=(9, max(3, 0.5 * len(parsed))))
        for i, (label, dt) in enumerate(parsed):
            ax.scatter(dt, y[i], s=80, color=self._palette(0), zorder=3)
            ax.annotate(label, (dt, y[i]), xytext=(6, 0), textcoords="offset points",
                        fontsize=9, va="center")
        ax.set_yticks([])
        ax.set_yticklabels([])
        ax.set_xlabel("Date")
        ax.set_title("Event Timeline")
        ax.grid(axis="x", linestyle=":", alpha=0.4)
        fig.tight_layout()
        self._save(fig, output_name)
        return fig

    # ── Generic wrapper ──────────────────────────────────────────────────────────

    def plot(
        self,
        chart_type: str,
        df: pd.DataFrame,
        output_name: str,
        **kwargs,
    ) -> "plt.Figure":
        """
        Generic plot dispatcher.

        chart_type: one of the keys in CHART_PRESETS
        """
        dispatch = {
            "parallel_trends": self.plot_parallel_trends,
            "robustness_summary": self.plot_robustness_summary,
            "factor_returns": self.plot_factor_returns,
            "correlation_heatmap": self.plot_correlation_matrix,
            "residual_diagnostics": self.plot_residual_diagnostics,
            "heterogeneity": self.plot_heterogeneity,
            "rdd_plot": self.plot_rdd,
            "cumulative_effect": self.plot_cumulative_effect,
            "placebo_distribution": self.plot_placebo_distribution,
            "synthetic_control": self.plot_synthetic_control,
            "psm_distribution": self.plot_psm_distribution,
            "timeseries": self.plot_timeseries,
            # V2 extensions
            "event_study": self.plot_event_study,
            "did_scatter": self.plot_did_scatter,
            "heterogeneity_forest": self.plot_heterogeneity_forest,
            "sensitivity_tornado": self.plot_sensitivity_tornado,
            "coef_evolution": self.plot_coefficient_evolution,
            "dose_response": self.plot_dose_response,
            "balance_table": self.plot_balance_table,
            "event_timeline": self.plot_event_timeline,
        }

        runner = dispatch.get(chart_type)
        if runner is None:
            raise ValueError(f"Unknown chart type: {chart_type}. "
                           f"Available: {list(dispatch.keys())}")

        return runner(df, output_name=output_name, **kwargs)
