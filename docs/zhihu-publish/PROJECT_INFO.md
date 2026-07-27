# 知乎发布项目说明 · FinResearch Agent

## GitHub 项目描述（一句话）

> **End-to-end AI research pipeline for economics & finance: 43 data sources · 47 causal inference methods · 30 journal templates · from idea to submission-ready LaTeX draft.**

（GitHub Repo Settings → 填入 Description + Topics 即可）

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
FinResearch Agent 是一个端到端 AI 研究工作流，专为经济金融学者设计。

核心功能：
• 43 个数据源（A 股 / 美股 / 宏观 / 学术文献）
• 47 种因果识别方法（DID / IV / RDD / PSM / GMM / 合成控制等）
• 30 个期刊模板（JF / JFE / RFS / 经济研究 / 金融研究等）
• 8 步研究流水线，每步强制人工确认
• 完整数据溯源（provenance tracking）

快速开始：
  pip install "finai-research-workflow[extras]"
  finai-pipeline --topic "碳排放权交易对企业绿色创新的影响"

⚠️ AI 生成的草稿必须经研究者审阅后方可投稿。
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
