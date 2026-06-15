# Demo Assets

This directory contains visual assets for the project README and documentation.

## 5 张互补架构图 (5 Complementary Diagrams)

| # | 文件 | 一句话 | 视角 |
|---|---|---|---|
| 1 | `01-architecture-overview.svg/png` | 5 层端到端架构 (用户→接口→核心→技能→数据) | 高层鸟瞰 |
| 2 | `02-skill-system-map.svg/png` | 17 个 skill 完整体系 (4 阶段) | 技能层 |
| 3 | `03-mcp-ecosystem-map.svg/png` | 44 个 MCP server 生态 (8 类别 + 中心) | 数据层 |
| 4 | `04-research-pipeline.svg/png` | 8 步研究流水线 (想法→论文) | 流程层 |
| 5 | `05-deployment-data-flow.svg/png` | 部署/数据流 + 3 层安全边界 | 运维层 |

**设计原则**：每张图只讲一个故事，互不重叠。统一暗色背景 16:10 比例。

**自动生成**：
```bash
python scripts/gen_architecture_diagrams.py
# 输出 → .github/demo/0[1-5]-*.{svg,png}
```

**转换 PNG**（需要 rsvg-convert）：
```bash
brew install librsvg
for f in .github/demo/0[1-5]-*.svg; do
  rsvg-convert -w 1600 -h 1000 "$f" -o "${f%.svg}.png"
done
```
2. Save it in this directory
3. Update the README.md image link to point to your file
4. Commit and push to GitHub
