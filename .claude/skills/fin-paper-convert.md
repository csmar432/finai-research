# fin-paper-convert — LaTeX 编译与格式转换

将论文草稿自动转换为目标期刊的 LaTeX 格式，编译生成 PDF，支持 IEEE/AEA/JF/JFE/RFS/CTeX 等模板。

## 功能

### 模板系统

**英文顶刊**：JF / JFE / RFS / AER / AEA / JAE / Econometrics Journal

**中文顶刊**：
- 经济研究 — CTeX 格式
- 金融研究 — CTeX 格式
- 管理世界 — CTeX 格式
- 会计研究 — CTeX 格式

### 编译流程

```bash
pdflatex → bibtex → pdflatex → pdflatex
# 中文期刊：
xelatex → bibtex → xelatex → xelatex
```

### 多版本输出

| 版本 | 用途 |
|------|------|
| main.pdf | 最终稿 |
| anonymous.pdf | 双盲审稿 |
| arxiv.pdf | arXiv 投稿 |
| word.docx | 部分期刊要求 |

### PDF 验证

- 字体嵌入检查
- 文件大小
- 页数验证
- 编译错误日志

## 核心脚本

- `scripts/journal_template.py` — 期刊模板选择
- `scripts/research_framework/report_generator.py` — LaTeX 生成

## 输出

`draft_v{version}/main.pdf`

## 调用方式

```
"编译一下论文到经济研究格式"
```
