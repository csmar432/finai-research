# fin-paper-draft — 论文正文写作

根据 `PAPER_OUTLINE.md` 大纲和 `REFINED_DESIGN.md` 研究设计，生成完整的论文正文草稿（英文/中文），覆盖 Introduction 到 Conclusion 所有章节。

## 功能

### 章节覆盖

| 章节 | 中文期刊 | 英文期刊 |
|------|---------|---------|
| Abstract | 摘要 | Abstract |
| Introduction | 引言 | Introduction |
| Literature & Hypotheses | 文献综述与假说 | Literature Review + Hypotheses Development |
| Data & Methodology | 数据与研究设计 | Data & Methodology |
| Empirical Results | 实证结果 | Empirical Results |
| Robustness | 稳健性检验 | Robustness Checks |
| Conclusion | 结论 | Conclusion |
| References | 参考文献 | References |

### LaTeX 输出

- 英文顶刊（JF/JFE/RFS 风格）
- 中文顶刊（经济研究/金融研究/管理世界风格）

### 核心脚本

- `scripts/research_framework/report_generator.py` — LaTeX 报告生成
- `scripts/journal_template.py` — 期刊模板系统

## 输出

各章节 `.tex` 文件：
- `introduction.tex`
- `literature.tex`
- `methodology.tex`
- `results.tex`
- `conclusion.tex`
- `references.bib`

## 调用方式

```
"帮我写Introduction部分，关于DID方法研究关税对A股企业创新的影响"
```
