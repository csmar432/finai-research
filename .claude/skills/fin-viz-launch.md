# fin-viz-launch — 可视化唤起入口

将研究描述转换为高质量学术图表，自然语言驱动，自动推荐图表类型并生成可发表级别的图表。

## 功能

### 三种工作模式

| 模式 | 说明 |
|------|------|
| Quick | 关键词 + `AdvancedChartFactory`，无需 LLM |
| LLM | CoDA 风格 `ChartPipeline`，多轮优化 |
| Interactive | 用户确认后再生成 |

### 图表类型（20+种）

| 类别 | 图表 |
|------|------|
| DID 专用 | 平行趋势图、事件研究图、系数森林图 |
| 机制分析 | Sankey 图、漏斗图、Alluvial 图 |
| 异质性 | 分组柱状图、交互效应热力图 |
| 稳健性 | 安慰剂分布、PSM 密度 |
| 时间序列 | 脉冲响应、滚动窗口 |
| 描述性 | 核密度、相关性热力 |
| 高级 | Ridgeline、CONSORT、Waffle |

### 核心组件

| 脚本 | 功能 |
|------|------|
| `scripts/core/chart_factory.py` | 图表工厂（20+模板）|
| `scripts/core/chart_pipeline.py` | CoDA 优化流水线 |
| `scripts/fin-viz-launcher.py` | 交互式启动器 |
| `scripts/core/provenance.py` | 数据溯源追踪 |

## 输出

- `draft_v{version}/figures/*.pdf`（≥300 DPI）
- 图表代码备份（可复现）

## 调用方式

```
"绘制DID系数森林图"
"生成省级面板数据的异质性分析图，目标期刊经济研究"
```
