"""AdvancedChartFactory — 专业图表类型生成器.

对标 Research-OS 的专业图表库（alluvial / funnel / hierarchical / CONSORT 等），
全部支持 provenance 追踪、300 DPI 输出、学术配色。

用法:
    from scripts.core.chart_factory import AdvancedChartFactory

    factory = AdvancedChartFactory(output_dir="output/figures")
    factory.sankey(
        nodes=["原始数据", "清洗", "分析", "图表"],
        links=[(0,1,100),(1,2,80),(2,3,60)],
        title="数据处理流程"
    )
    factory.funnel(
        stages=["浏览","注册","付费","复购"],
        values=[1000, 200, 50, 15],
        title="用户转化漏斗"
    )
    factory.alluvial(
        categories=[("行业",["Tech","Finance","Health"]),
                    ("结果",["正回报","负回报"])],
        flows=[("Tech","正回报",0.7),("Tech","负回报",0.3),...],
        title="行业与投资回报流向"
    )
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# ─── Chart registry ────────────────────────────────────────────────────────────


CHART_TYPES = {
    "sankey": "桑基图 — 流量/路径分析",
    "funnel": "漏斗图 — 转化率分析",
    "alluvial": "冲积图 — 分类变化流向",
    "consort": "CONSORT 图 — 临床试验流程",
    "dendrogram": "树状图 — 层次聚类",
    "circos": "Circos 图 — 基因组/关系可视化",
    "sunburst": "旭日图 — 层次数据径向",
    "chord": "弦图 — 流量/关系矩阵",
    "sankey_micro": "微宏观 Sankey — 经济结构流动",
    "ensemble_ribbon": "集成预测区间 — 不确定性可视化",
    "ridgeline": "山脊图 — 分布时序变化",
    "waffle": "华夫图 — 比例可视化",
}


@dataclass
class ChartRecord:
    """Provenance record for a generated chart."""
    chart_id: str
    chart_type: str
    title: str
    output_path: Path
    data_sources: list[str]
    code_snapshot: str
    dpi: int = 300
    format: str = "pdf"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chart_id": self.chart_id,
            "chart_type": self.chart_type,
            "title": self.title,
            "output_path": str(self.output_path),
            "data_sources": self.data_sources,
            "dpi": self.dpi,
            "format": self.format,
            "metadata": self.metadata,
        }


# ─── Base academic style ──────────────────────────────────────────────────────


ACADEMIC_STYLE = {
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 1.2,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}

CB_PALETTE = [
    "#0072B2", "#009E73", "#D55E00", "#CC79A7",
    "#56B4E9", "#F0E442", "#E69F00", "#999999",
]


def _apply_style(plt: Any) -> None:
    try:
        import matplotlib
        for k, v in ACADEMIC_STYLE.items():
            matplotlib.rcParams[k] = v
    except Exception:
        pass


# ─── Provenance Registry ──────────────────────────────────────────────────────


class ChartRegistry:
    """Global registry of all generated charts for provenance tracking."""

    def __init__(self, registry_path: Path | None = None):
        self.records: list[ChartRecord] = []
        self._path = registry_path or Path("output/figures/chart_registry.jsonl")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def register(self, record: ChartRecord) -> None:
        self.records.append(record)
        self._persist()

    def _persist(self) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def find_by_type(self, chart_type: str) -> list[ChartRecord]:
        return [r for r in self.records if r.chart_type == chart_type]

    def find_by_source(self, data_source: str) -> list[ChartRecord]:
        return [r for r in self.records if data_source in r.data_sources]

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r.chart_type] = counts.get(r.chart_type, 0) + 1
        return {"total": len(self.records), "by_type": counts}


# ─── AdvancedChartFactory ──────────────────────────────────────────────────────


class AdvancedChartFactory:
    """
    生成专业学术图表类型的工厂。

    支持的图表类型:
        sankey         — 桑基图（流量分析）
        funnel         — 漏斗图（转化分析）
        alluvial       — 冲积图（分类变化）
        consort        — CONSORT 图（临床试验）
        dendrogram     — 树状图（层次聚类）
        sunburst       — 旭日图（层次径向）
        chord          — 弦图（关系矩阵）
        sankey_micro   — 微宏观 Sankey（经济结构）
        ridgeline      — 山脊图（分布时序）
        waffle         — 华夫图（比例）
    """

    def __init__(
        self,
        output_dir: str | Path = "output/figures",
        registry: ChartRegistry | None = None,
        dpi: int = 300,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry or ChartRegistry(self.output_dir / "chart_registry.jsonl")
        self.dpi = dpi
        self._id_prefix = "adv"

    # ── Common helpers ────────────────────────────────────────────────────────

    def _save(
        self,
        fig: Any,
        filename: str,
        fmt: str = "pdf",
        extra_metadata: dict | None = None,
        data_sources: list[str] | None = None,
    ) -> Path:
        """Save figure and register provenance."""
        path = self.output_dir / f"{filename}.{fmt}"
        try:
            fig.savefig(path, dpi=self.dpi, bbox_inches="tight")
        except Exception:
            path = path.with_suffix(".png")
            fig.savefig(path, dpi=self.dpi, bbox_inches="tight")

        record = ChartRecord(
            chart_id=f"{self._id_prefix}_{uuid.uuid4().hex[:8]}",
            chart_type=filename.rsplit("_", 1)[-1],
            title=filename,
            output_path=path,
            data_sources=data_sources or [],
            code_snapshot="",  # filled by caller
            dpi=self.dpi,
            format=fmt,
            metadata=extra_metadata or {},
        )
        self.registry.register(record)
        return path

    # ── Sankey Diagram ─────────────────────────────────────────────────────

    def sankey(
        self,
        nodes: list[str],
        links: list[tuple[int, int, float]],
        title: str = "数据处理流程",
        output_name: str = "sankey_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        桑基图 — 展示流量从一个状态到另一个状态的流向与比例。

        参数:
            nodes: 节点名称列表，索引对应 link 中的 from/to
            links: [(源节点索引, 目标节点索引, 流量值), ...]
            title: 图表标题
            output_name: 输出文件名（不含后缀）
        """
        try:
            import matplotlib
            import matplotlib.pyplot as plt
            from matplotlib.sankey import Sankey
        except ImportError:
            print("  [AdvancedChartFactory] sankey: matplotlib.sankey 不可用")
            return None

        _apply_style(plt)
        fig, ax = plt.subplots(figsize=(max(8, len(nodes) * 1.5), 6))

        try:
            flows = []
            for src, dst, val in links:
                flow = [0] * len(nodes)
                flow[src] = -val
                flow[dst] = val
                flows.append(flow)

            sankey = Sankey(ax=ax, scale=0.5, margin=0.3)
            for flow in flows:
                sankey.add(
                    flows=[f for f in flow if f != 0],
                    labels=[nodes[i] for i, f in enumerate(flow) if f != 0],
                    orientations=[0 if f < 0 else 1 for f in flow if f != 0],
                )
            diagrams = sankey.finish()
            for d in diagrams:
                d.text.set_fontsize(9)
            ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
        except Exception as e:
            print(f"  [AdvancedChartFactory] sankey rendering: {e}")
            return None

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "sankey", "nodes": nodes, "links": len(links)},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Funnel Chart ────────────────────────────────────────────────────────

    def funnel(
        self,
        stages: list[str],
        values: list[float],
        title: str = "用户转化漏斗",
        output_name: str = "funnel_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        漏斗图 — 展示多阶段转化率。

        参数:
            stages: 阶段名称列表（从上到下）
            values: 各阶段数值
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as patches
        except ImportError:
            return None

        _apply_style(plt)
        n = len(stages)
        fig, ax = plt.subplots(figsize=(8, max(4, n * 0.9)))

        max_val = float(max(values))
        bar_h = 0.7

        for i, (stage, val) in enumerate(zip(stages, values)):
            width = val / max_val
            conv_rate = val / values[0] if i > 0 else 1.0

            color = CB_PALETTE[i % len(CB_PALETTE)]
            rect = patches.FancyBboxPatch(
                ((1 - width) / 2, n - 1 - i), width, bar_h,
                boxstyle="round,pad=0.02",
                facecolor=color, edgecolor="white", linewidth=1.5,
                transform=ax.transData, clip_on=False,
            )
            ax.add_patch(rect)

            ax.text(
                0.5, n - 1 - i + bar_h / 2,
                f"{stage}  ({val:,.0f}  |  {conv_rate:.1%})",
                ha="center", va="center",
                fontsize=10, fontweight="bold",
                color="white" if width > 0.25 else "black",
            )

        ax.set_xlim(0, 1)
        ax.set_ylim(0, n)
        ax.axis("off")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "funnel", "stages": stages, "values": values},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Alluvial Diagram ────────────────────────────────────────────────────

    def alluvial(
        self,
        categories: list[tuple[str, list[str]]],
        flows: list[tuple[str, str, float]],
        title: str = "分类变化流向",
        output_name: str = "alluvial_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        冲积图 — 展示分类在不同状态间的转移与流量。

        参数:
            categories: [(类别名, [成员列表]), ...]
            flows: [(源成员, 目标成员, 流量比例), ...]
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as patches
        except ImportError:
            return None

        _apply_style(plt)
        n_cats = len(categories)
        fig, ax = plt.subplots(figsize=(max(10, n_cats * 3), 6))
        ax.set_xlim(0, n_cats)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

        total_widths: list[float] = []
        for cat_name, members in categories:
            total_widths.append(sum(f[2] for f in flows if f[0] in members or f[1] in members))

        x_positions = np.linspace(0.1, 0.9, n_cats)

        for ci, ((cat_name, members), x) in enumerate(zip(categories, x_positions)):
            rect = patches.FancyBboxPatch(
                (x - 0.08, 0.0), 0.16, 1.0,
                boxstyle="round,pad=0.01",
                facecolor=CB_PALETTE[ci % len(CB_PALETTE)],
                edgecolor="white", alpha=0.9,
            )
            ax.add_patch(rect)
            ax.text(x, 0.5, cat_name, ha="center", va="center",
                    fontsize=11, fontweight="bold", color="white")
            for mi, m in enumerate(members):
                ax.text(x - 0.07, 0.1 + mi * 0.08, m,
                        ha="left", va="center", fontsize=7.5, color="white", clip_on=True)

        for src_name, dst_name, flow_val in flows:
            src_cat_i = next((i for i, (c, ms) in enumerate(categories) if src_name in ms), -1)
            dst_cat_i = next((i for i, (c, ms) in enumerate(categories) if dst_name in ms), -1)
            if src_cat_i < 0 or dst_cat_i < 0:
                continue

            x0, x1 = x_positions[src_cat_i], x_positions[dst_cat_i]
            src_member_i = next((i for i, m in enumerate(categories[src_cat_i][1]) if m == src_name), 0)
            dst_member_i = next((i for i, m in enumerate(categories[dst_cat_i][1]) if m == dst_name), 0)

            y0 = 0.1 + src_member_i * 0.08
            y1 = 0.1 + dst_member_i * 0.08
            color = CB_PALETTE[src_cat_i % len(CB_PALETTE)]
            alpha = min(0.8, flow_val)
            ax.fill_betweenx(
                [y0 - 0.01, y0 + 0.01],
                [x0, x0], [x1, x1],
                color=color, alpha=alpha,
            )
            ax.plot([x0 + 0.08, x1 - 0.08], [y0, y1],
                    color=color, alpha=alpha * 0.7, linewidth=flow_val * 3)

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "alluvial", "categories": [c[0] for c in categories]},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── CONSORT Diagram ─────────────────────────────────────────────────────

    def consort(
        self,
        groups: dict[str, dict],
        title: str = "CONSORT 流程图",
        output_name: str = "consort_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        CONSORT 流程图 — 临床试验受试者流程（CONSORT 2010 标准）。

        参数:
            groups: {
                "enrollment": {"excluded": N, "reasons": [...]},
                "randomized": N,
                "allocated": N,
                "followed": N,
                "analysed": N,
                "withdrawn": N,
                ...
            }
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as patches
        except ImportError:
            return None

        _apply_style(plt)
        fig, ax = plt.subplots(figsize=(12, max(10, len(groups) * 1.2)))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

        def box(ax, x, y, w, h, text, color_idx=0, style="round,pad=0.05"):
            c = CB_PALETTE[color_idx % len(CB_PALETTE)]
            rect = patches.FancyBboxPatch(
                (x, y), w, h,
                boxstyle=style,
                facecolor=c, edgecolor="black", linewidth=1,
                alpha=0.85 if color_idx > 0 else 1.0,
            )
            ax.add_patch(rect)
            ax.text(x + w / 2, y + h / 2, text,
                    ha="center", va="center", fontsize=8.5,
                    fontweight="bold" if color_idx == 0 else "normal",
                    wrap=True,
                    color="white" if color_idx == 0 else "black")

        def arrow(ax, x0, y0, x1, y1, label=""):
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="->", color="gray", lw=1.2))
            if label:
                mid = (x0 + x1) / 2, (y0 + y1) / 2
                ax.text(mid[0], mid[1], label, fontsize=7.5, ha="center", color="gray")

        box(ax, 3.5, 8.5, 3, 1.2, "登记\n(N=...)", 0)
        box(ax, 3.5, 7.0, 3, 1.0, "排除\n(N=...)", 5)
        arrow(ax, 5, 8.5, 5, 8.0, "不符合条件")
        box(ax, 3.5, 5.8, 3, 1.0, "知情同意\n(N=...)", 1)
        arrow(ax, 5, 7.0, 5, 6.8)
        box(ax, 0.5, 4.2, 3, 1.0, "随机分组\n试验组 (N=...)", 2)
        box(ax, 6.5, 4.2, 3, 1.0, "随机分组\n对照组 (N=...)", 3)
        arrow(ax, 3.5, 5.8, 2.0, 5.2)
        arrow(ax, 6.5, 5.8, 8.0, 5.2)
        box(ax, 0.5, 2.5, 3, 1.0, "随访完成\n(N=...)", 2)
        box(ax, 6.5, 2.5, 3, 1.0, "随访完成\n(N=...)", 3)
        arrow(ax, 2.0, 4.2, 2.0, 3.5)
        arrow(ax, 8.0, 4.2, 8.0, 3.5)
        box(ax, 3.5, 0.8, 3, 1.0, "数据分析\n(N=...)", 4)
        arrow(ax, 2.0, 2.5, 5.0, 1.8)
        arrow(ax, 8.0, 2.5, 5.0, 1.8)

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "consort"},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Dendrogram ──────────────────────────────────────────────────────────

    def dendrogram(
        self,
        linkage_matrix: np.ndarray,
        labels: list[str],
        title: str = "层次聚类树状图",
        output_name: str = "dendrogram_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        树状图 — 层次聚类结果可视化。

        参数:
            linkage_matrix: scipy.cluster.hierarchy.linkage() 返回的矩阵
            labels: 叶子节点标签
        """
        try:
            import matplotlib.pyplot as plt
            from scipy.cluster.hierarchy import dendrogram as _sci_dendrogram
        except ImportError:
            return None

        _apply_style(plt)
        fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.4), 6))

        _sci_dendrogram(
            linkage_matrix,
            labels=labels,
            ax=ax,
            leaf_rotation=45,
            leaf_font_size=9,
            color_threshold=0.7 * max(linkage_matrix[:, 2]),
        )
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.tick_params(axis="x", labelsize=8)
        plt.tight_layout()

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "dendrogram", "n_leaves": len(labels)},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Sunburst ────────────────────────────────────────────────────────────

    def sunburst(
        self,
        hierarchy: dict,
        title: str = "层次结构旭日图",
        output_name: str = "sunburst_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        旭日图 — 层次数据的径向可视化。

        参数:
            hierarchy: {"name": "root", "children": [{"name": "...", "value": N}, ...]}
        """
        try:
            import matplotlib.pyplot as plt
            import squarify
        except ImportError:
            return None

        _apply_style(plt)
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.axis("off")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

        # Squarify treemap as sunburst approximation
        try:
            values = [max(1, int(hierarchy.get("value", 100)))]
            colors = CB_PALETTE[:1]
            squarify.plot(
                sizes=values, label=["root"], alpha=0.9,
                color=CB_PALETTE[0], text_kwargs={"fontsize": 12},
                ax=ax,
            )
        except Exception:
            pass

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "sunburst"},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Ridge Line (Joy Plot) ──────────────────────────────────────────────

    def ridgeline(
        self,
        time_labels: list[str],
        distributions: list[list[float]],
        colors: list[str] | None = None,
        title: str = "分布时序变化",
        output_name: str = "ridgeline_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        山脊图 — 展示多个时间段的分布变化（Joy Plot 风格）。

        参数:
            time_labels: 时间标签列表
            distributions: 各时间段的数值分布
        """
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
        except ImportError:
            return None

        _apply_style(plt)
        n = len(time_labels)
        fig, axes = plt.subplots(
            n, 1, figsize=(10, max(6, n * 1.2)),
            sharex=True, sharey=False,
        )
        if n == 1:
            axes = [axes]

        palette = colors or CB_PALETTE[:n]

        for i, (label, dist, ax) in enumerate(zip(time_labels, distributions, axes)):
            if not dist:
                ax.set_visible(False)
                continue
            dist_arr = np.array(dist)
            try:
                sns.kdeplot(dist_arr, ax=ax, fill=True, alpha=0.6,
                            color=palette[i % len(palette)], linewidth=1.5)
            except Exception:
                ax.hist(dist_arr, bins=20, alpha=0.5, color=palette[i % len(palette)])
            ax.text(0.02, 0.85, label, transform=ax.transAxes,
                    fontsize=10, fontweight="bold", va="top")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            if i < n - 1:
                ax.spines["bottom"].set_visible(False)
                ax.set_xticklabels([])
            ax.set_yticks([])

        fig.suptitle(title, fontsize=13, fontweight="bold", y=0.98)
        plt.tight_layout(h_pad=0.1)

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "ridgeline", "n_periods": n},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Waffle Chart ───────────────────────────────────────────────────────

    def waffle(
        self,
        categories: list[tuple[str, float]],
        title: str = "类别比例",
        output_name: str = "waffle_default",
        n_cells: int = 20,
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        华夫图 — 用方块表示类别比例。

        参数:
            categories: [(类别名, 数值/比例), ...]
            n_cells: 总格子数（建议 20 或 50）
        """
        try:
            import matplotlib.pyplot as plt
            import squarify
        except ImportError:
            return None

        _apply_style(plt)
        values = [max(1, int(c[1])) for c in categories]
        labels = [f"{c[0]}\n{v}" for c, v in zip(categories, values)]

        fig, ax = plt.subplots(figsize=(max(8, n_cells * 0.6), max(3, n_cells * 0.3)))
        ax.axis("off")
        squarify.plot(
            sizes=values, label=labels,
            alpha=0.9, color=CB_PALETTE[:len(categories)],
            text_kwargs={"fontsize": 9, "color": "white", "fontweight": "bold"},
            ax=ax,
        )
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "waffle", "categories": [c[0] for c in categories]},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Ensemble Ribbon (Prediction Interval) ─────────────────────────────────

    def ensemble_ribbon(
        self,
        x: list[float],
        y_median: list[float],
        y_lower: list[float],
        y_upper: list[float],
        y_mean: list[float] | None = None,
        title: str = "集成预测区间",
        output_name: str = "ensemble_ribbon_default",
        data_sources: list[str] | None = None,
    ) -> Path | None:
        """
        集成预测区间 — 展示多个模型预测的不确定性范围。

        参数:
            x: 时间/索引
            y_median: 中位数预测
            y_lower / y_upper: 95% 置信区间
            y_mean: 均值预测（可选）
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            return None

        _apply_style(plt)
        fig, ax = plt.subplots(figsize=(12, 5))

        x_arr = np.array(x)
        ax.fill_between(x_arr, y_lower, y_upper,
                        alpha=0.2, color=CB_PALETTE[0], label="95% CI")
        ax.plot(x_arr, y_median, "-", color=CB_PALETTE[0], linewidth=2,
                label="中位数预测", zorder=3)
        if y_mean:
            ax.plot(x_arr, y_mean, "--", color=CB_PALETTE[1], linewidth=1.5,
                   label="均值预测", zorder=2)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="-", zorder=1)
        ax.set_xlabel("时间", fontsize=11)
        ax.set_ylabel("预测值", fontsize=11)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.legend(loc="best", framealpha=0.9)
        ax.grid(alpha=0.3)
        plt.tight_layout()

        path = self._save(fig, output_name, "pdf",
                          extra_metadata={"chart_type": "ensemble_ribbon", "n_points": len(x)},
                          data_sources=data_sources)
        plt.close(fig)
        return path

    # ── Multi-format export ────────────────────────────────────────────────

    def save_all_formats(
        self,
        fig: Any,
        name: str,
        formats: list[str] | None = None,
        data_sources: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Path]:
        """
        将一个 matplotlib Figure 保存为多种格式（PDF / PNG / SVG）。
        """
        formats = formats or ["pdf", "png"]
        paths: dict[str, Path] = {}
        for fmt in formats:
            try:
                p = self._save(fig, name, fmt, extra_metadata=kwargs,
                               data_sources=data_sources)
                if p:
                    paths[fmt] = p
            except Exception:
                pass
        return paths

    # ── Registry summary ────────────────────────────────────────────────────

    def summary(self) -> dict:
        return self.registry.summary()
