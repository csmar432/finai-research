---
name: fin-ref-paper
description: 从LIT_REVIEW.md和IDEA_REPORT.md中提取参考文献，自动生成符合JF/JFE/RFS/GB-T-7714格式的references.bib，并管理引用一致性。
trigger: "参考文献|ref|bib|引用格式|citation|reference|文献引用"
version: 1.0.0
created: 2026-06-13
tags: [reference, bibtex, citation, formatting, literature]
---

# fin-ref-paper

从LIT_REVIEW.md和IDEA_REPORT.md中提取参考文献，自动生成符合JF/JFE/RFS/GB-T-7714格式的references.bib，并管理引用一致性。

## 触发条件

- 关键词: `参考文献` `ref` `bib` `引用格式` `citation` `reference` `文献引用` `BibTeX`
- Skill语法: `Skill: fin-ref-paper`
- 前置条件: 已有研究输出文件 (LIT_REVIEW.md, IDEA_REPORT.md 等)

## 参考文献管理流程

### 第一步：提取参考文献

从现有文档中自动提取参考文献信息：

```python
from scripts.ref_paper import ReferenceExtractor, ExtractedReference

extractor = ReferenceExtractor()

# 从多个来源提取
extracted = extractor.extract_from_multiple(
    sources=[
        "output/fin-literature/LIT_REVIEW.md",
        "output/fin-ideas/IDEA_REPORT.md",
        "output/fin-novelty/NOVELTY_REPORT.md",
    ]
)

print(f"提取到 {len(extracted)} 条参考文献")
for ref in extracted[:3]:
    print(f"  - {ref.author} ({ref.year}). {ref.title}. {ref.journal}.")
```

**提取的信息**:

| 字段 | 说明 | 示例 |
|------|------|------|
| author | 作者 | "Zhang, Y. and Li, X." |
| title | 标题 | "The Effect of Carbon Trading" |
| year | 年份 | 2023 |
| journal | 期刊 | "Journal of Finance" |
| volume | 卷 | "78" |
| issue | 期 | "3" |
| pages | 页码 | "1234-1289" |
| doi | DOI | "10.1111/jofi.12345" |
| url | URL | (optional) |

### 第二步：Enrich元数据

使用CrossRef API自动补全缺失信息：

```python
import requests

def get_crossref_metadata(doi: str) -> dict:
    """通过DOI获取完整的文献元数据"""
    resp = requests.get(
        f"https://api.crossref.org/works/{doi}",
        headers={"User-Agent": "fin-research/1.0 (mailto:research@example.com)"}
    )
    if resp.status_code == 200:
        return resp.json()["message"]
    return {}

def enrich_reference(ref: ExtractedReference) -> ExtractedReference:
    """补全缺失字段"""
    if ref.doi:
        meta = get_crossref_metadata(ref.doi)
        ref.volume = meta.get("volume", ref.volume)
        ref.issue = meta.get("issue", ref.issue)
        ref.pages = meta.get("page", ref.pages)
        ref.publisher = meta.get("publisher", "")
        # 规范化作者列表
        authors_raw = meta.get("author", [])
        ref.author = "; ".join([
            f"{a['family']}, {a['given'][0]}." 
            for a in authors_raw
        ])
    return ref
```

**API调用示例**:

```
GET https://api.crossref.org/works/10.1111/jofi.12345

Response:
{
  "message": {
    "title": ["The Effect of Carbon Trading on Innovation"],
    "author": [
      {"family": "Zhang", "given": "Yi"},
      {"family": "Li", "given": "Xiao"}
    ],
    "container-title": ["Journal of Finance"],
    "volume": "78",
    "issue": "3",
    "page": "1234-1289",
    "DOI": "10.1111/jofi.12345",
    "published": {"date-parts": [[2023, 6]]}
  }
}
```

### 第三步：转换为BibTeX格式

```python
def to_bibtex(ref: ExtractedReference, style: str = "jf") -> str:
    """将参考文献转换为BibTeX格式"""
    
    # 生成唯一引用键
    first_author = ref.author.split(";")[0].split(",")[0].strip()
    key = f"{first_author}{ref.year}"
    
    # 期刊缩写映射 (常见金融期刊)
    journal_abbr = {
        "Journal of Finance": "J. Finance",
        "Journal of Financial Economics": "J. Financ. Econ.",
        "Review of Financial Studies": "Rev. Financ. Stud.",
        "Quarterly Journal of Economics": "Q. J. Econ.",
        "American Economic Review": "Am. Econ. Rev.",
        "经济研究": "J. Econ. (China)",
        "金融研究": "J. Finance (China)",
    }
    
    journal = journal_abbr.get(ref.journal, ref.journal)
    
    bib_entry = f"""@article{{{key},
  author = {{{'; '.join([a.strip() for a in ref.author.split(';')])}}},
  title = {{{ref.title}}},
  journal = {{{journal}}},
  year = {{{ref.year}}},
  volume = {{{ref.volume or ''}}},
  number = {{{ref.issue or ''}}},
  pages = {{{ref.pages or ''}}},
  doi = {{{ref.doi or ''}}},
}}"""
    
    return bib_entry
```

**生成的BibTeX示例**:

```bibtex
@article{Zhang2023,
  author = {Zhang, Y. and Li, X.},
  title = {The Effect of Carbon Trading on Innovation: Evidence from China},
  journal = {J. Finance},
  year = {2023},
  volume = {78},
  number = {3},
  pages = {1234--1289},
  doi = {10.1111/jofi.12345},
}

@article{Li2022,
  author = {Li, H. and Wang, J.},
  title = {Digital Finance and Corporate Innovation: A Panel Study},
  journal = {J. Financ. Econ.},
  year = {2022},
  volume = {145},
  number = {2},
  pages = {567--589},
  doi = {10.1016/j.jfineco.2022.01.001},
}
```

### 第四步：按目标期刊格式化

```python
from scripts.ref_paper import ReferenceFormatter

formatter = ReferenceFormatter()

# JF/JFE/RFS格式 (AEA/biblio style)
jf_refs = formatter.format(refs, style="jf")
# 输出: Author (Year). Title. Journal Volume: Pages.

# GB/T 7714-2015格式 (中文顶刊)
cn_refs = formatter.format(refs, style="gb7714")
# 输出: [序号] 作者. 题目[文献类型]. 期刊名, 年, 卷(期): 页.

# 经济研究格式
jjyj_refs = formatter.format(refs, style="经济研究")
```

**格式对比**:

| 风格 | 格式示例 |
|------|----------|
| JF/JFE | Zhang, Y. and Li, X. (2023). The effect of carbon trading. *Journal of Finance*, 78(3): 1234–1289. |
| GB/T 7714 | 张三, 李四. 碳排放权交易对企业创新的影响[J]. 经济研究, 2023, 58(3): 1234-1289. |
| AEA | Zhang, Y., and X. Li. 2023. "The Effect of Carbon Trading on Innovation." *Journal of Finance* 78(3): 1234–1289. |

### 第五步：一致性审计

```python
from scripts.ref_paper import ReferenceAuditor

auditor = ReferenceAuditor()

# 检查项
issues = auditor.audit(
    bib_file="references.bib",
    tex_file="paper.tex"
)

# 问题类型
# - UNUSED_REF: .bib中有但.tex中未引用
# - MISSING_REF: .tex中引用但.bib中缺失
# - DUPLICATE: 重复条目
# - FORMAT_ERROR: 格式错误
# - CASE_MISMATCH: 作者姓名大小写不一致

for issue in issues:
    print(f"[{issue.severity}] {issue.type}: {issue.message}")
    print(f"  Location: {issue.location}")
```

**审计检查项**:

```
检查项:
□ 所有 \cite{} 键存在于 references.bib
□ 所有 references.bib 条目在 .tex 中被引用
□ 无重复条目
□ 作者姓名一致 (检查大小写)
□ DOI格式正确
□ 年份格式一致
□ 期刊名称标准化
□ 页码格式正确 (无"1234-89"应为"1234-1289")
```

## 期刊格式规范

### Journal of Finance (JF)

```
Author, A. B. and Author, C. D. (Year). Title of the article. Journal Name Volume(Number): Pages.
```

### Journal of Financial Economics (JFE)

```
Author, A. B. and C. D. Author (Year). Title. Journal Name Volume: Pages.
```

### Review of Financial Studies (RFS)

```
Author, A. B., and C. D. Author (Year). "Title of the Article." Journal Name Volume(Number): Pages.
```

### 经济研究 (GB/T 7714-2015)

```
[1] 作者1, 作者2. 文章标题[J]. 期刊名称, 年, 卷(期): 页码.
```

### 金融研究

```
[1] 作者1, 作者2. 文章标题[J]. 期刊名称, 年, 卷(期): 页码.
```

## 输出文件

### references.bib

主BibTeX文件，包含所有参考文献：

```bibtex
% 生成时间: 2026-06-13
% 目标期刊: 经济研究
% 参考文献数量: 45

@article{Zhang2023,
  author = {Zhang, Y. and Li, X.},
  title = {碳排放权交易对企业绿色创新的影响},
  journal = {经济研究},
  year = {2023},
  volume = {58},
  number = {3},
  pages = {1234--1289},
  doi = {10.1111/j.1245-2823.2023.01234},
}
```

### ref_index.md

按主题分类的文献索引：

```markdown
# 参考文献索引

## 理论基础
- Zhang2023: 碳排放权交易理论
- Li2022: 绿色创新理论框架

## 实证方法
- Callaway2021: CS-DID方法
- Sun2021: 事件研究估计

## 核心实证
- Wang2023: 碳交易对企业创新的正向影响
- Chen2022: 政策效果异质性分析
```

### ref_audit.md

一致性审计报告：

```markdown
# 参考文献一致性审计报告

## 审计时间
2026-06-13

## 问题汇总
| 问题类型 | 数量 | 严重程度 |
|----------|------|----------|
| UNUSED_REF | 3 | WARNING |
| MISSING_REF | 1 | ERROR |
| DUPLICATE | 0 | - |
| FORMAT_ERROR | 2 | WARNING |

## 详细问题

### ERROR: 引用缺失
- \cite{Huang2022} 在正文中引用但bib中不存在

### WARNING: 未使用文献
- Borusyak2024 在bib中但未在正文中引用
```

## 交互流程

```
[CHECKPOINT] 参考文献管理完成

审计结果:
✅ 所有引用键匹配
⚠️ 3条文献未使用 (可保留供附录)
✅ 格式正确

请选择:
1. 生成/更新 references.bib
2. 查看参考文献索引
3. 查看审计报告
4. 添加新文献
```

## 依赖项

- `scripts/ref_paper.py` — 参考文献管理核心
- `scripts/journal_template.py` — 期刊格式验证
- `scripts/research_framework/modern_did.py` — DID相关文献

## 约束

1. **DOI优先** — 有DOI时自动补全所有元数据
2. **格式标准化** — 按目标期刊格式输出
3. **一致性必查** — 每条引用必须有对应bib条目
4. **作者姓名规范** — 使用 "Last, First" 格式
5. **期刊缩写** — 英文期刊使用标准缩写
