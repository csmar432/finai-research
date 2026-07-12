# A 类手动任务详细清单 (MANUAL_TASKS_DETAILED_2026-07-12)

> **审计者**: FinResearch Agent
> **时间**: 2026-07-12 13:30 (UTC+8)
> **总时长**: ~3.5 小时 (5 大类, 9 子项)
> **关键**: 每项含 (a) 当前状态 (b) 待办步骤 (c) 阻塞原因 (d) 可自动化部分

---

## 📊 当前真实状态 (新发现, 修正之前 audit)

| 任务 | 之前以为 | 实际状态 |
|---|---|---|
| **PyPI 发布** | 待 token | ✅ **已完成** (v0.2.0a0, 2026-07-11) |
| **Zenodo DOI** | PENDING | ✅ **已分配**: 10.5281/zenodo.21262689 |
| **Social Preview** | 待上传 | ✅ **已生成**: `.github/social-preview.png` 1280×640 (60KB) |
| **GitHub Discussions** | 待启用 | ✅ **已启用** + 6 个分类 |
| **GitHub Topics** | 待设置 | ✅ **已设置 12 个** |
| **Demo GIF** | 待录制 | 🟡 SVG 已生成, GIF 待录 |

**修正**: 原 audit 误判 A4 (PyPI) 和 Zenodo 为待办. 现这两项已 completed.

---

## A1. 录制 Demo GIF (30-60 min)

**当前状态**: 🟡
- ✅ SVG 已生成: `docs/assets/demo-terminal.svg` (4.4KB, 95 行)
- ✅ PNG 已生成: `docs/assets/quickstart.png` (177KB)
- ❌ GIF 未生成: README 引用的 `.github/demo/demo.gif` 不存在

**待办步骤** (推荐方案 A, 纯脚本):

```bash
# 1. 安装 asciinema (终端录制) + agg (GIF 转换)
brew install asciinema
pip install agg

# 2. 录制 6-15 秒终端动画
asciinema rec .github/demo/demo.cast \
  --title "FinAI Research Workflow" \
  --command "python3 scripts/health_check.py && python3 scripts/count_assets.py"

# 3. 转 GIF (60KB)
agg .github/demo/demo.cast .github/demo/demo.gif --theme monokai --cols 100 --rows 30

# 4. 验证
file .github/demo/demo.gif
# 应输出: GIF image data, version 89a
ls -lh .github/demo/demo.gif
# 应 ≤ 200KB
sips -g pixelWidth -g pixelHeight .github/demo/demo.gif
# 宽度 ≤ 800px

# 5. 提交
git add .github/demo/demo.gif
git commit -m "feat(demo): record asciinema + agg GIF (6-15s, ≤200KB)"
```

**阻塞原因**: 无, 用户授权即可.
**可自动化部分**: 完全可脚本化 (无需 GUI).
**预估**: 10 min (录制 + 转码 + 验证 + commit).

---

## A2. 上传 GitHub Social Preview (5 min)

**当前状态**: ✅ 已生成, 🟡 待上传

| 字段 | 值 |
|---|---|
| 文件 | `.github/social-preview.png` |
| 尺寸 | 1280 × 640 (GitHub 要求) |
| 大小 | 60 KB |
| 修改时间 | 2026-07-12 12:52 |

**待办步骤**:

1. 打开 https://github.com/csmar432/finai-research/settings
2. 向下滚至 "Social preview" 部分
3. 点 "Upload an image..." → 选 `.github/social-preview.png`
4. 点 "Submit"

**阻塞原因**: GitHub API **不支持**上传 social preview, 必须 UI.
**可自动化部分**: 0% (完全 UI 操作).
**预估**: 2-3 min.

---

## A3. 社区 PR + 社媒 (2.5 小时, 9 子项)

### A3.1. Awesome List PR (60 min, 4 真待办)

**真实状态** (与原 audit 一致):

| # | 文件 | 仓库 | 状态 | 待办 |
|---|---|---|---|---|
| 1 | `PR-01-antontarasenko-awesome-economics.md` | antontarasenko/awesome-economics | WITHDRAWN | 跳过 |
| 2 | `PR-02-matteocourthoud-awesome-causal-inference.md` | matteocourthoud/awesome-causal-inference | **DRAFT** | 用户 web 提交 |
| 3 | `PR-03-wilsonfreitas-awesome-quant.md` | wilsonfreitas/awesome-quant | **DRAFT** | 用户 web 提交 |
| 4 | `PR-04-academic-awesome-datascience.md` | academic/awesome-datascience | **DRAFT** | 用户 web 提交 |
| 5 | `PR-05-emptymalei-awesome-research.md` | emptymalei/awesome-research | **DRAFT** | 用户 web 提交 |
| 6 | `PR-06-WITHDRAWN-wong2-awesome-mcp-servers.md` | wong2/awesome-mcp-servers | NOT SUBMITTABLE | 跳过 |
| 7 | `PR-07-DEFERRED-vinta-awesome-python.md` | vinta/awesome-python | DEFERRED | 延后 |

**通用流程 (每个 PR 5-10 min)**:
1. 打开对应 PR 草稿文件 → 复制 "PR Body" 段
2. 打开目标仓库 README → 点 ✏️ 编辑
3. 在合适章节粘贴新条目 (格式见文件)
4. 点 "Propose changes" → 填 PR 标题 → "Create pull request"

**阻塞原因**: 必须用户 web 浏览器操作.
**可自动化部分**: 0% (GitHub 主页编辑需要人工 review).
**预估**: 4 × 8 min = 32 min (DRAFT), 加 review = 60 min.

---

### A3.2. HN + Reddit (3 个 subreddit) (45 min)

| # | 文件 | 平台 | 文案就绪 | 待办 |
|---|---|---|---|---|
| 1 | `01-hackernews.md` | Hacker News (Show HN) | ✅ | 用户 web 提交 |
| 2 | `02-reddit-machinelearning.md` | r/MachineLearning | ✅ | 用户 web 提交 |
| 3 | `03-reddit-python.md` | r/Python | ✅ | 用户 web 提交 |

**最佳时间**: 周二/周三 8-10 AM EST (美东 9 PM 北京).

**HN 步骤**:
1. 打开 https://news.ycombinator.com/submit
2. 登录账号 (如无 → 注册, 用户名 `csmar432` 一致品牌)
3. 填表:
   - **Title**: `Show HN: I built an end-to-end AI research agent for economists`
   - **URL**: `https://github.com/csmar432/finai-research`
4. 点 Submit

**关键 HN 跟进规则**:
- ❌ 不要 vote begging
- ❌ 不要立即营销
- ✅ 前 4 小时回复所有评论
- ✅ 接受所有技术批评

**Reddit 步骤** (2 个 subreddit):
1. 打开 subreddit submit 页
2. 选 Flair (Tool / Project / Software)
3. 粘贴已备好的 body 文案
4. 不要 spam 其他 subreddit

**阻塞原因**: 需要账号登录 + 真人评论互动.
**可自动化部分**: 0% (Reddit 算法 + HN 规则明确禁止机器人).
**预估**: 3 × 10 min 提交 + 15 min 互动回复 = 45 min.

---

### A3.3. 中文社媒 (3 项, 60 min)

| # | 文件 | 平台 | 文案就绪 | 待办 |
|---|---|---|---|---|
| 1 | `04-zhihu.md` | 知乎专栏 + 短想法 | ✅ | 用户发布 + 调格式 |
| 2 | `05-weibo.md` | 微博 | ✅ | 用户发微博 |
| 3 | `06-x-com.md` | X.com (Twitter) | ✅ | 用户发推 |

**知乎步骤** (15 min):
1. 打开 https://zhuanlan.zhihu.com/write → 登录
2. 粘贴 Markdown 正文
3. **手动调整** (知乎编辑器不完美支持 MD):
   - 表格 → 重排
   - 代码块 → 检查渲染
   - 图片 → 手动上传到知乎
4. 存草稿 → 检查 → 发布
5. 同步到 topic: 经济金融学术圈 / 数量经济学 / 计量经济学
6. 发到朋友圈/微信群

**微博步骤** (5 min):
1. 打开 https://weibo.com → 登录
2. 粘贴短文 (含 GitHub 链接 + 2-3 关键能力)
3. 加话题标签 (#AI研究 #量化 #论文写作)
4. 发布

**X.com 步骤** (5 min):
1. 打开 https://x.com/compose/post → 登录
2. 粘贴推文 (≤ 280 字符, 含 GitHub 链接)
3. 加 2-3 个 hashtag (#AcademicAI #EmpiricalResearch)
4. 发布

**阻塞原因**: 中文平台账号 + 知乎编辑器格式调整.
**可自动化部分**: 0%.
**预估**: 知乎 30 min + 微博 5 min + X 5 min = 40 min + 格式调整缓冲 20 min = 60 min.

---

## A4. PyPI 发布 ✅ 已完成 (无需操作)

**实际状态** (2026-07-11 22:54 已发布):

| 字段 | 值 |
|---|---|
| Package | `finai-research-workflow` |
| Version | `0.2.0a0` |
| Upload time | 2026-07-11 14:54 UTC |
| Wheel | 2.5 MB (`finai_research_workflow-0.2.0a0-py3-none-any.whl`) |
| Sdist | 4.9 MB (`finai_research_workflow-0.2.0a0.tar.gz`) |
| Owner | `yi432` |
| URL | https://pypi.org/project/finai-research-workflow/0.2.0a0/ |

**验证方法**:
```bash
curl -s "https://pypi.org/pypi/finai-research-workflow/json" | python -c "import sys,json;d=json.load(sys.stdin)['info'];print(d['version'],d['upload_time'])"
# → 0.2.0a0 2026-07-11T14:54:14
```

**待办**: 0. 不需要任何操作.

---

## A5. Zenodo DOI ✅ 已完成 (无需操作)

**实际状态** (Zenodo 已存档并分配 DOI):

| 字段 | 值 |
|---|---|
| DOI | **10.5281/zenodo.21262689** |
| URL | https://doi.org/10.5281/zenodo.21262689 |
| Badge | README 中已有 `[![DOI]...]` 链接 |
| Source | `.zenodo.json` (已配置完整 metadata) |

**待办**: 0. 在 `docs/CITATION_GUIDE.md` 中可把 `10.5281/zenodo.PENDING` 替换为真实 DOI.

**可选优化** (5 min, 我可以代做):
- 修改 `docs/CITATION_GUIDE.md` §1 BibTeX, `doi = {10.5281/zenodo.PENDING}` → `doi = {10.5281/zenodo.21262689}`
- 修改 `.zenodo.json` 中描述里 `42 econometric methods` → `47 econometric methods`, `45 journal templates` → `30 journal templates` (其他数字已正确)
- 修改 README 中引用块的 DOI placeholder

---

## A6. mcpservers.org 收录 (15 min, 推荐先跳过)

**当前状态**: 🟡 待办 (low priority)

**背景**:
- 7 个 awesome list 中 PR-06 (wong2/awesome-mcp-servers) 被禁
- 该项目维护者明确说: "We do not accept PRs. Please submit your MCP on the website: https://mcpservers.org/submit"
- 因此 A6 是 PR-06 的替代方案

**待办步骤**:
1. 打开 https://mcpservers.org/submit → 注册账号
2. 填写项目信息:
   - 名称: `FinAI Research Workflow`
   - 描述: 43 MCP servers for economic/financial research
   - GitHub: `https://github.com/csmar432/finai-research`
   - License: MIT
3. 邮箱验证 (1 封邮件)
4. 等待收录 (1-7 天)

**阻塞原因**: 邮箱 + 真人 review.
**可自动化部分**: 0%.
**预估**: 15 min (5 提交 + 5 验证 + 5 等待).
**优先级**: 🟢 低 — 不影响 5 平台社媒效果.

---

## 📋 优先级建议 (本周末执行计划)

### 🟡 第一优先 (1 小时)
1. **A1** 录制 Demo GIF (10 min, 我可代写命令)
2. **A2** 上传 Social Preview (3 min)
3. **A5** 修正 CITATION_GUIDE.md 的 DOI placeholder (5 min, 我可代办)

**总**: 18 min, 含 auto 5 min.

### 🟡 第二优先 (1.5 小时)
4. **A3.1** 提交 4 个 awesome-list PR (32 min)
5. **A3.2** 发 HN + 2 个 Reddit (45 min)

**总**: 1 小时 17 分.

### 🟢 第三优先 (1 小时)
6. **A3.3** 发知乎 + 微博 + X.com (60 min)

**总**: 1 小时.

### 🟢 可选
7. **A6** mcpservers.org (15 min, 可跳过)

---

## 🎯 总结数字 (修正版)

| 任务 | 时长 | 阻塞 | 真实状态 |
|---|---|---|---|
| A1 Demo GIF | 10 min | 无 | 🟡 SVG 有, GIF 待录 |
| A2 Social Preview | 3 min | GitHub UI | 🟡 文件有, 待上传 |
| A3.1 Awesome PR (4) | 32 min | web 浏览器 | 🟡 DRAFT 就绪 |
| A3.2 HN + Reddit (3) | 45 min | 账号 + 互动 | 🟡 文案就绪 |
| A3.3 知乎/微博/X.com (3) | 60 min | 中文平台 | 🟡 文案就绪 |
| A4 PyPI | — | — | ✅ **已发布** |
| A5 Zenodo | — | — | ✅ **DOI 已分配** |
| A5 opt Zenodo 占位符 | 5 min | 无 | 🟡 CITATION_GUIDE 待改 |
| A6 mcpservers.org | 15 min | 邮箱 | 🟢 低优先 |

**待办总时长**: ~2.5 小时 (排除 A4/A5 已完成项, A6 可选).

---

## 🟢 我可以代做的部分 (无需用户操作)

1. ✅ **A5 自动修复**: 替换 `CITATION_GUIDE.md` 中 DOI placeholder → 真实 DOI
2. ✅ **A5 自动修复**: 同步 `.zenodo.json` 描述计数 (42 → 47, 45 → 30)
3. ✅ **A1 命令生成**: 输出完整 asciinema + agg 一键脚本 (复制粘贴即可执行)
4. ✅ **A3 文案润色**: 对现有 HN/Reddit/知乎文案做更精确的英文/中文版

---

**完整版报告**: 本文件, `docs/audit/MANUAL_TASKS_DETAILED_2026-07-12.md`