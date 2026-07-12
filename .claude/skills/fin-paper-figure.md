# fin-paper-figure — 图表生成

根据 `FIGURE_PLAN.md` 图表计划和 `TABLE_PLAN.md` 表格计划，生成 matplotlib/seaborn 代码并执行，输出 ≥300 DPI 的高质量图表（PDF/SVG/PNG 格式）。

## 功能

### 图表类型（20+种预设）

| 类别 | 图表类型 |
|------|---------|
| DID 专用 | 平行趋势图、森林图、动态效应图 |
| 机制分析 | 中介效应路径图（Sankey）、调节效应热力图 |
| 异质性分析 | 分组柱状图、分位数图 |
| 稳健性 | 安慰剂分布图、PSM 密度图 |
| 时间序列 | 事件研究折线图、脉冲响应图 |
| 描述性 | 核密度图、相关性热力图 |
| 面板数据 | 堆叠面积图、ridgeline 图 |

### 数据溯源

- `scripts/core/provenance.py` — 追踪每个图表的数据来源、时间戳、处理步骤

### 输出规范

- 分辨率：≥300 DPI
- 格式：PDF（首选，矢量）/ SVG / PNG
- 字体：Times New Roman / 宋体（中文期刊）
- 尺寸：单栏（3.5 inch）/ 双栏（7 inch）

## 核心脚本

- `scripts/core/chart_factory.py` — 图表工厂（20+模板）
- `scripts/core/chart_pipeline.py` — CoDA 优化流水线
- `scripts/research_framework/fin_charts.py` — 金融图表

## 输出

`draft_v{version}/figures/*.pdf`

## 调用方式

```
"生成DID系数森林图"
"做一个企业规模和研发投入关系的异质性分析图"
```
