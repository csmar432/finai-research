# fin-generate-idea — 经济金融研究想法生成

> **注意**：本文件是知识参考文档。操作版本见 `.cursor/skills/fin-generate-idea/SKILL.md`（542行，含完整流程和代码示例）。

## 功能

针对经济金融研究方向，生成 8-12 个可发表的研究想法，经过数据可行性筛选后输出排序报告。

## 流程（7步）

```
研究方向输入
     ↓
阶段1: 研究领域解析 + 约束提取
     ↓
阶段2: 文献提取 — 使用 MCP 获取高影响力论文
     ↓
阶段3: 缺口分析 — 识别领域内"未完成"的工作
     ↓
阶段4: 想法生成 — 基于文献生成 8-12 个想法
     ↓
阶段5: 【强制】数据可行性筛选 — 对每个想法运行数据源检查
     ↓
阶段6: 过滤标记 — 无数据路径的想法标记"需授权模拟"
     ↓
阶段7: 综合排序 — novelty × 0.4 + data × 0.3 + publish × 0.3
     ↓
输出: IDEA_REPORT.md
```

## 评分公式

每个想法从三个维度评分（0-10分）：

| 维度 | 权重 | 评估内容 |
|---|---|---|
| **新颖性 (novelty)** | 40% | 与现有文献的差异化、方法创新、理论贡献 |
| **数据可行性 (data)** | 30% | MCP 数据源可用性、数据质量、数据缺口 |
| **发表潜力 (publish)** | 30% | 目标期刊匹配度、方法复杂度、样本量 |

**综合得分** = novelty × 0.4 + data × 0.3 + publish × 0.3

## 数据优先原则

1. 想法生成时即验证数据可行性
2. 数据缺口的想法不进推荐名单，除非用户明确授权模拟数据
3. 无数据支撑的想法在想法生成阶段即淘汰，不等到阶段5

## 数据可行性验证

对每个候选想法运行 `idea_data_checker.py`：

```python
from scripts.idea_data_checker import quick_check

# 验证所有想法的数据可行性
report = quick_check(ideas)
print(report)
# 输出: 每个想法的 MCP 可用性 × 数据质量 × 缺口评估
```

## 输出

- `IDEA_REPORT.md` — 排序后的研究想法报告（含评分、新颖性理由、数据可行性说明）
- 每个想法包含：研究问题、假设、识别策略、所需数据、目标期刊、预期结论

## 目标期刊（按研究方向推荐）

| 研究方向 | 推荐期刊 |
|---|---|
| 公司金融 | JF / JFE / Journal of Corporate Finance |
| 银行与金融中介 | Journal of Financial Economics / Journal of Money, Credit and Banking |
| 资产定价 | RFS / JFQA / Journal of Financial Markets |
| ESG / 绿色金融 | Journal of Banking & Finance / Review of Finance |
| 数字金融 / 金融科技 | Journal of Financial Economics / Information Economics and Policy |
| 宏观金融 | Journal of Monetary Economics / Journal of International Economics |
| 实证产业组织 | RAND Journal of Economics / Journal of Economics & Management Strategy |
| 中国研究 | 经济研究 / 金融研究 / 管理世界 / China Economic Review |

## 使用示例

```
用户: "我想研究碳排放权交易对企业绿色创新的影响"

Agent → 解析约束（政策/企业/创新/中国）
  → MCP: openalex + context7 检索相关论文
  → 识别研究缺口（异质性效应/长期创新/溢出效应等未研究）
  → 生成 10 个候选想法
  → idea_data_checker 验证（碳市场数据 + 专利数据 + 上市公司数据）
  → 排序输出 → IDEA_REPORT.md
```

## 详见

完整操作文档：`.cursor/skills/fin-generate-idea/SKILL.md`
