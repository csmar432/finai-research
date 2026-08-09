# GitHub Social Preview 上传指引

> **目标**: 把 `social-preview.png` 上传到 GitHub 仓库 Settings → Social preview
>
> **当前文件**（指标由 `scripts/count_assets.py` 自动读取）:
> - `docs/assets/social-preview.png` ⭐ **推荐从这里上传** — 路径在网页 UI 中好找
> - `.github/social-preview.png` — 备份位置 (隐藏目录, 网页选择器中不可见)

---

## 🚶 步骤 (3 分钟)

### Step 1: 打开 Settings
```
https://github.com/csmar432/finai-research/settings
```

向下滚动到 **"Social preview"** 部分 (位于 "Social preview" 标题下方).

### Step 2: 上传图
两种方式:

**方式 A — 直接本地上传** (推荐):
1. 打开 Finder → 找到本仓库下 `docs/assets/social-preview.png`
   (在 Finder 输入 `Cmd+Shift+G`, 粘贴 `~/Desktop/论文-研报工作流/docs/assets/social-preview.png`)
2. 在 GitHub Settings 页面点 "Upload an image..."
3. 选刚找到的 `docs/assets/social-preview.png`
4. 点 "Submit"

**方式 B — 拖拽**:
1. 在 Finder 中把 `docs/assets/social-preview.png` 拖到 GitHub 页面
2. 点 "Submit"

### Step 3: 验证
页面会显示新上传的预览图. 检查:
- [ ] 数字与 `python scripts/count_assets.py` 输出一致（当前为 43 / 58 / 18 / 30）
- [ ] 没有裁剪
- [ ] 文字清晰
- [ ] 主标题为 “Research that can show its work.”

---

## ⚠️ 不要上传这些文件

| 文件 | 原因 |
|---|---|
| `docs/assets/social-preview-1280x320.png` | ❌ **DEPRECATED** — 尺寸错误 (旧 GitHub 要求) 且数字过时, 已移到 `.archive/` |
| `docs/assets/social-preview-1280x320.svg` | ❌ **DEPRECATED** — 同上 |
| `docs/assets/banner.png` | ❌ 是项目 banner, 不是 social preview |
| `docs/assets/quickstart.png` | ❌ 是 quickstart 截图, 不是 social preview |

---

## 🔧 如果图片需要重新生成

```bash
cd /Users/xuzheyi/Desktop/论文-研报工作流
python scripts/gen_social_preview.py
# 会同时更新 .github/social-preview.png 和 docs/assets/social-preview.png
```

生成器从 `scripts/count_assets.py` 读取数字；仓库文件会自动更新，但 GitHub Settings 中已经上传的图片不会自动替换，指标变化后需重新上传。

---

## 📊 当前 Social Preview 内容

右侧流程与底部指标展示:
- **43** MCP Data Sources
- **58** Econometric Method Modules
- **18** AI Skills
- **30** Journal Templates (JF / 经济研究 / ...)

左侧强调可验证研究，右侧展示 Discover → Design → Evidence → Estimate → Write → Review，底部为仓库地址。
