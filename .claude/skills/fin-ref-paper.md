# fin-ref-paper — 参考文献管理与格式规范化

从 `LIT_REVIEW.md` 和 `IDEA_REPORT.md` 中提取参考文献，自动生成符合 JF/JFE/RFS/GB-T-7714 格式的 `references.bib`，并管理引用一致性。

## 功能

### 参考文献提取

从已有文档中提取 BibTeX 条目：
- `LIT_REVIEW.md`
- `IDEA_REPORT.md`
- `PAPER_OUTLINE.md`

### 格式支持

| 格式 | 适用 |
|------|------|
| JF/JFE/RFS | 英文顶刊 |
| AER | AEA 系列 |
| GB/T 7714-2015 | 中文顶刊 |
| BibLaTeX | 现代模板 |

### 参考文献类型

- 期刊论文（journal article）
- Working Papers（NBER / arXiv）
- 中文期刊
- 专著（books）
- 会议论文

### 增强流程

1. CrossRef DOI API 补全元数据
2. Google Scholar 补充引用信息
3. 本地引用一致性审计

## 输出

| 文件 | 说明 |
|------|------|
| `references.bib` | 主参考文献文件 |
| `ref_index.md` | 按主题分类的索引 |
| `ref_audit.md` | 引用审计报告 |

## 调用方式

```
"生成论文参考文献bib文件"
"检查一下引用格式是否正确"
```
