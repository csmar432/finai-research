# 论文-研报工作流 · 快速参考

> 本文件是项目快速参考指南。完整文档见根目录 [使用指南.md](使用指南.md)（993行，13章）或 [README.md](README.md)。

---

## 常用命令

```bash
# 健康检查
python scripts/health_check.py --json

# 完整流水线
python scripts/agent_pipeline.py --topic "研究主题"

# 演示研报（无需配置）
python scripts/demo_research_report.py --stock 000001.SZ

# 分步骤执行
python scripts/research_framework/pipeline.py --mode lit-review --topic "..."
python scripts/research_framework/pipeline.py --mode regression --topic "..."

# 数据预检查
python scripts/data_source_checker.py
python scripts/idea_data_checker.py

# MCP 工具列表
python scripts/core/mcp_tool_market.py --dir mcp_servers --search "gdp"

# 期刊模板
python scripts/journal_template.py --list
python scripts/journal_template.py --generate JFE output.tex
```

## Skill 速查

| 技能 | 用途 | 示例 |
|------|------|------|
| `fin-full-pipeline` | 端到端流水线 | `Skill: fin-full-pipeline "关税与A股创新"` |
| `fin-lit-review` | 文献综述 | `Skill: fin-lit-review "碳排放权 DID"` |
| `fin-generate-idea` | 想法生成 | `Skill: fin-generate-idea "绿色金融"` |
| `fin-novelty-check` | 新颖性验证 | `Skill: fin-novelty-check "研究标题"` |
| `fin-experiment-design` | 实证设计 | `Skill: fin-experiment-design "研究主题"` |
| `fin-paper-draft` | 正文写作 | `Skill: fin-paper-draft "PAPER_OUTLINE.md"` |
| `fin-paper-figure` | 图表生成 | `Skill: fin-paper-figure "FIGURE_PLAN.md"` |
| `fin-review-loop` | Review 循环 | `Skill: fin-review-loop "draft_v1/"` |
| `fin-paper-convert` | LaTeX 编译 | `Skill: fin-paper-convert "draft_v2/"` |

## MCP 数据优先级

```
A股数据    → user-tushare     (需 TUSHARE_TOKEN)
美股数据    → user-yfinance   (无需 Key)
中国宏观    → user-financial  (无需 Key)
全球宏观    → user-wb-data   (无需 Key)
学术论文    → user-openalex   (无需 Key)
论文全文    → user-context7   (无需 Key)
ArXiv/NBER  → user-arxiv / user-nber-wp (无需 Key)
```

## 实证方法速查

```
有政策实验   → DID（modern_did.py）
  └─ 交错处理 → Callaway-SantAnna / Sun-Abraham / Borusyak
无对照组    → 合成控制（synthetic_control.py）
有内生性    → IV/2SLS（iv_panel.py）
动态面板    → Panel GMM（iv_panel.py）
有清晰断点  → RDD（rdd.py）
```

## 期刊字数参考

| 期刊 | 字数 |
|------|------|
| JF / JFE | ~40,000 词 |
| RFS | ~45,000 词 |
| JME | ~35,000 词 |
| 经济研究 / 金融研究 | ~20,000 字 |
| 管理世界 | ~15,000 字 |

## 输出目录

```
output/fin-literature/    ← 文献综述
output/fin-ideas/          ← 研究想法
output/fin-novelty/        ← 新颖性验证
output/fin-refinement/     ← 研究设计
output/fin-experiments/    ← 实证结果
output/fin-manuscript/     ← 论文草稿（LaTeX）
output/fin-review/         ← 对抗性 review
papers/                    ← 研报输出
```

## 核心原则

1. **数据优先** — 想法阶段即验证数据可行性
2. **禁止静默 Fallback** — 模拟数据必须用户授权
3. **强制 Checkpoint** — 每阶段完成后等待用户确认
4. **生成-评审分离** — 写作和 review 由不同模块处理

---

> 完整文档：[论文写作工作流使用指南](使用指南.md)（993 行，13 章）
