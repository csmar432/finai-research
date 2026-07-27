# 知乎配图插入位置指南（中文版）

> **配套文件**：`docs/zhihu-publish/articles/01_main_article.md`
> **配图位置**：每张图下面标注了"插在第 X 节后"
> **全部中文**，适配知乎中文平台阅读体验

---

## 一、封面图（最重要）

| 文件 | 位置 | 用途 |
|------|------|------|
| `assets/cover.png` | 知乎编辑器 → "封面图" → 上传 | 文章首图，决定点击率 |

**选封面时核对**：
- 尺寸：1200×630 ✓
- 大小：89 KB ✓
- 主标题清晰可见（"AI-Powered Finance & Economics Research"）

---

## 二、正文 5 张配图（按章节顺序）

### 图 1：项目数据快照

- **位置**：第二章"它能做什么？"开头
- **文件**：`assets/figure_00_overview.png`
- **说明**：4 个核心数字的卡片仪表盘（43/47/88/12,520）
- **配图文字**：`项目数据快照 · 43 MCP / 47 方法 / 88 期刊 / 12,520 tests`

### 图 2：43 MCP 数据源分布

- **位置**：第二章"1. 数据获取：43 个 MCP 服务器"段尾
- **文件**：`assets/figure_02_mcp.png`
- **说明**：饼图 + 条形图展示 6 个类别
- **配图文字**：`43 个数据源 · 6 大类别覆盖经管研究全场景`

### 图 3：88 期刊模板分布

- **位置**：第二章"3. 论文写作"段尾
- **文件**：`assets/figure_04_journals.png`
- **说明**：4 大期刊组（英文 top 5 / 英文更多 / 中文 top 5 / 中文更多）
- **配图文字**：`88 个期刊模板 · 覆盖 JF/JFE/RFS 和经济研究/金融研究等顶刊`

### 图 4：OpenSSF Gold 徽章

- **位置**：第五章"工程实践：为什么不是又一个 Demo？"开头
- **文件**：`assets/figure_03_openssf.png`
- **说明**：金色徽章 + 21/21 评分
- **配图文字**：`OpenSSF Best Practices · Gold 等级 21/21 通过`

### 图 5：系统健康检查雷达图

- **位置**：第五章"工程实践"表格下方
- **文件**：`assets/figure_01_health.png`
- **说明**：8 维度雷达图（覆盖率 88.5/100）
- **配图文字**：`系统健康雷达 · 8 维度全绿`

---

## 三、配套跟进 1 的配图

如果是发跟进 1（`02_followup_demo.md`），额外需要 3 张截图：

| 位置 | 自己截取 |
|------|---------|
| 流水线 8 步运行截图 | 跑 `python scripts/agent_pipeline.py --topic test` 截图 |
| Callaway-Sant'Anna 估计量输出 | 跑 `python scripts/research_framework/modern_did.py` 截图 |
| 4 种估计量对比表 | 跑回归脚本后截图 |

> 这 3 张图需要您自己跑工具生成（因为是基于真实数据的输出）。

---

## 四、上传步骤

### 知乎编辑器操作

1. 打开知乎创作中心 → 写文章
2. 把主文 markdown 全部粘贴进编辑器
3. **不要使用 markdown 图片语法**（知乎不渲染）
4. 手动定位到每个图位 → 点击编辑器"插入图片"按钮 → 上传对应 PNG
5. 调整图片大小（建议 80-90% 宽度）
6. 添加图片说明（用文字标注在图片下方）

### 图片大小建议

- 封面图：完整宽度（1200px）
- 正文配图：80% 宽度（让读者有视觉缓冲）
- 重点图（如 OpenSSF 徽章）：居中 60% 宽度

### 图片位置对照表

| 主文章节 | 插入位置 | 对应文件 |
|----------|---------|---------|
| 标题下方 | 封面 | `cover.png` |
| 二、能力地图 | 数据快照 | `figure_00_overview.png` |
| 二、1. 数据获取 | MCP 分布 | `figure_02_mcp.png` |
| 二、3. 论文写作 | 期刊分布 | `figure_04_journals.png` |
| 五、工程实践 | OpenSSF 徽章 | `figure_03_openssf.png` |
| 五、工程实践 | 健康雷达 | `figure_01_health.png` |

---

## 五、自定义生成

如果想改图（数字、配色、布局），编辑：

```bash
# 封面图
python docs/zhihu-publish/tools/gen_cover.py

# 5 张正文图
python docs/zhihu-publish/tools/gen_figures.py
```

**修改入口**：
- 封面配色：在 `gen_cover.py` 顶部修改 `COLORS` 字典
- 数字更新：在 `gen_figures.py` 修改对应函数（`fig_00_overview` 等）
- 期刊列表：在 `fig_04_journals` 中修改 `sections` 数组

---

## 六、完成检查清单

发布前确认 6 张图都已上传：

- [ ] `cover.png` — 封面图
- [ ] `figure_00_overview.png` — 数据快照
- [ ] `figure_02_mcp.png` — MCP 分布
- [ ] `figure_04_journals.png` — 期刊分布
- [ ] `figure_03_openssf.png` — OpenSSF 徽章
- [ ] `figure_01_health.png` — 健康雷达

> **总计 6 张专业配图**，平均 80-100 KB，知乎编辑器上传流畅。
