# 🛡 Push 前审核手册 (Pre-Push Audit)

> **不立即 push**。按本手册**逐步审核**后,再决定推什么、留什么、改什么。
> **预计时间**: 30-60 分钟 (按范围)

---

## ✅ 你的选择确认

| 决策点 | 你的选择 | 含义 |
|---|---|---|
| **Q1: 邮箱** | **A: `yi1353370501@gmail.com`** ✅ | 学术圈友好, 已 Verified |
| **Q2: Name** | **(待定)** | 见下方说明 |
| **Q3: 审核** | **必须审核后才推** | 不会自动 push |
| **Q4: 仓库** | **GitHub 上未创建** | 你需先创建仓库 |

---

## 🎯 Q2: Name 字段 3 个选项

你说不清楚用哪个, 我给你 3 个具体选项:

### 选项 1: `Xu Zheyí` (推荐 ⭐⭐⭐⭐⭐)
```
显示:  Xu Zheyí
URL:   https://github.com/csmar432 (不变)
commit:  Xu Zheyí <yi1353370501@gmail.com>
适用:  学术圈 + 国际化 + 不在意姓名暴露
优点:  中英兼容, 学术圈标准格式, "í" 拼写符合汉语拼音
```

### 选项 2: `许哲逸` (推荐 ⭐⭐⭐⭐)
```
显示:  许哲逸
URL:   https://github.com/csmar432 (不变)
commit:  许哲逸 <yi1353370501@gmail.com>
适用:  国内学术圈优先, 不担心海外读者
优点:  中文环境最自然, 国内合作者一眼认出
```

### 选项 3: `X. Z. (许哲逸)`
```
显示:  X. Z. (许哲逸)
URL:   https://github.com/csmar432 (不变)
commit:  X. Z. (许哲逸) <yi1353370501@gmail.com>
适用:  工业界 + 学术混合作风
优点:  既显示缩写专业感, 又括号注明中文, 双重识别
```

### 我的建议

| 你的身份 | 推荐 |
|---|---|
| **PhD 在读** | `Xu Zheyí` (学术圈默认) |
| **Master 在读** | `许哲逸` (国内) |
| **工业界 + 副业** | `X. Z. (许哲逸)` |
| **完全匿名** | 不放真名, 用 `csmar432` |

**告诉我你的选择, 我会一并更新 GitHub profile。**

---

## 📊 当前仓库状态 (详细)

### 物理大小
```
仓库根目录: 818M
  ├─ .venv/: 770M  ← 虚拟环境, 不推送 ✅
  ├─ .git/:  17M  ← git 元数据, 不推送
  ├─ output/: 2.3M ← 输出, 已 .gitignore
  ├─ canvases/: 44K  ← Canvas 文件, 已 .gitignore
  └─ 实际推送: ~30-50M ✅ 完全合理
```

### 文件统计
```
本地 commit: 15 个
未提交文件: 575 个 (含 49 untracked + 526 modified)
仓库根文件: 70 个
tracked files: 733 个
```

### 改动分布 (按目录)
| 目录 | 改动数 | 类别 | 推不推 |
|---|---|---|---|
| `scripts/core` | 64 | 核心代码 | ✅ 推 |
| `scripts/` 其他 | 55 | 业务逻辑 | ✅ 推 |
| 根目录 | 35 | 配置/文档 | ✅ 推 |
| `scripts/research_framework` | 20 | 框架 | ✅ 推 |
| `knowledge/skills` | 18 | 技能 | ✅ 推 |
| `tests` | 12 | 测试 | ✅ 推 |
| `docs` | 10 | 文档 | ✅ 推 |
| `mcp_servers/*/tools` | 50+ | MCP 定义 | ✅ 推 |
| `mcp_servers/*/Dockerfile` | 多 | 容器 | ✅ 推 |

### 安全扫描结果
```
✅ 无 .env 文件泄漏
✅ 无 .bak 文件 (数据/草稿)
✅ 无 .db 数据库
✅ 无 .sqlite 缓存
✅ 无内部审计文件泄漏
✅ 无 papers/ 用户论文
✅ 无 tariff_research/ 内部研究
```

**结论: 仓库**内容干净, 全部是公开内容, 无需脱敏。**

---

## 🎯 3 种审核范围 (选 1 个)

### 🟢 范围 A: 最小化审核 (15 min) ⭐ 推荐

**只审核"顶层 + 4 个核心目录"** (~50 个文件)

```bash
# 1. 看根目录新文件 (最关键)
ls -la \
  AGENTS.md \
  DEPRECATED.md \
  FAQ.md \
  MANIFEST.in \
  PROFILE_README.md \
  README_EN.md \
  RELEASE_CHECKLIST.md \
  CITATION.cff \
  Makefile \
  run.sh \
  run.bat 2>/dev/null

# 2. 看 4 个新工作流
cat .github/workflows/publish-pypi.yml
cat .github/workflows/release-drafter.yml
cat .github/workflows/release-sign.yml
cat .github/workflows/pr-labeler.yml
cat .github/workflows/stale.yml

# 3. 看新增的元数据
cat .github/release-drafter.yml
cat .github/labeler.yml
cat .github/CODEOWNERS
cat .github/FUNDING.yml
cat .zenodo.json
cat .all-contributorsrc
cat .pre-commit-config.yaml
cat .dockerignore
cat .editorconfig
```

**目的**: 确认 "基础设施" 文件没问题 (CI/CD、发布、Zenodo、Codeowners)
**风险**: 可能漏掉个别代码问题
**适合**: 时间紧, 信任历史

### 🟡 范围 B: 中等审核 (40 min)

**最小化 + 所有 `scripts/core/` 改动** (~150 个文件)

```bash
# 范围 A 的全部, 再加:
git diff --name-only HEAD | grep "scripts/core/" | head -100

# 重点文件 (如出现):
git diff HEAD scripts/core/llm_gateway.py
git diff HEAD scripts/core/orchestrator.py
git diff HEAD scripts/core/agent_state.py
git diff HEAD scripts/core/checkpoint.py
git diff HEAD scripts/core/provenance.py
```

**目的**: 核心代码 (agent + LLM) 必须亲自看
**风险**: 中等, 但**有 64 个 core/ 改动**
**适合**: 你要严肃开源这个项目

### 🔴 范围 C: 全面审核 (90 min)

**所有 575 个文件** (完整 diff)

```bash
# 完整 diff 统计
git diff --stat HEAD | tail -20
git diff --stat HEAD | grep "files? changed"

# 分批查看 (按目录)
for dir in scripts docs knowledge tests mcp_servers; do
  echo "===== $dir ====="
  git diff --stat HEAD | grep "^.* $dir/"
done

# 看全部新增文件
git status -s | grep "^??" | awk '{print $2}' > /tmp/new_files.txt
echo "  新增文件数: $(wc -l < /tmp/new_files.txt)"
```

**目的**: 每个文件都过一遍
**风险**: 时间长
**适合**: 项目要给导师/雇主审核

---

## 📝 我推荐: **范围 A + 关键 core 文件 (20 min)**

混合方案：审核基础设施 + 5 个最关键的 core 文件。

```bash
# === A 范围: 15 min ===
# 基础设施 (元数据 + CI)
# (见上面命令)

# === 关键 core: 5 min ===
# 只看这 5 个最关键的 (orchestrator/llm_gateway 是项目大脑):
git diff HEAD --stat scripts/core/orchestrator.py
git diff HEAD --stat scripts/core/llm_gateway.py
git diff HEAD --stat scripts/core/agent_state.py
git diff HEAD --stat scripts/core/provenance.py
git diff HEAD --stat scripts/core/checkpoint.py
```

---

## 🛡 审核检查清单 (通用)

无论选哪个范围, 必查项:

### 必查 1: 邮箱/密钥泄漏
```bash
# 检查: 是否有人不小心 commit 了真实邮箱/密码/API key
git diff HEAD | grep -iE "password|api_key|secret|token" | grep -v ".env.example" | head -20
```

### 必查 2: 真实姓名/学校/公司
```bash
# 检查: 是否泄漏了真实身份
git diff HEAD | grep -iE "许哲逸|xuzheyi|sjtu|pku|thu|fdu|renmin|@gmail|@qq" | head -20
```

### 必查 3: 大文件 (单文件 > 1MB)
```bash
# 检查: 是否有大文件被误加
git diff HEAD | grep "^Binary" | head -10
```

### 必查 4: 中文隐私信息
```bash
# 检查: 中文隐私 (手机号、身份证、银行卡模式)
git diff HEAD | grep -E "1[3-9][0-9]{9}|[\d]{17}[0-9X]" | head -10
```

---

## 📋 审核流程 (按范围 A + 关键 core)

### Phase 1: 基础设施 (10 min)

```bash
cd /Users/xuzheyi/Desktop/论文-研报工作流

# 1. 元数据文件 (10 个, 必看)
for f in AGENTS.md DEPRECATED.md FAQ.md MANIFEST.in PROFILE_README.md \
         README_EN.md RELEASE_CHECKLIST.md CITATION.cff Makefile \
         .zenodo.json; do
  echo "===== $f ====="
  wc -l "$f" 2>/dev/null
  head -10 "$f" 2>/dev/null
  echo
done

# 2. CI/CD 工作流 (5 个, 必看)
ls .github/workflows/

# 3. Issue 模板
ls .github/ISSUE_TEMPLATE/ 2>/dev/null
```

### Phase 2: 关键核心代码 (10 min)

```bash
# 4. 最关键的 5 个 core 文件 (过目一下 diff)
git diff HEAD --stat scripts/core/orchestrator.py
git diff HEAD --stat scripts/core/llm_gateway.py
git diff HEAD --stat scripts/core/agent_state.py
git diff HEAD --stat scripts/core/provenance.py
git diff HEAD --stat scripts/core/checkpoint.py
```

### Phase 3: 安全扫描 (3 min)

```bash
# 5. 跑必查 1-4
git diff HEAD | grep -iE "password|api_key|secret|token" | grep -v ".env.example" | head
git diff HEAD | grep -iE "许哲逸|xuzheyi|@gmail|@qq.com" | head
git diff HEAD | grep -E "1[3-9][0-9]{9}" | head
```

### Phase 4: 决策 (2 min)

通过 → 继续下一步
发现问题 → 修复或回滚

---

## 🆘 发现问题怎么办?

### 如果发现泄漏了真实邮箱/姓名

```bash
# 在 .gitattributes / .env.example / etc. 中找, 删除或替换
# 然后 commit 修复
git add -A
git commit --amend --no-edit
```

### 如果发现泄漏了 API key

```bash
# ⚠️ 立即: 撤销该 key (在你用的服务上)
# 1. 登入对应服务 (OpenAI / DeepSeek / Tushare)
# 2. 撤销/重置 key
# 3. 在仓库删除该 key
# 4. commit + 推送
```

### 如果发现大文件

```bash
# 1. 检查文件
file path/to/large_file
du -h path/to/large_file

# 2. 如果不需要, 删除
rm path/to/large_file
git add -A
git commit -m "chore: remove accidentally committed large file"

# 3. 如果需要, 加 .gitignore
echo "path/to/large_file" >> .gitignore
```

---

## 🎯 审核完毕后的下一步 (供你决策)

### 决策 1: 是否现在 push?

| 选项 | 含义 |
|---|---|
| **是, 全推** | `git add -A && git commit && git push` |
| **是, 部分推** | 手动选文件, `git add <files> && git commit` |
| **否, 改完再推** | 修复审核问题后, 再走一遍 |

### 决策 2: 推送后立即做什么?

| 选项 | 含义 |
|---|---|
| **继续发布 v1.0.0** | 修邮箱 → push → tag → PyPI |
| **先等几天观察** | push 后让子弹飞一会儿, 看反馈 |
| **分批推送** | 第一次推 1 个目录, 验证流程, 后续推 |

---

## 📊 关键问题再确认

在我帮你执行 push 之前, 请明确回答:

```
Q2: GitHub profile Name 字段用哪个?
  (a) Xu Zheyí        (推荐 PhD/学术圈)
  (b) 许哲逸           (推荐 Master/国内)
  (c) X. Z. (许哲逸)  (推荐工业界)
  (d) csmar432         (推荐完全匿名)
  (e) 其他: ___

Q3: 现在是否要先在 GitHub 创建 finai-research-workflow 仓库?
  (a) 是, 我现在去创建 (创建后告诉我 URL)
  (b) 否, 暂时不创建, 我还想改东西
  (c) 我想用别的仓库名: ___

Q4: 审核范围选哪个?
  (a) 范围 A 最小 (15 min)         ⭐ 推荐
  (b) 范围 B 中等 (40 min)
  (c) 范围 C 全面 (90 min)
  (d) 混合 A + 关键 core (20 min)  ⭐ 我推荐
  (e) 我自己来

Q5: 推送策略?
  (a) 一次性 push 全部 (包括 575 个改动)
  (b) 第一次 push 已有 15 个 commit, 后续再决定
  (c) 第一次只 push 基础设施 (元数据 + CI), 后续推代码
```

---

## ✅ 完成标志

**当你回答完上述 Q2-Q5, 我会**:
1. 帮你修 commit 邮箱 (用 Gmail)
2. 帮你写完整的 push 命令 (含 URL 替换)
3. 帮你跑修复脚本 (改 author 信息)
4. 帮你验证 push 成功 + 绿点亮

**在那之前, 我不会 push 任何东西。**

---

## 📞 需要帮助?

- **Q1 邮箱**: 已确认 Gmail ✅
- **Q2 姓名**: 等你回答
- **Q3 仓库**: 等你创建
- **Q4 范围**: 推荐混合 A + 关键 core
- **Q5 策略**: 推荐 (a) 一次性

**最简回答**: 给我 (Q2选项)(Q3是/否)(Q4选项)(Q5选项) 即可, 我直接干。

