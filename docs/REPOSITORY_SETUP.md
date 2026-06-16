# 仓库设置建议 (GitHub Settings)

> 在 GitHub 仓库页 → Settings 中配置。

## 1. General

- ✅ **Default branch**: `main`
- ✅ **Allow squash merging**: ✅
- ✅ **Allow merge commits**: ✅
- ✅ **Allow rebase merging**: ❌ (推荐用 squash)
- ✅ **Automatically delete head branches**: ✅

## 2. Features

- ✅ **Issues**: ✅ 启用
- ✅ **Projects**: ❌ 关闭 (用 GitHub Projects V2 即可)
- ✅ **Wiki**: ❌ 关闭 (用 docs/ + mkdocs)
- ✅ **Discussions**: ✅ 启用 (Q&A 社区)
- ✅ **Sponsorships**: 可选

## 3. Pull Requests

- ✅ **Allow squash merging**
- ✅ **Default commit message**: `Pull request title and description`
- ✅ **Always suggest updating pull request branches**
- ✅ **Allow auto-merge**
- ✅ **Automatically delete head branches after pull requests are merged**

## 4. Security

- ✅ **Private vulnerability reporting**: ✅ 启用 (依赖 SECURITY.md)
- ✅ **Dependency graph**: ✅ 启用
- ✅ **Dependabot alerts**: ✅ 启用
- ✅ **Dependabot security updates**: ✅ 启用
- ✅ **Code scanning**: ✅ 启用 CodeQL

## 5. Pages (文档站点)

- ✅ **Source**: `Deploy from a branch`
- ✅ **Branch**: `gh-pages` / `root`
- ✅ **Custom domain**: 可选

## 6. Social Preview (关键!)

- 📷 **添加 Social preview 图片** (1280×640 PNG)
  - 用现有的 `.github/demo/01-architecture-overview.png` 也可
  - 用户在社交媒体/搜索引擎看到的第一印象

## 7. Topics (关键!)

- 添加 5-10 个 topics 提高 GitHub 搜索排名：
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

## 8. About (右上角)

- 📝 **Description**: 
  ```
  End-to-end AI agent pipeline for economic and financial research. 
  43 MCP data servers, 49 econometric methods (DID/IV/RDD/PSM), 
  17 AI skills, 70 journal templates.
  ```
- 🔗 **Website**: 可指向 GitHub Pages
- ⭐ **Topics**: 见 #7
- ✅ **Releases**: ✅
- ✅ **Packages**: ✅
- ✅ **Contributors**: ✅
- ✅ **Sponsorship**: 可选

## 9. Integrations & services

- ✅ **Codecov.io** (代码覆盖率):
  1. 注册 https://about.codecov.io/
  2. 添加仓库
  3. 复制 token → 仓库 Settings → Secrets → `CODECOV_TOKEN`
  4. README badge 自动激活

- ✅ **Zenodo** (学术 DOI):
  1. 注册 https://zenodo.org/
  2. 链接 GitHub: https://zenodo.org/account/settings/github/
  3. 选择本仓库
  4. 新 Release 时自动获得 DOI
  5. 在 README 中显示 DOI badge

## 10. Branch Protection (main 分支)

- ✅ **Require pull request reviews before merging**: 1 approval
- ✅ **Require status checks to pass before merging**:
  - CI / Lint & Type Check
  - CI / Tests batch 1/3
  - CI / Tests batch 2/3
  - CI / Tests batch 3/3
  - CI / Coverage Report
- ✅ **Require conversation resolution before merging**
- ✅ **Require signed commits** (optional)
- ✅ **Include administrators** (可选, 严格模式)
- ✅ **Allow force pushes**: ❌ (永远不要)

## 11. Secrets (Settings → Secrets and variables → Actions)

仓库需要的 secrets:
- `GITHUB_TOKEN` - 自动提供
- `CODECOV_TOKEN` - 注册 Codecov 后获得
- `DEEPSEEK_API_KEY` - 仅 PR 测试时用 (用 `dummy_key` 即可)
- `RELAY_API_KEY` - 同上

**不要** commit 真实 API keys！

## 12. PyPI Trusted Publishing (推荐)

- 在 https://pypi.org/manage/account/publishing/ 添加：
  - **Owner**: 你的用户名
  - **Repository**: `csmar432/finai-research-workflow`
  - **Workflow filename**: `publish-pypi.yml`
  - **Environment name**: `pypi`
- 不需要 API token, GitHub Actions 用 OIDC 自动认证

## 13. Post-release checklist

每次发布后:
- [ ] GitHub Release 包含完整 changelog
- [ ] PyPI 包可安装 (`pip install finai-research-workflow`)
- [ ] Codecov 报告更新
- [ ] Zenodo DOI 自动创建
- [ ] sigstore-action 签名 release
- [ ] 在社交媒体宣布
- [ ] 更新 DISCUSSION
