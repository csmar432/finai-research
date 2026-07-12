# API 参考

> **本文件是项目公开 API 的权威入口**。
>
> 内容从 `scripts/` 下的 docstring 自动生成（由 `scripts/generate_api_reference.py`），
> 实际可用模块可能多于本文件列出的部分——本文件仅覆盖**稳定公开 API**。
>
> 最后更新：2026-07-12 (audit_fix_2026_07_12 — 修正类名 + 统一计数)

---

## 0. Pipeline 角色澄清

项目有两个 `pipeline` 入口，但**不是平行入口**，而是不同抽象层：

| 入口 | 抽象层 | 用途 |
|------|--------|------|
| `scripts/agent_pipeline.py` | **Agent 层**（端到端研究流程）| 主题 → 文献 → 想法 → 设计 → 数据 → 论文 PDF，多阶段 HITL 检查点 |
| `scripts/research_framework/pipeline.py` | **回归层**（DID 工具函数）| 单一面板回归 + LaTeX 表格格式化（`run_did`, `did_to_latex`, `extract`）|

**调用关系**：agent_pipeline 在数据/设计阶段调用 research_framework.pipeline 完成具体回归计算。两者协议不同：
- agent_pipeline 用 `AgentPipelineResult`（dict，含 `success/outline/literature`）
- research_framework/pipeline.py 用 `extract()` 返回的 coef dict

README 主推前者作为用户入口；后者供框架内调用。

---

## 1. 核心 Agent 入口

| 模块 | 用途 | 文档 |
|------|------|------|
| `scripts/agent_pipeline.py` | 端到端研究流水线（主题→论文 PDF） | 自动生成 |
| `scripts/start_research.py` | 5 轮渐进式主题澄清入口 | 入口 CLI |
| `scripts/health_check.py` | 系统健康检查（必跑） | `--json` 输出 |

## 2. 澄清与画像

| 模块 | 用途 |
|------|------|
| `scripts.core.progressive_clarifier.ProgressiveClarifier` | 5 轮渐进式主题澄清（重命名自 NoraOrchestrator，2026-06-27） |
| `scripts.core.progressive_clarifier.ClarificationState` | 澄清流程状态 |
| `scripts.core.progressive_clarifier.ResearchProfile` | 锁定后的研究画像 |
| `scripts.core.variable_redundancy.VariableRedundancyResolver` | 变量冗余候选生成 |

## 3. 文献与想法

| 模块 | 用途 |
|------|------|
| `scripts.literature_download` | 系统性文献检索（arxiv/semantic_scholar/openalex） |
| `scripts.core.hypothesis_explorer.PilotExperimentGenerator` | 研究想法生成（探索假设节点 + 候选实验） |
| `scripts.core.evolution_gate.NoveltyGate` | 新颖性验证（JF/JFE/RFS 查重） |
| `scripts.core.llm_reviewer.LLMReviewer` | 对抗性 review 循环 |

## 4. 实证设计（47 个方法模块）

| 类 | 模块 | 用途 |
|-----|------|------|
| `RegressionEngine` | `scripts/research_framework/regression_engine.py` | DID/OLS/PSM/GMM 通用回归 |
| `TripleDiffDIDEngine` | `scripts/research_framework/triple_diff_did.py` | 三重差分 DID（`DDDResult`） |
| `ModernDiDEngine` | `scripts/research_framework/modern_did.py` | 现代 DID（Callaway-Sant'Anna / Sun-Abraham / Borusyak / Goodman-Bacon / dCdH） |
| `SyntheticControlEngine` | `scripts/research_framework/synthetic_control.py` | 合成控制法（Abadie et al. 2010/2015/2021） |
| `SyntheticDiDEngine` | `scripts/research_framework/synthetic_did.py` | 合成 DID（Arkhangelsky et al. 2021） |
| `LocalProjectionsDID` | `scripts/research_framework/local_projections_did.py` | 局部投影 DID（Jordà 2005） |
| `PanelQuantileRegression` | `scripts/research_framework/panel_quantile_regression.py` | 面板分位数回归（Canay 2011, Koenker 2004） |
| `InteractiveFixedEffects` | `scripts/research_framework/interactive_fixed_effects.py` | 交互固定效应（Bai 2009）+ CCE（Bai & Ng 2013） |
| `SpatialRegression` | `scripts/research_framework/spatial_regression.py` | 空间回归 SAR/SEM/SDM/SLX |
| `IVPanel` | `scripts/research_framework/iv_panel.py` | IV/Panel/GMM（IV/2SLS/Arellano-Bond/Fama-MacBeth） |
| `RDDEngine` | `scripts/research_framework/rdd.py` | 断点回归（Sharp/Fuzzy/IK/CCT/MSED 带宽） |
| `PanelThresholdRegression` | `scripts/research_framework/panel_threshold_regression.py` | 面板门槛回归（Hansen 2000）+ bootstrap |
| `VuongTest` | `scripts/research_framework/vuong_kob.py` | Vuong (1989) 非嵌套似然比检验 + Clarke test |
| `KOBDecomposition` | `scripts/research_framework/vuong_kob.py` | Kitagawa (2015) 三因素分解 + Bootstrap SE |
| `MediationTest` | `scripts/research_framework/mediation_test.py` | 中介效应（Baron-Kenny/Sobel/Bootstrap/JointSig）— canonical |
| `OaxacaBlinderDecomposition` | `scripts/research_framework/vuong_kob.py` | OB (1973) 工资差距分解（基于 Jann 2008 threefold, 修复于 2026-07-12） |
| `RobustnessRunner` | `scripts/research_framework/robustness_runner.py` | 19 类稳健性 + 13 种方法 dispatch（v1.8.7） |
| `PanelVAR` | `scripts/research_framework/panel_var.py` | Panel VAR（Abrigo & Love 2016）+ IRF/FEVD/Granger |
| `DiscreteChoiceModel` | `scripts/research_framework/discrete_choice.py` | Logit/Probit/Ordered/Negative Binomial |
| `GARCHModel` | `scripts/research_framework/volatility_models.py` | GARCH/GJR-GARCH/EGARCH + HAR |
| `TVPVAR` / `DCCGARCH` | `scripts/research_framework/time_varying_models.py` | TVP-VAR (Nakajima 2010) / DCC-GARCH (Engle 2002) |
| `CoxPHModel` | `scripts/research_framework/survival_analysis.py` | Cox PH / Kaplan-Meier / Fine-Gray |
| `CausalForest` / `DoubleML` | `scripts/research_framework/causal_ml.py` | 因果森林 / DML / X-Learner / T-Learner |
| `PanelCointegrationTest` | `scripts/research_framework/panel_cointegration.py` | Pedroni/Kao/Westerlund 协整 + Panel ECM |
| `GreenBondFactorModel` | `scripts/research_framework/green_bond_model.py` | Green bond premium / ESG factor decomposition |
| `IVSurfaceBuilder` | `scripts/research_framework/options_iv_surface.py` | 期权 IV surface + BS solver + Greeks |

> 完整 47 个方法模块列表见 `scripts/research_framework/`，由 `scripts/count_assets.py` 自动统计。

## 5. 数据获取

| 模块 | 用途 |
|------|------|
| `scripts.core.data_gate.DataGate` | 数据就绪门控（防 silent fallback） |
| `scripts.core.provenance.ProvenanceTracker` | 数据溯源追踪 |
| `scripts.core.checkpoint.CheckpointManager` | 断点续传 |
| `scripts.universal_data_fetcher.UniversalDataFetcher` | 统一数据获取（7 层 fallback） |
| `scripts/research_framework/a_share_firm_controls.FirmControl` | A 股公司控制变量目录（`list_controls` / `get_control` / `compute_controls`） |
| `scripts/research_framework/china_carbon_events.CarbonETSConfig` | 中国碳市场政策事件（`build_carbon_ets_panel` / `carbon_ets_regression_template`） |
| `scripts/research_framework/china_policy_events.ChinaPolicyEvent` | 中国政策事件数据库（`get_china_policy_event` / `list_china_policy_events`） |

## 6. 论文写作

| 模块 | 用途 |
|------|------|
| `scripts.research_framework.report_generator.ReportGenerator` | LaTeX/Word 双格式论文生成 |
| `scripts.research_framework.fin_charts.FinancialChartFactory` | 20+ 种专业金融图表（≥300 DPI） |
| `scripts.journal_template.JournalTemplate` | **30** 种期刊模板（EN/ZH/JP/DE），见 `scripts/count_assets.py` |

## 7. Skills（Cursor / Claude Code / Copilot，17 个）

| Skill | 功能 |
|-------|------|
| `fin-full-pipeline` | 端到端流水线（主题→论文 PDF） |
| `fin-idea-discovery` | 想法发现 + 数据验证 |
| `fin-lit-review` | 系统性文献综述 |
| `fin-generate-idea` | 8-12 个排序想法（含实证验证） |
| `fin-novelty-check` | 新颖性验证（JF/JFE/RFS 查重） |
| `fin-experiment-design` | 完整实证设计（DID/IV/RD/PSM） |
| `fin-paper-writing` | 论文写作编排 |
| `fin-paper-draft` | 正文生成（LaTeX） |
| `fin-paper-plan` | 大纲生成（30 种期刊模板） |
| `fin-paper-figure` | 图表生成（≥300 DPI，20+类型） |
| `fin-paper-convert` | LaTeX 编译 |
| `fin-review-loop` | 多轮对抗性 review |
| `fin-submit-check` | 投稿前检查 |
| `fin-data-acquisition` | 数据获取 + 回归脚本生成 |
| `fin-brief-generator` | 生成 `FIN_BRIEF.md` |
| `fin-ref-paper` | BibTeX 参考文献管理 |
| `fin-viz-launch` | 自然语言 → 学术图表 |

完整 17 个 skill 文件在 `.cursor/skills/`。

## 8. MCP 数据源（`{{MCP_COUNT}}` 个目录，自动生成）

> 数字由 `scripts/count_mcp.py` 自动扫描并写入 `.docs-cache/MCP_COUNT.txt`。

| 类型 | 数量 | 说明 |
|------|------|------|
| 学术文献 | 5 | OpenAlex, ArXiv, Context7, Semantic Scholar, NBER |
| A 股数据 | 4 | Tushare, Wind, CSMAR, 东方财富研报 |
| 美股/全球 | 3 | yfinance, SEC EDGAR, enhanced-finance |
| 宏观经济 | 10 | World Bank, IMF, OECD, BEA, Fed, FRED, EODHD, financial 等 |
| 工具类 | 21+ | 浏览器、文件系统、LaTeX、pandas、加密货币等 |

完整列表：`python scripts/register_mcp_servers.py --list` 或 `ls mcp_servers/user_*/`。

---

## 维护说明

- 本文件当前为**人工编写的初始版**（2026-06-27）
- 计划：未来用 `mkdocstrings` 从 docstring 自动生成
- 不在本文件列出的模块属于**内部实现细节**，可能随时变更
- 发现过时内容请提交 PR 或 issue