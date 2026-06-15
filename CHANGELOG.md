# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **`scripts/core/agent_pipeline_core.py`**: `AgentOrchestratorPipeline` — 统一编排流水线，解决 DAG 编排缺失 + 调用路径分散两大架构问题；Kahn 拓扑排序、StageConfig 依赖管理、QualityGates + AutoReviewRules 集成；31 个单元测试
- **`tests/test_agent_pipeline_core.py`**: 31 new tests for `AgentOrchestratorPipeline` — topological sort (linear/parallel/cycle), dependency checking, quality gates integration, auto review integration, HITL flow, single-entry API, accessors
- **`scripts/core/quality_gates.py` → `agent_pipeline.py` integration**: `_run_quality_check()` 在每个 stage 结果提取后自动执行 `PaperQualityGates`，结果存入 `AgentPipelineResult.quality_reports`
- **`scripts/core/auto_review_rules.py` → `agent_pipeline.py` integration**: `_run_auto_review()` 在每个 stage 结果提取后自动执行 `AutoReviewRules` 评分，结果存入 `AgentPipelineResult.auto_review_reports`；偏见探测从理论到实际可用
- **`docs/DOCKER_INSTALL.md`**: Docker Desktop 安装指南 — macOS (Homebrew/官方)、Linux (Ubuntu/Debian)、Windows (WSL2)；含 OrbStack 轻量替代方案、API Key 配置、故障排除（端口冲突/镜像构建失败/Apple Silicon兼容性）
- **`mcp_servers/start_all.sh`**: MCP 一键启动脚本 — `--group` 按组启动（finance/macro/academic/china）、`--health` 健康检查、`--logs` 日志查看、`--status` 状态监控；`--pull`/`--build` 镜像管理；Docker 自动检测
- **`agent_pipeline.py`**: 修复 `CitationVerifier` 初始化错误（`cache_dir` → `timeout`+`cache_size`）；`_extract_stage_text()` 文本提取工具方法；`get_quality_report()` 公开查询接口；`AgentPipelineResult` 新增 `quality_reports`/`auto_review_reports` 字段
- **`tests/test_reviewer_calibrator.py`**: 31 new tests for `ReviewerCalibrator`, `CalibratorFeedbackLoop`, `BiasHistoryDB`, `PersistentCalibratorFeedbackLoop`
- **`scripts/DEPRECATED.md`**: Deprecated scripts registry documenting 11 duplicate/abandoned scripts with replacement versions

### Changed
- **`mcp_servers/*/Dockerfile` (41 servers)**: All Dockerfiles upgraded to best-practice standard — non-root `mcpuser` user, `HEALTHCHECK`, version-pinned dependencies (`mcp>=1.1.0`, `requests>=2.31.0`, etc.), OCI Labels, `PYTHONUNBUFFERED=1`, `EXPOSE 8000`; previously only 7 servers had this standard
- **`scripts/research_framework/leamer_sensitivity.py`**: `LevinsohnPetrinEstimator.fit()` signature unified with `finance_sensitivity.py` — renamed `intermediate` → `intermediate_input`, added `min_obs` parameter, added comprehensive docstring
- **`CLAUDE.md`**: Corrected multiple stale numbers — research_framework count (27→41), core modules (80+→92), research_directions (11→12), journal templates (44→70), skill count confirmed at 17
- **`README.md`**: Updated key numbers — research_framework modules (27→41), research directions (11→12), journal templates (41→70)
- **`pyproject.toml`**: Removed unused `torch` and `accelerate` from `deep-learning` optional group (no imports found in codebase); marked as commented placeholders for future use

### Deprecated
- **11 duplicate scripts**: `econometrics.py`, `econometrics_advanced.py`, `export_hubei_data.py`, `generate_hubei_excel.py`, `fetch_msci_cyh.py`, `fetch_msci_esg_v2.py`, `entity_list_data_fetcher.py`, `financial_report_structure.py`, `report_generator.py`, `professional_review_agent.py`, `review_layer.py` — all marked with deprecation header, see `scripts/DEPRECATED.md`

### Fixed
- **`tests/test_reviewer_calibrator.py`**: Fixed `CalibrationResult` → `CalibrationReport` field name mismatch (`calibrated_overall` → `calibrated_overall_score`)
- **`agent_pipeline.py`**: Fixed `CitationVerifier` initialization — `cache_dir` parameter changed to `timeout=10.0` + `cache_size=500` to match actual `CitationVerifier.__init__` signature; verified with integration test
- **`scripts/research_framework/leamer_sensitivity.py`**: Fixed `LevinsohnPetrinEstimator.fit()` internal references from `intermediate` to `intermediate_input` after parameter rename

### Security
- **34 MCP Dockerfiles**: Upgraded from root to non-root `mcpuser` execution, eliminating root privilege requirement in containers

---

## [v1.6.0] — 2026-06-09

### Added
- **`scripts/journal_templates_multilang.py`**: 9 new journal templates — Japanese (JER, JJID) + German (ZWiSt, AStA, JNS, Schmollers Jahrbuch, AEQ) — with full LaTeX code and AEA/bibstyles
- **`scripts/core/provenance_rag.py`**: NumberExtractor (8 types: coefficient, t-stat, p-value, R², F-stat, CI, sample size, effect) + ProvenanceRAG with ChromaDB vector + SQLite fallback modes; `is_random_fallback` property + `check_fallback_warning()` for user-visible degradation alerts
- **`scripts/mcp_schema_check.py`**: MCP server schema vs handler validation tool; detects named-handler and dispatcher patterns; `python scripts/mcp_schema_check.py`
- **`scripts/ci_verify.py`**: CI auxiliary script; `check_docker_compose()` + `check_mcp_schemas()` for GitHub Actions lint job
- **`scripts/core/reviewer_calibrator.py` — CalibratorFeedbackLoop / PersistentCalibratorFeedbackLoop / BiasHistoryDB**: Automatic bias-to-prompt feedback loop (744→1429 lines); 6 bias types → LLM prompt adjustment mapping; score correction engine (downscale/upscale/spread_out/neutralize); bias correction verification; BiasHistoryDB SQLite persistence (bias records, trends, journal profiles, CSV+JSON export); PersistentCalibratorFeedbackLoop with `auto_calibration_advice()`; CLI demos (--bias-demo, --loop-demo)
- **MCP Dockerfile 增强（7个）**: 为 user_arxiv/user_brave_search/user_chinese_customs/user_chinese_literature/user_cnrd/user_sipo/user_third_party_esg 新增 Dockerfile（含非root用户/healthcheck/版本锁定/Labels）；现 41/41 MCP 服务器全部有 Dockerfile
- **MCP Schema `inputSchema.description` 补全（216个）**: 41个 MCP 服务器 216个工具的 inputSchema.description 全部补全；从 server.py 源码提取真实描述，清理转义字符；194个工具使用真实描述

### Fixed
- **`scripts/validate_econometrics.py`**: Stata `--version` flag (cross-platform); DID/IV matrix access changed from numeric indices to named access `_b[coef]` / `_se[coef]`; removed dead `_STATA_DO` templates and `_write_do_file` function
- **`scripts/research_rag.py`**: Fixed silent random-vector fallback with user-level warning; added `Embedder._fallback_mode`, `Embedder.is_random_fallback`, `ResearchRAG.is_random_fallback`, `ResearchRAG.check_fallback_warning()`; warnings include pip install instructions
- **`docs/mkdocs.yml`**: Added tutorial overview entry to navigation
- **PROJECT_EVALUATION.md**: 6 categories fixed — MCP count (28→41), test count (158→1498), synthetic control/RDD (⚠️→✅), P3 items 2/3/5/6 (⚠️→✅)

### Changed
- **`.github/workflows/ci.yml`**: Refactored to 5 parallel jobs (lint, test-batch-1/2/3, docker); tests split into 3 batches to avoid OOM; `concurrency` for auto-cancel; MCP schema check + docker-compose validation added to lint; docker job gated to PR-only runs
- **`PROJECT_EVALUATION.md`**: Document updated to v1.6.0 (2026-06-09); Review mechanism score 8.5→9.2/10 (CalibratorFeedbackLoop); MCP architecture 8.5→9.0/10 (Dockerfile 41/41 + inputSchema.description 216); overall score 91.3→94.7/100


### Added
- **11 research directions**: `green_finance`, `carbon_economics`, `digital_finance`, `esg_finance`, `corporate_finance`, `behavioral_finance`, `fintech_innovation`, `macro_finance`, `real_estate_finance`, `international_finance`, `political_economy_finance` — each with policy events, MCP data fetching, regression methods, LaTeX table plans, and figure plans
- **5 new research directions**: `ClimateFinanceDirection`, `AIFinanceDirection`, `HouseholdFinanceDirection`, `PublicFinanceDirection`, `CryptoFinanceDirection` (in `research_directions/__init__.py`, auto-registered, total 16 directions)
- **`LiteratureParser` class**: Parses papers from ArXiv ID (Context7 MCP), DOI (CrossRef API), PDF file (PyMuPDF), extracting methodology, sample size, key findings
- **`ResearchGapScorer` class**: Algorithmically computes research gap scores and identifies bridging opportunities across research directions
- **`scripts/core/specialized_agents.py`**: 6 specialized review agents — `ProofreaderAgent`, `RReviewerAgent`, `TikZCriticAgent`, `AdversarialQAAgent`, `LiteratureGapAgent`, `DataAuditAgent` — with full LLM-powered review and `run_all_agents()` parallel execution
- **3 new ADR documents** (`docs/adr/`): ADR-001 (7-layer fallback strategy), ADR-002 (ProvenanceChain design), ADR-003 (SEPL self-evolution protocol)
- **`PipelineTelemetry` class** in `checkpoint.py`: Tracks stage durations, token counts, API call counts, error counts, MCP call counts, auto-saves to `data/pipeline_telemetry.jsonl`
- **`ProvenanceChain.export_figure_provenance_report()`**: Per-figure Markdown provenance report with full data lineage
- **Test suites**: `tests/test_ai_parliament.py` (25 tests), `tests/test_self_evolution.py` (33 tests), `tests/test_specialized_agents.py` (22 tests) — 80 new tests total
- **`docs/index.md`**: MkDocs documentation homepage
- **`scripts/deprecated/research_workflow.py`**: Legacy workflow (deprecated in favor of `agent_pipeline.py`)
- **28 MCP tool JSON files enhanced**: All tools now use standard `inputSchema` format with complete descriptions and parameter schemas (SIPO 4 tools, CNRDS 4 tools, chinese_literature 4 tools, customs 4 tools, third_party_esg 4 tools, openalex 2 tools, arxiv 2 tools, context7 2 tools, brave_search 1 tool, yfinance 5 tools)

### Fixed
- **SyntaxError in `carbon_economics.py` (line 999)**: Invalid escape sequence `\q` in f-string → fixed to `\\quad`
- **SyntaxError in `macro_finance.py` (lines 657, 820)**: Invalid escape sequences `\m` and `\%` → fixed to `\\multicol` and `\\%`
- **SyntaxError in `corporate_finance.py` (lines 1335, 1342)**: Invalid escape sequences `\c` and `\%` in `_table_ma_performance` → fixed LaTeX table string escaping
- **`digital_finance.py` registration**: Fixed `DirectionFactory.register()` call signature from two-argument to single-instance form
- **`.gitignore` stale negate rules**: Removed `!data/msci_esg_ratings.json` and `!data/test_national.json` (files deleted); restored `!data/national_province_data_2026.json`
- **`docs/mkdocs.yml`**: Restored from git (accidentally deleted in working directory)
- **`mcp_servers/__pycache__`**: Removed stray `__pycache__` directory from MCP server root
- **`knowledge/skills/README.md`**: Fixed "17个技能" → "18个技能", fixed "符号链接" → "目录副本", fixed `>=` → `≥` and `->` → `→`
- **`knowledge/README.md`**: Fixed "17个技能" → "18个技能"
- **`scripts/SCRIPTS_INDEX.md`**: Fixed Obsolete section empty table, removed duplicate MSCI entries, corrected script count (72 total)
- **`CHANGELOG.md`**: Fixed outdated numbers (17 skills → 18 skills, 35 MCP → 43 MCP, 27 modules → 41 modules)

### Changed
- **Documentation numbers aligned**: All markdown files now consistently report 43 MCP servers, 41 `research_framework` modules, and 12 research directions, 17 skills, 49 econometric methods
- **`research_directions/`**: Expanded from 6 to 11 direction files with full academic depth (policy events, MCP calls, robust regression methods, LaTeX table/figure plans)
- **Architecture diagram**: SVG updated with correct numbers (43 MCP / 41 framework / 17 skills / 49 methods)

---

## [1.5.1] - 2026-06-04

### Added
- **18 skills** (in `knowledge/skills/`, `.cursor/skills/`, `.claude/skills/`): `fin-full-pipeline`, `fin-idea-discovery`, `fin-lit-review`, `fin-generate-idea`, `fin-novelty-check`, `fin-experiment-design`, `fin-paper-writing`, `fin-paper-draft`, `fin-paper-plan`, `fin-paper-figure`, `fin-paper-convert`, `fin-review-loop`, `fin-submit-check`, `fin-data-acquisition`, `fin-brief-generator`, `fin-ref-paper`, `fin-viz-launch`
- **41 MCP data servers** covering A-share stocks, macroeconomics, US markets, academic literature, reports/news, forex/commodities
- **27 `research_framework` modules**: `modern_did.py`, `synthetic_control.py`, `synthetic_did.py`, `local_projections_did.py`, `triple_diff_did.py`, `rdd.py`, `panel_quantile_regression.py`, `interactive_fixed_effects.py`, `iv_panel.py`, `panel_var.py`, `spatial_regression.py`, `vuong_kob.py`, `leamer_sensitivity.py`, `regression_engine.py`, `data_fetcher.py`, `report_generator.py`, `robustness_runner.py`, `fin_charts.py`, `pipeline.py`, `diagnostic_reporter.py`, `llm_reviewer.py`, and more
- **`scripts/core/` modules** (76 modules): agent orchestration, MCP tool management, event monitoring, checkpoint, provenance tracking
- **`docs/` tutorials**: 01-quickstart, 02-financial-report, 03-research-directions, 04-mcp-marketplace, 05-event-driven-research
- **MkDocs documentation site** with Material theme
- **Project evaluation report** (`PROJECT_EVALUATION.md`, score 90.5/100)
- **MkDocs `docs/mkdocs.yml`** for documentation site generation

### Changed
- **`agent_pipeline.py`**: Main entry point for the research workflow
- **`health_check.py`**: System health diagnostic with API key and LLM availability checks
- **`data/` directory structure**: Organized with subdirectories for `macro/`, `customs/`, `esg/`, `policy/`, `user_uploaded/`, `processed/`
- **`.cursor/rules/`**: Role-specific rules for Cursor IDE (MCP tools, analyst, paper writer, researcher)

---

## [1.5.0] - 2026-05-23

### Added
- **Research agent framework** with 4-module architecture: `ResearchMemory`, `ResearchPlanner`, `ResearchReflector`, `ToolSelector`
- **Agent pipeline orchestration** via `scripts/agent_pipeline.py`
- **Autonomy loop** with checkpoint and review cycles
- **MCP server ecosystem** with 35+ data servers

### Changed
- Project renamed from `finai-research-workflow` to `论文-研报工作流`

---

## [1.0.0] - Initial Release

### Added
- Basic agent workflow with 5-step research pipeline
- `research_workflow.py` (legacy, now deprecated)
- Core data fetching modules
