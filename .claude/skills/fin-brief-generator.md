# fin-brief-generator — 研究简报生成

根据用户输入或已有研究输出（文献综述/想法报告/新颖性报告），自动生成或更新 `FIN_BRIEF.md`。可从已有输出推断字段值，减少用户填写负担。

## 功能

### 三种工作模式

| 模式 | 适用场景 |
|------|---------|
| 推理模式（Inference）| 有既往输出（LIT_REVIEW.md / IDEA_REPORT.md / NOVELTY_REPORT.md）|
| 问卷模式（Questionnaire）| 有部分信息，需补充 |
| 快问快答（Quick Q&A）| 从零开始 |

### 增强工具（2026-06）

| 工具 | 功能 |
|------|------|
| `PolicyDatabase` | 23 个中国准自然实验数据库 |
| `AShareVariableFetcher` | 8 个 A 股特殊变量 |
| Chinese Literature MCP | 百度学术 + OpenAlex 中文 |
| `FinancialChartFactory` | 20 个图表模板 |
| `PaperQualityScorer` | 论文质量评分 |

### 收集字段

- 研究主题 / 领域
- 目标期刊 / 地域范围
- 数据来源 / 计算资源
- 研究类型 / 方法偏好
- 行为控制（AUTO_PROCEED / HUMAN_CHECKPOINT / REVIEWER_DIFFICULTY）

## 输出

`FIN_BRIEF.md` — 研究简报

## 调用方式

```
"生成研究简报"
"根据已有的文献综述更新FIN_BRIEF.md"
```
