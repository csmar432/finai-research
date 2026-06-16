# 🎯 个人品牌 + 邮箱修复完整指南

> 这是基于专业评估的**逐步操作手册**。每一步都有"为什么"和"怎么做"。
> **完成时间**: 30-45 分钟

---

## 📊 评估总览 (4 个问题)

| # | 问题 | 等级 | 我能否改 | 是否必做 |
|---|---|---|---|---|
| **A** | 邮箱 .local 域名, GitHub 无法验证 | 🔴 P0 | ✅ 立即改 | **必须** |
| **B** | 用户名 csmar432 品牌风险 | 🟠 P1 | ❌ 改不了 | **决策** |
| **C** | 仓库 Display Name 是中文 | 🟡 P2 | ⚠️ 部分 | **推荐** |
| **D** | Profile README 缺失 | 🟡 P2 | ✅ 立即写 | **推荐** |

---

# 🔴 A. 邮箱修复 (必修, 15 min)

## 为什么要修

```
你的 commit 邮箱: xuzheyi@yiMac-Air.local
                   └─ .local = macOS 本地 mDNS, 互联网不可达
                   
后果:
  1. GitHub 无法发送验证邮件 → email status = unverified
  2. 你的 commit 不计入 contribution graph → 绿点不亮
  3. 协作者/雇主看不到你的工作量
  4. 影响 GitHub Pro / Student Developer Pack 申请
```

## Step 1: 在 GitHub 找到你的 noreply 邮箱 (2 min)

**操作**:
1. 浏览器打开 https://github.com/settings/emails
2. 找到这一行 (在最下面):
   ```
   "Don't show my email address publicly. I'll use [12345+csmar432]@users.noreply.github.com when performing web-based Git operations."
   ```
3. 复制 `12345+csmar432` (这是你的 GitHub user ID 数字,具体数字因账号而异)
4. 完整 noreply 邮箱: `12345+csmar432@users.noreply.github.com`

**验证**: 完整格式: `数字+csmar432@users.noreply.github.com`

> ⚠️ 你的数字可能不是 12345, 是你在 GitHub 注册时被分配的 ID。
> 如果找不到, 可以访问 https://api.github.com/users/csmar432 看 `id` 字段。

## Step 2: 决定显示姓名 (1 min)

**问题**: 你的真实姓名 "许哲逸" 现在出现在每条 commit 里。

| 选项 | 利弊 |
|---|---|
| **保留 "许哲逸"** | 国内学者容易识别你, 但也暴露身份 |
| **改 "Xu Zheyí"** | 中性国际化, 但认识你的人知道是你 |
| **改 "X. Z."** | 学术圈常见缩写, 足够识别 |
| **改 "csmar432"** | 完全匿名, 跟用户名一致 |

**推荐**: **`Xu Zheyí`** —— 学术圈标准, 拼写一致 (拼音 + 声调), 国际化。

## Step 3: 运行修复脚本 (1 min)

```bash
cd $REPO_ROOT

# 1. 干跑 (不改任何东西, 预览效果)
python scripts/fix_git_authorship.py \
  --new-email "12345+csmar432@users.noreply.github.com" \
  --new-name "Xu Zheyí" \
  --dry-run

# 2. 实际执行 (会要求你输入 "yes" 确认)
python scripts/fix_git_authorship.py \
  --new-email "12345+csmar432@users.noreply.github.com" \
  --new-name "Xu Zheyí"
```

**脚本会**:
- 用 `git filter-branch` 重写所有 15 个 commit
- 改 author name + email + committer name + email
- 打印验证步骤

## Step 4: 推送到 GitHub (1 min)

⚠️ **重要**: 如果仓库已 push, 需要 `git push -f` 强制覆盖!

```bash
# 验证本地是否修改成功
git log --all --format='%an <%ae>' | sort -u
# 应该看到: Xu Zheyí <12345+csmar432@users.noreply.github.com>

# 检查 remote
git remote -v
# 应该是: https://github.com/csmar432/finai-research-workflow.git

# ⚠️ 强制推送 (会覆盖远端历史, 其他人需重新 clone)
git push -f origin main

# 推送 tag (如果有)
git push -f origin --tags
```

## Step 5: 验证 GitHub 端 (5 min)

1. 打开 https://github.com/csmar432/finai-research-workflow/commits/main
2. 检查最新 commit 应该显示 "Xu Zheyí" 而不是 "许哲逸"
3. **关键**: 打开 https://github.com/csmar432 主页, 看 contribution graph
4. **重点**: 仓库首页 → Insights → Contributors → 你的名字应该出现
5. Settings → Emails: "xuzheyi@yiMac-Air.local" 标记为 unverified (正常)
6. Settings → Emails: 新 noreply 邮箱应该自动加入 (来自 commit author)

## Step 6: 在 GitHub UI 启用 noreply 邮箱 (2 min)

1. 打开 https://github.com/settings/emails
2. ✅ 勾选 "Keep my email addresses private"
3. ✅ 勾选 "Block commits that expose my email"
4. 这样未来 commit 不会被强制用真实邮箱

---

# 🟠 B. 用户名 csmar432 品牌风险 (决策, 5 min)

## 评估

```
用户名: csmar432
       └── csmar = 国泰安 (CSMAR, 中文学术圈最常用的金融数据库)
       
潜在问题:
  • 陌生人可能以为你是国泰安官方
  • SEO 抢注嫌疑
  • 与"经济金融研究"方向契合但辨识度低

潜在优势:
  • 国泰安用户群(国内金融学术圈)会联想到你
  • 简短, 易记
  • 已建立历史, 改名代价大
```

## 选项

| 选项 | 决定 | 适用场景 |
|---|---|---|
| **保持 csmar432** | 不动 | 品牌已建立, 接受潜在误解 |
| **新用户名 + 迁移** | 创建新号, 标记旧号 "moved to @new" | 长期专业发展 |
| **新用户名 + 弃用** | 旧号冻结, 新号做主力 | 完全重新开始 |

## GitHub 限制

⚠️ **GitHub 用户名一旦注册, 不能修改** (只能删除重建)。
⚠️ 改名的链接全失效: 旧仓库链接 / Star / Issue 引用。

## 我的建议 (不强制)

**短期**: 保持 csmar432, 在 Bio 中澄清身份。
**长期** (1-2 年后): 如果项目影响力扩大, 考虑:
- 注册新用户名 (如 `xuzheyi`, `xzy-research`, `xzy-finance`)
- 在旧号 bio 写 "Brand evolved to @new_username"
- 项目迁移用 GitHub redirects

## 立即能做

1. https://github.com/csmar432 → Edit profile
2. Bio 字段添加:
   ```
   📊 经济金融 AI 学术研究 · 与国泰安 (CSMAR) 无关 · 自有项目
   ```
3. 链接 https://github.com/settings/profile
4. 设置 Location: `中国` 或 `Shanghai, China`
5. 链接个人网站 (可选, 用 GitHub Pages)

---

# 🟡 C. 仓库 Display Name (1 min)

## 当前 vs 建议

| 字段 | 当前 | 建议 |
|---|---|---|
| Repository name (slug) | `finai-research-workflow` | ✅ 保持 |
| **Display Name** | 论文-研报工作流 | **FinAI Research Workflow** |
| Description | 已有 | ✅ 保持 |

## 怎么改

⚠️ GitHub 仓库的 **Display Name** 实际上是仓库的 Title, 在仓库顶部大标题位置。

**操作**:
1. 打开 https://github.com/csmar432/finai-research-workflow
2. 仓库标题 "论文-研报工作流" 旁边有 ✏️ Edit 按钮
3. 改为: `FinAI Research Workflow`
4. Save

**效果**:
- 仓库顶部标题变成英文
- Notifications / Watch 显示英文
- 改善英文 SEO

---

# 🟡 D. Profile README (推荐, 10 min)

## 是什么

在 `csmar432/csmar432` 仓库 (与自己用户名同名) 创建 `README.md`,
会**自动显示在 GitHub 个人主页**。

## 步骤

1. 打开 https://github.com/new
2. **Repository name**: `csmar432` (必须与用户名完全一致)
3. **Description**: `My GitHub profile README`
4. **Public** (必须公开)
5. **Add a README file** ✅
6. Create repository
7. **复制内容**: `cat PROFILE_README.md` 的内容粘贴到新仓库的 README.md
8. Commit

## 验证

打开 https://github.com/csmar432, 看到个人简介 + Pin 仓库 + 统计。

---

# ✅ 总操作时间表

| 时间 | 任务 | 状态 |
|---|---|---|
| 0:00 | A.1 找到 noreply 邮箱 | ☐ |
| 0:02 | A.2 决定新姓名 | ☐ |
| 0:03 | A.3 跑修复脚本 (干跑) | ☐ |
| 0:05 | A.3 实际运行 | ☐ |
| 0:06 | A.4 推送 (git push -f) | ☐ |
| 0:08 | A.5 验证 GitHub 端 | ☐ |
| 0:13 | A.6 启用 noreply | ☐ |
| 0:15 | **A 完成** | ☐ |
| 0:16 | B.1 决定用户名策略 | ☐ |
| 0:18 | B.2 更新 Bio (如需要) | ☐ |
| 0:20 | **B 完成** | ☐ |
| 0:21 | C.1 改仓库 Display Name | ☐ |
| 0:22 | **C 完成** | ☐ |
| 0:23 | D.1 创建 csmar432 仓库 | ☐ |
| 0:25 | D.2 粘贴 PROFILE_README.md | ☐ |
| 0:27 | D.3 Pin 仓库 | ☐ |
| 0:30 | **D 完成** | ☐ |
| **0:30** | **🎉 全部完成** | ☐ |

---

# 🎯 给"许哲逸" 的具体建议

| 你的情况 | 我的建议 |
|---|---|
| **学术圈** (在读 PhD / 老师) | **保留真名** "Xu Zheyí", 增强专业度, 利于合作 |
| **工业界 + 副业** | 改 "Xu Zheyí" 也行, 风险是雇主可能搜到 |
| **完全匿名** | 改 "csmar432" 作为 author name, 不暴露真名 |
| **混合** | author name = "Xu Zheyí", 但 GitHub profile 不放真名 |

## 学术 vs 工业界的不同建议

### 如果你是 PhD 在读/老师 (学术圈)
```
✅ 推荐 author name: Xu Zheyí
✅ 推荐 profile 显示: 完整姓名 + 学术方向
✅ 推荐 commit 频率: 高 (绿点很重要)
✅ 推荐仓库描述: 学术、严谨、可复现
```

### 如果你在工业界 + 副业开源
```
✅ 推荐 author name: Xu Zheyí (但不强求)
✅ 推荐 profile 显示: 职位 + 兴趣方向, 不放公司名
✅ 推荐 commit 频率: 周末 (绿点稀疏可接受)
✅ 推荐仓库描述: 工具化、工程化
```

---

# 🆘 常见问题

### Q1: git push -f 后, 之前的 PR / Issue 还存在吗?

**A**: ✅ 存在, PR/Issue 不在 commit history 里, 它们是 GitHub 的独立对象。
只是 PR 中指向的 commit hash 会变, 显示 "(force-pushed)"。

### Q2: 能不能不重写历史, 只是在 GitHub UI 改 display name?

**A**: GitHub UI 的 display name 和 commit author 是两件事。
- UI display name: 影响仓库标题、Issue 显示
- commit author: 影响绿点、贡献图、API

两者**必须都改**才能让绿点亮。

### Q3: 我只有 15 个 commit, 直接 `git commit --amend` 行不行?

**A**: ❌ 不行, `--amend` 只改最新一个。
需要 `git filter-branch` 或 `git rebase --root` (更复杂)。

### Q4: 邮箱 .local 还能用吗?

**A**: macOS 本地 git 操作仍可用 (.local 在本机可解析)。
但 GitHub 完全无法验证。
**结论**: 必须改。

### Q5: 改完后, 我之前的 PR 还能看到原作者吗?

**A**: ⚠️ GitHub 会自动更新 PR 中的 commit 作者。
如果你的 `csmar432` 账号是唯一 contributor, 没问题。
如果其他人有 commit, 他们的信息不受影响。

---

# ✅ 完成检查

- [ ] A.1 找到 noreply 邮箱 (数字 ID)
- [ ] A.2 决定新姓名
- [ ] A.3 跑修复脚本
- [ ] A.4 推送 (-f)
- [ ] A.5 GitHub contribution graph 亮起
- [ ] A.6 启用 "Keep email private"
- [ ] B.1 用户名策略决策
- [ ] B.2 Bio 更新 (可选)
- [ ] C.1 仓库 Display Name 改英文
- [ ] D.1 创建 csmar432 仓库
- [ ] D.2 粘贴 Profile README
- [ ] D.3 Pin 仓库

**全部勾选后, 你的 GitHub 形象 100% 完整!**

---

# 📞 需要帮助?

每个步骤都有详细的 "操作 + 验证 + 故障排除"。  
任何一步卡住, 重新读对应章节即可。

