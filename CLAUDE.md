# 论文-研报工作流 · FinResearch Agent

> 经济金融领域 AI 研究助手。参考 Night Owl Research Agent (NORA) 设计，深度集成 A股数据 + 中文期刊 + MCP 工具生态。

---

## 🎯 一句话说清楚我能做什么

**"告诉我要研究什么主题，我帮你：从文献综述 → 想法生成 → 实证设计 → 论文草稿 → LaTeX 编译，全自动。"**

---

## 🚀 第一次用？直接说主题

不需要记任何命令。**直接说你的研究方向**，我来判断怎么启动：

```
"我想研究关税政策对A股出口型企业创新的影响"
"帮我分析一下绿色债券的定价效率"
"我想写一篇关于数字金融的论文"
```

---

## 📋 常用操作（不用记，收藏即可）

| 你想做什么 | 直接说 | 说明 |
|-----------|--------|------|
| 完整论文流程 | `从头研究 [主题]` | 文献→想法→大纲→写作→PDF |
| 文献综述 | `帮我综述 [主题]` | MCP 搜索 + 引文图谱 |
| 研究想法 | `有什么新想法 [主题]` | 8-12 个候选想法，数据验证 |
| 实证设计 | `设计实验 [想法]` | DID/IV/RD/面板 |
| 论文写作 | `写论文 [主题]` | LaTeX，可选中文顶刊格式 |
| 图表生成 | `生成图表 [需求]` | matplotlib，≥300 DPI + 12种专业图表 |
| 专业图表 | `生成 [桑基/漏斗/森林图...]` | AdvancedChartFactory，provenance追踪 |
| 对抗性 review | `review 我的论文` | 学术规范 + 实证严谨性 |
| 自动唤醒 | `python scripts/on_enter.py` | 进入目录自动运行 |
| 后台监控 | `python scripts/event_monitor.py --macro-scheduler --auto-trigger` | NFP/CPI/FOMC 自动触发 |

---

## 🔑 核心原则

1. **MCP 优先** — 所有数据通过 MCP 工具获取（tushare / financial / eodhd 等），不用凭空编造
2. **数据是硬约束** — 没有数据支撑的想法不推荐
3. **Checkpoint** — 每个阶段完成后暂停，**你确认后再继续**
4. **生成-评审分离** — 写作和 review 由不同模块处理
5. **中文顶刊标准** — 经济研究 / 金融研究 / 管理世界（含稳健性检验要求）

---

## 📊 数据工具速查

| 你要什么 | 用这个 MCP |
|---------|-----------|
| A股行情/财务/融资融券 | `user-tushare`（需 TUSHARE_TOKEN）|
| 中国宏观（GDP/CPI/M2）| `user-financial` |
| 美联储/FOMC | `user-fed-data` |
| 世界银行宏观 | `user-wb-data` |
| 国债收益率/经济日历 | `user-eodhd` |
| 研报/新闻 | `user-eastmoney-reports` |
| 外汇/航运/大宗商品 | `user-enhanced-finance` |
| 学术论文/Working Papers | `user-nber-wp`（NBER）+ 网络搜索 |
| 中文文献 | `user-brave-search`（经济研究/金融研究）|

> **大部分工具无需 API Key，直接调用即可。**

---

## 🗂️ 输出结构

所有输出在 `output/` 目录：

```
output/
├── fin-literature/      # 文献综述（LIT_REVIEW.md, CITATION_GRAPH.json）
├── fin-ideas/           # 研究想法（IDEA_REPORT.md）
├── fin-novelty/        # 新颖性验证（NOVELTY_REPORT.md）
├── fin-refinement/     # 研究设计（REFINED_DESIGN.md, ROBUSTNESS_PLAN.md）
├── fin-experiments/    # 实证结果（scripts/, results/)
├── fin-review/         # 对抗性review（REVIEW_REPORT.md）
└── fin-manuscript/     # 论文草稿（draft_vN/，含 main.tex + main.pdf）
```

---

## ⚙️ 可选标志（按需设置）

在开始前或 `FIN_BRIEF.md` 中配置：

| 标志 | 默认 | 说明 |
|------|------|------|
| `AUTO_PROCEED` | `false` | `true`=自动选最优；`false`=checkpoint确认 |
| `HUMAN_CHECKPOINT` | `true` | `true`=review后暂停 |
| `REVIEWER_DIFFICULTY` | `standard` | standard / strict / nightmare |
| `COMPACT_MODE` | `false` | `true`=精简输出 |
| `TARGET_JOURNAL` | `auto` | JF / JFE / RFS / 经济研究 / 金融研究 等 |

> 可选功能使用前会先询问你是否安装了对应依赖（sandbox / browser 等）。

---

## 🏗️ 参考架构

- [Night Owl Research Agent (NORA)](https://github.com/GRIND-Lab-Core/night_owl_research_agent)
- [PaperOrchestra (Google)](https://github.com/google-research/paper-orchestra)
- [ARK (KAUST)](https://github.com/kaust-ark/ARK)
- [Qiongli (穷理)](https://github.com/jxpeng98/qiongli)
- [MSc (PoggioAI)](https://github.com/PoggioAI/PoggioAI_MSc)

---

## 🖼️ 可视化技能

| 技能 | 功能 | 典型调用 |
|------|------|---------|
| `fin-paper-figure` | matplotlib 图表生成（≥300 DPI）| `Skill: fin-paper-figure "[FIGURE_PLAN.md]"` |
| `fin-viz-launch` | 可视化唤起入口（自然语言 → 图表）| `Skill: fin-viz-launch "绘制DID系数森林图"` |
| `fin-paper-convert` | LaTeX 编译 + 多版本 | `Skill: fin-paper-convert "[draft_vN/]"` |
