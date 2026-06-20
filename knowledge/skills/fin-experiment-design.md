# fin-experiment-design — 实证方法设计

根据研究想法和 `REFINED_DESIGN.md`，生成完整的实证研究设计方案，覆盖识别策略选择、样本构建、变量定义、稳健性检验清单和内生性处理方案。

## 功能

### 识别策略选择（决策树）

```
样本是否包含处理组/对照组？
├── 是 → 是否为时点处理？
│   ├── 是 → DID（双重差分）
│   │   ├── 只有一个处理时点 → Callaway-SantAnna / Sun-Abraham / Borusyak
│   │   └── 多个处理时点 → Callaway-SantAnna（QJE 2021）
│   └── 否 → 合成控制（Abel/Arkhangelsky）
└── 否 →
    ├── 是否为连续变量处理？
    │   ├── 是 → RDD（断点回归）
    │   └── 否 → IV/工具变量
    └── 是否需要因果森林？
        └── Double/Debiased ML
```

### 计量方法覆盖（~30种主要算法）

**A. DID 家族（12种）**：Callaway-SantAnna (QJE 2021)、Sun-Abraham (REStud 2021)、Borusyak-Jaravel-Sposto (REStud 2024)、Goodman-Bacon (QJE 2021)、dCdH (JASA 2020)、Gardner Two-Stage (2022)、Honest DiD (Rambachan 2023)、合成控制 (Abel JASA 2016)、合成 DID (Arkhangelsky Science 2021)、三重差分 DDD、局部投影 DID、事件研究法

**B. IV/GMM/RDD（7种）**：IV/2SLS、Panel GMM (Arellano-Bond/Blundell-Bond)、Jackknife IV、RDD 精确/模糊 (Cattaneo 2019)、交互固定效应 (Bai 2009 CCE)、面板门槛回归 (Hansen 2000)、合成控制权重推断

**C. 时间序列与波动率（8种）**：GARCH/GJR/EGARCH、Realized Volatility (HAR)、DCC-GARCH、Panel VAR (Abrigo & Love 2016)、TVP-VAR、面板协整检验 (Pedroni/Kao/Westerlund)、面板 ECM、溢出指数 (Diebold-Yilmaz)

**D. 离散选择与生存分析（7种）**：Logit/Probit、有序 Logit、负二项回归、边际效应、Cox 比例风险、Kaplan-Meier、Fine-Gray 竞争风险

**E. 因果机器学习（5种）**：Causal Forest、Double ML (DoubleML)、T-Learner/X-Learner、CS-DID 异质性处理效应、Buncher-Fillator 中介分析

**F. 结构估计与敏感性（5种）**：Olley-Pakes、Levinsohn-Petrin、Leamer 敏感性分析、Oster Bounds、Vuong 检验

**G. 金融专题（5种）**：绿色债券 greenium 估计、绿色债券事件研究、期权隐含波动率曲面、Black-Scholes + Greeks、Fama-MacBeth 回归

**H. 稳健性与辅助（5种）**：PSM-DID、面板分位数回归、空间回归（SDM/SAR/SEM）、稳健性检验（18类）、数据溯源追踪

**I. 特色变量与政策库**：A股特色变量（8种）、中国政策实验数据库（25项政策）、PRISMA 合规报告

## 输出文件

| 文件 | 说明 |
|------|------|
| `REFINED_DESIGN.md` | 核心设计 |
| `EXPERIMENT_PLAN.md` | 执行计划 |
| `VARIABLE_DEFINITIONS.md` | 变量定义表 |
| `ROBUSTNESS_PLAN.md` | 稳健性检验（≥6类）|
| `ENDOGENEITY_PLAN.md` | 内生性处理方案 |
| `EXECUTION_CHECKLIST.md` | 执行清单 |

## 调用方式

```
"设计一下关税对企业创新影响的实证方案"
```
