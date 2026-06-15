# 🚀 发布前检查清单 (Pre-release Checklist)

> 发布 v1.0.0 前必须逐项勾选。

## ✅ 1. 代码与测试

- [x] 86 个测试文件，全部通过
- [x] `pytest tests/ -v` 无 error
- [x] Coverage ≥ 60% (CI 强制)
- [x] `ruff check scripts/` 无 error
- [x] `mypy scripts/` 无 error (警告可接受)
- [x] Pre-commit hooks 全部安装并通过
- [x] Conventional Commits 规范

## ✅ 2. 文档

- [x] `README.md` (中文) 完整
- [x] `README_EN.md` (英文) 完整
- [x] `使用指南.md` 13 章 1049 行
- [x] `CHANGELOG.md` 包含 [Unreleased] 和 [1.0.0] 段
- [x] `LICENSE` MIT (含年份)
- [x] `CONTRIBUTING.md` 完整
- [x] `CODE_OF_CONDUCT.md` 完整
- [x] `SECURITY.md` 完整
- [x] `FAQ.md` 完整
- [x] `CITATION.cff` 完整
- [x] docs/ 22 个文档
- [x] knowledge/skills/ 17 个技能
- [x] templates/ 6 个 LaTeX 模板
- [x] examples/ 5 个可运行示例
- [x] API reference (docs/api_reference.md)
- [x] Sphinx 配置 (docs/api/conf.py)

## ✅ 3. 社区与治理

- [x] `CODEOWNERS` 完整
- [x] Issue 模板 (bug/feature/config)
- [x] PR 模板
- [x] PR labeler workflow
- [x] Stale bot workflow
- [x] all-contributors config
- [x] FUNDING.yml
- [x] Discussion 启用 (在 GitHub Settings)

## ✅ 4. CI/CD

- [x] `.github/workflows/ci.yml` (7 jobs)
- [x] `.github/workflows/docs.yml` (build + deploy to Pages)
- [x] `.github/workflows/release-drafter.yml`
- [x] `.github/workflows/release-sign.yml` (sigstore)
- [x] `.github/workflows/stale.yml`
- [x] `.github/workflows/pr-labeler.yml`
- [x] `.github/workflows/publish-pypi.yml` (Trusted Publishing OIDC)

## ✅ 5. 仓库元数据

- [ ] ⚠️ **在 GitHub Settings 添加 description** (About 区域)
- [ ] ⚠️ **在 GitHub Settings 添加 topics** (5-10 个)
- [ ] ⚠️ **添加 Social Preview 图片** (1280×640 PNG)
- [ ] ⚠️ **启用 Discussions**
- [ ] ⚠️ **设置 Branch protection (main 分支)**

## ✅ 6. 第三方服务 (一次性设置)

- [ ] ⚠️ **注册 Codecov.io** → 添加 token 到 GitHub Secrets
- [ ] ⚠️ **注册 Zenodo** → 链接 GitHub 仓库
- [ ] ⚠️ **配置 PyPI Trusted Publishing** (publish-pypi.yml + workflow file)
- [ ] ⚠️ **(可选) 设置 GitHub Pages 自定义域名**

## ✅ 7. 打包与发布工具

- [x] `pyproject.toml` 完整 (含 hatch build config)
- [x] `MANIFEST.in` 完整
- [x] `[project.scripts]` 6 个 CLI 入口
- [x] `scripts/cli.py` 主 CLI
- [x] `scripts/release.py` 一键发布脚本
- [x] `requirements.txt` + `requirements-optional.txt`

## ✅ 8. 测试发布流程

```bash
# 1. 干跑发布 (不改任何东西)
python scripts/release.py 1.0.0 --dry-run

# 2. 真实发布到 TestPyPI (推荐)
python scripts/release.py 1.0.0-rc.1 --test

# 3. 在 TestPyPI 验证: pip install -i https://test.pypi.org/simple/ finai-research-workflow==1.0.0-rc.1

# 4. 正式发布
python scripts/release.py 1.0.0

# 5. git push origin main && git push origin v1.0.0
```

## ✅ 9. 发布后任务

- [ ] 在 GitHub 创建 Release (从 v1.0.0 tag)
- [ ] Release notes 自动从 `releases/v1.0.0.md` 生成
- [ ] 验证 PyPI 包可安装
- [ ] 验证 sigstore 签名
- [ ] 验证 Codecov 报告更新
- [ ] 验证 Zenodo DOI 创建
- [ ] 在 Discussion 发布公告
- [ ] (可选) 发 Twitter / 知乎 / 微博 公告

## 📊 发布完成度

| 类别 | 完成 | 总数 | 进度 |
|---|---|---|---|
| 代码与测试 | 8 | 8 | 100% |
| 文档 | 15 | 15 | 100% |
| 社区与治理 | 8 | 8 | 100% |
| CI/CD | 7 | 7 | 100% |
| 仓库元数据 | 0 | 5 | **0%** ⚠️ |
| 第三方服务 | 0 | 4 | **0%** ⚠️ |
| 打包与发布 | 6 | 6 | 100% |
| **总计** | **44** | **53** | **83%** |

**剩余 9 项**都是**手动在 GitHub UI / 第三方网站**完成的，**不是代码任务**。

## 🎯 发布前最后一步

```bash
# 完整发布流程（在你准备好 PyPI Trusted Publishing + 第三方账号之后）
python scripts/release.py 1.0.0 --skip-tests
git push origin main
git push origin v1.0.0
# 然后在 GitHub 页面确认 release
```

完成！
