# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed
- **CI pipeline robustness** (PR #46): Added `if [ -f pytest-batch*.log ]` guards to all failure-step log operations across batch1/batch2/batch3/cross-platform. Fixes the recurring `LOG READ ERR: ENOENT: no such file or directory, open 'pytest-cs.log'` when pytest never runs (e.g. install step fails).
- **QualityGates / AutoReviewRules load diagnostics** (PR #47): Distinguish `ImportError` (module missing) from other exceptions when initializing `PaperQualityGates` and `AutoReviewRules` in `agent_pipeline.py`. Logged warnings/errors now make it visible whether quality gates are NO-OP due to missing module or runtime error.
- **Journal template count correction** (PR #46): Updated `README.md`/`CLAUDE.md`/`CITATION.cff` to reflect the actual count of 44 journal templates (was 45) and 44 MCP servers (was 43 in some places).
- **DOI badge and citation** (PR #47): Replaced dead `zenodo.org/PENDING` link with shields.io `PENDING` badge. Added explicit notes in `README.md`/`docs/CITATION_GUIDE.md` explaining how to obtain a real DOI via Zenodo.
- **Module count accuracy** (PR #66 follow-up): Corrected stale module counts — `research_framework/` has **47** modules (not 41 as recorded in v0.1.0 CHANGELOG; 41 was accurate at time of that PR but directory has grown since); `TEMPLATES` dict has **45** entries (not 44 as recorded in v0.1.0 CHANGELOG).

### Changed
- **Project metadata** (PR #48): `config/project_config.json` author changed from placeholder `Your Name <your.email@example.com>` to `csmar432 <https://github.com/csmar432>`.
- **`scripts/research_framework/regression_engine.py`** (PR #48): Expanded top docstring with Quick Start / Examples sections (Issue #22 first module — synthetic DID data).

### Added
- **docstring examples** (PR #48, Issue #22): Quick Start sections added to four core econometric modules — `modern_did.py`, `synthetic_control.py`, `rdd.py`, `iv_panel.py`, `regression_engine.py`. All examples use synthetic data (numpy.random) and run independently of external data sources.

### Closed
- **Issue #42** (PR #48): CI fail log issue (49 bot comments) closed after v13 PR #46 fix landed and CI went green across v12/v13/v14/current main.

---

## [v0.1.0] — 2026-06-17

### Added
- **`scripts/core/agent_pipeline_core.py`**: `AgentOrchestratorPipeline` — 统一编排流水线，解决 DAG 编排缺失 + 调用路径分散两大架构问题；Kahn 拓扑排序、StageConfig 依赖管理、QualityGates + AutoReviewRules 集成；31 个单元测试
- **`tests/test_agent_pipeline_core.py`**: 31 new tests for `AgentOrchestratorPipeline` — topological sort (linear/parallel/cycle), dependency checking, quality gates integration, auto review integration, HITL flow, single-entry API, accessors
- **`scripts/core/quality_gates.py` → `agent_pipeline.py` integration**: `_run_quality_check()` 在每个 stage 结果提取后自动执行 `PaperQualityGates`，结果存入 `AgentPipelineResult.quality_reports`
- **`scripts/core/auto_review_rules.py` → `agent_pipeline.py` integration**: `_run_auto_review()` 在每个 stage 结果提取后自动执行 `AutoReviewRules` 评分，结果存入 `AgentPipelineResult.auto_review_reports`；偏见探测从理论到实际可用
- **`docs/DOCKER_INSTALL.md`**: Docker Desktop 安装指南 — macOS (Homebrew/官方)、Linux (Ubuntu/Debian)、Windows (WSL2)；含 OrbStack 轻量替代方案、API Key 配置、故障排除（端口冲突/镜像构建失败/Apple Silicon兼容性）
- **`mcp_servers/start_all.sh`**: MCP 一键启动脚本 — `--group` 按组启动（finance/macro/academic/china）、`--health` 健康检查、`--logs` 日志查看、`--status` 状态监控；`--pull`/`--build` 镜像管理；Docker 自动检测
- **`agent_pipeline.py`**: 修复 `CitationVerifier` 初始化错误（`cache_dir` → `timeout`+`cache_size`）；`_extract_stage_text()` 文本提取工具方法；`get_quality_report()` 公开查询接口；`AgentPipelineResult` 新增 `quality_reports`/`auto_review_reports` 字段
- **`tests/test_reviewer_calibrator.py`**: 31 new tests for `ReviewerCalibrator`, `CalibratorFeedbackLoop`, `BiasHistoryDB`, `PersistentCalibratorFeedbackLoop`
- **`scripts/register_mcp_servers.py`**: Deprecated scripts registry documenting 11 duplicate/abandoned scripts with replacement versions

### Changed
- **`mcp_servers/*/Dockerfile` (43 servers)**: All Dockerfiles upgraded to best-practice standard — non-root `mcpuser` user, `HEALTHCHECK`, version-pinned dependencies (`mcp>=1.1.0`, `requests>=2.31.0`, etc.), OCI Labels, `PYTHONUNBUFFERED=1`, `EXPOSE 8000`; previously only 7 servers had this standard
- **`scripts/research_framework/leamer_sensitivity.py`**: `LevinsohnPetrinEstimator.fit()` signature unified with `finance_sensitivity.py` — renamed `intermediate` → `intermediate_input`, added `min_obs` parameter, added comprehensive docstring
- **`CLAUDE.md`**: Corrected multiple stale numbers — research_framework count (27→47), core modules (80+→92), research_directions (11→12), journal templates (44→45), skill count confirmed at 17
- **`README.md`**: Updated key numbers — research_framework modules (27→47), research directions (11→12), journal templates (41→45)
- **`pyproject.toml`**: Removed unused `torch` and `accelerate` from `deep-learning` optional group (no imports found in codebase); marked as commented placeholders for future use

### Deprecated
- **11 duplicate scripts**: `econometrics.py`, `econometrics_advanced.py`, `export_hubei_data.py`, `generate_hubei_excel.py`, `fetch_msci_cyh.py`, `fetch_msci_esg_v2.py`, `entity_list_data_fetcher.py`, `financial_report_structure.py`, `report_generator.py`, `professional_review_agent.py`, `review_layer.py` — all marked with deprecation header, see `scripts/register_mcp_servers.py`

### Fixed
- **`tests/test_reviewer_calibrator.py`**: Fixed `CalibrationResult` → `CalibrationReport` field name mismatch (`calibrated_overall` → `calibrated_overall_score`)
- **`agent_pipeline.py`**: Fixed `CitationVerifier` initialization — `cache_dir` parameter changed to `timeout=10.0` + `cache_size=500` to match actual `CitationVerifier.__init__` signature; verified with integration test
- **`scripts/research_framework/leamer_sensitivity.py`**: Fixed `LevinsohnPetrinEstimator.fit()` internal references from `intermediate` to `intermediate_input` after parameter rename

### Security
- **34 MCP Dockerfiles**: Upgraded from root to non-root `mcpuser` execution, eliminating root privilege requirement in containers

---

