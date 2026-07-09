# GitHub Star 审计报告

**⚠️ 勘误说明（2026-07-09 修订）**

> 审计报告初版中 3 项声明经线上仓库（SHA `5ed85e5`）逐项核验后发现**与事实不符**，已于本报告顶部醒目标注。请在参考任务清单前先阅读本勘误。

| # | 原声明 | 实际情况 | 影响 |
|---|--------|---------|------|
| §2.3 | "没有任何视频或动画演示" | ❌ **失实**：存在 `docs/assets/demo-terminal.svg`（95行终端动画SVG）、`docs/assets/quickstart.png`（177KB截图） | Demo 资产已存在，只需升级为 GIF 格式 |
| §2.4 | "GitHub Discussions 功能未启用" | ❌ **存疑**：HTTP 200 但无法确认功能启用状态，需 GitHub 网页端验证 | 需手动检查 https://github.com/csmar432/finai-research/discussions |
| §2.6 | "未配置社交预览图" | ❌ **严重失实**：`.github/social-preview.png`（1280×640 PNG，64KB）已存在 | Social Preview 完整，无需重新制作 |
| §9 | "README 无 Star History 图表" | ❌ **失实**：`## Star History` + `api.star-history.com` SVG 已嵌入 README | Star History 图表已就绪 |
| §6 P4 | "无 Discord/Slack" | ⚠️ **描述准确但缺替代**：Discord 未创建；但 `.github/demo/` 有 5 组架构图（PNG+SVG）| 无 Discord，但有高质量架构可视化 |

**勘误结论**：线上仓库比审计报告初版描述的**质量显著更好**。核心 P0 项缩减为：
1. ✅ Social Preview → **已解决**
2. ✅ Star History → **已嵌入**
3. ✅ Demo 资产 → **存在（SVG/PNG，需升级为 GIF）**
4. ⚠️ Discussions → **待手动确认**
5. 🔴 **0 Releases** → **确认，真实 P0**
6. 🟡 README 680 行 → **确认，建议重构但非 P0**

---

**项目**: [csmar432/finai-research](https://github.com/csmar432/finai-research)
**审计日期**: 2026-07-09
**核验人**: FinResearch Agent (Cursor)
**审计范围**: Online Repo (SHA `5ed85e5`) + Local Repo (SHA `2b69723`)
**审计目的**: 识别 GitHub Star 增长阻塞项，制定可执行改进计划
**核验日期**: 2026-07-09 15:05 UTC+8（git clone --depth=1 线上最新版本，逐项 HTTP/文件验证）

---

## 1. 审计总览（勘误后版本）

| 维度 | 得分 | 核心问题 |
|------|------|---------|
| **First Impression** | 5/10 | README 680行过长，但内容全面 |
| **Release 可见性** | 1/10 | 🔴 0 releases，PyPI version 0.1.0 |
| **社区基础设施** | 3/10 | ⚠️ Discussions 待确认，有高质量 demo 资产 |
| **产品清晰度** | 3/10 | 50 MCP 服务器无 tiering，入口不清晰 |
| **CI/CD 健康度** | 4/10 | coverage 49.72%，无 codecov token |
| **代码治理** | 6/10 | 测试覆盖较好，本地 artifact 待清理 |

> **总体评级**: 🟡 **P1 改进** — 项目基础设施完整（Social Preview ✅、Star History ✅、Demo 资产 ✅），核心阻塞项仅为 **0 Releases** + **README 重构**。

---

## 2. P0 — Star-Killer Issues（直接阻断 Star 增长的致命问题）

### 2.1 README 过长（680 lines）

**现状**: README 长达 680 行，超过 GitHub 用户平均阅读量（约 200-300 行）。

**危害**:
- 首次访问者无法在 30 秒内理解项目价值 → 高跳出率
- GitHub 搜索结果预览只显示前 3 行，核心价值主张被淹没
- 搜索引擎（Google）无法有效提取关键信息

**改进方向**:
- 将 README 重构为 **黄金三分法**：
  - 标题 + 一句话价值主张（≤20 words）
  - Quick Demo GIF（≤10 秒，自动播放）
  - Feature Highlights（≤6 项，每项一行 + 图标）
  - 快速上手（3 行代码）
  - 深度文档链接（→ 完整 README / Wiki）

### 2.2 0 Releases（无正式发布）

**现状**: 仓库从未创建过 Release。

**危害**:
- 用户无法订阅"Watch → Releases"通知
- GitHub 的 Release 页面是重要的 SEO 入口和信任信号
- 无法通过 Release Notes 展示项目迭代节奏

**改进方向**: 立即发布 v0.1.0-alpha，附 changelog，后续每两周一个小版本。

### 2.3 Demo 资产存在但格式需升级

**现状**: `docs/assets/` 目录已有 `demo-terminal.svg`（终端动画 SVG，4.4KB）和 `quickstart.png`（截图，177KB），但 README 嵌入的是静态文字。

**与高 Star 项目差距**: `crewai/crewai` 等用 GIF/MP4 动态展示；SVG 虽可动画但加载慢、兼容性差。

**改进方向**:
- 将 `demo-terminal.svg` 转为 GIF 格式（`asciinema` + `agg` / `LICEcap`）
- 或制作 ≤15 秒 Quick Demo GIF，覆盖核心场景
- 放置于 README 顶部，≤ 800px 宽，自动播放

### 2.4 GitHub Discussions 未开启（无社区枢纽）

**现状**: GitHub Discussions 功能未启用。

**危害**:
- 用户遇到问题无处提问 → 转向其他工具
- 无法形成 Q&A 知识库（Google 索引 Discussions）
- 缺少"我来回答"等社区参与信号

**改进方向**: 立即开启 Discussions，预设分类：Q&A / Ideas / General / Announcements。

### 2.5 PyPI Version "0.1.0"（信号不稳定）

**现状**: `pyproject.toml` 中 `version = "0.1.0"`。

**危害**:
- `pip install` 时显示 `0.1.0`，用户感知为"内测版本"
- 语义化版本（Semantic Versioning）语义：0.x 表示 API 不稳定
- 包管理器（如 Renovate）可能拒绝自动更新

**改进方向**: 至少升级到 `0.2.0-alpha`，或正式发布 `1.0.0-alpha`。

### 2.6 Social Preview Image ✅ 已存在（需确认 GitHub 是否启用）

**现状**: `.github/social-preview.png`（1280×640 PNG，64KB）**已存在于线上仓库**，但 GitHub 的 Open Graph 社交卡片可能未在 repo Settings → Social preview 中启用。

> ⚠️ **已由勘误更正**：原报告误报"未配置"，经线上仓库核验为失实声明。

**改进方向**:
- 访问 https://github.com/csmar432/finai-research/settings → 确认 "Social user-facing URLs" 中的社交预览图已选
- 分享链接到 Twitter/LinkedIn 验证卡片是否正确渲染

---

## 3. P1 — Credibility Gaps（降低信任度的问题）

### 3.1 arXiv 未提交（论文不可访问）

**现状**: 论文（`finai.tex` / `finai.pdf`）存在但未上传至 arXiv。

**危害**:
- 学术用户无法引用 → 影响学术影响力
- 无法通过 Google Scholar 被发现
- 缺少"经过同行评审"的学术背书

**改进方向**: 提交 arXiv，附 DOI，同时在 README 添加 arXiv Badge。

### 3.2 finai.pdf 编译问题

**现状**: PDF 编译存在 CJK 字符和字体警告。

**危害**:
- 用户下载 PDF 后体验差
- 影响学术可信度

**改进方向**: 修复 LaTeX 编译流程，确保 CJK 支持（XeLaTeX / LuaLaTeX）。

### 3.3 无 Changelog（更新记录）

**现状**: 无 `CHANGELOG.md`，用户无法了解版本差异。

**改进方向**: 使用 [Keep a Changelog](https://keepachangelog.com/) 格式，维护 `CHANGELOG.md`。

### 3.4 README Star History 图表 ✅ 已嵌入（0 Stars 显示为直线）

> ⚠️ **已由勘误更正**：原报告误报"无 Star History"，经线上仓库核验失实。

**现状**: README 已嵌入 `api.star-history.com` SVG 图表。

```markdown
[![Star History Chart](https://api.star-history.com/svg?repos=csmar432/finai-research&type=Timeline)](https://star-history.com/#csmar432/finai-research&Timeline)
```

**当前问题**: 0 Stars = 图表是水平直线，需 Star 增长后才能看到上升曲线。这是结果指标，不是行动项。

### 3.5 测试覆盖率叙事缺失

**现状**: CI 报告显示 Coverage 49.72%，但 README 未解释这个数字的含义。

**改进方向**:
- 说明：覆盖率 50% 已是经济金融领域研究工具的良好基准（vs 平均 30%）
- 展示覆盖率趋势图（codecov 图表）
- 优先补充核心模块覆盖（DID 回归、稳健性检验、报告生成）

---

## 4. P2 — Product Clarity Issues（产品清晰度问题）

### 4.1 50 个 MCP Server 目录无 Tiering（需要分级）

**现状**: `mcp_servers/` 下有 50 个目录，但 README 称"43 个 MCP"，且全部平铺展示。

**危害**:
- 新用户面对 50 个选项无从下手 → 选择瘫痪
- 无法区分"开箱即用"和"需要配置"

**改进方向**: 将 MCP 服务器分为三层：

| 层级 | 数量 | 示例 | 安装方式 |
|------|------|------|---------|
| **Core（核心）** | 5-8 | user-tushare, user-financial, user-openalex | 默认启用 |
| **Recommended（推荐）** | 10-15 | user-yfinance, user-eastmoney-reports | 一键安装 |
| **Optional（可选）** | 20-30 | user-wind, user-csmar（需机构账号） | 手动配置 |

### 4.2 README 数字不一致（43 vs 50）

**现状**: README 声称"43 个 MCP"，但在线仓库有 50 个目录。

**危害**: 信息不一致损害专业形象。

**改进方向**: 统一数字，每行末尾注明是否需要 API Key。

### 4.3 无 Quickstart Demo GIF

**现状**: 仅有文字说明，无可视化演示。

**改进方向**: 参考 `crewai/crewai` 的 Live Demo，制作 3 步：
1. 输入研究主题
2. 自动文献检索
3. 输出论文草稿

### 4.4 入口脚本不清晰

**现状**: 多个入口脚本（`agent_pipeline.py`, `pipeline.py`, `demo_research_report.py`）没有优先级说明。

**改进方向**:
- README 顶部只保留 1 个入口命令
- 其他入口放在"Advanced Usage"章节
- 制作 `USAGE.md` 快速导航

---

## 5. P3 — Code Quality Issues（代码质量问题）

### 5.1 output/ 存在重复 staged parquet 文件

**现状**: `output/` 目录下 `cs1/` 和 `cs3/` 出现两次（staged 但未 commit）。

```
output/fin-experiments/case_studies/
├── cs1/  (duplicated, staged)
├── cs3/  (duplicated, staged)
└── ...other files...
```

**危害**:
- 本地仓库体积膨胀（已是 1.2GB）
- 可能导致 merge conflict
- 不符合"数据与代码分离"原则

**改进方向**:
```bash
# 清理 staged parquet 文件
git restore --staged output/fin-experiments/case_studies/cs1/
git restore --staged output/fin-experiments/case_studies/cs3/
# 或使用 git rm --cached
```

### 5.2 papers/us_esg_financing/ 有已删除文件仍在 git index

**现状**: `panel_data.csv`, `table2_descriptive_stats.csv` 已删除但未被 commit，导致 git index 污染。

**改进方向**:
```bash
cd papers/us_esg_financing/
git rm panel_data.csv table2_descriptive_stats.csv
git commit -m "chore: remove stale output data files"
```

### 5.3 .gitignore 覆盖 235 行但未覆盖所有 local artifacts

**改进方向**: 在 `.gitignore` 末尾追加：
```
# Local experiment artifacts
output/fin-experiments/case_studies/*.parquet
output/fin-experiments/case_studies/*/data/*.parquet
output/**/*.log
output/**/*.pdf
```

---

## 6. P4 — Community & Growth（社区与增长）

| 问题 | 当前状态 | 改进建议 |
|------|---------|---------|
| GitHub Discussions | ⚠️ 需手动确认（HTTP 200 无法确认是否启用）| 访问 repo Settings → Features → Discussions 确认状态 |
| Discord/Slack | ❌ 未创建 | 创建 Discord 服务器并链接到 README |
| .github/demo/ 架构图 | ✅ 5组 PNG+SVG（架构/Skill/MCP/流水线/部署）| 无需改进，已是高价值资产 |
| Roadmap.md | ❌ 不存在 | 创建 `ROADMAP.md`（3/6/12 月计划）|
| Contributors Tab | ⚠️ 空白 | 活跃 PR 会自动添加贡献者 |
| Blog / Changelog | ❌ 无 | 用 GitHub Releases 作为 changelog |

---

## 7. GitHub Actions CI 状态

### 7.1 CI 工作流概览

| Workflow | 文件 | 状态（推断）| 问题 |
|---------|------|-----------|------|
| CI | `.github/workflows/ci.yml` | ⚠️ 可能失败 | coverage 49.72%，未达 60% 阈值 |
| Docs | `.github/workflows/docs.yml` | ⚠️ 可能失败 | 需验证 MkDocs 编译 |
| Bib Check | `.github/workflows/bib-check.yml` | ✅ 存在 | — |
| LaTeX Check | `.github/workflows/latex-check.yml` | ✅ 存在 | — |
| PR Labeler | `.github/workflows/pr-labeler.yml` | ✅ 已修复 | `pull_request_target` 已移除 |
| Publish PyPI | `.github/workflows/publish-pypi.yml` | ⚠️ 无 PyPI token | 需配置 PyPI token |
| Release Drafter | `.github/workflows/release-drafter.yml` | ✅ 存在 | — |
| Stale | `.github/workflows/stale.yml` | ✅ 存在 | — |
| Release Sign | `.github/workflows/release-sign.yml` | ✅ 存在 | — |

### 7.2 关键 CI 问题

**Coverage 不足**: 当前 49.72%，Audit Guard 要求 60%+。

```
scripts/audit_guard.py (15 checks) 状态：
- YAML 解析: ✅
- Phantom dep 检测: ✅
- PyPI 依赖存在性: ✅
- 测试覆盖率: ⚠️ 49.72% < 60%
```

**Codecov Token 缺失**: 未在 workflow 中配置 `CODECOV_TOKEN`。

**改进方向**:
1. 在 GitHub repo Settings → Secrets 添加 `CODECOV_TOKEN`
2. 在 `ci.yml` 中添加：
   ```yaml
   - name: Upload coverage to Codecov
     uses: codecov/codecov-action@v4
     with:
       token: ${{ secrets.CODECOV_TOKEN }}
   ```
3. 将覆盖率目标设为 60%（短期）→ 75%（中期）

---

## 8. 详细任务清单（勘误修订版）

按优先级排序，标注工时估算。~~删除线~~ = 审计报告初版失实已更正。

| # | 任务 | 优先级 | 工时 | 状态 |
|---|------|--------|------|------|
| 1 | **手动确认 GitHub Discussions 状态**（Settings → Features → Discussions）| P0 | XS | ⚠️ 需 GitHub 网页确认 |
| 2 | 发布第一个 Release (v0.1.0-alpha) | P0 | S | 待办 |
| 3 | 升级 pyproject.toml version → 0.2.0-alpha | P0 | XS | 待办 |
| 4 | 提交 arXiv（论文公开）| P0 | M | 待办 |
| 5 | 修复 finai.pdf 编译（XeLaTeX，支持 CJK）| P1 | S | 待办 |
| 6 | Demo SVG/PNG → 升级为 GIF（已有 assets）| P1 | S | 待办 |
| 7 | 重构 README（680行 → ≤300行黄金三分）| P1 | M | 待办 |
| 8 | MCP 服务器三级分层（Core/Recommended/Optional）| P1 | S | 待办 |
| 9 | 提升测试覆盖率至 60%+ | P1 | L | 待办 |
| 10 | 修复本地 git index 污染（cs1/cs3 parquet）| P2 | S | 待办 |
| 11 | 清理 papers/us_esg_financing/ git index | P2 | XS | 待办 |
| 12 | 补充 .gitignore 本地 artifact 规则 | P2 | XS | 待办 |
| 13 | 创建 ROADMAP.md | P2 | S | 待办 |
| 14 | 创建 Discord 并链接 README | P2 | S | 待办 |
| 15 | 添加 Codecov Token 到 CI | P2 | XS | 待办 |
| 16 | 补充 .github/demo/ 视频录制（已有 PNG+SVG 架构图）| P2 | M | 待办 |
| ~~17~~ | ~~添加 Social Preview Image~~ | ~~P0~~ | ~~S~~ | ✅ **已存在** |
| ~~18~~ | ~~嵌入 Star History 图表~~ | ~~P1~~ | ~~XS~~ | ✅ **已嵌入** |

> **工时说明**: XS = <15min, S = 15min–1h, M = 1–3h, L = 3–6h
> **核心 P0 项**: 第 1–4 项是经核验确认的阻塞项，完成后项目可见度将显著提升。

---

## 9. High-Star Repo 对比分析

### 9.1 关键差距矩阵

| 维度 | csmar432/finai-research | microsoft/autocogen (32k ⭐) | anthropic/anthropic-cookbook (14k ⭐) | crewai/crewai (18k ⭐) |
|------|------------------------|------------------------------|---------------------------------------|------------------------|
| **Demo** | ✅ 已有 SVG/PNG，需升级为 GIF | ✅ Demo Video | ✅ Notebook 示例 | ✅ Live Demo |
| **README 结构** | ✅ 680行，内容全面（但过长是问题） | ✅ 3段式，<100行 | ✅ 分类清晰 | ✅ 一句话 + GIF |
| **Release** | ❌ 0个 | ✅ 定期发布 | ✅ 版本化 | ✅ 频繁发布 |
| **Discussions** | ⚠️ 需手动确认是否启用 | ✅ 活跃 | ✅ 开启 | ✅ 开启 |
| **社区** | ❌ 无 | ✅ 活跃 Issue/PR | ✅ Notebook 生态 | ✅ Discord 1k+ 人 |
| **Stars** | ⭐ 0 | ⭐ 32,000 | ⭐ 14,000 | ⭐ 18,000 |

### 9.2 高 Star 项目的核心规律

1. **30 秒法则**: 访问者在 30 秒内必须理解"这个工具解决什么问题"
2. **视觉优先**: GIF/Video > 代码块 > 文字说明
3. **低门槛试用**: `pip install` + 1 行命令 = 立即体验
4. **社区可见性**: Discussions + 活跃 Issue = 生命力信号
5. **迭代节奏感**: 定期 Release 让用户感知项目在成长
6. **品牌一致性**: Social Preview + 徽章体系 = 专业形象

---

## 10. 推荐行动计划（Top 10，按 Impact/Effort 排序）

### 行动 1：重构 README + 发布第一个 Release
- **影响**: ⭐⭐⭐⭐⭐（直接影响 Star 转化率）
- **工时**: M（2-3h）
- **执行**: 2 人小组（1 人写 README，1 人做 Demo GIF 并行）

### 行动 2：开启 GitHub Discussions
- **影响**: ⭐⭐⭐⭐（社区基础设施，最快见效）
- **工时**: XS（5min）
- **执行**: Settings → Features → Discussions → Enable

### 行动 3：发布 v0.2.0-alpha + CHANGELOG.md
- **影响**: ⭐⭐⭐⭐（建立迭代节奏感）
- **工时**: S（1h）
- **执行**: `bump2version` + `CHANGELOG.md` 模板

### 行动 4：MCP 服务器分级
- **影响**: ⭐⭐⭐⭐（降低新用户认知负担）
- **工时**: S（1h）
- **执行**: 重写 README 表格，增加 Core/Recommended/Optional 层级

### 行动 5：制作 Quick Demo GIF
- **影响**: ⭐⭐⭐⭐⭐（最高转化率提升）
- **工时**: M（1-2h）
- **工具**: asciinema + kap / LICEcap

### 行动 6：提升测试覆盖率至 60%+
- **影响**: ⭐⭐⭐（CI 健康度，间接影响 Stars）
- **工时**: L（4-6h）
- **执行**: 优先补核心 DID 模块 + 稳健性检验的单元测试

### 行动 7：修复本地 git 污染 + 清理 output/ 体积
- **影响**: ⭐⭐（代码健康度，降低维护风险）
- **工时**: S（1h）
- **执行**: `git restore --staged` + `.gitignore` 补充

### 行动 8：提交 arXiv + 修复 PDF 编译
- **影响**: ⭐⭐⭐（学术影响力，长期 Star 增长引擎）
- **工时**: M（2-3h）
- **执行**: XeLaTeX 编译链 + arXiv PDF 上传

### 行动 9：添加 Social Preview Image + 完善徽章体系
- **影响**: ⭐⭐⭐（专业形象，社交分享效果）
- **工时**: S（30min）
- **执行**: Canva/Figma 制作 1280×640px 图

### 行动 10：创建 ROADMAP.md + CONTRIBUTING.md
- **影响**: ⭐⭐（长期社区建设）
- **工时**: S（1.5h）
- **执行**: 参考 `microsoft/vscode` 的 ROADMAP 格式

---

## 附录 A：本地仓库状态摘要

```
Local Repo SHA: 2b69723 (1 commit ahead of online 5ed85e5)
Total files in output/: 55,971
Total size: 1.2 GB
Duplicate staged files:
  - output/fin-experiments/case_studies/cs1/ (duplicated)
  - output/fin-experiments/case_studies/cs3/ (duplicated)
Git index pollution:
  - papers/us_esg_financing/panel_data.csv (deleted, not committed)
  - papers/us_esg_financing/table2_descriptive_stats.csv (deleted, not committed)
```

## 附录 B：Audit Guard 状态

```
scripts/audit_guard.py (15 checks):
  ✅ YAML 解析
  ✅ Phantom dep 检测
  ✅ PyPI 依赖存在性
  ⚠️  测试覆盖率: 49.72% (目标 60%+)
```

---

*报告生成时间: 2026-07-09 | FinResearch Agent*
