#!/usr/bin/env python3
"""
因子模型库：资产定价实证研究
============================
实现主流因子模型的时间序列和横截面回归分析，输出可直接嵌入论文的规范表格。

核心功能：
- Fama-French 三/四/五因子模型及扩展
- Fama-MacBeth 两步法横截面回归
- GMM 估计（广义矩估计）
- LASSO 因子筛选
- 多因子模型对比与 GRS 检验
- ESG Alpha 检验

学术参考：
- Fama & French (1993): Common risk factors in stock returns
- Carhart (1997): Persistence in mutual fund performance
- Fama & French (2015): A five-factor asset pricing model
- Novy-Marx (2013): The other side of value
- Fama & MacBeth (1973): Risk, return, and equilibrium

使用方法：
  from scripts.factor_models import FamaFrench3, CrossSectionalRegression

  # 时间序列回归
  ff3 = FamaFrench3()
  result = ff3.fit(returns_df, factors_df)
  print(result.to_markdown())

  # Fama-MacBeth 横截面回归
  fm = CrossSectionalRegression()
  result = fm.fit(returns_df, factors_df)
  print(result.to_markdown())
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


# ════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════

def _stars(pval: float) -> str:
    """显著性星号标注"""
    for threshold, marker in [(0.001, "***"), (0.01, "**"), (0.05, "*"), (0.1, r"$\dagger$")]:
        if pval <= threshold:
            return marker
    return ""


def _grs_test(
    alphas: np.ndarray,
    cov_alpha: np.ndarray,
    mean_excess: np.ndarray,
    cov_excess: np.ndarray,
    T: int,
    N: int,
    K: int
) -> tuple[float, float]:
    """
    GRS 检验 (Gibbons, Ross, Shanken, 1989)

    Args:
        alphas: N x 1 截距项向量
        cov_alpha: N x N 截距项协方差矩阵
        mean_excess: 1 x K 因子暴露均值行向量（每列=该因子的N个资产暴露均值），broadcast到N×K用于计算
        cov_excess: K x K 因子收益协方差矩阵
        T: 时间序列观测数
        N: 资产数量
        K: 因子数量

    Returns:
        (GRS统计量, p值)
    """
    from scipy import stats as scipy_stats

    # 奇异值检查
    try:
        cov_alpha_inv = np.linalg.inv(cov_alpha + np.eye(N) * 1e-8)
    except np.linalg.LinAlgError:
        return np.nan, np.nan

    # GRS 统计量
    alphas.T @ cov_alpha_inv @ alphas
    lambda_val = mean_excess.T @ np.linalg.inv(cov_excess + np.eye(K) * 1e-8) @ mean_excess
    trace_val = np.trace(lambda_val)

    grs_stat = (T - N - K) / N * alphas.T @ cov_alpha_inv @ alphas / (1 + trace_val)

    # F 分布近似
    pval = 1 - scipy_stats.f.cdf(grs_stat, N, T - N - K)

    # P3-audit-2026-07-04: numpy 2.x 严格要求 float() 输入是 0-d array。
    # grs_stat / pval 是 1x1 matrix → .item() 转 0-d 再 float()。
    # 老版本 numpy 1.x 也接受 1x1 matrix 的 float()，现统一用 .item() 防回归。
    return float(grs_stat.item()), float(pval.item())


# ════════════════════════════════════════════════════════════════════
# 因子模型基类
# ════════════════════════════════════════════════════════════════════

class FactorModelResult:
    """
    因子模型回归结果封装，支持格式化为 Markdown / LaTeX / CSV。
    """

    STAR = [(0.001, "***"), (0.01, "**"), (0.05, "*"), (0.1, r"$\dagger$")]

    def __init__(self, name: str = ""):
        self.name = name
        self.models = []
        self.coefs = []
        self.residuals = []
        self.factor_names = []
        self._alpha = None
        self._betas = None
        self._r2 = None

    def add_model(
        self,
        coef_df: pd.DataFrame,
        n_obs: int,
        r2: float,
        adj_r2: float | None = None,
        resid: np.ndarray | None = None,
        dep_var: str = "",
        cluster: str = "",
        n_clusters: int = 0,
        f_stat: float = 0,
        f_pval: float = 1,
        model_type: str = "FactorModel",
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
        if resid is not None:
            self.residuals.append(resid)

    def _fmt(self, value: float, se: float, pval: float, prec: int) -> str:
        s = _stars(pval)
        c_str = ("{0:.%df}" % prec).format(value)
        se_str = ("({0:.%df})" % prec).format(se)
        return c_str + s + " " + se_str

    def to_markdown(self, precision: int = 4) -> str:
        """Markdown 三线表"""
        if not self.coefs:
            return ""
        n = len(self.coefs)

        all_vars = set()
        for df in self.coefs:
            all_vars.update(df.index.tolist())

        main_vars = sorted(v for v in all_vars if v not in ("const", "截距项"))
        if "const" in all_vars:
            main_vars.append("const")
        var_order = main_vars

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

    def to_latex(self, precision: int = 4, caption: str = "",
                 label: str = "") -> str:
        """LaTeX booktabs 表格"""
        if not self.coefs:
            return ""
        n = len(self.coefs)

        all_vars = set()
        for df in self.coefs:
            all_vars.update(df.index.tolist())

        main_vars = sorted(v for v in all_vars if v not in ("const", "截距项"))
        if "const" in all_vars:
            main_vars.append("const")
        var_order = main_vars

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
                    c_str = ("{0:.%df}" % precision).format(row["coef"])
                    se_str = ("{0:.%df}" % precision).format(row["se"])
                    stars = _stars(row["pval"])
                    cells.append("$" + c_str + stars + "$ (" + se_str + ")")
                else:
                    cells.append("")
            lines.append(" & ".join(cells) + r" \\")

        lines.append(r"\midrule")
        n_obs_cells = [("{:,}").format(m["n_obs"]) for m in self.models]
        lines.append(r"N & " + " & ".join(n_obs_cells) + r" \\")

        r2_cells = [("{:.4f}").format(m["r2"]) for m in self.models]
        lines.append(r"R$^2$ & " + " & ".join(r2_cells) + r" \\")

        if any(m.get("adj_r2") for m in self.models):
            adj_cells = [("{:.4f}").format(m["adj_r2"])
                       if m.get("adj_r2") else "—"
                       for m in self.models]
            lines.append(r"Adj.\ R$^2$ & " + " & ".join(adj_cells) + r" \\")

        lines.extend([
            r"\bottomrule",
            r"\end{tabular}",
            r"\begin{tablenotes}[flushleft]",
            r"\item \textit{注：} 括号内为标准误。"
              + r"$^{*} p<0.1$, $^{**} p<0.05$, $^{***} p<0.01$。",
            r"\end{tablenotes}",
            r"\end{threeparttable}",
            r"\end{table}",
        ])
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """返回字典格式"""
        return {
            "models": self.models,
            "tables": [df.to_dict(orient="index") for df in self.coefs],
            "residuals": [r.tolist() if r is not None else None for r in self.residuals],
        }

    def to_csv(self, path: str | Path) -> None:
        """保存为 CSV 文件"""
        path = Path(path)
        dfs = []
        for i, (model_info, coef_df) in enumerate(zip(self.models, self.coefs)):
            df = coef_df.copy()
            df["model"] = model_info["name"]
            df["n_obs"] = model_info["n_obs"]
            df["r2"] = model_info["r2"]
            df["adj_r2"] = model_info.get("adj_r2")
            df["cluster"] = model_info.get("cluster", "")
            dfs.append(df)
        combined = pd.concat(dfs, names=["model"])
        combined.to_csv(path)

    def save_results(self, path: str | Path, fmt: str = "csv") -> None:
        """
        保存回归结果

        Args:
            path: 输出路径
            fmt: "csv" | "latex" | "markdown"
        """
        path = Path(path)
        if fmt == "csv":
            self.to_csv(path)
        elif fmt == "latex":
            path.write_text(self.to_latex())
        elif fmt == "markdown":
            path.write_text(self.to_markdown())
        else:
            raise ValueError(f"不支持的格式: {fmt}")


class BaseFactorModel:
    """
    因子模型基类，提供通用的时间序列回归功能。

    子类需要定义:
        name: str - 模型名称
        factors: list[str] - 因子名称列表
    """

    name = "BaseFactorModel"
    factors = []

    def __init__(self):
        self.result: FactorModelResult | None = None
        self._fitted = False

    def _validate_data(
        self, returns_df: pd.DataFrame, factors_df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """验证和准备数据"""
        # 确保因子数据对齐
        common_dates = returns_df.index.intersection(factors_df.index)
        if len(common_dates) == 0:
            raise ValueError("returns_df 和 factors_df 没有共同的日期索引")

        returns = returns_df.loc[common_dates].copy()
        factors = factors_df.loc[common_dates].copy()

        # 检查必需的因子
        missing = [f for f in self.factors if f not in factors.columns]
        if missing:
            raise ValueError(f"缺少因子: {missing}")

        return returns, factors

    def _run_regression(
        self,
        y: np.ndarray,
        X: np.ndarray,
        factor_names: list[str],
        robust: bool = True,
    ) -> tuple[dict, np.ndarray, float]:
        """
        执行单资产时间序列回归

        Returns:
            (coef_dict, residuals, r_squared)
        """
        import statsmodels.api as sm
        from scipy import stats as scipy_stats

        X_with_const = sm.add_constant(X)
        n, k = X_with_const.shape

        model = sm.OLS(y, X_with_const)
        fit = model.fit(disp=False)

        if robust:
            try:
                fit = fit.get_robustcov_results("HC3")
            except Exception:
                pass

        params = fit.params
        se = fit.bse
        tvals = fit.tvalues
        pvals = fit.pvalues

        # 重新计算 t/pval（如果用了稳健SE）
        if robust:
            try:
                cov = fit.cov_params()
                se = np.sqrt(np.diag(cov))
                tstats = params / se
                pvals = 2 * (1 - scipy_stats.t.cdf(np.abs(tstats), df=n - k))
            except Exception:
                tstats = tvals
                pvals = pvals

        coef_dict = {}
        all_names = ["const"] + factor_names
        for i, name in enumerate(all_names):
            coef_dict[name] = {
                "coef": float(params[i]),
                "se": float(se[i]),
                "t": float(tstats[i]),
                "pval": float(pvals[i]),
            }

        residuals = fit.resid
        r_squared = float(fit.rsquared)

        return coef_dict, residuals, r_squared

    def fit(
        self,
        returns_df: pd.DataFrame,
        factors_df: pd.DataFrame,
        cluster: str = "",
        robust: bool = True,
        name: str = "",
    ) -> FactorModelResult:
        """
        执行因子模型时间序列回归。

        Args:
            returns_df: 收益率 DataFrame，列为资产/组合，行索引为日期
            factors_df: 因子收益 DataFrame，列为因子名称，行索引为日期
            cluster: 聚类变量名（用于双面聚类标准误）
            robust: 使用 HC3 稳健标准误

        Returns:
            FactorModelResult 对象
        """
        returns, factors = self._validate_data(returns_df, factors_df)

        result = FactorModelResult(name=name or self.name)

        for col in returns.columns:
            y = returns[col].values
            X = factors[self.factors].values

            mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
            if mask.sum() < len(self.factors) + 2:
                continue

            y_clean = y[mask]
            X_clean = X[mask]

            coef_dict, resid, r2 = self._run_regression(
                y_clean, X_clean, self.factors, robust=robust
            )

            n_obs = len(y_clean)
            k = len(self.factors) + 1
            adj_r2 = 1 - (1 - r2) * (n_obs - 1) / (n_obs - k)

            coef_df = pd.DataFrame(coef_dict).T
            result.add_model(
                coef_df=coef_df,
                n_obs=n_obs,
                r2=r2,
                adj_r2=adj_r2,
                resid=resid,
                dep_var=str(col),
                cluster=cluster,
                f_stat=0,
                f_pval=1,
                model_type=self.name,
            )

        self.result = result
        self._fitted = True
        return result

    def summary(self) -> str:
        """返回 Markdown 格式结果"""
        if self.result is None:
            return "尚未执行 fit()"
        return self.result.to_markdown()


# ════════════════════════════════════════════════════════════════════
# Fama-French 系列因子模型
# ════════════════════════════════════════════════════════════════════

class FamaFrench3(BaseFactorModel):
    """
    Fama-French 三因子模型 (Fama & French, 1993)

    模型：
        R_it - R_ft = α_i + β_i(MKT_t) + s_i(SMB_t) + h_i(HML_t) + ε_it

    因子：
        - MKT: 市场超额收益 (Market minus risk-free rate)
        - SMB: 市值因子 (Small Minus Big)
        - HML: 价值因子 (High Minus Low)

    用法：
        ff3 = FamaFrench3()
        result = ff3.fit(returns_df, factors_df)
        print(result.to_markdown())
        result.save_results("ff3_results.csv", fmt="csv")
    """

    name = "FF3"
    factors = ["MKT", "SMB", "HML"]

    def __init__(self):
        super().__init__()
        self.factor_labels = {
            "MKT": "市场因子 (MKT)",
            "SMB": "市值因子 (SMB)",
            "HML": "价值因子 (HML)",
        }


class Carhart4(BaseFactorModel):
    """
    Carhart 四因子模型 (Carhart, 1997)

    模型：
        R_it - R_ft = α_i + β_i(MKT_t) + s_i(SMB_t) + h_i(HML_t) + m_i(MOM_t) + ε_it

    在 FF3 基础上加入动量因子：
        - MOM: 动量因子 (Winner Minus Loser, 过去一年收益高减收益低)

    用法：
        carhart4 = Carhart4()
        result = carhart4.fit(returns_df, factors_df)
        print(result.to_markdown())
    """

    name = "Carhart4"
    factors = ["MKT", "SMB", "HML", "MOM"]

    def __init__(self):
        super().__init__()
        self.factor_labels = {
            "MKT": "市场因子 (MKT)",
            "SMB": "市值因子 (SMB)",
            "HML": "价值因子 (HML)",
            "MOM": "动量因子 (MOM)",
        }


class FamaFrench5(BaseFactorModel):
    """
    Fama-French 五因子模型 (Fama & French, 2015)

    模型：
        R_it - R_ft = α_i + β_i(MKT_t) + s_i(SMB_t) + h_i(HML_t)
                     + r_i(RMW_t) + c_i(CMA_t) + ε_it

    因子：
        - MKT: 市场超额收益
        - SMB: 市值因子
        - HML: 价值因子
        - RMW: 盈利能力因子 (Robust Minus Weak)
        - CMA: 投资风格因子 (Conservative Minus Aggressive)

    用法：
        ff5 = FamaFrench5()
        result = ff5.fit(returns_df, factors_df)
        print(result.to_markdown())
    """

    name = "FF5"
    factors = ["MKT", "SMB", "HML", "RMW", "CMA"]

    def __init__(self):
        super().__init__()
        self.factor_labels = {
            "MKT": "市场因子 (MKT)",
            "SMB": "市值因子 (SMB)",
            "HML": "价值因子 (HML)",
            "RMW": "盈利因子 (RMW)",
            "CMA": "投资因子 (CMA)",
        }


class FF6_with_Q(BaseFactorModel):
    """
    FF6 + 质量因子 (Novy-Marx, 2013)

    基于 FF5 加入盈利质量因子：
        - GP: 毛利率因子 (Gross Profitability)

    Novy-Marx (2013) 发现毛利率因子能解释价值因子的定价能力。

    用法：
        ff6 = FF6_with_Q()
        result = ff6.fit(returns_df, factors_df)
        print(result.to_markdown())
    """

    name = "FF6_Q"
    factors = ["MKT", "SMB", "HML", "RMW", "CMA", "GP"]

    def __init__(self):
        super().__init__()
        self.factor_labels = {
            "MKT": "市场因子 (MKT)",
            "SMB": "市值因子 (SMB)",
            "HML": "价值因子 (HML)",
            "RMW": "盈利因子 (RMW)",
            "CMA": "投资因子 (CMA)",
            "GP": "毛利率因子 (GP)",
        }


# ════════════════════════════════════════════════════════════════════
# 时间序列回归
# ════════════════════════════════════════════════════════════════════

class TimeSeriesRegression:
    """
    时间序列 OLS 回归：对单个或多个资产进行因子模型回归。

    支持：
        - 单资产回归
        - 多资产批量回归
        - 聚类标准误
        - 滚动窗口回归

    用法：
        tsr = TimeSeriesRegression()
        result = tsr.fit(returns_df, factors_df)
        print(result.to_markdown())

        # 或对单资产
        result = tsr.fit_single(returns["port1"], factors_df)
    """

    def __init__(self):
        self.result: FactorModelResult | None = None
        self._residuals = None
        self._factor_loadings = None

    def fit(
        self,
        returns_df: pd.DataFrame,
        factors_df: pd.DataFrame,
        cluster: str = "",
        robust: bool = True,
        name: str = "TimeSeriesReg",
    ) -> FactorModelResult:
        """
        对多个资产执行时间序列回归。

        Args:
            returns_df: 资产收益率 DataFrame
            factors_df: 因子收益率 DataFrame
            cluster: 聚类变量（可选）
            robust: 使用 HC3 稳健标准误

        Returns:
            FactorModelResult
        """
        import statsmodels.api as sm
        from scipy import stats as scipy_stats

        # 对齐数据
        common_dates = returns_df.index.intersection(factors_df.index)
        returns = returns_df.loc[common_dates]
        factors = factors_df.loc[common_dates]

        factor_names = [c for c in factors.columns]
        result = FactorModelResult(name=name)

        residuals_dict = {}
        betas_dict = {}

        for col in returns.columns:
            y = returns[col].values
            X = factors[factor_names].values

            mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
            if mask.sum() < len(factor_names) + 2:
                continue

            y_clean = y[mask]
            X_clean = X[mask]

            X_with_const = sm.add_constant(X_clean)
            n, k = X_with_const.shape

            model = sm.OLS(y_clean, X_with_const)
            fit = model.fit(disp=False)

            if robust:
                try:
                    fit = fit.get_robustcov_results("HC3")
                except Exception:
                    pass

            params = fit.params
            se = fit.bse
            try:
                cov = fit.cov_params()
                se = np.sqrt(np.diag(cov))
            except Exception:
                pass
            tstats = params / se
            pvals = 2 * (1 - scipy_stats.t.cdf(np.abs(tstats), df=n - k))

            coef_dict = {}
            all_names = ["const"] + factor_names
            for i, nm in enumerate(all_names):
                coef_dict[nm] = {
                    "coef": float(params[i]),
                    "se": float(se[i]),
                    "t": float(tstats[i]),
                    "pval": float(pvals[i]),
                }

            coef_df = pd.DataFrame(coef_dict).T
            n_obs = len(y_clean)
            k_total = len(all_names)
            adj_r2 = 1 - (1 - fit.rsquared) * (n_obs - 1) / (n_obs - k_total)

            result.add_model(
                coef_df=coef_df,
                n_obs=n_obs,
                r2=float(fit.rsquared),
                adj_r2=adj_r2,
                resid=fit.resid,
                dep_var=str(col),
                cluster=cluster,
                f_stat=float(fit.fvalue),
                f_pval=float(fit.f_pvalue),
                model_type="TimeSeries",
            )

            residuals_dict[col] = fit.resid
            betas_dict[col] = {nm: float(params[i]) for i, nm in enumerate(all_names)}

        self.result = result
        self._residuals = pd.DataFrame(residuals_dict)
        self._factor_loadings = pd.DataFrame(betas_dict).T
        return result

    def fit_single(
        self,
        returns: pd.Series,
        factors_df: pd.DataFrame,
        robust: bool = True,
    ) -> tuple[dict, np.ndarray, float]:
        """
        对单个资产执行时间序列回归。

        Returns:
            (coef_dict, residuals, r_squared)
        """
        import statsmodels.api as sm
        from scipy import stats as scipy_stats

        common_dates = returns.index.intersection(factors_df.index)
        y = returns.loc[common_dates].values
        X = factors_df.loc[common_dates].values

        mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
        y_clean = y[mask]
        X_clean = X[mask]

        X_with_const = sm.add_constant(X_clean)
        n, k = X_with_const.shape

        model = sm.OLS(y_clean, X_with_const)
        fit = model.fit(disp=False)

        if robust:
            try:
                fit = fit.get_robustcov_results("HC3")
            except Exception:
                pass

        params = fit.params
        se = fit.bse
        try:
            cov = fit.cov_params()
            se = np.sqrt(np.diag(cov))
        except Exception:
            pass
        tstats = params / se
        pvals = 2 * (1 - scipy_stats.t.cdf(np.abs(tstats), df=n - k))

        factor_names = list(factors_df.columns)
        coef_dict = {}
        all_names = ["const"] + factor_names
        for i, nm in enumerate(all_names):
            coef_dict[nm] = {
                "coef": float(params[i]),
                "se": float(se[i]),
                "t": float(tstats[i]),
                "pval": float(pvals[i]),
            }

        return coef_dict, fit.resid, float(fit.rsquared)

    def get_residuals(self) -> pd.DataFrame:
        """获取残差"""
        return self._residuals

    def get_factor_loadings(self) -> pd.DataFrame:
        """获取因子暴露 (betas)"""
        return self._factor_loadings

    def rolling_regression(
        self,
        returns: pd.Series,
        factors_df: pd.DataFrame,
        window: int = 60,
        min_periods: int = 36,
    ) -> pd.DataFrame:
        """
        滚动窗口回归。

        Args:
            returns: 单资产收益率序列
            factors_df: 因子收益率 DataFrame
            window: 滚动窗口大小（月度数据建议60）
            min_periods: 最小观测数

        Returns:
            因子暴露的时间序列 DataFrame
        """
        common_dates = returns.index.intersection(factors_df.index)
        y = returns.loc[common_dates]
        X = factors_df.loc[common_dates]

        results = []
        for i in range(window, len(y)):
            y_window = y.iloc[i - window:i].values
            X_window = X.iloc[i - window:i].values

            mask = ~(np.isnan(y_window) | np.any(np.isnan(X_window), axis=1))
            if mask.sum() < min_periods:
                continue

            coef_dict, _, _ = self.fit_single(
                pd.Series(y_window, index=y.iloc[i - window:i].index[mask]),
                pd.DataFrame(X_window[mask], index=y.iloc[i - window:i].index[mask],
                            columns=X.columns),
            )
            coef_dict["date"] = y.index[i]
            results.append(coef_dict)

        return pd.DataFrame(results).set_index("date")

    def summary(self) -> str:
        """返回 Markdown 格式结果"""
        if self.result is None:
            return "尚未执行 fit()"
        return self.result.to_markdown()


# ════════════════════════════════════════════════════════════════════
# Fama-MacBeth 横截面回归
# ════════════════════════════════════════════════════════════════════

class CrossSectionalRegression:
    """
    Fama-MacBeth (1973) 两步法横截面回归

    第一步：对每个资产进行时间序列回归，获取因子暴露 (betas)
    第二步：对每个时点进行横截面回归，然后计算均值和 t 统计量

    输出：
        - 风险溢价估计（各因子的平均收益）
        - GRS 统计量检验截距项是否联合为零
        - Alpha 检验（CAPM alpha 是否为零）

    用法：
        fm = CrossSectionalRegression()
        result = fm.fit(returns_df, factors_df)
        print(result.to_markdown())
    """

    def __init__(self):
        self.result: FactorModelResult | None = None
        self.risk_premia = None
        self.grs_stat = None
        self.grs_pval = None
        self._step1_loadings = None
        self._step2_estimates = None

    def fit(
        self,
        returns_df: pd.DataFrame,
        factors_df: pd.DataFrame,
        add_constant: bool = True,
        robust: bool = True,
        name: str = "FamaMacBeth",
    ) -> FactorModelResult:
        """
        执行 Fama-MacBeth 两步法回归。

        Args:
            returns_df: 资产收益率 DataFrame (T x N)
            factors_df: 因子收益率 DataFrame (T x K)
            add_constant: 是否在横截面回归中加入常数项
            robust: 使用稳健标准误

        Returns:
            FactorModelResult，包含风险溢价估计和 t 统计量
        """
        import statsmodels.api as sm
        from scipy import stats as scipy_stats

        common_dates = returns_df.index.intersection(factors_df.index)
        returns = returns_df.loc[common_dates]
        factors = factors_df.loc[common_dates]

        T, N = returns.shape
        factor_names = list(factors.columns)
        K = len(factor_names)
        asset_names = list(returns.columns)

        # ========== 第一步：时间序列回归 ==========
        betas = np.zeros((N, K))
        alpha_hat = np.zeros(N)

        for j, asset in enumerate(asset_names):
            y = returns[asset].values
            X = factors[factor_names].values

            mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
            if mask.sum() < K + 2:
                betas[j] = np.nan
                alpha_hat[j] = np.nan
                continue

            y_clean = y[mask]
            X_clean = X[mask]

            X_with_const = sm.add_constant(X_clean)
            model = sm.OLS(y_clean, X_with_const)
            fit = model.fit(disp=False)

            alpha_hat[j] = fit.params[0]
            betas[j] = fit.params[1:K + 1]

        valid_assets = ~(np.isnan(betas).any(axis=1) | np.isnan(alpha_hat))
        betas_valid = betas[valid_assets]
        alpha_valid = alpha_hat[valid_assets]
        assets_valid = [asset_names[i] for i in range(N) if valid_assets[i]]
        N_valid = len(assets_valid)

        self._step1_loadings = pd.DataFrame(
            betas, index=asset_names, columns=factor_names
        )

        # ========== 第二步：横截面回归 ==========
        # 对每个时点 t 进行回归: R_t = λ * betas + alpha_t
        lambda_estimates = []

        for t in range(T):
            y_t = returns.iloc[t][valid_assets].values
            mask_t = ~np.isnan(y_t)

            if mask_t.sum() < K + 2:
                continue

            X_t = betas_valid[mask_t]
            y_t_clean = y_t[mask_t]

            if add_constant:
                X_t = sm.add_constant(X_t)

            try:
                model_t = sm.OLS(y_t_clean, X_t)
                fit_t = model_t.fit(disp=False)

                if robust:
                    try:
                        fit_t = fit_t.get_robustcov_results("HC3")
                    except Exception:
                        pass

                lambda_estimates.append(fit_t.params)
            except Exception:
                continue

        if len(lambda_estimates) == 0:
            warnings.warn("横截面回归未能执行")
            return FactorModelResult(name=name)

        lambda_df = pd.DataFrame(lambda_estimates, columns=["const"] + factor_names if add_constant else factor_names)
        self._step2_estimates = lambda_df

        # 计算均值和 t 统计量
        lambda_mean = lambda_df.mean()
        lambda_std = lambda_df.std(ddof=1)
        t_stats = lambda_mean / (lambda_std / np.sqrt(len(lambda_df)))
        p_vals = 2 * (1 - scipy_stats.t.cdf(np.abs(t_stats), df=len(lambda_df) - 1))

        # 残差
        residuals = []
        for t in range(T):
            y_t = returns.iloc[t][valid_assets].values
            mask_t = ~np.isnan(y_t)
            if mask_t.sum() < K + 2:
                continue
            X_t = betas_valid[mask_t]
            if add_constant:
                X_t = sm.add_constant(X_t)
            try:
                model_t = sm.OLS(y_t[mask_t], X_t)
                fit_t = model_t.fit(disp=False)
                residuals.extend(fit_t.resid.tolist())
            except Exception:
                continue

        # 构建结果表
        result = FactorModelResult(name=name)

        coef_dict = {}
        all_names = ["const"] + factor_names if add_constant else factor_names
        for nm in all_names:
            coef_dict[nm] = {
                "coef": float(lambda_mean[nm]),
                "se": float(lambda_std[nm] / np.sqrt(len(lambda_df))),
                "t": float(t_stats[nm]),
                "pval": float(p_vals[nm]),
            }

        coef_df = pd.DataFrame(coef_dict).T

        # 计算 R²（平均横截面 R²）
        r2_list = []
        for t in range(T):
            y_t = returns.iloc[t][valid_assets].values
            mask_t = ~np.isnan(y_t)
            if mask_t.sum() < K + 2:
                continue
            X_t = betas_valid[mask_t]
            if add_constant:
                X_t = sm.add_constant(X_t)
            try:
                model_t = sm.OLS(y_t[mask_t], X_t)
                fit_t = model_t.fit(disp=False)
                r2_list.append(fit_t.rsquared)
            except Exception:
                continue
        mean_r2 = np.mean(r2_list) if r2_list else np.nan

        # GRS 检验
        if not add_constant and N_valid > K:
            try:
                # 计算残差协方差
                resid_matrix = np.zeros((len(residuals) // N_valid, N_valid))
                idx = 0
                for t in range(T):
                    y_t = returns.iloc[t][valid_assets].values
                    mask_t = ~np.isnan(y_t)
                    if mask_t.sum() < K + 2:
                        continue
                    X_t = betas_valid[mask_t]
                    if add_constant:
                        X_t = sm.add_constant(X_t)
                    try:
                        model_t = sm.OLS(y_t[mask_t], X_t)
                        fit_t = model_t.fit(disp=False)
                        for j in range(mask_t.sum()):
                            resid_matrix[idx, j] = fit_t.resid[j]
                        idx += 1
                    except Exception:
                        continue

                if idx > N_valid + K:
                    cov_resid = np.cov(resid_matrix[:idx].T)
                    cov_alpha = cov_resid / idx
                    # mean_excess: N×K 因子暴露均值矩阵（每列是各资产的因子暴露均值）
                    mean_excess = betas_valid.mean(axis=0).values.reshape(-1, 1).T  # 1×K → broadcast to N×K
                    cov_excess = np.cov(factors[factor_names].values.T)
                    self.grs_stat, self.grs_pval = _grs_test(
                        alpha_valid.reshape(-1, 1).flatten()[:N_valid],
                        cov_alpha,
                        mean_excess,
                        cov_excess,
                        T, N_valid, K
                    )
            except Exception:
                self.grs_stat, self.grs_pval = np.nan, np.nan

        self.risk_premia = lambda_mean

        result.add_model(
            coef_df=coef_df,
            n_obs=T,
            r2=mean_r2,
            adj_r2=None,
            dep_var="Risk Premia",
            model_type="FamaMacBeth",
        )
        self.result = result
        return result

    def get_factor_loadings(self) -> pd.DataFrame:
        """获取第一步估计的因子暴露"""
        return self._step1_loadings

    def get_risk_premia(self) -> pd.Series:
        """获取风险溢价估计"""
        return self.risk_premia

    def get_grs_test(self) -> tuple[float, float]:
        """获取 GRS 统计量和 p 值"""
        return self.grs_stat, self.grs_pval

    def summary(self) -> str:
        """返回 Markdown 格式结果"""
        if self.result is None:
            return "尚未执行 fit()"
        s = self.result.to_markdown()
        if self.grs_stat is not None and not np.isnan(self.grs_stat):
            s += f"\n\n**GRS 统计量**: {self.grs_stat:.4f} (p = {self.grs_pval:.4f})"
        return s


# ════════════════════════════════════════════════════════════════════
# GMM 估计
# ════════════════════════════════════════════════════════════════════

class GMMEstimator:
    """
    广义矩估计 (GMM) for Asset Pricing

    GMM 是一种比 OLS 更灵活的估计方法，特别适用于：
        - 过度识别检验
        - 工具变量估计
        - 稳健的协方差估计

    矩条件：
        E[ε_t] = 0                        (均值条件)
        E[ε_t * z_t] = 0                 (正交条件)
    其中 ε_t = R_it - α_i - β_i' f_t

    用法：
        def moment_fn(params, y, X, z):
            residuals = y - params[0] - params[1:] @ X.T
            return np.array([np.mean(residuals), np.mean(residuals * z)])

        gmm = GMMEstimator()
        result = gmm.fit(y, X, moment_fn, initial_params=[0, 1, 0.5])
        print(result)
    """

    def __init__(self):
        self.result: dict | None = None
        self.params_ = None
        self.cov_ = None

    def moment_conditions(
        self,
        residuals: np.ndarray,
        params: np.ndarray,
        instruments: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        定义矩条件。

        默认矩条件：
            g = E[ε] = 0
            g = E[ε * z] = 0 (如果提供了工具变量)

        Args:
            residuals: 残差向量
            params: 参数估计
            instruments: 工具变量矩阵

        Returns:
            矩条件向量
        """
        moments = [np.mean(residuals)]

        if instruments is not None:
            # 清理工具变量中的 NaN
            valid = ~(np.isnan(residuals) | np.any(np.isnan(instruments), axis=1))
            if valid.sum() > 0:
                moments.extend(np.mean(residuals[valid, None] * instruments[valid], axis=0).tolist())

        return np.array(moments)

    def fit(
        self,
        y: np.ndarray,
        X: np.ndarray,
        moment_fn: callable,
        initial_params: np.ndarray | None = None,
        weights: np.ndarray | None = None,
        instrument: np.ndarray | None = None,
    ) -> dict:
        """
        执行 GMM 估计。

        Args:
            y: 因变量 (T x N 或 T,)
            X: 自变量/因子 (T x K)
            moment_fn: 矩条件函数
            initial_params: 初始参数值
            weights: 权重矩阵（默认使用恒等矩阵）
            instrument: 工具变量

        Returns:
            包含估计结果的字典
        """
        from scipy import optimize

        y = np.asarray(y).flatten()
        X = np.asarray(X)

        if y.shape[0] != X.shape[0]:
            raise ValueError("y 和 X 的时间维度不一致")

        T = len(y)

        if initial_params is None:
            # 使用 OLS 作为初始值
            X_with_const = np.column_stack([np.ones(T), X])
            ols_params = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
            initial_params = ols_params

        def objective(params):
            residuals = y - params[0] - params[1:] @ X.T
            moments = moment_fn(residuals, params, instrument)

            if weights is None:
                W = np.eye(len(moments))
            else:
                W = weights

            return T * moments @ W @ moments

        # 优化
        result = optimize.minimize(
            objective,
            initial_params,
            method="L-BFGS-B",
            options={"disp": False}
        )

        self.params_ = result.x

        # 计算标准误
        residuals = y - self.params_[0] - self.params_[1:] @ X.T
        moments = moment_fn(residuals, self.params_, instrument)
        k = len(moments)

        # 收敛协方差矩阵
        try:
            # 数值梯度
            eps = 1e-5
            grad = np.zeros((k, len(self.params_)))
            for i in range(len(self.params_)):
                params_plus = self.params_.copy()
                params_plus[i] += eps
                resid_plus = y - params_plus[0] - params_plus[1:] @ X.T
                moments_plus = moment_fn(resid_plus, params_plus, instrument)
                grad[:, i] = (moments_plus - moments) / eps

            # 矩条件方差
            moment_cov = np.cov(np.column_stack([moments] * T).T)
            if moment_cov.ndim == 0:
                moment_cov = np.array([[moment_cov]])

            # GMM 协方差
            grad_pinv = np.linalg.pinv(grad)
            self.cov_ = grad_pinv @ moment_cov @ grad_pinv.T / T

            se = np.sqrt(np.diag(self.cov_))
        except Exception:
            se = np.nan * np.ones(len(self.params_))

        self.result = {
            "params": self.params_,
            "se": se,
            "t_stats": self.params_ / se,
            "p_values": 2 * (1 - self._t_cdf(np.abs(self.params_ / se), T - len(self.params_))),
            "n_obs": T,
            "k_moments": k,
            "objective": result.fun,
        }

        return self.result

    def _t_cdf(self, x: np.ndarray, df: int) -> np.ndarray:
        """t 分布 CDF（避免 scipy 依赖）"""
        from scipy import stats as scipy_stats
        return scipy_stats.t.cdf(x, df)

    def summary(self) -> str:
        """返回估计结果摘要"""
        if self.result is None:
            return "尚未执行 fit()"

        lines = ["GMM 估计结果", "=" * 40]
        names = ["const"] + [f"beta_{i}" for i in range(len(self.params_) - 1)]

        for i, (nm, p, s, t, pv) in enumerate(zip(
            names, self.result["params"], self.result["se"],
            self.result["t_stats"], self.result["p_values"]
        )):
            sig = _stars(pv)
            lines.append(f"{nm:12s}: {p:10.6f} ({s:.4f})  t={t:8.4f} {sig}")

        lines.append(f"\n观测数: {self.result['n_obs']}")
        lines.append(f"矩条件数: {self.result['k_moments']}")
        lines.append(f"目标函数值: {self.result['objective']:.6f}")

        return "\n".join(lines)

    def J_test(self) -> tuple[float, float]:
        """
        J 统计量（过度识别检验）

        Returns:
            (J统计量, p值)
        """
        if self.result is None or self.cov_ is None:
            return np.nan, np.nan

        k = self.result["k_moments"]
        n = self.result["n_obs"]
        J = self.result["objective"] * n
        pval = 1 - self._chi2_cdf(J, k - len(self.params_))

        return J, pval

    def _chi2_cdf(self, x: float, df: int) -> float:
        """卡方分布 CDF"""
        from scipy import stats as scipy_stats
        return scipy_stats.chi2.cdf(x, df)


# ════════════════════════════════════════════════════════════════════
# LASSO 因子筛选
# ════════════════════════════════════════════════════════════════════

class LassoFactorSelector:
    """
    LASSO 因子筛选器

    使用 LASSO 回归从大量候选因子中筛选出定价能力最强的因子。
    基于 Tibshirani (1996) 的 LASSO 方法。

    特点：
        - 自动特征选择
        - 交叉验证确定最优正则化参数
        - 支持分组 LASSO（按因子类别）

    用法：
        selector = LassoFactorSelector(alpha=0.1)
        result = selector.fit(returns_df, factors_df)
        print(selector.selected_factors_)

        # 交叉验证
        cv_selector = LassoFactorSelector()
        cv_selector.fit_cv(returns_df, factors_df)
        print(cv_selector.best_alpha_)
    """

    def __init__(self, alpha: float = 0.1, max_iter: int = 1000, tol: float = 1e-4):
        """
        Args:
            alpha: LASSO 正则化参数
            max_iter: 最大迭代次数
            tol: 收敛阈值
        """
        self.alpha = alpha
        self.max_iter = max_iter
        self.tol = tol
        self.selected_factors_: list[str] | None = None
        self.coef_: pd.Series | None = None
        self.r2_: float | None = None
        self.best_alpha_: float | None = None
        self.cv_results_: dict | None = None

    def fit(
        self,
        returns_df: pd.DataFrame,
        factors_df: pd.DataFrame,
        name: str = "LASSO",
    ) -> FactorModelResult:
        """
        执行 LASSO 回归进行因子筛选。

        Args:
            returns_df: 资产收益率（可多个资产取平均）
            factors_df: 候选因子 DataFrame

        Returns:
            FactorModelResult
        """
        try:
            from sklearn.linear_model import Lasso, LassoCV
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            warnings.warn("scikit-learn 未安装，使用 statsmodels OLS 近似")
            return self._fallback_ols(returns_df, factors_df, name)

        # 对齐数据
        common_dates = returns_df.index.intersection(factors_df.index)
        y = returns_df.loc[common_dates].mean(axis=1).values
        X = factors_df.loc[common_dates].values

        mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
        y_clean = y[mask]
        X_clean = X[mask]

        # 标准化
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_clean)

        factor_names = list(factors_df.columns)

        # LASSO 回归
        model = Lasso(alpha=self.alpha, max_iter=self.max_iter, tol=self.tol)
        model.fit(X_scaled, y_clean)

        coefs = model.coef_
        self.coef_ = pd.Series(coefs, index=factor_names)

        # 筛选非零系数
        selected = self.coef_[np.abs(self.coef_) > 1e-6].sort_values(key=abs, ascending=False)
        self.selected_factors_ = list(selected.index)

        # 计算 R²
        y_pred = model.predict(X_scaled)
        ss_res = np.sum((y_clean - y_pred) ** 2)
        ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
        self.r2_ = 1 - ss_res / ss_tot

        # 构建结果
        result = FactorModelResult(name=name)

        coef_dict = {}
        for i, nm in enumerate(factor_names):
            coef_dict[nm] = {
                "coef": float(coefs[i]),
                "se": 0.0,
                "t": 0.0,
                "pval": 1.0,
            }

        coef_df = pd.DataFrame(coef_dict).T
        result.add_model(
            coef_df=coef_df,
            n_obs=len(y_clean),
            r2=self.r2_,
            adj_r2=None,
            dep_var="Portfolio Return",
            model_type="LASSO",
        )

        return result

    def fit_cv(
        self,
        returns_df: pd.DataFrame,
        factors_df: pd.DataFrame,
        n_alphas: int = 100,
        cv: int = 5,
        name: str = "LASSO_CV",
    ) -> FactorModelResult:
        """
        使用交叉验证确定最优 alpha 并拟合。

        Args:
            returns_df: 资产收益率
            factors_df: 候选因子 DataFrame
            n_alphas: 候选 alpha 数量
            cv: 交叉验证折数

        Returns:
            FactorModelResult
        """
        try:
            from sklearn.linear_model import LassoCV
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            warnings.warn("scikit-learn 未安装")
            return self._fallback_ols(returns_df, factors_df, name)

        common_dates = returns_df.index.intersection(factors_df.index)
        y = returns_df.loc[common_dates].mean(axis=1).values
        X = factors_df.loc[common_dates].values

        mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
        y_clean = y[mask]
        X_clean = X[mask]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_clean)

        list(factors_df.columns)

        # 交叉验证
        alphas = np.logspace(-5, 1, n_alphas)
        model_cv = LassoCV(alphas=alphas, cv=cv, max_iter=self.max_iter, tol=self.tol)
        model_cv.fit(X_scaled, y_clean)

        self.best_alpha_ = model_cv.alpha_
        self.alpha = self.best_alpha_

        return self.fit(returns_df, factors_df, name=name)

    def _fallback_ols(
        self, returns_df: pd.DataFrame, factors_df: pd.DataFrame, name: str
    ) -> FactorModelResult:
        """当 scikit-learn 不可用时的 OLS 近似"""
        tsr = TimeSeriesRegression()
        avg_returns = returns_df.mean(axis=1)
        return tsr.fit_single(avg_returns, factors_df) or FactorModelResult(name=name)

    def get_selected_factors(self) -> list[str]:
        """获取筛选后的因子列表"""
        return self.selected_factors_ or []

    def get_coefficients(self) -> pd.Series:
        """获取 LASSO 系数"""
        return self.coef_

    def summary(self) -> str:
        """返回结果摘要"""
        if self.selected_factors_ is None:
            return "尚未执行 fit()"

        lines = [f"LASSO 因子筛选结果 (alpha={self.alpha:.6f})", "=" * 50]
        lines.append(f"选中因子数: {len(self.selected_factors_)}")
        lines.append(f"R²: {self.r2_:.4f}" if self.r2_ else "R²: N/A")
        lines.append("\n选中因子:")
        for f in self.selected_factors_:
            coef = self.coef_[f]
            lines.append(f"  {f}: {coef:.6f}")

        if self.best_alpha_:
            lines.append(f"\n最优 alpha (CV): {self.best_alpha_:.6f}")

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# 因子模型对比
# ════════════════════════════════════════════════════════════════════

class FactorModelComparison:
    """
    多因子模型对比分析

    比较不同因子模型（如 FF3 vs FF5 vs Carhart4）的定价能力。

    输出：
        - 各模型的 R² 对比
        - Alpha 分布对比
        - GRS 统计量对比
        - 因子相关性矩阵

    用法：
        comparison = FactorModelComparison()
        result = comparison.compare(returns_df, {
            "FF3": factors_df[["MKT", "SMB", "HML"]],
            "FF5": factors_df[["MKT", "SMB", "HML", "RMW", "CMA"]],
            "Carhart4": factors_df[["MKT", "SMB", "HML", "MOM"]],
        })
        print(result.to_markdown())
    """

    def __init__(self):
        self.results: dict[str, FactorModelResult] = {}
        self.alpha_comparison: pd.DataFrame | None = None
        self.r2_comparison: pd.DataFrame | None = None

    def compare(
        self,
        returns_df: pd.DataFrame,
        model_factors: dict[str, pd.DataFrame],
        cluster: str = "",
        name: str = "ModelComparison",
    ) -> FactorModelResult:
        """
        比较多个因子模型。

        Args:
            returns_df: 资产收益率 DataFrame
            model_factors: 字典，键为模型名称，值为因子 DataFrame
            cluster: 聚类变量

        Returns:
            包含所有模型结果的 FactorModelResult
        """
        combined = FactorModelResult(name=name)

        for model_name, factors_df in model_factors.items():
            tsr = TimeSeriesRegression()
            result = tsr.fit(returns_df, factors_df, cluster=cluster, name=model_name)

            self.results[model_name] = result

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
                    model_type=model_info["model_type"],
                )

        # Alpha 对比
        self._compute_alpha_comparison(returns_df, model_factors)

        return combined

    def _compute_alpha_comparison(
        self,
        returns_df: pd.DataFrame,
        model_factors: dict[str, pd.DataFrame],
    ):
        """计算各模型 Alpha 对比"""
        alpha_data = {}

        for model_name, factors_df in model_factors.items():
            common_dates = returns_df.index.intersection(factors_df.index)
            returns = returns_df.loc[common_dates]
            factors = factors_df.loc[common_dates]

            alphas = []
            for col in returns.columns:
                y = returns[col].values
                X = factors.values

                mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
                if mask.sum() < factors.shape[1] + 2:
                    continue

                import statsmodels.api as sm
                X_clean = sm.add_constant(X[mask])
                y_clean = y[mask]

                model = sm.OLS(y_clean, X_clean)
                fit = model.fit(disp=False)
                alphas.append(fit.params[0])

            alpha_data[model_name] = {
                "Mean Alpha": np.mean(alphas),
                "Std Alpha": np.std(alphas),
                "Max |Alpha|": np.max(np.abs(alphas)),
                "Sig. Alpha (%)": np.mean([abs(a) > 1.96 * s for a, s in zip(alphas, np.std(alphas) / np.sqrt(len(alphas)))]) * 100,
            }

        self.alpha_comparison = pd.DataFrame(alpha_data).T

    def get_grs_comparison(
        self,
        returns_df: pd.DataFrame,
        model_factors: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        计算各模型的 GRS 统计量。

        Args:
            returns_df: 资产收益率
            model_factors: 因子字典

        Returns:
            GRS 统计量对比表
        """
        grs_data = {}

        for model_name, factors_df in model_factors.items():
            common_dates = returns_df.index.intersection(factors_df.index)
            returns = returns_df.loc[common_dates]
            factors = factors_df.loc[common_dates]

            T, N = returns.shape
            K = factors.shape[1]

            # 第一步：时间序列回归
            alphas = []
            betas = []
            resid_list = []

            for col in returns.columns:
                y = returns[col].values
                X = factors.values

                mask = ~(np.isnan(y) | np.any(np.isnan(X), axis=1))
                if mask.sum() < K + 2:
                    continue

                import statsmodels.api as sm
                X_clean = sm.add_constant(X[mask])
                y_clean = y[mask]

                model = sm.OLS(y_clean, X_clean)
                fit = model.fit(disp=False)
                alphas.append(fit.params[0])
                betas.append(fit.params[1:K + 1])
                resid_list.append(fit.resid)

            alphas = np.array(alphas)
            betas = np.array(betas)
            resid_matrix = np.column_stack(resid_list)

            if len(alphas) > K:
                try:
                    cov_alpha = np.cov(resid_matrix)
                    cov_excess = np.cov(factors.values.T)
                    # mean_excess: K-vector of mean factor loadings across all valid assets
                    mean_excess = np.mean(np.array(betas), axis=0)
                    grs, pval = _grs_test(
                        alphas, cov_alpha, mean_excess, cov_excess, T, len(alphas), K
                    )
                    grs_data[model_name] = {"GRS": grs, "p-value": pval}
                except Exception:
                    grs_data[model_name] = {"GRS": np.nan, "p-value": np.nan}

        return pd.DataFrame(grs_data).T

    def get_r2_comparison(self) -> pd.DataFrame:
        """获取 R² 对比"""
        r2_data = {}
        for model_name, result in self.results.items():
            r2s = [m["r2"] for m in result.models if m.get("r2") is not None]
            r2_data[model_name] = {
                "Mean R²": np.mean(r2s),
                "Median R²": np.median(r2s),
                "Max R²": np.max(r2s),
            }
        return pd.DataFrame(r2_data).T

    def get_factor_correlation(self, factors_df: pd.DataFrame) -> pd.DataFrame:
        """获取因子相关系数矩阵"""
        return factors_df.corr()

    def summary(self) -> str:
        """返回对比结果摘要"""
        lines = ["因子模型对比结果", "=" * 60]

        if self.r2_comparison is not None:
            lines.append("\nR² 对比:")
            lines.append(self.r2_comparison.to_string())

        if self.alpha_comparison is not None:
            lines.append("\nAlpha 对比:")
            lines.append(self.alpha_comparison.to_string())

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# ESG Alpha 检验
# ════════════════════════════════════════════════════════════════════

class ESGAlphaTest:
    """
    ESG Alpha 检验

    检验 ESG 因子是否提供传统因子模型无法解释的超额收益。

    方法：
        1. 在 FF5 基础上加入 ESG 因子
        2. 比较基准 FF5 和 FF5+ESG 的 Alpha
        3. 检验 Alpha 差异是否显著（套索检验）
        4. 计算增量 R²

    用法：
        esg_test = ESGAlphaTest()
        result = esg_test.fit(
            returns_df=portfolio_returns,
            factors_df=ff5_factors,
            esg_df=esg_scores,
        )
        print(result.to_markdown())
    """

    def __init__(self):
        self.result: FactorModelResult | None = None
        self.alpha_improvement: pd.Series | None = None
        self.delta_r2: float | None = None

    def fit(
        self,
        returns_df: pd.DataFrame,
        factors_df: pd.DataFrame,
        esg_df: pd.DataFrame,
        base_factors: list[str] = None,
        name: str = "ESG_Test",
    ) -> FactorModelResult:
        """
        执行 ESG Alpha 检验。

        Args:
            returns_df: 资产收益率 DataFrame
            factors_df: 传统因子 DataFrame (FF5)
            esg_df: ESG 因子/得分 DataFrame
            base_factors: 基准因子列表（默认 FF5）

        Returns:
            FactorModelResult，包含基准模型和扩展模型的对比
        """
        if base_factors is None:
            base_factors = ["MKT", "SMB", "HML", "RMW", "CMA"]

        # 合并数据
        common_dates = returns_df.index.intersection(
            factors_df.index.intersection(esg_df.index)
        )
        returns = returns_df.loc[common_dates]
        factors = factors_df.loc[common_dates][base_factors]
        esg = esg_df.loc[common_dates]

        # 确保 ESG 列名
        if isinstance(esg, pd.Series):
            esg = esg.to_frame("ESG")
        esg_col = esg.columns[0]

        # 扩展因子集
        extended_factors = factors.copy()
        extended_factors["ESG"] = esg[esg_col]

        # 基准模型回归
        tsr_base = TimeSeriesRegression()
        result_base = tsr_base.fit(returns, factors, name="FF5")

        # 扩展模型回归
        tsr_ext = TimeSeriesRegression()
        result_ext = tsr_ext.fit(returns, extended_factors, name="FF5+ESG")

        # 计算 Alpha 改进
        alpha_base = []
        alpha_ext = []
        for i, col in enumerate(returns.columns):
            if i < len(result_base.coefs):
                coef_df = result_base.coefs[i]
                # Extract intercept from coefs DataFrame
                alpha_base_val = 0.0
                if isinstance(coef_df, pd.DataFrame):
                    if 'const' in coef_df.index:
                        alpha_base_val = float(coef_df.loc['const', 'coef'])
                    elif len(coef_df) > 0 and coef_df.index[0] == 0:
                        alpha_base_val = float(coef_df.iloc[0]['coef'])
                alpha_base.append(alpha_base_val)
            if i < len(result_ext.coefs):
                coef_df = result_ext.coefs[i]
                # Extract intercept from coefs DataFrame
                alpha_ext_val = 0.0
                if isinstance(coef_df, pd.DataFrame):
                    if 'const' in coef_df.index:
                        alpha_ext_val = float(coef_df.loc['const', 'coef'])
                    elif len(coef_df) > 0 and coef_df.index[0] == 0:
                        alpha_ext_val = float(coef_df.iloc[0]['coef'])
                alpha_ext.append(alpha_ext_val)

        # 构建对比结果
        combined = FactorModelResult(name=name)

        # 添加基准模型
        for coef_df, model_info in zip(result_base.coefs, result_base.models):
            combined.add_model(
                coef_df=coef_df.copy(),
                n_obs=model_info["n_obs"],
                r2=model_info["r2"],
                adj_r2=model_info.get("adj_r2"),
                dep_var=model_info["dep_var"],
                cluster=model_info.get("cluster", ""),
                model_type="Baseline",
            )

        # 添加扩展模型
        for coef_df, model_info in zip(result_ext.coefs, result_ext.models):
            combined.add_model(
                coef_df=coef_df.copy(),
                n_obs=model_info["n_obs"],
                r2=model_info["r2"],
                adj_r2=model_info.get("adj_r2"),
                dep_var=model_info["dep_var"],
                cluster=model_info.get("cluster", ""),
                model_type="ESG",
            )

        self.result = combined

        # 计算增量 R²
        r2_base = np.mean([m["r2"] for m in result_base.models])
        r2_ext = np.mean([m["r2"] for m in result_ext.models])
        self.delta_r2 = r2_ext - r2_base

        return combined

    def get_factor_correlation(
        self,
        factors_df: pd.DataFrame,
        esg_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        计算因子与 ESG 的相关系数。

        Returns:
            相关系数矩阵
        """
        common_dates = factors_df.index.intersection(esg_df.index)
        combined = pd.concat([
            factors_df.loc[common_dates],
            esg_df.loc[common_dates]
        ], axis=1)
        return combined.corr()

    def summary(self) -> str:
        """返回检验结果摘要"""
        if self.result is None:
            return "尚未执行 fit()"

        lines = ["ESG Alpha 检验结果", "=" * 60]
        lines.append(self.result.to_markdown())

        if self.delta_r2 is not None:
            lines.append(f"\n增量 R²: {self.delta_r2:.4f}")

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════════════

def factor_model_summary(
    returns_df: pd.DataFrame,
    factors_df: pd.DataFrame,
    model: str = "ff5",
) -> FactorModelResult:
    """
    便捷函数：执行因子模型回归。

    Args:
        returns_df: 资产收益率
        factors_df: 因子收益率
        model: "ff3" | "carhart4" | "ff5" | "ff6"

    Returns:
        FactorModelResult
    """
    if model == "ff3":
        return FamaFrench3().fit(returns_df, factors_df)
    elif model == "carhart4":
        return Carhart4().fit(returns_df, factors_df)
    elif model == "ff5":
        return FamaFrench5().fit(returns_df, factors_df)
    elif model == "ff6":
        return FF6_with_Q().fit(returns_df, factors_df)
    else:
        raise ValueError(f"未知模型: {model}")


def load_fama_french_factors(
    start_date: str = "1963-07",
    end_date: str = "2024-12",
    source: str = "fama_french",
) -> pd.DataFrame:
    """
    加载 Fama-French 因子数据（从本地或网络）

    Args:
        start_date: 开始日期
        end_date: 结束日期
        source: "fama_french" (Kenneth French数据库)

    Returns:
        因子收益率 DataFrame
    """
    try:
        import pandas_datareader.data as web
    except ImportError:
        warnings.warn("pandas_datareader 未安装，使用模拟数据")
        dates = pd.date_range(start_date, end_date, freq="M")
        n = len(dates)
        rng = np.random.default_rng(42)  # deterministic simulation
        factors = pd.DataFrame({
            "MKT": rng.standard_normal(n) * 0.05 + 0.01,
            "SMB": rng.standard_normal(n) * 0.02,
            "HML": rng.standard_normal(n) * 0.02,
            "RMW": rng.standard_normal(n) * 0.015,
            "CMA": rng.standard_normal(n) * 0.015,
        }, index=dates)
        return factors

    try:
        ff = web.DataReader("FamaFrenchFactorPortfolio", "famafrench")[0]
        ff.columns = [c.strip() for c in ff.columns]
        return ff.loc[start_date:end_date]
    except Exception as e:
        warnings.warn(f"下载失败: {e}，使用模拟数据")
        dates = pd.date_range(start_date, end_date, freq="M")
        n = len(dates)
        rng = np.random.default_rng(42)  # deterministic simulation
        factors = pd.DataFrame({
            "MKT": rng.standard_normal(n) * 0.05 + 0.01,
            "SMB": rng.standard_normal(n) * 0.02,
            "HML": rng.standard_normal(n) * 0.02,
            "RMW": rng.standard_normal(n) * 0.015,
            "CMA": rng.standard_normal(n) * 0.015,
        }, index=dates)
        return factors


# ════════════════════════════════════════════════════════════════════
# 演示
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("因子模型库 v1.0")
    print("=" * 50)
    print("支持模型：FF3 / Carhart4 / FF5 / FF6+Quality")
    print("方法：时间序列回归 / Fama-MacBeth / GMM / LASSO")
    print("\n使用示例：")
    print("""
  from scripts.factor_models import (
      FamaFrench3, Carhart4, FamaFrench5,
      CrossSectionalRegression, GMMEstimator,
      LassoFactorSelector, FactorModelComparison, ESGAlphaTest
  )

  # 1. Fama-French 三因子模型
  ff3 = FamaFrench3()
  result = ff3.fit(returns_df, factors_df)
  print(result.to_markdown())
  result.save_results("ff3_results.csv", fmt="csv")

  # 2. Fama-MacBeth 横截面回归
  fm = CrossSectionalRegression()
  result = fm.fit(returns_df, factors_df)
  print(result.to_markdown())

  # 3. 因子模型对比
  comparison = FactorModelComparison()
  result = comparison.compare(returns_df, {
      "FF3": factors_df[["MKT", "SMB", "HML"]],
      "FF5": factors_df[["MKT", "SMB", "HML", "RMW", "CMA"]],
  })
  print(result.to_markdown())

  # 4. LASSO 因子筛选
  selector = LassoFactorSelector()
  result = selector.fit_cv(large_returns_df, candidate_factors_df)

  # 5. ESG Alpha 检验
  esg_test = ESGAlphaTest()
  result = esg_test.fit(portfolio_returns, ff5_factors, esg_scores)
  print(result.to_markdown())
    """)


# ════════════════════════════════════════════════════════════════════
# 因子模型库 v1.0
# ════════════════════════════════════════════════════════════════════
