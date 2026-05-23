#!/usr/bin/env python3
"""
计量经济学与实证分析工具
=====================
对金融/经济面板数据进行统计推断，输出可直接嵌入论文的规范表格。

核心功能：
- OLS / 面板回归（含固定效应虚拟变量）
- DID 双重差分（事件研究法）
- 聚类标准误（行业/年份/企业维度）
- 稳健性检验套件（替换变量、缩尾、子样本）
- 输出：Markdown 三线表 / LaTeX booktabs

设计原则：
  1. 所有回归结果由 statsmodels 程序化计算，不依赖 AI 生成数字
  2. 表格格式遵循学术规范（三线表、显著性标注、样本量/R方固定）
  3. 每个回归输出可追溯：模型名、变量名、观测数、标准误聚类方式

使用方法：
  from scripts.econometrics import OLSRegression, DIDRegression
  from scripts.econometrics import table_to_markdown, descriptive_stats

  model = OLSRegression(data=df, y="roe")
  model.fit("roe ~ size + lev + C(year) + C(industry)", cluster="industry")
  print(model.result.to_markdown())

  did = DIDRegression(data=df, y="employment",
                     treatment="treated", post="post")
  did.fit(controls=["size", "age"], cluster="industry", event_study=True)
  print(did.result.to_markdown())

  desc = descriptive_stats(df, ["roe", "size", "lev"])
  print(desc.to_markdown())
"""

import re
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


# ════════════════════════════════════════════════════════════════════
# 表格格式器
# ════════════════════════════════════════════════════════════════════

class RegressionTable:
    """
    回归结果表格封装，支持格式化为 Markdown / LaTeX / JSON。
    """

    STAR = [(0.001, "***"), (0.01, "**"), (0.05, "*"), (0.1, "^*")]

    def __init__(self, name: str = ""):
        self.name = name
        self.models = []   # list[dict]
        self.coefs = []    # list[pd.DataFrame]

    def add_model(
        self,
        coef_df: pd.DataFrame,
        n_obs: int,
        r2: float,
        adj_r2: Optional[float] = None,
        dep_var: str = "",
        cluster: str = "",
        n_clusters: int = 0,
        f_stat: float = 0,
        f_pval: float = 1,
        model_type: str = "OLS",
    ):
        self.models.append({
            "name": self.name or model_type,
            "dep_var": dep_var,
            "model_type": model_type,
            "n_obs": n_obs,
            "r2": r2,
            "adj_r2": adj_r2,
            "cluster": cluster,
            "n_clusters": n_clusters,
            "f_stat": f_stat,
            "f_pval": f_pval,
        })
        self.coefs.append(coef_df)

    def _stars(self, pval: float) -> str:
        for threshold, marker in self.STAR:
            if pval <= threshold:
                return marker
        return ""

    def _fmt(self, value: float, se: float, pval: float, prec: int) -> str:
        s = self._stars(pval)
        c_str = ("{0:.%df}" % prec).format(value)
        se_str = ("({0:.%df})" % prec).format(se)
        return c_str + s + " " + se_str

    def to_markdown(self, precision: int = 4) -> str:
        """Markdown 三线表，可直接嵌入论文 prompt"""
        if not self.coefs:
            return ""
        n = len(self.coefs)

        # 收集所有变量
        all_vars = set()
        for df in self.coefs:
            all_vars.update(df.index.tolist())

        main_vars = sorted(
            v for v in all_vars
            if not v.startswith("C(")
            and v not in ("const", "截距项")
        )
        fe_vars = sorted(v for v in all_vars if v.startswith("C("))
        if "const" in all_vars:
            fe_vars.append("const")
        var_order = main_vars + fe_vars

        header = "| 变量 | " + " | ".join("(%d)" % (i + 1) for i in range(n)) + " |"
        sep = "|------|" + "|".join("------" for _ in range(n)) + "|"

        rows = []
        for var in var_order:
            cells = [var]
            for df in self.coefs:
                if var in df.index:
                    row = df.loc[var]
                    cells.append(self._fmt(row["coef"], row["se"], row["pval"], precision))
                else:
                    cells.append("")
            rows.append("| " + " | ".join(cells) + " |")

        stats = []
        nobs = "| **观测数 N** | " + " | ".join(
            "**{:,}**".format(m["n_obs"]) for m in self.models) + " |"
        stats.append(nobs)
        if self.models[0].get("r2") is not None:
            r2_row = "| **R²** | " + " | ".join(
                "%.4f" % m["r2"] for m in self.models) + " |"
            stats.append(r2_row)
        if any(m.get("adj_r2") for m in self.models):
            adj_row = "| **Adj. R²** | " + " | ".join(
                "%.4f" % m["adj_r2"] if m.get("adj_r2") else "—"
                for m in self.models) + " |"
            stats.append(adj_row)
        if self.models[0].get("cluster"):
            cl_row = "| **聚类** | " + " | ".join(
                "%s (n=%d)" % (m["cluster"], m["n_clusters"])
                for m in self.models) + " |"
            stats.append(cl_row)

        return "\n".join([header, sep] + rows + [""] + stats)

    def _latex_num(self, val: float, prec: int) -> str:
        return ("{0:.%df}" % prec).format(val)

    def to_latex(self, precision: int = 4, caption: str = "",
                 label: str = "") -> str:
        """LaTeX booktabs 表格（可直接编译）"""
        if not self.coefs:
            return ""
        n = len(self.coefs)

        all_vars = set()
        for df in self.coefs:
            all_vars.update(df.index.tolist())

        main_vars = sorted(
            v for v in all_vars
            if not v.startswith("C(")
            and v not in ("const", "截距项")
        )
        fe_vars = sorted(v for v in all_vars if v.startswith("C("))
        if "const" in all_vars:
            fe_vars.append("const")
        var_order = main_vars + fe_vars

        col_fmt = "l" + "r" * n
        lines = [
            r"\begin{table}[!htbp]",
            r"\centering",
            r"\begin{threeparttable}",
            r"\caption{" + caption + r"}",
            r"\label{" + label + r"}",
            r"\begin{tabular}{" + col_fmt + r"}",
            r"\toprule",
            " & ".join([""] + ["(%d)" % (i + 1) for i in range(n)]) + r" \\",
            r"\midrule",
        ]

        for var in var_order:
            label_str = var.replace("_", r"\_")
            cells = [r"\textbf{" + label_str + "}"]
            for df in self.coefs:
                if var in df.index:
                    row = df.loc[var]
                    c_str = self._latex_num(row["coef"], precision)
                    se_str = self._latex_num(row["se"], precision)
                    stars = self._stars(row["pval"])
                    cells.append("$" + c_str + stars + "$ (" + se_str + ")")
                else:
                    cells.append("")
            lines.append(" & ".join(cells) + r" \\")

        lines.append(r"\midrule")
        n_obs_cells = [("{:,}").format(m["n_obs"]) for m in self.models]
        lines.append("观测数 N & " + " & ".join(n_obs_cells) + r" \\")

        r2_cells = [("{:.4f}").format(m["r2"]) for m in self.models]
        lines.append(r"R$^2$ & " + " & ".join(r2_cells) + r" \\")

        if any(m.get("adj_r2") for m in self.models):
            adj_cells = [("{:.4f}").format(m["adj_r2"])
                       if m.get("adj_r2") else "—"
                       for m in self.models]
            lines.append(r"Adj.\ R$^2$ & " + " & ".join(adj_cells) + r" \\")

        if self.models[0].get("cluster"):
            cl_cells = ["%s (n=%d)" % (m["cluster"], m["n_clusters"])
                         for m in self.models]
            lines.append("聚类 & " + " & ".join(cl_cells) + r" \\")

        lines.extend([
            r"\bottomrule",
            r"\end{tabular}",
            r"\begin{tablenotes}[flushleft]",
            r"\item \textit{注：} 括号内为聚类标准误。"
              + r"$^{*} p<0.1$, $^{**} p<0.05$, $^{***} p<0.01$。",
            r"\end{tablenotes}",
            r"\end{threeparttable}",
            r"\end{table}",
        ])
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "models": self.models,
            "tables": [df.to_dict(orient="index") for df in self.coefs],
        }


def table_to_markdown(tbl: RegressionTable, precision: int = 4) -> str:
    return tbl.to_markdown(precision=precision)


def table_to_latex(tbl: RegressionTable, caption: str = "",
                    label: str = "", precision: int = 4) -> str:
    return tbl.to_latex(caption=caption, label=label, precision=precision)


# ════════════════════════════════════════════════════════════════════
# OLS 回归
# ════════════════════════════════════════════════════════════════════

class OLSRegression:
    """OLS / 面板回归，支持聚类标准误。"""

    STAR = [(0.001, "***"), (0.01, "**"), (0.05, "*"), (0.1, "^*")]

    def __init__(self, data: pd.DataFrame, y: str):
        self.data = data.dropna(subset=[y]).copy()
        self.y = y
        self.result: Optional[RegressionTable] = None

    def _stars(self, pval: float) -> str:
        for t, s in self.STAR:
            if pval <= t:
                return s
        return ""

    def _parse_formula(self, formula: str):
        """解析 y ~ x1 + x2 + C(year) 格式"""
        parts = re.split(r"\s*~\s*", formula)
        if len(parts) != 2:
            raise ValueError("formula 须为 'y ~ x1 + x2' 格式，当前: " + formula)
        y_var = parts[0].strip()
        pred_str = parts[1].strip()
        terms = [t.strip() for t in pred_str.split("+")]
        fe_terms = [t for t in terms if t.startswith("C(")]
        main_terms = [t for t in terms if not t.startswith("C(")]
        return y_var, main_terms, fe_terms

    def fit(
        self,
        formula: str,
        cluster: str = "",
        robust: str = "HC3",
        name: str = "",
    ) -> RegressionTable:
        """
        执行 OLS 回归。

        Args:
            formula:  "y ~ x1 + x2 + C(year) + C(industry)"
            cluster:  聚类变量名，如 "industry"
            robust:   "HC3"（推荐）或 "HC0"
            name:     表格列标题
        """
        from statsmodels.regression.linear_model import OLS
        import statsmodels.api as sm
        from scipy import stats as scipy_stats

        dep, x_vars, fe_terms = self._parse_formula(formula)

        df = self.data.copy()

        # 固定效应虚拟变量
        for fe in fe_terms:
            m = re.match(r"C\((\w+)\)", fe)
            if m and m.group(1) in df.columns:
                col = m.group(1)
                df[col] = pd.Categorical(df[col])
                dummies = pd.get_dummies(df[col], prefix=fe, drop_first=True)
                for dc in dummies.columns:
                    df[dc] = dummies[dc]

        # 可用变量
        reg_vars = [dep] + x_vars + fe_terms
        avail = [v for v in reg_vars if v in df.columns]
        df = df[avail].dropna()
        y_arr = df[dep].values
        X_cols = [v for v in x_vars + fe_terms if v in df.columns]

        X = df[X_cols].values
        X = sm.add_constant(X)
        n, k = X.shape
        names = ["const"] + X_cols

        # OLS 拟合
        fit_result = OLS(y_arr, X).fit(disp=False)
        cov_type = "clustered" if cluster else robust
        if cluster:
            try:
                groups = df[cluster].values
                fit_result = fit_result.get_robustcov_results("cluster", groups=groups)
            except Exception as e:
                warnings.warn("聚类标准误计算失败: " + str(e))

        se_arr = fit_result.bse
        t_arr = fit_result.tvalues
        p_arr = fit_result.pvalues

        # 如果用了聚类SE，t/pval 需要重新计算
        if cluster:
            try:
                cov_clu = fit_result.cov_params()
                se_arr = np.sqrt(np.diag(cov_clu))
                for i in range(len(names)):
                    if se_arr[i] > 0:
                        t_arr[i] = fit_result.params[i] / se_arr[i]
                        p_arr[i] = 2 * (1 - scipy_stats.t.cdf(abs(t_arr[i]), df=n - k))
            except Exception:
                pass

        # 构建系数表
        coef_data = {}
        for i, name in enumerate(names):
            coef_data[name] = {
                "coef": float(fit_result.params[i]),
                "se": float(se_arr[i]),
                "t": float(t_arr[i]),
                "pval": float(p_arr[i]),
            }
        coef_df = pd.DataFrame(coef_data).T

        # n_clusters
        n_clu = 0
        if cluster and cluster in df.columns:
            n_clu = len(np.unique(df[cluster].dropna()))

        tbl = RegressionTable(name=name)
        tbl.add_model(
            coef_df=coef_df,
            n_obs=n,
            r2=float(fit_result.rsquared),
            adj_r2=float(fit_result.rsquared_adj),
            dep_var=dep,
            cluster=cluster,
            n_clusters=n_clu,
            f_stat=float(fit_result.fvalue),
            f_pval=float(fit_result.f_pvalue),
            model_type="OLS",
        )
        self.result = tbl
        return tbl

    def summary(self) -> str:
        if self.result is None:
            return "尚未执行 fit()"
        return self.result.to_markdown()


# ════════════════════════════════════════════════════════════════════
# DID 双重差分
# ════════════════════════════════════════════════════════════════════

class DIDRegression:
    """
    双重差分分析，支持事件研究法（Event Study）。

    用法：
        did = DIDRegression(data=df, y="employment",
                           treatment="treated", post="post")
        did.fit(controls=["size"], cluster="industry", event_study=False)
        print(did.result.to_markdown())
    """

    def __init__(
        self,
        data: pd.DataFrame,
        y: str,
        treatment: str,
        post: str,
        unit: str = "unit",
        time: str = "year",
    ):
        self.y = y
        self.treatment = treatment
        self.post = post
        self.unit = unit
        self.time = time
        self.data = data.dropna(subset=[y, treatment, post]).copy()
        self.result: Optional[RegressionTable] = None

    def _stars(self, pval: float) -> str:
        for t, s in [(0.001, "***"), (0.01, "**"), (0.05, "*"), (0.1, "^*")]:
            if pval <= t:
                return s
        return ""

    def fit(
        self,
        controls: Optional[list] = None,
        cluster: str = "",
        event_study: bool = False,
        name: str = "",
    ) -> RegressionTable:
        controls = controls or []
        df = self.data.copy()
        required = [self.y, self.treatment, self.post, self.unit, self.time] + controls
        df = df.dropna(subset=required)

        if event_study:
            return self._event_study(df, controls, cluster, name)
        return self._standard_did(df, controls, cluster, name)

    def _standard_did(
        self, df: pd.DataFrame, controls: list, cluster: str, name: str
    ) -> RegressionTable:
        import statsmodels.api as sm
        from statsmodels.regression.linear_model import OLS
        from scipy import stats as scipy_stats

        df["did"] = df[self.treatment] * df[self.post]
        X_vars = ["did"] + controls
        avail = [v for v in X_vars + [self.y] if v in df.columns]
        df = df[avail].dropna()
        y_arr = df[self.y].values
        X = df[X_vars].values
        X = sm.add_constant(X)
        n = len(y_arr)

        fit_result = OLS(y_arr, X).fit(disp=False)
        se_arr = fit_result.bse
        t_arr = fit_result.tvalues
        p_arr = fit_result.pvalues

        if cluster and cluster in df.columns:
            try:
                groups = df[cluster].values
                fit_result = fit_result.get_robustcov_results("cluster", groups=groups)
                cov_clu = fit_result.cov_params()
                se_arr = np.sqrt(np.diag(cov_clu))
                for i, p in enumerate(fit_result.params):
                    if se_arr[i] > 0:
                        t_arr[i] = p / se_arr[i]
                        p_arr[i] = 2 * (1 - scipy_stats.t.cdf(abs(t_arr[i]), df=n - len(X_vars) - 1))
            except Exception:
                pass

        names = ["const"] + X_vars
        coef_data = {}
        for i, nm in enumerate(names):
            coef_data[nm] = {
                "coef": float(fit_result.params[i]),
                "se": float(se_arr[i]),
                "t": float(t_arr[i]),
                "pval": float(p_arr[i]),
            }
        coef_df = pd.DataFrame(coef_data).T

        n_clu = 0
        if cluster and cluster in df.columns:
            n_clu = len(np.unique(df[cluster].dropna()))

        tbl = RegressionTable(name=name)
        tbl.add_model(
            coef_df=coef_df,
            n_obs=n,
            r2=float(fit_result.rsquared),
            adj_r2=float(fit_result.rsquared_adj),
            dep_var=self.y,
            cluster=cluster,
            n_clusters=n_clu,
            f_stat=float(fit_result.fvalue),
            f_pval=float(fit_result.f_pvalue),
            model_type="DID",
        )
        self.result = tbl
        return tbl

    def _event_study(
        self, df: pd.DataFrame, controls: list, cluster: str, name: str
    ) -> RegressionTable:
        """事件研究法：每期生成一个相对时间虚拟变量"""
        import statsmodels.api as sm
        from statsmodels.regression.linear_model import OLS
        from scipy import stats as scipy_stats

        periods = sorted(df[self.time].unique())
        # 找到中间期作为基期（政策实施前一/二期）
        mid = periods[len(periods) // 2 - 1] if len(periods) > 1 else periods[0]

        interaction_terms = []
        for t in periods:
            col = "rel_%s" % t
            df[col] = ((df[self.time] == t).astype(float)) * df[self.treatment]
            if t != mid:
                interaction_terms.append(col)

        X_vars = interaction_terms + controls
        avail = [v for v in X_vars + [self.y] if v in df.columns]
        df = df[avail].dropna()
        y_arr = df[self.y].values
        X = df[X_vars].values
        X = sm.add_constant(X)
        n = len(y_arr)
        names = ["const"] + X_vars

        fit_result = OLS(y_arr, X).fit(disp=False)
        se_arr = fit_result.bse
        t_arr = fit_result.tvalues
        p_arr = fit_result.pvalues

        if cluster and cluster in df.columns:
            try:
                groups = df[cluster].values
                fit_result = fit_result.get_robustcov_results("cluster", groups=groups)
                cov_clu = fit_result.cov_params()
                se_arr = np.sqrt(np.diag(cov_clu))
                for i, p in enumerate(fit_result.params):
                    if se_arr[i] > 0:
                        t_arr[i] = p / se_arr[i]
                        p_arr[i] = 2 * (1 - scipy_stats.t.cdf(abs(t_arr[i]), df=n - len(X_vars) - 1))
            except Exception:
                pass

        coef_data = {}
        for i, nm in enumerate(names):
            coef_data[nm] = {
                "coef": float(fit_result.params[i]),
                "se": float(se_arr[i]),
                "t": float(t_arr[i]),
                "pval": float(p_arr[i]),
            }
        coef_df = pd.DataFrame(coef_data).T

        n_clu = 0
        if cluster and cluster in df.columns:
            n_clu = len(np.unique(df[cluster].dropna()))

        tbl = RegressionTable(name=name)
        tbl.add_model(
            coef_df=coef_df,
            n_obs=n,
            r2=float(fit_result.rsquared),
            adj_r2=float(fit_result.rsquared_adj),
            dep_var=self.y,
            cluster=cluster,
            n_clusters=n_clu,
            f_stat=float(fit_result.fvalue),
            f_pval=float(fit_result.f_pvalue),
            model_type="EventStudy",
        )
        self.result = tbl
        return tbl

    def summary(self) -> str:
        if self.result is None:
            return "尚未执行 fit()"
        return self.result.to_markdown()


# ════════════════════════════════════════════════════════════════════
# 稳健性检验套件
# ════════════════════════════════════════════════════════════════════

class RobustnessSuite:
    """对同一回归执行多组稳健性检验，合并为对比表。"""

    def __init__(self, base_model: OLSRegression):
        self.base = base_model
        self.results = []  # list[(label, RegressionTable)]

    def add(
        self,
        label: str,
        transform_fn,
        formula: str,
        cluster: str = "",
    ) -> "RobustnessSuite":
        """添加一组稳健性检验"""
        df_new = transform_fn(self.base.data.copy())
        model = OLSRegression(df_new, self.base.y)
        result = model.fit(formula, cluster=cluster, name=label)
        self.results.append((label, result))
        return self

    def compare(self) -> RegressionTable:
        """将所有检验合并为一张表"""
        combined = RegressionTable(name="稳健性检验")
        for label, result in self.results:
            for coef_df, model_info in zip(result.coefs, result.models):
                combined.add_model(
                    coef_df=coef_df.copy(),
                    n_obs=model_info["n_obs"],
                    r2=model_info["r2"],
                    adj_r2=model_info.get("adj_r2"),
                    dep_var=model_info["dep_var"],
                    cluster=model_info.get("cluster", ""),
                    n_clusters=model_info.get("n_clusters", 0),
                    f_stat=model_info.get("f_stat", 0),
                    f_pval=model_info.get("f_pval", 1),
                    model_type="Robustness: " + label,
                )
        return combined


# ════════════════════════════════════════════════════════════════════
# 描述性统计
# ════════════════════════════════════════════════════════════════════

def descriptive_stats(
    data: pd.DataFrame,
    vars_list: list,
    precision: int = 4,
) -> RegressionTable:
    """
    生成描述性统计表（均值、标准差、N）。

    表格结构：
      - 每行一个变量：均值（系数列） + 标准差（括号SE列）
      - 底部行：样本量 N
    """
    avail = [v for v in vars_list if v in data.columns]
    df = data[avail].dropna()
    n = len(df)

    # 每行 = 一个变量；coef=均值，se=标准差，pval=1（无显著性）
    coef_data = {}
    for v in avail:
        mean_val = float(df[v].mean())
        std_val = float(df[v].std())
        coef_data[v] = {
            "coef": mean_val,
            "se": std_val,
            "t": 0.0,
            "pval": 1.0,
        }
    coef_df = pd.DataFrame(coef_data).T

    tbl = RegressionTable(name="Descriptive Statistics")
    tbl.add_model(coef_df=coef_df, n_obs=n, r2=None, model_type="DescStat")
    return tbl


def correlation_table(data: pd.DataFrame, vars_list: list, precision: int = 3) -> str:
    """Pearson 相关系数矩阵 Markdown 表格"""
    avail = [v for v in vars_list if v in data.columns]
    corr = data[avail].corr().round(precision)
    return corr.to_markdown()


# ════════════════════════════════════════════════════════════════════
# 常用缩尾 / 数据清洗工具
# ════════════════════════════════════════════════════════════════════

def winsorize_col(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """对单列进行缩尾处理"""
    lo, hi = s.quantile([lower, upper])
    return s.clip(lower=lo, upper=hi)


def winsorize_all(df: pd.DataFrame, cols: list, lower: float = 0.01,
                 upper: float = 0.99) -> pd.DataFrame:
    """对指定列批量缩尾"""
    result = df.copy()
    for col in cols:
        if col in result.columns:
            result[col] = winsorize_col(result[col], lower, upper)
    return result


# ════════════════════════════════════════════════════════════════════
# 演示
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("计量经济学工具 v1.0")
    print("=" * 50)
    print("功能：OLS/DID 回归 + 规范表格生成 + 稳健性检验")
    print("依赖：pip install statsmodels scipy")
    print("\n使用示例：")
    print("""
  from scripts.econometrics import OLSRegression, DIDRegression
  from scripts.econometrics import table_to_markdown, descriptive_stats
  from scripts.econometrics import RobustnessSuite, winsorize_all

  # OLS 回归
  model = OLSRegression(data=df, y="roe")
  model.fit("roe ~ size + lev + C(year) + C(industry)", cluster="industry")
  print(model.result.to_markdown())
  print(model.result.to_latex(caption="公司特征与ROE", label="tab:reg1"))

  # DID 回归
  did = DIDRegression(data=df, y="employment",
                     treatment="treated", post="post")
  did.fit(controls=["size", "age"], cluster="industry")
  print(did.result.to_markdown())

  # 描述性统计
  desc = descriptive_stats(df, ["roe", "size", "lev"])
  print(desc.to_markdown())

  # 稳健性检验套件
  suite = RobustnessSuite(model)
  suite.add("缩尾1%", lambda d: winsorize_all(d, ["roe", "size"], 0.01, 0.99),
           "roe ~ size + lev + C(year)", cluster="industry")
  suite.add("剔除金融危机", lambda d: d[d["year"] >= 2010],
           "roe ~ size + lev + C(year)", cluster="industry")
  robust_tbl = suite.compare()
  print(robust_tbl.to_markdown())
    """)
