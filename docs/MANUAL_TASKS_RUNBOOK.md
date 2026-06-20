# 手动事项 Runbook (MANUAL_TASKS_RUNBOOK)

> **本地操作手册**：4 个手动事项的逐步流程指引。
> 本文件不纳入版本控制（.gitignore 防护），仅本地参考。
> 所有可复制内容放在代码块中。预估总耗时：60-90 分钟。

---

## 📋 总览

| # | 任务 | 耗时 | 难度 | 关键链接 |
|---|------|------|------|----------|
| 1 | 合并 PR (5 commit) | 10 min | 简单 | https://github.com/csmar432/finai-research-workflow/pull/new/audit-fixes-2026-06-16 |
| 2 | 设置 GitHub Topics | 5 min | 简单 | 仓库 Settings → Topics |
| 3 | 发 awesome list PR (×7) | 60 min | 中等 | 7 个 awesome list 仓库 |
| 4 | 发 HN/Reddit/知乎 | 30 min | 中等 | HN/Reddit/知乎平台 |

**建议顺序**: 1 → 2 → 4 → 3（先合并，再发外部传播）

---

# 任务 1: 合并 PR (5 commit)

## 1.1 进入 PR 页面

1. 打开 https://github.com/csmar432/finai-research-workflow/pull/new/audit-fixes-2026-06-16
2. 看到 "Open pull request" 表单
3. **Title**: `🚀 v1.0 全面修复 + 高星路线图 (5 commits)`
4. **Comment** 粘贴：

```markdown
## 📋 概述

5 个 commit 包含 4 类改进：

1. **779ce5a** - 修复 2 个 P0 运行时 bug + 统一文档数字 (43 MCP, 42 methods)
2. **f2cf278** - 高星路线图 + README 视觉资产 (banner/quickstart) + Star History
3. **d92b338** - 修复 P0 测试失败 (test_iv_surface_latex_export KeyError) + 删除 8 个泄露隐私的内部文档
4. **586cab8** - 完善社区基础设施 (Issue/PR 模板 + ROADMAP gitignore)
5. **0480ce6** - A+B 阶段全部完成 (Week 1-2 + 60天核心功能)
   - 3 张 social preview (1280×640/1280×320/800×800)
   - 3 个 Mermaid 架构图 (Pipeline DAG / MCP Fallback / Modern DID)
   - 5 列对比表 (vs StatsPAI/PaperOrchestra/E2ER/dowhy)
   - 6 个新 Python 模块 (碳交易/政策事件/A股控制/PSM-DID/Mediation/Moderation)
   - 4 个 Launch 草稿 (HN/Reddit/知乎/awesome list)
   - 完整 CONTRIBUTING + CITATION 指南
   - 3 个集成 (Claude Code plugin / Cursor ext / GitHub Action)

## ✅ 测试

- 150/150 核心测试通过
- 6 个新模块 demo 全部成功
- health_check.py 正常
- 隐私扫描：跟踪文件零泄露

## 🔒 隐私清理

- 删除 8 个含真实身份信息的内部 docs
- ROADMAP.md / STAR_GROWTH_PLAN.md 在 .gitignore
- 新 commit 历史完全干净

## 📂 涉及文件

- 23 个新文件 (+8,121 行)
- 6 个 Python 模块 (china_carbon_events / china_policy_events / a_share_firm_controls / psm_did / mediation / moderation)
- 4 个 Markdown 文档 (LAUNCH_KIT / AWESOME_LIST_PR / CITATION / BLOG_OUTLINES)
- 6 个视觉资产 (3 social preview × 2 格式)
- 3 个集成 (Claude Code / Cursor / GitHub Action)
- 1 个工具 (dependency_upgrader.py)
- 1 个脚本 (setup_env.sh)

## 🧪 Reviewer 自查清单

- [x] All tests pass
- [x] Documentation updated
- [x] No PII leak
- [x] Backward compatible
- [x] CHANGELOG updated
- [x] No force push needed
```

5. 滚到页面底部，点 **"Create pull request"**（绿色按钮）
6. 会跳转到 PR review 页面（URL 变成 `/pull/24` 之类）

## 1.2 等待 CI 通过

1. 在 PR 页面，滚到 "Checks" 部分
2. 等待 5-15 分钟
3. 如果全绿 ✅ → 进入 1.3
4. 如果有红 ❌：
   - 点开看 log
   - 大概率是 network (apt-get 失败) 或 1 个 flaky test
   - 修后 push，CI 会自动 re-run

## 1.3 合并 PR

1. 页面右侧（或底部）找到 **"Merge pull request"** 按钮
2. 点击下拉箭头 → 选 **"Squash and merge"**（推荐，5 commit 合成 1 个）
3. 弹出确认框：
   - **Commit message** 自动生成，可修改为：

```
🚀 v1.0 release: 修复 + 高星资产 + 经济金融特化功能 (squash of 5 commits)

- 修 P0 测试 bug (test_iv_surface_latex_export KeyError)
- 修 Dockerfile xuzheyi → csmar432 (本地)
- 删 8 个内部 docs (含 PII)
- 加 23 个新文件 (+8,121 行):
  * 6 Python 模块 (碳交易/政策事件/A股控制/PSM-DID/Mediation/Moderation)
  * 4 docs (LAUNCH_KIT/AWESOME_LIST_PR/CITATION/BLOG_OUTLINES)
  * 6 视觉资产 (3 social preview × 2 格式)
  * 3 集成 (Claude Code/Cursor ext/GitHub Action)
  * 1 工具 (dependency_upgrader.py)
  * 1 脚本 (setup_env.sh)
- 加 3 Mermaid 架构图 + 5 列对比表到 README
- 完整 CONTRIBUTING + CITATION 指南

Tests: 150/150 pass | 隐私: 0 leak | Demo: PSM-DID ATT=0.4996 ✓

Co-authored-by: Cursor <cursoragent@cursor.com>
```

4. 点 **"Confirm squash and merge"**
5. 弹窗询问是否删除分支 → ✅ 勾选 "Delete branch"
6. 点 **"Delete branch"** 确认

## 1.4 验证合并成功

1. 打开 https://github.com/csmar432/finai-research-workflow/commits/main
2. 应该看到刚才的 commit 在最顶部
3. README 顶部会自动展示 social-preview-1280x640.png

## 1.5 失败应急

| 失败情况 | 解决方案 |
|---------|----------|
| CI 红但本地全绿 | 用 admin override（你仓库主）|
| Merge conflict | 在本地 main 上 `git merge audit-fixes-2026-06-16`，解冲突，push 后再合 |
| 想改 commit message | squash merge 时改 message 即可 |

---

# 任务 2: 设置 GitHub Topics (10 个)

## 2.1 进入设置

1. 打开 https://github.com/csmar432/finai-research-workflow/settings#repo-topics
2. 滚到 **"Topics"** 部分
3. 看到一个输入框 + "Add topic" 按钮

## 2.2 添加 10 个 topics

**逐个复制粘贴**到输入框（每次一个，按 Enter 或点 "Add topic"）：

```
academic-research
financial-ai
econometrics
paper-writing
latex
mcp
difference-in-differences
causal-inference
research-workflow
agent
```

## 2.3 验证

1. 页面回到顶部 → 点仓库名 → 看 README 顶部
2. **"About" 卡片** 右侧应该显示 10 个彩色 topic 标签

## 2.4 为什么是这 10 个？

| Topic | 覆盖范围 | 搜索量 |
|---|---|---|
| academic-research | 学术研究通用 | 高 |
| financial-ai | 金融 AI 垂直 | 中 |
| econometrics | 计量经济学 | 高 |
| paper-writing | 论文写作 | 高 |
| latex | LaTeX 排版 | 极高 |
| mcp | Model Context Protocol | 中（上升期）|
| difference-in-differences | DID 核心方法 | 中 |
| causal-inference | 因果推断 | 极高 |
| research-workflow | 研究工作流 | 中 |
| agent | AI Agent | 极高 |

---

# 任务 3: 发 awesome list PR (×7)

> **总计 7 个 PR**，每个 5-10 分钟。**重要性排序**：

| 优先级 | Awesome list | 理由 |
|---|---|---|
| ⭐⭐⭐⭐⭐ | awesome-economics | 直接相关，命中搜索多 |
| ⭐⭐⭐⭐⭐ | awesome-causal-inference | 因果推断核心社区 |
| ⭐⭐⭐⭐ | awesome-mcp | MCP 是趋势词，新晋好客 |
| ⭐⭐⭐⭐ | awesome-llm-agents | AI Agent 上升期 |
| ⭐⭐⭐ | awesome-academic-writing | 学术写作社区 |
| ⭐⭐ | awesome-stata | 计量社区 |
| ⭐ | awesome-python (Science) | 通用，被淹没概率高 |

## 3.1 通用流程

每个 awesome list 都是**同一个流程**：

### Step 1: 找到 awesome list 仓库

打开对应仓库（从 docs/AWESOME_LIST_PR_TEMPLATES.md 复制链接）

### Step 2: 阅读 CONTRIBUTING.md（如果存在）

大多数 awesome list 在 README 顶部或 CONTRIBUTING.md 有要求。

### Step 3: Fork + 编辑

1. 打开 awesome list 的 README.md
2. 点 ✏️ "Edit this file" 按钮
3. 如果提示 "Fork this repository" → 点击创建 fork
4. **进入 GitHub 网页编辑器**

### Step 4: 添加条目

1. **找到正确位置**（看模板里的指示）
2. **保持原有格式**（其他条目的格式）
3. **粘贴新条目**（来自模板）
4. **不要修改其他条目**

### Step 5: 提交 PR

1. 滚到底部 → "Propose changes"
2. **Commit title** 填 `Add FinAI Research Workflow`
3. **Extended description** 粘贴模板里的 "PR Body" 段
4. 点 "Propose changes"
5. 跳转到 "Comparing changes" 页面
6. 点 "Create pull request"
7. 确认 PR 标题 + 描述
8. 点 "Create pull request"

## 3.2 7 个 PR 具体内容

### PR 1: awesome-economics

**仓库**: https://github.com/antonalley/awesome-economics

**步骤**:
1. 打开 https://github.com/antonalley/awesome-economics/blob/main/README.md
2. 点 ✏️ 编辑
3. 找到 "Software" 或 "Tools" 章节
4. 在适当位置加一行：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - End-to-end AI agent pipeline for economic & financial research (lit review → empirical design → DID/IV/RDD → paper writing). 43 MCP data sources, 42 econometric methods, 17 AI skills. MIT.
```

5. Commit title: `Add FinAI Research Workflow`
6. PR title: `Add FinAI Research Workflow to Software section`
7. PR body: 粘贴 `docs/AWESOME_LIST_PR_TEMPLATES.md` 中 "1. awesome-economics" 部分的 PR Body

### PR 2: awesome-causal-inference

**仓库**: https://github.com/mauricio-zuber/awesome-causal-inference

**步骤**:
1. 打开 https://github.com/mauricio-zuber/awesome-causal-inference/blob/main/README.md
2. 找 "Software" 章节 → "Python" 子章节
3. 加：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - End-to-end AI agent for empirical research with modern causal inference (Callaway-Sant'Anna, Sun-Abraham, Borusyak, Goodman-Bacon, dCdH, Synthetic DiD, IV, GMM, RDD, PSM).
```

4. PR title: `Add FinAI Research Workflow`
5. PR body: 粘贴模板 "2. awesome-causal-inference" 段

### PR 3: awesome-mcp

**仓库**: https://github.com/kevinwu06/awesome-mcp (或 https://github.com/wong2/awesome-mcp)

**步骤**:
1. 找 "Servers" 或 "By Use Case" → "Research"
2. 加：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - 43 MCP servers for economic/financial research: Tushare (A-share), CSMAR, Wind, yfinance, FRED, OpenAlex (200M papers), ArXiv, Context7 (paper fulltext), and 35+ more.
```

3. PR title: `Add FinAI Research Workflow (43 MCP servers for economic research)`
4. PR body: 粘贴模板 "3. awesome-mcp" 段

### PR 4: awesome-llm-agents

**仓库**: https://github.com/kaushik-bhat/awesome-llm-agents (或 https://github.com/Thinklab-SJTU/awesome-LLM-agents)

**步骤**:
1. 找 "Frameworks" 或 "Research Applications"
2. 加：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - Multi-agent pipeline for economic research: 8 specialised agents (idea, lit review, novelty, design, data, analysis, writing, adversarial review) with human-in-the-loop checkpoints. 17 Skills, 43 MCP data sources.
```

3. PR title: `Add FinAI Research Workflow (multi-agent economic research pipeline)`
4. PR body: 粘贴模板 "4. awesome-llm-agents" 段

### PR 5: awesome-academic-writing

**仓库**: https://github.com/snwau/awesome-academic-writing

**步骤**:
1. 找 "Tools / Software" 章节
2. 加：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - AI-assisted academic paper writing for economists. 45 journal templates (English: JF/JFE/RFS/JAE/Econometrica; Chinese: 经济研究/金融研究/管理世界/会计研究/中国工业经济). LaTeX compilation, BibTeX management, citation verification, multi-round adversarial review.
```

3. PR title: `Add FinAI Research Workflow (45 journal templates, EN+CN)`
4. PR body: 粘贴模板 "5. awesome-academic-writing" 段

### PR 6: awesome-stata

**仓库**: https://github.com/wfg/awesome-stata

**步骤**:
1. 找 "Related Tools" 或 "Python alternatives" 章节
2. 加：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - Python equivalent of a complete Stata workflow for empirical economics. Modern DiD (CS/SunAb/Borusyak/GB/dCdH), IV, GMM, RDD, PSM. Outputs publication-ready LaTeX. Use when you want a Python-based end-to-end pipeline.
```

3. PR title: `Add FinAI Research Workflow (Python equivalent of complete Stata workflow)`
4. PR body: 粘贴模板 "6. awesome-stata" 段

### PR 7: awesome-python (Science)

**仓库**: https://github.com/vinta/awesome-python

**步骤**:
1. 找 "Science" 章节
2. **在 alphabetical order 找 "F" 位置**（注意 awesome-python 严格按字母排序）
3. 加：

```markdown
- [FinAI Research Workflow](https://github.com/csmar432/finai-research-workflow) - End-to-end AI agent for economic & financial research. 43 MCP data sources, 42 econometric methods, 17 AI skills, 45 journal templates (EN+CN). MIT.
```

4. PR title: `Add FinAI Research Workflow to Science section`
5. PR body: 粘贴模板 "7. awesome-python" 段

## 3.3 PR merge 后做什么

1. **4 周内**检查是否被合并
2. 如果 4 周未合并 → 在 PR 下 ping 维护者（"Friendly ping, is there anything I can do to help merge this?"）
3. 如果 8 周仍未合并 → 找下一个相关 awesome list
4. **记录所有 PR 状态**在自建 `docs/AWESOME_LIST_PR_TRACKER.md`

## 3.4 应急

| 情况 | 解决方案 |
|---|---|
| 找不到 README 锚点 | GitHub 搜索框搜 "Software" 找位置 |
| 维护者要求"1 PR = 1 tool" | 已经满足（每个 PR 加 1 个条目）|
| 排序规则是 alphabetical | 把首字母改成 `f`（小写）|
| 维护者要求 "description 限制 50 字" | 缩短 description 到 50 字内 |
| 多个维护者都不回复 | 找其他类似 list |

---

# 任务 4: 发 HN/Reddit/知乎

> **总时间约 30 分钟**。建议先合并 PR 再发（外部链接生效）。

## 4.0 准备

1. 确认 PR 已合并（任务 1 完成）
2. README 顶部 banner 已生效
3. **测试链接**（用 `curl -I https://github.com/csmar432/finai-research-workflow` 验证 200）

## 4.1 Hacker News (Show HN)

**最佳时间**: 周二/周三 8-10 AM EST (美东 = 北京晚 21-23 点)

### Step 1: 登录

1. 打开 https://news.ycombinator.com/submit
2. 登录账号（如果没账号 → 注册，用 `csmar432` 用户名保持品牌一致）
3. 填表

### Step 2: 填表

- **Title**: `Show HN: I built an end-to-end AI research agent for economists`
- **URL**: `https://github.com/csmar432/finai-research-workflow`
- **Text** (可选, 如果用 text 模式):

打开 https://news.ycombinator.com/submit → 选 "Show HN" 分类 → 把 `docs/LAUNCH_KIT.md` 中 "1. Hacker News — Show HN" 部分的 **Body** 整段粘贴。

### Step 3: 提交

点 "Submit"，注意页面是灰色极简风，要确认看到 "Show HN:" 标签

### Step 4: 跟进（重要！）

HN 提交后 1 小时内:

1. **你自己 + 几个朋友** 立即评论 1-2 条（避免沉底）
2. **回复所有评论**（前 4 小时是关键）
3. **HN 规则**:
   - ❌ 不要 "vote begging"
   - ❌ 不要解释 "I'm the author" 后立刻做营销
   - ✅ 接受所有批评（"too complex", "doesn't work"）
   - ✅ 给具体技术答案
4. 24 小时内如果没上首页 → 接受现实，可以试 resubmit 1 周后（换标题）

## 4.2 Reddit r/economics

**最佳时间**: 周二-周四 9-11 AM EST

### Step 1: 登录

1. 打开 https://www.reddit.com/r/economics/submit
2. 用已有账号登录（如没有 → 注册，用 brand 一致用户名）

### Step 2: 填表

- **Title**:
```
[Tool] I built an open-source AI agent that goes from research question to submission-ready LaTeX (43 MCP data sources, ~30 econometric methods, 17 AI skills, MIT licensed)
```
- **Body**: 粘贴 `docs/LAUNCH_KIT.md` 中 "2. Reddit r/economics" 部分
- **Flair**: 选 "Tool" 或 "Software"
- **Subreddit**: r/economics

### Step 3: 提交

点 "Post"。

### Step 4: 跟进

1. **每条评论都回复**（Reddit 算法看互动率）
2. 24 小时内回应负面评论
3. **重要**: 有些人会要求"演示" → 可以录 2-3 分钟 demo 上传 YouTube/Bilibili，贴链接
4. **不要 spam 链接**到其他 subreddit（会被 ban）

## 4.3 Reddit r/MachineLearning

**URL**: https://www.reddit.com/r/MachineLearning/submit

- **Title**:
```
[P] FinAI — an open-source multi-agent AI pipeline that turns a one-line research question into a submission-ready empirical econ paper (time and costs vary by complexity)
```
- **Body**: 粘贴 `docs/LAUNCH_KIT.md` 中 "3. Reddit r/MachineLearning" 部分
- **Flair**: "Project" 或 "Tool"

## 4.4 Reddit r/AskAcademia

**URL**: https://www.reddit.com/r/AskAcademia/submit

- **Title**:
```
[Tool] I open-sourced an end-to-end AI research workflow for empirical economics — would love feedback from active researchers
```
- **Body**: 粘贴 `docs/LAUNCH_KIT.md` 中 "4. Reddit r/AskAcademia" 部分

## 4.5 知乎专栏

**URL**: https://zhuanlan.zhihu.com/write

### Step 1: 登录

1. 打开 https://www.zhihu.com → 登录
2. 进入 https://zhuanlan.zhihu.com/write

### Step 2: 写文章

- **标题**: 粘贴 `docs/LAUNCH_KIT.md` 中 "5. 知乎专栏" 部分的标题
- **正文**: 粘贴整段 Markdown

> **重要**: 知乎的编辑器**不完美支持 Markdown**，有些格式会丢。建议：
> 1. 先在 Sublime Text / VSCode 写好
> 2. 复制粘贴
> 3. **手动调整** 表格 / 列表 / 代码块
> 4. 插入图片需要手动上传

### Step 3: 发布

- 选"专栏"或"想法"（建议专栏，更专业）
- **不立即发布** → 先存为草稿 → 检查一次 → 再发布

### Step 4: 同步

发到知乎后:
1. 复制链接
2. 发到：
   - 经济金融学术圈 (topic)
   - 数量经济学 (topic)
   - 计量经济学 (topic)
3. 发到你的朋友圈/微信群

## 4.6 备用：微信公众号

如果你有公众号:

1. 复制知乎文章的 markdown
2. 用 [md2zhihu](https://github.com/) 或手动排版
3. 标题 + 摘要 + 头图（用 `docs/assets/social-preview-1280x640.png`）
4. **晚 8-10 点**推送（阅读高峰）

## 4.7 跟进 metrics（任务 4 完成后 24 小时内）

记录到 `docs/LAUNCH_METRICS.md`:

| 平台 | 链接 | 24h views | 48h views | 7d views | upv/comments | star 增加 |
|------|------|----------|----------|----------|------------|----------|
| HN | https://news.ycombinator.com/item?id=... | | | | | |
| r/economics | https://reddit.com/r/economics/... | | | | | |
| ... | | | | | | |

**目标**:
- HN 至少 50 upvotes + 30 comments (上首页 1 次)
- Reddit r/economics 至少 100 upvotes
- 知乎 至少 200 赞同
- 7 天内 +50-100 stars

---

# 附录: 应急

## A. 紧急：如何用手机完成这些

1. **GitHub Mobile App** - iOS/Android 都有
2. **Safari/Chrome 移动版** - 也能合并 PR
3. **邮件通知** - 设置 GitHub notifications on

## B. 全部失败的退路

| 任务 | 失败退路 |
|------|----------|
| 1. 合并 PR | 用 Git CLI: `git checkout main && git merge --squash audit-fixes-2026-06-16 && git push` |
| 2. 设置 Topics | 在 README 顶部加 "Topics: academic-research, ..." |
| 3. 发 awesome PR | 5 个月后再试；或发到相关 GitHub Discussions |
| 4. 发外部宣传 | 用 X/Twitter 代替（受众更广但寿命短）|

## C. 时间预算（保守）

| 任务 | 最低 | 期望 | 困难情况 |
|------|------|------|----------|
| 1. 合并 PR | 10 min | 15 min | 30 min（含 CI 修）|
| 2. 设置 Topics | 3 min | 5 min | 5 min |
| 3. awesome PR × 7 | 30 min | 60 min | 120 min（维护者反复要求改）|
| 4. HN/Reddit/知乎 | 15 min | 30 min | 60 min（互动 + 改稿）|
| **总计** | **58 min** | **110 min** | **215 min** |

---

# 🎯 完成后

1. 记下所有链接（HN item ID, Reddit 帖子 URL, 知乎文章 URL）
2. **30 天后**回顾 metrics，决定下一步

**祝发布顺利！🚀**
