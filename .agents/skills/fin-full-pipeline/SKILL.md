---
name: fin-full-pipeline
description: 经济金融研究端到端完整流程。从研究想法到可投稿论文，覆盖文献综述、想法生成、新颖性验证、实证方法设计、论文大纲、正文写作、图表生成、LaTeX编译和投稿前检查。
trigger: "研究...|完整流程...|从想法到论文...|端到端..."
argument-hint: "[research-direction]"
---

# fin-full-pipeline：经济金融研究端到端完整流程

端到端的经济金融学术研究流程，从用户描述研究方向开始，到生成可投稿论文 PDF 结束。

```
研究方向输入
       ↓
阶段1: FIN_BRIEF.md 生成      [FIN_BRIEF.md]
       ↓ checkpoint
阶段2: 文献综述               [LIT_REVIEW.md]
       ↓ checkpoint
阶段3: 想法生成 + 数据验证    [IDEA_REPORT.md]
       ↓【想法-数据交叉验证】← P1 强制检查点，不跳过
       ↓ checkpoint
阶段4: 新颖性验证             [NOVELTY_REPORT.md]
       ↓ checkpoint
阶段5: 实证方法设计           [REFINED_DESIGN.md]
       ↓ checkpoint
阶段6: 数据获取               [DATA_MANIFEST.md + data/*.csv]
       ↓ checkpoint
阶段7: 论文大纲               [PAPER_OUTLINE.md + FIGURE_PLAN.md]
       ↓ checkpoint
阶段8: 正文写作               [draft_v1/main.tex]
       ↓ checkpoint
阶段9: 图表生成               [draft_v1/figures/*.pdf]
       ↓ checkpoint
阶段10: 对抗性Review           [REVIEW_REPORT.md]
       ↓ checkpoint
阶段11: LaTeX编译              [draft_v1/main.pdf]
       ↓ checkpoint
阶段12: 投稿前检查             [SUBMIT_CHECK_REPORT.md]
       ↓
最终输出: 可投稿论文 PDF + 完整研究包
```

---

## 核心原则：数据优先

**数据验证必须在阶段3（想法生成）完成，不等到阶段6（数据获取）才发现无数据。**

```
传统流程（有问题）:
  想法生成 → 新颖性验证 → 实证设计 → 数据获取 ← 到这里才发现无数据！
       ↓                                    ↓
    浪费大量时间                   不得不返回更换主题

改进流程（当前）:
  想法生成 → 【想法-数据交叉验证】→ 新颖性验证 → 实证设计 → 数据获取
       ↓                                    ↓
    在此处检查数据可行性         数据已知可行，只需执行
    无数据→立即告知用户          预先设计的获取方案
```

---

## 执行前的准备

### 系统准备（每次启动必须执行）

```bash
# 检查环境并初始化输出目录（PROJECT_DIR 自动取当前目录）
PROJECT_DIR="$(pwd)"
cd "$PROJECT_DIR" || exit 1

# 创建所有输出目录
mkdir -p \
  output/fin-literature \
  output/fin-ideas \
  output/fin-novelty \
  output/fin-refinement \
  output/fin-experiments/data/finance \
  output/fin-review/round_1 \
  output/fin-manuscript/draft_v1/figures \
  output/fin-manuscript/draft_v1/tables \
  output/fin-manuscript/draft_v1/scripts

# 检查 Python 关键依赖
python3 -c "import json, yaml, pandas, numpy, matplotlib, seaborn, statsmodels; print('[✓] All Python deps OK')" 2>/dev/null \
  || echo '[!] Python deps missing — run: pip install pandas numpy matplotlib seaborn statsmodels pyyaml'

# 检查 LaTeX 编译器
for cmd in pdflatex xelatex bibtex; do
  if command -v $cmd &>/dev/null; then
    echo "[✓] $cmd"
  else
    echo "[!] $cmd not found"
  fi
done

# 检查 Docker MCP 服务是否运行
for svc in mcp_eastmoney_reports mcp_financial mcp_enhanced_finance; do
  if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
    echo "[✓] $svc running"
  else
    echo "[!] $svc not running"
  fi
done
```

### 读取上下文（步骤1）

按优先级读取已有研究上下文：

1. `FIN_RESEARCH_PLAN.md` — 详细研究计划（最优先）
2. `FIN_BRIEF.md` — 12段式研究简报（次优先）
3. 用户直接输入的研究方向（兜底）

如果两者都不存在，则需要用户描述研究方向。

---

## 阶段详解

### 阶段1：生成 FIN_BRIEF.md

**目标：** 将用户的研究方向转化为结构化的12段式研究简报。

**触发条件：** `FIN_BRIEF.md` 不存在或内容为空。

**执行方式：**

```python
# 检查是否存在
import os
if os.path.exists("FIN_BRIEF.md"):
    with open("FIN_BRIEF.md") as f:
        content = f.read().strip()
    if content:
        print("FIN_BRIEF.md 已存在，内容如下：")
        print(content[:500])
        # 展示确认菜单
        print("是否使用现有 FIN_BRIEF.md？（y/n）")
        # 等待用户输入
        # 如果用户选择 n，删除并重新生成
```

**FIN_BRIEF.md 格式（12段式）：**

```markdown
# 研究简报

## 1. 研究标题
[一句话标题，≤30字]

## 2. 研究领域
[宏观金融 / 公司金融 / 资产定价 / 金融计量 / 行为金融]

## 3. 研究问题
[一句话描述核心研究问题]

## 4. 研究类型
[实证 / 理论 / 综述 / 方法创新]

## 5. 目标期刊
[JF / JFE / RFS / 经济研究 / 金融研究 / 管理世界]

## 6. 核心假设
[H1: ... H2: ... H3: ...]

## 7. 数据来源
[A股 / 美股 / 宏观 / 跨境]

## 8. 识别策略
[DID / IV / RDD / PSM / 面板GMM]

## 9. 样本期
[YYYY-YYYY]

## 10. 核心变量
- 被解释变量（Y）：
- 解释变量（X）：
- 控制变量：

## 11. 预期结论
[预期的实证发现]

## 12. 潜在贡献
[理论贡献 / 识别策略创新 / 数据集贡献]
```

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段1：研究简报生成完成
════════════════════════════════════════════════════════════

  研究标题: [标题]
  研究领域: [领域]
  目标期刊: [期刊]
  识别策略: [策略]
  样本期:   [年份范围]

  请选择：
    (1) 确认并继续
    (2) 修改某个字段
    (3) 补充更多细节
    (4) 重新描述研究方向
```

**必须等待用户选择**，不能自动继续。

---

### 阶段2：文献综述

**目标：** 构建研究领域的完整文献地图，识别核心文献和研究缺口。

**调用技能：**

```
Skill: fin-lit-review
"[研究方向简述，从 FIN_BRIEF.md 读取]"
```

**MCP 检索组合（优先使用）：**

```
# 1. NBER 工作论文（近3年）
server: user-nber-wp
tool: get_nber_paper
params: { "query": "[研究关键词]", "year_from": 2023 }

# 2. OpenAlex 学术论文
server: user-openalex
tool: get_openalex_works
params: { "query": "[研究主题]", "per_page": 25 }

# 3. ArXiv 预印本
server: user-arxiv
tool: semantic_search
params: { "query": "[研究主题]" }

# 4. 东方财富研报（业界视角）
server: user-eastmoney-reports
tool: get_research_report
params: { "ts_code": "[相关股票代码]", "max_results": 10 }

# 5. 网络搜索（补充）
server: user-brave-search
tool: brave_web_search
params: { "query": "[研究主题 + 顶刊名]" }
```

**输出文件：**
- `output/fin-literature/LIT_REVIEW.md` — 完整文献综述（≥3000字）
- `output/fin-literature/LIT_SUMMARY.md` — 精简版（≤1000字）

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段2：文献综述完成
════════════════════════════════════════════════════════════

  核心文献:
    • [文献1]: [主要发现]
    • [文献2]: [主要发现]

  研究缺口:
    • [缺口1]: [描述]
    • [缺口2]: [描述]

  覆盖期刊: JF / JFE / RFS / 经济研究

  请选择：
    (1) 继续下一阶段
    (2) 补充检索 [具体方向] 的文献
    (3) 调整研究方向（缺口与我的想法不完全匹配）
```

---

### 阶段3：想法生成 + 想法-数据交叉验证（P1 强制检查点）

**目标：** 生成8-12个研究想法，过滤后保留数据可行的想法。

**调用技能：**

```
Skill: fin-generate-idea
"[研究方向，从 FIN_BRIEF.md 读取]"
```

#### 子步骤 3A：想法生成

**核心逻辑：**

```python
from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

config = AgentPipelineConfig(
    topic="[研究方向]",
    venue="[目标期刊]",
    research_field="[研究领域]",
    use_hitl=False,
    visualize=True,
)
pipeline = AgentPipeline(config=config)

# 生成候选想法（8-12个）
ideas = pipeline._orchestrator.generate_ideas(topic="[研究方向]")
```

**想法格式：**

```python
ideas = [
    {
        "id": "idea_001",
        "title": "关税冲击与资本结构调整速度",
        "description": "利用DID分析2018年中美关税战对企业资本结构调整速度的影响",
        "keywords": ["tariff", "capital structure", "DID", "A-share"],
        "hypothesis": "H1: 关税暴露程度越高，企业资本结构调整速度下降越显著",
        "novelty_score": 8.5,  # 1-10
        "data_feasibility": "high",  # high/medium/low
    },
    # ... 8-12个想法
]
```

**想法排序标准：**
1. 数据可行性（必须先满足）
2. 新颖性评分（目标期刊查重）
3. 理论贡献潜力
4. 实证可操作性

#### 子步骤 3B：【P1 强制】想法-数据交叉验证 ← 绝对不能跳过

**必须执行的数据验证：**

```python
from scripts.idea_data_checker import IdeaDataValidator

validator = IdeaDataValidator(ideas=ideas)
report = validator.validate_all()
validator.print_report(report)

# report.idea_results[0] 包含：
#   - idea: 原始想法
#   - feasibility: Feasibility.AVAILABLE / PARTIALLY_AVAILABLE / DATA_GAP / REQUIRES_AUTH
#   - feasibility_score: 0.0-1.0
#   - gaps: 数据缺口列表
#   - actions: 修复建议
```

**验证结果处理：**

| 可行性 | 含义 | 处理方式 |
|--------|------|---------|
| `AVAILABLE` | 真实数据可用 | ✅ 直接进入推荐名单 |
| `PARTIALLY_AVAILABLE` | 部分数据缺失 | ⚠️ 进入推荐名单，但需补充缺失数据 |
| `DATA_GAP` | 数据缺口严重 | ❌ 不进入推荐名单，需用户决策 |
| `REQUIRES_AUTH` | 需授权模拟数据 | 🔐 必须显式授权 |

**用户交互（强制）：**

```
════════════════════════════════════════════════════════════
     ⚠️  阶段3.5：想法-数据交叉验证（P1 强制检查点）
════════════════════════════════════════════════════════════

  验证结果统计:
    ✅ 数据可行:       X 个想法
    ⚠️ 部分可行:       X 个想法
    ❌ 数据缺口:       X 个想法
    🔐 需授权模拟:    X 个想法

  ──────────────────────────────────────────────────────

  ✅ 数据可行的想法（直接推进）:
    1. [想法标题]
       数据: tushare, akshare
    2. [想法标题]
       数据: tushare, esg_rating

  ⚠️ 部分可行的想法（需补充数据）:
    3. [想法标题]
       缺失: ESG评级数据
       获取途径: Wind ESG数据库 / 商道融绿

  ❌ 数据缺口的想法（无法推进）:
    4. [想法标题]
       缺失: 上市公司海关进出口明细（HS编码）
       获取途径: CSMAR海关数据库（需机构账号）
       网址: https://www.gtadata.com

  ──────────────────────────────────────────────────────

  请选择：
    (1) 选择想法1（数据可行）
    (2) 选择想法2（数据可行）
    (3) 补充缺失数据后再继续（优先获取 [数据名称]）
    (4) 授权使用模拟数据（仅演示用，论文不能发表）
    (5) 更换研究方向
```

**禁止事项：**
- ❌ 禁止跳过此检查点
- ❌ 禁止静默 fallback 到模拟数据
- ❌ 禁止将 `DATA_GAP` 状态的想法推荐给用户
- ❌ 禁止在用户未授权的情况下使用模拟数据

**硬中断条件：** 如果所有想法都是 `DATA_GAP` 且没有替代方案，流程必须停止。

```python
validated = [r for r in report.idea_results if r.feasibility in (
    Feasibility.AVAILABLE, Feasibility.PARTIALLY_AVAILABLE
)]

if not validated:
    print("⚠️  所有候选想法均无数据支持，流程硬中断")
    print("请选择：")
    print("  (1) 补充数据（将数据文件放入 data/ 目录）")
    print("  (2) 更换研究方向")
    # 等待用户输入
    # 如果用户选择继续处理，确保只有有数据的想法进入后续阶段
```

**输出文件：**
- `output/fin-ideas/IDEA_REPORT.md` — 完整想法报告（含数据验证结果）
- `output/fin-ideas/IDEA_CANDIDATES.md` — 精简版 TOP 3-5

---

### 阶段4：新颖性验证

**目标：** 在 JF/JFE/RFS/arXiv/中文顶刊中检索，确认研究想法的新颖性。

**调用技能：**

```
Skill: fin-novelty-check
"[选定想法的描述]"
```

**检索覆盖矩阵：**

| 来源 | 时间范围 | 重要性 | 检索词示例 |
|------|---------|--------|-----------|
| JF/JFE/RFS/JME | 近5年 | 最高 | `carbon trading + innovation` |
| 经济研究/金融研究/管理世界 | 近5年 | 很高（A股必查） | `碳排放权交易 + 绿色创新` |
| arXiv q-fin | 近2年 | 高 | `tariff + innovation + DID` |
| NBER Working Papers | 近3年 | 高 | `trade war + capital structure` |
| SSRN | 近2年 | 中高 | 补充检索 |
| 东方财富研报 | 无限制 | 中 | 业界视角补充 |

**输出文件：**
- `output/fin-novelty/NOVELTY_REPORT.md` — 新颖性报告

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段4：新颖性验证完成
════════════════════════════════════════════════════════════

  综合评分: X/10
  评估等级: 高度新颖 / 中度新颖 / 缺乏新颖性

  最接近的先例:
    • [文献]: [主要方法，与本研究的区别]

  主要风险:
    • [reviewer最可能引用的先例]

  差异化策略:
    • [本研究如何区分]

  请选择：
    (1) 继续细化该方向（新颖性可接受）
    (2) 调整研究角度以更好区分
    (3) 更换研究方向
    (4) 查看详细报告后再决定
```

---

### 阶段5：实证方法设计

**目标：** 将研究想法细化为完整可执行的实证方案。

**调用技能：**

```
Skill: fin-experiment-design
"[选定想法的描述 + REFINED_DESIGN.md]"
```

**识别策略选择决策树：**

```
用户描述研究方向
       ↓
是否存在明确的外生冲击事件？
       ↓ yes                    ↓ no
是否存在对照组？         是否存在工具变量？
       ↓ yes         ↓ no           ↓ yes      ↓ no
     DID           是否有       IV/2SLS    面板回归
                 清晰断点？              + 安慰剂检验
                       ↓ yes
                     RDD
```

**输出文件：**
- `output/fin-refinement/REFINED_DESIGN.md` — 细化后的研究设计
- `output/fin-refinement/EXPERIMENT_PLAN.md` — 详细实验执行计划
- `output/fin-refinement/VARIABLE_DEFINITIONS.md` — 变量定义表
- `output/fin-refinement/ROBUSTNESS_PLAN.md` — 稳健性检验方案（≥6种）
- `output/fin-refinement/ENDOGENEITY_PLAN.md` — 内生性处理方案
- `output/fin-refinement/EXECUTION_CHECKLIST.md` — 实验执行检查清单

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段5：实证方法设计完成
════════════════════════════════════════════════════════════

  识别策略: [DID / IV / RDD / 面板GMM]
  被解释变量Y: [变量名]
  核心解释变量X: [变量名]
  控制变量: [列表]
  固定效应: [类型]
  稳健性检验: [N]项
  内生性处理: [方案]

  请选择：
    (1) 确认设计方案，继续数据获取
    (2) 调整变量定义（说明要改什么）
    (3) 更换识别策略（说明原因）
    (4) 查看完整设计报告
```

---

### 阶段6：数据获取

**目标：** 根据 REFINED_DESIGN.md 获取所有所需数据。

**调用技能：**

```
Skill: fin-data-acquisition
"[REFINED_DESIGN.md]"
```

#### 【关键】数据源预检查（必须首先执行）

```python
from scripts.data_source_checker import DataSourceChecker, DataRequirement

requirements = [
    DataRequirement(
        name="financial_data",
        user_facing_name="A股财务数据",
        description="资产负债率、ROA、规模等公司财务指标",
        sources=["tushare", "wind", "csmar", "akshare"],
        required=True,
    ),
    DataRequirement(
        name="customs_data",
        user_facing_name="上市公司海关进出口明细（HS编码）",
        description="用于计算企业关税暴露强度",
        sources=["csmar_customs"],
        required=True,
    ),
    # ... 根据 REFINED_DESIGN.md 添加其他需求
]

checker = DataSourceChecker(requirements)
result = checker.run()
checker.print_report()

# 【硬中断】如果需要模拟数据
if result.requires_synthetic_data:
    from scripts.pipeline_checkpoint import InteractivePipelineCheckpoint
    cp = InteractivePipelineCheckpoint()
    authorized = cp.authorize_synthetic_or_stop(
        purpose="本研究所需的A股财务数据和海关进出口数据"
    )
    if not authorized:
        # 流程停止，用户必须：
        # - 补充真实数据，或
        # - 更换研究方向
        STOP_HERE
```

**MCP 数据获取示例：**

```yaml
# A股行情数据
server: user-tushare
tool: get_daily_quote
params:
  ts_code: "000001.SZ"
  start_date: "20200101"
  end_date: "20241231"

# 财务数据
server: user-tushare
tool: get_financial_report
params:
  ts_code: "000001.SZ"
  report_type: "income"

# 宏观数据（无需 Key）
server: user-financial
tool: get_macro_china
params:
  indicator: "gdp"

# 美股数据（无需 Key）
server: user-yfinance
tool: get_yf_historical
params:
  ticker: "AAPL"
  start_date: "2020-01-01"
  end_date: "2024-12-31"
```

**输出文件：**
- `output/fin-experiments/DATA_MANIFEST.md` — 数据清单与来源
- `output/fin-experiments/DATA_VALIDATION.md` — 数据验证报告
- `data/finance/*.csv` — 原始数据文件（**真实数据**）

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段6：数据获取完成
════════════════════════════════════════════════════════════

  数据状态:
    ✅ 已获取: [列表]
    ❌ 未获取: [列表]
    ⚠️  模拟: [列表]

  请选择：
    (1) 确认数据，继续实证分析
    (2) 补充数据后再继续
    (3) 查看详细数据状态报告
    (4) 暂停，评估数据质量后再决定
```

---

### 阶段7：论文大纲

**目标：** 基于目标期刊生成完整的论文大纲及配套文件。

**调用技能：**

```
Skill: fin-paper-plan
"[选定想法的完整描述]"
```

**输出文件：**
- `output/fin-manuscript/PAPER_OUTLINE.md` — 完整论文大纲
- `output/fin-manuscript/FIGURE_PLAN.md` — 图表计划
- `output/fin-manuscript/TABLE_PLAN.md` — 表格计划
- `output/fin-manuscript/ABSTRACT_DRAFT.md` — 摘要草稿

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段7：论文大纲生成完成
════════════════════════════════════════════════════════════

  目标期刊: [期刊名]
  预估字数: [X]字
  结构: [N]章

  大纲预览:
    1. Introduction — [约X字]
    2. Literature Review — [约X字]
    3. Hypothesis Development — [约X字]
    4. Data & Methodology — [约X字]
    5. Empirical Results — [约X字]
    6. Robustness Checks — [约X字]
    7. Conclusion — [约X字]

  图表计划: [N]张图 + [M]张表

  请选择：
    (1) 确认大纲，开始正文写作
    (2) 修改某章节内容或长度
    (3) 调整图表计划
    (4) 先保存，稍后再写
```

---

### 阶段8：正文写作

**目标：** 根据 PAPER_OUTLINE.md 和 REFINED_DESIGN.md 生成完整的论文正文草稿。

**调用技能：**

```
Skill: fin-paper-draft
"[PAPER_OUTLINE.md]"
```

**执行前准备：**

```bash
# 创建 LaTeX 目录结构（PROJECT_DIR 自动取当前目录）
PROJECT_DIR="$(pwd)"
DRAFT_DIR="$PROJECT_DIR/output/fin-manuscript/draft_v1"
mkdir -p "$DRAFT_DIR/figures" "$DRAFT_DIR/tables" "$DRAFT_DIR/scripts"
```

**输出文件：**
- `output/fin-manuscript/draft_v1/main.tex` — 主文件
- `output/fin-manuscript/draft_v1/introduction.tex`
- `output/fin-manuscript/draft_v1/literature.tex`
- `output/fin-manuscript/draft_v1/methodology.tex`
- `output/fin-manuscript/draft_v1/results.tex`
- `output/fin-manuscript/draft_v1/conclusion.tex`
- `output/fin-manuscript/draft_v1/references.bib`

---

### 阶段9：图表生成

**目标：** 生成期刊级别的图表（≥300 DPI，PDF矢量格式）。

**调用技能：**

```
Skill: fin-paper-figure
"[FIGURE_PLAN.md]"
```

**DID 研究必须生成的图表：**

1. **平行趋势图** — 政策前后实验组与对照组的趋势对比
2. **安慰剂检验图** — 随机化处理时间的系数分布
3. **动态效应图** — 事件研究框架下的各期系数

**输出文件：**
- `output/fin-manuscript/draft_v1/figures/*.pdf` — 所有图表
- `output/fin-manuscript/draft_v1/scripts/generate_figures.py` — 可复现脚本

---

### 阶段10：对抗性 Review

**目标：** 对论文正文草稿进行多轮严格评审。

**调用技能：**

```
Skill: fin-review-loop
"[draft_v1/main.tex]"
```

**Review 维度：**

| 维度 | 检查项 |
|------|--------|
| 理论贡献 | 研究缺口是否真正填补？ |
| 识别策略 | DID/IV/RDD 是否正确使用？ |
| 数据质量 | 样本选择是否存在偏误？ |
| 稳健性 | 是否有足够的稳健性检验？ |
| 写作质量 | 逻辑是否清晰？表述是否准确？ |

**输出文件：**
- `output/fin-review/REVIEW_REPORT.md` — 完整 review 报告
- `output/fin-review/REVIEW_STATE.json` — 每轮评分和状态
- `output/fin-review/round_*/` — 各轮详细 review

**checkpoint 交互：**

```
════════════════════════════════════════════════════════════
          阶段10：Review 完成
════════════════════════════════════════════════════════════

  当前轮次: X/4
  综合评分: X/10
  接受建议: [接受 / 大修 / 小修]

  主要问题:
    • [问题1]
    • [问题2]

  是否需要修改后重新提交？
```

---

### 阶段11：LaTeX 编译

**目标：** 编译生成可投稿的 PDF 文件。

**编译脚本：**

```bash
PROJECT_DIR="$(pwd)"
DRAFT_DIR="$PROJECT_DIR/output/fin-manuscript/draft_v1"
cd "$DRAFT_DIR"

# 检测期刊类型
if grep -qi "经济研究\|金融研究\|管理世界\|中国工业经济" main.tex; then
  COMPILER=xelatex
else
  COMPILER=pdflatex
fi

# 完整编译流程
$COMPILER -interaction=nonstopmode main.tex
bibtex main
$COMPILER -interaction=nonstopmode main.tex
$COMPILER -interaction=nonstopmode main.tex

# 检查结果
if [ -f "main.pdf" ]; then
  echo "✅ 编译成功: main.pdf"
else
  echo "❌ 编译失败，查看 compile_log.txt"
fi
```

**输出文件：**
- `output/fin-manuscript/draft_v1/main.pdf`
- `output/fin-manuscript/draft_v1/compile_log.txt`

---

### 阶段12：投稿前检查

**目标：** 全面检查匿名性、格式、图表、引用、参考文献等所有投稿必需项。

**调用技能：**

```
Skill: fin-submit-check
"[draft_v1/]"
```

**输出文件：**
- `output/fin-review/SUBMIT_CHECK_REPORT.md` — 检查报告
- `output/fin-review/SUBMIT_CHECK_ISSUES.md` — 待修复问题清单

---

## 完整输出文件结构

```
output/
├── FIN_BRIEF.md                    ← 研究简报
├── fin-literature/
│   ├── LIT_REVIEW.md              ← 完整文献综述
│   └── LIT_SUMMARY.md            ← 精简版
├── fin-ideas/
│   ├── IDEA_REPORT.md             ← 完整想法报告
│   └── IDEA_CANDIDATES.md         ← TOP 3-5 候选
├── fin-novelty/
│   └── NOVELTY_REPORT.md          ← 新颖性验证
├── fin-refinement/
│   ├── REFINED_DESIGN.md          ← 研究设计
│   ├── EXPERIMENT_PLAN.md         ← 实验计划
│   ├── VARIABLE_DEFINITIONS.md    ← 变量定义
│   ├── ROBUSTNESS_PLAN.md         ← 稳健性方案
│   ├── ENDOGENEITY_PLAN.md        ← 内生性方案
│   └── EXECUTION_CHECKLIST.md     ← 执行清单
├── fin-experiments/
│   ├── DATA_MANIFEST.md           ← 数据清单
│   ├── DATA_VALIDATION.md         ← 数据验证
│   └── data/finance/*.csv         ← 原始数据
├── fin-review/
│   ├── REVIEW_REPORT.md           ← Review 报告
│   ├── REVIEW_STATE.json          ← 评分状态
│   ├── SUBMIT_CHECK_REPORT.md     ← 投稿检查
│   └── round_*/                   ← 各轮详情
└── fin-manuscript/
    ├── PAPER_OUTLINE.md            ← 论文大纲
    ├── FIGURE_PLAN.md              ← 图表计划
    ├── TABLE_PLAN.md               ← 表格计划
    ├── ABSTRACT_DRAFT.md          ← 摘要草稿
    └── draft_v1/
        ├── main.tex                ← 主文件
        ├── introduction.tex
        ├── literature.tex
        ├── methodology.tex
        ├── results.tex
        ├── conclusion.tex
        ├── references.bib
        ├── figures/*.pdf           ← 图表
        ├── tables/
        ├── scripts/generate_figures.py
        ├── main.pdf                ← 编译后 PDF
        └── compile_log.txt
```

---

## 禁止模式（Forbidden Patterns）

以下行为绝对禁止：

| 禁止行为 | 说明 |
|---------|------|
| 静默 fallback 到模拟数据 | 必须显式告知用户并获取授权 |
| 跳过想法-数据交叉验证 | 阶段 3.5 是 P1 强制检查点 |
| 跳过 checkpoint | 每个阶段完成后必须等待用户确认 |
| 在正文中写入模拟数据的回归系数 | 实证实数必须来自真实数据 |
| 跳过新颖性验证 | 必须检索目标期刊确认新颖性 |
| 不标注数据来源 | 所有图表必须标注数据来源 |
| 自动选择研究方向 | 用户必须明确选择 |

---

## 关键模块引用

### AgentPipeline（主类）

```python
from scripts.agent_pipeline import AgentPipeline, AgentPipelineConfig

# 基本用法
config = AgentPipelineConfig(
    topic="[研究方向]",
    venue="[目标期刊]",
    research_field="[研究领域]",
    use_hitl=False,
    visualize=True,
)
pipeline = AgentPipeline(config=config)
result = pipeline.run(topic="[研究方向]")
```

### IdeaDataValidator（想法-数据验证）

```python
from scripts.idea_data_checker import IdeaDataValidator, Feasibility

validator = IdeaDataValidator(ideas=ideas)
report = validator.validate_all()

# 检查结果
for idea_result in report.idea_results:
    if idea_result.feasibility == Feasibility.AVAILABLE:
        # ✅ 数据可行
    elif idea_result.feasibility == Feasibility.PARTIALLY_AVAILABLE:
        # ⚠️ 部分可行，需补充
    elif idea_result.feasibility == Feasibility.DATA_GAP:
        # ❌ 数据缺口，不推荐
```

### DataSourceChecker（数据源预检查）

```python
from scripts.data_source_checker import DataSourceChecker, DataRequirement

requirements = [
    DataRequirement(
        name="financial_data",
        user_facing_name="A股财务数据",
        sources=["tushare", "akshare"],
        required=True,
    ),
]
checker = DataSourceChecker(requirements)
result = checker.run()

if result.requires_synthetic_data:
    # 硬中断，必须用户授权
    pass
```

### InteractivePipelineCheckpoint（强制交互）

```python
from scripts.pipeline_checkpoint import InteractivePipelineCheckpoint, Stage, DecisionOption

cp = InteractivePipelineCheckpoint()
cp.wait_at_checkpoint(
    stage=Stage.DATA_ACQUISITION,
    summary="数据获取完成",
    next_options=[
        DecisionOption("proceed", "运行实证回归", "使用当前数据直接跑回归"),
        DecisionOption("supplement", "补充数据后继续", "获取更多数据后再跑"),
    ],
)
```

---

## 快速命令参考

```bash
# 启动完整流水线
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响" --venue "经济研究"

# 快速想法验证
python scripts/idea_data_checker.py --ideas "关税+DID" --validate

# 数据源预检查
python scripts/data_source_checker.py --requirements tariff_research

# 编译论文
python scripts/research_framework/pipeline.py --topic "..." --compile

# 检查系统状态
python scripts/health_check.py
```
