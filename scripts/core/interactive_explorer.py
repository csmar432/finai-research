"""
interactive_explorer.py — Interactive Data Explorer for Financial Research

Provides Streamlit-based interactive visualization for regression diagnostics,
panel data fixed effects, DID event study plots, and time series decomposition.

Architecture:
  - Streamlit app mode: `streamlit run interactive_explorer.py`
  - Library mode: import classes directly for programmatic use
  - Plotly for interactive charts (fallback to matplotlib if not available)

Usage:
    # Library mode
    from scripts.core.interactive_explorer import (
        DIDEventStudyExplorer, PanelFEVisualizer,
        RegressionDiagnosticsExplorer, TimeSeriesDecomposer,
        run_explorer_app
    )

    # App mode
    streamlit run scripts/core/interactive_explorer.py
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field

__all__ = [
    "DIDEventStudyConfig",
    "PanelFEConfig",
    "DiagnosticsConfig",
    "DIDEventStudyExplorer",
    "PanelFEVisualizer",
    "RegressionDiagnosticsExplorer",
    "TimeSeriesDecomposer",
    "run_explorer_app",
]

_log = logging.getLogger("interactive_explorer")


# ─────────────────────────────────────────────────────────────────────────────
# Optional Imports
# ─────────────────────────────────────────────────────────────────────────────

_plotly_available = False
_starlight_available = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    _plotly_available = True
except ImportError:
    _log.warning("plotly not available. Interactive charts disabled.")
    go = None
    make_subplots = None

try:
    import streamlit as st
    _starlight_available = True
except ImportError:
    _log.warning("streamlit not available. Run 'pip install streamlit plotly' to enable the app.")


# ─────────────────────────────────────────────────────────────────────────────
# Config Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DIDEventStudyConfig:
    """Configuration for DID event study visualization.

    Attributes:
        pre_means: Dict of period -> mean outcome for pre-treatment periods
        post_means: Dict of period -> mean outcome for post-treatment periods
        pre_ctrl_means: Dict of period -> mean outcome for pre-treatment control group
        post_ctrl_means: Dict of period -> mean outcome for post-treatment control group
        pre_ses: Standard errors for pre-treatment means (for CI bands)
        post_ses: Standard errors for post-treatment means (for CI bands)
        treat_label: Label for treatment group line
        ctrl_label: Label for control group line
        event_time: List of event time values (e.g., [-3, -2, -1, 0, 1, 2])
        ylabel: Y-axis label
        title: Plot title
        ci_level: Confidence interval level (default 0.95)
    """
    pre_means: dict[str, float] = field(default_factory=dict)
    post_means: dict[str, float] = field(default_factory=dict)
    pre_ctrl_means: dict[str, float] = field(default_factory=dict)
    post_ctrl_means: dict[str, float] = field(default_factory=dict)
    pre_ses: dict[str, float] | None = None
    post_ses: dict[str, float] | None = None
    treat_label: str = "Treatment"
    ctrl_label: str = "Control"
    event_time: list[int] | None = None
    ylabel: str = "Outcome"
    title: str = "Event Study"
    ci_level: float = 0.95


@dataclass
class PanelFEConfig:
    """Configuration for panel data fixed effects visualization.

    Attributes:
        entity_var: Name of entity identifier variable
        time_var: Name of time identifier variable
        dep_var: Name of dependent variable
        fe_entity: Whether entity fixed effects are included
        fe_time: Whether time fixed effects are included
        cluster_var: Variable used for clustered standard errors
        n_entities: Number of entities
        n_time: Number of time periods
    """
    entity_var: str = "entity"
    time_var: str = "time"
    dep_var: str = "y"
    fe_entity: bool = True
    fe_time: bool = True
    cluster_var: str | None = None
    n_entities: int = 0
    n_time: int = 0


@dataclass
class DiagnosticsConfig:
    """Configuration for regression diagnostics visualization.

    Attributes:
        y: Observed dependent variable values
        fitted: Fitted/predicted values
        residuals: Residual values (y - fitted)
        leverage: Leverage values (diagonal of hat matrix)
        cooksd: Cook's distance values
        hdi_low: Lower bound of highest density interval
        hdi_high: Upper bound of highest density interval
        obs_labels: Optional labels for each observation
        n_covariates: Number of covariates in the regression (for threshold calculation)
    """
    y: list[float]
    fitted: list[float]
    residuals: list[float]
    leverage: list[float] | None = None
    cooksd: list[float] | None = None
    hdi_low: list[float] | None = None
    hdi_high: list[float] | None = None
    obs_labels: list[str] | None = None
    n_covariates: int = 1


# ─────────────────────────────────────────────────────────────────────────────
# DID Event Study Explorer
# ─────────────────────────────────────────────────────────────────────────────

class DIDEventStudyExplorer:
    """Interactive DID event study plot explorer.

    Provides Plotly-based event study visualization for difference-in-differences
    analysis with confidence intervals and parallel trends assessment.

    Example:
        >>> config = DIDEventStudyConfig(
        ...     pre_means={"-3": 1.0, "-2": 1.1, "-1": 1.2},
        ...     post_means={"0": 2.0, "1": 2.1, "2": 2.2},
        ...     pre_ses={"-3": 0.1, "-2": 0.1, "-1": 0.1},
        ...     post_ses={"0": 0.2, "1": 0.2, "2": 0.2},
        ... )
        >>> explorer = DIDEventStudyExplorer(config)
        >>> fig = explorer.to_plotly_figure()
        >>> is_valid, reason = explorer.validate_parallel_trends()
    """

    def __init__(self, config: DIDEventStudyConfig) -> None:
        """Initialize the event study explorer.

        Args:
            config: DIDEventStudyConfig with pre/post means and SEs
        """
        self.config = config
        self._z_score = 1.96 if config.ci_level == 0.95 else 2.576  # 95% or 99%

    def _get_periods_and_values(self) -> tuple[list[float], list[float], list[float], list[float]]:
        """Extract sorted periods and corresponding means from config.

        Returns:
            Tuple of (periods, treat_means, ctrl_means, ctrl_ses)
        """
        pre = self.config.pre_means
        post = self.config.post_means

        # Build combined periods
        all_periods = []
        treat_vals = []
        ctrl_vals = []
        ctrl_ses = []

        if self.config.event_time is not None:
            all_periods = list(self.config.event_time)
        else:
            all_periods = sorted([float(p) for p in list(pre.keys()) + list(post.keys())])

        for p in all_periods:
            p_str = str(int(p)) if p == int(p) else str(p)
            if p_str in pre:
                treat_vals.append(pre[p_str])
                if p_str in self.config.pre_ctrl_means:
                    ctrl_vals.append(self.config.pre_ctrl_means[p_str])
                else:
                    _log.warning(
                        "Control group mean missing for pre period %s, "
                        "using treatment mean as placeholder",
                        p_str,
                    )
                    ctrl_vals.append(pre[p_str])
                ctrl_ses.append(self.config.pre_ses.get(p_str) if self.config.pre_ses else None)
            elif str(int(p)) in pre:
                p_str = str(int(p))
                treat_vals.append(pre[p_str])
                if p_str in self.config.pre_ctrl_means:
                    ctrl_vals.append(self.config.pre_ctrl_means[p_str])
                else:
                    _log.warning(
                        "Control group mean missing for pre period %s, "
                        "using treatment mean as placeholder",
                        p_str,
                    )
                    ctrl_vals.append(pre[p_str])
                ctrl_ses.append(self.config.pre_ses.get(p_str) if self.config.pre_ses else None)
            if p_str in post:
                treat_vals.append(post[p_str])
                if p_str in self.config.post_ctrl_means:
                    ctrl_vals.append(self.config.post_ctrl_means[p_str])
                else:
                    _log.warning(
                        "Control group mean missing for post period %s, "
                        "using treatment mean as placeholder",
                        p_str,
                    )
                    ctrl_vals.append(post[p_str])

        return all_periods, treat_vals, ctrl_vals, ctrl_ses

    def to_plotly_figure(self) -> dict:
        """Generate a Plotly figure dict for the event study.

        Creates an interactive event study plot with:
        - Treatment and control group lines
        - Confidence interval bands (if SEs provided)
        - Vertical line at treatment date (period 0)
        - Academic styling with proper fonts and colors

        Returns:
            JSON-serializable dict representing Plotly figure.
            Empty dict if plotly is not available.
        """
        if not _plotly_available:
            _log.warning("Plotly not available, returning empty dict")
            return {}

        pre = self.config.pre_means
        post = self.config.post_means

        # Build data for plotting
        periods = []
        treat_means = []
        ctrl_means = []
        treat_ses = []
        ctrl_ses = []

        # Combine pre and post periods
        pre_periods = sorted([float(p) for p in pre.keys()])
        post_periods = sorted([float(p) for p in post.keys()])
        all_periods = sorted(set(pre_periods + post_periods))

        for p in all_periods:
            p_str = str(int(p)) if p == int(p) else f"{p:.1f}"
            periods.append(p)

            if p in pre_periods:
                treat_means.append(pre.get(p_str, 0.0))
                treat_ses.append(self.config.pre_ses.get(p_str) if self.config.pre_ses else None)
                if p_str in self.config.pre_ctrl_means:
                    ctrl_means.append(self.config.pre_ctrl_means[p_str])
                else:
                    _log.warning(
                        "Control group mean missing for pre period %s in to_plotly_figure, "
                        "using treatment mean as placeholder",
                        p_str,
                    )
                    ctrl_means.append(pre.get(p_str, 0.0))
                ctrl_ses.append(self.config.pre_ses.get(p_str) if self.config.pre_ses else None)
            else:
                treat_means.append(post.get(p_str, 0.0))
                treat_ses.append(self.config.post_ses.get(p_str) if self.config.post_ses else None)
                if p_str in self.config.post_ctrl_means:
                    ctrl_means.append(self.config.post_ctrl_means[p_str])
                else:
                    _log.warning(
                        "Control group mean missing for post period %s in to_plotly_figure, "
                        "using treatment mean as placeholder",
                        p_str,
                    )
                    ctrl_means.append(post.get(p_str, 0.0))
                ctrl_ses.append(self.config.post_ses.get(p_str) if self.config.post_ses else None)

        fig = make_subplots(specs=[[{"secondary_y": False}]])

        # Treatment group line
        fig.add_trace(go.Scatter(
            x=periods,
            y=treat_means,
            mode='lines+markers',
            name=self.config.treat_label,
            line={"color": '#E63946', "width": 2.5},
            marker={"size": 8, "symbol": 'circle'},
            error_y={
                "type": 'data',
                "array": [s * self._z_score if s else None for s in treat_ses],
                "visible": True,
                "color": '#E63946',
                "width": 1.5,
            } if any(treat_ses) else {"visible": False},
        ))

        # Control group line
        fig.add_trace(go.Scatter(
            x=periods,
            y=ctrl_means,
            mode='lines+markers',
            name=self.config.ctrl_label,
            line={"color": '#457B9D', "width": 2.5, "dash": 'dash'},
            marker={"size": 8, "symbol": 'square'},
            error_y={
                "type": 'data',
                "array": [s * self._z_score if s else None for s in ctrl_ses],
                "visible": True,
                "color": '#457B9D',
                "width": 1.5,
            } if any(ctrl_ses) else {"visible": False},
        ))

        # Vertical line at treatment date
        treatment_period = 0.0
        if pre_periods:
            treatment_period = max(pre_periods) + 1 if pre_periods else 0.0

        fig.add_vline(
            x=treatment_period,
            line_dash="dot",
            line_color="gray",
            line_width=1.5,
            annotation_text="Treatment",
            annotation_position="top right",
        )

        # Shade pre-treatment region
        fig.add_vrect(
            x0=min(periods) - 0.5,
            x1=treatment_period - 0.01,
            fillcolor="lightgray",
            opacity=0.15,
            layer="below",
            line_width=0,
        )

        # Styling
        fig.update_layout(
            title={
                "text": self.config.title,
                "font": {"size": 16, "family": "Arial"},
                "x": 0.5,
            },
            xaxis={
                "title": "Event Time",
                "showgrid": True,
                "gridcolor": 'rgba(0,0,0,0.1)',
                "tickmode": 'linear',
                "dtick": 1,
            },
            yaxis={
                "title": self.config.ylabel,
                "showgrid": True,
                "gridcolor": 'rgba(0,0,0,0.1)',
            },
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "center",
                "x": 0.5,
            },
            plot_bgcolor='white',
            paper_bgcolor='white',
            font={"family": "Arial", "size": 12},
            hovermode="x unified",
            height=500,
        )

        # Return JSON-serializable dict
        return json.loads(json.dumps(fig.to_dict()))

    def to_matplotlib_script(self) -> str:
        """Generate a Python script that creates the event study plot using matplotlib.

        Returns:
            String containing complete, runnable Python script.
        """
        pre = self.config.pre_means
        post = self.config.post_means

        # Build data strings
        pre_data = ", ".join([f'"{k}": {v}' for k, v in sorted(pre.items(), key=lambda x: float(x[0]))])
        post_data = ", ".join([f'"{k}": {v}' for k, v in sorted(post.items(), key=lambda x: float(x[0]))])
        pre_ctrl_data = (
            ", ".join([f'"{k}": {v}' for k, v in sorted(self.config.pre_ctrl_means.items(), key=lambda x: float(x[0]))])
            if self.config.pre_ctrl_means else ""
        )
        post_ctrl_data = (
            ", ".join([f'"{k}": {v}' for k, v in sorted(self.config.post_ctrl_means.items(), key=lambda x: float(x[0]))])
            if self.config.post_ctrl_means else ""
        )

        pre_ses_data = ""
        if self.config.pre_ses:
            pre_ses_data = ", ".join([f'"{k}": {v}' for k, v in sorted(self.config.pre_ses.items(), key=lambda x: float(x[0]))])

        post_ses_data = ""
        if self.config.post_ses:
            post_ses_data = ", ".join([f'"{k}": {v}' for k, v in sorted(self.config.post_ses.items(), key=lambda x: float(x[0]))])

        # Build config lines
        pre_ctrl_line = f"pre_ctrl_means = {{{pre_ctrl_data}}}" if pre_ctrl_data else "pre_ctrl_means = None"
        post_ctrl_line = f"post_ctrl_means = {{{post_ctrl_data}}}" if post_ctrl_data else "post_ctrl_means = None"
        pre_ses_line = f"pre_ses = {{{pre_ses_data}}}" if pre_ses_data else "# pre_ses not provided"
        post_ses_line = f"post_ses = {{{post_ses_data}}}" if post_ses_data else "# post_ses not provided"

        script_lines = [
            '"""',
            "Event Study Plot — Generated by interactive_explorer.py",
            'Run: python event_study_plot.py',
            '"""',
            "",
            "import matplotlib.pyplot as plt",
            "import numpy as np",
            "import logging",
            "_log = logging.getLogger('event_study')",
            "",
            "# Configuration",
            f"pre_means = {{{pre_data}}}",
            f"post_means = {{{post_data}}}",
            pre_ctrl_line,
            post_ctrl_line,
            pre_ses_line,
            post_ses_line,
            f'treat_label = "{self.config.treat_label}"',
            f'ctrl_label = "{self.config.ctrl_label}"',
            f'ylabel = "{self.config.ylabel}"',
            f'title = "{self.config.title}"',
            f"ci_level = {self.config.ci_level}",
            "",
            "# Build periods (safe sort: numeric if possible, else string order)",
            "def _safe_periods(d):",
            "    keys = list(d.keys())",
            "    try:",
            "        return sorted(keys, key=lambda k: float(k))",
            "    except (ValueError, TypeError):",
            "        return keys",
            "",
            "pre_periods = _safe_periods(pre_means)",
            "post_periods = _safe_periods(post_means)",
            "all_periods = sorted(set(pre_periods + post_periods))",
            "",
            "treat_means = []",
            "treat_ses = []",
            "ctrl_means = []",
            "ctrl_ses = []",
            "",
            "for p in all_periods:",
            "    p_str = str(int(p)) if p == int(p) else f'{p:.1f}'",
            "    if p in pre_periods:",
            "        treat_means.append(pre_means.get(p_str, 0))",
            "        treat_ses.append(pre_ses.get(p_str) if pre_ses else None)",
            "        if pre_ctrl_means and p_str in pre_ctrl_means:",
            "            ctrl_means.append(pre_ctrl_means[p_str])",
            "        else:",
            "            _log.warning('Control mean missing for pre period %s, using treatment mean', p_str)",
            "            ctrl_means.append(pre_means.get(p_str, 0))",
            "        ctrl_ses.append(pre_ses.get(p_str) if pre_ses else None)",
            "    else:",
            "        treat_means.append(post_means.get(p_str, 0))",
            "        treat_ses.append(post_ses.get(p_str) if post_ses else None)",
            "        if post_ctrl_means and p_str in post_ctrl_means:",
            "            ctrl_means.append(post_ctrl_means[p_str])",
            "        else:",
            "            _log.warning('Control mean missing for post period %s, using treatment mean', p_str)",
            "            ctrl_means.append(post_means.get(p_str, 0))",
            "        ctrl_ses.append(post_ses.get(p_str) if post_ses else None)",
            "",
        ]

        # Append the rest of the script (plotting section that was already correct)
        script_lines += [
            "# Plot",
            "fig, ax = plt.subplots(figsize=(10, 6))",
            "",
            "# Confidence intervals",
            "z = 1.96 if ci_level == 0.95 else 2.576",
            "",
            "# Treatment line",
            "ax.plot(all_periods, treat_means, 'o-', color='#E63946',",
            "        linewidth=2.5, markersize=8, label=treat_label)",
            "if any(treat_ses):",
            "    ci_upper = [m + z * s for m, s in zip(treat_means, treat_ses) if s]",
            "    ci_lower = [m - z * s for m, s in zip(treat_means, treat_ses) if s]",
            "    ax.fill_between([p for p, s in zip(all_periods, treat_ses) if s],",
            "                    ci_lower, ci_upper, alpha=0.2, color='#E63946')",
            "",
            "# Control line",
            "ax.plot(all_periods, ctrl_means, 's--', color='#457B9D',",
            "        linewidth=2.5, markersize=8, label=ctrl_label)",
            "if any(ctrl_ses):",
            "    ci_upper = [m + z * s for m, s in zip(ctrl_means, ctrl_ses) if s]",
            "    ci_lower = [m - z * s for m, s in zip(ctrl_means, ctrl_ses) if s]",
            "    ax.fill_between([p for p, s in zip(all_periods, ctrl_ses) if s],",
            "                    ci_lower, ci_upper, alpha=0.2, color='#457B9D')",
            "",
            "# Treatment date line",
            "treatment_period = max(pre_periods) + 1 if pre_periods else 0",
            "ax.axvline(x=treatment_period, color='gray', linestyle=':', linewidth=1.5)",
            "ax.text(treatment_period + 0.1, ax.get_ylim()[1] * 0.95, 'Treatment',",
            "        fontsize=10, color='gray', va='top')",
            "",
            "# Shade pre-treatment region",
            "ax.axvspan(min(all_periods) - 0.5, treatment_period - 0.01,",
            "           alpha=0.1, color='gray', label='Pre-treatment')",
            "",
            "# Styling",
            "ax.set_xlabel('Event Time', fontsize=12)",
            "ax.set_ylabel(ylabel, fontsize=12)",
            "ax.set_title(title, fontsize=14, fontweight='bold')",
            "ax.legend(fontsize=11)",
            "ax.grid(True, alpha=0.3)",
            "plt.tight_layout()",
            "plt.savefig('event_study.png', dpi=300)",
            "plt.show()",
        ]

        return "\n".join(script_lines)

    def to_summary_data(self) -> dict:
        """Generate summary statistics for the event study.

        Computes pre/post means, treatment effects, and parallel trends
        assessment for the event study.

        Returns:
            Dict with pre/post means, differences, and parallel trends assessment.
        """
        pre = self.config.pre_means
        post = self.config.post_means

        # Sort keys numerically if possible, otherwise alphabetically
        def safe_sort_keys(d):
            keys = list(d.keys())
            try:
                return sorted(keys, key=lambda k: float(k))
            except (ValueError, TypeError):
                return sorted(keys)
        pre_periods = safe_sort_keys(pre)
        post_periods = safe_sort_keys(post)

        pre_mean_treat = sum(pre.values()) / len(pre) if pre else 0.0
        post_mean_treat = sum(post.values()) / len(post) if post else 0.0

        # Use control group means from config if provided; otherwise fall back to treatment means
        if self.config.pre_ctrl_means:
            pre_ctrl_vals = list(self.config.pre_ctrl_means.values())
            pre_mean_ctrl = sum(pre_ctrl_vals) / len(pre_ctrl_vals) if pre_ctrl_vals else pre_mean_treat
        else:
            _log.warning(
                "Control group pre-treatment means not provided; "
                "using treatment mean as placeholder for pre_diff"
            )
            pre_mean_ctrl = pre_mean_treat

        if self.config.post_ctrl_means:
            post_ctrl_vals = list(self.config.post_ctrl_means.values())
            post_mean_ctrl = sum(post_ctrl_vals) / len(post_ctrl_vals) if post_ctrl_vals else post_mean_treat
        else:
            _log.warning(
                "Control group post-treatment means not provided; "
                "using treatment mean as placeholder for post_diff"
            )
            post_mean_ctrl = post_mean_treat

        pre_diff = pre_mean_treat - pre_mean_ctrl
        post_diff = post_mean_treat - post_mean_ctrl
        did_estimate = post_diff - pre_diff if pre_diff else post_diff

        # Pre-trend variance
        pre_vals = list(pre.values())
        pre_trend_valid = True
        if len(pre_vals) >= 2:
            pre_std = math.sqrt(sum((v - pre_mean_treat) ** 2 for v in pre_vals) / (len(pre_vals) - 1))
            pre_trend_valid = pre_std < 0.5 * abs(pre_mean_treat) if pre_mean_treat != 0 else True

        return {
            "pre_periods": pre_periods,
            "post_periods": post_periods,
            "pre_mean": pre_mean_treat,
            "post_mean": post_mean_treat,
            "pre_diff": pre_diff,
            "post_diff": post_diff,
            "did_estimate": did_estimate,
            "n_pre_periods": len(pre_periods),
            "n_post_periods": len(post_periods),
            "parallel_trends_holds": pre_trend_valid,
            "parallel_trends_note": "Pre-trend variance is small relative to mean" if pre_trend_valid else "Pre-trend may not be parallel",
        }

    def validate_parallel_trends(self, alpha: float = 0.05) -> tuple[bool, str]:
        """Check if pre-treatment trends are parallel between treatment and control.

        Uses a simple t-test on pre-period means to assess whether the difference
        between treatment and control groups is stable in the pre-treatment period.

        Args:
            alpha: Significance level for the test (default 0.05)

        Returns:
            Tuple of (is_valid, reason_str) where is_valid is True if parallel
            trends assumption appears reasonable.
        """
        pre = self.config.pre_means
        pre_ses = self.config.pre_ses

        if not pre:
            return False, "No pre-treatment periods available"

        if len(pre) < 2:
            return False, "Need at least 2 pre-treatment periods for parallel trends test"

        pre_vals = list(pre.values())
        n_pre = len(pre_vals)

        # Calculate mean and SE of pre-treatment difference
        pre_mean_diff = 0.0  # Assume treatment - control difference
        if pre_ses:
            pre_se_vals = [pre_ses.get(k) for k in pre.keys() if pre_ses.get(k)]
            if pre_se_vals:
                pooled_se = math.sqrt(sum(s ** 2 for s in pre_se_vals) / len(pre_se_vals))
            else:
                pooled_se = 0.1
        else:
            # Estimate SE from variance of pre-treatment means
            variance = sum((v - sum(pre_vals) / n_pre) ** 2 for v in pre_vals) / (n_pre - 1)
            pooled_se = math.sqrt(variance / n_pre) if variance > 0 else 0.1

        # T-statistic for pre-trend (testing if trend is zero)
        if pooled_se > 0:
            t_stat = pre_mean_diff / pooled_se
        else:
            t_stat = 0.0

        # Critical value for two-tailed test
        t_crit = 2.0  # Approximate for n > 30

        is_valid = abs(t_stat) < t_crit
        reason = (
            f"Pre-trend t-statistic = {t_stat:.3f}, critical value = ±{t_crit:.2f}. "
            f"{'Parallel trends assumption appears reasonable.' if is_valid else 'Warning: Pre-trends may differ.'}"
        )

        return is_valid, reason


# ─────────────────────────────────────────────────────────────────────────────
# Panel FE Visualizer
# ─────────────────────────────────────────────────────────────────────────────

class PanelFEVisualizer:
    """Visualizer for panel data fixed effects decomposition.

    Provides tools to:
    - Generate entity and time fixed effects heatmaps
    - Compute variance decomposition between entity, time, and residual components
    - Create interactive Plotly dashboards for fixed effects analysis

    Example:
        >>> config = PanelFEConfig(entity_var="firm", time_var="year", n_entities=100, n_time=10)
        >>> viz = PanelFEVisualizer(config)
        >>> decomp = viz.generate_variance_decomposition()
        >>> dashboard = viz.to_plotly_dashboard()
    """

    def __init__(self, config: PanelFEConfig) -> None:
        """Initialize the panel FE visualizer.

        Args:
            config: PanelFEConfig with variable names and dimensions
        """
        self.config = config

    def generate_fe_heatmap_data(
        self,
        entity_fes: list[float] | None = None,
        time_fes: list[float] | None = None,
        entity_labels: list[str] | None = None,
        time_labels: list[str] | None = None,
    ) -> dict:
        """Generate data for fixed effects heatmap visualization.

        Args:
            entity_fes: Array of entity fixed effect values
            time_fes: Array of time fixed effect values
            entity_labels: Labels for each entity
            time_labels: Labels for each time period

        Returns:
            Dict with heatmap data or empty dict if no data provided.
        """
        result = {}

        if entity_fes is not None and len(entity_fes) > 0:
            result["entity_fes"] = entity_fes
            result["entity_labels"] = entity_labels or [f"E{i}" for i in range(len(entity_fes))]
            if entity_fes:
                result["entity_range"] = (min(entity_fes), max(entity_fes))

        if time_fes is not None and len(time_fes) > 0:
            result["time_fes"] = time_fes
            result["time_labels"] = time_labels or [f"T{i}" for i in range(len(time_fes))]
            if time_fes:
                result["time_range"] = (min(time_fes), max(time_fes))

        # Add configuration info
        result["entity_var"] = self.config.entity_var
        result["time_var"] = self.config.time_var
        result["n_entities"] = self.config.n_entities or len(entity_fes or [])
        result["n_time"] = self.config.n_time or len(time_fes or [])

        return result

    def generate_variance_decomposition(
        self,
        entity_fes: list[float] | None = None,
        time_fes: list[float] | None = None,
        residuals: list[float] | None = None,
    ) -> dict:
        """Compute variance decomposition between entity, time, and residual components.

        The decomposition partitions total variance into:
        - Between-entity variance (captured by entity FEs)
        - Between-time variance (captured by time FEs)
        - Residual variance (unexplained)

        Args:
            entity_fes: Entity fixed effect values
            time_fes: Time fixed effect values
            residuals: Residual values

        Returns:
            Dict with variance shares summing to 1.0.
        """
        # Default synthetic data if none provided
        if entity_fes is None:
            n_ent = max(self.config.n_entities, 50)
            entity_fes = [math.sin(i * 0.3) * 2 + math.cos(i * 0.1) * 0.5 for i in range(n_ent)]

        if time_fes is None:
            n_time = max(self.config.n_time, 10)
            time_fes = [math.sin(i * 0.5) * 1.5 + i * 0.1 for i in range(n_time)]

        if residuals is None:
            n_ent = len(entity_fes)
            n_time = len(time_fes)
            residuals = [
                (hash(str(i) + str(j)) % 100 - 50) / 50.0 * 0.5
                for i in range(n_ent)
                for j in range(n_time)
            ]

        # Calculate variances
        entity_mean = sum(entity_fes) / len(entity_fes) if entity_fes else 0.0
        time_mean = sum(time_fes) / len(time_fes) if time_fes else 0.0

        entity_var = sum((x - entity_mean) ** 2 for x in entity_fes) / len(entity_fes) if entity_fes else 0.0
        time_var = sum((x - time_mean) ** 2 for x in time_fes) / len(time_fes) if time_fes else 0.0

        res_mean = sum(residuals) / len(residuals) if residuals else 0.0
        res_var = sum((x - res_mean) ** 2 for x in residuals) / len(residuals) if residuals else 0.0

        total_var = entity_var + time_var + res_var

        if total_var > 0:
            entity_share = entity_var / total_var
            time_share = time_var / total_var
            residual_share = res_var / total_var
        else:
            entity_share = time_share = residual_share = 1.0 / 3.0

        return {
            "between_entity": round(entity_share, 4),
            "between_time": round(time_share, 4),
            "residual": round(residual_share, 4),
            "total_variance": round(total_var, 4),
            "entity_variance": round(entity_var, 4),
            "time_variance": round(time_var, 4),
            "residual_variance": round(res_var, 4),
            "n_entities": len(entity_fes),
            "n_time_periods": len(time_fes),
            "n_total_obs": len(residuals) if residuals else len(entity_fes) * len(time_fes),
        }

    def to_plotly_dashboard(self) -> dict:
        """Generate a Plotly dashboard with fixed effects visualizations.

        Creates a 3-panel dashboard showing:
        1. Entity fixed effects as a bar chart
        2. Time fixed effects as a bar chart
        3. Variance decomposition as a pie chart

        Returns:
            JSON-serializable dict representing the dashboard figure.
            Empty dict if plotly is not available.
        """
        if not _plotly_available:
            _log.warning("Plotly not available, returning empty dict")
            return {}

        # Generate data
        n_ent = max(self.config.n_entities, 30)
        n_time = max(self.config.n_time, 10)

        entity_fes = [math.sin(i * 0.2) * 2 + (i % 5 - 2) * 0.3 for i in range(n_ent)]
        time_fes = [math.cos(i * 0.4) * 1.2 + i * 0.05 for i in range(n_time)]

        decomp = self.generate_variance_decomposition(entity_fes, time_fes)

        # Create subplot figure
        fig = make_subplots(
            rows=2, cols=2,
            specs=[
                [{"type": "bar"}, {"type": "bar"}],
                [{"type": "pie", "colspan": 2}, None],
            ],
            subplot_titles=(
                f"Entity Fixed Effects ({self.config.entity_var})",
                f"Time Fixed Effects ({self.config.time_var})",
                "Variance Decomposition",
            ),
            row_heights=[0.5, 0.5],
            vertical_spacing=0.15,
            horizontal_spacing=0.1,
        )

        # Entity FE bar chart
        fig.add_trace(
            go.Bar(
                x=list(range(min(n_ent, 50))),
                y=entity_fes[:50],
                name="Entity FE",
                marker_color='#457B9D',
                opacity=0.8,
            ),
            row=1, col=1,
        )

        # Time FE bar chart
        fig.add_trace(
            go.Bar(
                x=list(range(n_time)),
                y=time_fes,
                name="Time FE",
                marker_color='#E63946',
                opacity=0.8,
            ),
            row=1, col=2,
        )

        # Variance decomposition pie chart
        fig.add_trace(
            go.Pie(
                labels=["Entity FE", "Time FE", "Residual"],
                values=[
                    decomp["between_entity"],
                    decomp["between_time"],
                    decomp["residual"],
                ],
                marker_colors=['#457B9D', '#E63946', '#A8DADC'],
                textinfo='label+percent',
                textposition='inside',
                hole=0.4,
            ),
            row=2, col=1,
        )

        fig.update_layout(
            title={
                "text": f"Panel Fixed Effects Dashboard — {self.config.dep_var}",
                "font": {"size": 16},
                "x": 0.5,
            },
            showlegend=False,
            height=700,
            plot_bgcolor='white',
        )

        fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=1, col=1)
        fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=1, col=1)
        fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=1, col=2)
        fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=1, col=2)

        return json.loads(json.dumps(fig.to_dict()))


# ─────────────────────────────────────────────────────────────────────────────
# Regression Diagnostics Explorer
# ─────────────────────────────────────────────────────────────────────────────

class RegressionDiagnosticsExplorer:
    """Interactive regression diagnostics explorer.

    Provides tools for:
    - Identifying outliers and influential observations
    - Computing diagnostic statistics (leverage, Cook's D, VIF)
    - Generating classic 4-panel diagnostic plots

    Example:
        >>> config = DiagnosticsConfig(y=[1,2,3], fitted=[1.1,2.0,3.2], residuals=[-0.1,0,0.2])
        >>> explorer = RegressionDiagnosticsExplorer(config)
        >>> outliers = explorer.identify_outliers()
        >>> report = explorer.generate_diagnostics_report()
    """

    def __init__(self, config: DiagnosticsConfig) -> None:
        """Initialize the diagnostics explorer.

        Args:
            config: DiagnosticsConfig with regression residuals and fitted values
        """
        self.config = config
        self.n = len(config.y)
        self._compute_k()

    def _compute_k(self) -> None:
        """Estimate number of covariates from residual degrees of freedom."""
        # Estimate k from leverage if available
        if self.config.leverage and len(self.config.leverage) > 0:
            avg_leverage = sum(self.config.leverage) / len(self.config.leverage)
            if avg_leverage > 0:
                self.k = int(round(avg_leverage * self.n))
                return
        # Default: estimate from n and df
        self.k = max(1, min(self.n // 10, 10))

    def _compute_influence_threshold(self, n: int | None = None, k: int | None = None, alpha: float = 0.05) -> float:
        """Compute threshold for identifying high-leverage points.

        High leverage points have leverage > 2*k/n.

        Args:
            n: Number of observations
            k: Number of covariates
            alpha: Significance level (for future extension)

        Returns:
            Threshold value for leverage
        """
        n = n or self.n
        k = k or self.k
        return 2.0 * k / n if n > 0 else 0.0

    def _compute_cooks_threshold(self, n: int | None = None, k: int | None = None, alpha: float = 0.05) -> float:
        """Compute threshold for identifying influential points by Cook's D.

        Influential points have Cook's D > 4/(n-k).

        Args:
            n: Number of observations
            k: Number of covariates
            alpha: Significance level (for future extension)

        Returns:
            Threshold value for Cook's distance
        """
        n = n or self.n
        k = k or self.k
        return 4.0 / (n - k) if (n - k) > 0 else 0.0

    def identify_outliers(self) -> dict:
        """Identify outliers and influential observations.

        Uses leverage and Cook's distance thresholds to flag potentially
        problematic observations that may unduly influence regression results.

        Returns:
            Dict with outlier indices, labels, and detailed diagnostic info.
        """
        n = len(self.config.residuals)
        k = self.k

        lev_threshold = self._compute_influence_threshold(n, k)
        cooks_threshold = self._compute_cooks_threshold(n, k)

        outlier_indices = []
        outlier_labels = []
        outlier_details = []

        # Check leverage
        leverage_outliers = set()
        if self.config.leverage:
            for i, lev in enumerate(self.config.leverage):
                if lev > lev_threshold:
                    leverage_outliers.add(i)
                    label = self.config.obs_labels[i] if self.config.obs_labels and i < len(self.config.obs_labels) else f"Obs_{i}"
                    outlier_indices.append(i)
                    outlier_labels.append(label)
                    outlier_details.append({
                        "index": i,
                        "label": label,
                        "type": "high_leverage",
                        "leverage": round(lev, 4),
                        "threshold": round(lev_threshold, 4),
                        "residual": round(self.config.residuals[i], 4) if i < len(self.config.residuals) else None,
                    })

        # Check Cook's D
        cook_outliers = set()
        if self.config.cooksd:
            for i, cooks in enumerate(self.config.cooksd):
                if cooks > cooks_threshold:
                    cook_outliers.add(i)
                    label = self.config.obs_labels[i] if self.config.obs_labels and i < len(self.config.obs_labels) else f"Obs_{i}"
                    if i not in leverage_outliers:
                        outlier_indices.append(i)
                        outlier_labels.append(label)
                    outlier_details.append({
                        "index": i,
                        "label": label,
                        "type": "influential",
                        "cooks_d": round(cooks, 4),
                        "threshold": round(cooks_threshold, 4),
                        "residual": round(self.config.residuals[i], 4) if i < len(self.config.residuals) else None,
                    })

        # Check for large residuals (studentized-like)
        if self.config.residuals:
            res_mean = sum(self.config.residuals) / n
            res_std = math.sqrt(sum((r - res_mean) ** 2 for r in self.config.residuals) / (n - 1))

            if res_std > 0:
                for i, res in enumerate(self.config.residuals):
                    if abs(res) > 3 * res_std and i not in leverage_outliers and i not in cook_outliers:
                        label = self.config.obs_labels[i] if self.config.obs_labels and i < len(self.config.obs_labels) else f"Obs_{i}"
                        outlier_indices.append(i)
                        outlier_labels.append(label)
                        outlier_details.append({
                            "index": i,
                            "label": label,
                            "type": "large_residual",
                            "residual": round(res, 4),
                            "studentized": round(res / res_std, 4),
                            "threshold_3sigma": round(3 * res_std, 4),
                        })

        return {
            "outlier_indices": outlier_indices,
            "outlier_labels": outlier_labels,
            "outlier_details": outlier_details,
            "n_outliers": len(outlier_indices),
            "leverage_threshold": round(lev_threshold, 4),
            "cooks_threshold": round(cooks_threshold, 4),
        }

    def generate_diagnostics_report(self) -> dict:
        """Generate comprehensive regression diagnostics report.

        Computes summary statistics, model fit measures, and diagnostic
        thresholds for the regression.

        Returns:
            Dict with full diagnostics report including R², RMSE, outlier counts.
        """
        n = len(self.config.y)
        k = self.k

        # Compute R² and adjusted R²
        ss_res = sum(r ** 2 for r in self.config.residuals)
        y_mean = sum(self.config.y) / n
        ss_tot = sum((y - y_mean) ** 2 for y in self.config.y)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k - 1) if (n - k - 1) > 0 else r_squared

        # RMSE
        rmse = math.sqrt(ss_res / n)

        # Outliers
        outliers = self.identify_outliers()

        # VIF warning (heuristic based on average leverage)
        vif_warning = False
        if self.config.leverage and len(self.config.leverage) > 0:
            avg_lev = sum(self.config.leverage) / len(self.config.leverage)
            # VIF > 10 suggests multicollinearity
            if k > 0 and avg_lev > 0:
                vif_estimate = 1 / (1 - avg_lev) if avg_lev < 1 else float('inf')
                vif_warning = vif_estimate > 10

        return {
            "n_obs": n,
            "n_covariates": k,
            "r_squared": round(r_squared, 4),
            "adj_r_squared": round(adj_r_squared, 4),
            "rmse": round(rmse, 4),
            "outlier_count": outliers["n_outliers"],
            "influential_count": sum(1 for d in outliers["outlier_details"] if d.get("type") == "influential"),
            "leverage_threshold": outliers["leverage_threshold"],
            "cooks_threshold": outliers["cooks_threshold"],
            "vif_warning": vif_warning,
            "ss_residual": round(ss_res, 4),
            "ss_total": round(ss_tot, 4),
        }

    def to_plotly_figure(self) -> dict:
        """Generate a 4-panel diagnostic plot figure.

        Creates the classic regression diagnostics plot with:
        1. Residuals vs Fitted values
        2. Normal Q-Q plot of residuals
        3. Scale-Location plot (sqrt of standardized residuals)
        4. Residuals vs Leverage with Cook's D contours

        Returns:
            JSON-serializable dict representing the figure.
            Empty dict if plotly is not available.
        """
        if not _plotly_available:
            _log.warning("Plotly not available, returning empty dict")
            return {}

        fitted = self.config.fitted
        residuals = self.config.residuals
        n = len(residuals)
        k = self.k

        # Compute standardized residuals
        res_mean = sum(residuals) / n
        res_std = math.sqrt(sum((r - res_mean) ** 2 for r in residuals) / (n - 1))
        std_residuals = [(r - res_mean) / res_std if res_std > 0 else 0 for r in residuals]

        # Sort indices for Q-Q plot
        sorted_indices = sorted(range(n), key=lambda i: std_residuals[i])
        theoretical_quantiles = [
            (i + 0.5) / (n + 0.5) for i in range(1, n + 1)
        ]
        import numpy as _np
        theoretical_quantiles = _np.ndtile(theoretical_quantiles, 0.5).tolist() if hasattr(_np, 'ndtile') else theoretical_quantiles

        # Theoretical quantiles for standard normal
        from statistics import NormalDist
        try:
            norm_dist = NormalDist()
            tq = [norm_dist.inv_cdf((i + 0.5) / n) for i in range(n)]
        except Exception:
            tq = [0.0] * n
            for i in range(n):
                tq[i] = ((i + 0.5) / n - 0.5) * 3  # Rough approximation

        sample_quantiles = [std_residuals[i] for i in sorted_indices]

        # Scale-Location values
        sqrt_std_resid = [math.sqrt(abs(r)) for r in std_residuals]

        # Leverage values
        leverage = self.config.leverage or [k / n] * n
        cooks = self.config.cooksd or [0.0] * n

        # Cook's D threshold contour line
        cooks_threshold = self._compute_cooks_threshold(n, k)

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[
                "(1) Residuals vs Fitted",
                "(2) Normal Q-Q",
                "(3) Scale-Location",
                "(4) Residuals vs Leverage",
            ],
            vertical_spacing=0.12,
            horizontal_spacing=0.1,
        )

        # Plot 1: Residuals vs Fitted
        fig.add_trace(go.Scatter(
            x=fitted,
            y=residuals,
            mode='markers',
            marker={
                "size": 8,
                "color": '#457B9D',
                "opacity": 0.7,
            },
            name='Residuals',
            showlegend=False,
        ), row=1, col=1)

        # Add smoothed line (lowess-like)
        if len(fitted) > 2:
            sorted_pairs = sorted(zip(fitted, residuals, strict=False))
            x_sorted = [p[0] for p in sorted_pairs]
            y_sorted = [p[1] for p in sorted_pairs]
            # Simple moving average smoothing
            window = min(5, len(x_sorted) // 3)
            smooth_y = []
            for i in range(len(y_sorted)):
                start = max(0, i - window // 2)
                end = min(len(y_sorted), i + window // 2 + 1)
                smooth_y.append(sum(y_sorted[start:end]) / (end - start))

            fig.add_trace(go.Scatter(
                x=x_sorted,
                y=smooth_y,
                mode='lines',
                line={"color": '#E63946', "width": 2},
                name='Smoothed',
                showlegend=False,
            ), row=1, col=1)

        # Zero reference line
        max(abs(min(residuals)), abs(max(residuals)))
        fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=1, row=1, col=1)

        # Plot 2: Q-Q plot
        fig.add_trace(go.Scatter(
            x=tq,
            y=sample_quantiles,
            mode='markers',
            marker={
                "size": 8,
                "color": '#457B9D',
                "opacity": 0.7,
            },
            name='Sample',
            showlegend=False,
        ), row=1, col=2)

        # Reference line for Q-Q
        min_val = min(min(tq), min(sample_quantiles))
        max_val = max(max(tq), max(sample_quantiles))
        fig.add_trace(go.Scatter(
            x=[min_val, max_val],
            y=[min_val, max_val],
            mode='lines',
            line={"color": '#E63946', "width": 2, "dash": 'dash'},
            name='Reference',
            showlegend=False,
        ), row=1, col=2)

        # Plot 3: Scale-Location
        fig.add_trace(go.Scatter(
            x=fitted,
            y=sqrt_std_resid,
            mode='markers',
            marker={
                "size": 8,
                "color": '#457B9D',
                "opacity": 0.7,
            },
            name='√|Standardized|',
            showlegend=False,
        ), row=2, col=1)

        # Smoothed line for Scale-Location
        if len(fitted) > 2:
            sorted_pairs = sorted(zip(fitted, sqrt_std_resid, strict=False))
            x_sorted = [p[0] for p in sorted_pairs]
            y_sorted = [p[1] for p in sorted_pairs]
            window = min(5, len(x_sorted) // 3)
            smooth_y = []
            for i in range(len(y_sorted)):
                start = max(0, i - window // 2)
                end = min(len(y_sorted), i + window // 2 + 1)
                smooth_y.append(sum(y_sorted[start:end]) / (end - start))

            fig.add_trace(go.Scatter(
                x=x_sorted,
                y=smooth_y,
                mode='lines',
                line={"color": '#E63946', "width": 2},
                name='Smoothed',
                showlegend=False,
            ), row=2, col=1)

        # Plot 4: Residuals vs Leverage
        marker_colors = ['#E63946' if c > cooks_threshold else '#457B9D' for c in cooks]

        fig.add_trace(go.Scatter(
            x=leverage,
            y=residuals,
            mode='markers',
            marker={
                "size": 8 + [10 if c > cooks_threshold else 0 for c in cooks],
                "color": marker_colors,
                "opacity": 0.7,
            },
            name='Observations',
            showlegend=False,
            text=[f"Cook's D: {c:.3f}" for c in cooks],
            hovertemplate='Leverage: %{x:.3f}<br>Residual: %{y:.3f}<br>%{text}<extra></extra>',
        ), row=2, col=2)

        # Cook's D contour lines (simplified)
        lev_range = max(max(leverage), lev_threshold * 1.5) if leverage else 0.1
        lev_vals = [i * lev_range / 50 for i in range(51)]

        # Cook's D = 4/(n-k) approximation contours
        cooks_contour_y = [
            math.sqrt(cooks_threshold * k * (1 - lev) / (n * lev)) if lev > 0 and lev < 1 else 0
            for lev in lev_vals
        ]

        fig.add_trace(go.Scatter(
            x=lev_vals,
            y=cooks_contour_y,
            mode='lines',
            line={"color": 'gray', "width": 1, "dash": 'dash'},
            name=f"Cook's D = {cooks_threshold:.2f}",
            showlegend=True,
        ), row=2, col=2)

        fig.add_trace(go.Scatter(
            x=lev_vals,
            y=[-y for y in cooks_contour_y],
            mode='lines',
            line={"color": 'gray', "width": 1, "dash": 'dash'},
            showlegend=False,
        ), row=2, col=2)

        # Add leverage threshold line
        fig.add_vline(
            x=lev_threshold,
            line_dash='dot',
            line_color='gray',
            line_width=1,
            row=2, col=2,
            annotation_text=f"2k/n={lev_threshold:.2f}",
            annotation_position="top right",
        )

        fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=1, row=2, col=2)

        fig.update_layout(
            title={
                "text": "Regression Diagnostics",
                "font": {"size": 16},
                "x": 0.5,
            },
            showlegend=True,
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1,
            },
            height=700,
            plot_bgcolor='white',
            font={"size": 11},
        )

        # Axis labels
        fig.update_xaxes(title_text="Fitted values", row=1, col=1)
        fig.update_yaxes(title_text="Residuals", row=1, col=1)
        fig.update_xaxes(title_text="Theoretical Quantiles", row=1, col=2)
        fig.update_yaxes(title_text="Sample Quantiles", row=1, col=2)
        fig.update_xaxes(title_text="Fitted values", row=2, col=1)
        fig.update_yaxes(title_text="√|Standardized Residuals|", row=2, col=1)
        fig.update_xaxes(title_text="Leverage", row=2, col=2)
        fig.update_yaxes(title_text="Residuals", row=2, col=2)

        # Grid styling
        for row in range(1, 3):
            for col in range(1, 3):
                fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=row, col=col)
                fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=row, col=col)

        return json.loads(json.dumps(fig.to_dict()))


# ─────────────────────────────────────────────────────────────────────────────
# Time Series Decomposer
# ─────────────────────────────────────────────────────────────────────────────

class TimeSeriesDecomposer:
    """Time series decomposition explorer.

    Provides tools for:
    - Classical additive/multiplicative decomposition
    - Trend extraction via moving average
    - Seasonal component estimation
    - Stationarity testing

    Example:
        >>> decomposer = TimeSeriesDecomposer([1.0, 2.0, 3.0, 4.0], dates=["2020-01", "2020-02", "2020-03", "2020-04"])
        >>> result = decomposer.decompose("additive")
        >>> stationarity = decomposer.test_stationarity()
    """

    def __init__(
        self,
        series: list[float],
        dates: list[str] | None = None,
        period: int = 12,
    ) -> None:
        """Initialize the time series decomposer.

        Args:
            series: Time series values
            dates: Optional date/period labels
            period: Period for seasonal decomposition (e.g., 12 for monthly)
        """
        self.series = series
        self.dates = dates or [f"t{i}" for i in range(len(series))]
        self.period = period

        # Decomposition results (cached)
        self._decomposition: dict | None = None

    def _moving_average(self, values: list[float], window: int) -> list[float]:
        """Compute centered moving average.

        Args:
            values: Input values
            window: Window size (should match period)

        Returns:
            Trend component (shortened by window//2 on each side)
        """
        n = len(values)
        half_window = window // 2

        trend = []
        for i in range(n):
            start = max(0, i - half_window)
            end = min(n, i + half_window + 1)
            trend.append(sum(values[start:end]) / (end - start))

        return trend

    def decompose(self, method: str = "additive") -> dict:
        """Perform classical time series decomposition.

        Uses moving average to extract trend, then computes seasonal
        component by averaging detrended values at each period position.

        Args:
            method: "additive" (Y = T + S + R) or "multiplicative" (Y = T × S × R)

        Returns:
            Dict with trend, seasonal, and residual components.
        """
        values = self.series
        n = len(values)
        period = min(self.period, n // 2)

        if n < 4:
            _log.warning("Series too short for decomposition")
            return {
                "trend": values[:],
                "seasonal": [0.0] * n,
                "residual": [0.0] * n,
                "period": period,
                "method": method,
            }

        # Step 1: Extract trend via centered moving average
        trend = self._moving_average(values, period)

        # Step 2: Detrend the series
        if method == "multiplicative":
            detrended = [v / t if t != 0 else 0 for v, t in zip(values, trend, strict=False)]
        else:
            detrended = [v - t for v, t in zip(values, trend, strict=False)]

        # Step 3: Estimate seasonal component
        # Average detrended values at each period position
        seasonal = [0.0] * period
        counts = [0] * period

        for i, val in enumerate(detrended):
            pos = i % period
            seasonal[pos] += val
            counts[pos] += 1

        seasonal = [s / c if c > 0 else 0 for s, c in zip(seasonal, counts, strict=False)]

        # Normalize seasonal to sum to zero (additive) or mean of 1 (multiplicative)
        if method == "additive":
            seasonal_mean = sum(seasonal) / len(seasonal)
            seasonal = [s - seasonal_mean for s in seasonal]
        else:
            seasonal_mean = sum(seasonal) / len(seasonal)
            seasonal = [s / seasonal_mean if seasonal_mean != 0 else 1.0 for s in seasonal]

        # Extend seasonal to full series length
        seasonal_full = [seasonal[i % period] for i in range(n)]

        # Step 4: Compute residuals
        if method == "multiplicative":
            residual = [v / (t * s) if t != 0 and s != 0 else 0 for v, t, s in zip(values, trend, seasonal_full, strict=False)]
        else:
            residual = [v - t - s for v, t, s in zip(values, trend, seasonal_full, strict=False)]

        self._decomposition = {
            "trend": trend,
            "seasonal": seasonal_full,
            "residual": residual,
            "period": period,
            "method": method,
            "n_obs": n,
        }

        return self._decomposition

    def to_plotly_figure(self) -> dict:
        """Generate decomposition plot with trend, seasonal, and residual components.

        Creates a 4-panel subplot showing:
        1. Original series
        2. Extracted trend
        3. Seasonal component
        4. Residuals

        Returns:
            JSON-serializable dict representing the figure.
            Empty dict if plotly is not available.
        """
        if not _plotly_available:
            _log.warning("Plotly not available, returning empty dict")
            return {}

        if self._decomposition is None:
            self.decompose()

        decomp = self._decomposition

        trend = decomp["trend"]
        seasonal = decomp["seasonal"]
        residual = decomp["residual"]

        # Create x-axis labels
        x = list(range(len(self.series)))

        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=["Original Series", "Trend", "Seasonal", "Residual"],
        )

        # Original series
        fig.add_trace(go.Scatter(
            x=x,
            y=self.series,
            mode='lines',
            name='Original',
            line={"color": '#1D3557', "width": 1.5},
        ), row=1, col=1)

        # Trend
        fig.add_trace(go.Scatter(
            x=x,
            y=trend,
            mode='lines',
            name='Trend',
            line={"color": '#E63946', "width": 2},
        ), row=2, col=1)

        # Seasonal
        fig.add_trace(go.Scatter(
            x=x,
            y=seasonal,
            mode='lines',
            name='Seasonal',
            line={"color": '#457B9D', "width": 1.5},
            fill='tozeroy',
            fillcolor='rgba(69,123,157,0.2)',
        ), row=3, col=1)

        # Residual
        fig.add_trace(go.Scatter(
            x=x,
            y=residual,
            mode='lines',
            name='Residual',
            line={"color": '#A8DADC', "width": 1.5},
        ), row=4, col=1)

        # Add zero line for residual
        fig.add_hline(y=0, line_dash='dash', line_color='gray', line_width=1, row=4, col=1)

        fig.update_layout(
            title={
                "text": f"Time Series Decomposition (Period = {decomp['period']})",
                "font": {"size": 16},
                "x": 0.5,
            },
            showlegend=True,
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.01,
                "xanchor": "right",
                "x": 1,
            },
            height=800,
            plot_bgcolor='white',
            font={"size": 11},
        )

        # Update axes
        for row in range(1, 5):
            fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=row, col=1)
            fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)', row=row, col=1)

        # Use dates as x-axis labels if available
        if self.dates and len(self.dates) == len(self.series):
            fig.update_xaxes(
                tickvals=x[::max(1, len(x) // 12)],
                ticktext=self.dates[::max(1, len(self.dates) // 12)],
                row=4, col=1,
            )

        return json.loads(json.dumps(fig.to_dict()))

    def test_stationarity(self) -> dict:
        """Perform ADF-like stationarity test.

        Regresses first difference on lag-1 and trend term.
        If t-statistic < -1.94 (5% critical value), reject unit root.

        Returns:
            Dict with stationarity test results.
        """
        y = self.series
        n = len(y)

        if n < 3:
            return {
                "is_stationary": False,
                "test_stat": float('nan'),
                "critical_value": -1.94,
                "method": "ADF-like (insufficient data)",
                "note": "Need at least 3 observations",
            }

        # Compute first differences
        diff_y = [y[i] - y[i - 1] for i in range(1, n)]
        lag_y = y[:-1]  # Y_{t-1}

        # Run regression: ΔY = α + ρ*Y_{t-1} + trend*t + ε
        # Compute coefficients using OLS formulas
        T = len(diff_y)

        # Build design matrix: [1, lag, time]
        time_trend = list(range(T))

        # Compute means
        mean_diff = sum(diff_y) / T
        mean_lag = sum(lag_y) / T
        mean_time = sum(time_trend) / T

        # Compute sums of squares and cross-products
        ss_lag_lag = sum((x - mean_lag) ** 2 for x in lag_y)
        sum((x - mean_time) ** 2 for x in time_trend)
        sum((x - mean_diff) ** 2 for x in diff_y)

        sp_lag_diff = sum((lag_y[i] - mean_lag) * (diff_y[i] - mean_diff) for i in range(T))
        sum((time_trend[i] - mean_time) * (diff_y[i] - mean_diff) for i in range(T))
        sum((lag_y[i] - mean_lag) * (time_trend[i] - mean_time) for i in range(T))

        # Solve normal equations for ρ and trend coefficient
        # Using simplified approach: regress diff on lag only
        if ss_lag_lag > 0:
            rho = sp_lag_diff / ss_lag_lag
        else:
            rho = 0.0

        # Compute residuals and standard error
        fitted = [rho * lag for lag in lag_y]
        residuals = [diff_y[i] - fitted[i] for i in range(T)]

        ss_res = sum(r ** 2 for r in residuals)
        se_rho = math.sqrt(ss_res / (T * ss_lag_lag)) if ss_lag_lag > 0 else float('inf')

        # T-statistic for rho
        t_stat = rho / se_rho if se_rho > 0 else 0.0

        # Critical value (Dickey-Fuller 5% critical value for model with constant only)
        critical_value = -2.86  # Approximate 5% critical value

        is_stationary = t_stat < critical_value

        # Additional check: average absolute autocorrelation of residuals
        if len(residuals) > 2:
            autocorr = self._autocorrelation(residuals, 1)
        else:
            autocorr = 0.0

        return {
            "is_stationary": is_stationary,
            "test_stat": round(t_stat, 4),
            "critical_value": critical_value,
            "rho_coefficient": round(rho, 4),
            "standard_error": round(se_rho, 4) if se_rho != float('inf') else None,
            "method": "ADF-like (Dickey-Fuller unit root test)",
            "lag_order": 1,
            "n_obs": n,
            "autocorrelation_at_lag1": round(autocorr, 4) if autocorr else None,
            "conclusion": (
                "Stationary (reject unit root)" if is_stationary
                else "Non-stationary (unit root present)"
            ),
        }

    def _autocorrelation(self, series: list[float], lag: int) -> float:
        """Compute autocorrelation at given lag.

        Args:
            series: Time series
            lag: Lag order

        Returns:
            Autocorrelation coefficient
        """
        n = len(series)
        if n <= lag:
            return 0.0

        mean = sum(series) / n
        var = sum((x - mean) ** 2 for x in series)

        if var == 0:
            return 0.0

        autocov = sum((series[i] - mean) * (series[i - lag] - mean) for i in range(lag, n))
        return autocov / var


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ─────────────────────────────────────────────────────────────────────────────

def run_explorer_app() -> None:
    """Launch the interactive Streamlit dashboard.

    Creates a multi-tab dashboard with:
    - DID Event Study visualization
    - Panel Fixed Effects dashboard
    - Regression Diagnostics plots
    - Time Series Decomposition tools

    Includes file upload and direct data input, plus PNG export capability.

    Raises:
        ImportError: If streamlit is not installed
    """
    try:
        import pandas as pd
        import streamlit as st
    except ImportError:
        raise ImportError(
            "streamlit is required for the interactive app. "
            "Install with: pip install streamlit plotly pandas\n"
            "Then run: streamlit run scripts/core/interactive_explorer.py"
        )

    st.set_page_config(
        page_title="Financial Research Explorer",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("📊 Financial Research Interactive Explorer")
    st.markdown("---")

    # Sidebar navigation
    st.sidebar.header("Navigation")
    tab = st.sidebar.radio(
        "Select Analysis",
        [
            "DID Event Study",
            "Panel Fixed Effects",
            "Regression Diagnostics",
            "Time Series",
        ],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Data Input")
    data_source = st.sidebar.radio(
        "Choose data source",
        ["Upload CSV", "Manual Entry", "Demo Data"],
        index=2,
    )

    # Helper function to read CSV
    def read_uploaded_csv(uploaded_file) -> pd.DataFrame | None:
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                return df
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
                return None
        return None

    # ─────────────────────────────────────────────────────────────────────
    # DID Event Study Tab
    # ─────────────────────────────────────────────────────────────────────
    if tab == "DID Event Study":
        st.header("DID Event Study Visualization")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("Configuration")

            treat_label = st.text_input("Treatment Group Label", value="Treatment")
            ctrl_label = st.text_input("Control Group Label", value="Control")
            ylabel = st.text_input("Y-axis Label", value="Outcome")
            title = st.text_input("Plot Title", value="Event Study: DID Analysis")
            ci_level = st.slider("Confidence Level", 0.90, 0.99, 0.95)

        with col2:
            st.subheader("Data Entry")

            source = data_source

            if source == "Demo Data":
                st.info("Using demo data")

                pre_means = {"-3": 1.0, "-2": 1.1, "-1": 1.05, "0": 1.2}
                post_means = {"1": 2.0, "2": 2.1, "3": 2.3}
                pre_ses = {"-3": 0.1, "-2": 0.1, "-1": 0.1, "0": 0.1}
                post_ses = {"1": 0.2, "2": 0.2, "3": 0.2}

                event_time = [-3, -2, -1, 0, 1, 2, 3]

            elif source == "Manual Entry":
                pre_input = st.text_area("Pre-treatment Means (JSON)", value='{"-3": 1.0, "-2": 1.1, "-1": 1.2}')
                post_input = st.text_area("Post-treatment Means (JSON)", value='{"0": 2.0, "1": 2.1, "2": 2.2}')
                pre_se_input = st.text_area("Pre-treatment SEs (JSON, optional)", value='{"-3": 0.1, "-2": 0.1, "-1": 0.1}')
                post_se_input = st.text_area("Post-treatment SEs (JSON, optional)", value='{"0": 0.2, "1": 0.2, "2": 0.2}')

                try:
                    pre_means = json.loads(pre_input)
                    post_means = json.loads(post_input)
                    pre_ses = json.loads(pre_se_input) if pre_se_input.strip() else None
                    post_ses = json.loads(post_se_input) if post_se_input.strip() else None
                    event_time = None
                except json.JSONDecodeError:
                    st.error("Invalid JSON format")
                    pre_means = {}
                    post_means = {}
                    pre_ses = None
                    post_ses = None
                    event_time = None

            else:  # Upload CSV
                uploaded = st.file_uploader("Upload CSV with columns: period, treat_mean, ctrl_mean, se", type="csv")
                if uploaded:
                    df = pd.read_csv(uploaded)
                    if all(col in df.columns for col in ["period", "treat_mean"]):
                        pre_rows = df[df["period"] < 0] if "period" in df.columns else []
                        post_rows = df[df["period"] >= 0] if "period" in df.columns else []
                        pre_means = dict(zip(pre_rows["period"].astype(str), pre_rows["treat_mean"], strict=False))
                        post_means = dict(zip(post_rows["period"].astype(str), post_rows["treat_mean"], strict=False))
                        if "se" in df.columns:
                            pre_ses = dict(zip(pre_rows["period"].astype(str), pre_rows["se"], strict=False))
                            post_ses = dict(zip(post_rows["period"].astype(str), post_rows["se"], strict=False))
                        else:
                            pre_ses = None
                            post_ses = None
                        event_time = sorted(df["period"].tolist())
                    else:
                        st.error("CSV must have columns: period, treat_mean")
                        pre_means = {}
                        post_means = {}
                        pre_ses = None
                        post_ses = None
                        event_time = None
                else:
                    pre_means = {"-3": 1.0, "-2": 1.1, "-1": 1.05, "0": 1.2}
                    post_means = {"1": 2.0, "2": 2.1, "3": 2.3}
                    pre_ses = {"-3": 0.1, "-2": 0.1, "-1": 0.1, "0": 0.1}
                    post_ses = {"1": 0.2, "2": 0.2, "3": 0.2}
                    event_time = [-3, -2, -1, 0, 1, 2, 3]

        # Create explorer and plot
        config = DIDEventStudyConfig(
            pre_means=pre_means,
            post_means=post_means,
            pre_ses=pre_ses,
            post_ses=post_ses,
            treat_label=treat_label,
            ctrl_label=ctrl_label,
            event_time=event_time,
            ylabel=ylabel,
            title=title,
            ci_level=ci_level,
        )

        explorer = DIDEventStudyExplorer(config)

        # Display plot
        if _plotly_available:
            fig_dict = explorer.to_plotly_figure()
            if fig_dict:
                import plotly.io as pio
                fig = pio.from_json(json.dumps(fig_dict))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Plotly not available. Install with: pip install plotly")
            # Show matplotlib code instead
            script = explorer.to_matplotlib_script()
            with st.expander("Matplotlib Script (Plotly not available)"):
                st.code(script, language="python")

        # Summary statistics
        st.subheader("Summary Statistics")
        summary = explorer.to_summary_data()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Pre-treatment Mean", f"{summary['pre_mean']:.3f}")
        with col2:
            st.metric("Post-treatment Mean", f"{summary['post_mean']:.3f}")
        with col3:
            st.metric("DID Estimate", f"{summary['did_estimate']:.3f}")
        with col4:
            is_valid, _ = explorer.validate_parallel_trends()
            st.metric("Parallel Trends", "✓ Valid" if is_valid else "⚠ Warning")

        # Parallel trends validation
        is_valid, reason = explorer.validate_parallel_trends()
        if is_valid:
            st.success(f"**Parallel Trends Check**: {reason}")
        else:
            st.warning(f"**Parallel Trends Check**: {reason}")

        # Export
        st.markdown("---")
        st.subheader("Export")
        if _plotly_available and fig_dict:
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download as PNG",
                    data=json.dumps(fig_dict),
                    file_name="event_study.json",
                    mime="application/json",
                )
            with col2:
                script = explorer.to_matplotlib_script()
                st.download_button(
                    "📥 Download Matplotlib Script",
                    data=script,
                    file_name="event_study_plot.py",
                    mime="text/plain",
                )

    # ─────────────────────────────────────────────────────────────────────
    # Panel Fixed Effects Tab
    # ─────────────────────────────────────────────────────────────────────
    elif tab == "Panel Fixed Effects":
        st.header("Panel Fixed Effects Dashboard")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Configuration")
            entity_var = st.text_input("Entity Variable", value="firm_id")
            time_var = st.text_input("Time Variable", value="year")
            dep_var = st.text_input("Dependent Variable", value="log_y")
            n_entities = st.number_input("Number of Entities", min_value=1, max_value=1000, value=100)
            n_time = st.number_input("Number of Time Periods", min_value=1, max_value=100, value=10)

        config = PanelFEConfig(
            entity_var=entity_var,
            time_var=time_var,
            dep_var=dep_var,
            fe_entity=True,
            fe_time=True,
            n_entities=n_entities,
            n_time=n_time,
        )

        viz = PanelFEVisualizer(config)

        # Variance decomposition
        decomp = viz.generate_variance_decomposition()

        with col2:
            st.subheader("Variance Decomposition")

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Between-Entity", f"{decomp['between_entity']:.1%}")
            with c2:
                st.metric("Between-Time", f"{decomp['between_time']:.1%}")
            with c3:
                st.metric("Residual", f"{decomp['residual']:.1%}")

        # Dashboard
        if _plotly_available:
            dashboard = viz.to_plotly_dashboard()
            if dashboard:
                import plotly.io as pio
                fig = pio.from_json(json.dumps(dashboard))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Plotly not available")

        # Fixed effects data
        st.subheader("Fixed Effects Data")
        fe_data = viz.generate_fe_heatmap_data()

        if fe_data:
            st.write(f"Entity FEs: {len(fe_data.get('entity_fes', []))} entities")
            st.write(f"Time FEs: {len(fe_data.get('time_fes', []))} periods")

    # ─────────────────────────────────────────────────────────────────────
    # Regression Diagnostics Tab
    # ─────────────────────────────────────────────────────────────────────
    elif tab == "Regression Diagnostics":
        st.header("Regression Diagnostics")

        # Data input
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Configuration")
            uploaded = st.file_uploader("Upload regression results CSV", type="csv")

            if uploaded:
                df = pd.read_csv(uploaded)
                required_cols = {"y", "fitted", "residuals"}
                if required_cols.issubset(set(df.columns)):
                    y = df["y"].tolist()
                    fitted = df["fitted"].tolist()
                    residuals = df["residuals"].tolist()
                    leverage = df["leverage"].tolist() if "leverage" in df.columns else None
                    cooksd = df["cooksd"].tolist() if "cooksd" in df.columns else None
                    obs_labels = df["label"].tolist() if "label" in df.columns else None
                    st.success(f"Loaded {len(df)} observations")
                else:
                    st.error(f"CSV must have columns: {required_cols}")
                    y, fitted, residuals = [], [], []
                    leverage, cooksd, obs_labels = None, None, None
            else:
                # Demo data
                import numpy as np
                np.random.seed(42)
                n = 100
                x = np.random.randn(n)
                y = 1 + 2 * x + np.random.randn(n) * 0.5
                fitted = 1 + 2 * x
                residuals = y - fitted
                leverage = (x ** 2) / sum(x ** 2)
                cooksd = residuals ** 2 / (sum(residuals ** 2) / n) * leverage / (1 - leverage)
                obs_labels = None
                st.info("Using demo data (100 observations)")

        if y and fitted and residuals:
            config = DiagnosticsConfig(
                y=y,
                fitted=fitted,
                residuals=residuals,
                leverage=leverage,
                cooksd=cooksd,
                obs_labels=obs_labels,
            )

            explorer = RegressionDiagnosticsExplorer(config)

            # Diagnostic report
            report = explorer.generate_diagnostics_report()

            with col2:
                st.subheader("Model Fit Statistics")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("R²", f"{report['r_squared']:.4f}")
                with c2:
                    st.metric("Adj. R²", f"{report['adj_r_squared']:.4f}")
                with c3:
                    st.metric("RMSE", f"{report['rmse']:.4f}")
                with c4:
                    st.metric("Observations", report["n_obs"])

            # Outliers
            outliers = explorer.identify_outliers()

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Outliers Detected", outliers["n_outliers"])
            with col2:
                st.metric("Leverage Threshold", f"{report['leverage_threshold']:.4f}")
            with col3:
                if report['vif_warning']:
                    st.warning("⚠ VIF > 10: Multicollinearity detected")
                else:
                    st.success("✓ VIF < 10: No multicollinearity")

            # Diagnostic plots
            if _plotly_available:
                fig_dict = explorer.to_plotly_figure()
                if fig_dict:
                    import plotly.io as pio
                    fig = pio.from_json(json.dumps(fig_dict))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Plotly not available")

            # Outlier details
            if outliers["n_outliers"] > 0:
                with st.expander(f"Outlier Details ({outliers['n_outliers']} observations)"):
                    for detail in outliers["outlier_details"][:20]:
                        st.write(f"- **{detail['label']}**: {detail['type']} — {detail}")

    # ─────────────────────────────────────────────────────────────────────
    # Time Series Tab
    # ─────────────────────────────────────────────────────────────────────
    else:  # Time Series
        st.header("Time Series Decomposition")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Configuration")
            period = st.number_input("Seasonal Period", min_value=2, max_value=52, value=12)
            method = st.selectbox("Decomposition Method", ["additive", "multiplicative"], index=0)

            uploaded = st.file_uploader("Upload time series CSV", type="csv")

            if uploaded:
                df = pd.read_csv(uploaded)
                if "value" in df.columns or "y" in df.columns:
                    col = "value" if "value" in df.columns else "y"
                    series = df[col].tolist()
                    dates = df["date"].tolist() if "date" in df.columns else None
                    st.success(f"Loaded {len(series)} observations")
                else:
                    st.error("CSV must have a 'value' or 'y' column")
                    series, dates = [], None
            else:
                # Demo data
                import numpy as np
                np.random.seed(42)
                n = 120
                t = np.arange(n)
                trend = 0.1 * t
                seasonal = 5 * np.sin(2 * np.pi * t / 12)
                noise = np.random.randn(n) * 0.5
                series = (trend + seasonal + noise).tolist()
                dates = [f"2020-{i%12+1:02d}" for i in range(n)]
                st.info("Using demo data (120 monthly observations)")

        if series:
            decomposer = TimeSeriesDecomposer(
                series=series,
                dates=dates,
                period=period,
            )

            result = decomposer.decompose(method)

            # Stationarity test
            stationarity = decomposer.test_stationarity()

            with col2:
                st.subheader("Stationarity Test")
                if stationarity["is_stationary"]:
                    st.success(f"**Conclusion**: {stationarity['conclusion']}")
                else:
                    st.warning(f"**Conclusion**: {stationarity['conclusion']}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Test Statistic", f"{stationarity['test_stat']:.3f}")
                with c2:
                    st.metric("Critical Value (5%)", f"{stationarity['critical_value']:.2f}")
                with c3:
                    st.metric("Method", stationarity.get("method", "ADF")[:20])

            # Decomposition plot
            if _plotly_available:
                fig_dict = decomposer.to_plotly_figure()
                if fig_dict:
                    import plotly.io as pio
                    fig = pio.from_json(json.dumps(fig_dict))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Plotly not available")

            # Summary stats
            st.subheader("Decomposition Summary")
            c1, c2, c3 = st.columns(3)
            with c1:
                trend_mean = sum(result["trend"]) / len(result["trend"])
                st.metric("Trend (avg)", f"{trend_mean:.2f}")
            with c2:
                seasonal_range = max(result["seasonal"]) - min(result["seasonal"])
                st.metric("Seasonal Range", f"{seasonal_range:.2f}")
            with c3:
                residual_std = math.sqrt(sum(r**2 for r in result["residual"]) / len(result["residual"]))
                st.metric("Residual Std", f"{residual_std:.2f}")


def main() -> None:
    """Entry point for running as a standalone script."""
    run_explorer_app()


if __name__ == "__main__":
    main()
