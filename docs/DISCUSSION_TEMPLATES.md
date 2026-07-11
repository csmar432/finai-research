# GitHub Discussions 模板与种子问题

> **审计来源**: `docs/audit/GITHUB_STAR_AUDIT_2026-07-09.md` §2.4
> **状态**: ✅ **已启用并配置**（2026-07-11 17:11 验证）
> **更新**: 2026-07-11

## 启用状态（已自动验证）

```
✅ has_discussions: true
✅ 6 个默认分类已就绪:
   • Announcements    (DIC_kwDOS7QcBc4C_QUG)
   • General         (DIC_kwDOS7QcBc4C_QUH)
   • Ideas           (DIC_kwDOS7QcBc4C_QUJ)
   • Polls           (DIC_kwDOS7QcBc4C_QUK)
   • Q&A             (DIC_kwDOS7QcBc4C_QUI)
   • Show and tell   (DIC_kwDOS7QcBc4C_QUK)
```

> ⚠️ **常见困惑**: 启用 Discussions 后，"Set up discussions" 按钮会**消失**，
> 改为在 Discussions 标签页右上角的 **"Edit categories"** 按钮管理分类。
> 这不是 bug，是 GitHub 在 2024 年改版后的新流程。

## 启用步骤（已完成，仅供参考）

1. 访问 https://github.com/csmar432/finai-research/settings
2. 向下滚动至 **Features** 部分
3. ✅ 勾选 **Discussions** ← 你已执行
4. ~~点击 "Set up discussions"~~ ← GitHub 2024+ 已移除此按钮
5. 现在管理分类：访问 https://github.com/csmar432/finai-research/discussions
   → 右上角 **⚙️** → **Edit categories**

---

## 推荐的分类（6 个）

### 1. 📣 Announcements
**用途**: 项目重大更新、版本发布、活动公告

### 2. 🙋 Q&A
**用途**: 用户提问、问题排查、使用咨询

### 3. 💡 Ideas
**用途**: 新功能建议、研究方向、新 MCP server 请求

### 4. 🎉 Show and tell
**用途**: 用户分享用 FinAI 产出的论文、研报、实验结果

### 5. 📚 Resources
**用途**: 教程、最佳实践、外部资源链接

### 6. 🛠️ Help wanted
**用途**: 寻找贡献者、悬赏任务、Bounty 任务

---

## 种子问题（首批 5 条）

### Q&A 1: 安装问题

**标题**: pip install 失败：ModuleNotFoundError: No module named 'paper_pipeline'

**正文**:
```
报错：
ModuleNotFoundError: No module named 'paper_pipeline'

环境：macOS 14.5, Python 3.12.3

执行命令：
$ pip install -e ".[dev]"
$ python scripts/start_research.py --topic "ESG financing"

期望：进入 idea-discovery 阶段
实际：报错如上

请问如何解决？
```

### Q&A 2: API Key 配置

**标题**: Tushare Token 在哪里配置？

**正文**:
```
我按照 README 设置 TUSHARE_TOKEN，但是仍然报错：
"Please configure TUSHARE_TOKEN in environment"

是否需要在 .env 文件中配置？还是 ~/.bashrc？
```

### Ideas 1: 论文投递支持

**标题**: 能否增加 arXiv 自动提交功能？

**正文**:
**问题**：当前需要手动将 finai.pdf 上传到 arXiv。

**建议**：在 `scripts/paper_submission.py` 中添加：
```python
python scripts/paper_submission.py \
  --paper papers/finai_methodology/finai.pdf \
  --category econ.EM \
  --auto-submit
```

**价值**：降低学者使用门槛，提升 arXiv 引用率。

### Show and tell 1: 用户案例

**标题**: 我用 FinAI 完成了一篇 DID 实证论文（附流程）

**正文**:
**主题**: 数字金融对企业创新的影响（2020-2024 A 股面板）

**流程**:
1. `start_research.py --topic "数字金融 创新"`
2. 引用了 12 篇文献（包括 Aghion et al. 2023）
3. DID 设计：treated = 试点城市企业
4. 用 `modern_did.py::CallawaySantAnnaEstimator`
5. 用 `robustness_runner.py::run_comprehensive("full")`
6. 写作 → 5 轮 AI review → 手动修改 → 投稿《经济研究》

**结论**: 基本无障碍，但 `data_fetcher` 在 Tushare 限流时会卡住。

### Help wanted 1: 文档贡献

**标题**: [悬赏] 编写 3 篇高 Star 项目的对比分析

**正文**:
**任务**: 在 `docs/benchmark/` 下编写 markdown，对比：
- `microsoft/autogen`（多代理）
- `anthropic/anthropic-cookbook`（LLM 应用）
- `crewai/crewai`（多代理协作）
- `csmar432/finai-research`（本研究）

**奖励**:
- 🎁 50 USD GitHub Sponsors credit
- 📜 写入 CONTRIBUTORS.md
- 🏷️ `help-wanted` + `good first issue` 标签

---

## 模板格式

仓库可创建以下 `.github/` 文件作为正式模板：

```
.github/
├── DISCUSSION_TEMPLATE/
│   ├── qa.yml          # Q&A 提问模板
│   ├── idea.yml        # Ideas 建议模板
│   ├── show-and-tell.yml
│   └── help-wanted.yml
```

### 示例：qa.yml

```yaml
name: Question
description: Ask the community a question about FinAI Research Workflow.
title: "[Question] "
labels: ["question"]
body:
  - type: textarea
    id: problem
    attributes:
      label: 问题描述
      description: 详细描述你遇到的问题
      placeholder: |
        报错信息：
        执行命令：
        期望结果：
        实际结果：
    validations:
      required: true
  - type: input
    id: env
    attributes:
      label: 环境信息
      placeholder: macOS 14.5, Python 3.12.3
    validations:
      required: true
  - type: dropdown
    id: component
    attributes:
      label: 受影响组件
      options:
        - scripts/research_framework/
        - scripts/agent_pipeline.py
        - MCP 服务器
        - LaTeX 生成
        - 其他
    validations:
      required: true
```

---

## 验证方法

启用后验证：
```bash
# 检查 Discussions 已启用
gh api repos/csmar432/finai-research --jq '.has_discussions'
# → true

# 检查分类（启用后 1-2 分钟可查询）
gh api graphql -f query='
{ repository(owner: "csmar432", name: "finai-research") {
    discussionCategories(first: 10) {
      nodes { name }
    }
  }
}'
```

---

**执行人**: 用户手动（GitHub 网页端），模板创建可由 Cursor 自动完成