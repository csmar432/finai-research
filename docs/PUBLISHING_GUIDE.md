# 🚀 v1.0.0 发布操作手册

> **目标**: 帮你从 0 到 1 完成 GitHub 仓库的元数据设置 + 第三方服务配置，最终发布 v1.0.0 到 PyPI。
> **预计时间**: 45-60 分钟
> **难度**: ⭐⭐ (每个步骤都有详细指引)

---

## 📋 操作总览

| 阶段 | 任务 | 估时 | 难度 |
|---|---|---|---|
| **Phase 1: GitHub 仓库元数据** | 5 项 | 15 min | ⭐ |
| **Phase 2: 第三方服务** | 4 项 | 25 min | ⭐⭐ |
| **Phase 3: PyPI Trusted Publishing** | 1 项 | 5 min | ⭐ |
| **Phase 4: 正式发布** | 4 步 | 10 min | ⭐ |

> 顺序很重要: 1 → 2 → 3 → 4

---

# Phase 1: GitHub 仓库元数据 (15 min)

> 位置: 浏览器打开 `https://github.com/csmar432/finai-research-workflow`

## 1.1 添加 Description (1 min)

**为什么**: 用户在搜索/发现项目时第一眼看到的内容。

**操作**:
1. 打开仓库主页: https://github.com/csmar432/finai-research-workflow
2. 在页面右侧 (About 区域) 找到 "Edit" 按钮
3. Description 字段填入:

```
End-to-end AI agent pipeline for economic and financial research. 
49 MCP data servers, 49 econometric methods (DID/IV/RDD/PSM), 
17 AI skills, 34 journal templates. 
Designed for JF/JFE/RFS/经济研究/金融研究 submissions.
```

4. 勾选 ✅ Releases / ✅ Packages / ✅ Contributors
5. 点击 "Save changes"

**检查**: 刷新页面，About 区域显示新 Description。

---

## 1.2 添加 Topics (1 min)

**为什么**: GitHub 搜索排名权重最高。

**操作**:
1. 在仓库主页 → About 区域 → Edit
2. Topics 输入框,逐个添加 (GitHub 会自动提示):

```
academic-research
financial-ai
econometrics
paper-writing
latex
mcp
cursor
difference-in-differences
instrumental-variables
causal-inference
```

3. Save

**检查**: About 区域显示 10 个蓝色 topic 标签。

---

## 1.3 添加 Social Preview 图片 (2 min)

**为什么**: 用户在 Twitter/微博/搜索结果看到的第一印象图片 (1280×640)。

**操作**:
1. Settings → General → Social preview
2. 点击 "Upload an image" (注意: 必须 ≥ 1280×640, PNG/JPG)
3. 推荐使用你已有的架构图:
   - `.github/demo/01-architecture-overview.png`
   - `.github/demo/04-research-pipeline.png`
   - 或专门为 social preview 设计一个 (用 Figma/Canva)
4. Upload

**检查**: 打开任何 Issue 页面,顶部会显示这张图。

---

## 1.4 启用 Discussions (1 min)

**为什么**: 社区 Q&A 平台 (替代单独的 Slack/微信群)。

**操作**:
1. Settings → General → Features
2. ✅ 勾选 "Discussions"
3. (可选) 配置欢迎帖: Discussions → "Set up categories"

**推荐 Categories**:
- 📣 Announcements
- 💡 Ideas
- 🙏 Q&A
- 📚 Show and tell

**检查**: 仓库顶部多出 "Discussions" 标签。

---

## 1.5 设置 main 分支保护 (10 min)

**为什么**: 防止 main 分支被直接 push,要求 PR + CI 通过。

**操作**:
1. Settings → Branches → Add branch protection rule
2. Branch name pattern: `main`
3. 配置:

```
✅ Require a pull request before merging
   ✅ Require approvals: 1
   ✅ Dismiss stale pull request approvals when new commits are pushed

✅ Require status checks to pass before merging
   ✅ Require branches to be up to date before merging
   Status checks 搜索并添加 (CI 跑过后才显示):
   - Lint & Type Check
   - Tests batch 1/3
   - Tests batch 2/3
   - Tests batch 3/3
   - Coverage Report

✅ Require conversation resolution before merging
✅ Include administrators (可选)
❌ Allow force pushes (永远关闭)
```

4. Save changes

**检查**: 尝试直接 push 到 main,应该被拒绝。

---

# Phase 2: 第三方服务 (25 min)

## 2.1 注册 Codecov (代码覆盖率) (5 min)

**为什么**: Coverage badge + 趋势图,自动从 CI 抓数据。

**操作**:
1. 打开 https://about.codecov.io/
2. 用 GitHub 账号登录
3. 添加组织: 选择你的 GitHub 用户
4. 添加仓库: csmar432/finai-research-workflow
5. 复制 token (Settings → General → Repository Upload Token)
6. 在 GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret
   - Name: `CODECOV_TOKEN`
   - Value: 粘贴上面复制的 token
7. Add secret

**激活**:
- 在 `.github/workflows/ci.yml` 的 coverage job 中加 (如果还没加):
```yaml
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    token: ${{ secrets.CODECOV_TOKEN }}
    files: ./coverage.xml
```

**检查**:
- 推一次新 commit → GitHub Actions → Coverage job → 上传成功
- 打开 https://codecov.io/gh/csmar432/finai-research-workflow
- README badge 自动激活 (现在显示具体百分比)

---

## 2.2 链接 Zenodo (学术 DOI) (5 min)

**为什么**: 每次 GitHub Release 自动生成 DOI,适合学术引用。

**操作**:
1. 打开 https://zenodo.org/
2. 用 GitHub 账号登录 (首次需授权)
3. 进入 https://zenodo.org/account/settings/github/
4. 在 "GitHub repositories" 列表中找到 `csmar432/finai-research-workflow`
5. 启用 sync (ON)
6. (可选) 填写 `.zenodo.json` 中作者 ORCID (在 https://orcid.org/ 注册)

**激活**:
- 第一次发布 GitHub Release 时自动触发
- Zenodo 给你一个 DOI 链接,如 `10.5281/zenodo.1234567`
- 更新 README 的 DOI badge:
  ```markdown
  [![DOI](https://zenodo.org/badge/DOI/<your-actual-doi>.svg)](https://doi.org/<your-actual-doi>)
  ```

**检查**:
- 在 Releases 页面发布 v1.0.0
- 5-10 分钟后, https://zenodo.org/ 你的 dashboard 显示新版本

---

## 2.3 注册 GitHub Container Registry (Docker images) (5 min, 可选)

**为什么**: 自动发布 Docker 镜像 (如果你的用户用 Docker 部署)。

**操作**:
1. 仓库根目录创建 `.github/workflows/docker-publish.yml` (你已有,见下)
2. (此项目可选,因用户通常 pip install)

**检查**:
- 推送 tag → Actions 自动 build + push
- `docker pull ghcr.io/csmar432/finai-research-workflow:v1.0.0`

---

## 2.4 设置 Dependabot (依赖自动更新) (2 min, 已配)

**状态**: 已配置, 无需操作。

**验证**:
- 打开 https://github.com/csmar432/finai-research-workflow/security/dependabot
- 启用: Dependabot alerts ✅ / Dependabot security updates ✅

---

# Phase 3: PyPI Trusted Publishing (5 min)

> 这是**关键**,决定能否自动发布到 PyPI。

## 3.1 在 PyPI 配置 Trusted Publisher

**操作**:
1. 打开 https://pypi.org/manage/account/publishing/
2. 滚动到 "Add a new pending publisher"
3. 填写:
   - **Owner**: `csmar432` (你的 PyPI 用户名, 如未注册先去 https://pypi.org/account/register/)
   - **Repository name**: `finai-research-workflow` 
   - **Workflow filename**: `publish-pypi.yml`
   - **Environment name**: `pypi`
4. Submit
5. (可选) 同样在 https://test.pypi.org/manage/account/publishing/ 配置 TestPyPI

**检查**: 在你的 PyPI 账号 → Publishing → 看到 "csmar432/finai-research-workflow" 一条。

---

## 3.2 在 GitHub 创建 Environment

**操作**:
1. GitHub 仓库 → Settings → Environments → New environment
2. Name: `pypi`
3. (可选) Protection rules: Required reviewers (推荐你自己)
4. Configure environment
5. (再次) 进 environment → Add secret (此项目不需要,因为用 OIDC)

**检查**: 仓库 → Settings → Environments 列表中有 `pypi`。

---

# Phase 4: 正式发布 (10 min)

> 此时所有"管道"已通,只需 push tag 触发自动发布。

## 4.1 提交当前所有改动 (1 min)

```bash
cd /Users/xuzheyi/Desktop/论文-研报工作流
git add -A
git commit -m "chore(release): prepare v1.0.0 - CLI, MANIFEST, publish workflow, badges"
git push origin main
```

---

## 4.2 打 v1.0.0 tag 并推送 (1 min)

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

**检查**:
- 仓库主页 → Releases 出现 v1.0.0 (draft)
- Actions → publish-pypi.yml 自动开始跑

---

## 4.3 创建 GitHub Release (2 min)

**操作**:
1. 仓库主页 → Releases → v1.0.0 → Edit
2. 填写:
   - **Title**: v1.0.0
   - **Description**: 复制 `releases/v1.0.0.md` 的内容
   - **Tag**: v1.0.0
   - **Target**: main
3. ✅ Set as the latest release
4. Publish release

**触发**:
- publish-pypi.yml 自动 build + publish
- release-sign.yml 自动 sigstore 签名
- release-drafter.yml 后续版本自动生成 draft

---

## 4.4 验证发布成功 (5 min)

**验证清单** (逐项打勾):

```bash
# A. PyPI 包可安装
pip install finai-research-workflow
python -c "import scripts; print('✅ 安装成功')"
finai version
finai health

# B. 验证测试通过
pytest tests/ -x -q
# 应该: 86 tests passed

# C. 验证 GitHub Release
# 打开: https://github.com/csmar432/finai-research-workflow/releases/tag/v1.0.0
# ✅ 看到 release notes
# ✅ 看到 .whl 和 .tar.gz 下载
# ✅ sigstore 签名文件 (.sig, .cert)

# D. 验证 Zenodo DOI
# 打开: https://zenodo.org/search?q=finai-research-workflow
# ✅ 看到 v1.0.0 entry
# ✅ 有 DOI 链接

# E. 验证 Codecov
# 打开: https://codecov.io/gh/csmar432/finai-research-workflow
# ✅ 看到 coverage 报告
# ✅ README badge 颜色正确 (绿/黄/红)

# F. 验证 docs 部署
# 打开 GitHub Pages 链接
# ✅ 看到 mkdocs 站点
```

---

## 4.5 发布公告 (5 min, 可选)

在以下平台发布公告:

- **GitHub Discussions**: 创建一个 "📣 v1.0.0 Released" pinned 帖
- **Twitter/X**: 配架构图 + 一句话介绍
- **知乎/微博**: 中文版本
- **Reddit**: r/MachineLearning, r/econometrics
- **Hacker News**: Show HN: FinAI Research Workflow

---

# 📊 操作时间线 (推荐)

| 时间 | 任务 | 状态 |
|---|---|---|
| 0:00 | Phase 1.1: Description | ☐ |
| 0:01 | Phase 1.2: Topics | ☐ |
| 0:02 | Phase 1.3: Social Preview | ☐ |
| 0:05 | Phase 1.4: Discussions | ☐ |
| 0:06 | Phase 1.5: Branch protection | ☐ |
| 0:15 | **Phase 1 完成** | ☐ |
| 0:16 | Phase 2.1: Codecov | ☐ |
| 0:21 | Phase 2.2: Zenodo | ☐ |
| 0:26 | Phase 2.3: Container Registry (可选) | ☐ |
| 0:31 | Phase 2.4: Dependabot 验证 | ☐ |
| 0:33 | **Phase 2 完成** | ☐ |
| 0:34 | Phase 3.1: PyPI Trusted Publisher | ☐ |
| 0:37 | Phase 3.2: GitHub Environment | ☐ |
| 0:40 | **Phase 3 完成** | ☐ |
| 0:41 | Phase 4.1: commit & push | ☐ |
| 0:42 | Phase 4.2: git tag | ☐ |
| 0:43 | Phase 4.3: GitHub Release | ☐ |
| 0:45 | Phase 4.4: 验证 | ☐ |
| 0:50 | Phase 4.5: 公告 (可选) | ☐ |
| **0:55** | **🎉 v1.0.0 正式发布!** | ☐ |

---

# 🆘 常见问题

### Q1: PyPI 名字 "finai-research-workflow" 被占怎么办?

**A**:
1. 打开 https://pypi.org/project/finai-research-workflow/
2. 如果被占,在 `pyproject.toml` 改 name:
   ```toml
   [project]
   name = "finai-research-workflow"  # 改为不同名字
   ```
3. 重新 release

### Q2: Trusted Publishing 第一次失败?

**A**:
1. 检查 PyPI account 邮箱是否已验证
2. 检查环境名拼写 (PyPI: `pypi` 必须全小写)
3. 检查 workflow filename (必须是 `publish-pypi.yml`)
4. 第一次失败可手动重试:
   ```bash
   pip install twine
   python -m build
   twine upload dist/*
   ```

### Q3: 推 tag 后没自动触发 publish-pypi.yml?

**A**:
1. 检查 `on: release: types: [published]` 触发器
2. 必须先在 GitHub UI 创建 Release (不是只 push tag)
3. 检查 Secrets/Environment 名称

### Q4: sigstore 签名失败?

**A**:
1. 检查 `permissions: id-token: write` 是否给
2. 检查 sigstore-action 是否最新版本
3. 第一次可能需联网下载 cosign binary,等待 2-3 分钟

### Q5: 测试太慢导致 CI 超时?

**A**:
1. CI 已分 3 个 batch 并行跑
2. 单个 job 超时可调 `actions/setup-python@v5` 的 `python-version`
3. 可选: 移到 self-hosted runner (macOS 跑 Python 测试更快)

---

# ✅ 完成检查

- [ ] Phase 1 全部完成
- [ ] Phase 2 全部完成 (Container 可选)
- [ ] Phase 3 全部完成
- [ ] v1.0.0 在 PyPI 可安装
- [ ] GitHub Release 显示完整 changelog
- [ ] Zenodo DOI 已生成
- [ ] Codecov badge 已激活
- [ ] GitHub Pages 文档已部署
- [ ] 公告已发 (可选)

**全部勾选后, v1.0.0 正式发布! 🎉**

---

# 📞 需要帮助?

- **Issue**: https://github.com/csmar432/finai-research-workflow/issues
- **Discussion**: https://github.com/csmar432/finai-research-workflow/discussions
- **Email**: xuzheyi@users.noreply.github.com

