# Changelog

All notable changes to FinAI Research Workflow are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **TokenBucketRateLimiter per-server collisions**: replaced `hash()`-slot
  buckets with exact per-server dict keys so `rate_limit_per_server` no longer
  flakes under PYTHONHASHSEED / xdist (CI `test_per_server_rate_limit`).
- **Writing pre-gate compat**: stop inventing `baseline_p=1.0` for
  `negative_result_handler` on the writing track (always blocked). Soft-skip
  unless real baseline stats are present in writing/refinement payloads;
  keep fail-closed for manuscript/reference/data_source import failures.
- **Deprecated CLI modes**: `research_framework/pipeline.py` accepts
  `data|analysis|draft|lit-review|novelty-check|regression` again as aliases
  that print an actionable redirect and exit 2 (DeprecationWarning; no silent
  reimplementation). Makefile `validate-novelty` and lit-review docs updated.
- **Dual-track docs**: clarified writing (`agent_pipeline`) vs empirical demo
  (`research_framework/pipeline.py`) vs production empirics (`enhanced_pipeline` /
  `modern_did`) in `ARCHITECTURE.md` §0, `AGENTS.md`, `api_reference.md`,
  `README.md`, `CLAUDE.md`; removed dead CLI modes (`data`/`analysis`/`draft`/
  `lit-review`) from argparse and examples.
- **NoveltyGate real search**: `_check_novelty` now queries Semantic Scholar +
  OpenAlex via `literature_download`, filters by `lookback_years`, soft-boosts
  top journals, scores token Jaccard; LLM heuristic only when search is down
  (documented in report `search_status`).
- **Writing pre-gate data_source_checker**: fixed wrong import
  `scripts.research_framework.data_source_checker` → `scripts.data_source_checker`;
  added `check_data_sources()` adapter; gate reports are normalized to dicts;
  failures are fail-closed (`passed=False`) instead of silent greenlight.
- **HITL post-exec + resume semantics**: `AgentOrchestrator` previously called
  `HITLGate.hold()` *before* `agent.run()`, so gated stages often never executed;
  `resume_pipeline` also clamped/skipped incorrectly. Gates now hold **after**
  real agent output (with `stage_result` in gate content). Approve continues from
  the next step; reject re-runs the same stage with `prior_rejection_feedback`;
  resume while still PENDING is a no-op (fail-closed). Prior stage results are
  carried via `_resume_stage_results`.
- **PDF / post-run bookkeeping dead path**: end-to-end TeX/PDF generation and
  provenance/HITL bookkeeping lived under `_auto_generate_arch_diagrams` after
  `return arch_paths` (unreachable). Moved into `AgentPipeline.run()` (and
  mirrored on successful `resume_pipeline`), skipped while HITL-paused.
- **Agent-host entry robustness**: isolation / non-interactive hosts previously had no
  fail-closed FinAI entry when LLM was missing and Mock was forbidden, so agents
  freestyled outside the official pipeline. Added `scripts/agent_host_entry.py` and
  `scripts/core/agent_host_report.py` to write canonical `output/SKIPPED_CONFIG.md` +
  `output/FINAL.md`, wired the same artifacts into `agent_pipeline` exit code 4, and
  documented the protocol in `AGENTS.md` / `fin-full-pipeline` skill.

### Added
- `tests/test_orchestrator_hitl_resume.py`: regression coverage for post-exec HITL,
  approve→continue, reject→rerun+feedback, pending no-op, final-stage approve.

## [0.2.0a1] - 2026-08-07

### Fixed
- Corrected maintainer docs: `audit_guard` check count 17→25, MCP directory count 50→43, and primary entry documented as `agent_pipeline.py` (not `agent.py`).
- Fixed `Makefile` `pipeline-lit` target (removed nonexistent `--stage lit`; points to `literature_download.py`).

### Changed
- Cleared stale PyPI publish workflow waits for mismatched GitHub tags (`v1.0.0`/`v1.0.1`/`v0.2.0-alpha`) that would have uploaded wrong/conflicting package versions.
- Bumped package version to `0.2.0a1` for a clean Trusted Publishing release aligned with `pyproject.toml`.

### Fixed (audit_fix_2026_07_12, carried in tree)
- **T001**: Removed mechanism tests from `scripts/us_esg_regression.py` that
  constructed `cds_proxy`, `rating_proxy`, and `analyst_cov_proxy` as linear
  functions of treatment variables (endless tautology — would mechanically
  re-state the baseline DID coefficient). Table 5 now outputs an "Omitted"
  notice with reference to future work using genuine IBES / TRACE / S&P data.
- **T002**: `SyntheticControlEngine.sig` no longer returns heuristic stars
  based on raw RMSPE ratio thresholds. New `.sig` reads permutation p-value
  from `inference()`. Legacy heuristic preserved as `.rmspe_ratio_sig`.
- **T003**: Added `T_post < 5` warning to `process_data()` in
  `scripts/us_esg_regression.py` per Roth & Sant'Anna (2023, *Biometrika*).
  Table 3 tablenotes updated with explicit "illustrative, not definitive" caveat.
- **T004**: Fixed `pyproject.toml` `force-include` paths. Previous config
  referenced `finai_research_workflow/<dir>` (nonexistent source), causing
  hatchling to fail with `Forced include not found`. Now correctly points to
  actual source directories (`config`, `templates`, `knowledge`, `mcp_servers`).
- **T005**: Added `examples/_template/` skeleton (5 markdown files + README)
  for users to bootstrap new research projects. Updated `.gitignore` to allow
  template through.
- **T006**: Added synthetic test fixtures (`data/sample/`): 250-obs ESG panel,
  300-obs staggered DID panel, 5-entry BibTeX. README documents they are
  for offline testing only.
- **T007**: Added 2 Jupyter notebooks (`notebooks/00_quickstart.ipynb`,
  `notebooks/01_did_lab.ipynb`) with Angrist-Pischke MHE Ch.4 walk-through.
- **T008**: Added `scripts/generate_fixtures.py` for reproducible fixture
  generation. Defaults seed=42 for deterministic output.
- **T009**: Fixed `README_EN.md` Zenodo DOI badge (`PENDING` → `21262689`)
  and removed duplicate "Architecture overview" entry.
- **T010**: Aligned `README_EN.md` structure with `README.md` — added
  "Why FinAI Research Workflow?", expanded Quality Gates, added comparison
  table with alternatives.

### Added
- 16 regression tests across 3 new files:
  - `tests/test_us_esg_regression_t001_audit.py` (7 tests, T001)
  - `tests/test_synthetic_control_t002_audit.py` (8 tests, T002)
  - `tests/test_us_esg_t003_shortpanel.py` (6 tests + 1 skipped, T003)

## [0.2.0a0] - 2026-07-11

### Added

- `mcp_servers/_shared/_version.py`: single source of truth for APP_VERSION/APP_NAME,
  reads from top-level `pyproject.toml` (skips `mcp_servers/pyproject.toml` sub-package)
- 3 GitHub Discussion seed posts (#135 release announcement, #136 ideas/arXiv
  auto-submit, #137 Q&A install) for community seeding
- `audit_guard.py` Check 16: scans 260+ scripts/**/*.py files for hardcoded
  `vX.Y.Z` version drift from `[project].version`
- `tests/test_version_drift.py`: 14 regression tests covering CLI banner, MCP
  servers (sec_edgar/cryptocompare/newsapi), `gen_architecture_diagrams.py`
- GitHub Description updated with accurate numbers (43 MCP, 47 methods, 30 templates)
- 3 GitHub Discussion templates + 4 kinds of category defaults enabled

### Fixed

- `scripts/cli.py` banner: was hardcoded `v1.0.0`, now dynamic from pyproject
- `scripts/cli.py` `version_cmd`: fallback `"1.0.0"` → 5-tier resolution
  (pyproject → importlib.metadata → "0.0.0+unknown")
- `mcp_servers/user_sec_edgar/server.py`: `APP_VERSION = "1.0.0"` → dynamic
- `mcp_servers/user_cryptocompare/server.py`: same fix
- `mcp_servers/user_newsapi/server.py`: same fix
- `scripts/gen_architecture_diagrams.py`: header() default `version="v1.0.0"`
  → dynamic; inline "v1.0.0 标签" → dynamic
- `README.md`: "~20 种计量方法" / "~30 Econometric Methods" → "47" (truth)
- `tests/test_research_directions_advanced.py`: stale docstring "all 12" → 13
- `.gitignore`: added MANUAL_TASKS.md (local-only runbook)

### Changed

- This is a pre-release (`alpha`) tag — used during the Star Audit follow-up
  phase. Next stable will be `0.3.0` once DemO GIF + topics + awesome-list
  promotion complete.

## [1.0.1] - 2026-07-08

### Fixed

- Trigger Zenodo webhook for DOI minting. The v1.0.0 release did not auto-archive
  on Zenodo because the GitHub integration toggle was enabled after the release
  was created. This patch release forces a fresh GitHub → Zenodo webhook cycle
  and re-archives the same v1.0.0 source tree (no code changes).

## [1.0.0] - 2026-07-08

### Added

- 8,048 pytest tests across 398 test files (32.2% coverage baseline)
- 47 econometric methods (DID, IV, RDD, PSM, GMM, modern staggered DID variants,
  synthetic control, synthetic DID, panel quantile, interactive fixed effects,
  triple-diff, local projections, spatial regression, ...)
- 43 MCP data-source servers (OpenAlex, ArXiv, Semantic Scholar, NBER, SEC EDGAR,
  Tushare, yfinance, FRED, World Bank, IMF, OECD, Eastmoney reports, ...)
- 30 journal templates (经济研究 / 金融研究 / JF / JFE / RFS / JPE / Econometrica / ...)
- 17 AI skills for Claude Code, Cursor, GitHub Copilot
- GitHub Discussions enabled with 6 default categories
- Smoke tests for `scripts/start_research.py` (0% → 70.5% coverage on entry point)
- Dependabot configuration for Python ecosystem security updates

### Fixed

- `scripts/research_framework/volatility_models.py::VolatilitySpillover.diebold_yilmaz`:
  four silent bugs (statsmodels API drift, shape mismatch, pandas `applymap`
  deprecation, `.loc` slice) caused the main spillover path to silently fall back
  to a correlation-based approximation. All four fixed; main path now produces
  correct diebold-yilmaz spillover indices.
- `pyproject.toml`: pytest/pytest-cov upper bounds widened to match the locked
  versions that dependabot already resolved.

### Changed

- Repository renamed from `FinAI-Research-Workflow` to `finai-research`. Old URL
  permanently 301-redirects to new URL. PyPI package name `finai-research-workflow`
  is intentionally unchanged to preserve `pip install` ergonomics.

### Known Limitations

- All LLM-generated outputs (papers, reviews, design docs) **require human
  verification before submission**. Hallucinated citations and inappropriate
  statistical claims are possible.
- Windows is a secondary platform; macOS and Ubuntu are primary tested targets.