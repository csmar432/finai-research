# Scripts Index · 脚本索引

> 本文件是 `scripts/` 目录的权威索引。每个脚本都有分类标签和使用说明。
> 最后更新: 2026-07-07（自动对账）

---

## 分类总览

| 分类 | 数量 | 说明 |
|------|------|------|
| 🚀 Entry Points (`scripts/*.py`) | 104 | 顶级入口脚本（含 CLI） |
| 📦 Core Modules (`scripts/core/`) | 105 | 核心库（被其他模块导入）|
| 📊 Research Framework (`scripts/research_framework/`) | 56 | 计量方法模块 |
| 🧭 Research Directions (`scripts/research_directions/`) | 15 | 研究方向领域 |
| 🧪 Tests (`tests/`) | 653 | 测试文件 |
| 🔌 MCP Servers (`mcp_servers/user_*/`) | 43 | MCP 数据源 |
| **合计（仅 Python 文件）** | **936** | 不含 MCP / docs / tests fixtures |

> 自动生成于 2026-07-14
---

## 一、Entry Points · 用户入口

这些脚本有独立的命令行接口（`if __name__ == "__main__"`），用户可以直接运行。

### 1.1 核心研究 Pipeline

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `agent.py` | `python scripts/agent.py` | 统一的 AI 研究 Agent CLI（主入口） |
|| `agent_pipeline.py` | via `AI()` class | 5-Agent 流水线编排器（AgentPipeline 类，被其他模块导入） |
|| `enhanced_workflow.py` | `python scripts/enhanced_workflow.py` | 增强研究工作流（含 HITL checkpoint） |
|| `interactive_paper_pipeline.py` | `python scripts/interactive_paper_pipeline.py` | 交互式论文写作（每个章节 checkpoint） |
|| `research_workflow.py` | — | **已废弃** → `deprecated/research_workflow.py`，使用 `agent_pipeline.py` |

### 1.2 论文写作与提交

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `paper_write.py` | `python scripts/paper_write.py` | 端到端论文写作（含 outline → chapter → full draft） |
|| `paper_full_pipeline.py` | `python scripts/paper_full_pipeline.py` | 生成 → 润色 → Word 转换 |
|| `paper_submitter.py` | `python scripts/paper_submitter.py` | 完整投稿系统（arXiv / SSRN / OpenReview） |
|| `paper_submit.py` | `python scripts/paper_submit.py` | `paper_submitter.py` 的 CLI 封装 |
|| `paper_tools.py` | `python scripts/paper_tools.py` | LaTeX / BibTeX / 查重工具合集 |
|| `paper_versioning.py` | `python scripts/paper_versioning.py` | Git 风格的论文版本控制 |
|| `paper_visualizer.py` | `python scripts/paper_visualizer.py` | 架构图 / 结果可视化生成 |
|| `paper_reader.py` | `python scripts/paper_reader.py` | 论文下载 / 摘要 / 问答（支持 arXiv / Semantic Scholar） |
|| `generate_docx_tables.py` | `python scripts/generate_docx_tables.py` | LaTeX/Markdown 表格 → Word 格式转换 |
|| `generate_empirical_tables.py` | `python scripts/generate_empirical_tables.py` | 从回归结果生成规范三线表格（LaTeX/HTML/MD） |

### 1.3 实证分析

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `empirical_agent.py` | `python scripts/empirical_agent.py` | 智能实证分析 Agent（自动诊断 + 调参） |
|| `empirical_advisor.py` | via class | 实证分析顾问（5级调参策略，被 `empirical_agent.py` 使用） |
|| `econometrics_extended.py` | `python scripts/econometrics_extended.py` | 核心计量引擎（DID / OLS / PSM / GMM / Heckman 等） |

### 1.4 金融分析

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `demo_research_report.py` | `python scripts/demo_research_report.py` | A股研报端到端演示（招商银行 600036） |
||| `factor_models.py` | `python scripts/factor_models.py` | Fama-French / Fama-MacBeth 因子模型 |
|| `quantitative_factor_library.py` | `python scripts/quantitative_factor_library.py` | 量化因子库 + 事件研究 |

### 1.5 监测与可视化

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `dashboard.py` | `streamlit run scripts/dashboard.py` | 研究进度监控 Dashboard（Streamlit） |
|| `workflow_viz_server.py` | `python scripts/workflow_viz_server.py` | 工作流可视化 HTTP 服务 |
|| `pipeline_builder.py` | `streamlit run scripts/pipeline_builder.py` | 低代码 Pipeline 构建器（Streamlit） |
|| `run_research.py` | `python scripts/run_research.py` | 队列消费者 + 可视化服务器启动器 |
|| `event_monitor.py` | `python scripts/event_monitor.py` | 宏观事件监控（NFP / CPI / FOMC 自动触发研究） |
|| `fin-viz-launcher.py` | `python scripts/fin-viz-launcher.py` | 自然语言图表生成启动器 |

### 1.6 文献与引用

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `citation_graph.py` | `python scripts/citation_graph.py` | 引用网络构建（支持多个来源） |
|| `literature_download.py` | `python scripts/literature_download.py` | 批量论文下载（arXiv / Semantic Scholar / NBER） |
|| `paper_quality_scorer.py` | `python scripts/paper_quality_scorer.py` | 论文质量评分（ACL/NeurIPS 标准） |

### 1.7 配置与安装

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `setup_wizard.py` | `python scripts/setup_wizard.py` | 首次配置向导（交互式） |
|| `register_mcp_servers.py` | `python scripts/register_mcp_servers.py` | MCP 服务器注册 CLI |
|| `keychain_setup.py` | `python scripts/keychain_setup.py` | macOS Keychain API Key 管理 |

### 1.8 数据与省份

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `data_version.py` | `python scripts/data_version.py` | 数据版本管理器 |
||| `generate_hubei_excel_v2.py` | `python scripts/generate_hubei_excel_v2.py` | v2 版（样式更丰富） |
|| `generate_national_excel.py` | `python scripts/generate_national_excel.py` | 全国各省 Excel 报告 |

### 1.9 特殊用途

|| 脚本 | 命令 | 说明 |
||------|------|------|
|| `on_enter.py` | 在 `.zshrc` 中自动调用 | 进入目录时自动唤醒研究 Agent |
||| `cleanup_paper_index.py` | `python scripts/cleanup_paper_index.py` | 一次性：清理 paper_index.json 中的过期记录 |

---

## 二、Core Modules · 核心库

这些脚本**没有独立的 CLI**，它们通过 `from scripts.xxx import Y` 被其他脚本使用。

|| 脚本 | 行数 | 主要类/函数 | 被导入位置 |
||------|------|------------|-----------|
|| `ai_router.py` | 1355 | `AIRouter`, `ModelKey`, `ModelPool` | `agent_pipeline`, `paper_write`, `paper_tools_core`, `empirical_advisor`, `dashboard`, `paper_full_pipeline`, `interactive_paper_pipeline`, `paper_reader`, `paper_quality_scorer`, `paper_visualizer`, `paper_submit`, `core/llm_gateway`, `core/llm_reviewer` |
|| `empirical_advisor.py` | 1444 | `EmpiricalAdvisor`, `DiagnosticSuite` | `empirical_agent`, `generate_empirical_tables`, `econometrics_extended`, `agent_pipeline`, `research_directions/` |
||| `econometrics_extended.py` | 2083 | `RDDRegression`, `FamaMacBeth`, `PanelThresholdReg`, `EventStudyCAR` | `empirical_advisor`, `research_directions/` |
|| ~~`econometrics_advanced.py`~~ | ~~963~~ | ~~Wild bootstrap, Baron-Kenny mediation~~ | **v6 已删除**（0 import，2026-06-18）|
|| `journal_template.py` | 3991 | `JournalTemplate`, `generate_latex()`, `JOURNAL_METADATA` | `agent_pipeline`, `paper_write`, `paper_full_pipeline` |
|| `knowledge_graph.py` | 1152 | `CitationGraph`, `build_graph()`, `find_papers()` | `paper_write`, `paper_reader`, `research_rag`, `review_layer`, `__init__.py` |
|| `experiment_tracker.py` | 909 | `ExperimentTracker`, `track()`, `compare()` | `agent_pipeline`, `dashboard`, `paper_write`, `review_layer` |
|| `research_rag.py` | 1000 | `ResearchRAG`, `index()`, `query()`, `retrieve()` | `dashboard`, `paper_write`, `core/llm_reviewer`, `__init__.py` |
|| `review_layer.py` | 680 | `ReviewLayer`, `batch_review()`, `fix_quality()` | `paper_write`, `agent_pipeline`, `paper_full_pipeline` |
|| `paper_tools_core.py` | 310 | `submit_to_arxiv()`, `submit_to_ssrn()`, `submit_to_openreview()` | `paper_submit`, `paper_submitter` |
|| `paper_quality_scorer.py` | 701 | `PaperQualityScorer`, `score()`, `suggest_improvements()` | `agent_pipeline`, `dashboard`, `paper_write` |
|| `paper_versioning.py` | 708 | `PaperVersionManager`, `commit()`, `diff()`, `restore()` | `paper_write`, `agent_pipeline` |
|| `prisma_tracker.py` | 463 | `PRISMATracker`, `generate_flow_diagram()` | （纯库函数，无广泛外部导入） |
|| `citation_stance.py` | 419 | `CitationStanceClassifier`, `classify()` | `knowledge_graph`, `citation_graph` |
||| `data_pipeline.py` | 174 | 轻量数据管道（大部分已被 `research_framework/` 替代） | `interactive_paper_pipeline` |
|| `__init__.py` | 37 | 重新导出 `AI`, `Task`, `KnowledgeGraph`, `ResearchRAG` | — |

---

## 三、Tool Scripts · 工具脚本

一次性或窄用途的脚本，不属于主流研究流程。

|| 脚本 | 用途 | 说明 |
||------|------|------|
|| `auto_register_tools.py` | MCP 注册 | 修补 `tool_selector.py` 注册表 |
|| `cleanup_paper_index.py` | 数据清理 | 清理 paper_index.json 过期记录 |
||| `fetch_msci_xu.py` | 数据采集 | MSCI ESG 评级批量抓取（支持 --person 参数）|
|| `fetch_msci_cyh.py` | 数据采集 | MSCI ESG 评级批量抓取（支持 --person 参数）|
|| `fetch_msci_xu2.py` | 数据采集 | `fetch_msci_xu.py` 的修订版（无独立入口） |
|| `fetch_provincial_stats.py` | 数据采集 | 各省统计数据获取 |
|| `fix_metadata.py` | 数据修复 | 一次性 MCP 元数据修复 |
|| `generate_docx_tables.py` | 格式转换 | LaTeX/MD → Word 表格 |
|| `generate_empirical_tables.py` | 表格生成 | 从计量结果生成规范表格 |
|| `green_credit_data.py` | 绿色金融 | 绿色信贷数据管道 |
|| `green_credit_formatter.py` | 绿色金融 | 绿色信贷论文格式转换 |
|| `green_credit_regression.py` | 绿色金融 | 绿色信贷 DID 回归 |
|| `green_credit_visualizer.py` | 绿色金融 | 绿色信贷 matplotlib 图表 |
|| `literature_download.py` | 文献下载 | 批量 arXiv / NBER 论文下载 |
|| `paper_tools.py` | 工具集 | LaTeX / BibTeX / 查重工具 |
|| `parse_mcp_data.py` | 数据解析 | MCP 响应数据解析器 |
|| `register_mcp_servers.py` | MCP 配置 | MCP 服务器注册 |
|| `us_esg_formatter.py` | ESG 格式 | 美国 ESG 论文格式化（无独立入口） |
|| `us_esg_regression.py` | ESG 回归 | 美国能源板块 ESG 回归 |
|| `verify_metadata.py` | 数据验证 | 元数据一次性验证 |
||| `generate_hubei_excel_v2.py` | Excel 报告 | v2 版 |
|| `generate_national_excel.py` | Excel 报告 | 全国各省 Excel 报告 |

---

## 四、Obsolete · 废弃

以下脚本已废弃，**不应使用**：

|| 脚本 | 废弃原因 | 替代品 |
||------|---------|--------|
| `research_workflow.py` | 被 `agent_pipeline.py` 替代 | `scripts/agent_pipeline.py` |

> 注：`fetch_msci_xu.py`、`fetch_msci_xu2.py`、`fetch_msci_cyh.py` 为个人数据采集脚本，根据需要保留或清理。

---

## 五、Subdirectories · 子目录

`scripts/` 下的子目录包含更专业的模块，不在本索引范围内：

|| 目录 | 内容 |
||------|------|
|| `scripts/core/` | 核心 Agent 系统（79个文件，72个非测试模块）：orchestrator, memory, planner, reflector, session, tool_selector, hitl_gate, llm_gateway, latex_lint, latex_diff, pdf_vision_check, sandbox, self_evolution, cross_session_knowledge, literature_vector_store, macro_event_bus, checkpoint, provenance, mcp_tool_market, agent_state, reviewer_calibrator, chart_factory, chart_pipeline, ai_parliament, collaboration, presence_server, sandbox_executor, plotstyle_validator, vlm_chart_critic 等 |
|| `scripts/research_framework/` | 实证研究框架（**41个模块**，v0.1.0 新增10个）：pipeline, data_fetcher, data_validator, regression_engine, modern_did, synthetic_control, synthetic_did, rdd, spatial_regression, iv_panel, robustness_runner, panel_quantile_regression, interactive_fixed_effects, local_projections_did, triple_diff_did, vuong_kob, leamer_sensitivity, diagnostic_reporter, finance_sensitivity, kob_decomposition, vuong_test, enhanced_pipeline, fin_charts, report_generator, a_share_variables, policy_database, base, journal_templates_multilang, provenance_rag, **panel_var**, **discrete_choice**, **volatility_models**, **time_varying_models**, **survival_analysis**, **causal_ml**, **panel_cointegration**, mediation_test, panel_threshold_regression, prisma_compliance, **green_bond_model**, **options_iv_surface** |
|| `scripts/research_directions/` | 研究方向定义（12个）：digital_finance, green_finance, carbon_economics, corporate_finance, macro_finance, asset_pricing, behavioral_finance, fintech_innovation, real_estate_finance, international_finance, political_economy_finance, esg_finance |

---

## 六、贡献指南

### 添加新脚本

1. 确定分类：Entry Point / Core Module / Tool Script
2. Entry Point 必须有 `if __name__ == "__main__":`
3. 在本索引中登记
4. 如果是 Core Module，在 `scripts/__init__.py` 中添加重新导出（如适用）

### 归档工具脚本

如果工具脚本不再需要，可以：
1. 移到 `scripts/archive/` 目录（保留历史）
2. 从本索引中移除
3. 更新 git commit

### 命名规范

```
entry_point_*.py      # 用户入口（小写下划线）
core_module_*.py      # 核心库（小写下划线）
data_fetch_*.py       # 数据采集（小写下划线）
report_*.py           # 报告生成（小写下划线）
```

---

*本索引由 `scripts/SCRIPTS_INDEX.md` 维护，最后更新: 2026-07-14（自动对账）
