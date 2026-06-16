# GitHub Repository Metadata

> 📋 集中存放 GitHub 仓库页需要手动粘贴的所有元数据。
> 用法：到 https://github.com/csmar432/FinAI-Research-Workflow/settings
> 把下面字段对应填入。

## 1. Description (顶部 "About" 卡片)

```
End-to-end AI agent workflow for economic & financial research: lit review → idea generation → empirical design (DID/IV/RDD) → paper writing. 43 MCP data servers, 49 econometric methods, 17 AI skills, 70 journal templates.
```

## 2. Website

```
https://github.com/csmar432/FinAI-Research-Workflow
```
（或留空，等 GitHub Pages 发布后填 `https://csmar432.github.io/FinAI-Research-Workflow/`）

## 3. Topics (建议 5-10 个)

| Topic | 覆盖范围 |
|---|---|
| `academic-research` | 学术研究通用 |
| `financial-ai` | 金融 AI 垂直 |
| `econometrics` | 计量经济学 |
| `paper-writing` | 论文写作 |
| `latex` | LaTeX 排版 |
| `mcp` | Model Context Protocol |
| `difference-in-differences` | DID 核心方法 |
| `causal-inference` | 因果推断 |
| `research-workflow` | 端到端工作流 |
| `agent` | AI Agent |

复制粘贴（GitHub 接受小写/中划线）：

```
academic-research
financial-ai
econometrics
paper-writing
latex
mcp
difference-in-differences
causal-inference
research-workflow
agent
```

## 4. Releases / Packages / Contributors

- ✅ **Releases**: 已启用（`v0.1.0` 已发布）
- ✅ **Packages**: 已启用
- ✅ **Contributors**: 已启用

## 5. Social Preview（1280×640 PNG）

用项目里已有的截图：

```
$REPO_ROOT/.github/demo/01-architecture-overview.png
```

或者重新生成：

```bash
# 用 SVG 渲染
python -c "
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
fig, ax = plt.subplots(figsize=(12.8, 6.4), dpi=100)
ax.set_xlim(0, 12.8); ax.set_ylim(0, 6.4); ax.axis('off')
ax.set_facecolor('#0d1117')
fig.patch.set_facecolor('#0d1117')
# 标题
ax.text(6.4, 4.8, 'FinAI Research Workflow', ha='center', fontsize=42, color='white', weight='bold')
ax.text(6.4, 3.8, 'AI-powered research workflow for finance & economics', ha='center', fontsize=18, color='#8b949e')
# 三个 box
for i, (x, label, color) in enumerate([
    (1.5, '43 MCP\\nData Sources', '#58a6ff'),
    (6.4, '49 Econometric\\nMethods (DID/IV/RDD)', '#7ee787'),
    (11.3, '70 Journal\\nTemplates', '#ffa657'),
]):
    ax.add_patch(mpatches.FancyBboxPatch((x-1.2, 1.4), 2.4, 1.4, boxstyle='round,pad=0.05', facecolor='#161b22', edgecolor=color, linewidth=2))
    ax.text(x, 2.1, label, ha='center', va='center', fontsize=12, color=color, weight='bold')
ax.text(6.4, 0.6, 'github.com/csmar432/FinAI-Research-Workflow', ha='center', fontsize=14, color='#8b949e')
plt.savefig('.github/social-preview.png', dpi=100, facecolor='#0d1117')
print('saved')
"
```

## 6. Branch Protection Rules（main 分支）

Settings → Branches → Add rule:

- **Branch name pattern**: `main`
- ✅ **Require pull request reviews before merging**: 1 approval
- ✅ **Require status checks to pass before merging**:
  - `CI / Lint & Type Check`
  - `CI / Tests batch 1/3 (core)`
  - `CI / Tests batch 2/3 (orchestrator)`
  - `CI / Tests batch 3/3 (econometrics)`
  - `CI / Cross-platform smoke test (ubuntu-latest, 3.12)`
  - `CI / Cross-platform smoke test (macos-latest, 3.12)`
- ✅ **Require conversation resolution before merging**
- ❌ **Allow force pushes**: 永远禁用
- ❌ **Allow deletions**: 永远禁用

## 7. Discussions（社区）

Settings → General → Features:
- ✅ **Discussions**: 启用
  - 📌 Announcements
  - 💡 Ideas
  - 🙏 Q&A
  - 📣 Show and tell

## 8. Pages（文档站，可选）

Settings → Pages:
- Source: **Deploy from a branch**
- Branch: `gh-pages` / `root`

> 当前 `docs.yml` 只构建 mkdocs 站点并上传为 artifact，不自动部署。要启用 Pages
> 需要把 build artifact push 到 `gh-pages` 分支或改用 `mkdocs gh-deploy`。

## 9. Codecov（覆盖率徽章）

1. 注册 https://about.codecov.io/，绑定仓库
2. 复制 token
3. Settings → Secrets → Actions → 新建 `CODECOV_TOKEN`
4. 仓库 README 的 codecov badge 会自动激活

## 10. Zenodo（学术 DOI）

1. 注册 https://zenodo.org/
2. https://zenodo.org/account/settings/github/ 链接 GitHub
3. 选择本仓库
4. 每次 GitHub Release 自动生成 DOI
5. README 中可加 DOI badge

## 11. PyPI Trusted Publishing

pypi.org/manage/account/publishing/ → Add a new pending publisher:
- Owner: `csmar432`（或你的用户名）
- Repository: `FinAI-Research-Workflow`
- Workflow filename: `publish-pypi.yml`
- Environment name: `pypi`

无需 API token，GitHub Actions 用 OIDC 自动认证。

## 12. Security

- ✅ Private vulnerability reporting (需 `SECURITY.md` 已有)
- ✅ Dependabot alerts
- ✅ Dependabot security updates
- ✅ Code scanning → CodeQL

## 13. 一键检查清单

- [ ] Description 设置
- [ ] Topics 设置（5-10 个）
- [ ] Website 设置（如有 Pages）
- [ ] Social preview 上传 1280×640 PNG
- [ ] Branch protection: main 需要 1 review + 6 status checks
- [ ] Discussions 启用
- [ ] Releases/Packages/Contributors 启用
- [ ] Codecov token 加入 Secrets
- [ ] Zenodo 链接 GitHub
- [ ] PyPI Trusted Publishing 配置
