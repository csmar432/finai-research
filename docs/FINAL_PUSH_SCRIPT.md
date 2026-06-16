# 🚀 最终推送脚本 (FINAL_PUSH_SCRIPT.md)

> 状态: 准备就绪, 等你 GO
> 推送范围: ~580 个文件 (含本轮修复)
> 跳过: 10 个本地材料
> 综合审计: ⭐⭐⭐⭐ (4/5)
> 硬编码密钥: 0 (修复后) ✅

## 本轮审计与修复

**修复的安全/质量项 (3 项)**：

1. `scripts/core/sandbox_runner.py` — 3 处 docstring `api_key="e2b_..."` → `os.environ.get("E2B_API_KEY")`
2. `scripts/core/observability.py` — 2 处 docstring `langsmith_api_key="..."` → `os.environ.get("LANGSMITH_API_KEY")`
3. `scripts/core/sandbox.py` — 1 处 docstring `api_key="e2b_..."` → `os.environ.get("E2B_API_KEY")`
4. `scripts/health_check.py` — `ProblemCategory.API_KEY` 加 docstring 注释 (避免误读)

> 这些都是**文档示例**而非真实硬编码, 但用 `os.environ.get()` 模式更专业。

---

## 步骤 1: 添加 47 个公开项目文件

```bash
cd $REPO_ROOT

# 一次性添加所有公开项目内容
git add .all-contributorsrc .dockerignore .editorconfig .gitattributes \
        .pre-commit-config.yaml .zenodo.json \
        CITATION.cff MANIFEST.in \
        README_EN.md RELEASE_CHECKLIST.md run.bat \
        .github/CODEOWNERS .github/FUNDING.yml .github/labeler.yml .github/release-drafter.yml \
        .github/demo/01-architecture-overview.png .github/demo/01-architecture-overview.svg \
        .github/demo/02-skill-system-map.png .github/demo/02-skill-system-map.svg \
        .github/demo/03-mcp-ecosystem-map.png .github/demo/03-mcp-ecosystem-map.svg \
        .github/demo/04-research-pipeline.png .github/demo/04-research-pipeline.svg \
        .github/demo/05-deployment-data-flow.png .github/demo/05-deployment-data-flow.svg \
        .github/workflows/pr-labeler.yml .github/workflows/publish-pypi.yml \
        .github/workflows/release-drafter.yml .github/workflows/release-sign.yml \
        .github/workflows/stale.yml \
        config/mcp_profiles.json \
        docs/api/ \
        examples/ \
        papers/demo_000001_SZ.tex \
        releases/ \
        scripts/checkpoint.py scripts/cli.py scripts/core/formatters.py \
        scripts/fetch_msci_esg.py scripts/fetch_msci_esg_v2.py \
        scripts/fix_git_authorship.py scripts/gen_architecture_diagrams.py \
        scripts/keychain_manager.py scripts/release.py scripts/retry_utils.py \
        tests/test_retry_utils.py

# 验证 (应该没有错误)
git status -s | grep -v "^??" | head -3
echo "  ↑ 已 staged 的文件数:"
git status -s | grep -v "^??" | wc -l
```

## 步骤 2: 确认本地材料**不**被 add

```bash
# 这些应该保持 ?? (untracked), 绝不能 add
echo "===== 跳过的本地材料 (必须保持 untracked) ====="
for f in PROFILE_README.md \
         docs/BRAND_AND_EMAIL_GUIDE.md \
         docs/HIGH_STAR_STRATEGY.md \
         docs/PRE_PUSH_AUDIT_GUIDE.md \
         docs/PUBLISHING_GUIDE.md \
         docs/REPOSITORY_SETUP.md \
         docs/YOUR_SPECIFIC_FIX.md \
         docs/FINAL_PUSH_SCRIPT.md \
         scripts/fetch_msci_xu.py \
         scripts/fetch_msci_xu2.py; do
  state=$(git status -s "$f" 2>/dev/null | head -1)
  echo "  $state $f"
done
echo ""
echo "  期望: 8 个 ?? (untracked, 不会被 commit) + 2 个 D (从索引删除, 本地保留)"
```

## 步骤 3: 提交

```bash
# 推荐拆成 2-3 个 commit, 历史更清晰
# 但 1 个 commit 也可以 (1.0.0 发布)

# === 选项 A: 单个 commit (简洁) ===
git commit -m "feat: v1.0.0 release — MCP ecosystem, modern econometrics, full pipeline

• 35+ MCP data sources (academic, A-shares, US, macro, crypto)
• 27 econometric methods (modern DID, IV, RD, GMM, synthetic control)
• 17 AI skills (lit review, idea gen, novelty check, paper writing)
• 34 journal templates (JF, JFE, RFS, 经济研究, 金融研究)
• Adversarial review loop
• Full Claude Code + Copilot + Cursor support

Refactor:
• Renamed fetch_msci_xu.py → fetch_msci_esg.py (generic tool)
• Renamed fetch_msci_xu2.py → fetch_msci_esg_v2.py
• Made fix_git_authorship.py generic with placeholders

Infrastructure:
• Added codecov, bandit, pre-commit, ruff badges
• 7 GitHub workflows (CI, docs, PyPI, release, stale)
• 86 tests with CI integration
• Full documentation (tutorials, ADRs, architecture)"

# === 选项 B: 拆 2-3 commit (更专业) ===
# Commit 1: 核心代码 (无 scripts/fix_git_authorship.py)
# Commit 2: 文档和示例
# Commit 3: 工具脚本
```

## 步骤 4: 创建 GitHub 仓库 (UI 操作)

> **这一步需要你在浏览器中点鼠标**

```bash
# 在浏览器中打开 GitHub, 创建新仓库:
# https://github.com/new

# 仓库名: finai-research-workflow
# 描述: "经济金融 AI 学术研究工作流 - End-to-end agent for financial research"
# 公开: ✓
# README/LICENSE/.gitignore: 全部不勾选 (本地已有)
# 点击: Create repository
```

## 步骤 5: 修 commit 作者 + push

```bash
cd $REPO_ROOT

# 5.1 修本地 commit 的作者 (用 noreply 邮箱, 让绿点显示)
# 替换 USERNAME/EMAIL 为你的实际值
python scripts/fix_git_authorship.py \
  --old-email "old@example.com" \
  --new-email "12345+USERNAME@users.noreply.github.com" \
  --new-name "Your Name" \
  --dry-run
# ↑ 先看, 确认无误后再去掉 --dry-run

python scripts/fix_git_authorship.py \
  --old-email "old@example.com" \
  --new-email "12345+USERNAME@users.noreply.github.com" \
  --new-name "Your Name"
# ↑ 实际重写 (会改所有 commit hash)

# 5.2 添加 GitHub remote
# 替换 USERNAME/REPO 为你的实际值
git remote add origin https://github.com/USERNAME/REPO.git

# 5.3 push (新仓库, 第一次)
git push -u origin main
```

## 步骤 6: push 后配置 (UI)

```bash
# 在 GitHub 仓库页面:
# 1. About (右侧) → 添加 Description, Topics, Website
# 2. Settings → Features → ✓ Discussions
# 3. Settings → General → Default branch → main
# 4. 等待 CI/CD 通过 (查看 Actions tab)
```

---

## 🆘 紧急回滚 (万一出错)

```bash
# 1. 撤销 commit (未 push 时)
git reset --soft HEAD~1   # 软回滚 (保留修改)
git reset --hard HEAD~1   # 硬回滚 (删除修改)

# 2. 撤销 add
git restore --staged <file>

# 3. 撤销 git rm
git restore --staged scripts/fetch_msci_xu.py
git restore --staged scripts/fetch_msci_xu2.py

# 4. 撤销 fix_git_authorship (用 reflog)
git reflog  # 找旧 commit hash
git reset --hard <旧 hash>
```

---

## 📊 推送前最终自检

```bash
cd $REPO_ROOT

echo "===== 自检 1: 没有误 add 的本地材料 ====="
for f in PROFILE_README.md \
         docs/BRAND_AND_EMAIL_GUIDE.md \
         docs/HIGH_STAR_STRATEGY.md \
         docs/PRE_PUSH_AUDIT_GUIDE.md \
         docs/PUBLISHING_GUIDE.md \
         docs/REPOSITORY_SETUP.md \
         docs/YOUR_SPECIFIC_FIX.md \
         scripts/fetch_msci_xu.py \
         scripts/fetch_msci_xu2.py; do
  state=$(git status -s "$f" 2>/dev/null | head -1)
  if [[ "$state" == "A "* ]] || [[ "$state" == "M "* ]]; then
    echo "  ❌ 严重: $f 已被 add, 立刻撤销!"
  elif [[ "$state" == "??"* ]]; then
    echo "  ✓ $f (本地保留, 不推送)"
  else
    echo "  ? $f (状态: '$state')"
  fi
done

echo ""
echo "===== 自检 2: 已 tracked + staged 文件总数 ====="
git status -s | grep -v "^??" | wc -l

echo ""
echo "===== 自检 3: 关键文件已就位 ====="
for f in scripts/fetch_msci_esg.py scripts/fetch_msci_esg_v2.py scripts/fix_git_authorship.py; do
  if git status -s "$f" | grep -qE "A |M "; then
    echo "  ✓ $f (已 staged)"
  elif git status -s "$f" | grep -qE "D "; then
    echo "  ✓ $f (已 staged 删除)"
  else
    echo "  ? $f (状态: $(git status -s $f | head -1))"
  fi
done

echo ""
echo "===== 自检 4: 无敏感信息残留 ====="
echo "  扫描新脚本中真名/真邮箱..."
grep -lE "你的真名|你的真邮箱" scripts/fetch_msci_esg.py scripts/fetch_msci_esg_v2.py scripts/fix_git_authorship.py 2>/dev/null
echo "  (空 = 干净 ✅)"
```

---

## ⏸ 等你 GO

**说 "go" 我会立即执行**:
1. 步骤 1: 添加 47 个文件
2. 步骤 2: 验证 (自动)
3. 步骤 3: 单个 commit
4. (暂停, 等你创建 GitHub 仓库)
5. 步骤 5: 修邮箱 + push
6. (暂停, 等你配置 GitHub)

**或者你也可以拆开**:
- "go add" → 只执行步骤 1-3
- "go push" → 假设 GitHub 仓库已创建, 直接 push

