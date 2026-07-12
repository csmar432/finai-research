---
description: Generate academic-quality figures (>=300 DPI) for economics and finance papers
trigger: "生成图|图表|figure|可视化|绘制|plot|图表生成|学术图表"
version: 1.0
dependencies:
  - FIGURE_PLAN.md
  - TABLE_PLAN.md
  - PAPER_OUTLINE.md
  - empirical data files (.dta, .csv, .xlsx)
outputs:
  - draft_v{version}/figures/*.pdf
  - draft_v{version}/figures/*.png
  - draft_v{version}/figures/*.svg
tags:
  - visualization
  - matplotlib
  - fin-paper
  - academic-graphics
---

# fin-paper-figure

> Generate academic-quality figures (>=300 DPI) for economics and finance papers. Reads FIGURE_PLAN.md and actual data, then produces publication-ready figures using FinancialChartFactory.

## Step 0: Environment Check

Before generating any figures, verify the environment:

```bash
# Check required packages
python -c "import matplotlib; import seaborn; import pandas; print('OK')"

# Check data availability
ls -la data/processed/
ls -la output/fin-experiments/
```

```python
# Verify output directories exist
import os
output_base = "output/fin-manuscript/draft_v1"
figure_dir = f"{output_base}/figures"
os.makedirs(figure_dir, exist_ok=True)
print(f"Figure output directory: {figure_dir}")
```

## Step 1: Read Input Files

Read the figure plan and actual data:

```python
import pandas as pd
from pathlib import Path

# Read FIGURE_PLAN.md
outline_path = Path("output/fin-manuscript/draft_v1/FIGURE_PLAN.md")
if outline_path.exists():
    figure_plan = outline_path.read_text(encoding="utf-8")
    print("Read FIGURE_PLAN.md")

# Read TABLE_PLAN.md for reference
table_plan_path = Path("output/fin-manuscript/draft_v1/TABLE_PLAN.md")
if table_plan_path.exists():
    table_plan = table_plan_path.read_text(encoding="utf-8")

# Read PAPER_OUTLINE.md to determine journal style
outline_path = Path("output/fin-manuscript/draft_v1/PAPER_OUTLINE.md")
if outline_path.exists():
    paper_outline = outline_path.read_text(encoding="utf-8")
    # Extract target journal
    # target_journal = extract_journal(paper_outline)
```

## Step 2: Configure Chart Settings

Set up the `ChartConfig` based on the target journal:

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class JournalStyle(Enum):
    CHINESE_TOP = "chinese_top"      # 经济研究/金融研究/管理世界
    AEA = "aea"                       # AER/JF/JFE/RFS
    CHICAGO = "chicago"               # JPE
    IEEE = "ieee"                     # 通用英文


@dataclass
class ChartConfig:
    """Configuration for academic figure generation."""
    # Canvas
    figsize: tuple = (8, 5.5)          # width, height in inches
    dpi: int = 300                     # dots per inch (publication standard)
    tight_layout: bool = True
    
    # Font (critical for Chinese journals)
    font_family: str = "Times New Roman"  # English journals
    font_size: int = 10
    title_fontsize: int = 12
    label_fontsize: int = 10
    legend_fontsize: int = 9
    tick_fontsize: int = 9
    
    # Colors
    color_palette: str = "colorblind"  # "Set2" for Chinese printing
    primary_color: str = "#2E86AB"      # Blue
    secondary_color: str = "#F6AE2D"   # Orange
    accent_color: str = "#E94F37"      # Red for policy year
    ci_color: str = "#2E86AB"          # Confidence interval fill
    
    # Output
    output_formats: List[str] = None   # ["pdf", "png", "svg"]
    style: str = "seaborn-v0_8-paper"
    
    # Grid
    grid_alpha: float = 0.3
    grid_linestyle: str = "--"
    
    # Line styles
    line_width: float = 1.5
    marker_size: float = 5
    ci_alpha: float = 0.2
    
    def __post_init__(self):
        if self.output_formats is None:
            self.output_formats = ["pdf", "png"]


# Chinese journal configuration (经济研究/金融研究/管理世界)
CHINESE_CONFIG = ChartConfig(
    figsize=(8, 5.5),
    dpi=300,
    font_family="SimHei",
    font_size=10,
    title_fontsize=12,
    label_fontsize=10,
    legend_fontsize=9,
    tick_fontsize=9,
    color_palette="Set2",      # Better for Chinese printing
    primary_color="#2E86AB",
    secondary_color="#F6AE2D",
    accent_color="#E94F37",
    ci_color="#2E86AB",
    output_formats=["pdf", "png"],
    style="seaborn-v0_8-paper",
    grid_alpha=0.3,
    grid_linestyle="--",
    line_width=1.5,
    marker_size=5,
    ci_alpha=0.2,
)

# English top journal configuration (JF/JFE/RFS/AER)
ENGLISH_CONFIG = ChartConfig(
    figsize=(7, 5),
    dpi=300,
    font_family="Times New Roman",
    font_size=10,
    title_fontsize=12,
    label_fontsize=10,
    legend_fontsize=9,
    tick_fontsize=9,
    color_palette="colorblind",
    primary_color="#4472C4",
    secondary_color="#ED7D31",
    accent_color="#C00000",
    ci_color="#4472C4",
    output_formats=["pdf", "png"],
    style="seaborn-v0_8-paper",
    grid_alpha=0.3,
    grid_linestyle="--",
    line_width=1.5,
    marker_size=5,
    ci_alpha=0.2,
)
```

## Step 3: Set Up FinancialChartFactory

```python
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime


class FinancialChartFactory:
    """
    Factory for generating publication-quality academic figures
    in economics and finance.
    """
    
    def __init__(self, output_dir: str, config: ChartConfig):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self._apply_style()
        self._setup_fonts()
    
    def _apply_style(self):
        """Apply matplotlib style settings."""
        plt.style.use(self.config.style)
        sns.set_palette(self.config.color_palette)
    
    def _setup_fonts(self):
        """Configure fonts for the target journal."""
        if self.config.font_family == "SimHei":
            # Chinese font setup
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Heiti TC', 'Arial Unicode MS']
            plt.rcParams['axes.unicode_minus'] = False
        else:
            # English font setup
            plt.rcParams['font.family'] = ['Times New Roman']
        plt.rcParams['font.size'] = self.config.font_size
        plt.rcParams['axes.titlesize'] = self.config.title_fontsize
        plt.rcParams['axes.labelsize'] = self.config.label_fontsize
        plt.rcParams['xtick.labelsize'] = self.config.tick_fontsize
        plt.rcParams['ytick.labelsize'] = self.config.tick_fontsize
    
    def _save(self, fig, filename: str):
        """Save figure in multiple formats."""
        base_path = self.output_dir / filename.replace(".pdf", "").replace(".png", "")
        for fmt in self.config.output_formats:
            path = base_path.with_suffix(f".{fmt}")
            fig.savefig(path, dpi=self.config.dpi, bbox_inches='tight', 
                       format=fmt)
            print(f"  Saved: {path}")
    
    def _add_publication_style(self, ax, xlabel: str = "", ylabel: str = "",
                               title: str = "", grid: bool = True):
        """Apply consistent publication styling to a plot."""
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=self.config.label_fontsize)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=self.config.label_fontsize)
        if title:
            ax.set_title(title, fontsize=self.config.title_fontsize, 
                        fontweight='bold')
        if grid:
            ax.grid(True, alpha=self.config.grid_alpha, 
                    linestyle=self.config.grid_linestyle)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
    
    def plot_parallel_trends(self, df: pd.DataFrame,
                             time_var: str = "relative_time",
                             treat_var: str = "did",
                             y_var: str = "y",
                             ci_level: float = 0.95,
                             save_path: str = "parallel_trends.pdf",
                             title: str = "Parallel Trends Test") -> plt.Figure:
        """
        Plot parallel trends / event study figure for DID designs.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with columns: relative_time, y (point estimate), y_se (std err)
        time_var : str
            Column name for relative time (e.g., -5 to +5)
        treat_var : str
            Column name for treatment indicator (unused, kept for API compatibility)
        y_var : str
            Column name for the outcome variable
        ci_level : float
            Confidence interval level (default 0.95)
        save_path : str
            Output filename
        title : str
            Figure title
        
        Returns
        -------
        plt.Figure
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        # Compute confidence interval
        z = 1.96 if ci_level == 0.95 else 1.645
        df = df.copy()
        if 'y_se' in df.columns:
            df['ci_upper'] = df[y_var] + z * df['y_se']
            df['ci_lower'] = df[y_var] - z * df['y_se']
        
        # Determine pre/post split
        if time_var in df.columns:
            time_col = time_var
        else:
            time_col = df.columns[0]
        
        # Plot point estimates
        ax.plot(df[time_col], df[y_var], 
                color=self.config.primary_color,
                linewidth=self.config.line_width,
                marker='o',
                markersize=self.config.marker_size,
                label='DID Estimate')
        
        # Plot confidence interval
        if 'ci_upper' in df.columns:
            ax.fill_between(df[time_col], df['ci_lower'], df['ci_upper'],
                          color=self.config.primary_color,
                          alpha=self.config.ci_alpha,
                          label='95% CI')
        
        # Add vertical line at policy year (time=0)
        if 0 in df[time_col].values:
            ax.axvline(x=0, color=self.config.accent_color,
                      linestyle='--', linewidth=1.5,
                      label='Policy Year')
        
        # Add horizontal line at y=0
        ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
        
        # Reference line at 0 for pre-period (should be near 0 if parallel holds)
        ax.set_xlabel('Relative Time (Years)', fontsize=self.config.label_fontsize)
        ax.set_ylabel('DID Coefficient', fontsize=self.config.label_fontsize)
        ax.set_title(title, fontsize=self.config.title_fontsize, fontweight='bold')
        
        self._add_publication_style(ax)
        ax.legend(loc='best', fontsize=self.config.legend_fontsize)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
```

## Step 4: Figure Generation Functions

### 4.1 DID专用图 (DID Event Study)

```python
    def plot_cumulative_effect(self, df: pd.DataFrame,
                               event_window: str = "relative_week",
                               car: str = "car",
                               se: Optional[str] = None,
                               save_path: str = "cumulative_effect.pdf",
                               title: str = "Cumulative Abnormal Returns") -> plt.Figure:
        """
        Plot cumulative abnormal returns (CAR) event study.
        Used for short-window event studies around policy announcements.
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        z = 1.96
        df = df.copy()
        
        # Compute CAR if not provided
        if car not in df.columns and 'car' in df.columns:
            df[car] = df['car']
        
        if event_window not in df.columns:
            ax.plot(df.index, df[car], color=self.config.primary_color,
                   linewidth=self.config.line_width, marker='o',
                   markersize=self.config.marker_size)
        else:
            ax.plot(df[event_window], df[car],
                   color=self.config.primary_color,
                   linewidth=self.config.line_width, marker='o',
                   markersize=self.config.marker_size)
        
        # Add CI if SE provided
        if se and se in df.columns:
            upper = df[car] + z * df[se]
            lower = df[car] - z * df[se]
            if event_window in df.columns:
                ax.fill_between(df[event_window], lower, upper,
                              color=self.config.primary_color, alpha=self.config.ci_alpha)
            else:
                ax.fill_between(df.index, lower, upper,
                              color=self.config.primary_color, alpha=self.config.ci_alpha)
        
        # Event window boundaries
        ax.axvline(x=0, color=self.config.accent_color, linestyle='--', linewidth=1.5)
        ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
        
        self._add_publication_style(ax, ylabel="Cumulative Return (%)",
                                    title=title)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
    
    def plot_placebo_distribution(self, coefs: np.ndarray,
                                  true_coef: float,
                                  save_path: str = "placebo.pdf",
                                  title: str = "Placebo Test",
                                  xlabel: str = "Estimated Coefficient",
                                  n_simulations: int = 500) -> plt.Figure:
        """
        Plot histogram of placebo (randomized) coefficients with true coefficient marked.
        
        Parameters
        ----------
        coefs : np.ndarray
            Array of estimated coefficients from placebo tests
        true_coef : float
            The actual estimated coefficient from the main regression
        save_path : str
            Output filename
        title : str
            Figure title
        xlabel : str
            X-axis label
        n_simulations : int
            Number of placebo simulations (for caption)
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        # Histogram of placebo coefficients
        n, bins, patches = ax.hist(coefs, bins=30, color=self.config.primary_color,
                                   alpha=0.7, edgecolor='white', linewidth=0.5)
        
        # Mark the true coefficient
        ymax = ax.get_ylim()[1]
        ax.axvline(x=true_coef, color=self.config.accent_color,
                  linestyle='--', linewidth=2.0,
                  label=f'True Effect = {true_coef:.3f}')
        
        # Mark 95th percentile of placebo distribution
        p95 = np.percentile(coefs, 95)
        ax.axvline(x=p95, color='gray', linestyle=':', linewidth=1.5,
                  label=f'95th Pct = {p95:.3f}')
        
        ax.set_xlabel(xlabel, fontsize=self.config.label_fontsize)
        ax.set_ylabel('Frequency', fontsize=self.config.label_fontsize)
        ax.set_title(title, fontsize=self.config.title_fontsize, fontweight='bold')
        
        self._add_publication_style(ax)
        
        # Legend
        ax.legend(loc='upper right', fontsize=self.config.legend_fontsize)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
    
    def plot_robustness_summary(self, results_dict: Dict[str, Tuple[float, float]],
                                 save_path: str = "robustness_forest.pdf",
                                 title: str = "Robustness Check Results",
                                 true_coef: Optional[float] = None) -> plt.Figure:
        """
        Forest plot summarizing robustness check coefficients.
        
        Parameters
        ----------
        results_dict : dict
            Dictionary mapping test names to (coef, se) tuples
        save_path : str
            Output filename
        title : str
            Figure title
        true_coef : float, optional
            The baseline coefficient to compare against
        """
        names = list(results_dict.keys())
        coefs = [v[0] for v in results_dict.values()]
        ses = [v[1] for v in results_dict.values()]
        
        # Sort by coefficient value
        sorted_pairs = sorted(zip(names, coefs, ses), key=lambda x: x[1])
        names, coefs, ses = zip(*sorted_pairs)
        
        y_pos = np.arange(len(names))
        z = 1.96
        
        fig, ax = plt.subplots(figsize=(7, max(4, len(names) * 0.4)))
        
        # Horizontal dot plot
        ax.scatter(coefs, y_pos, color=self.config.primary_color,
                  s=50, zorder=3)
        
        # CI whiskers
        for i, (c, s) in enumerate(zip(coefs, ses)):
            ax.plot([c - z*s, c + z*s], [i, i],
                   color=self.config.primary_color, linewidth=1.5)
            ax.plot([c - z*s, c - z*s], [i - 0.1, i + 0.1],
                   color=self.config.primary_color, linewidth=1.5)
            ax.plot([c + z*s, c + z*s], [i - 0.1, i + 0.1],
                   color=self.config.primary_color, linewidth=1.5)
        
        # Reference line
        if true_coef is not None:
            ax.axvline(x=true_coef, color=self.config.accent_color,
                      linestyle='--', linewidth=1.5, label=f'Baseline = {true_coef:.3f}')
        ax.axvline(x=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names, fontsize=self.config.tick_fontsize)
        ax.set_xlabel('Coefficient Estimate', fontsize=self.config.label_fontsize)
        ax.set_title(title, fontsize=self.config.title_fontsize, fontweight='bold')
        
        self._add_publication_style(ax)
        
        if true_coef is not None:
            ax.legend(loc='upper right', fontsize=self.config.legend_fontsize)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
```

### 4.2 异质性分析图

```python
    def plot_heterogeneity(self, df: pd.DataFrame,
                           group_col: str,
                           y_var: str,
                           se_var: Optional[str] = None,
                           save_path: str = "heterogeneity.pdf",
                           title: str = "Heterogeneity Analysis",
                           ylabel: str = "DID Coefficient",
                           xlabel: str = "Group") -> plt.Figure:
        """
        Grouped bar chart for heterogeneity analysis.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with group_col, y_var, and optionally se_var
        group_col : str
            Column for grouping (e.g., 'size_group', 'soe', 'industry')
        y_var : str
            Column for the coefficient/estimate
        se_var : str, optional
            Column for standard error (for CI whiskers)
        save_path : str
            Output filename
        title : str
            Figure title
        ylabel : str
            Y-axis label
        xlabel : str
            X-axis label
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        groups = df[group_col].unique()
        x_pos = np.arange(len(groups))
        
        # Colors
        colors = sns.color_palette(self.config.color_palette, n_colors=len(groups))
        
        bars = ax.bar(x_pos, df[y_var], color=colors,
                     width=0.6, edgecolor='white', linewidth=0.5)
        
        # Add CI whiskers if SE provided
        if se_var:
            z = 1.96
            for i, (bar, se) in enumerate(zip(bars, df[se_var])):
                ax.plot([bar.get_x() + bar.get_width()/2, 
                        bar.get_x() + bar.get_width()/2],
                       [bar.get_height() - z*se, bar.get_height() + z*se],
                       color='black', linewidth=1.0)
                ax.plot([bar.get_x() + bar.get_width()/2 - 0.05,
                        bar.get_x() + bar.get_width()/2 + 0.05],
                       [bar.get_height() + z*se, bar.get_height() + z*se],
                       color='black', linewidth=1.0)
                ax.plot([bar.get_x() + bar.get_width()/2 - 0.05,
                        bar.get_x() + bar.get_width()/2 + 0.05],
                       [bar.get_height() - z*se, bar.get_height() - z*se],
                       color='black', linewidth=1.0)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.3f}',
                   ha='center', va='bottom', fontsize=self.config.tick_fontsize)
        
        ax.set_xticks(x_pos)
        ax.set_xticklabels(groups, fontsize=self.config.tick_fontsize,
                          rotation=15 if len(groups) > 4 else 0)
        ax.set_ylabel(ylabel, fontsize=self.config.label_fontsize)
        ax.set_xlabel(xlabel, fontsize=self.config.label_fontsize)
        ax.set_title(title, fontsize=self.config.title_fontsize, fontweight='bold')
        
        self._add_publication_style(ax, grid=False)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
    
    def plot_marginal_effects(self, df: pd.DataFrame,
                              x_var: str,
                              marginal_effect: str,
                              se: Optional[str] = None,
                              save_path: str = "marginal_effects.pdf",
                              title: str = "Marginal Effects",
                              xlabel: Optional[str] = None,
                              ylabel: str = "Marginal Effect") -> plt.Figure:
        """
        Plot marginal effects with confidence intervals.
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        z = 1.96
        ax.plot(df[x_var], df[marginal_effect],
               color=self.config.primary_color,
               linewidth=self.config.line_width,
               marker='o', markersize=self.config.marker_size)
        
        if se and se in df.columns:
            upper = df[marginal_effect] + z * df[se]
            lower = df[marginal_effect] - z * df[se]
            ax.fill_between(df[x_var], lower, upper,
                          color=self.config.primary_color,
                          alpha=self.config.ci_alpha)
        
        ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
        
        self._add_publication_style(ax,
                                   xlabel=xlabel or x_var,
                                   ylabel=ylabel,
                                   title=title)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
```

### 4.3 资产定价图

```python
    def plot_factor_returns(self, df: pd.DataFrame,
                           date_col: str = "date",
                           factor_cols: List[str] = None,
                           save_path: str = "factor_returns.pdf",
                           title: str = "Factor Cumulative Returns",
                           factor_names: Optional[Dict[str, str]] = None) -> plt.Figure:
        """
        Plot cumulative factor returns over time.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with date column and factor return columns
        date_col : str
            Column name for dates
        factor_cols : list
            List of factor column names (e.g., ['mkt_rf', 'smb', 'hml'])
        save_path : str
            Output filename
        title : str
            Figure title
        factor_names : dict, optional
            Mapping from factor_cols to display names
        """
        if factor_cols is None:
            factor_cols = ['mkt_rf', 'smb', 'hml']
        if factor_names is None:
            factor_names = {}
        
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        colors = sns.color_palette(self.config.color_palette, n_colors=len(factor_cols))
        
        for i, col in enumerate(factor_cols):
            cumulative = (1 + df[col]/100).cumprod()
            label = factor_names.get(col, col)
            ax.plot(df[date_col], cumulative,
                   color=colors[i], linewidth=self.config.line_width,
                   label=label)
        
        ax.axhline(y=1, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
        
        ax.set_xlabel('Date', fontsize=self.config.label_fontsize)
        ax.set_ylabel('Cumulative Return (Starting at 1)', fontsize=self.config.label_fontsize)
        ax.set_title(title, fontsize=self.config.title_fontsize, fontweight='bold')
        
        self._add_publication_style(ax)
        ax.legend(loc='best', fontsize=self.config.legend_fontsize,
                 framealpha=0.9)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
    
    def plot_correlation_matrix(self, df: pd.DataFrame,
                                var_cols: List[str],
                                save_path: str = "corr_heatmap.pdf",
                                title: str = "Correlation Matrix",
                                method: str = 'pearson',
                                annot: bool = True,
                                fmt: str = '.2f') -> plt.Figure:
        """
        Plot correlation matrix as a heatmap.
        """
        corr = df[var_cols].corr(method=method)
        
        fig, ax = plt.subplots(figsize=(max(6, len(var_cols) * 0.8),
                                        max(5, len(var_cols) * 0.8)))
        
        mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
        
        cmap = sns.diverging_palette(220, 10, as_cmap=True)
        
        sns.heatmap(corr, mask=mask, cmap=cmap, center=0,
                   annot=annot, fmt=fmt, square=True,
                   linewidths=0.5, ax=ax,
                   cbar_kws={"shrink": 0.8},
                   annot_kws={"size": self.config.tick_fontsize - 1})
        
        ax.set_title(title, fontsize=self.config.title_fontsize, fontweight='bold',
                    pad=10)
        
        plt.xticks(rotation=45, ha='right',
                  fontsize=self.config.tick_fontsize)
        plt.yticks(rotation=0,
                  fontsize=self.config.tick_fontsize)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
    
    def plot_time_series(self, df: pd.DataFrame,
                        date_col: str,
                        value_col: str,
                        save_path: str = "time_series.pdf",
                        title: str = "Time Series",
                        ylabel: Optional[str] = None,
                        xlabel: str = "Date",
                        hline_value: Optional[float] = None,
                        hline_label: Optional[str] = None) -> plt.Figure:
        """
        Plot generic time series with optional reference line.
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)
        
        ax.plot(df[date_col], df[value_col],
               color=self.config.primary_color,
               linewidth=self.config.line_width)
        
        if hline_value is not None:
            ax.axhline(y=hline_value, color=self.config.accent_color,
                      linestyle='--', linewidth=1.5,
                      label=hline_label or f'{hline_value}')
            ax.legend(loc='best', fontsize=self.config.legend_fontsize)
        
        self._add_publication_style(ax,
                                   xlabel=xlabel,
                                   ylabel=ylabel or value_col,
                                   title=title)
        
        self._save(fig, save_path)
        plt.close(fig)
        return fig
```

## Step 5: Provenance Tracking

Record data lineage for every figure:

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List
import json


@dataclass
class ProvenanceRecord:
    """Record of data provenance for a generated figure."""
    entity: str                           # e.g., "figure:parallel_trends"
    source: str                           # e.g., "empirical_results.dta"
    transformation: str                    # e.g., "event_study_regression"
    timestamp: str                         # ISO format datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    output_files: List[str] = field(default_factory=list)
    data_hash: Optional[str] = None       # hash of source data
    figure_code: Optional[str] = None     # snippet of plotting code
    notes: Optional[str] = None


class ProvenanceTracker:
    """
    Track provenance for all generated figures.
    Ensures reproducibility and data lineage.
    """
    
    def __init__(self, output_path: str = "output/fin-manuscript/draft_v1/provenance.json"):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.records: List[ProvenanceRecord] = []
        self._load_existing()
    
    def _load_existing(self):
        """Load existing provenance records."""
        if self.output_path.exists():
            with open(self.output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.records = [ProvenanceRecord(**r) for r in data.get("records", [])]
    
    def _save(self):
        """Save provenance records to JSON."""
        data = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "records": [asdict(r) for r in self.records]
        }
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def record(self,
               entity: str,
               source: str,
               transformation: str,
               parameters: Optional[Dict[str, Any]] = None,
               output_files: Optional[List[str]] = None,
               data_hash: Optional[str] = None,
               figure_code: Optional[str] = None,
               notes: Optional[str] = None):
        """
        Record a provenance entry for a generated figure.
        """
        record = ProvenanceRecord(
            entity=entity,
            source=source,
            transformation=transformation,
            timestamp=datetime.now().isoformat(),
            parameters=parameters or {},
            output_files=output_files or [],
            data_hash=data_hash,
            figure_code=figure_code,
            notes=notes,
        )
        self.records.append(record)
        self._save()
        print(f"  Provenance recorded: {entity}")
```

## Step 6: Generate All Figures from FIGURE_PLAN.md

Main execution script:

```python
#!/usr/bin/env python3
"""Generate all figures from FIGURE_PLAN.md."""

import pandas as pd
import numpy as np
from pathlib import Path
from financial_chart_factory import FinancialChartFactory, ChartConfig, ProvenanceTracker


def main():
    # === Configuration ===
    output_dir = "output/fin-manuscript/draft_v1"
    figure_dir = f"{output_dir}/figures"
    data_dir = "output/fin-experiments"
    
    # Detect journal style from PAPER_OUTLINE.md
    outline_file = Path(f"{output_dir}/PAPER_OUTLINE.md")
    if outline_file.exists():
        content = outline_file.read_text(encoding="utf-8")
        if "经济研究" in content or "金融研究" in content or "管理世界" in content:
            config = ChartConfig(
                figsize=(8, 5.5),
                dpi=300,
                font_family="SimHei",
                color_palette="Set2",
            )
        else:
            config = ChartConfig(
                figsize=(7, 5),
                dpi=300,
                font_family="Times New Roman",
                color_palette="colorblind",
            )
    else:
        config = ChartConfig()
    
    # Initialize factory and tracker
    factory = FinancialChartFactory(figure_dir, config)
    tracker = ProvenanceTracker(output_path=f"{output_dir}/provenance.json")
    
    print("=" * 60)
    print("Generating Academic Figures")
    print(f"Output directory: {figure_dir}")
    print(f"Journal config: {config.font_family}, {config.dpi} DPI")
    print("=" * 60)
    
    # === 图4-1: 平行趋势检验 ===
    print("\n[1/4] Generating parallel trends figure...")
    try:
        pt_data = pd.read_stata(f"{data_dir}/parallel_trends.dta")
        factory.plot_parallel_trends(
            df=pt_data,
            time_var="relative_time",
            y_var="did_coef",
            save_path="fig_parallel_trends.pdf",
            title="Parallel Trends Test"
        )
        tracker.record(
            entity="figure:parallel_trends",
            source=f"{data_dir}/parallel_trends.dta",
            transformation="event_study_regression",
            parameters={"ci_level": 0.95},
            output_files=[f"{figure_dir}/fig_parallel_trends.pdf"],
        )
    except Exception as e:
        print(f"  ⚠ Could not generate: {e}")
    
    # === 图4-2: 动态效应 ===
    print("\n[2/4] Generating dynamic effects figure...")
    try:
        dyn_data = pd.read_stata(f"{data_dir}/dynamic_effects.dta")
        factory.plot_cumulative_effect(
            df=dyn_data,
            event_window="relative_year",
            car="car",
            se="car_se",
            save_path="fig_dynamic_effects.pdf",
            title="Dynamic Treatment Effects"
        )
    except Exception as e:
        print(f"  ⚠ Could not generate: {e}")
    
    # === 图5-1: 安慰剂检验 ===
    print("\n[3/4] Generating placebo test figure...")
    try:
        placebo_coefs = np.load(f"{data_dir}/placebo_coefs.npy")
        baseline_coef = 0.052  # from main regression
        factory.plot_placebo_distribution(
            coefs=placebo_coefs,
            true_coef=baseline_coef,
            save_path="fig_placebo.pdf",
            title="Placebo Test (500 Simulations)",
            xlabel="Estimated DID Coefficient",
            n_simulations=500
        )
    except Exception as e:
        print(f"  ⚠ Could not generate: {e}")
    
    # === 图4-3: 异质性分析 ===
    print("\n[4/4] Generating heterogeneity figure...")
    try:
        het_data = pd.read_stata(f"{data_dir}/heterogeneity_results.dta")
        factory.plot_heterogeneity(
            df=het_data,
            group_col="size_group",
            y_var="did_coef",
            se_var="did_se",
            save_path="fig_het_size.pdf",
            title="Heterogeneity by Firm Size",
            ylabel="DID Coefficient",
            xlabel="Size Quintile"
        )
    except Exception as e:
        print(f"  ⚠ Could not generate: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Figure generation complete!")
    print(f"Output: {figure_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

## Step 7: Quick Reference — Chart Types

| Figure Type | Method | Use Case |
|-------------|--------|----------|
| Event Study / Parallel Trends | `plot_parallel_trends()` | DID identification check |
| Cumulative Effect | `plot_cumulative_effect()` | CAR / cumulative shock response |
| Forest Plot | `plot_robustness_summary()` | Multiple robustness coefficients |
| Placebo Distribution | `plot_placebo_distribution()` | Randomization inference |
| Grouped Bar | `plot_heterogeneity()` | Heterogeneous treatment effects |
| Marginal Effects | `plot_marginal_effects()` | Continuous moderator |
| Factor Returns | `plot_factor_returns()` | Asset pricing factor performance |
| Correlation Heatmap | `plot_correlation_matrix()` | Variable correlation overview |
| Time Series | `plot_time_series()` | Macro indicators, portfolio returns |

## Output Summary

After generation, print a summary:

```
✅ FIGURES GENERATED

Figures: 4
Output: output/fin-manuscript/draft_v1/figures/

├── fig_parallel_trends.pdf  (8.0 x 5.5 in, 300 DPI)
├── fig_dynamic_effects.pdf   (8.0 x 5.5 in, 300 DPI)
├── fig_placebo.pdf           (8.0 x 5.5 in, 300 DPI)
└── fig_het_size.pdf          (8.0 x 5.5 in, 300 DPI)

Provenance: output/fin-manuscript/draft_v1/provenance.json
```

---

## ChartConfig Quick Reference

```python
# For Chinese journals (经济研究/金融研究/管理世界)
config = ChartConfig(
    font_family="SimHei",        # Critical: Chinese characters
    font_size=10,
    title_fontsize=12,
    label_fontsize=10,
    color_palette="Set2",        # Colorblind-safe for Chinese printing
    dpi=300,                     # Publication standard
    figsize=(8, 5.5),           # Standard academic ratio
)

# For English journals (JF/JFE/RFS/AER)
config = ChartConfig(
    font_family="Times New Roman",
    font_size=10,
    title_fontsize=12,
    label_fontsize=10,
    color_palette="colorblind",
    dpi=300,
    figsize=(7, 5),
)
```
