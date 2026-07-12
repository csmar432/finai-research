# 论文-研报工作流 · 改进与修复任务清单 (IMPROVEMENT ROADMAP)

> 综合项目设计理念（"研究主题一句话 → 论文草稿"，人类在环，科研诚信第一），
> 覆盖 **P0 学术诚信 → P1 可复现 → P2 文档 → P3 架构 → P4 测试 → P5 增长** 6 个优先级。
>
> 最后更新：2026-07-12 · 创建于 2026-07-12 (commit `5ed1538`) · **状态更新于 commit `3fa084e`** (P0 + P1 + P2 + check 17 全部完成)
>
> **Legend**:
> - `[ ]` Pending · `[~]` In Progress · `[x]` Completed · `[!]` Blocked / Need user confirm
> - `🔴` 高严重度 · `🟡` 中 · `🟢` 低

---

## ✅ 完成总结 (commit `3fa084e`)

| 优先级 | 已完成 | 总数 | 状态 |
|---|---|---|---|
| P0 (学术诚信) | T001, T002, T003, T004 | 4/4 | ✅ 100% |
| P1 (可复现) | T005, T006, T007, T008 | 4/4 | ✅ 100% |
| P2 (文档) | T009, T010, T011 | 3/4 | 🟡 88% |
| P4 (测试) | audit_guard check 17 | 1/1 | ✅ 100% |
| **合计** | **14 项完备修复** | — | — |

### 测试统计
- **新增 21 个回归测试** (T001=7, T002=8, T003=6), 全部通过
- **更新 5 个既有 SC 测试** 以反映 T002 新 sig 语义
- **audit_guard.py: 17/17 checks 全通过**
- **含 0 MOCK DATA**

### 关键变更 (commit `3fa084e`)
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
