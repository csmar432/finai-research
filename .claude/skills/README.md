# 知识库

> 论文-研报工作流的知识管理和技能文档中心。

## 目录结构

```
knowledge/
├── skills/              # 技能文档真相源（18个文件：17个技能.md + 1个README.md索引）
│   ├── README.md        # 总索引（本文件）
│   ├── fin-full-pipeline.md
│   ├── fin-idea-discovery.md
│   ├── fin-lit-review.md
│   ├── fin-generate-idea.md
│   ├── fin-novelty-check.md
│   ├── fin-experiment-design.md
│   ├── fin-paper-writing.md
│   ├── fin-paper-draft.md
│   ├── fin-paper-plan.md
│   ├── fin-paper-figure.md
│   ├── fin-paper-convert.md
│   ├── fin-review-loop.md
│   ├── fin-submit-check.md
│   ├── fin-data-acquisition.md
│   ├── fin-brief-generator.md
│   ├── fin-ref-paper.md
│   └── fin-viz-launch.md
├── chapters/           # 论文章节模板（预留）
├── outlines/           # 研究大纲模板（预留）
└── papers/             # 参考论文（预留）
```

## 技能文档（skills/）

`knowledge/skills/` 是**唯一真相源**，通过目录副本共享给多个工具：

| 目录副本 | 适用工具 |
|---------|---------|
| `.claude/skills/` | Claude Code |
| `.github/skills/` | GitHub Copilot |
| `.cursor/skills/` | Cursor（**独立副本**，非符号链接）|

**不依赖 Cursor Skill 系统的工具**（Claude Code、Copilot）通过读取这些 `.md` 文件来了解每个技能的功能。

共计 **17** 个技能文档，分布在 18 个文件（含本索引 README.md）。

### 17 个技能概览

| 类别 | 技能 | 功能 |
|------|------|------|
| **完整流程** | `fin-full-pipeline` | 端到端研究流水线 |
| **想法发现** | `fin-idea-discovery` | 从方向到可执行方案 |
| **文献综述** | `fin-lit-review` | 系统性文献搜索 + 引文网络 |
| | `fin-generate-idea` | 8-12 个想法生成 + 数据验证 |
| | `fin-novelty-check` | 新颖性验证（顶刊查重）|
| **实证设计** | `fin-experiment-design` | DID/IV/RD/PSM 完整方案 |
| **数据获取** | `fin-data-acquisition` | MCP 数据拉取 + 回归脚本 |
| **论文写作** | `fin-paper-plan` | 大纲生成 |
| | `fin-paper-draft` | 正文生成（LaTeX）|
| | `fin-paper-writing` | 写作编排协调 |
| **图表生成** | `fin-paper-figure` | matplotlib 图表（≥300 DPI）|
| | `fin-viz-launch` | 自然语言 → 学术图表 |
| **格式输出** | `fin-paper-convert` | LaTeX 编译 |
| **质量保证** | `fin-review-loop` | 多轮对抗性 review |
| | `fin-submit-check` | 投稿前检查 |
| **辅助工具** | `fin-brief-generator` | 生成 FIN_BRIEF.md |
| | `fin-ref-paper` | BibTeX 参考文献管理 |

## 其他知识位置

| 知识类型 | 管理位置 | 说明 |
|---------|---------|------|
| 角色规则 | `.cursor/rules/*.mdc` | 分析师/研究员/论文助手规范（Cursor 专用）|
| Agent 定义 | `.cursor/agents/*.md` | literature-scout 等 Agent 行为定义（Cursor 专用）|
| 研究简报 | `FIN_BRIEF.md` | 每个项目的上下文起点 |
| 项目总入口 | `CLAUDE.md` | 三工具统一入口文档 |

## 知识管理原则

1. **单一真相源** — 技能文档只保存在 `knowledge/skills/`，其他地方通过目录副本引用
2. **工具无关** — 文档使用通用 Markdown，不含工具特定语法
3. **自然语言驱动** — 在 Claude Code / Copilot 中直接用自然语言描述需求即可
4. **上下文驱动** — Agent 通过研究输出文件（`output/`）获取上下文，而非预存知识
