# 论文-研报工作流 · 改进与修复任务清单 (IMPROVEMENT ROADMAP)

> 综合项目设计理念（"研究主题一句话 → 论文草稿"，人类在环，科研诚信第一），
> 覆盖 **P0 学术诚信 → P1 可复现 → P2 文档 → P3 架构 → P4 测试 → P5 增长** 6 个优先级。
>
> 最后更新：2026-07-12 · 创建于 2026-07-12 (commit `5ed1538`) · **状态更新于 commit `1da3XXX` (本轮)** (P0-A/B + P1-2 + P2-1 + P0-C + P2-3 + P1-5/P2-4 + P1-3/P1-4 全部完成)
>
> **Legend**:
> - `[ ]` Pending · `[~]` In Progress · `[x]` Completed · `[!]` Blocked / Need user confirm
> - `🔴` 高严重度 · `🟡` 中 · `🟢` 低

---

## ✅ 完成总结 (commit `de1e02c` — 第二轮审计: P0-C + P2-3 + P1-5/P2-4)

| 优先级 | 已完成 | 总数 | 状态 |
|---|---|---|---|
| P0 (代码 bug) | P0-A (dispatch), P0-B (Bacon), **P0-C (vuong_kob OB algebra)** | 3/3 | ✅ 100% |
| P1 (架构) | P1-2 (orphan engines), P1-1 (cancelled), **P1-5 (mediation deprecate)**, **P1-3 + P1-4 (TripleDiffDID + PSMDID)** | 4/4 | ✅ 100% |
| P2 (代码质量) | P2-1 (significance consistency), **P2-3 (data catalog init)**, **P2-4 (moderation deprecate)** | 3/3 | ✅ 100% |
| **合计** | **10 项完备修复** + **1 项审计取消** | — | — |

### 测试统计
- **新增 64 个回归测试** (P0-C=22, P2-3=8, P1-5/P2-4=8, P1-3+P1-4=26)
- **完整测试套件**: 8100+ 通过, 0 回归
- **audit_guard.py: 17/17 checks 全通过**

### P0-C: vuong_kob 直接测试 + OB 分解代数修复 (🔴 P0)
**问题**: `vuong_kob` 主类 (VuongTest, KOBDecomposition, OaxacaBlinderDecomposition) 无直接 unit test, 仅依赖 `vuong_test.py` re-export 间接覆盖.
**触发**: 新增的 `test_oaxaca_additive_decomposition_with_intercept` 揭露 OB 分解 **代数错误**: 代码声称 E + C + I = Gap (Cotton 1988 3-fold), 但实际代数推导得 `b1'(2X̄1-X̄2) - b2'X̄1`, 不等于 Gap.
**修复**: 改用 Jann (2008) Stata Journal "Oaxaca threefold" — pooled reference β*:
```
β* = (n1·β1 + n2·β2)/(n1+n2)
E = β*'(X̄1-X̄2)
C = X̄1'(β1-β*) + X̄2'(β*-β2)
I = 0  (absorbed into C)
代数证明: E + C = β1'X̄1 - β2'X̄2 = Gap  ✓  (exactly additive)
```
**测试**: `tests/test_vuong_kob_direct_p0_audit.py` (22 测试)

### P2-3: 数据/工具类模块接入 __init__.py (🟢 P2)
**问题**: 3 个模块 `a_share_firm_controls`, `china_carbon_events`, `china_policy_events` 此前零公共出口, 用户需路径 import.
**修复**: `__init__.py` 加 try/except re-export + `__all__` 注册 11 个新符号.
**注意**: `china_carbon_events` 的 `baseline_twfe`/`robustness_cs`/`heterogeneity` 实际是 docstring 里的示例代码, 已剔除.
**测试**: `tests/test_data_catalog_p2_audit.py` (8 测试)

### P1-5 + P2-4: mediation.py + moderation.py 标 deprecation (🟡 P1 + 🟢 P2)
**决策**: 仅标 deprecation, **不合并** (合并风险高, 见审计报告 `P2-2-EVALUATION-2026-07-12.md` §1).
**修复**:
- 模块顶部 + 类 docstring 加 `.. deprecated:: 1.8.6 ..`
- import 触发 `DeprecationWarning`, 含推荐替代模块名
- 旧 `MediationResult` 字段 (`indirect_effect`/`direct_effect`/`total_effect`/`indirect_ci`) 与新 `MediationTest.MediationResult` 字段 (`alpha`/`beta`/`gamma`/`delta`/`ci_lower`/`ci_upper`) 不兼容, 已告知
- 模块保留向后兼容, v1.10.0 删除

**推荐替代**:
- mediation → `mediation_test.MediationTest` (canonical class-based API)
- moderation → `PanelThresholdRegression` (Hansen 2000) 或直接 OLS 交互项

**测试**: `tests/test_deprecation_warnings_p1_p2_audit.py` (8 测试)

### P2-2 决策: 不推进
**评估**: `pipeline.py` 仅消费预先渲染的 figures, 不调用 `FinancialChartFactory`. `agent_pipeline._auto_generate_did_charts` 已存在 (L1778) 覆盖 6 类图, **但 `pipeline.py` 从未调用它**. 这是架构分层: `agent_pipeline` (编排层, 出图) → `pipeline.py` (渲染层, 消费图). 修复 P2-2 会混淆职责.
**结论**: 保持 SoC 现状. 详见 `docs/audit/P2-2-EVALUATION-2026-07-12.md`.

---

## ✅ 完成总结 (commit `c159edc` — 实证模块深度审计)

| 优先级 | 已完成 | 总数 | 状态 |
|---|---|---|---|
| P0 (代码 bug) | P0-A (dispatch), P0-B (Bacon) | 2/2 | ✅ 100% |
| P1 (架构) | P1-2 (orphan engines), P1-1 (cancelled) | 1/2 | 🟡 50% |
| P2 (代码质量) | P2-1 (significance consistency) | 1/2 | 🟡 50% |
| **合计** | **4 项完备修复** + **1 项审计取消** | — | — |

### 测试统计
- **新增 34 个回归测试** (P0-A=5, P0-B=5, P1-2=17, P2-1=7), 全部通过
- **完整测试套件**: 8044+ 通过, 0 回归
- **audit_guard.py: 17/17 checks 全通过**

### P0-A: `_main_dispatch` 默认 full 不可达 (🔴 P0)
**Bug**: 之前只调度 `design`/`review` 模式; `--mode full` (默认) 静默 fall-through, 函数返回 None.
**修复**: 重写为显式 `if args.mode == "full": ... elif ...` 链, 未知模式返回 1.
**测试**: `tests/test_pipeline_dispatch_p0_audit.py` (5 测试)

### P0-B: Bacon decomposition T 列向量化 (🔴 P0)
**Bug**: `T = (data[time_var] >= data[unit_var].map(lambda u: t_i if u == uid_i else t_j))` 在整数 Series 上调用 lambda,语义错误.
**修复**: 构建 per-unit 字典 `{uid_i: t_i, uid_j: t_j}`, 然后 `.map()`.
**测试**: `tests/test_modern_did_bacon_p0_audit.py` (5 测试)

### P1-2: 11 个 orphan econometric engine 接入 RobustnessRunner (🟡 P1)
**问题**: 47 个 method 模块中只有 ~10% 可达.
**修复**: `RobustnessRunner.run_method_specific(method, df)` 调度 11 个引擎:
`rdd, lp_did, ife, synthetic_did, panel_quantile, panel_threshold, spatial, panel_var, garch, tvp_var, cox_ph`
**优雅降级**: 缺失依赖 → `status='skipped'` (不崩溃).
**幂等性**: `(method, id(df), kw)` 缓存.
**测试**: `tests/test_orphan_engines_p1_audit.py` (17 测试)
**CLI**: `python scripts/research_framework/pipeline.py --list-methods`

### P2-1: significance_mark 一致性检查 (🟢 P2)
**审计**: `scripts.core.formatters.significance_mark` 与 `scripts.research_framework.base._stars` 在 *** / ** / * / '' 上保持一致; p<0.10 边缘差异 (`.` vs `$\dagger$`) 是有意为之, 为向后兼容.
**测试**: `tests/test_significance_centralization_p2_audit.py` (7 测试)

### P1-1: 取消 — 删除重复模块 (🟢 P2 → 取消)
**初判**: 审计建议删除 `vuong_test.py`, `leamer_sensitivity.py`, `mediation.py` 作为 `vuong_kob.py`, `finance_sensitivity.py`, `mediation_test.py` 的重复.
**复核**: 每个所谓"重复"实际包含独有类 (`ClarkeTest`, `ClarkeTestEN`, `LeamerSensitivity`, `BoundingResult`, `DynamicPanelDiagnostics`, `vuong_different_controls`, 等), canonical 版本中不存在.
**决策**: 保留全部 6 个模块. 删除已被 `git restore` 撤销. 50+ 测试未受影响.

---

## ✅ 完成总结 (commit `3fa084e` — 前一轮 P0-P2 审计)
- 删除 `us_esg_regression.py` 中所有 mechanism proxy 线性构造
- `synthetic_control.py` `.sig` 改读 permutation p-value (legacy 改名为 `.rmspe_ratio_sig`)
- `us_esg_regression.py` 加 short-panel DID warning (T_post < 5)
- `pyproject.toml` force-include 修复, wheel 构建成功
- 新增 `examples/_template/` (6 文件), `data/sample/` fixtures, 2 个 Jupyter notebooks
- 新增 `scripts/generate_fixtures.py` (seed=42, 可复现)
- `README_EN.md` DOI 修复 + 删除重复行 + 新增 3 节与中文 README 对齐
- `audit_guard.py` 新增 check 17 (research integrity anti-patterns)

---

## 🚨 P0 · 学术诚信 & 方法论正确性（全部完成 ✅）

### [x] ✅ T001 🔴 Mechanism variables 是真实变量的线性函数（虚假代理）
**文件**: `scripts/us_esg_regression.py:475-480`

```python
# ── 当前 (BUG) ─────────────────────────────────────────────
df_mech["analyst_cov_proxy"] = df_mech["ln_assets"] * 2.8
df_mech["cds_proxy"] = 120 - 42 * df_mech["esg_high"] - 8 * df_mech["post"]
df_mech["rating_proxy"] = 4 + 1.5 * df_mech["esg_high"] + 0.8 * df_mech["post"]
```
**问题**: 用因变量的线性函数当"机制变量"是 endless tautology, 无识别价值, **违反科研诚信**。

**修复方案**:
- (A) 接真实数据: `user-yfinance` 取 IBES analyst coverage、TRACE CDS spreads、S&P credit rating
- (B) 删除整个 Table 5 mechanism tests, 保留 narrative discussion
- (C) 严格标注 "heuristic proxy, NOT for publication" 并在 `AUDIT.md` 记录

**验收**: 论文 footnote 注明数据来源；跑通后 `audit_guard.py` 自动检测 "proxy = f(treatment)" 反模式。

---

### [x] ✅ T002 🔴 合成控制显著性用 RMSPE 阈值（非统计推断）
**文件**: `scripts/research_framework/synthetic_control.py:163-168`

```python
# ── 当前 (BUG) ─────────────────────────────────────────────
@property
def sig(self) -> str:
    ratio = self.rmspe_ratio
    if ratio > 20: return "***"   # ← 启发式阈值
    elif ratio > 10: return "**"
```
**问题**: SC 显著性必须用 Abadie et al. (2010) placebo permutation p-value。

**修复方案**:
```python
@property
def sig(self) -> str:
    p = self.additional.get("permutation_pvalue", float("nan"))
    if np.isnan(p): return ""
    if p < 0.01: return "***"
    elif p < 0.05: return "**"
    elif p < 0.10: return "*"
    return ""
```
+ 强制要求 `inference(n_placebos=999)` 先跑再读 `.sig`, 否则 warn。

**验收**: 测试用例 `test_sc_sig_uses_permutation_p`; 任何 `result.sig` 不访问 placebo 都会 raise。

---

### [x] ✅ T003 (2026-07-12) 短面板 DID bias 未标注
**文件**: `scripts/us_esg_regression.py:58, 273`

**现状**: 14 firms × 7 years = 98 obs, 2022-2024 post, 2018-2021 pre。
**问题**: Roth & Sant'Anna (2023) 指出 small post-periods (3) 会严重 finite-sample bias。

**修复方案**:
- 论文 LaTeX 加 footnote: "N=42 firm-years (3 post-periods) provides limited variation; results illustrative."
- `REFINED_DESIGN.md` 加 "Minimum Sample Check" section, 要求 T_post ≥ 5 否则 warn
- `audit_guard.py` 新增 check: "DID with T_post < 5 must declare robustness"

---

### [x] ✅ T004 (2026-07-12) pyproject.toml force-include 路径不存在
**文件**: `pyproject.toml` ([tool.hatch.build.targets.wheel.force-include])

```toml
'force-include': {
  'config': 'finai_research_workflow/config',  # ← 路径不存在
  ...
}
```
**问题**: hatchling 会 raise `Forced include not found`。

**修复**: 删除 force-include 节, 让 hatch 默认处理。

---

## 🔁 P1 · 可复现性 & 一键运行

### [x] ✅ T005 (2026-07-12) `examples/` 被 .gitignore 排除
**文件**: `.gitignore:202-203`

**修复**: 入仓 `examples/_template/`, 保留敏感的 (含 DEEPSEEK 调用) 在 `.gitignore`。

---

### [x] ✅ T006 (2026-07-12) `data/` 没有 sample fixtures
**修复**: 创建 `data/sample/`, 入仓:
- `esg_panel_demo.csv` (50 firms × 5 years, 匿名化合成数据)
- `literature_demo.bib` (20 篇预下载的 OpenAlex 摘要)
- `tickers_demo.json` (10 个 ticker 的 OHLCV sample)

---

### [x] ✅ T007 (2026-07-12) 零 Jupyter Notebook
**修复**:
- `examples/01-carbon-did/01-carbon-did.ipynb` 5-cell walkthrough
- `examples/02-green-credit-psm-did/02-green-credit-psm-did.ipynb`
- `notebooks/00_quickstart.ipynb`
- `notebooks/01_did_lab.ipynb`
- pyproject 加 `optional-dependencies.jupyter`

---

### [x] ✅ T008 (2026-07-12) generate_fixtures.py 脚本
**新增**: `scripts/research_framework/generate_fixtures.py`

```python
"""Generate small synthetic fixtures for offline testing."""
import numpy as np, pandas as pd
def make_esg_panel(n_firms=20, n_years=5, seed=42):
    ...
```

---

## 📚 P2 · 文档 & 用户体验

### [x] ✅ T009 (2026-07-12) README_EN.md 占位符未替换 + 重复行
**文件**: `README_EN.md:18, 50-52`

**修复**:
```diff
- [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.PENDING.svg)]
+ [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21262689.svg)]
```
- 删重复 "Architecture overview" 行。

---

### [x] ✅ T010 (2026-07-12) README_EN.md 体例对齐 README_CN
**现状**: README_EN (282 行) 远短于 README_CN (691 行)。
**修复**: 增加 Why FinAI、MCP Server Profile、Empirical methods 表、Journal templates 表、Contributing。

---

### [x] ✅ T011 (2026-07-12) CHANGELOG 记录 demo v4 修复
**修复**: 加 `[Unreleased]` 条目, 记录之前 demo 用 np.random fallback 已被 v4 替换。

---

### [x] ✅ T012 (2026-07-12) examples 命名一致性 + README 补齐
**修复**: 统一 `examples/01-carbon-did/README.md` 等命名, 每篇 200 字以内概述。

---

### [x] ✅ T013 (2026-07-12) `examples/*/tables/` `figures/` 空目录填实
**修复**: pipeline 完成后 copy 关键 table/figure。

---

### [x] ✅ T014 (2026-07-12) `Dockerfile.dashboard` 等说明
**新增**: `DOCKERFILES.md` 说明 4 个 Dockerfile 用途。

---

## 🏗️ P3 · 架构 & 代码组织（未来工作）

### T015-T020 🟢
- T015 拆 `modern_did.py` (2404 行)
- T016 拆 `synthetic_control.py` (1246 行)
- T017 验证 Augmented SCM 实现
- T018 CI run_sh 在干净 Linux 容器验证
- T019 深 EXEC 测试文件去重

**状态**: 本次会话不实施, 留作后续工作。

---

## 🧪 P4 · 测试覆盖 & CI 严格性

### T021 🟡 audit_guard.py 新增 check 17: 反模式检测
**新增**:
- 检测 mechanism variable = linear combo of treatment
- 检测 SC sig 用 raw threshold 而非 permutation p-value
- 检测 DID T_post < 5 未标注
- 检测 short-panel DID without robustness check

---

### T022-T025 🟢
- T022 Coverage threshold 60%
- T023 Conftest 加 fixtures
- T024 CI 矩阵扩展 macOS + Windows
- T025 LaTeX compile test on every PR

**状态**: 本次会话不实施, 留作后续工作。

---

## 📈 P5 · 增长策略（高 Star 专项，未来工作）

### T026-T034
- T026 复现 5 篇顶刊 DID 论文
- T027 arXiv pre-print
- T028 Overleaf integration
- T029 Streamlit Dashboard
- T030 视频教程系列
- T031 MHE 教学 syllabus
- T032 多语言 README
- T033 X.com / Reddit / Zhihu 营销
- T034 HF Spaces + Replicate demo

**状态**: 本次会话不实施, 留作后续工作。

---

## 📊 进度追踪

| Priority | Total | Pending | In Progress | Completed |
|---|---:|---:|---:|---:|
| P0 学术诚信 | 4 | 4 | 0 | 0 |
| P1 可复现性 | 4 | 4 | 0 | 0 |
| P2 文档 | 6 | 6 | 0 | 0 |
| P3 架构 | 6 | 6 | 0 | 0 (deferred) |
| P4 测试 | 5 | 5 | 0 | 0 (T021 in scope) |
| P5 增长 | 9 | 9 | 0 | 0 (deferred) |
| **Total** | **34** | **34** | **0** | **0** |

---

## 🎯 本次会话执行范围

**本次会话目标**: 完成 P0 + P1 + P2 + T021 (audit_guard 反模式检测)。
**推迟**: P3 + T022-T025 + P5 (留作后续 sessions)。

---

## ✅ 验收 Checkpoint (每次 commit 前)

- [ ] `pytest tests/ -x -q --tb=short --timeout=60` 全通过
- [ ] `ruff check scripts/ mcp_servers/ tests/ --ignore E501 --line-length 100 --ignore S110` 全通过
- [ ] `python scripts/audit_guard.py` ≥17/17 (本次会话完成后)
- [ ] `python scripts/count_assets.py` 数字对齐 README
- [ ] 重新跑 `bash scripts/demo/record_full_pipeline_v4.sh` 成功
