---
name: fin-paper-draft
description: 经济金融论文正文写作。根据PAPER_OUTLINE.md大纲和REFINED_DESIGN.md研究设计，生成完整的论文正文草稿（英文/中文），覆盖Introduction到Conclusion所有章节。
argument-hint: [chapter-name]
---

# 经济金融论文正文写作

根据论文大纲和研究设计，生成完整的论文正文草稿（LaTeX格式）。

## 触发条件

**触发关键词**：`写章节`、`生成正文`、`draft chapter`、`写Introduction`、`写Methodology`、`写Conclusion`

**指定章节**：`introduction`、`literature`、`methodology`、`results`、`robustness`、`conclusion`、`abstract`

## 前置条件

读取以下文件（按优先级）：

| 优先级 | 文件路径 | 说明 |
|--------|----------|------|
| 1 | `FIN_BRIEF.md` | 目标期刊、语言、字数目标 |
| 2 | `output/fin-manuscript/PAPER_OUTLINE.md` | 论文大纲 |
| 3 | `output/fin-refinement/REFINED_DESIGN.md` | 研究设计 |
| 4 | `output/fin-refinement/VARIABLE_DEFINITIONS.md` | 变量定义 |
| 5 | `output/fin-refinement/ROBUSTNESS_PLAN.md` | 稳健性检验方案 |
| 6 | `output/fin-manuscript/FIGURE_PLAN.md` | 图表计划 |
| 7 | `output/fin-manuscript/TABLE_PLAN.md` | 表格计划 |
| 8 | `output/fin-literature/LIT_REVIEW.md` | 文献综述 |
| 9 | `output/fin-novelty/NOVELTY_REPORT.md` | 新颖性报告 |
| 10 | `output/fin-experiments/DATA_MANIFEST.md` | 数据清单 |

## 输出文件

```
output/fin-manuscript/draft_v{N}/
├── introduction.tex       # 引言
├── literature.tex          # 文献综述与假说
├── methodology.tex         # 数据与实证方法
├── results.tex             # 实证结果
├── robustness.tex          # 稳健性检验
├── conclusion.tex          # 结论
├── abstract.tex            # 摘要
└── references.bib           # 参考文献
```

## 论文规格确认

从 `FIN_BRIEF.md` 提取：

```
目标期刊: [JF/JFE/RFS/经济研究/金融研究/管理世界]
语言: [English/中文]
字数目标: [X词/字]
LaTeX模板: [aea/jfe/rfs/经济研究/...]
```

## 章节写作模板

### Abstract / 摘要

#### 英文摘要模板（JF/JFE风格，250 words）

```latex
\begin{abstract}
This paper examines whether [RESEARCH QUESTION] using [DATA SOURCE]
covering [SAMPLE PERIOD]. Our identification strategy exploits
[NATURAL EXPERIMENT / IDENTIFICATION STRATEGY], which allows us to
address [ENDOGENEITY CONCERN]. We find that [MAIN FINDING 1],
consistent with [THEORY/PREDICTION]. A one-standard-deviation
increase in [X] is associated with [Y] basis points
[increase/decrease] in [OUTCOME], representing [ECONOMIC MAGNITUDE].
Further analysis reveals that [MECHANISM]: the effect operates
primarily through [CHANNEL]. The result is stronger for [SUBGROUP]
and weaker for [SUBGROUP]. Our results are robust to [ROBUSTNESS
CHECKS] and continue to hold after controlling for [ALTERNATIVE
EXPLANATIONS]. The findings contribute to [LITERATURE STREAMS] and
have implications for [POLICY/INVESTORS/REGULATORS].

\textbf{JEL Classification:} [e.g., G01, G14, G32]
\textbf{Keywords:} [3--5 keywords]
\end{abstract}
```

#### 中文摘要模板（经济研究风格，500字）

```latex
\begin{cnabstract}
本文研究[核心问题]。基于[数据来源]，利用[计量方法]进行实证分析，
样本期为[时间范围]，包含[样本量]个[观测值]。实证结果表明：[主要发现]。
具体地，[X]每增加一个标准差，[Y]相应[增加/减少]约[幅度]，经济意义[显著/有限]。
机制检验表明，[机制路径]是主要传导渠道。分组检验显示，该效应在[子样本]中更为显著，
而在[子样本]中则不显著。经过[稳健性检验]后，结论依然成立。本文对[文献]有贡献，
对[政策/实践]有启示。

\textbf{关键词}：[3--5个关键词]
\end{cnabstract}
```

---

### Introduction / 引言

#### 英文引言模板（JF/JFE风格，1,000-1,500 words）

```latex
\section{Introduction}
\label{sec:introduction}

\textbf{Research Motivation (Paragraph 1-2)}:
[Start with a striking fact or puzzle that motivates the research.
Why is this question important? What gap exists in current knowledge?
What are the practical/implications?]

\textbf{Literature Review (Paragraph 3-4)}:
[Review the most relevant literature streams. Acknowledge what we know,
but emphasize what we do NOT know. Identify the research gap this paper fills.]

\textbf{This Paper (Paragraph 5)}:
[This paper examines whether/how... State the research question clearly
and concisely. Briefly preview the main finding.]

\textbf{Contributions (Paragraph 6)}:
This paper makes three main contributions to the literature:

\begin{itemize}
    \item \textbf{First}, [contribution 1 - theoretical/empirical discovery]
    \item \textbf{Second}, [contribution 2 - methodology/data innovation]
    \item \textbf{Third}, [contribution 3 - policy/practical implication]
\end{itemize}

\textbf{Main Findings (Paragraph 7)}:
[Report the headline result to entice readers to continue.]

\textbf{Paper Structure (Paragraph 8)}:
The remainder of this paper proceeds as follows. Section~\ref{sec:literature}
reviews the related literature and develops the hypotheses.
Section~\ref{sec:data} describes the data and sample construction.
Section~\ref{sec:methodology} presents the empirical methodology.
Section~\ref{sec:results} reports the main results and robustness checks,
and Section~\ref{sec:conclusion} concludes.
```

#### 中文引言模板（经济研究风格，约2,000字）

```latex
\section{引言}
\label{sec:introduction}

\subsection{一、研究背景与问题（约600字）}

[描述研究背景，引出核心问题。
开头要"钩子"——可以用一个令人惊讶的事实、矛盾现象或政策争议切入。
为什么这个问题重要？对学术和实践有何意义？]

\subsection{二、文献综述与研究缺口（约400字）}

[回顾相关文献的两个主要脉络：
1. [文献脉络A]：...（主要发现/理论/争议）
2. [文献脉络B]：...（主要发现/理论/争议）

指出研究缺口：现有文献在[X]方面存在不足，本文试图填补这一空白。]

\subsection{三、本文研究设计与主要发现（约500字）}

[简要描述：
1. 研究设计（数据、方法、识别策略）
2. 主要实证发现
3. 核心结论]

\subsection{四、边际贡献（约300字）}

本文相对于现有文献的边际贡献：

\begin{itemize}
    \item \textbf{贡献1（[理论/发现层面]）}：[具体描述]
    \item \textbf{贡献2（[方法/数据层面]）}：[具体描述]
    \item \textbf{贡献3（[政策/实践层面]）}：[具体描述]
\end{itemize}

\subsection{五、文章结构安排（约200字）}

本文的结构安排如下：第二节梳理相关文献并提出研究假说，
第三节介绍数据与研究设计，第四节报告实证结果，第五节进行稳健性检验，
第六节总结全文并讨论政策启示。
```

---

### Literature Review & Hypotheses / 文献综述与研究假说

#### 英文文献综述模板

```latex
\section{Literature Review and Hypothesis Development}
\label{sec:literature}

\subsection{[Topic A] Literature}
\label{sec:topic_a}

[Organize by theme, not by author. Review the literature on Topic A,
including key theoretical frameworks, empirical findings, and debates.
Cite the most relevant papers from JF/JFE/RFS.

Example structure:
The relationship between X and Y has been documented in several strands
of literature. First, ... \cite{author1_year}. Second, ... \cite{author2_year}.
However, these studies primarily focus on ... and have not considered ...]

\subsection{[Topic B] Literature}
\label{sec:topic_b}

[Similarly review Topic B literature, showing how it connects to Topic A
and identifying the gap this paper fills.]

\subsection{Research Hypotheses}
\label{sec:hypotheses}

\textbf{H1}: [State H1 clearly and concisely. Provide theoretical justification
referencing the literature reviewed above. Explain the mechanism.]

\textbf{H2}: [State H2 with theoretical justification.]

\textbf{H3}: [State H3 with theoretical justification. H1-H3 should form
a logical chain, either parallel or sequential.]
```

#### 中文文献综述模板

```latex
\section{文献综述与研究假说}
\label{sec:literature}

\subsection{一、[主题A]相关研究}

[梳理A领域的研究脉络，引用JFE/RFS等顶刊文献。
按主题分类，而非按作者罗列。
每个子领域要有评述性总结，而非简单描述。]

\textbf{（一）[子主题A1]}

[描述A1领域的理论框架和实证发现。
引用：\cite{author_year}发现...]

\textbf{（二）[子主题A2]}

[描述A2领域的研究...]
[指出A领域研究存在的不足或争议...]

\subsection{二、[主题B]相关研究}

[同样梳理B领域的文献...]
[指出B领域的研究缺口...]

\subsection{三、研究假说}

基于上述文献综述，本文提出以下研究假说：

\textbf{假说H1}：[假说内容]
[理论推导：基于X理论/文献，预期...]
[机制说明：...]

\textbf{假说H2}：[假说内容]
[理论推导：...]

\textbf{假说H3}：[假说内容]
[理论推导：...]
```

---

### Data & Methodology / 数据与实证方法

#### 英文方法论模板

```latex
\section{Data and Methodology}
\label{sec:methodology}

\subsection{Sample Construction and Data Sources}
\label{sec:sample}

[Describe:
1. Primary data source(s)
2. Sample period
3. Selection criteria
4. Sample construction process (with reference to Figure 1)
5. Final sample size (N = X firm-years)

Example:
Our primary data come from [source], which provides [information].
We supplement with [additional sources] for [variables]. The sample
covers the period [years] and includes [criteria] firms. We exclude
[reasons] observations, resulting in a final sample of [N] firm-year
observations spanning [industries] industries. Table~\ref{tab:sample}
and Figure~\ref{fig:sample} detail the sample construction process.]

\subsection{Variable Definitions}
\label{sec:var_def}

[Define all variables in a clear table. Include:

\textbf{Dependent Variable}: [Y definition and source]
\textbf{Key Independent Variable}: [X definition and source]
\textbf{Control Variables}: [C1, C2, C3 definitions and sources]
\textbf{Mediator Variables} (if applicable): [M definition]

Refer to Table~\ref{tab:var_def} for detailed definitions.]

\begin{table}[htbp]
  \centering
  \caption{Variable Definitions}
  \label{tab:var_def}
  \begin{threeparttable}
  \begin{tabular}{lclc}
    \hline\hline
    \textbf{Variable} & \textbf{Definition} & \textbf{Source} \\
    \hline
    \textit{Dependent Variable} & & \\
    $Y$ & [Definition] & [Source] \\
    \hline
    \textit{Key Independent Variable} & & \\
    $X$ & [Definition] & [Source] \\
    \hline
    \textit{Control Variables} & & \\
    $Size$ & [Definition] & [Source] \\
    $LEV$ & [Definition] & [Source] \\
    $ROA$ & [Definition] & [Source] \\
    \hline\hline
  \end{tabular}
  \begin{tablenotes}
    \item[1] [Additional notes on variable construction]
    \item[2] [Winsorization details if applicable]
  \end{tablenotes}
  \end{threeparttable}
\end{table}

\subsection{Descriptive Statistics}
\label{sec:descriptive}

[Report and discuss descriptive statistics.
Reference Table~\ref{tab:summary} for summary statistics
and Table~\ref{tab:correlation} for correlation matrix.

Key points to discuss:
- Sample composition
- Key variable distributions
- Potential concerns (multicollinearity, outliers, etc.)]

\subsection{Empirical Strategy}
\label{sec:strategy}

\textbf{Baseline Regression Model}:
\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta \cdot X_{it} + \gamma \cdot Controls_{it}
    + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

[Explain each component of the model.
State the identification strategy (DID/IV/RDD/etc.).
Discuss why this strategy addresses endogeneity.
State the fixed effects and clustering level.]

\textbf{[Identification Strategy Details]}:
[For DID: Explain the treatment/control group assignment.
For IV: Discuss instrument validity (relevance and exclusion restriction).
For RDD: Describe the running variable and cutoff.]

\textbf{Parallel Trends Assumption} (for DID):
[State the parallel trends assumption and how it will be tested.
Reference Figure~\ref{fig:trends} for the pre-treatment trends test.]
```

#### 中文方法论模板

```latex
\section{研究设计}
\label{sec:methodology}

\subsection{一、样本选择与数据来源}

[描述：
1. 主要数据来源
2. 样本时间范围
3. 样本选择标准
4. 样本筛选过程（参考图1）
5. 最终样本量（N = X 公司-年）

数据来源列表：
\begin{itemize}
    \item [数据1]: [来源]，包含[变量]，时间范围[年/月]
    \item [数据2]: [来源]...
\end{itemize}]

\subsection{二、变量定义}

[定义所有变量，包括：

\textbf{被解释变量}：[Y的定义和来源]
\textbf{核心解释变量}：[X的定义和来源]
\textbf{控制变量}：[C1、C2、C3的定义和来源]
\textbf{中介变量}（如有）：[M的定义]

详见表~\ref{tab:var_def}。]

\begin{table}[htbp]
  \centering
  \caption{变量定义}
  \label{tab:var_def}
  \begin{threeparttable}
  \begin{tabular}{lccc}
    \hline\hline
    变量 & 变量名称 & 衡量方式 & 数据来源 \\
    \hline
    \textit{被解释变量} & & & \\
    $Y$ & [名称] & [定义] & [来源] \\
    \hline
    \textit{核心解释变量} & & & \\
    $X$ & [名称] & [定义] & [来源] \\
    \hline
    \textit{控制变量} & & & \\
    $Size$ & [名称] & [定义] & [来源] \\
    $LEV$ & [名称] & [定义] & [来源] \\
    $ROA$ & [名称] & [定义] & [来源] \\
    \hline\hline
  \end{tabular}
  \begin{tablenotes}
    \item[1] [补充说明]
  \end{tablenotes}
  \end{threeparttable}
\end{table}

\subsection{三、描述性统计}

[报告和讨论描述性统计。
参考表~\ref{tab:summary}和表~\ref{tab:correlation}。

讨论要点：
- 样本构成
- 主要变量的分布特征
- 多重共线性和极端值问题]

\subsection{四、实证模型}

\textbf{基准回归模型}：
\begin{equation}
\label{eq:baseline}
Y_{it} = \alpha + \beta \cdot X_{it} + \gamma \cdot Controls_{it}
    + \mu_i + \lambda_t + \varepsilon_{it}
\end{equation}

[解释模型中各变量的含义。
$\beta$是核心系数，衡量...]
[固定效应设置：$\mu_i$表示[公司]固定效应，$\lambda_t$表示[年份]固定效应]
[标准误聚类：在[公司]层面聚类，参考\citet{pcse2015}]

\textbf{[识别策略]（如DID）}：
[描述处理组/对照组的划分依据]
[平行趋势假设：处理组和对照组在政策实施前有相似的趋势]
[检验方法：参考图~\ref{fig:trends}]
```

---

### Empirical Results / 实证结果

#### 英文结果模板

```latex
\section{Results}
\label{sec:results}

\subsection{Parallel Trends Verification}
\label{sec:trends}

[Reference Figure~\ref{fig:trends}.
Discuss pre-treatment trends: are they parallel?
Report statistical tests for parallel trends.
State whether the parallel trends assumption holds.]

\begin{figure}[htbp]
  \centering
  \includegraphics[width=0.8\textwidth]{fig_trends.pdf}
  \caption{Parallel Trends Verification}
  \label{fig:trends}
\end{figure}

\subsection{Main Results}
\label{sec:main_results}

[Reference Table~\ref{tab:main}.
Column-by-column interpretation of results.
Start with simple specifications, add controls and fixed effects.

Example:
Table~\ref{tab:main} reports the baseline regression results.
Column (1) reports the bivariate relationship between X and Y.
The coefficient on X is [positive/negative] and statistically significant
([t-stat] in parentheses). Column (2) adds control variables...
Column (3) adds firm and year fixed effects...
Column (4) is our preferred specification...

The estimated coefficient in column (4) implies that a one-standard-deviation
increase in X is associated with [Y]\% [increase/decrease] in the outcome,
representing an economically meaningful effect.]

\begin{table}[htbp]
  \centering
  \caption{Main Results}
  \label{tab:main}
  \begin{threeparttable}
  \begin{tabular}{lcccc}
    \toprule
    & \multicolumn{4}{c}{Dependent Variable: $Y$} \\
    \cmidrule{2-5}
    & (1) & (2) & (3) & (4) \\
    \midrule
    $X$ & [coef]\{se\} & [coef]\{se\} & [coef]\{se\} & [coef]\{se\} \\
    \midrule
    Controls & No & Yes & Yes & Yes \\
    Firm FE & No & No & Yes & Yes \\
    Year FE & No & No & Yes & Yes \\
    \midrule
    Observations & [N] & [N] & [N] & [N] \\
    $R^2$ & [R2] & [R2] & [R2] & [R2] \\
    \bottomrule
  \end{tabular}
  \begin{tablenotes}
    \item \textit{Notes:} This table reports...
    \item Standard errors in parentheses are clustered at the firm level.
    \item *** p<0.01, ** p<0.05, * p<0.1
  \end{tablenotes}
  \end{threeparttable}
\end{table}

\subsection{Economic Magnitude}
\label{sec:magnitude}

[Discuss economic significance beyond statistical significance.
Calculate and interpret:
- Marginal effects
- Elasticities
- Economic scale (e.g., \% of mean outcome)

Reference Figure~\ref{fig:magnitude} for visualization.]

\subsection{Heterogeneity Analysis}
\label{sec:heterogeneity}

[Reference Table~\ref{tab:heterogeneity} or Figure~\ref{fig:heterogeneity}.
Discuss how effects vary across:
- Firm size
- Industry
- Region
- Time period
- Other relevant dimensions]

\subsection{Mechanism Tests}
\label{sec:mechanism}

[Reference Figure~\ref{fig:mechanism}.
Test the proposed mechanisms/channels using:
- Mediation analysis (three-step approach)
- Interactive effects
- Subsample analysis

Example:
To investigate the mechanism, we follow \citet{mediation2014} and conduct
a three-step mediation analysis...
The results suggest that [M] mediates [X\%] of the total effect.]
```

#### 中文结果模板

```latex
\section{实证结果与分析}
\label{sec:results}

\subsection{一、基准回归结果}

[参考表~\ref{tab:main}。
逐列解读结果，从简单规格到复杂规格。

示例：
表~\ref{tab:main}报告了基准回归结果。第(1)列仅包含核心解释变量X，
系数为[正值/负值]且在[1\%/5\%/10\%]水平上显著。第(2)列加入控制变量后，
X的系数[略有变化/保持不变]...第(3)列进一步加入固定效应...
第(4)列是本文的主回归规格...

主规格的估计系数表明，X每增加一个标准差，Y相应[增加/减少]约[幅度]，
占Y基准均值的[X\%]，经济意义[显著/有限]。]

\begin{table}[htbp]
  \centering
  \caption{基准回归结果}
  \label{tab:main}
  \begin{threeparttable}
  \begin{tabular}{lcccc}
    \hline\hline
     & \multicolumn{4}{c}{被解释变量：Y} \\
    \cline{2-5}
     & (1) & (2) & (3) & (4) \\
    \hline
    $X$ & [系数] & [系数] & [系数] & [系数] \\
     & ([标准误]) & ([标准误]) & ([标准误]) & ([标准误]) \\
    \hline
    控制变量 & 否 & 是 & 是 & 是 \\
    企业固定效应 & 否 & 否 & 是 & 是 \\
    年份固定效应 & 否 & 否 & 是 & 是 \\
    \hline
    观测值 & [N] & [N] & [N] & [N] \\
    $R^2$ & [R2] & [R2] & [R2] & [R2] \\
    \hline\hline
  \end{tabular}
  \begin{tablenotes}
    \item \textit{注：}... \\
    \item 括号内为在企业层面聚类的标准误。*** p<0.01, ** p<0.05, * p<0.1
  \end{tablenotes}
  \end{threeparttable}
\end{table}

\subsection{二、经济显著性分析}

[讨论经济显著性而不仅是统计显著性。
计算并解释：
- 边际效应
- 弹性
- 经济规模估算]

\subsection{三、异质性分析}

[参考表~\ref{tab:heterogeneity}或图~\ref{fig:heterogeneity}。
讨论效应在不同子样本中的差异：
- 企业规模
- 行业
- 地区
- 时间段]

\subsection{四、机制检验}

[参考图~\ref{fig:mechanism}。
使用以下方法检验传导机制：
- 中介效应三步法
- 交互项分析
- 分样本分析]

\subsection{五、稳健性检验}

[参考表~\ref{tab:robustness}和图~\ref{fig:placebo}。
逐一报告稳健性检验结果：
\textbf{替换被解释变量}：表~\ref{tab:robust_y}
\textbf{替换核心解释变量}：表~\ref{tab:robust_x}
\textbf{去除极端值}：表~\ref{tab:robust_trim}
\textbf{子样本回归}：表~\ref{tab:robust_subsample}
\textbf{安慰剂检验}：图~\ref{fig:placebo}
\textbf{工具变量}：表~\ref{tab:robust_iv}]
```

---

### Conclusion / 结论

#### 英文结论模板

```latex
\section{Conclusion}
\label{sec:conclusion}

[Summary: 500-800 words]

\textbf{Summary of Main Findings}:
This paper examines whether [RESEARCH QUESTION]. Using [DATA] and
[IDENTIFICATION STRATEGY], we find that [MAIN FINDING 1] and [MAIN FINDING 2].

\textbf{Mechanisms}:
The effect operates primarily through [MECHANISM]. [Additional mechanism discussion.]

\textbf{Academic Contributions}:
This paper makes three main contributions. First, [contribution 1]...
Second, [contribution 2]... Third, [contribution 3]...

\textbf{Policy/Practical Implications}:
The findings have important implications for [policymakers/investors/regulators/firms].
Specifically, [specific recommendations]...

\textbf{Limitations}:
This study has several limitations. First, [limitation 1]...
Second, [limitation 2]... Future research could address these limitations by [suggestions].
```

#### 中文结论模板

```latex
\section{结论与启示}
\label{sec:conclusion}

\subsection{一、主要结论}

[总结全文（500-800字）：
1. 核心发现一
2. 核心发现二
3. 机制分析结果]

本文基于[数据来源]，利用[计量方法]考察了[研究问题]。
实证结果表明：[主要结论1]...[主要结论2]...

\subsection{二、学术贡献}

本文对[文献A]和[文献B]有如下贡献：
第一，[贡献1]...
第二，[贡献2]...
第三，[贡献3]...

\subsection{三、政策启示}

[对不同主体的启示：
- 对监管机构：...
- 对企业管理者：...
- 对投资者：...]

\subsection{四、研究局限与未来方向}

本文存在以下局限：
第一，[局限1]...
第二，[局限2]...

未来的研究可以从以下方向拓展：
第一，[可能的研究方向1]...
第二，[可能的研究方向2]...
```

---

## 参考文献格式

### BibTeX模板

```bibtex
@article{author_year,
  title     = {Paper Title},
  author    = {Author, A. and Author, B.},
  journal   = {Journal Name},
  year      = {YYYY},
  volume    = {XX},
  number    = {X},
  pages     = {XXX--XXX},
  doi       = {10.XXXX/j.XXXX.XXXX.XXXX}
}

@book{author_book,
  title     = {Book Title},
  author    = {Author, A.},
  publisher = {Publisher},
  year      = {YYYY},
  address   = {City}
}

@misc{author_year,
  title     = {Working Paper Title},
  author    = {Author, A.},
  year      = {YYYY},
  howpublished = {Available at SSRN: \url{https://ssrn.com/abstract=XXXX}}}
```

### 引用规范

| 期刊风格 | 引用格式 | LaTeX命令 |
|----------|----------|-----------|
| JF/JFE/RFS | Author (Year) | `\citep{key}` 或 `\citet{key}` |
| 经济研究 | 顺序编码 | `\cite{key}` |
| AEA | Author (Year) | `\citep{key}` |

---

## 占位符规则

首次生成时，对尚未确定的数值使用占位符：

| 占位符 | 含义 |
|--------|------|
| `[coef]` | 待填入的回归系数 |
| `[se]` | 待填入的标准误 |
| `[N]` | 待填入的样本量 |
| `[R2]` | 待填入的R方 |
| `[p-value]` | 待填入的p值 |
| `[sig]` | 显著性标记（***/**/*） |

---

## 控制标志

| 标志 | 默认值 | 说明 |
|------|--------|------|
| LANGUAGE | `english` 或 `chinese` | 论文语言 |
| JOURNAL | 目标期刊 | 确定模板格式 |
| DRAFT_VERSION | `v1` | 草稿版本号 |
| PLACEHOLDER_MODE | `true` | 首次生成使用占位符 |
| HUMAN_CHECKPOINT | `true` | 每章节后暂停确认 |

---

## 关键原则

1. **先有骨架，再填血肉**。按PAPER_OUTLINE.md的结构严格写作。
2. **引用要精确**。每个论断必须有文献支撑，禁止无引用的一般性陈述。
3. **数据位置要对应**。文字中引用的图表编号必须与实际表格编号一致。
4. **实证结果必须与REFINED_DESIGN.md一致**。不要凭空编造系数和标准误。
5. **假设推导要有理论链条**。H1→H2→H3的逻辑要连贯。
6. **稳健性检验要有解释**。为什么做这些检验？它们分别验证什么威胁？
7. **LaTeX公式要编号**。所有重要公式使用 `\label{}` 编号，方便交叉引用。
8. **第一次生成用占位符**。对于真实系数和标准误，使用占位符，由后续数据填充。
9. **中英文分开生成**。英文论文按英文格式，中文论文按中文格式，不要混用。
10. **结论不过度推断**。结论只能基于本文实证结果，不能过度延伸。
11. **表格使用三段式（threeparttable）**。中文顶刊要求caption在上、notes在下。
12. **显著性标记统一**。使用 `***, **, *` 格式。
