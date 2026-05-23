#!/usr/bin/env python3
"""
研报生成器
==========
将结构化数据自动填充到研报模板，生成 Markdown / HTML / PDF 格式的研报。

功能：
- 财务数据自动填充
- 图表嵌入（matplotlib / plotly）
- 多格式输出
"""

import os
import json
import warnings
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")   # 必须在 import pyplot 之前
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")


# ─── 配置 ────────────────────────────────────────────────
CONFIG_DIR = Path(__file__).parent.parent / "config"
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def load_llm_config():
    with open(CONFIG_DIR / "llm_config.json") as f:
        return json.load(f)


# ─── 图表风格配置 ────────────────────────────────────────

FINANCIAL_STYLE = {
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.size": 9,
    "legend.fontsize": 8,
    "lines.linewidth": 1.5,
}


def setup_financial_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "font.size": 9,
        "legend.fontsize": 8,
        "lines.linewidth": 1.5,
        "text.color": "#333333",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def save_figure(fig, filename: str, dir_path: str = "figures"):
    """保存图表到指定目录。"""
    output_dir = Path(dir_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path, bbox_inches="tight", dpi=300, facecolor="white")
    plt.close(fig)
    return str(path)


# ─── 图表生成函数 ────────────────────────────────────────

def plot_income_trend(df: pd.DataFrame, year_col: str, revenue_col: str,
                       profit_col: str, output_path: str = "figures") -> str:
    """收入与利润趋势图。"""
    setup_financial_style()
    fig, ax = plt.subplots(figsize=(8, 4))

    ax.plot(df[year_col], df[revenue_col], marker="o", label="营业收入", color="#1f3a5f")
    ax.plot(df[year_col], df[profit_col], marker="s", label="净利润", color="#f5a623")

    ax.set_xlabel("年度")
    ax.set_ylabel("金额（亿元）")
    ax.set_title("营业收入与净利润趋势")
    ax.legend()
    ax.grid(True, alpha=0.3)

    return save_figure(fig, "income_trend.png", output_path)


def plot_roe_duPont(df: pd.DataFrame, years: list, roe_values: list,
                     output_path: str = "figures") -> str:
    """ROE 杜邦分析趋势图。"""
    setup_financial_style()
    fig, ax = plt.subplots(figsize=(7, 4))

    bars = ax.bar(years, roe_values, color="#4a90d9", alpha=0.85, edgecolor="white")
    for bar, val in zip(bars, roe_values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("年度")
    ax.set_ylabel("ROE (%)")
    ax.set_title("净资产收益率（ROE）趋势")
    ax.axhline(y=np.mean(roe_values), color="red", linestyle="--", alpha=0.5, label=f"均值 {np.mean(roe_values):.1f}%")
    ax.legend()

    return save_figure(fig, "roe_trend.png", output_path)


def plot_valuation_comparison(companies: list, metrics: dict,
                                output_path: str = "figures") -> str:
    """
    可比公司估值对比图。

    Args:
        companies: 公司列表
        metrics: dict，如 {"PE": [12.5, 15.2, 18.1], "PB": [1.2, 1.5, 1.8]}
    """
    setup_financial_style()
    n_metrics = len(metrics)
    fig, axes = plt.subplots(1, n_metrics, figsize=(5 * n_metrics, 4))

    if n_metrics == 1:
        axes = [axes]

    colors = ["#1f3a5f", "#4a90d9", "#f5a623", "#6ab04c"]

    for ax, (metric_name, values) in zip(axes, metrics.items()):
        bars = ax.bar(companies, values, color=colors[:len(companies)], alpha=0.85, edgecolor="white")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=8)
        ax.set_title(f"{metric_name} 估值对比", fontproperties=None)
        ax.set_ylabel(metric_name)
        ax.tick_params(axis="x", rotation=15)

    plt.tight_layout()
    return save_figure(fig, "valuation_comparison.png", output_path)


def plot_dcf_sensitivity(base_value: float, param1_vals: list, param2_vals: list,
                           matrix: np.ndarray, output_path: str = "figures") -> str:
    """DCF 敏感性分析热力图。"""
    setup_financial_style()
    fig, ax = plt.subplots(figsize=(7, 5))

    im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(param2_vals)))
    ax.set_yticks(range(len(param1_vals)))
    ax.set_xticklabels([f"{v:.1f}%" for v in param2_vals])
    ax.set_yticklabels([f"{v:.1f}%" for v in param1_vals])
    ax.set_xlabel("WACC 假设")
    ax.set_ylabel("永续增长率假设")
    ax.set_title("DCF 估值敏感性分析")

    for i in range(len(param1_vals)):
        for j in range(len(param2_vals)):
            color = "white" if matrix[i, j] < base_value * 0.85 or matrix[i, j] > base_value * 1.15 else "black"
            ax.text(j, i, f"{matrix[i, j]:.0f}", ha="center", va="center", color=color, fontsize=8)

    plt.colorbar(im, ax=ax, label="估值（元）")
    return save_figure(fig, "dcf_sensitivity.png", output_path)


# ─── 研报生成器 ──────────────────────────────────────────

class ReportGenerator:
    """研报生成器。"""

    def __init__(self, template_path: str = None):
        if template_path is None:
            template_path = TEMPLATE_DIR / "research_report.md"
        if not Path(template_path).exists():
            raise FileNotFoundError(
                f"研报模板不存在: {template_path}\n"
                f"请确认 templates/research_report.md 文件存在。"
            )
        with open(template_path, encoding="utf-8") as f:
            self.template = f.read()

    def fill_financial_data(self, data: dict) -> str:
        """填充财务数据到模板。"""
        content = self.template
        for key, value in data.items():
            placeholder = f"{{{key}}}"
            if placeholder in content:
                if isinstance(value, (int, float)):
                    content = content.replace(placeholder, f"{value:,.2f}")
                else:
                    content = content.replace(placeholder, str(value))
        return content

    def add_figure_md(self, figure_path: str, caption: str = "") -> str:
        """生成 Markdown 格式的图表引用。"""
        filename = os.path.basename(figure_path)
        return f'\n![{caption}]({figure_path})\n'

    def generate(self, company_name: str, financial_data: dict,
                  output_dir: str = "reports") -> dict:
        """
        生成完整研报。

        Returns:
            dict，包含 "markdown", "html" 文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        company_safe = company_name.replace("*", "").replace("/", "")

        financial_data.setdefault("company_name", company_name)
        financial_data.setdefault("report_date", datetime.now().strftime("%Y-%m-%d"))
        financial_data.setdefault("analyst", "")
        financial_data.setdefault("data_date", datetime.now().strftime("%Y-%m-%d"))

        md_content = self.fill_financial_data(financial_data)

        md_path = output_dir / f"{company_safe}_{timestamp}.md"
        html_path = output_dir / f"{company_safe}_{timestamp}.html"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        import markdown
        html_body = markdown.markdown(md_content, extensions=["tables", "fenced_code"])
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 900px; margin: 2rem auto; padding: 0 2rem;
         line-height: 1.8; color: #333; }}
h1 {{ color: #1f3a5f; border-bottom: 2px solid #1f3a5f; padding-bottom: 0.5rem; }}
h2 {{ color: #4a90d9; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th {{ background: #1f3a5f; color: white; padding: 8px; }}
td {{ padding: 8px; border: 1px solid #ddd; }}
tr:nth-child(even) {{ background: #f8f9fa; }}
img {{ max-width: 100%; border: 1px solid #eee; }}
blockquote {{ border-left: 4px solid #4a90d9; padding-left: 1rem; color: #666; }}
</style></head><body>{html_body}</body></html>"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        print(f"[✓] 研报已生成:")
        print(f"    Markdown: {md_path}")
        print(f"    HTML:     {html_path}")

        return {"markdown": str(md_path), "html": str(html_path)}


# ─── 演示 ────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    os.makedirs("reports", exist_ok=True)
    os.makedirs("figures", exist_ok=True)

    gen = ReportGenerator()

    # 演示图表生成
    df_financial = pd.DataFrame({
        "year": [2021, 2022, 2023, 2024],
        "revenue": [100, 120, 145, 170],
        "profit": [15, 18, 22, 28],
    })
    fig_path = plot_income_trend(df_financial, "year", "revenue", "profit")
    print(f"图表已保存: {fig_path}")

    # 演示研报生成
    sample_data = {
        "company_name": "示例公司",
        "report_date": "2026-05-19",
        "revenue_2024": 170.5,
        "profit_2024": 28.3,
        "roe_2024": 15.2,
        "target_price": 25.6,
        "current_price": 20.3,
        "upside": 26.1,
        "rating": "增持",
        "analyst": "AI 分析师",
        "data_date": "2026-05-19",
    }
    gen.generate("示例公司", sample_data, output_dir="reports")
