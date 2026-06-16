---
name: fin-experiment-design
description: 经济金融实证方法设计。根据研究想法和REFINED_DESIGN.md，生成完整的实证研究设计方案，覆盖识别策略选择、样本构建、变量定义、稳健性检验清单和内生性处理方案。
argument-hint: [research-idea-reference]
trigger: "设计实证方案|实验设计|研究设计|实证方法"
---

# 经济金融实证方法设计

将研究想法细化为完整、可执行的实证研究设计。

## 输出文件

所有文件输出到 `output/fin-refinement/` 目录：

| 文件 | 说明 | 优先级 |
|------|------|--------|
| `REFINED_DESIGN.md` | 核心研究设计文档（**最重要**） | 必须 |
| `EXPERIMENT_PLAN.md` | 详细实验执行计划 | 必须 |
| `VARIABLE_DEFINITIONS.md` | 变量定义表 | 必须 |
| `ROBUSTNESS_PLAN.md` | 稳健性检验方案 | 必须 |
| `ENDOGENEITY_PLAN.md` | 内生性处理方案 | 必须 |
| `EXECUTION_CHECKLIST.md` | 实验执行检查清单 | 必须 |

## 前置条件

读取以下文件（按优先级）：
1. `output/fin-ideas/IDEA_REPORT.md` — 选定研究想法
2. `output/fin-novelty/NOVELTY_REPORT.md` — 新颖性验证
3. `output/fin-literature/LIT_REVIEW.md` — 文献综述
4. `FIN_BRIEF.md` — 研究简报
5. `output/fin-refinement/REFINED_DESIGN.md` — 如已存在，读取并更新

## 核心模块依赖

```python
# scripts/research_framework/modern_did.py
from modern_did import ModernDiDEngine, DiDEstimationResult

# scripts/research_framework/robustness_runner.py
from robustness_runner import RobustnessRunner, RobustnessReport

# scripts/research_framework/iv_panel.py
from iv_panel import IVPanel

# scripts/research_framework/rdd.py
from rdd import RDDEngine
```

---

# 阶段1：识别策略选择（决策树）

> **⚠️ Checkpoint**: 策略选择后必须向用户展示决策树结果，解释为何选择该策略。

## 决策树

```
样本是否包含处理组/对照组？
│
├── 是 → 政策/处理时点是否单一？
│   ├── 是 → 经典 2×2 DID
│   │   ├── 单一处理队列 → 标准 DID (Angrist & Pischke 2009)
│   │   └── 多处理队列 → Callaway-SantAnna (QJE 2021) [推荐]
│   │       或 Sun-Abraham (REStud 2021)
│   │       或 Borusyak-Jaravel-Spinks (REStud 2024)
│   │       或 Gardner (2022) shock-free
│   │
│   └── 否 → 合成控制法 (Abadie et al. 2010)
│       或 合成 DID (Arkhangelsky et al. 2021)
│
└── 否 → 处理变量是否为连续型？
    ├── 是 → 断点回归 (RDD)
    │   ├── 精确 RDD
    │   └── 模糊 RDD (含 IV)
    │
    └── 否 → 工具变量法
        ├── 弱 IV 检验: Kleibergen-Paap rk F statistic
        └── 面板 GMM: Arellano-Bond / Blundell-Bond
```

## 识别策略详解

### A. 双重差分 (DID)

**适用条件**：
- 存在明确的政策/事件处理时机
- 处理组和对照组在政策前满足平行趋势假设
- 处理效应在处理后持续（持续性DID）或仅在当期（短暂DID）

**核心假设**：
1. **平行趋势假设**：处理组和对照组在政策实施前趋势一致
2. **SUTVA**：无溢出效应，无处理组个体影响对照组
3. **无预期效应**：个体在政策实施前不会提前调整行为

**标准 DID 模型**：
$$Y_{it} = \alpha + \beta \cdot D_{it} + \gamma \cdot X_{it} + \mu_i + \lambda_t + \varepsilon_{it}$$

其中 $D_{it} = Treatment_i \times Post_t$ 是核心 DID 项。$\beta$ 是平均处理效应 (ATT)。

**交错 DID**（多个政策时点）：

| 方法 | 论文 | 适用场景 |
|------|------|----------|
| Callaway-SantAnna | QJE 2021 | 组-时间 ATT，可处理不同处理强度 |
| Sun-Abraham | REStud 2021 | 交互加权估计 |
| Borusyak-Jaravel-Spinks | REStud 2024 | 反事实推断，效率更高 |
| Goodman-Bacon | QJE 2021 | 分解诊断工具 |

### B. 合成控制法 (SCM)

**适用条件**：
- 单一处理单元（如一个国家/州/城市）
- 有多个未受处理的对照单元
- 可构建加权对照组

**Arkhangelsky et al. 2021 (Synthetic DID)**：
结合 SCM 和 DID，适用于：
- 干预前有趋势差异
- 需要预测反事实结果

### C. 断点回归 (RDD)

**精确 RDD**：
$$Y_i = \alpha + \beta \cdot D_i + f(X_i) + \varepsilon_i$$
$D_i = 1(X_i \geq c)$，$f(\cdot)$ 是跑分变量的多项式函数。

**模糊 RDD**：
断点仅影响处理概率，估算 LATE（局部平均处理效应）。

**核心检验**：
1. **密度检验 (McCrary)**：断点两侧样本密度是否连续
2. **预先指定变量连续性**：协变量在断点处是否平滑
3. **带宽选择**：IK (2012) / CCT (2014) / MSE 最小化

### D. 工具变量 (IV)

**工具变量质量评估**：

| 标准 | 要求 | 评估方法 |
|------|------|----------|
| 相关性 | F统计量 > 10 | 第一阶段 F 统计量 |
| 排他性 | Z 不影响 Y（除通过 X 外） | 理论论证 |
| 外生性 | Z 不受 Y 影响 | 理论论证 |
| 唯一性 | Z 仅通过 X 影响 Y | 理论论证 |

**估计方法**：
- 2SLS（两阶段最小二乘）：默认方法
- LIML（有限信息极大似然）：弱工具变量时更稳健
- GMM（广义矩估计）：异方差稳健标准误

### E. 面板数据方法

**固定效应模型**：
$$Y_{it} = \alpha + \beta \cdot X_{it} + \mu_i + \lambda_t + \varepsilon_{it}$$

**动态面板 GMM**：
$$Y_{it} = \alpha + \rho \cdot Y_{i,t-1} + \beta \cdot X_{it} + \mu_i + \varepsilon_{it}$$

- Arellano-Bond GMM
- Blundell-Bond 系统 GMM

---

# 阶段2：样本构建

## 样本定义

### 2.1 处理组/对照组定义

```markdown
## 处理组定义

| 标准 | 具体定义 | 数据来源 |
|------|----------|----------|
| 行业标准 | 属于 [具体行业代码] | CSMAR / Wind |
| 规模标准 | 总资产 > [阈值] 亿元 | CSMAR / Wind |
| 所有制标准 | 国有企业 / 民营企业 | CSMAR |
| 地区标准 | 位于 [省份/城市] | CSMAR |

## 对照组定义

对照组选择原则：
1. **行业匹配**：与处理组同行业
2. **规模相近**：与处理组规模相近（±20%）
3. **时间匹配**：同期上市
4. **排除标准**：剔除金融公司、ST公司、退市公司
```

### 2.2 时间窗口

```markdown
## 时间窗口

| 阶段 | 时间范围 | 说明 |
|------|----------|------|
| 政策前期 | [YYYY-Q1] - [YYYY-Q4] | 平行趋势检验 |
| 政策当期 | [YYYY-Q1] | 政策实施时点 |
| 政策后期 | [YYYY-Q1] - [YYYY-Q4] | 长期效应分析 |

最小时间窗口：政策前后各 3 年
推荐时间窗口：政策前后各 5 年
```

---

# 阶段3：变量定义

生成 `VARIABLE_DEFINITIONS.md`：

```markdown
# 变量定义表

## 被解释变量（Y）

| 变量名 | 中文名 | 定义 | 计算方式 | 数据来源 | 频率 | 预期符号 |
|--------|--------|------|----------|----------|------|----------|
| y_main | [主变量] | [经济学定义] | [计算公式] | [来源] | Annual | +/- |
| y_robust1 | [稳健性变量1] | ... | ... | ... | ... | +/- |
| y_robust2 | [稳健性变量2] | ... | ... | ... | ... | +/- |

## 核心解释变量（X）

| 变量名 | 中文名 | 定义 | 计算方式 | 数据来源 | 频率 | 预期方向 |
|--------|--------|------|----------|----------|------|----------|
| treat | 处理变量 | Treatment×Post | 虚拟变量 | 政策数据库 | - | + |
| treat_intensity | 处理强度 | [定义] | [计算] | 政策数据库 | Annual | + |
| x_main | [核心变量] | [定义] | [计算] | [来源] | ... | +/- |

## 控制变量

### 公司层面

| 变量名 | 中文名 | 定义 | 计算方式 | 数据来源 | 理由 |
|--------|--------|------|----------|----------|------|
| Size | 企业规模 | Ln(总资产) | Ln(总资产) | CSMAR/Wind | 规模效应 |
| Lev | 资产负债率 | 总负债/总资产 | 财务比率 | CSMAR/Wind | 资本结构 |
| ROA | 资产收益率 | 净利润/总资产 | 财务比率 | CSMAR/Wind | 盈利能力 |
| MB | 市值账面比 | 市值/账面价值 | 市场/账面 | CSMAR | 成长性 |
| Age | 企业年龄 | Ln(上市年限+1) | 年份计算 | CSMAR | 生命周期 |
| TOP1 | 股权集中度 | 第一大股东持股比例 | 持股比例 | CSMAR | 公司治理 |
| Dual | 两职合一 | 董事长兼总经理 | 虚拟变量 | CSMAR | 公司治理 |
| Board | 董事会规模 | 董事人数 | 人数 | CSMAR | 公司治理 |
| SOE | 所有制 | 国有企业 | 虚拟变量 | CSMAR | 所有制效应 |

### 宏观层面

| 变量名 | 中文名 | 定义 | 计算方式 | 数据来源 |
|--------|--------|------|----------|----------|
| GDP_g | GDP增速 | GDP同比增长率 | 同比 | 国家统计局 |
| M2_g | M2增速 | M2同比增长率 | 同比 | 央行 |
| CPI | 通胀率 | 消费者价格指数 | 同比 | 国家统计局 |
| HHI | 行业集中度 | Herfindahl 指数 | 计算 | CSMAR |

## 固定效应设置

| 固定效应 | 目的 | 是否加入 |
|----------|------|----------|
| 公司固定效应 (μᵢ) | 控制不随时间变化的个体异质性 | ✅ 必须 |
| 年度固定效应 (λₜ) | 控制共同时间趋势 | ✅ 必须 |
| 行业×年度 | 控制行业共同冲击 | ✅ 推荐 |
| 省份×年度 | 控制地区共同冲击 | ✅ 推荐 |
| 公司×行业趋势 | 控制公司特定趋势 | ⚠️ 可选 |

## 标准误聚类

| 聚类维度 | 理由 | 适用场景 |
|----------|------|----------|
| 公司层面 | 公司内观测相关 | 默认选项 |
| 公司×年度双维 | 既有个体内相关又有年间相关 | 标准做法 (CGM 2011) |
| 行业×年度 | 行业层面冲击相关 | 有明显行业效应时 |
| 省份×年度 | 省份层面冲击相关 | 地区政策研究 |

## 变量符号约定

```python
# Stata 变量命名规范
y_main = "innovation"           # 被解释变量
treat = "did"                    # DID 交互项
x_vars = ["size", "lev", "roa", "mb", "age", "top1", "dual", "board", "soe"]
macro_vars = ["gdp_g", "m2_g", "cpi"]
fe = "i.stock_code i.year"       # 固定效应
cluster = "stock_code"           # 聚类维度
```
```

---

# 阶段4：识别策略详细设计

## 4.1 DID 详细设计

### 平行趋势假设

**事件研究设计**（必须做）：
$$Y_{it} = \alpha + \sum_{k=-T}^{-2} \delta_k D_{it}^k + \sum_{k=0}^{K} \gamma_k D_{it}^k + \gamma \cdot X_{it} + \mu_i + \lambda_t + \varepsilon_{it}$$

其中 $D_{it}^k = Treatment_i \times 1(t = T_0 + k)$。

**平行趋势检验要点**：
- 政策前各期 ($k < 0$) 的系数 $\delta_k$ 应统计上不显著（置信区间包含0）
- 绘制 $\delta_k$ 的系数图（95%置信区间）
- 可使用 `modern_did.py` 的 `event_study_data()` 方法

### 交错 DID 特别注意事项

当存在多个处理时点时：

| 问题 | 解决方案 |
|------|----------|
| 不同处理时点导致处理状态定义不一致 | 使用 Callaway-SantAnna 组-时间 ATT |
| 早期处理组作为晚期处理组对照组 | Borusyak-Jaravel-Spinks 反事实推断 |
| 存在处理效应异质性 | Sun-Abraham 交互加权估计 |
| 处理效应随时间变化 | 事件研究 + 动态效应分解 |

### ModernDiDEngine 使用

```python
from modern_did import ModernDiDEngine

# 初始化
engine = ModernDiDEngine(
    df=data,
    y_var="innovation",           # 被解释变量
    treat_var="treatment",        # 处理组虚拟变量
    time_var="year",              # 时间变量
    unit_var="stock_code",        # 单位变量
    x_vars=["size", "lev", "roa", "mb", "age", "top1"],
    cluster_var="stock_code"      # 聚类变量
)

# 1. Callaway-SantAnna (推荐)
result_cs = engine.cs()
print(f"CS ATT: {result_cs.coef:.4f} (SE: {result_cs.se:.4f})")

# 2. Borusyak-Jaravel-Spinks
result_bjs = engine.bjs()
print(f"BJS ATT: {result_bjs.coef:.4f} (SE: {result_bjs.se:.4f})")

# 3. Sun-Abraham
result_sa = engine.sa()
print(f"SA ATT: {result_sa.coef:.4f} (SE: {result_sa.se:.4f})")

# 4. Goodman-Bacon 分解（诊断工具）
bacon_df = engine.bacon()
print(bacon_df)

# 5. 事件研究数据
event_study = engine.event_study_data(horizons=range(-5, 6))
engine.plot_event_study(estimator="cs", horizons=range(-5, 6), save_path="event_study.pdf")

# 6. Honest DiD (Rambachan-Roth 敏感性分析)
honest_result = engine.honest_did(m=0.5, delta_grid=None)
print(honest_result)

# 7. Wild Bootstrap
wild_result = engine.wild_bootstrap(n_boot=999, cluster_var="stock_code")
print(f"Wild Bootstrap ATT: {wild_result.coef:.4f} (p={wild_result.pval:.4f})")
```

## 4.2 RDD 详细设计

```python
from rdd import RDDEngine

# 初始化
rdd = RDDEngine(
    df=data,
    outcome="performance",        # 结果变量
    running="score",               # 跑分变量
    cutoff=0,                      # 断点位置
    treatment="treated"            # 处理变量
)

# 1. 带宽选择
bw_ik = rdd.bandwidth_ik()        # Imbens-Kalyanaraman 2012
bw_cct = rdd.bandwidth_cct()      # Calonico-Cattaneo-Titiunik 2014

# 2. 精确 RDD
sharp_result = rdd.sharp_rdd(bandwidth=bw_ik, kernel="triangular")

# 3. 模糊 RDD（需要工具变量）
fuzzy_result = rdd.fuzzy_rdd(instrument="fuzzy_inst", bandwidth=bw_ik)

# 4. McCrary 密度检验
mccrary = rdd.mccrary_test()
print(f"McCrary t-stat: {mccrary['t_stat']:.3f}, p-value: {mccrary['p_value']:.3f}")

# 5. 预先指定变量连续性检验
covariates = ["size", "lev", "age"]
for var in covariates:
    continuity_test = rdd.test_covariate_balance(var)
    print(f"{var}: p-value = {continuity_test['p_value']:.3f}")
```

## 4.3 IV 详细设计

```python
from iv_panel import IVPanel

# 初始化
iv = IVPanel(
    df=data,
    y_var="innovation",            # 被解释变量
    instruments=["iv1", "iv2"],    # 工具变量列表
    x_vars=["size", "lev", "roa"]  # 外生控制变量
)

# 1. 第一阶段
first_stage = iv.first_stage()
print(f"First Stage F: {first_stage['f_stat']:.2f}")

# 2. 第二阶段
second_stage = iv.second_stage()
print(f"2SLS Coefficient: {second_stage['coef']:.4f}")

# 3. 弱工具变量检验
kp_f = iv.weak_instrument_test()
print(f"Kleibergen-Paap rk F: {kp_f:.2f}")  # > 10 表示非弱 IV

# 4. 过度识别检验（Sargan-Hansen）
overid = iv.overidentification_test()

# 5. 面板 GMM
gmm_result = iv.panel_gmm()
```

## 4.4 合成控制法详细设计

```python
from synthetic_control import SyntheticControl

# 初始化
sc = SyntheticControl(
    df=data,
    treated_unit="treated_id",
    outcome_var="y",
    control_pool=["ctrl1", "ctrl2", "ctrl3", ...],
    time_var="year",
    treatment_time=2015
)

# 1. 合成控制
result = sc.fit()

# 2. 推断（置换检验）
placebo_results = sc.placebo_test(n_permutations=500)

# 3. 绘图
sc.plot(save_path="sc_results.pdf")

# 4. RMSPE 比率
rmspe_ratio = sc.rmspe_ratio()

# 合成 DID（Arkhangelsky et al. 2021）
from synthetic_did import SyntheticDID
sdid = SyntheticDID(
    df=data,
    treated_unit="treated_id",
    outcome_var="y",
    time_var="year",
    treatment_time=2015,
    control_pool=[...]
)
sdid_result = sdid.fit()
```

---

# 阶段5：稳健性检验方案

生成 `ROBUSTNESS_PLAN.md`：

## 最低要求（6种，顶刊通常要求更多）

| 编号 | 检验名称 | 具体操作 | 预期结果 | 对应输出 |
|------|----------|----------|----------|----------|
| R1 | 平行趋势检验 | 事件研究设计，预处理系数不显著 | 预处理系数 CI 包含 0 | 图2 |
| R2 | 安慰剂检验 | 500次随机处理时点/处理组 | 伪系数分布在0附近 | 图6 |
| R3 | 替换被解释变量 | 使用替代指标度量 Y | 核心结论不变 | 表A3 |
| R4 | 替换核心解释变量 | 使用替代指标度量 X | 核心结论不变 | 表A4 |
| R5 | 子样本回归 | 去除金融/ST/极端值 | 核心结论不变 | 表A5-A8 |
| R6 | 双重差分估计量比较 | CS/BJS/SA/Gardner 对比 | 量级方向一致 | 表3 |

## 扩展稳健性检验

| 编号 | 检验名称 | 具体操作 | 对应输出 |
|------|----------|----------|----------|
| R7 | Bacon 分解 | Goodman-Bacon QJE 2021 | 诊断表 |
| R8 | Honest DiD | Rambachan-Roth 2023 | 敏感性表 |
| R9 | Wild Bootstrap | Wu 1986 / Cameron et al. 2008 | p值 |
| R10 | PSM+DID | 倾向得分匹配后做 DID | 表A9 |
| R11 | 增加控制变量 | 加入行业×年度固定效应 | 表A10 |
| R12 | 不同标准误 | Robust vs 聚类 vs 双维聚类 | 表A11 |
| R13 | Oster 边界 | Oster 2019 δ 方法 | 敏感性分析 |
| R14 | 带宽敏感（RD） | IK / CCT / 0.5x / 2x 带宽 | 表A12 |
| R15 | 不同时间窗口 | 政策前后 3/5/7 年 | 表A13 |

## RobustnessRunner 使用

```python
from robustness_runner import RobustnessRunner

runner = RobustnessRunner()

# 运行所有稳健性检验
report = runner.run_all(df=data, main_result=main_result)

# 1. 平行趋势检验
pt_result = runner.parallel_trends(data, horizons=range(-5, 6))

# 2. 安慰剂检验（500次随机）
placebo = runner.run_placebo(data, n_permutations=500)
runner.plot_placebo_distribution(placebo, save_path="placebo.pdf")

# 3. 子样本检验
subsample_results = runner.run_subsample(data, subsample_defs=[
    {"name": "exclude_finance", "filter": "industry != '金融'"},
    {"name": "exclude_st", "filter": "st == 0"},
    {"name": "high_tech", "filter": "industry in ['计算机', '电子']"}
])

# 4. Oster 边界
oster = runner.oster_bounds(
    df=data,
    y_var="innovation",
    treat_var="did",
    x_vars=["size", "lev", "roa", "mb", "age"]
)

# 5. Wild Bootstrap
wild = runner.wild_bootstrap(df=data, n_boot=999, cluster_var="stock_code")

# 生成报告
print(report.summary())
```

---

# 阶段6：内生性处理

生成 `ENDOGENEITY_PLAN.md`：

## 内生性来源识别

### 1. 反向因果
- **问题**：Y 可能反过来影响 X
- **风险**：高（Y→X 的反馈效应）
- **处理方案**：滞后项 IV / LP / 面板方法

### 2. 遗漏变量
- **问题**：存在同时影响 X 和 Y 的遗漏因素
- **风险**：中-高
- **处理方案**：加入更多控制变量 / 固定效应 / IV

### 3. 测量误差
- **问题**：X 或 Y 的测量存在误差
- **风险**：中
- **处理方案**：使用替代测量 / IV / 误差修正模型

### 4. 选择偏误
- **问题**：样本自选择进入处理
- **风险**：高
- **处理方案**：PSM / Heckman 两步法 / IV

## 内生性检验

| 检验方法 | 原假设 | 检验统计量 | 阈值 | Python/Stata |
|----------|--------|-----------|------|--------------|
| Durbin-Wu-Hausman | X 是外生的 | F 统计量 | p < 0.1 表示内生 | ` estat endogenous` |
| Sargan-Hansen | 工具变量过度识别 | J 统计量 | p > 0.1 表示工具有效 | ` estat overid` |
| 弱工具变量 | 第一阶段 F < 10 | F 统计量 | F > 10 表示非弱 IV | `ivweakparm` |

## 内生性解决方案

### 方案 A：工具变量法
[见阶段4.3]

### 方案 B：滞后变量法
$$Y_{it} = \alpha + \beta \cdot X_{i,t-1} + \gamma \cdot Controls_{it} + \mu_i + \lambda_t + \varepsilon_{it}$$

使用 X 的滞后项作为解释变量，缓解同期内生性。

### 方案 C：Arellano-Bond GMM
```python
from iv_panel import IVPanel

gmm = IVPanel(df=data, y_var="y", instruments=["l.x1", "l.x2"])
gmm_result = gmm.arellano_bond_gmm()
```

### 方案 D：Oster 边界
```python
from robustness_runner import RobustnessRunner

# 计算使核心系数归零所需的遗漏变量强度
oster_result = runner.oster_bounds(
    df=data,
    y_var="innovation",
    treat_var="did",
    x_vars=["size", "lev", "roa", "mb", "age"]
)
# 如果 δ > 1，说明需要比可观测变量更强的遗漏变量才能归零
```

---

# 阶段7：输出文件模板

## 7.1 REFINED_DESIGN.md（核心文档）

```markdown
# 实证研究设计

## 1. 研究问题

[从 IDEA_REPORT.md 提取研究问题]

## 2. 识别策略

### 2.1 策略选择
- **选择策略**：[DID / IV / RDD / 面板 GMM / SCM]
- **选择理由**：[为什么这个策略最适合本研究]

### 2.2 策略适用性检验
- [列出关键假设和检验方法]

## 3. 样本构建

### 3.1 数据来源
- 公司财务数据：[CSMAR / Wind / Tushare]
- 宏观数据：[国家统计局 / 央行]
- 政策数据：[具体来源]

### 3.2 样本选择
- 时间范围：[YYYY - YYYY]
- 处理组：[N 家]
- 对照组：[N 家]
- 总观测值：[N]

### 3.3 排除标准
- 金融公司
- ST/*ST 公司
- 上市不满 [X] 年
- 关键变量缺失

## 4. 变量定义

[见 VARIABLE_DEFINITIONS.md]

## 5. 估计方法

### 5.1 基准模型
$$Y_{it} = \alpha + \beta \cdot D_{it} + \gamma \cdot X_{it} + \mu_i + \lambda_t + \varepsilon_{it}$$

### 5.2 固定效应设置
- 公司固定效应
- 年度固定效应
- [行业×年度 / 省份×年度]

### 5.3 标准误聚类
- [公司层面 / 公司×年度双维]

## 6. 稳健性检验

[见 ROBUSTNESS_PLAN.md]

## 7. 内生性处理

[见 ENDOGENEITY_PLAN.md]

## 8. 预期结果

- 核心系数方向：[正向 / 负向]
- 核心系数显著性：[1% / 5% / 10%]
- 经济显著性：[具体含义]
```

## 7.2 EXPERIMENT_PLAN.md

```markdown
# 实验执行计划

## 阶段1：数据准备（第1-2周）
- [ ] 获取公司财务数据
- [ ] 获取宏观数据
- [ ] 构建政策/处理变量
- [ ] 合并面板数据集
- [ ] 变量清洗和计算
- [ ] Winsorize 处理

## 阶段2：描述性统计（第2周）
- [ ] 全样本描述性统计（表1）
- [ ] 处理组/对照组均值差异检验
- [ ] 相关性矩阵
- [ ] 样本筛选流程记录

## 阶段3：主回归（第3-4周）
- [ ] 基准回归
- [ ] 平行趋势检验
- [ ] 动态效应分析
- [ ] 异质性分析

## 阶段4：稳健性检验（第4-5周）
- [ ] R1-R6 必做检验
- [ ] R7-R15 扩展检验

## 阶段5：内生性处理（第5周）
- [ ] IV / GMM 估计
- [ ] 内生性检验

## 阶段6：论文写作（第6周）
- [ ] 实证结果表格整理
- [ ] 结果描述撰写
```

---

# 检查清单

## 策略选择检查
- [ ] 已向用户展示决策树结果
- [ ] 已解释选择该策略的理由
- [ ] 已识别核心假设
- [ ] 已设计假设检验方法

## 样本构建检查
- [ ] 处理组定义清晰
- [ ] 对照组定义合理
- [ ] 时间窗口充足
- [ ] 排除标准有据

## 变量定义检查
- [ ] 被解释变量定义清晰
- [ ] 核心解释变量定义清晰
- [ ] 控制变量选择有理论依据
- [ ] 数据来源明确

## 稳健性检验检查
- [ ] 至少 6 种稳健性检验
- [ ] 每种检验有明确经济学含义
- [ ] 结果格式统一

## 内生性处理检查
- [ ] 已识别潜在内生性来源
- [ ] 已设计处理方案
- [ ] 已设计检验方法

## 关键原则

1. **识别策略决定论文质量上限**。DID/IV/RD 优于简单 OLS，方法选择要与研究问题匹配。
2. **平行趋势假设是 DID 的生命线**。必须做事件研究设计检验，不能跳过。
3. **稳健性检验不是越多越好**。选择有明确经济学意义的检验。
4. **内生性要诚实讨论**。不能假装没有内生性，要主动识别并处理。
5. **工具变量要同时满足相关性和排他性**。F > 10 只是相关性门槛，排他性需要理论论证。
6. **固定效应和聚类标准误的选择要有依据**。不同选择可能改变显著性结果。
7. **数据清洗步骤必须记录**。审稿人可能要求重复清洗过程。
8. **样本选择要谨慎**。去除金融公司、ST 公司等决策必须有依据。
