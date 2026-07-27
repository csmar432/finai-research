# 知乎发布项目说明 · FinResearch Agent

## GitHub 项目描述（一句话，学术化中文）

> **面向经济金融领域的端到端 AI 学术研究工作流，集成多源数据获取、因果推断与可投稿论文自动生成，加速研究者从想法到草稿的全流程。**

---

## GitHub Topics（选填，推荐）

```
ai-agent
academic-research
economics
finance
causal-inference
did
machine-learning
latex
python
research-tool
```

---

## 知乎文章题目（供上传参考）

```
用 6 个月做了个开源项目：让 AI 帮你跑完 43 类实证模型、生成可投稿的 LaTeX 论文草稿
```

---

## 知乎文章副标题 / 摘要（发布时用）

> **"告诉我研究主题，我帮你从文献综述 → 实证设计 → 数据获取 → 论文草稿 → LaTeX 编译。"**
>
> ⚠️ AI 草稿必须经研究者审阅后投稿——AI 不替代作者，只加速流程。

---

## 封面图

路径：`docs/zhihu-publish/assets/avatar.png`

- 尺寸：400×400 px（GitHub 头像推荐比例）
- 风格：深色科技感 + 8 步流水线节点
- 核心数据：43 数据源 / 47 因果方法 / 30 期刊模板
- 可直接作为 GitHub Organization 头像

生成脚本：`docs/zhihu-publish/tools/gen_avatar.py`
如需调整尺寸，修改 `create_avatar()` 中的 `figsize=(4, 4)` 和 `dpi=100`。

---

## 项目说明（GitHub Repo 页面）

（可直接粘贴到 GitHub → Repo Settings → "About" 框）

```
FinResearch Agent 是一个面向经济金融领域的端到端 AI 学术研究工作流，旨在将研究者从文献检索、数据获取、实证分析与论文排版的重复劳动中解放出来，使其将精力集中于 idea 生成与识别策略设计等核心工作。该工作流集成了 43 个数据源服务器，覆盖 A 股、美股、全球宏观与学术文献等主要数据类型；实现了 47 种因果推断方法，包括标准双重差分、Bacon 分解、Callaway-Sant'Anna (2021)、工具变量法、断点回归、面板门槛模型、合成控制与合成双重差分等主流及前沿计量方法；支持 JF、JFE、RFS 等英文顶刊与《经济研究》《金融研究》等中文顶刊的 LaTeX 模板，可直接输出符合投稿规范的论文草稿。整个流程包含 8 个标准化阶段，每阶段设置强制人工确认点（Human-in-the-Loop），确保研究者始终把控研究方向；同时内置完整的数据溯源模块，每次数据获取均记录来源、时间戳与 API 版本，杜绝静默造数。研究者以一句话描述研究方向，即可启动完整流水线，依次完成文献综述、研究想法生成、新颖性验证、实证设计、数据获取、回归分析与论文写作。⚠️ AI 生成的草稿必须经研究者独立审阅后方可投稿，工具定位为加速研究流程而非替代研究者本人。

快速开始：
  pip install "finai-research-workflow[extras]"
  finai-pipeline --topic "碳排放权交易对企业绿色创新的影响"

License: MIT | Python 3.10+
```

---

## 知乎文章内容大纲

详见 `docs/zhihu-publish/articles/01_main_article.md`

建议配图（已有素材）：
- `assets/cover.png` — 封面图（1200×630）
- `assets/figure_00_overview.png` — 数据快照
- `assets/figure_01_health.png` — 健康检查雷达图
- `assets/figure_02_mcp.png` — 43 MCP 分布
- `assets/figure_03_openssf.png` — OpenSSF Gold 认证
- `assets/figure_04_journals.png` — 期刊模板分布

---

## 发布检查

- [ ] GitHub Description 已填入（英文，一句话）
- [ ] GitHub Topics 已设置（6-8 个）
- [ ] 知乎文章标题确认
- [ ] 封面图已上传（avatar.png）
- [ ] 主文配图已确认（6 张）
- [ ] GitHub 链接已添加（每张图下方）
- [ ] AI 局限性声明已包含
- [ ] 检查清单已过一遍（`checklists/pre-publish.md`）
