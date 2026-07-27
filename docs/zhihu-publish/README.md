# 知乎发布全流程指引 · FinResearch Agent v1.0

> **包名**：`docs/zhihu-publish/`
> **目标**：4 篇内容分阶段推送，引导 Star/Fork/Issue
> **核心指标**：首周 GitHub Star +10-30、Issue +2-5

---

## 一、文件结构速览

```
docs/zhihu-publish/
├── README.md                      ← 本文件（你是从这里开始）
├── PUBLISHING_PLAN.md             ← 完整 4 篇发布计划
├── IMAGE_GUIDE.md                 ← 配图插入位置指南（**新**）
├── articles/                      ← 4 篇文案（按时间顺序发布）
│   ├── 01_main_article.md         ← D1 周一：主文（约 4,500 字，已含 5 处配图标记）
│   ├── 02_followup_demo.md        ← D2 周二：真实演示
│   ├── 03_followup_qa.md          ← D4 周四：抢答问题
│   └── 04_followup_community.md   ← D7 周日：征集 issue
├── assets/                        ← 6 张专业配图（matplotlib 设计）
│   ├── cover.png                  ← 封面图（1200×630 知乎推荐）
│   ├── figure_00_overview.png     ← 数据快照仪表盘
│   ├── figure_01_health.png       ← 健康检查雷达图
│   ├── figure_02_mcp.png          ← 43 MCP 分布（饼图+条形图）
│   ├── figure_03_openssf.png      ← OpenSSF Gold 徽章
│   └── figure_04_journals.png     ← 88 期刊模板分布
├── tools/                         ← 配图生成工具
│   ├── gen_cover.py               ← 封面生成器
│   └── gen_figures.py             ← 5 张正文图生成器
├── checklists/                    ← 检查清单
│   ├── pre-publish.md             ← 发文前 24h 检查项
│   ├── post-publish.md            ← 发文后 24h 行动项
│   └── KPIs.md                    ← 关键指标追踪表
└── link-tracking/                 ← 链接追踪（占位，发文时创建）
```

---

## 二、3 步快速上手

### 第 1 步：D1 周一早上 8:30（发布前 1h）

```bash
# 1. 打开主文
open docs/zhihu-publish/articles/01_main_article.md

# 2. 打开配图素材
ls docs/zhihu-publish/assets/

# 3. 用工具脚本生成 PNG（可选）
python docs/zhihu-publish/tools/terminal_to_png.py
```

→ 打开知乎创作中心 → 写文章 → 复制主文 → 添加配图 → 添加封面 → 保存草稿

### 第 2 步：D1 周一 9:30（准时发布）

- 点击"发布"
- 关闭"同步到微博/微信"
- 立刻自己顶一条评论："求 Star 求 Fork"
- 设置 5 个闹钟（T+1h/3h/6h/12h/24h 互动提醒）

### 第 3 步：D2/D4/D7 跟进

打开 `articles/02_followup_demo.md` / `03_followup_qa.md` / `04_followup_community.md` 按各自的发布时间发布。

---

## 三、发布时间表（北京时间）

| 时间 | 阶段 | 内容 | 渠道 |
|------|------|------|------|
| D1 周一 9:30 | 主文 | 项目完整介绍 | 知乎专栏文章 |
| D2 周二 20:00 | 跟进 1 | 真实案例演示 | 知乎想法/短文 |
| D4 周四 12:00 | 跟进 2 | 抢答热门问题 | 知乎回答 |
| D7 周日 21:00 | 跟进 3 | 征集 issue | 知乎想法 |

> **为什么是这个节奏？**
> - D1 周一早 9:30：学术人群活跃时段，避开周一上午开会
> - D2 周二晚：第一次跟进，强化产品印象
> - D4 周四午：午饭时间刷知乎高峰
> - D7 周日晚：周末深度阅读，建立长期印象

---

## 四、关键 KPI

### 知乎侧

| 指标 | D1 目标 | D7 目标 |
|------|---------|---------|
| 主文阅读量 | 500 | 2,000 |
| 主文点赞 | 25 | 100 |
| 主文收藏 | 50 | 200 |
| 想法/回答互动 | 5 条评论 | 30 条评论 |

### GitHub 侧（核心引流目标）

| 指标 | D7 目标 | D30 目标 |
|------|---------|----------|
| Stars | +20 | +80 |
| Forks | +2 | +10 |
| Issues | +3 | +10 |
| 新 Contributors | +1 | +3 |

---

## 五、检查清单路径

| 阶段 | 检查清单 |
|------|----------|
| D1 发文前 24h | `checklists/pre-publish.md` |
| D1 发文后 24h | `checklists/post-publish.md` |
| 全程 KPI 追踪 | `checklists/KPIs.md` |

---

## 六、避坑（经验教训）

### ❌ 不要做

- 标题党（"震惊体"会降权重）
- 全文堆砌术语不说人话
- 不放 GitHub 链接
- 不强调"草稿需审阅"（误导用户）
- 跟评论区黑子对线（拉黑即可）
- 发完就不管了（一篇爆文靠持续运营）

### ✅ 要做

- 真实数据 + 真实截图
- 主动暴露局限
- 每条评论认真回复（< 100 字最佳）
- 持续发跟进内容
- 收到 Issue/PR 24h 内回复

---

## 七、紧急情况处理

| 情况 | 处理方式 |
|------|----------|
| 阅读量 < 100 | 检查是否违规词、是否被降权，必要时重新编辑 |
| 评论区被攻击 | 立刻锁评论区，不对线 |
| 工具在用户端报错 | 立刻在 GitHub Issue 跟踪，并在评论区公开进度 |
| 大 V 转发 | 24h 内深度评论互动（不要只说"谢谢"） |

---

## 八、资源索引

- **主文**：`articles/01_main_article.md`
- **跟进 1**：`articles/02_followup_demo.md`
- **跟进 2**：`articles/03_followup_qa.md`
- **跟进 3**：`articles/04_followup_community.md`
- **详细计划**：`PUBLISHING_PLAN.md`
- **配图素材**：`assets/`
- **配图工具**：`tools/terminal_to_png.py`
- **检查清单**：`checklists/`

---

## 九、下一步

1. **今天**：阅读 `articles/01_main_article.md`，确认文案无误
2. **明天（D1 周一 8:30）**：跑 `tools/terminal_to_png.py` 生成图片
3. **D1 周一 9:30**：发布主文
4. **D2/D4/D7**：按时间表发跟进内容

**现在开始第一步：复制主文到知乎草稿箱，开始排版。**
