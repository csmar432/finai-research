# 知识库

> 本目录为空占位目录。Agent 相关领域知识已迁移到 `.cursor/skills/` 和 `.cursor/rules/` 中管理。

## 目录结构

```
knowledge/
├── chapters/      # 论文章节模板（预留）
├── outlines/      # 研究大纲模板（预留）
└── papers/       # 参考论文（预留）
```

## 知识管理策略

Agent 的领域知识通过以下途径管理：

| 知识类型 | 管理位置 | 说明 |
|---------|---------|------|
| 技能定义 | `.cursor/skills/fin-*/SKILL.md` | 每个技能有独立 markdown 文件 |
| 领域规则 | `.cursor/rules/*.mdc` | 经济金融研究规范 |
| 研究简报 | `FIN_BRIEF.md` | 每个研究项目的上下文起点 |
| 研究简报 | `FIN_RESEARCH_PLAN.md` | 详细研究计划（可选） |
| 期刊格式 | `.cursor/skills/fin-paper-*/SKILL.md` | JF/JFE/RFS/CTeX 格式规范 |

## 为何不在此目录存储知识？

1. **Skill 优先**：所有 agent 操作规程通过 markdown skill 文件驱动，而非静态知识库
2. **动态更新**：skill 文件由 agent 在研究过程中实时生成和更新
3. **上下文驱动**：agent 通过读取当前研究的输出文件（output/）获取上下文，而非预存知识

## 如需添加知识文件

请在以下位置之一添加：

- **领域知识** → `.cursor/knowledge/`（需先创建目录）
- **参考论文** → `papers/`（推荐 PDF 格式）
- **大纲模板** → `knowledge/outlines/`
- **章节模板** → `knowledge/chapters/`

## 当前状态

- `papers/us_esg_financing/` 包含一篇参考论文的相关材料
