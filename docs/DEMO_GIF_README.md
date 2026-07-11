# Demo 资产说明（SVG/PNG → GIF 升级指南）

> **审计来源**: `docs/audit/GITHUB_STAR_AUDIT_2026-07-09.md` §2.3
> **现状**: 已存在 `docs/assets/demo-terminal.svg` (4.4KB) 和 `docs/assets/quickstart.png` (177KB)
> **更新**: 2026-07-11

## 当前资产

```
docs/assets/
├── demo-terminal.svg     # 95 行终端动画 SVG (4.4KB)
└── quickstart.png        # 快速上手截图 (177KB)
.github/
├── demo/                 # 5 组架构图（PNG+SVG 双格式）
│   ├── architecture.png + architecture.svg
│   ├── skill-system.png + skill-system.svg
│   ├── mcp-servers.png + mcp-servers.svg
│   ├── pipeline.png + pipeline.svg
│   └── deployment.png + deployment.svg
└── social-preview.png    # 1280×640 社交预览图 (64KB)
```

## 升级为 GIF（待执行）

### 方案 A：asciinema + agg（推荐）

```bash
# 安装 asciinema
brew install asciinema

# 录制研究流程（≤ 15 秒）
asciinema rec demo.cast \
  --title "FinAI Research Workflow Demo" \
  --command "python scripts/start_research.py --topic 'carbon trading innovation' --stage idea-discovery"

# 转换为 GIF
pip install agg
agg demo.cast docs/assets/demo.gif --theme monokai
```

### 方案 B：Kap（macOS 屏幕录制）

```bash
# 安装 Kap（开源屏幕录制 → GIF）
brew install --cask kap

# 录制研究流程窗口 → 导出为 GIF
# 1. 打开 Kap → 选择窗口
# 2. 点击录制
# 3. 执行：python scripts/start_research.py --topic "..."
# 4. 停止录制 → 保存为 docs/assets/demo.gif
```

### 方案 C：脚本化生成（无 GUI）

```bash
# 使用 svg-term + gifski 流水线
brew install gifski

# 1. svg-term 渲染 SVG 为 PNG 序列
npx svg-term --out demo-frames --frame 50 \
  < docs/assets/demo-terminal.svg

# 2. png2gif 转 GIF
gifski --fps 20 --quality 90 \
  demo-frames/*.png \
  -o docs/assets/demo.gif
```

## 推荐参数

| 参数 | 值 | 理由 |
|------|----|----|
| 宽度 | ≤ 800 px | GitHub README 渲染最佳 |
| 时长 | 10-15 秒 | 用户注意力上限 |
| 帧率 | 15-20 fps | 平衡流畅度与文件大小 |
| 文件大小 | ≤ 2 MB | README 加载友好 |
| 循环 | 启用 | 用户无需手动重播 |

## 嵌入 README

升级完成后，README 顶部加入：

```markdown
## Quick Demo

![FinAI Research Workflow Demo](docs/assets/demo.gif)

> ⏱️ 15 秒看完完整流程：从研究主题到论文草稿
```

## 不推荐的方案

- ❌ **MP4 视频**：GitHub README 仅支持静态图片
- ❌ **WebM**：同上
- ❌ **过长 GIF**（> 30 秒）：文件大、加载慢

---

## 验证

```bash
# 检查 GIF 头
file docs/assets/demo.gif
# → GIF image data, version 89a, ...

# 检查文件大小
ls -lh docs/assets/demo.gif
# → 目标 ≤ 2 MB

# 检查尺寸
sips -g pixelWidth -g pixelHeight docs/assets/demo.gif
# → ≤ 800px 宽
```

---

**执行人**: 待用户授权（需选择 A/B/C 方案之一并录制）