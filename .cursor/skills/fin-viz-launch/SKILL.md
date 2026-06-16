---
name: fin-viz-launch
description: 将用户的研究描述转换为高质量学术图表，自动推荐最佳图表类型并生成matplotlib/seaborn代码，输出≥300 DPI的PDF/SVG/PNG。
trigger: "画图|可视化|figure|chart|plot|图表|图表生成|生成图表"
version: 1.0.0
created: 2026-06-13
tags: [visualization, chart, figure, matplotlib, academic, plot]
---

# fin-viz-launch

将用户的研究描述转换为高质量学术图表，自动推荐最佳图表类型并生成matplotlib/seaborn代码，输出≥300 DPI的PDF/SVG/PNG。

## 触发条件

- 关键词: `画图` `可视化` `figure` `chart` `plot` `图表` `图表生成` `生成图表` `生成图片`
- Skill语法: `Skill: fin-viz-launch`
- 前置条件: 有可用数据 (DataFrame) 或数据路径

## 三种工作模式

### 模式一：快速模式 (Quick Mode)

通过关键词匹配，无须LLM直接调用预设模板：

```python
from scripts.research_framework import FinancialChartFactory, ChartConfig

factory = FinancialChartFactory(output_dir="figures/")

# 关键词 → 预设映射
# "平行趋势" → parallel_trends
# "安慰剂" → placebo_distribution
# "相关性" → correlation_heatmap

# 直接使用预设
fig = factory.plot("parallel_trends", df,
    time_var="year",
    treat_var="treat",
    y_var="innovation",
    save_path="figures/parallel_trends.pdf",
    dpi=300,
)
```

### 模式二：LLM模式 (CoDA-Style Pipeline)

描述 → 选择图表类型 → 生成代码 → 执行 → 迭代：

```python
from scripts.research_framework import ChartLLMGenerator

generator = ChartLLMGenerator(
    model="deepseek",
    output_dir="figures/",
)

# 用户描述
user_description = "显示处理组和对照组在政策前后的创新投入趋势，标注置信区间"

# LLM选择图表类型并生成代码
result = generator.generate(
    description=user_description,
    data=df,
    context={"methodology": "DID", "journal": "经济研究"},
)

# result = {
#     "chart_type": "parallel_trends",
#     "code": "...",
#     "reasoning": "选择了带置信区间的平行趋势图...",
# }

# 执行代码
fig = generator.execute(result["code"])
```

### 模式三：交互模式 (Interactive Mode)

用户确认后再生成：

```
用户: 画一个展示DID回归结果的图

AI推荐: 系数森林图 (forest plot) 适合展示DID系数和置信区间

请确认:
1. 接受推荐 → 生成森林图
2. 换成其他类型 → 选择: 条形图/时序图/热力图
3. 自定义参数 → 指定: 颜色/标签/标题

> 1

[生成森林图...]
```

## 20种预设图表模板

### 实证研究图表

| 图表类型 | 关键词 | 用途 |
|----------|--------|------|
| `parallel_trends` | 平行趋势, pre-trend | DID平行趋势检验 |
| `placebo_distribution` | 安慰剂, placebo | 安慰剂检验分布 |
| `robustness_summary` | 稳健性, robustness | 稳健性系数森林图 |
| `psm_distribution` | PSM, 倾向得分 | 倾向得分分布 |
| `did_coef_timeline` | DID系数, 时序 | DID系数时间变化 |
| `cumulative_effect` | 累积, CAR | 累积处理效应 |
| `event_study` | 事件研究, 窗口 | 事件窗口期收益 |

### 描述性图表

| 图表类型 | 关键词 | 用途 |
|----------|--------|------|
| `correlation_heatmap` | 相关性, 相关矩阵 | 变量相关热力图 |
| `descriptive_bar` | 描述性, 对比 | 分组对比柱状图 |
| `heterogeneity_bar` | 异质性, 分组 | 异质性分析柱状图 |
| `marginal_effects` | 边际效应 | 边际效应图 |
| `ridgeline` | 分布, 时序 | Ridgeline时序分布 |
| `waffle` | 构成, 比例 | Waffle构成图 |

### 诊断图表

| 图表类型 | 关键词 | 用途 |
|----------|--------|------|
| `residual_qq` | QQ图, 残差 | 残差QQ图 |
| `residual_distribution` | 残差, 分布 | 残差分布 |
| `synthetic_control` | 合成控制, SCM | 合成控制反事实 |
| `rdd_plot` | RDD, 断点 | 断点回归图 |

### 金融图表

| 图表类型 | 关键词 | 用途 |
|----------|--------|------|
| `factor_returns` | 因子收益, FF | FF因子收益时序 |
| `stock_return_dist` | 收益率, 分布 | 收益率分布 |
| `rolling_correlation` | 滚动相关 | 滚动相关性 |

## 图表预设代码示例

### parallel_trends (平行趋势图)

```python
def plot_parallel_trends(
    df: pd.DataFrame,
    time_var: str = "year",
    treat_var: str = "treat",
    y_var: str = "y",
    ci: float = 0.95,
    save_path: str = None,
    dpi: int = 300,
) -> plt.Figure:
    """绘制平行趋势图"""
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 计算各年各组的均值和标准误
    grouped = df.groupby([time_var, treat_var])[y_var].agg(["mean", "sem"])
    grouped["ci"] = grouped["sem"] * 1.96  # 95% CI
    
    # 分离处理组和对照组
    treat = grouped.xs(1, level=treat_var)
    control = grouped.xs(0, level=treat_var)
    
    # 绘图
    ax.plot(treat.index, treat["mean"], "o-", color="#E74C3C", 
            label="处理组", linewidth=2, markersize=8)
    ax.fill_between(treat.index, treat["mean"] - treat["ci"], 
                    treat["mean"] + treat["ci"], color="#E74C3C", alpha=0.2)
    
    ax.plot(control.index, control["mean"], "s--", color="#3498DB", 
            label="对照组", linewidth=2, markersize=8)
    ax.fill_between(control.index, control["mean"] - control["ci"], 
                    control["mean"] + control["ci"], color="#3498DB", alpha=0.2)
    
    # 政策时点标注
    ax.axvline(x=policy_year, color="gray", linestyle=":", alpha=0.7)
    ax.text(policy_year, ax.get_ylim()[1], " 政策实施", 
            fontsize=10, color="gray", va="top")
    
    # 预处理期虚线
    ax.axvspan(pre_min, policy_year - 1, alpha=0.1, color="gray")
    ax.text(pre_min + 0.5, ax.get_ylim()[0], "预处理期", 
            fontsize=9, color="gray", style="italic")
    
    ax.set_xlabel("年份", fontsize=12)
    ax.set_ylabel(y_var, fontsize=12)
    ax.legend(loc="best", fontsize=11)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
        # 同时保存PNG
        png_path = save_path.replace(".pdf", ".png")
        fig.savefig(png_path, dpi=dpi, bbox_inches="tight")
    
    return fig
```

### robustness_summary (稳健性森林图)

```python
def plot_robustness_forest(
    results: dict,
    labels: list,
    true_val: float = 0,
    save_path: str = None,
    dpi: int = 300,
) -> plt.Figure:
    """绘制稳健性检验系数森林图"""
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    y_positions = np.arange(len(labels))
    coef_values = [r["coef"] for r in results]
    ci_lower = [r["ci_lower"] for r in results]
    ci_upper = [r["ci_upper"] for r in results]
    
    # 绘制系数点和置信区间
    for i, (y, coef, lo, hi) in enumerate(zip(y_positions, coef_values, ci_lower, ci_upper)):
        color = "#2ECC71" if (lo <= true_val <= hi) else "#E74C3C"
        ax.plot([lo, hi], [y, y], color=color, linewidth=2)
        ax.plot(coef, y, "o", color=color, markersize=10)
    
    # 真实值参考线
    ax.axvline(x=true_val, color="black", linestyle="--", linewidth=1.5, alpha=0.7)
    
    # 零线标注
    ax.axvline(x=0, color="gray", linestyle=":", alpha=0.5)
    
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("系数估计值 (95% CI)", fontsize=12)
    ax.set_title("稳健性检验结果", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="x")
    
    # 添加图例
    ax.plot([], [], "o", color="#2ECC71", label="显著")
    ax.plot([], [], "o", color="#E74C3C", label="不显著")
    ax.legend(loc="upper right", fontsize=10)
    
    plt.tight_layout()
    
    if save_path:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
    
    return fig
```

### correlation_heatmap (相关性热力图)

```python
def plot_correlation_heatmap(
    df: pd.DataFrame,
    vars: list,
    cmap: str = "RdBu_r",
    center: float = 0,
    save_path: str = None,
    dpi: int = 300,
) -> plt.Figure:
    """绘制变量相关性热力图"""
    
    corr = df[vars].corr()
    
    fig, ax = plt.subplots(figsize=(12, 10))
    
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap=cmap,
        center=center,
        vmin=-1, vmax=1,
        square=True,
        linewidths=0.5,
        cbar_kws={"shrink": 0.8, "label": "相关系数"},
        ax=ax,
    )
    
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=10)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=10)
    ax.set_title("变量相关性矩阵", fontsize=14, fontweight="bold", pad=20)
    
    plt.tight_layout()
    
    if save_path:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
    
    return fig
```

## FinancialChartFactory API

```python
from scripts.research_framework import FinancialChartFactory, ChartConfig

# 初始化工厂
factory = FinancialChartFactory(
    output_dir="figures/",
    default_dpi=300,
    style="academic",  # academic / journal / presentation
)

# ============ 使用预设 ============
fig = factory.plot(
    "parallel_trends",
    df=df,
    time_var="year",
    treat_var="treat",
    y_var="innovation",
    save_path="figures/parallel_trends.pdf",
)

# ============ 自定义配置 ============
config = ChartConfig(
    title="图1: 平行趋势检验",
    xlabel="年份",
    ylabel="研发投入强度 (%)",
    legend=True,
    legend_loc="best",
    grid=True,
    grid_alpha=0.3,
    font_family="Times New Roman",
    font_size=12,
)

fig = factory.plot_custom(
    chart_type="line",
    data=df,
    config=config,
    save_path="figures/custom_line.pdf",
)

# ============ 批量生成 ============
charts = [
    ("parallel_trends", {"df": did_df, ...}),
    ("placebo_distribution", {"df": placebo_df, ...}),
    ("heterogeneity_bar", {"df": hetero_df, ...}),
]

results = factory.batch_generate(charts)
print(f"成功生成 {results['success']} 个图表")
```

## 图表规范 (学术发表标准)

```
分辨率: >= 300 DPI (必需)
格式: PDF (矢量) + PNG (位图备份)
字体: Times New Roman (英文) / 宋体/黑体 (中文)
字号: 轴标签 10-12pt, 标题 12-14pt, 图例 9-11pt
线宽: 1.5-2.5pt
标记大小: 6-10pt
颜色: 使用色盲友好配色 (避免红绿区分)
边距: 紧凑但留白充足
纵横比: 约 4:3 或 1:1
```

## 溯源元数据

每个图表自动记录溯源信息：

```python
from scripts.core.provenance import ChartProvenance

provenance = ChartProvenance()

provenance.record_chart(
    chart_id="fig1_parallel_trends",
    chart_type="parallel_trends",
    data_source="tushare + manual",
    data_timestamp=datetime.now(),
    code_hash=hashlib.md5(code.encode()).hexdigest(),
    output_files=["figures/parallel_trends.pdf", "figures/parallel_trends.png"],
    parameters={
        "time_var": "year",
        "treat_var": "treat",
        "y_var": "innovation",
        "ci_level": 0.95,
    },
)

provenance.export("figures/provenance.json")
```

## 交互流程

```
用户: 画一个平行趋势图

[Quick Mode] 检测到关键词 "平行趋势"

推荐图表类型: parallel_trends (预设模板)
- 适用: DID平行趋势检验
- 数据要求: 包含时间变量、处理组标记、结果变量

请确认:
1. 使用预设模板 → 立即生成
2. 调整参数 → 指定: 置信区间/颜色/标签
3. 更换图表类型 → 选择其他模板

> 2

请输入调整参数 (直接回车使用默认值):
- 置信区间水平 [95%]: 
- 标题 []: 平行趋势检验
- 处理组标签 [处理组]: 
- 对照组标签 [对照组]: 

[生成图表...]
✅ 图表已保存: figures/parallel_trends.pdf
✅ 分辨率: 300 DPI
```

## 输出规范

```
figures/
├── parallel_trends.pdf      # 矢量图 (出版用)
├── parallel_trends.png      # 位图 (预览用)
├── parallel_trends_meta.json # 溯源元数据
├── placebo_distribution.pdf
├── placebo_distribution.png
├── robustness_summary.pdf
...
```

## 依赖项

- `scripts/research_framework/fin_charts.py` — 图表工厂核心
- `scripts/research_framework/chart_llm_generator.py` — LLM图表生成
- `scripts/core/provenance.py` — 溯源追踪
- `scripts/journal_template.py` — 期刊格式适配

## 约束

1. **分辨率强制** — 所有图表必须 >= 300 DPI
2. **双格式输出** — 必须同时生成 PDF 和 PNG
3. **溯源记录** — 每个图表记录数据来源和生成参数
4. **学术规范** — 字体、字号、线宽符合发表标准
5. **色盲友好** — 避免仅用红绿区分
