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

### 文字质量规范（强制）

所有章节必须遵守以下规范（详见 `docs/writing-guide/ANTI_AI_WRITING_GUIDE.md`）：

**AI 味零容忍关键词**：

值得注意的是 | 综上所述 | 从某种意义上 | 客观来说 | 在一定程度上 | 某种程度上 | 相对而言 | 近年来 | 随着时代发展 | 当今社会 | 可能存在 | 有待进一步研究 | 首先我们需要 | 非常重要的 | 具有重大意义的 | 已经被 | 可以被认为 | XX研究表明

**底气五要素**（结论段必须满足至少一项）：

1. 具体数字：β = 0.463，95% CI [0.458, 1.596]，p = 0.002
2. 经济规模：占样本均值的 2.8%，相当于减少碳排放 50 万吨
3. 机制描述：通过 X 渠道，而非 Y 渠道
4. 对比发现：A 效应是 B 效应的 14.8 倍
5. 理论对应：与 Porter Hypothesis 预测一致

**表格引导句**：每张表格前 ≥2 句引导（主题句 + 来源句），后 ≥1 句解读。

**图表注释**：caption 须包含"说明什么"（而不仅是"展示什么"），含具体数字或对比描述。

**自动化检测**：

```bash
python scripts/paper_language_checker.py paper.tex
```

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
