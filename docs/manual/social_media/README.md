# HN / Reddit / 中文社媒 提交包

> **状态 (2026-07-12)**: 5/5 任务中, **1/5 可自动化 (已推 4 个 awesome-list PR), 1/5 已手动完成 (mcpservers.org)**.
> 剩余 3 项 (HN/Reddit/知乎/微博/X.com) **需要人工 web 提交** —
> 每个文件含完整可复制粘贴的文案 + 详细操作步骤。
>
> **2026-07-12 更新**:
> - mcpservers.org 已发布 (✅ HTTP 200, https://mcpservers.org/zh-CN/servers/csmar432/finai-research)
> - 文案润色 — 移除未确认的 PR 编号, 加入真实 PyPI/Zenodo 引用.

## 5 项任务总览

| # | 任务 | 类型 | 状态 |
|---|------|------|------|
| 1 | 5 个 awesome-list PR | **GitHub API** | ✅ 4 DRAFT + 2 WITHDRAWN/DEFERRED (见 `awesome_list_prs/PR-*.md`) |
| 2 | PyPI 发布 | **PyPI token 必需** | ✅ **已发布 v0.2.0a0** (2026-07-11) |
| 3 | mcpservers.org | **Web form + 邮件验证** | ✅ **已发布 (2026-07-12)** | https://mcpservers.org/zh-CN/servers/csmar432/finai-research |
| 4 | HN/Reddit | **Web form** | ⏸️ 需 web 提交 (文案备好) |
| 5 | 知乎/微博/X.com | **Web form + 登录** | ⏸️ 需 web 提交 (文案备好) |

## 文件清单

```
docs/manual/social_media/
├── README.md                      ← 本文件
├── 01-hackernews.md               ← HN "Show HN" 提交
├── 02-reddit-machinelearning.md   ← r/MachineLearning 提交
├── 03-reddit-python.md            ← r/Python 提交
├── 04-zhihu.md                    ← 知乎专栏文章 + 短想法
├── 05-weibo.md                    ← 微博
└── 06-x-com.md                    ← X.com (Twitter)
```

## 通用文案原则

每篇都遵循以下约束（避免被拒/被喷）：

1. **No marketing language** — 不写 "revolutionary"、"amazing"、"best"。
2. **AI disclaimer 必含** — 强调 AI 生成的所有统计结果/引用必须人工复核。
3. **具体数字** — 43 个 MCP / 47 个方法 / 30 个期刊 / 17 个 skill / 13 个方向。
4. **Issue link 公开** — 公开 GitHub 仓库 + 4 个 PR 链接 (作为 social proof)。
5. **CC0/MIT 协议** — 强调开源。

## 时区策略

| 平台 | 最佳时间 (美东 ET) | 北京时间 | 周几最优 |
|------|---------------------|----------|----------|
| HackerNews | 8-10 AM | 20-22 点 | 周二-周四 |
| Reddit ML | 8-10 AM | 20-22 点 | 周二-周四 |
| Reddit Python | 8-10 AM | 20-22 点 | 周二-周四 |
| 知乎 | 9-11 AM / 21-23 点 | 同 | 周一-周三 |
| 微博 | 12-14 PM / 21-23 点 | 同 | 任意 |
| X.com | 9 AM / 3 PM ET | 21 点 / 3 AM | 周二-周四 |

## AI Disclaimer (每篇必含)

```
⚠️ 所有 AI 生成的回归结果和引用必须由研究者复核后投稿。
本工具通过 HITL gates 强制人工确认，但并不能消除研究者责任。
```

English version:
```
⚠️ All AI-generated regression results and citations MUST be
verified by the human researcher before submission.
The tool enforces HITL gates but does not eliminate
this responsibility.
```

## 提交顺序建议

1. **HN Show HN** — 流量最大、可能上首页 (>200 upvote)
2. **Reddit r/MachineLearning** — 技术受众
3. **Reddit r/Python** — 工具受众
4. **知乎专栏** — 中文研究者社区
5. **微博** — 短形式传播
6. **X.com** — 国际化传播

每两个之间间隔 ≥ 2 小时，避免被识别为 spam。

## 自动提交状态

✅ **已完成** (本会话):

- 4 个 GitHub PR 已开 (matteocourthoud / wilsonfreitas / academic / emptymalei)
- PR 链接已写入 `docs/manual/social_media/README.md` 顶部 (见下)
- PyPI 包已构建 (`dist/finai_research_workflow-0.2.0a0-py3-none-any.whl`)
- mcpservers.org 已发布: https://mcpservers.org/zh-CN/servers/csmar432/finai-research (HTTP 200, 2026-07-12)

❌ **无法自动完成** (需人工):

- HN/Reddit/知乎/微博/X.com — 平台防 spam，不开放自动 post API
- PyPI 上传 — 需 PyPI token (你可在 https://pypi.org/account/register/ 注册)

## 引用的 4 个 PR 链接 + mcpservers.org (用于文案)

```
https://github.com/matteocourthoud/awesome-causal-inference/pull/14
https://github.com/wilsonfreitas/awesome-quant/pull/468
https://github.com/academic/awesome-datascience/pull/654
https://github.com/emptymalei/awesome-research/pull/111
https://mcpservers.org/zh-CN/servers/csmar432/finai-research   # 已发布 2026-07-12
```
