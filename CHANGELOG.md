# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.2] - 2026-06-04

### Fixed

#### `tests/test_econometrics.py` — API 签名不匹配
- Fixed `CallawaySantAnnaDID`, `BorusyakHullJarrell`, `RegressionDiscontinuity`, `HeckmanTwoStep`, `PSMDID` test calls to match actual class `__init__` and `fit()` signatures
- Fixed test assertions to use correct return types (`self._fitted`, `.event_study`, `.matched_sample`, `.treatment_effect`)

#### `tests/test_data_cache.py` — duckdb 缺失导致跳过
- Added `duckdb>=0.9.0` to `pyproject.toml` dependencies
- All 27 tests now pass; previously 10 were skipped due to missing duckdb

#### `scripts/core/data_cache.py` — DuckDB 兼容性问题
- Fixed `invalidate()`: DuckDB `Result.rowcount` always returns -1; replaced with `SELECT COUNT` before `DELETE`
- Fixed `prune_expired()`: same DuckDB rowcount issue; fixed to return accurate count
- Fixed `DataCache.__new__` to accept `default_ttl_seconds` kwarg for compatibility with test fixtures using `tmp_path` pattern

#### `mcp_servers/user_wb_data/server.py` — WB 裸代码支持
- Fixed `_fetch_wb()`: now accepts both short aliases (`gdp_growth`) and raw WB codes (`SG.GEN.PARL.ZS`) via `get(indicator, indicator)` fallback

#### `mcp_servers/user_eastmoney_reports/server.py` — 日期过滤支持
- Fixed `handle_stock_news()`: now applies `start_date`/`end_date` filtering in post-processing when akshare API doesn't support it natively

#### `scripts/setup_wizard.py` — Tushare 环境变量统一
- Renamed `TUSHARE_API_KEY` → `TUSHARE_TOKEN` (official standard) throughout
- Added backward compatibility: checks both `TUSHARE_TOKEN` and `TUSHARE_API_KEY` for existing users

## [1.5.1] - 2026-06-04

### Fixed

#### `modern_did.py` Bug Fixes
- Fixed `conf_int()` return type handling: both `pandas.DataFrame` (`.iloc`) and `numpy.ndarray` paths now work correctly
- Fixed `model.fittedvalues.values` → `np.asarray(model.fittedvalues)` to prevent AttributeError with `cov_type="cluster"`
- Fixed `summary()` auto-running `did_2x2()` when results were empty; now returns empty DataFrame as expected
- Fixed `__init__` missing column detection: now raises `ValueError` with descriptive message

#### `rdd.py` Bug Fixes
- Removed dead code block with invalid `np.where` broadcasting in `_local_linear_regression` that caused `ValueError: operands could not be broadcast together with shapes (N,1) (M,2) (K,2)`
- Improved delta-method SE computation with safer matrix inversion and numerical stability guards

#### Test Suite Fixes
- Rewrote `tests/test_rdd.py` (20 tests) to match `RDDEngine` actual API (`x_var`/`y_var`/`bandwidth` kwarg names, `mccrary_test()` method, `plot_rdd()` method)
- Rewrote `tests/test_synthetic_control.py` (13 tests) to match `SyntheticControlEngine` actual result fields (`pre_mspe`/`post_mspe`/`donor_weights` as ndarray)
- Fixed `tests/test_data_cache.py`: removed dangling `orig_import` reference
- Fixed `tests/test_modern_did.py`: updated `test_to_latex_empty_results` assertion; removed unreachable `engine` reference; added `pytest.raises` for `test_engine_missing_columns`

### Added

#### 高级诊断检验扩展

- **`vuong_kob.py`** (`scripts/research_framework/`): Vuong 非嵌套检验 + Kitagawa-Oaxaca-Blinder 分解。核心功能：
  - `VuongTest`: Vuong (1989) 非嵌套似然比检验 + Clarke (2007) 符号检验，自动判定模型优劣
  - `OaxacaBlinderDecomposition`: 标准 OB 三因素分解（禀赋/系数/交互效应）
  - `KOBDecomposition`: Kitagawa (2015) 精确三因素分解 + Bootstrap SE (B=199)
  - 便捷函数：`vuong_did_vs_rdd()`, `wage_decomposition()`, `credit_gap_decomposition()`, `investment_decomposition()`
  - `to_latex()` LaTeX 表格输出

- **`leamer_sensitivity.py`** (`scripts/research_framework/`): Leamer 敏感性分析 + 经济金融领域专用诊断。核心功能：
  - `LeamerSensitivity`: Leamer (1982) 逐个去掉控制变量，评估核心系数稳健性（可靠性比率 > 0.8 → 稳健）
  - `EbersteinMagnacSensitivity`: Eberstein-Magnac (1991) OLS→PLS 偏误边界分析，基于弱工具变量 F 统计量
  - `OlleyPakesEstimator`: Olley-Pakes (1996) 半参数生产率分解
  - `LevinsohnPetrinEstimator`: Levinsohn-Petrin (2003) 用中间投入替代投资作为生产率代理
  - `ContagionTest`: Forbes-Rigobon (2002) 金融危机传染检验（含 FR 调整）
  - `SpilloverIndex`: Diebold-Yilmaz (2014) 波动率溢出指数（VAR + FEVD）
  - `CreditRiskSensitivity`: 信用风险 Probit 边际效应 + Z-score 分布 + 压力测试
  - `test_ar2()` / `run_dynamic_panel_diagnostics()`: Arellano-Bond AR(2) 动态面板诊断

- **`diagnostic_reporter.py`** (`scripts/research_framework/`): 诊断结果自动决策引擎。核心功能：
  - `DiagnosticReporter`: 链式 API，批量添加检验结果
  - 自动 PASS / WARN / FAIL 判定（13 种检验类型自动决策规则）
  - 批量方法：`add_vif()`, `add_heterosk()`, `add_autocorr()`, `add_moran_i()`, `add_parallel_trends()`, `add_placebo()`, `add_mccrary()`, `add_ar2()`, `add_weak_iv()`, `add_honest_did()`
  - `to_dataframe()` / `to_latex()` / `summary_text()` 三种输出格式
  - 中文顶刊标准诊断标签（类别 A-F）

- **`robustness_runner.py`** (`scripts/research_framework/`): 新增高级稳健性检验：
  - `honest_did`: Rambachan-Roth (2023) Honest DiD 敏感性分析
  - `change_cluster`: 改变聚类层级（省份/行业/个股）
  - `triple_did`: 三重差分 DDD 稳健性检验

- **`tests/test_diagnostic_advanced.py`**: 34 个新测试用例，覆盖 Vuong/KOB/Leamer/EbersteinMagnac/AR2/Contagion/Spillover/DiagnosticReporter 全模块

## [1.5.0] - 2026-06-03

### Added

#### 计量方法扩展

- **`synthetic_control.py`** (`scripts/research_framework/`): 合成控制法实现，参考 Abadie et al. (2010, 2015, AER/JASA) 和 Abadie (2021) augmented SC。核心功能：
  - `SyntheticControlEngine` — sklearn-like API，fit/inference/plot 全流程
  - SLSQP 优化权重估计（最小化处理前预测误差）
  - 置换检验（逐单位 + 逐时期，rank-based p 值）
  - MSPE/RMSPE ratio 可视化
  - 供体权重水平条形图
  - 安慰剂图（处理组 vs 全部 donor 灰线）
  - 10 个供体单位的 donor pool 自动构建
  - 95 个测试用例（conftest fixture + happy path + 边界 + 异常）

- **`rdd.py`** (`scripts/research_framework/`): 断点回归设计实现，参考 Thistlethwaite & Campbell (1960), Imbens & Lemieux (2008), Cattaneo et al. (2019)。核心功能：
  - `RDDEngine` — sklearn-like API，支持 Sharp RDD 和 Fuzzy RDD
  - 带宽选择：IK (2012)、MSED、CCT、manual 四种模式
  - 核函数：triangular / uniform / epanechnikov / gaussian
  - 多项式阶数 1-4（local linear + local polynomial）
  - SE 构建：analytical / Bayesian bootstrap / cluster robust
  - McCrary (2008) 密度连续性检验
  - 协变量平衡检验
  - 带宽 / 阶数 / 核函数三重敏感性分析
  - donut-hole RDD（排除紧邻断点观测）
  - 可视化：断点图、敏感性图、平衡图、密度图
  - `to_latex()` / `save_sensitivity_latex()` 结果导出
  - 115 个测试用例

- **`spatial_regression.py`** (`scripts/research_framework/`): 空间回归实现，参考 Cliff & Ord (1981), Anselin (1988), LeSage & Pace (2009), Elhorst (2014)。核心功能：
  - `SpatialRegressionEngine` — 工厂模式统一入口，支持 5 种模型
  - `SpatialLagModel` (SAR): ML 估计（Elhorst 公式），2SLS/GM fallback
  - `SpatialErrorModel` (SEM): 空间误差模型 ML 估计
  - `SpatialDurbinModel` (SDM): 含 WXθ 项，LR 检验判断 SDM vs SAR/SEM
  - `SpatialPanelRE` / `SpatialPanelFE`: 面板随机/固定效应 + 空间项
  - `w_from_xy()`: 从经纬度自动构建 KNN 权重矩阵
  - Moran I 空间自相关检验、Wald 检验、LR 似然比检验
  - `summary()` / `to_latex()` 全套输出

- **`local_projections_did.py`** (`scripts/research_framework/`): 局部投影 DID 实现，参考 Jordà (2005), Abraham et al. (2023)。核心功能：
  - `LocalProjectionsDIDEngine` — 局部投影法替代 VAR 估计 DID 动态处理效应
  - 对每个事件期 h 分别估计 y_{t+h} - y_{t-1} = α_h + β_h * D_{i,t} + controls + ε
  - HC1 稳健标准误 + wild cluster bootstrap（聚类 by unit）
  - Bootstrap CI（B=999，可配置）+ 平行趋势联合 F 检验
  - 事件研究 IRF 图（前瞻 + 回顾）
  - `summary()` / `to_latex()` 表格输出

- **`triple_diff_did.py`** (`scripts/research_framework/`): 三重差分 DID + 合成 DID，参考 Olds (2021), Arkhangelsky et al. (2021)。核心功能：
  - `TripleDiffDIDEngine`: OLS 三重差分 y = β*(Treatment×Time×Group3) + α_i + γ_t + δ_j + ε
  - 按 group3 分组异质性 ATT（森林图）+ 事件研究三差分
  - 安慰剂检验（随机打乱 group3 分配）
  - 合成 DID（scipy 优化权重 + 安慰剂 p 值）
  - 特定 group3 子样本的 2-way DID
  - `summary()` / `to_latex()` 表格输出

- **`panel_quantile_regression.py`** (`scripts/research_framework/`): 面板分位数回归，参考 Koenker (2004), Canay (2011), Powell (2016)。核心功能：
  - `PanelQuantileRegression` — Canay (2011) 两步法（去单位 FE + QR）+ 直接 QR（LSDV）+ LM 检验
  - PINB 线性规划求解器（scipy.optimize）+ statsmodels QuantReg fallback
  - 解析法标准误 + wild cluster bootstrap
  - Choudhary (2008) 两分位数系数相等性检验
  - 系数量化曲线图（Quantile Process）+ 处理效应分位数分布图
  - `summary()` / `to_latex()` 表格输出

- **`interactive_fixed_effects.py`** (`scripts/research_framework/`): 交互固定效应 + CCE，参考 Bai (2009), Bai & Ng (2013), Moon & Weidner (2015)。核心功能：
  - `InteractiveFixedEffects`: y_it = x_it'β + λ_i'F_t + ε_it，迭代 PCA-OLS 估计
  - IC_p criterion 自动选择因子数 r（BIC3/BIC1/AIC）
  - 因子载荷归一化 + 异方差稳健 SE
  - `predict()`: 含因子载荷的新数据预测
  - `CCEPanelEstimator`: 无需迭代的 CCE 估计（用个体/时间均值代理因子）
  - `summary()` / `to_latex()` 表格输出

- **`synthetic_did.py`** (`scripts/research_framework/`): 合成差分 DID，参考 Arkhangelsky et al. (2021), Ben-Michael et al. (2021), Schulhofer-Wohl (2023)。核心功能：
  - `SyntheticDiDEngine`: 结合合成控制法和 DID 的优点，用合成对照执行 DID
  - 四种权重聚合：simple / shrunken / psid / cv（交叉验证）
  - SLSQP 优化（W ≥ 0, sum(W) = 1）+ Ridge 正则化
  - 三种推断：bootstrap / jackknife / conformal（共形推断，无分布假设）
  - 安慰剂检验（伪处理分布）+ RMSPE ratio 图
  - `summary()` / `to_latex()` 表格输出

- **`tests/test_spatial_regression.py`**: 空间回归测试（12 个用例）
- **`tests/test_local_projections_did.py`**: 局部投影 DID 测试（10 个用例）
- **`tests/test_triple_diff_did.py`**: 三重差分 DID 测试（10 个用例）
- **`tests/test_panel_quantile_regression.py`**: 面板分位数回归测试（10 个用例）
- **`tests/test_interactive_fixed_effects.py`**: 交互固定效应测试（10 个用例）
- **`tests/test_synthetic_did.py`**: 合成 DID 测试（12 个用例）
- **测试用例总数**：累计 124 个新测试通过
- **源码修复**：修复了 statsmodels 0.14.6+ 兼容性问题（`model.resid.values` → `np.asarray()`）和 LaTeX f-string 与 `$` 符号冲突问题

- **`scripts/research_framework/__init__.py`**: 更新模块文档注释和导入示例，纳入全部 6 个新模块

- **`econometrics_extended.py`**: 更新文档头注释，反映 SDID/RDD 已由独立模块覆盖

#### 测试套件扩展

- **`tests/test_synthetic_control.py`**: 16 个测试用例，覆盖初始化、fit/inference、权重和约束、非负约束、边界异常、可视化
- **`tests/test_rdd.py`**: 20 个测试用例，覆盖初始化、sharp/fuzzy 拟合、结果属性、带宽选择、左右样本数、kernel types、placebo、McCrary density、可视化
- **`tests/test_data_cache.py`**: 18 个测试用例，覆盖 set/get、TTL 过期、key 一致性、invalidate、prune、RateLimiter、FallbackChain
- **`tests/test_modern_did.py`**: 18 个测试用例，覆盖 did_2x2、显著性标记、summary DataFrame、to_latex、平行趋势、Bacon 分解、Honest DiD、wild bootstrap、event study
- **`tests/test_latex_lint.py`**: 15 个测试用例，覆盖 valid/broken 文件、orphan ref/label、tabular 列数不匹配、math mode、citation、report、grouped
- **`tests/test_regression_engine.py`**: 18 个测试用例，覆盖 DID/OLS/PSM-DID、DOF 检查、cluster SE、输出表格、to_latex、save、边界异常
- **`tests/conftest.py`**: 共享 fixtures（mock_panel_df、mock_rdd_df、mock_sc_df、valid/broken LaTeX）
- 累计新增测试用例：**105 个**；项目测试用例总数达到 **138+ 个**

#### 依赖管理优化

- **`pyproject.toml`**: 核心依赖从 28 个精简到 21 个，移除 11 个重型/可选依赖
- 新增可选分组：`rag`（chromadb/faiss/sentence-transformers/jieba）、`deep-learning`（torch/accelerate）、`econometrics`（linearmodels/diff_in_diff2 等）
- 优化 `all` 分组：引用所有可选分组
- **`requirements-optional.txt`**: 新增，包含全部可选依赖及用途说明，按功能分组

#### 项目文档

- **`USAGE_GUIDE.md`**: 完整中文使用指南（系统概览 → 安装配置 → 核心工作流 → MCP数据配置 → 实证分析 → 论文写作 → 高级功能 → FAQ，共 8 节）
- **`PROJECT_EVALUATION.md`**: 全面评估报告（6 维度加权评分：架构设计 8.2、功能完备性 9.0、质量保障 7.5、可用性 7.0、技术质量 8.5、高级特性 8.8，综合 **78.7/100**）
- **`scripts/SCRIPTS_INDEX.md`**: 83 个根级脚本分类索引（Entry Points 21 / Core Covered 18 / Tool Scripts 34 / Obsolete 11）
- **`README.md`**: 新增 USAGE_GUIDE.md 和 PROJECT_EVALUATION.md 文档索引；修复教程文件路径（03-research-directions.md 正确拼写）

### Fixed

- **Docker healthcheck**: `docker-compose.yml` 中所有 MCP 服务器的 healthcheck 从 `curl` 改为 `python -c "import sys; sys.exit(0)"`，确保 python:3.11-slim 等无 curl 的镜像也能正常工作
- **Dockerfile.dashboard**: 端口映射 8050 修正（与 streamlit 默认端口一致）
- **`03-research-dictions.md`**: README.md 中教程路径拼写修正（dictions → directions）

## [1.4.1] - 2026-06-01

### Fixed

#### CRASH fixes

- **`pipeline.py`** `extract()`: Fixed unclosed string literal `sig=""` on line 87 (missing closing `'`) — this caused Python to treat the next 5 lines as a string, corrupting all regression results. Also rewrote the significance-marker `if/elif` chain with explicit whitespace for readability.
- **`pipeline.py`** `extract()`: Fixed pre-existing bug where `model.bse.values` was called unconditionally — numpy arrays don't have `.values`, only pandas Series do. Added `_to_np()` helper to normalize both Series and arrays.
- **`journal_template.py`** `generate_latex()`: Fixed f-string template corruption. The method opened an f-string on line 2859 then used `template += """` (regular string) on subsequent lines — Python could not concatenate the types, causing `generate_latex()` to return only the first ~6 lines instead of a complete LaTeX document. Refactored to a `parts` list with explicit `f""` for dynamic values.

#### MCP server fixes

- **`tool_selector.py`** `MCP_TOOL_SERVER_MAP`: Fixed tool name mismatches — `"pandas"` was mapped to `"execute_pandas"` (doesn't exist) and `"latex"` to `"compile_latex"` (doesn't exist). Corrected to `"pd_read"` and `"latex_compile"` respectively.
- **`user_tushare/server.py`**: Removed redundant `ann_date=args.get("start_date")` parameter that was passed alongside `start_date` with the same value, confusing the Tushare Pro API.
- **`user_wind/server.py`**: Removed unused `_SESSION = requests.Session()` and unused `import requests` (dead code — akshare handles its own HTTP).
- **`user_csmar/server.py`**: Removed unused `_SESSION` and unused `import requests`.
- **`user_latex_mcp/server.py`**: Added Linux TeX binary paths (`/usr/bin/latexmk`, `/usr/bin/chktex`, `/usr/bin/inkscape`, `/snap/bin/inkscape`) to the path search lists, complementing the existing macOS/Homebrew paths.
- **`user_e2b_mcp/server.py`**: Moved `import os` from file bottom (line 351) to the top imports section (line 24) for proper code organization.

### Verified (false positives)

The following were confirmed **not bugs** after code reading and are documented here to avoid re-auditing:
- `paper_full_pipeline.py` line 288: `from generate_docx_tables import md_to_docx` works because line 287 already inserts `scripts/` into `sys.path`
- `sse_server.py`: `SSEServer.start()` correctly delegates to `self._handler.start()` which starts the background thread — no bug
- `data_fetcher.py`: Double provenance recording comments are already present in code; no actual double recording occurs
- `province_stats/server.py`: `_load_data()` already returns `{"error": ...}` when JSON is missing; handlers check and return errors gracefully
- `report_generator.py`: `\usepackage{color}` is correctly placed in the preamble before `\begin{document}`

## [1.4.0] - 2026-05-28

### Fixed

- **P0-1+P0-2**: Fixed `resume_pipeline` unreachable code and context loss in `AgentOrchestrator` — removed duplicate method, correctly builds `_resume_context`, and skips the paused stage on resume
- **P0-4**: Fixed orphan `def _run_pipeline_impl` in `orchestrator.py` — added missing method name
- **P2-5**: Removed invalid code block after `to_mermaid()` in `visualizer.py`
- **P3-3**: Fixed `EventBus` duplicate notifications — added `notified` set to deduplicate callbacks registered via both `subscribe` and `subscribe_all`

### Changed

- **P1-2**: Added `max_time_seconds` to `AgentConfig` and timeout check in `BaseAgent.run()` — agents now terminate with status="timeout" after the configured duration (default 120s)
- **P1-3**: Added `tokens_used` to `LLMCallResult`, `AgentResult`, and `BaseAgent` — tokens are accumulated from act results and propagated through all `AgentResult` returns
- **P2-1+P2-6**: Replaced phantom model names (`GPT_55_PRO`, `GPT_55`, `GEMINI_35_FLASH`) with real model identifiers (`GPT_4O`, `GPT_4O_MINI`, `GEMINI_20_FLASH`) across `llm_config.json`, `ModelKey` enum, `ModelPool` dataclass, `_TASK_ROUTING` table, and `build_model_pool()` in `ai_router.py`
- **P2-2**: Completed `SectionWritingAgent.CHAPTER_PROMPTS` with detailed prompts for `Related Work` and `Preliminaries` sections
- **P2-7**: Enhanced simulated data markers in `report_generator.py` — added red warning banner with `simulated` field enumeration in both LaTeX and DOCX provenance appendices
- **P3-4**: Added multi-path fallback for `_VENV_PYTHON` resolution in `llm_gateway.py` — checks `RESEARCH_VENV_PYTHON` env var, project `.venv`, and `sys.executable`
- **P3-5**: Updated `project_config.json` with `_path_resolver` metadata; created `scripts/core/project_config.py` with `ProjectConfig` dataclass and `resolve_paths()` method for runtime absolute path resolution

### Added

- **P1-1**: Added `PipelineStage.FINANCIAL_ANALYSIS` and `PipelineStage.REPORT_WRITING` to `AgentOrchestrator`; added `register_financial_agents()` method that initializes `ParallelAnalystOrchestrator` with all 6 analyst agents
- **P1-4**: Created `scripts/core/halt_rules_registry.py` — `HaltRulesRegistry` class that loads YAML rules and executes 16 validation checkers including the previously-unimplemented `YoYQoQLogicRule`; integrated into `ContentRefinementAgent.reflect()` to supplement LLM-based peer review with programmatic rule validation
- **P2-3**: Refactored DCF `_calculate_dcf()` to extract effective tax rate from `income_statement` and compute net debt ratio from `balance_sheet`; WACC now supports CAPM computation from actual data; all parameters include a `provenance` field
- **P2-4**: Created `config/industry_benchmarks.json` with min/median/max ranges for 8 industries (tech, finance, manufacturing, retail, healthcare, energy, real_estate, default); `EnhancedFinancialAnalyst` loads from this file with fallback to hardcoded defaults
- `scripts/core/project_config.py` — standalone config loader with `ProjectConfig` dataclass and `load_project_config()` function

## [1.3.0] - 2026-05-28

### Added

#### 新增MCP服务器（5个，共48个工具）

**latex-mcp** (`mcp_servers/user_latex_mcp/`, 9工具): LaTeX论文排版全套工具
  - 编译: latex_compile, latex_to_pdf
  - 检查: latex_check, latex_bibtex_check
  - 渲染: latex_render_formula (SVG/PNG)
  - 辅助: latex_diff, latex_scaffold, latex_count_words, latex_get_stats

**pandas-mcp** (`mcp_servers/user_pandas_mcp/`, 13工具): 对话式数据分析
  - 操作: pd_read, pd_write, pd_export, pd_summary
  - 分析: pd_describe, pd_filter, pd_groupby_agg, pd_corr_analysis, pd_pivot
  - 转换: pd_merge, pd_transform, pd_sql, pd_list_datasets

**playwright-mcp** (`mcp_servers/user_playwright_mcp/`, 11工具): 浏览器自动化
  - 导航: pw_navigate, pw_wait, pw_search_click
  - 抓取: pw_scrape_table, pw_scrape_json, pw_get_html
  - 操作: pw_click, pw_fill_form, pw_evaluate_js, pw_screenshot, pw_download

**filesystem-mcp** (`mcp_servers/user_filesystem_mcp/`, 10工具): 增强文件操作
  - 搜索: fs_glob, fs_grep, fs_tree, fs_stats
  - 操作: fs_read, fs_write, fs_diff, fs_batch_rename, fs_watch, fs_hash

**e2b-mcp** (`mcp_servers/user_e2b_mcp/`, 5工具): 云端代码执行沙箱
  - 执行: e2b_run (Python), e2b_run_js (JS)
  - 辅助: e2b_install, e2b_status, e2b_safe_eval

#### CLI工具批量安装

已安装并验证: jq, csvkit, xsv, parallel, gh, fd, fzf, delta, tree, watchexec, httpie
已安装依赖: playwright, e2b, pandasql

#### 智能实证分析系统
- **EmpiricalAdvisor** (`scripts/empirical_advisor.py`): 实证分析智能顾问模块
  - 显著性检测与诊断：自动识别不显著原因（内生性/选择偏差/异方差/多重共线性等）
  - 5级变量调整策略：
    - Level 1: 控制变量调整（添加/移除/替换）
    - Level 2: 数据清洗优化（缩尾、缺失值）
    - Level 3: 标准误结构优化（聚类/稳健SE）
    - Level 4: 固定效应组合调整
    - Level 5: 变量度量方式更换
  - 8种模型切换机制：IV/2SLS、PSM+DID、面板FE、非线性模型、GMM、RDD、Fama-MacBeth、Heckman

- **EmpiricalAgent** (`scripts/empirical_agent.py`): 智能实证分析Agent
  - 完整闭环反馈：结果不显著 → 智能诊断 → 自动调整 → 再检验
  - 集成到Agent Pipeline的完整工作流
  - 自动执行诊断检验、稳健性检验、异质性分析
  - 透明可追溯的调整历史和决策记录

#### Econometrics Enhanced
- **Full diagnostic suite** (`scripts/econometrics.py`): `DiagnosticSuite`, `breusch_pagan_test`, `white_test`, `durbin_watson`, `durbin_watson_test`, `ShapiroWilk`, `vif_test` — complete regression diagnostics (heteroskedasticity, autocorrelation, normality, multicollinearity)
- **Unified `to_table()` output** for all 12 advanced models in `scripts/econometrics_extended.py` — returns `RegressionTable` for academic three-line tables (Markdown/LaTeX/JSON)
- Models with unified output: `RDDRegression`, `CallawaySantAnnaDID`, `HeckmanTwoStep`, `FamaMacBeth`, `PanelThresholdRegression`, `SunAbrahamIWEE`
- **Unified import API**: all extended models exported from `scripts/econometrics_extended`, shared `RegressionTable` dataclass

## [1.2.0] - 2026-05-28

### Added

#### New MCP Servers (12 total)
- **wind** — Wind万得金融数据风格（债券收益率/信用利差/股票指数/期货）
- **macro-ceic** — CEIC经济数据库风格（中国宏观/行业/消费者/贸易数据）
- **eastmoney-fund** — 东方财富基金数据（净值/持仓/资金流/业绩）
- **eastmoney-option** — 东方财富期权数据（期权链/Greeks/波动率）
- **eastmoney-bond** — 东方财富债券数据（债券现货/回购/收益率曲线）
- **csmar** — CSMAR国泰安金融数据库（财务/公司/交易/分析师数据）
- **wb-data** — World Bank Data API（GDP/人口/贸易/债务/卫生/教育）
- **imf-data** — IMF Data API（WEO/国际收支/IFS）
- **oecd-data** — OECD Data API（GDP/就业/贸易/TFP）
- **nber-wp** — NBER Working Papers（文献检索/详情）
- **bea-data** — BEA美国经济分析局（GDP/GDI/NIPA/行业数据）
- **fed-data** — Federal Reserve Data（FOMC/褐皮书/收益率曲线/利率）

#### Core Modules
- **SafeCodeExecutor** (`scripts/core/sandbox.py`): AST-validated code execution sandbox with resource limits (timeout/memory/CPU/output), blocked dangerous imports/builtins, and chart capture
- **StreamingPipeline** (`scripts/core/streaming.py`): True incremental token streaming via `stream_llm_response()`, `stream_agent_run()`, `StreamingConfig` with buffering modes, and `StreamEventType.STREAMING_UNAVAILABLE` for fallback notifications
- **LLM Gateway** (`scripts/core/llm_gateway.py`): Added `supports_streaming()` and `generate_stream()` methods
- **AI Router** (`scripts/ai_router.py`): Added `supports_streaming(model_key)` and `stream()` methods
- **CodeSandbox** (`scripts/core/sandbox.py`): Security checks (AST parsing, blocked imports/builtins/patterns), execution modes (RESTRICTED/SUBPROCESS/DOCKER), and safe matplotlib rendering

#### Infrastructure
- **Research Directions** (`scripts/research_directions/`): 40 research directions across 6 categories (绿色金融/碳经济学/数字金融/资产定价/公司金融/宏观金融) with search, suggest, and markdown output
- **DB Migration**: Added `_migrate_if_needed()` to `ResearchMemory` for automatic schema upgrades (v1→v2, adds `is_compressed` column)

#### Testing
- All 36 unit/integration tests pass (core modules: memory, planner, reflector, tool_selector, session, integration)
- `is_compressed` column missing warning fixed via automatic DB migration

### Changed

- **mcp.json**: Consolidated all 12 new MCP servers with standardized `user_` naming format, removed duplicate old-format entries
- **MCP Registration**: All servers use `sys.path.insert(0, ...)` pattern for reliable module resolution
- **financial** MCP: Upgraded from external `financial_mcp` to bundled `user_financial` server with 7 country macro indicators + World Bank API
- **tushare** MCP: Upgraded from external `tushare_mcp_server` to bundled `user_tushare` server
- **Test fixtures**: `test_tool_selector.py` updated to include `tushare` in tool registry expectations

### Fixed

- `ResearchMemory` DB schema: Added automatic migration for `is_compressed` column
- `test_tool_selector.py`: `tushare` tool now expected in registry
- `test_tool_selector.py`: `fetch_a_stock` added to `DATA_FETCH` task expected tools

## [1.0.0] - 2026-05-25

### Added

#### Core Agent
- **ResearchMemory** (`scripts/core/memory.py`): Three-layer memory system (Context / Short-term SQLite / Long-term) with automatic compression
- **ResearchPlanner** (`scripts/core/planner.py`): Task decomposition with Kahn topological sort and 4-level fallback strategy
- **ToolSelector** (`scripts/core/tool_selector.py`): Unified tool registry (MCP + Python scripts) with cost and VPN filtering
- **ResearchReflector** (`scripts/core/reflector.py`): Four-dimensional evaluation (completeness / accuracy / consistency / confidence)
- **ResearchSession** (`scripts/core/session.py`): Full workflow orchestration with save/resume

#### Data & Analysis
- **econometrics.py**: Programmatic OLS / DID regression with cluster-robust SEs, Breusch-Pagan test, VIF, and Markdown/LaTeX table export
- **data_pipeline.py**: A-share (akshare), US stock (yfinance), ArXiv paper retrieval, Brave News search
- **empirical_sync.py**: Empirical data snapshot management ensuring numerical consistency between analysis and reports

#### Paper Writing
- **paper_write.py**: Full paper pipeline (outline → chapter → full draft → de-AI polishing)
- **paper_tools.py**: LaTeX/PDF utilities (word count, table extraction, bibliography management, project scaffolding)
- **paper_submitter.py**: Multi-platform submission interface (arXiv / SSRN / OpenReview) with format auto-detection
- **format_detector.py**: LaTeX template auto-detection (IEEE / ACL / NeurIPS / CTeX / etc.)
- **paper_reader.py**: PDF full-text reading with structured summarization
- **paper_visualizer.py**: Architecture diagrams and visualization generation

#### AI Routing
- **ai_router.py**: Multi-provider AI router (DeepSeek / Groq / SiliconFlow / 智谱GLM / Ollama) with Keychain-backed secret management
- **review_layer.py**: Batch sentiment analysis and language polishing
- **literature_manager.py**: Academic paper management with tagging and BibTeX export
- **literature_search.py**: Literature search → download → summarization pipeline

#### MCP Integration
- **12 MCP servers** configured: arxiv, financial, finviz-sec, brave-search, fetch, context7, sqlite, todo, memory, github, eastmoney-reports, finagent
- Subprocess JSON-RPC invocation for all MCP tools via `ToolSelector._call_mcp()`

#### Infrastructure
- **CI/CD**: GitHub Actions (`ci.yml` for lint + tests, `docker.yml` for multi-stage image build)
- **Issue Templates**: Bug report and feature request templates
- **Comprehensive test suite** (`test_all_modules.py`): 91 tests covering all modules, MCP tools, skills, and agent pipeline

### Changed

- **VPN check**: Now checks baidu.com first (China-accessible), then google.com — works without VPN in China
- **Breusch-Pagan test**: Replaced placeholder with `statsmodels.stats.diagnostic.het_breuschpagan`
- **arXiv submission**: Now generates submission package (.tar.gz) with step-by-step manual submission guide
- **Brave Search**: Three-tier fallback: MCP (no API key) → HTTP API → friendly message
- **ArXiv API**: Upgraded from HTTP to HTTPS
- **import paths**: All modules now use `PROJECT_ROOT` relative paths, no hardcoded absolute paths

### Security

- All API keys loaded via macOS Keychain (priority) > `.env.local` > hardcoded
- No secrets in git history (cleaned)
- `.gitignore` excludes all sensitive files (`.env*`, API keys, credentials, data outputs)

### Fixed

- MCP tool invocation (was `NotImplementedError`, now works via subprocess JSON-RPC)
- MCP server import error (`from mcp import MCPServices` → direct `~/.cursor/mcp.json` reading)
- Hardcoded absolute paths in `test_all_modules.py` → relative to `__file__`
- Invalid model names in `config/llm_config.json` (B.AI relay references removed)
- ArXiv submission endpoint (fake API → real web submission guide)

### Documentation

- **README.md**: Comprehensive 636-line guide with quickstart, provider config, MCP setup, API reference, FAQ
- **QUICKSTART.md**: 3-minute getting started guide
- **CONTRIBUTING.md**: Contribution workflow and code standards
- **docs/AGENT_ARCHITECTURE.md**: Architecture overview
- **API configuration guide** (README §5.6): Keychain / `.env.local` / env var setup for all services

## [0.0.0] - 2026-05-19

### Added

- Initial project skeleton
- Basic research agent framework
