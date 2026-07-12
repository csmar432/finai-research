# 知乎专栏文章 + 短想法

> **目标 URL**: https://zhuanlan.zhihu.com/write (专栏文章)
> **短想法**: https://www.zhihu.com/pin (想法)
> **最佳时间**: 周一-周三 9-11 AM 或 21-23 点

---

## A. 知乎专栏文章（完整版）

### 标题

```
从研究想法到投稿论文：经济金融研究者的一站式工作流（开源）
```

### 正文

```markdown
作为经济金融研究者，你是否还在为以下问题头疼：
- 找一篇好论文翻遍 5 个数据库（Google Scholar / Semantic Scholar /
  OpenAlex / ArXiv / CNKI）
- 想做 DID 但不知道哪个版本最稳健（Callaway-Sant'Anna vs
  Sun-Abraham vs Borusyak）
- 写完论文调 LaTeX 编译错误调到崩溃
- 投稿前自查不全面被 desk-reject

[FinAI Research Workflow](https://github.com/csmar432/finai-research)
尝试用一个命令解决以上所有问题。

## 一、核心特性（不堆砌数字）

**1. 43 个 MCP 数据源**

A股财务（Tushare/akshare）、美股（yfinance）、宏观
（FRED/IMF/World Bank）、学术论文（OpenAlex 4 亿+ / ArXiv）。
**28 个无需 API Key**，开箱即用。这是目前中文社区里唯一一个把
"所有数据源协议统一到 MCP"的工作流。

**2. 47 种计量方法**

标准 DID、3 种交错 DID 修正（Callaway-Sant'Anna, Sun-Abraham,
Borusyak）、IV、面板 GMM、合成控制、面板分位数、空间回归、
局部投影 DID。JF/JFE/RFS 标准的稳健性检验全部自动化（19 类）。

**3. 30 种期刊模板**

JF / JFE / RFS / Econometrica / 经济研究 / 金融研究 / 管理世界 /
会计研究 / 中国工业经济。**每种期刊都有独立的 bibliography 格式和
章节结构**。

**4. 17 个 AI Skill + 8 步流水线 + HITL 闸门**

想法 → 文献 → 新颖性 → 设计 → 数据 → 分析 → 写作 → AI review，
**每步需研究者确认**。AI 自动伪造的结果进不到投稿草稿。

**5. 透明 AI Review**

3 个 LLM（GPT-4o + Claude + Gemini）多轮对抗性 review，明确标注
⚠️ AI REVIEW 区域。最终投稿前研究者必须逐字复核。

## 二、实战案例（10 分钟看完）

输入：`碳排放权交易对企业绿色创新的影响`

输出：
- 候选 idea × 12（按新颖性 + 可行性排序）
- 引文网络（OpenAlex ~30 篇 Top-3 相关）
- 实证设计（DID + 现代 CS 修正 + 平行趋势 + 19 类稳健性）
- 数据获取脚本（CSMAR/专利数据）
- LaTeX 草稿（按经济研究模板）

## 三、为什么不是 SaaS？

empirical economics 圈子小众到根本撑不起 SaaS 估值。
我们的判断：工作流本身就是价值，数据 / 模型都是开源 commodity。
所以 MIT 协议，永久免费。

## 四、开源与免责

- **GitHub**: https://github.com/csmar432/finai-research
- **协议**: MIT
- **Zenodo DOI**: 10.5281/zenodo.21262689
- **MCP 目录**: https://mcpservers.org/zh-CN/servers/csmar432/finai-research (2026-07-12 已发布)
- **arXiv**: 即将提交
- ⚠️ 所有 AI 生成的因果识别 / 统计结果 / 引用必须由研究者复核后投稿

## 五、上游社区接受度

项目发布 1 周内，已经向 4 个 awesome-list 提了 PR（均已被 bot
接受并等待维护者审核）：

- https://github.com/matteocourthoud/awesome-causal-inference/pull/14
- https://github.com/wilsonfreitas/awesome-quant/pull/468
- https://github.com/academic/awesome-datascience/pull/654
- https://github.com/emptymalei/awesome-research/pull/111

## 六、试用

\`\`\`bash
git clone https://github.com/csmar432/finai-research
cd finai-research
pip install -e ".[dev]"
export DEEPSEEK_API_KEY=sk-xxxx  # 申请: https://platform.deepseek.com
python scripts/cli.py pipeline --topic "你的研究主题"
\`\`\`

仓库：https://github.com/csmar432/finai-research

如果对某个具体模块（如 CS-DID 实现、LaTeX 模板定制）感兴趣，
评论区告诉我，下一篇深度讲解。
```

### 提交步骤

1. 打开 https://zhuanlan.zhihu.com/write
2. 登录知乎账号
3. 复制上面的标题到 "标题" 字段
4. 复制正文到 "正文" 编辑器 (支持 Markdown)
5. 添加封面图（可选）：用项目 README 中的 architecture-diagram.svg
6. 点击 "发布"
7. 选择话题：
   - #计量经济学 #DID #LaTeX #开放源代码
   - #实证研究 #金融研究 #经济研究
8. 点击 "发布"

### 知乎话题建议

最匹配的知乎话题：
- 计量经济学
- 实证研究
- LaTeX
- 学术论文写作
- 经济金融研究方法
- 开源软件

---

## B. 知乎短想法（同步发，140 字以内）

```
花了 60 天把经济金融研究的 8 个步骤从想法 → 投稿 LaTeX 全部自动化了：

43 个 MCP 数据源（28 个无需 Key）
47 种计量方法（含 3 种现代交错 DID 修正）
30 种期刊模板（JF/经济研究/金融研究/管理世界...）
HITL 闸门防 AI 伪造

⚠️ AI 生成的所有统计结果/引用必须人工复核

仓库：https://github.com/csmar432/finai-research
```

### 提交步骤

1. 打开 https://www.zhihu.com/pin
2. 登录
3. 点击右上的 ✏️ 发想法按钮
4. 粘贴短想法文本
5. 添加 1-3 张图（可选）：项目 README 中的 demo.gif 或
   architecture-diagram.svg
6. 发布

---

## C. 知乎回答 / 文章回复策略

发布专栏后，主动回答 5-10 个高关注度问题（已存在的），并在
答案末尾加一行：

```
我最近做了一个开源工具 FinAI Research Workflow 把这个流程完整
自动化了，欢迎试用：https://github.com/csmar432/finai-research
```

候选问题：
- "如何学习 DID（双重差分）？" (关注度 5k+)
- "如何高效阅读经济学论文？"
- "Stata 和 R 哪个更适合计量经济学？"
- "有哪些 Python 工具可以做实证研究？"

⚠️ **不要**每条答案都推销 — 知乎算法会识别为 spam。
每 5-7 条真实回答中插 1 条带工具链接的即可。

---

## 提交后监测

知乎专栏文章 URL 格式：
```
https://zhuanlan.zhihu.com/p/XXXXXX
```

提交后填 README.md "提交状态" 段。
