---
name: fin-submit-check
description: 根据目标期刊要求，对论文进行投稿前全面检查，涵盖格式、引用、图表、数据可用性等所有投稿必需项。
trigger: "投稿前检查|submit check|格式检查|合规检查|投稿检查"
version: 1.0.0
created: 2026-06-13
tags: [paper, submission, check, format, journal]
---

# fin-submit-check

根据目标期刊要求，对论文进行投稿前全面检查，涵盖格式、引用、图表、数据可用性等所有投稿必需项。

## 触发条件

- 关键词: `投稿前检查` `submit check` `格式检查` `合规检查` `投稿检查` `论文检查`
- Skill语法: `Skill: fin-submit-check`
- 前置条件: 已有完整的论文草稿 (`.tex` 文件)

## 十大检查类别

### 1. 匿名性检查 (双盲审稿)

```
检查项:
□ 作者姓名未出现在正文、致谢、基金声明中
□ 无"感谢XX老师的指导"类致谢
□ 基金编号是否匿名化处理
□ 运行 latexmk 或 pdflatex 后检查 .log 中是否有 "[author name] removed"

检查命令:
grep -i "author" paper.tex
grep -i "感谢" paper.tex
grep "removed" paper.log || echo "No author info found"
```

### 2. 格式检查

```
检查项:
□ 字数/页数在限制内
□ 行距正确 (单倍/双倍)
□ 页边距符合要求
□ 字体要求满足 (如 JF 要求 Times New Roman 12pt)
□ 标题格式正确
□ 脚注格式正确

针对 JF/JFE:
- 主文本不超过 50 页 (含参考文献)
- 12pt Times New Roman
- 双倍行距
- 2.54cm 页边距
```

### 3. 图表分辨率检查

```python
from PIL import Image
from pathlib import Path

def check_figure_resolution(figures_dir: str, min_dpi: int = 300) -> list:
    """检查所有图表分辨率"""
    issues = []
    for f in Path(figures_dir).glob("*.png"):
        img = Image.open(f)
        dpi = img.info.get("dpi", (72, 72))
        if min(dpi) < min_dpi:
            issues.append(f"LOW DPI: {f} = {dpi}")
        print(f"{f.name}: {dpi[0]:.0f} x {dpi[1]:.0f} DPI")
    return issues

# 执行
issues = check_figure_resolution("figures/", min_dpi=300)
```

```
检查项:
□ 所有图表 >= 300 DPI
□ 图表有清晰标题
□ 图表在正文中被引用
□ 图表编号连续
□ EPS/PDF 格式用于矢量图
□ PNG/JPEG 用于位图
```

### 4. 引用完整性检查

```
检查项:
□ 无 [?], [citation needed] 等占位符
□ 所有参考文献 .bib 条目都在正文中被引用
□ 所有引用的文献都在 .bib 中
□ DOI 链接有效
□ 无重复引用

检查命令:
grep -c "\[?\]" paper.tex  # 应为 0
grep -c "\\cite{" paper.tex
```

### 5. 参考文献格式检查

```
检查项:
□ JF/JFE 格式: Author (Year). Title. Journal Volume: Pages.
□ 经济研究/金融研究: GB/T 7714-2015
□ 作者姓名格式一致
□ 期刊名称缩写正确
□ 年份准确

验证命令:
python scripts/journal_template.py --validate-refs --journal JF

常见格式错误:
❌ Author, A. B. (Year). Title. Journal. -> 缺少卷期页
❌ Author, A. (ed.). Title. -> 作者格式不一致
```

### 5. 引用真实性核查 (CitationVerifier)

```
检查项:
□ 核心引用（≥5篇）已在 Semantic Scholar / CrossRef 中验证
□ 验证率 ≥ 90%（≥90% 的引用能被外部数据库确认）
□ 引用可信度得分 ≥ 0.8
□ 无无法验证的虚构引用

阈值标准:
✅ PASS: 验证率 ≥ 90%，且核心引用均已验证
⚠️  WARN: 验证率 70-89%，需人工逐条核对
❌ FAIL: 验证率 < 70%，或发现虚构引用

验证命令:
python scripts/core/citation_verifier.py "Author (2020). Title. Journal."

CitationVerifier 在流水线中的调用路径:
  AgentPipeline._ensure_initialized()
    → AgentOrchestrator.register_default_agents(citation_verifier=self._verifier)
      → LiteratureReviewAgent.__init__(gateway, citation_verifier=citation_verifier)
        → self._citation_verifier.verify_batch(candidates)
          → Semantic Scholar / CrossRef API
```

### 6. 公式编号检查

```
检查项:
□ 所有公式都有编号
□ 编号连续无跳跃
□ 交叉引用有效 (\eqref{eq:xxx})
□ 重要公式有名称标注

检查命令:
grep "\\label{" paper.tex | grep -v "fig:" | grep -v "tab:" | wc -l
grep -E "\\ref\{eq:" paper.tex | sort -u
```

### 7. 数据可用性声明

```
检查项:
□ 数据可用性声明存在
□ 代码可用性声明存在
□ 数据集描述完整 (来源、时间、样本量)
□ 补充材料列表完整

声明模板 (JF 要求):
We will make our data and code available to reproduce the results.

声明模板 (中文顶刊):
"数据集和代码可根据作者要求提供" 或 "已上传至XXX平台"
```

### 8. 附录检查

```
检查项:
□ 所有互联网附录有链接或说明
□ 变量定义表完整
□ 稳健性检验结果在附录或正文
□ 额外测试结果标注清晰

变量定义表必需项:
□ 变量名称
□ 变量定义/计算方法
□ 数据来源
□ 预期符号
```

### 9. 语法与语言检查

```
检查项:
□ 无语法错误
□ 技术术语一致
□ 动词时态正确 (现在时描述方法，过去时描述结果)
□ 冠词使用正确

工具推荐:
- LanguageTool (命令行版本)
- Grammarly API
- WriteGood

检查命令:
languagetool paper.tex
writegood paper.tex
```

### 10. LaTeX 编译检查

```
检查项:
□ 0 编译错误
□ 0 编译警告 (或警告可忽略)
□ 无 overfull/underfull hbox
□ 字体嵌入验证
□ 目录/引用完整

编译命令:
pdflatex -interaction=nonstopmode paper.tex
biber paper  # 处理参考文献
pdflatex paper.tex
pdflatex paper.tex  # 第二次编译

检查日志:
grep -i "error" paper.log
grep -i "warning" paper.log
grep "Overfull\|Underfull" paper.log
```

### 11. AI 内容披露核查 (必检)

```
检查项:
□ LaTeX 文档包含 AI 辅助写作声明脚注
□ 声明中包含"需要独立验证"或类似免责表述
□ 若使用模拟数据，该数据已被明确标注（SIMULATED 标签或红色警示）

# 自动检测命令
grep -i "AI assistance\|AI-assisted\|AI draft\|generated with AI" paper.tex
grep -i "independent verification\|需要独立验证\|empirical results require" paper.tex

# 若使用模拟数据，还需检查
grep -i "SIMULATED\|demonstration\|演示" paper.tex

声明模板 (英文期刊):
\textit{[This manuscript was drafted with AI assistance.
All empirical results require independent verification before submission.]}

声明模板 (中文期刊):
\textit{[本文由 AI 辅助生成。所有实证结果在投稿前需经独立验证。]}

严重问题判定:
❌ FAIL: 文档无任何 AI 披露声明
❌ FAIL: 使用模拟数据但未标注
⚠️  WARN: AI 披露存在但不规范（缺失免责表述）
```

## 期刊特定检查清单

### Journal of Finance (JF)

```
□ 双盲审稿 (匿名所有作者信息)
□ 不超过 50 页主文本
□ Times New Roman 12pt
□ 双倍行距
□ 匿名指南: https://www.afajof.org/
□ Online Appendix 必需
□ Data and Code Availability Statement 必需
```

### Journal of Financial Economics (JFE)

```
□ 双盲审稿
□ 不超过 50 页
□ Times New Roman 12pt
□ 双倍行距
□ Data Availability Statement 必需
```

### 经济研究

```
□ 作者信息页单独
□ 中文参考文献格式: GB/T 7714-2015
□ 英文参考文献需翻译
□ 3000-15000 字
□ 摘要 200-300 字
□ 资助基金标注
```

### 金融研究

```
□ 作者信息页单独
□ 中文参考文献格式: GB/T 7714-2015
□ 不超过 20000 字
□ 摘要 200 字左右
□ 图表有中英文标题
```

## 输出文件

### SUBMIT_CHECK_REPORT.md

```markdown
# 投稿前检查报告
生成时间: 2026-06-13
目标期刊: JF

## 检查摘要
| 类别 | 状态 | 问题数 |
|------|------|--------|
| 匿名性 | ✅ PASS | 0 |
| 格式 | ⚠️ WARN | 2 |
| 图表分辨率 | ✅ PASS | 0 |
| 引用完整性 | ✅ PASS | 0 |
| 参考文献格式 | ❌ FAIL | 5 |
| 公式编号 | ✅ PASS | 0 |
| 数据可用性 | ⚠️ WARN | 1 |
| 附录 | ✅ PASS | 0 |
| 语法检查 | ⚠️ WARN | 3 |
| LaTeX编译 | ✅ PASS | 0 |
| AI内容披露 | ⚠️ WARN | 1 |
| 引用真实性 | ⚠️ WARN | 2 |

## 总体状态: ⚠️ 需要修复后投稿
```

### SUBMIT_CHECK_ISSUES.md

```markdown
# 详细问题清单

## ❌ 严重问题 (必须修复)

### 参考文献格式
1. Line 45: 作者姓名格式不一致 (应为 "Last, First" 格式)
2. Line 78: 缺少期刊卷号
3. Line 112: DOI 格式错误

## ⚠️ 警告 (建议修复)

### 格式
1. 行距略大于双倍行距
2. 图表标题字体小于正文

### 语法
1. Line 156: 语法错误 "the results shows" -> "the results show"
2. Line 203: 冠词缺失 "in figure" -> "in Figure"
```

## 交互流程

```
[CHECKPOINT] 投稿前检查完成。

问题汇总: 2个严重问题，4个警告

请选择:
1. 修复所有问题 → 自动生成修复建议
2. 查看详细问题清单 → 展示 SUBMIT_CHECK_ISSUES.md
3. 跳过检查 → 继续投稿流程
```

## 依赖项

- `scripts/journal_template.py` — 期刊模板和格式验证
- `scripts/health_check.py` — LaTeX 环境检查
- `scripts/research_framework/fin_charts.py` — 图表分辨率检查

## 约束

1. 必须完整执行全部12类检查
2. 每类检查必须给出明确的 PASS/WARN/FAIL 状态
3. 问题清单必须具体到行号或位置
4. 修复建议必须可操作
5. 达到 FAIL 状态时不得继续投稿流程
