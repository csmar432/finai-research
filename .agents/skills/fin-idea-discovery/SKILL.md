---
name: fin-idea-discovery
description: 经济金融研究的完整想法发现流程。从研究方向出发，经过文献综述、想法生成、新颖性验证、实证方法设计和数据获取，输出经过数据实证验证的可执行研究方案。
argument-hint: [research-direction]
---

# 经济金融研究想法发现流程

从研究方向 `$ARGUMENTS` 开始，经过系统化流程，输出经过数据验证的可执行研究方案。

## 流程概览

```
研究方向输入
     ↓
阶段1: 研究方向理解 — 解析研究领域（绿色金融/数字金融/ESG/碳经济学/宏观金融/公司金融）
     ↓
阶段2: 文献综述 — 使用 MCP 工具搜索 OpenAlex/ArXiv/NBER/中文顶刊
     ↓
阶段3: 研究缺口识别 — 从文献中识别 3-5 个具体研究缺口
     ↓
阶段4: 想法生成 — 从缺口生成 8-12 个研究想法
     ↓
阶段5: 新颖性预检查 — 对每个想法快速检索 arXiv/NBER
     ↓
阶段6: 【强制】想法-数据交叉验证 — 使用 idea_data_checker.py 验证每个想法的数据可行性
     ↓ checkpoint（必须暂停，展示数据可行性表格给用户）
     ↓
阶段7: 排序输出 — 按新颖性(40%) + 数据可行性(30%) + 发表潜力(30%) 排序
     ↓
输出: IDEA_REPORT.md + IDEA_DATA_CHECK.md
```

## 核心原则

### 数据优先原则（必须遵守）

**数据验证必须前移到想法阶段，不等到数据获取阶段才发现无数据**

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

### 强制 checkpoint

阶段6（数据验证）完成后，**必须暂停**并展示数据可行性表格给用户，在用户确认前不得进入下一阶段。

## 输出文件

```
output/fin-ideas/
├── IDEA_REPORT.md         ← 完整想法报告（包含所有想法的详细信息）
├── IDEA_DATA_CHECK.md     ← 数据可行性报告（阶段6输出）
└── IDEA_CANDIDATES.md     ← 精简版（TOP 3-5 最优想法）

output/fin-novelty/
└── NOVELTY_PRECHECK.md    ← 初步新颖性检查结果
```

## 阶段详解

### 阶段1: 研究方向理解

#### 1.1 解析研究领域

根据用户描述，识别研究方向所属领域：

| 领域 | 核心关键词 | 典型数据需求 |
|------|----------|-------------|
| 绿色金融 | ESG、碳排放、绿色债券、气候风险 | ESG评级、碳排放数据、财务面板 |
| 数字金融 | Fintech、数字普惠、移动支付、互联网金融 | 第三方支付数据、用户规模 |
| 碳经济学 | 碳交易、碳配额、碳关税、减排 | 碳市场数据、企业排放数据 |
| 宏观金融 | 货币政策、金融周期、系统性风险 | 宏观指标、金融市场数据 |
| 公司金融 | 融资约束、资本结构、并购、股利政策 | 财务面板、公司治理数据 |
| 资产定价 | 因子模型、异常收益、机构投资者 | 市场数据、因子数据 |
| 行为金融 | 投资者情绪、散户行为、羊群效应 | 交易数据、账户数据 |
| 金融科技 | 区块链、数字货币、API金融 | 平台数据、交易数据 |

#### 1.2 提取用户约束

从用户输入中提取：

- **目标期刊**：JF/JFE/RFS/经济研究/金融研究等
- **研究类型**：实证/理论/综述/方法创新
- **偏好方法**：DID/IV/RDD/机器学习等
- **数据偏好**：A股/美股/全球/宏观
- **时间范围**：样本期要求

### 阶段2: 文献综述

#### 2.1 MCP 多源检索

**必须按顺序执行以下检索**：

```yaml
# 第1步：NBER 工作论文（预印本先行）
CallMcpTool: user-nber-wp -> search_nber_papers
  query: "[核心关键词] + A股/China + 实证方法"
  year_from: 2023

# 第2步：OpenAlex 学术论文
CallMcpTool: user-openalex -> get_openalex_works
  query: "[研究领域] + [核心机制] + China"
  per_page: 30

# 第3步：中文顶刊（A股研究必查）
CallMcpTool: user-brave-search -> brave_web_search
  query: "经济研究 金融研究 管理世界 [核心关键词] A股"
  num_results: 10

CallMcpTool: user-brave-search -> brave_web_search
  query: "中国工业经济 世界经济 [核心机制] 实证"
  num_results: 10

# 第4步：ArXiv 预印本（机器学习/计量方法）
CallMcpTool: user-arxiv -> semantic_search
  query: "[研究领域] + China + empirical"
  max_results: 20
```

#### 2.2 引文图谱构建

```bash
python scripts/citation_graph.py "[研究方向关键词]" \
    --depth 2 \
    --max-papers 50 \
    --output output/fin-literature/CITATION_GRAPH.json \
    --report output/fin-literature/CITATION_REPORT.md
```

#### 2.3 文献筛选标准

| 标准 | 要求 | 原因 |
|------|------|------|
| 期刊层次 | 顶刊优先（JF/JFE/RFS + 中文顶刊）| 质量可靠 |
| 时间范围 | 近5年为主 + 高引经典文献 | 前沿 + 理论基础 |
| 方法可靠性 | 识别策略清晰，稳健性检验充分 | 可作为方法参照 |
| 样本相关性 | A股/新兴市场 > 美股 | 中国市场特殊性 |

### 阶段3: 研究缺口识别

从文献综述中识别 3-5 个具体研究缺口：

1. **未被检验的假设**：文献中存在但未系统验证的命题
2. **未被探索的场景**：某方法/发现未在特定市场中验证
3. **矛盾发现的解释**：争议性结论的新解释
4. **新数据带来的机会**：新数据集开启的新方向
5. **方法论的空白**：某计量方法在特定场景未被使用

**输出格式**：

```markdown
## 研究缺口

### 缺口1: [缺口名称]
- **现有研究**：已有哪些相关研究
- **研究空白**：什么还没有被检验
- **为什么重要**：填补这个缺口的理论和实践意义
- **可行性**：数据和方法是否可行

### 缺口2: [缺口名称]
...
```

### 阶段4: 想法生成

基于识别的研究缺口，使用 LLM 生成 8-12 个研究想法：

#### 4.1 生成提示词模板

```
你是一名经济金融领域顶级学者。请基于以下研究缺口，生成8-12个可发表的实证研究想法。

研究领域：[领域名称]
研究缺口：
1. [缺口1描述]
2. [缺口2描述]
...

要求：
1. 每个想法必须明确对应一个研究缺口
2. 说明使用的识别策略（DID/IV/RDD/面板等）
3. 明确所需的核心数据
4. 指出边际贡献（理论/方法/数据）
5. 评估发表潜力（目标期刊）

输出格式：
## Idea 1: [标题]
- **研究缺口**: [对应哪个缺口]
- **核心机制**: [因果传导路径]
- **识别策略**: [DID/IV/RDD/...]
- **数据需求**: [核心数据集]
- **边际贡献**: [理论/方法/数据创新]
- **发表潜力**: [目标期刊]

...
```

#### 4.2 想法格式模板

每个想法必须包含：

```markdown
## Idea N: [标题]

### 基本信息
- **研究缺口**: [对应哪个缺口编号和描述]
- **研究问题**: [一句话描述核心问题]
- **核心机制**: [因果传导路径，A→B→C]

### 方法设计
- **识别策略**: [DID/IV/RDD/面板/合成控制/机器学习]
- **识别假设**: [关键识别假设是什么]
- **估计方法**: [固定效应模型/工具变量/...]

### 数据需求
- **核心数据集**: [主要数据来源]
- **时间范围**: [样本期]
- **样本量**: [估计样本量]
- **关键变量**: [Y、X、控制变量]

### 边际贡献
- **理论贡献**: [对现有理论的拓展或挑战]
- **方法贡献**: [计量方法或分析方法的创新]
- **数据贡献**: [新数据集或新变量]

### 发表潜力
- **目标期刊**: [最适合发表的期刊]
- **新颖性**: [高/中/低]
- **可行性**: [高/中/低]

### 初步信号（可选）
- **文献支持**: [支持该假设的已有文献]
- **机制合理性**: [理论机制是否成立]
```

### 阶段5: 新颖性预检查

对每个想法进行快速新颖性检查：

```yaml
# 对每个想法执行快速检索
CallMcpTool: user-nber-wp -> search_nber_papers
  query: "[想法核心关键词] + China + [方法]"
  year_from: 2023

CallMcpTool: user-openalex -> get_openalex_works
  query: "[想法核心关键词] + empirical + China"
  per_page: 10
```

**输出**：更新每个想法的"新颖性"字段，标记"高/中/低"

### 阶段6: 想法-数据交叉验证（强制）

**这是流程中最关键的 checkpoint，必须执行**

#### 6.1 调用 IdeaDataValidator

```python
from scripts.idea_data_checker import IdeaDataValidator, quick_check

# 准备想法列表（从阶段4生成）
ideas = [
    {
        "id": "idea_1",
        "title": "关税冲击与资本结构调整速度",
        "description": "利用DID分析2018年关税冲击对企业资本结构调整速度的影响",
        "keywords": ["tariff", "capital structure", "DID", "A-share"],
    },
    # ... 更多想法
]

# 执行数据可行性验证
validator = IdeaDataValidator(ideas)
report = validator.validate_all()
validator.print_report(report)
```

#### 6.2 验证报告解读

`ValidationReport` 包含以下关键字段：

| 字段 | 说明 |
|------|------|
| `available_count` | 数据完全可行的想法数 |
| `partial_count` | 部分可行的想法数 |
| `gap_count` | 数据缺口的想泗数 |
| `auth_needed_count` | 需要授权模拟的想法数 |
| `idea_results` | 每个想法的详细验证结果 |

#### 6.3 可行性评分标准

| 状态 | 评分 | 含义 |
|------|------|------|
| AVAILABLE | 1.0 | 数据完全可用，可立即推进 |
| PARTIALLY_AVAILABLE | 0.6 | 部分数据缺失，可推进但需补充 |
| DATA_GAP | 0.0 | 数据缺口严重，需先补充数据 |
| REQUIRES_AUTH | 0.3 | 需要用户授权使用模拟数据 |

#### 6.4 checkpoint 展示模板

```
═══════════════════════════════════════════════════════════════════
                    想法-数据可行性验证报告
═══════════════════════════════════════════════════════════════════

  验证结果统计:
    ✅ 数据可行:       3 个想法
    ⚠️  部分可行:     5 个想法
    ❌ 数据缺口:      2 个想法
    🔐 需授权模拟:    2 个想法

  ━━ ✅ 数据可行的想法 (3个) ━━
  1. [想法标题]
     评分: 1.0/1.0 | 数据可行，可立即推进
     数据: tushare (财务数据), akshare (免费备选)

  2. [想法标题]
     ...

  ━━ ⚠️  部分可行的想法 (5个) ━━
  1. [想法标题]
     评分: 0.6/1.0 | 部分数据缺失，可推进但需补充
     ⚡ 缺失数据: 融资融券数据（需Tushare Pro Token）

  2. [想法标题]
     ...

  ━━ ❌ 数据缺口的想法 (2个) ━━
  这些想法当前无法推进，需要先补充数据。

  1. [想法标题]
     评分: 0.0/1.0
     缺失数据: 上市公司海关进出口明细（HS8位码）
     获取途径: CSMAR海关数据库（通过学校图书馆VPN）
     网址: https://www.gtadata.com
     成本/限制: 需CSMAR机构账号

  2. [想法标题]
     ...

  ━━ 🔐 需授权模拟的想法 (2个) ━━
  1. [想法标题]
     评分: 0.3/1.0 | 需要用户授权使用模拟数据

─────────────────────────────────────────────────────────────────
  批量数据行动建议:
    • 优先解决以下数据缺口: customs_trade, patent_data

  下一步（请选择）:
    (1) 补充数据——获取API Key或联系学校图书馆
    (2) 授权模拟——仅用演示流程，结果不能发表
    (3) 更换主题——选择数据更易获取的研究方向

═══════════════════════════════════════════════════════════════════
```

#### 6.5 用户决策点

**必须等待用户明确选择**，以下选项：

1. **补充数据**：获取 API Key 或联系学校图书馆
2. **授权模拟**：仅用演示流程，结果不能发表
3. **更换主题**：选择数据更易获取的研究方向
4. **继续部分可行想法**：对部分可行的想法继续推进

### 阶段7: 排序与输出

#### 7.1 综合评分公式

```
综合评分 = 新颖性评分 × 0.4 + 数据可行性评分 × 0.3 + 发表潜力评分 × 0.3
```

| 评分维度 | 权重 | 评分标准 |
|---------|------|---------|
| 新颖性 | 40% | 高=10, 中=7, 低=4 |
| 数据可行性 | 30% | 可行=10, 部分=6, 缺口=0, 模拟=3 |
| 发表潜力 | 30% | 顶刊=10, 一区=8, 二区=6 |

#### 7.2 输出排序后的想法报告

```markdown
# 研究想法报告

**研究方向**: [方向]
**生成日期**: [日期]
**想法总数**: N个（其中M个数据可行）

## 执行摘要

[3-5句话总结推荐想法的核心发现]

## TOP 3 推荐想法

### 想法 1: [标题] ⭐⭐⭐
**综合评分**: X.X/10

| 维度 | 评分 |
|------|------|
| 新颖性 | X/10 |
| 数据可行性 | X/10 |
| 发表潜力 | X/10 |
| **综合评分** | **X.X/10** |

- **研究问题**: [一句话]
- **识别策略**: [方法]
- **核心数据**: [数据来源]
- **边际贡献**: [创新点]

### 想法 2: [标题] ⭐⭐
...

### 想法 3: [标题] ⭐
...

## 所有想法列表

| 排名 | 想法 | 综合评分 | 新颖性 | 数据可行 | 发表潜力 |
|------|------|---------|--------|---------|---------|
| 1 | 想法1 | 9.2 | 高 | 可行 | 顶刊 |
| 2 | 想法2 | 8.5 | 高 | 部分 | 一区 |
| ... | ... | ... | ... | ... | ... |

## 数据需求汇总

### 可直接使用的数据
- [数据源1]: [描述]
- [数据源2]: [描述]

### 需要补充的数据
- [数据源]: [如何获取]

## 下一步

1. 选择一个想法继续推进
2. 进入 fin-novelty-check 进行完整新颖性验证
3. 进入 fin-experiment-design 进行实证设计
```

## IdeaDataValidator API 参考

### 导入方式

```python
from scripts.idea_data_checker import (
    IdeaDataValidator,
    IdeaDataRequirement,
    ValidationReport,
    Feasibility,
    quick_check
)
```

### 核心类和方法

```python
class IdeaDataValidator:
    def __init__(self, ideas: list[dict], verbose: bool = False)
    """初始化验证器

    Args:
        ideas: 想法字典列表，每个字典应包含：
               - id: 想法唯一标识
               - title: 想法标题
               - description: 想法描述
               - keywords: 关键词列表（自动从标题/描述提取）
    """

    def validate_all(self) -> ValidationReport
    """对所有想法执行数据可行性验证，返回完整报告"""

    def validate_single(self, idea: dict) -> IdeaValidationResult
    """验证单个想法的数据可行性"""

    def print_report(self, report: ValidationReport) -> None
    """打印验证报告（带颜色）"""

def quick_check(ideas: list[dict]) -> ValidationReport
"""一行调用：对所有想法进行验证并打印报告"""
```

### 数据需求定义

```python
@dataclass
class IdeaDataRequirement:
    data_type: str              # "financial_panel" | "customs_trade" | ...
    description: str             # 对用户说明
    required_variables: list[str]  # 必须包含的变量
    time_frequency: str         # "daily" | "monthly" | "yearly"
    time_range: str             # "2010-2024"
    sample_scope: str           # "A股全样本" | "创业板" | ...
    data_sources_candidates: list[str]  # 可能的来源
    priority: int = 1          # 1=必须，2=重要但可替代，3=可选
```

### 验证结果解读

```python
# 检查所有想法的可行性
for result in report.idea_results:
    print(f"{result.idea['title']}: {result.feasibility.value}")
    print(f"  评分: {result.feasibility_score:.1f}/1.0")
    print(f"  建议: {result.recommendation}")

    # 如果有数据缺口
    if result.gaps:
        print("  数据缺口:")
        for gap in result.gaps:
            print(f"    - {gap}")

    # 如果需要行动
    if result.actions:
        print("  行动:")
        for action in result.actions:
            print(f"    - {action}")
```

## MCP 工具快速索引

| 需求 | MCP Server | 工具 |
|------|------------|------|
| NBER 工作论文 | `user-nber-wp` | `search_nber_papers` |
| OpenAlex 论文 | `user-openalex` | `get_openalex_works` |
| ArXiv 论文 | `user-arxiv` | `semantic_search` |
| 中文文献 | `user-brave-search` | `brave_web_search` |
| 论文全文 | `user-context7` | `get_context7_by_query` |
| 研报补充 | `user-eastmoney-reports` | `get_research_report` |

## 关键约束

1. **数据验证是强制 checkpoint**：阶段6 必须暂停，不能自动继续
2. **模拟数据需要明确授权**：没有用户授权不能使用模拟数据
3. **想法必须与研究缺口对应**：每个想法必须明确指出填补哪个缺口
4. **评分必须透明**：展示所有维度的评分和权重
5. **中文文献不可忽视**：A股研究中中文顶刊是必查项

## 快速执行命令

```bash
# 完整流程执行
python scripts/research_framework/pipeline.py \
    --topic "研究方向" \
    --mode idea_discovery \
    --output output/fin-ideas/

# 仅想法生成（不含数据验证）
python scripts/research_framework/pipeline.py \
    --topic "研究方向" \
    --mode idea_generation

# 仅数据验证
python scripts/idea_data_checker.py \
    --ideas-file output/fin-ideas/IDEA_REPORT.md \
    --report-file output/fin-ideas/IDEA_DATA_CHECK.md
```
