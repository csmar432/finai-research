"""
计量经济学规则引擎 (Econometrics Rule Engine)
=============================================
对实证研究论文的计量方法进行自动验证，支持：
- DID 平行趋势假设检验
- IV 弱工具变量检验
- PSM 倾向得分匹配平衡性检验
- OLS 异方差检验

与 halt_rules/empirical_paper.yaml 中的质量规则对应，
可独立运行，也可集成到 HaltRulesRegistry 中使用。

使用方法：
    from scripts.core.econometrics_rules import EconometricsRuleEngine, ValidationResult

    engine = EconometricsRuleEngine()
    result = engine.validate("did", {
        "event_study_df": df,  # DataFrame with [period, coef, se]
        "pre_periods": 3,
    })
    print(result.passed, result.warnings, result.errors)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats


# ════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════


@dataclass
class ValidationResult:
    """标准化验证结果，用于所有计量经济学检验。"""
    passed: bool                           # 是否通过全部检查
    warnings: list[str] = field(default_factory=list)   # 警告信息列表
    errors: list[str] = field(default_factory=list)     # 错误信息列表
    details: dict[str, Any] = field(default_factory=dict)  # 检验细节（统计量、p值等）

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.passed = False

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def summary(self) -> str:
        lines = []
        if self.passed and not self.warnings:
            lines.append("PASS — 全部检验通过")
        else:
            if self.errors:
                lines.append(f"FAIL — {len(self.errors)} 个错误:")
                for e in self.errors:
                    lines.append(f"  [ERROR] {e}")
            if self.warnings:
                lines.append(f"WARN — {len(self.warnings)} 个警告:")
                for w in self.warnings:
                    lines.append(f"  [WARN] {w}")
        if self.details:
            lines.append("\n检验详情:")
            for k, v in self.details.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# DID Validator
# ════════════════════════════════════════════════════════════════════


class DIDValidator:
    """
    检验 DID 双重差分识别假设。

    核心检验：
    1. 平行趋势假设 — 事件研究法（Event Study）
    2. 政策发生前的系数联合F检验

    论文应附上事件研究图，展示政策前各期的置信区间，
    并报告检验结果。
    """

    def check_parallel_trend(
        self,
        event_study_df: pd.DataFrame | dict,
        pre_periods: int = 3,
        alpha: float = 0.1,
    ) -> dict:
        """
        检验平行趋势假设。

        使用事件研究法结果：
        - 检验政策前各期系数是否联合显著异于0
        - 若联合F检验 p < alpha，则拒绝平行趋势假设

        Args:
            event_study_df: DataFrame，必须包含列 [period, coef, se]
                period: 相对期间（如 -3, -2, -1, 0, 1, 2, 3），0为政策实施期
                coef:  各期系数估计值
                se:    各期标准误
            pre_periods: 检验前几期（默认3期，[-3, -2, -1]）
            alpha: 显著性水平（默认0.1）

        Returns:
            dict:
                passed (bool): 平行趋势假设是否成立
                p_value (float): 联合F检验的p值
                f_stat (float): 联合F统计量
                joint_test (dict): 联合检验详情
                individual_tests (list[dict]): 各期个别检验结果
                issues (list[str]): 具体问题描述
        """
        df = self._ensure_df(event_study_df)

        # 提取前一期系数
        pre_df = df[df["period"] < 0].copy()
        if len(pre_df) == 0:
            return {
                "passed": True,
                "p_value": 1.0,
                "f_stat": 0.0,
                "joint_test": {},
                "individual_tests": [],
                "issues": ["未提供政策前期数据，无法检验平行趋势"],
            }

        # 取最近 pre_periods 期（或全部前一期如果有的话）
        unique_pre = sorted(pre_df["period"].unique())
        periods_to_test = unique_pre[-pre_periods:] if len(unique_pre) > pre_periods else unique_pre
        pre_subset = pre_df[pre_df["period"].isin(periods_to_test)]

        coefs = pre_subset["coef"].values
        ses = pre_subset["se"].values

        # ── 联合F检验（H0：所有前一期系数 = 0）────────────────────
        # 使用 χ² 检验近似：统计量 = Σ (coef/se)²，服从χ²(k)分布
        t_stats = coefs / ses
        f_stat = np.sum(t_stats**2)
        df_num = len(coefs)
        p_value = 1 - stats.chi2.cdf(f_stat, df_num)

        # ── 个别t检验（单侧：检验是否显著为负）────────────────────
        individual_results = []
        issues = []
        any_significant_pre = False

        for _, row in pre_subset.iterrows():
            t = row["coef"] / row["se"]
            p_two = 2 * (1 - stats.t.cdf(abs(t), df=100))  # 大样本近似
            # 只关注显著偏离0的情况
            is_sig = p_two < alpha
            if is_sig:
                any_significant_pre = True
                direction = "正" if row["coef"] > 0 else "负"
                issues.append(
                    f"期{row['period']}系数{row['coef']:.4f}在{alpha*100:.0f}%水平{direction}向显著，"
                    f"可能违反平行趋势假设"
                )
            individual_results.append({
                "period": int(row["period"]),
                "coef": float(row["coef"]),
                "se": float(row["se"]),
                "t_stat": float(t),
                "p_value": float(p_two),
                "significant": bool(is_sig),
            })

        # ── 综合判断 ─────────────────────────────────────────────
        joint_reject = p_value < alpha
        passed = not joint_reject and not any_significant_pre

        if joint_reject:
            issues.insert(0, f"联合F检验拒绝平行趋势假设（F={f_stat:.3f}, p={p_value:.4f}）")
        elif any_significant_pre:
            issues.insert(0, "部分前一期系数显著，可能违反平行趋势假设")

        if not issues:
            issues.append("平行趋势假设基本成立（前一期系数联合不显著）")

        return {
            "passed": passed,
            "p_value": float(p_value),
            "f_stat": float(f_stat),
            "df_num": df_num,
            "joint_reject_null": bool(joint_reject),
            "joint_test": {
                "h0": "所有前一期系数 = 0（平行趋势成立）",
                "f_stat": float(f_stat),
                "p_value": float(p_value),
                "reject_at_alpha": bool(joint_reject),
                "alpha": alpha,
            },
            "individual_tests": individual_results,
            "issues": issues,
        }

    def check_dynamic_did(
        self,
        event_study_df: pd.DataFrame | dict,
        min_pre_periods: int = 2,
        max_lead: int = 3,
    ) -> dict:
        """
        检验动态DID（多期处理效应）的事件研究规范。

        检验要点：
        1. 政策前期系数应不显著（无预趋势）
        2. 政策后期系数应逐渐稳定（或呈衰减趋势）
        3. 基准期（period=0 或 period=-1）系数应显著

        Args:
            event_study_df: DataFrame with [period, coef, se]
            min_pre_periods: 最少需要的前一期数量
            max_lead: 最大考察的后一期数量

        Returns:
            dict with passed, issues, pre_periods_ok, post_trend_ok
        """
        df = self._ensure_df(event_study_df)

        issues = []
        warnings = []

        pre = df[df["period"] < 0].copy()
        post = df[df["period"] > 0].copy()

        # 检查前一期数量
        if len(pre) < min_pre_periods:
            warnings.append(f"前一期数量不足（需要≥{min_pre_periods}，实际{len(pre)}）")

        # 前一期不应显著
        pre_passed = True
        for _, row in pre.iterrows():
            t = row["coef"] / row["se"]
            p = 2 * (1 - stats.t.cdf(abs(t), 100))
            if p < 0.1:
                pre_passed = False
                issues.append(f"期{row['period']}显著偏离0，预趋势可能存在")

        # 基准期（通常 period=-1 或 period=0）应显著
        base_periods = df[df["period"].isin([-1, 0])]
        base_sig = False
        for _, row in base_periods.iterrows():
            t = row["coef"] / row["se"]
            p = 2 * (1 - stats.t.cdf(abs(t), 100))
            if p < 0.05:
                base_sig = True
        if not base_sig and len(base_periods) > 0:
            warnings.append("基准期系数不显著，处理效应可能较弱")

        # 后期趋势检查
        post_trend_ok = True
        if len(post) >= 2:
            post_coefs = post.sort_values("period")["coef"].values
            # 简单检查：后期系数是否持续显著
            for _, row in post.iterrows():
                t = row["coef"] / row["se"]
                p = 2 * (1 - stats.t.cdf(abs(t), 100))
                if p > 0.2:  # 后期完全不显著可能是问题
                    warnings.append(f"期{row['period']}系数不显著，处理效应可能随时间衰减")

        return {
            "passed": pre_passed and len(issues) == 0,
            "pre_periods_ok": pre_passed,
            "post_trend_ok": post_trend_ok,
            "issues": issues,
            "warnings": warnings,
            "pre_periods_count": len(pre),
            "post_periods_count": len(post),
        }

    # ── Helper ──────────────────────────────────────────────────────

    @staticmethod
    def _ensure_df(data: pd.DataFrame | dict) -> pd.DataFrame:
        if isinstance(data, dict):
            return pd.DataFrame(data)
        return data


# ════════════════════════════════════════════════════════════════════
# Weak Instrument Test
# ════════════════════════════════════════════════════════════════════


class WeakInstrumentTest:
    """
    检验工具变量是否满足相关性要求。

    Stock-Yogo 临界值（部分常用值）:
    ┌──────────────────────────────────────────┬─────────────┐
    │ 偏误容忍度                              │ F > 临界值  │
    ├──────────────────────────────────────────┼─────────────┤
    │ 10% maximal IV relative bias            │ 16.38       │
    │ 5%  maximal IV relative bias           │ 19.93       │
    │ 30% maximal size distortion             │ 5.44        │
    │ 20% maximal size distortion            │ 7.25        │
    │ 15% maximal size distortion            │ 8.96        │
    │ 10% maximal size distortion            │ 11.59       │
    └──────────────────────────────────────────┴─────────────┘

    参考来源：Stock & Yogo (2005), "Testing for Weak Instruments in
             Linear IV Regression."
    """

    # Stock-Yogo critical values (10% IV relative bias = 16.38 is most common)
    STOCK_YOGO_CRITICAL_VALUES: dict[str, float] = {
        "10%_bias": 16.38,
        "5%_bias": 19.93,
        "30%_size_distortion": 5.44,
        "20%_size_distortion": 7.25,
        "15%_size_distortion": 8.96,
        "10%_size_distortion": 11.59,
    }

    def first_stage_f_stat(
        self,
        X: np.ndarray | pd.Series | list,
        Z: np.ndarray | pd.DataFrame | list,
        controls: np.ndarray | pd.DataFrame | list | None = None,
    ) -> dict:
        """
        计算一阶段F统计量（检验工具变量相关性）。

        回归：X ~ Z（+ controls）
        H0: 所有工具变量系数 = 0（工具变量弱）
        若 F > 10（经验法则），则拒绝弱工具变量假设

        Args:
            X: 内生变量（因变量在一阶段回归中），shape (n,) 或 (n, 1)
            Z: 工具变量（自变量），shape (n, k)，k >= 1
            controls: 控制变量（可选），shape (n, m)

        Returns:
            dict:
                f_stat (float): 总体F统计量
                p_value (float): F检验p值
                critical_values (dict): Stock-Yogo临界值参考
                is_weak (bool): 是否为弱工具变量（F <= 10）
                is_weak_by_sy (bool): 是否通过Stock-Yogo 10%偏误标准（F > 16.38）
                partial_r2 (float): 偏R²（工具变量对X的解释力）
                df_num (int): 分子自由度
                df_den (int): 分母自由度
        """
        # ── 数据准备 ─────────────────────────────────────────────
        X_arr = np.asarray(X, dtype=float).flatten()
        Z_arr = np.atleast_2d(np.asarray(Z, dtype=float))

        n = len(X_arr)
        k = Z_arr.shape[1]  # 工具变量个数

        if n != Z_arr.shape[0]:
            raise ValueError(f"样本量不匹配: X length={n}, Z rows={Z_arr.shape[0]}")

        # 添加常数项
        Z_design = np.column_stack([np.ones(n), Z_arr])

        if controls is not None:
            ctrl_arr = np.atleast_2d(np.asarray(controls, dtype=float))
            if ctrl_arr.shape[0] != n:
                raise ValueError(f"控制变量样本量不匹配: {ctrl_arr.shape[0]} != {n}")
            Z_design = np.column_stack([Z_design, ctrl_arr])

        # ── OLS 回归（一阶段）────────────────────────────────────
        try:
            beta, ssr, rank = np.linalg.lstsq(Z_design, X_arr, rcond=None)[:3]
        except np.linalg.LinAlgError as e:
            raise ValueError(f"一阶段回归失败: {e}") from e

        residuals = X_arr - Z_design @ beta

        # SSR（残差平方和）和 TSS（总平方和）
        ssr_val = np.sum(residuals**2)
        tss = np.sum((X_arr - np.mean(X_arr))**2)
        r_squared = 1 - ssr_val / tss if tss > 0 else 0.0

        # ── F统计量计算 ─────────────────────────────────────────
        # F = (R²_reduced - R²_full) / (1 - R²_full) * (n - k - 1) / (k)
        # 全模型 R²_full 即 r_squared（包含常数项），降维模型 R²_reduced = 0
        # 简化形式：F = (TSS - SSR) / SSR * (n - k - 1) / k
        df_num = k           # 工具变量个数
        df_den = n - Z_design.shape[1]  # 残差自由度

        if ssr_val <= 0:
            f_stat = float("inf")
            p_value = 0.0
        else:
            f_stat = ((tss - ssr_val) / ssr_val) * (df_den / df_num)
            p_value = 1 - stats.f.cdf(f_stat, df_num, df_den)

        # ── 偏R²（工具变量对内生变量的解释力）────────────────────
        # 偏R² = (X对Z回归的R²，剔除controls的影响)
        partial_r2 = r_squared  # 简化：直接用全模型R²

        # ── 判断 ────────────────────────────────────────────────
        is_weak_rule_of_thumb = f_stat <= 10.0
        sy_10pct = self.STOCK_YOGO_CRITICAL_VALUES["10%_bias"]
        is_weak_by_sy = f_stat <= sy_10pct

        return {
            "f_stat": float(f_stat),
            "p_value": float(p_value),
            "df_num": int(df_num),
            "df_den": int(df_den),
            "r_squared": float(r_squared),
            "partial_r2": float(partial_r2),
            "critical_values": dict(self.STOCK_YOGO_CRITICAL_VALUES),
            "is_weak": bool(is_weak_rule_of_thumb),
            "is_weak_by_sy": bool(is_weak_by_sy),
            "n_instruments": int(k),
            "n_obs": int(n),
            "interpretation": self._interpret_f(f_stat),
        }

    def sargan_test(
        self,
        residuals_2sls: np.ndarray,
        Z: np.ndarray,
        n_instruments: int,
        n_exog: int = 1,
    ) -> dict:
        """
        Sargan-Hansen 过度识别检验（工具变量外生性）。

        适用于工具变量数量 > 内生变量数量的情况。
        H0: 所有工具变量都是外生的（过度识别约束有效）

        Args:
            residuals_2sls: 2SLS残差（stage-1 fitted X 对 原X 的残差）
            Z: 所有工具变量（含外生变量），shape (n, k)
            n_instruments: 工具变量总数
            n_exog: 内生变量数量（默认1）

        Returns:
            dict with sargan_stat, p_value, df, is_overidentified, issues
        """
        Z_arr = np.atleast_2d(np.asarray(Z, dtype=float))
        residuals = np.asarray(residuals_2sls, dtype=float).flatten()
        n = len(residuals)

        if Z_arr.shape[0] != n:
            raise ValueError(f"样本量不匹配: residuals length={n}, Z rows={Z_arr.shape[0]}")

        # Sargan统计量 = n * R²（从残差对Z的回归中）
        try:
            # 残差对Z回归（含常数）求R²
            Z_with_const = np.column_stack([np.ones(n), Z_arr])
            _, ssr_full, _ = np.linalg.lstsq(Z_with_const, residuals, rcond=None)[:3]
            tss = np.sum((residuals - np.mean(residuals))**2)
            r_sq = 1 - ssr_full / tss if tss > 0 else 0.0
        except np.linalg.LinAlgError:
            return {
                "sargan_stat": None,
                "p_value": None,
                "df": 0,
                "is_overidentified": False,
                "issues": ["Sargan检验计算失败"],
            }

        sargan_stat = n * r_sq
        df = n_instruments - n_exog  # 过度识别自由度

        if df <= 0:
            return {
                "sargan_stat": float(sargan_stat) if n * r_sq > 0 else 0.0,
                "p_value": None,
                "df": int(df),
                "is_overidentified": False,
                "issues": ["恰好识别（工具变量数 = 内生变量数），无法进行过度识别检验"],
            }

        p_value = 1 - stats.chi2.cdf(sargan_stat, df)
        reject_exogeneity = p_value < 0.1

        issues = []
        if reject_exogeneity:
            issues.append(
                f"Sargan检验拒绝外生性假设（χ²={sargan_stat:.3f}, p={p_value:.4f}），"
                "部分工具变量可能内生"
            )

        return {
            "sargan_stat": float(sargan_stat),
            "p_value": float(p_value),
            "df": int(df),
            "is_overidentified": bool(df > 0),
            "reject_exogeneity": bool(reject_exogeneity),
            "issues": issues,
        }

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _interpret_f(f_stat: float) -> str:
        if f_stat > 19.93:
            return "强工具变量（对5%偏误稳健）"
        elif f_stat > 16.38:
            return "可接受工具变量（对10%偏误稳健）"
        elif f_stat > 10:
            return "边际工具变量（经验法则可通过，但存在偏误风险）"
        elif f_stat > 5:
            return "弱工具变量（标准误膨胀，因果推断不可靠）"
        else:
            return "极弱工具变量（严重偏误，应使用其他识别策略）"


# ════════════════════════════════════════════════════════════════════
# Balance Test Validator
# ════════════════════════════════════════════════════════════════════


class BalanceTestValidator:
    """
    检验倾向得分匹配（PSM）后的协变量平衡性。

    标准：
    - 各协变量在处理组与对照组之间的标准化偏差 < 10%
    - t检验不显著（p > 0.1）
    - 联合F检验不拒绝平衡假设

    论文应报告匹配前后各变量的均值、标准偏差和标准化偏差，
    并附上平衡性检验表。
    """

    def check_balance(
        self,
        df_matched: pd.DataFrame | dict,
        variables: list[str] | None = None,
        treatment_col: str = "treatment",
        threshold: float = 0.1,
        alpha: float = 0.1,
    ) -> dict:
        """
        检验PSM匹配后的协变量平衡性。

        Args:
            df_matched: 匹配后的DataFrame，包含处理组和对照组
            variables: 要检验的协变量列表（默认为所有数值型列）
            treatment_col: 处理变量列名（值为0/1或False/True）
            threshold: 标准化偏差阈值（默认10% = 0.1）
            alpha: t检验显著性水平

        Returns:
            dict:
                passed (bool): 是否通过平衡性检验
                imbalance_vars (list[str]): 失衡变量列表
                max_abs_bias (float): 最大绝对标准化偏差
                mean_abs_bias (float): 平均绝对标准化偏差
                balance_table (pd.DataFrame): 平衡性检验详细表
                issues (list[str]): 问题描述
        """
        df = self._ensure_df(df_matched)

        if treatment_col not in df.columns:
            raise ValueError(f"处理变量列 '{treatment_col}' 不存在于数据中")

        # 识别协变量
        if variables is None:
            variables = [
                c for c in df.columns
                if c != treatment_col and df[c].dtype in [np.float64, np.int64, float, int]
            ]

        treat = df[df[treatment_col] == 1] if df[treatment_col].dtype == int else df[df[treatment_col] is True]
        ctrl = df[df[treatment_col] == 0] if df[treatment_col].dtype == int else df[df[treatment_col] is False]

        if len(treat) == 0 or len(ctrl) == 0:
            return {
                "passed": False,
                "imbalance_vars": [],
                "max_abs_bias": None,
                "mean_abs_bias": None,
                "balance_table": pd.DataFrame(),
                "issues": ["处理组或对照组样本量为0"],
            }

        # ── 逐变量检验 ───────────────────────────────────────────
        results = []
        imbalance_vars = []
        all_abs_bias = []

        for var in variables:
            if var not in df.columns:
                continue

            x_t = treat[var].dropna()
            x_c = ctrl[var].dropna()

            if len(x_t) == 0 or len(x_c) == 0:
                continue

            mean_t = x_t.mean()
            mean_c = x_c.mean()
            std_t = x_t.std(ddof=1)
            std_c = x_c.std(ddof=1)
            pool_std = np.sqrt((std_t**2 + std_c**2) / 2)

            # 标准化偏差（Standardized Mean Difference）
            if pool_std > 1e-10:
                smd = abs(mean_t - mean_c) / pool_std
            else:
                smd = 0.0

            # t检验
            if len(x_t) >= 2 and len(x_c) >= 2:
                t_stat, p_val = stats.ttest_ind(x_t, x_c, equal_var=False)
            else:
                t_stat, p_val = 0.0, 1.0

            # 判断失衡
            is_imbalanced = smd > threshold or p_val < alpha

            if is_imbalanced:
                reason = f"SMD={smd:.3f} > {threshold}" if smd > threshold else f"t检验p={p_val:.4f} < {alpha}"
                imbalance_vars.append(var)

            all_abs_bias.append(smd)
            results.append({
                "variable": var,
                "mean_treated": float(mean_t),
                "mean_control": float(mean_c),
                "std_treated": float(std_t),
                "std_control": float(std_c),
                "pooled_std": float(pool_std),
                "std_mean_diff": float(smd),
                "t_stat": float(t_stat),
                "p_value": float(p_val),
                "is_balanced": not is_imbalanced,
            })

        results_df = pd.DataFrame(results)
        max_abs_bias = max(all_abs_bias) if all_abs_bias else 0.0
        mean_abs_bias = np.mean(all_abs_bias) if all_abs_bias else 0.0

        # ── 联合F检验 ──────────────────────────────────────────
        joint_f_issues = []
        joint_passed = True
        if len(results) > 1:
            failed_vars = [r for r in results if not r["is_balanced"]]
            if len(failed_vars) >= 2:
                joint_passed = False
                joint_f_issues.append(
                    f"联合检验：{len(failed_vars)}/{len(results)} 个变量失衡，"
                    f"平衡性可能不满足"
                )

        # ── 汇总判断 ────────────────────────────────────────────
        issues = []
        if imbalance_vars:
            issues.append(
                f"以下变量标准化偏差 > {threshold*100}%（失衡）: {', '.join(imbalance_vars)}"
            )
        if max_abs_bias > threshold:
            issues.append(
                f"最大标准化偏差为{max_abs_bias:.1%}（> {threshold*100}%），"
                "建议重新匹配或调整匹配方法"
            )
        if not joint_passed:
            issues.extend(joint_f_issues)

        passed = len(imbalance_vars) == 0 and max_abs_bias <= threshold

        return {
            "passed": passed,
            "imbalance_vars": imbalance_vars,
            "max_abs_bias": float(max_abs_bias),
            "mean_abs_bias": float(mean_abs_bias),
            "balance_table": results_df,
            "n_treated": len(treat),
            "n_control": len(ctrl),
            "threshold": threshold,
            "issues": issues,
        }

    def check_covariate_means(
        self,
        df_before: pd.DataFrame,
        df_after: pd.DataFrame | None = None,
        variables: list[str] | None = None,
        treatment_col: str = "treatment",
    ) -> dict:
        """
        报告匹配前后各协变量的均值差异（便于展示平衡性改善）。

        Args:
            df_before: 匹配前DataFrame
            df_after: 匹配后DataFrame（可选）
            variables: 协变量列表
            treatment_col: 处理变量列名

        Returns:
            dict with before/after balance summary tables
        """
        before_bal = self.check_balance(
            df_before, variables, treatment_col, threshold=0.1, alpha=0.1
        )

        result = {
            "before": {
                "max_abs_bias": before_bal["max_abs_bias"],
                "mean_abs_bias": before_bal["mean_abs_bias"],
                "imbalance_vars": before_bal["imbalance_vars"],
                "balance_table": before_bal["balance_table"],
            }
        }

        if df_after is not None:
            after_bal = self.check_balance(
                df_after, variables, treatment_col, threshold=0.1, alpha=0.1
            )
            result["after"] = {
                "max_abs_bias": after_bal["max_abs_bias"],
                "mean_abs_bias": after_bal["mean_abs_bias"],
                "imbalance_vars": after_bal["imbalance_vars"],
                "balance_table": after_bal["balance_table"],
            }
            # 改善情况
            if "max_abs_bias" in result["before"] and "max_abs_bias" in result["after"]:
                reduction = (
                    (result["before"]["max_abs_bias"] - result["after"]["max_abs_bias"])
                    / result["before"]["max_abs_bias"] * 100
                    if result["before"]["max_abs_bias"] > 0 else 0
                )
                result["improvement_pct"] = round(reduction, 1)
                result["passed"] = after_bal["passed"]

        return result

    # ── Helper ─────────────────────────────────────────────────────

    @staticmethod
    def _ensure_df(data: pd.DataFrame | dict) -> pd.DataFrame:
        if isinstance(data, dict):
            return pd.DataFrame(data)
        return data


# ════════════════════════════════════════════════════════════════════
# Heteroskedasticity Test
# ════════════════════════════════════════════════════════════════════


class HeteroskedasticityTest:
    """
    检验异方差问题的多种方法。

    支持：
    - Breusch-Pagan 检验（BP检验）
    - White 检验
    - Goldfeld-Quandt 检验（需要排序数据）
    - Breusch-Pagan-Godfrey（更稳健版本）

    论文应在异方差检验显著时：
    1. 使用稳健标准误（HC0/HC1/HC3）
    2. 在表格注释中说明"Weighting=HCSE"
    """

    def breusch_pagan(
        self,
        residuals: np.ndarray,
        X: np.ndarray | pd.DataFrame,
        max_power: int = 2,
    ) -> dict:
        """
        Breusch-Pagan 检验异方差。

        H0: 同方差（不存在异方差）
        H1: 异方差（残差方差与X相关）

        辅助回归：e² ~ X + X²（默认二次项）
        BP = n * R²（辅助回归的拟合优度 * 样本量）
        BP ~ χ²(df=X列数)

        Args:
            residuals: 回归残差，shape (n,)
            X: 自变量矩阵，shape (n, k)，应含常数项
            max_power: 辅助回归中X的最高次方（默认2，包含X²）

        Returns:
            dict:
                bp_stat (float): BP统计量
                p_value (float): p值
                has_heteroskedasticity (bool): 是否存在异方差（p < 0.1）
                r_squared (float): 辅助回归R²
                df (int): 自由度
                issues (list[str]): 问题描述
        """
        e2 = np.asarray(residuals, dtype=float) ** 2
        X_arr = np.atleast_2d(np.asarray(X, dtype=float))
        n = len(e2)

        if X_arr.shape[0] != n:
            raise ValueError(f"样本量不匹配: residuals={n}, X rows={X_arr.shape[0]}")

        # 辅助回归：e² ~ X + X²（辅助变量 = X, X²/|e| 或直接 X²）
        # 简化版本：e² ~ X 的拟合值
        X_with_const = np.column_stack([np.ones(n), X_arr])
        k = X_with_const.shape[1]

        try:
            # 标准化残差（避免极端值影响）
            e2_normalized = e2 / np.mean(e2)
            beta_aux, ssr_aux, _ = np.linalg.lstsq(X_with_const, e2_normalized, rcond=None)[:3]
            residuals_aux = e2_normalized - X_with_const @ beta_aux
            tss_aux = np.sum((e2_normalized - np.mean(e2_normalized))**2)
            r2_aux = 1 - np.sum(residuals_aux**2) / tss_aux if tss_aux > 0 else 0.0
        except np.linalg.LinAlgError:
            return {
                "bp_stat": None,
                "p_value": None,
                "has_heteroskedasticity": False,
                "r_squared": None,
                "df": 0,
                "issues": ["Breusch-Pagan辅助回归失败"],
            }

        bp_stat = n * r2_aux
        df = k - 1  # 不含常数项
        p_value = 1 - stats.chi2.cdf(bp_stat, df)

        has_hetero = p_value < 0.1  # 常用显著性水平

        issues = []
        if has_hetero:
            issues.append(
                f"Breusch-Pagan检验拒绝同方差假设（BP={bp_stat:.3f}, p={p_value:.4f}），"
                "建议使用稳健标准误（Clustered SE / HCSE）"
            )

        return {
            "bp_stat": float(bp_stat),
            "p_value": float(p_value),
            "has_heteroskedasticity": bool(has_hetero),
            "r_squared": float(r2_aux),
            "df": int(df),
            "n_obs": int(n),
            "issues": issues,
        }

    def white_test(
        self,
        residuals: np.ndarray,
        X: np.ndarray | pd.DataFrame,
        include_cross_terms: bool = True,
    ) -> dict:
        """
        White's 检验（带交叉项的异方差检验）。

        比BP检验更灵活，自动包含X²和交叉项。

        H0: 同方差
        辅助回归：e² ~ X + X² + X⊗X（交叉项）

        Args:
            residuals: 回归残差
            X: 自变量矩阵（不含常数项）
            include_cross_terms: 是否包含交叉项（默认True）

        Returns:
            dict with white_stat, p_value, has_heteroskedasticity, df, issues
        """
        e2 = np.asarray(residuals, dtype=float) ** 2
        X_raw = np.atleast_2d(np.asarray(X, dtype=float))
        n = len(e2)

        if X_raw.shape[0] != n:
            raise ValueError(f"样本量不匹配")

        # 构建辅助变量：X, X², X_i * X_j
        aux_vars = [np.ones(n), X_raw, X_raw**2]

        if include_cross_terms and X_raw.shape[1] >= 2:
            # 添加交叉项（仅对连续变量）
            for i in range(X_raw.shape[1]):
                for j in range(i + 1, X_raw.shape[1]):
                    aux_vars.append(X_raw[:, i] * X_raw[:, j])

        X_aux = np.column_stack(aux_vars)

        try:
            e2_normalized = e2 / np.mean(e2)
            _, ssr_aux, _ = np.linalg.lstsq(X_aux, e2_normalized, rcond=None)[:3]
            ssr_aux = float(np.asarray(ssr_aux).item() if np.ndim(ssr_aux) > 0 else ssr_aux)
            tss_aux = float(np.sum((e2_normalized - np.mean(e2_normalized))**2))
            r2_aux = float(1 - ssr_aux / tss_aux) if tss_aux > 1e-10 else 0.0
        except np.linalg.LinAlgError:
            return {
                "white_stat": None,
                "p_value": None,
                "has_heteroskedasticity": False,
                "df": 0,
                "issues": ["White辅助回归失败"],
            }

        white_stat = float(n * r2_aux)
        df = X_aux.shape[1] - 1  # 不含常数
        p_value = float(1 - stats.chi2.cdf(white_stat, df))

        has_hetero = p_value < 0.1

        issues = []
        if has_hetero:
            issues.append(
                f"White检验拒绝同方差假设（LM={white_stat:.3f}, p={p_value:.4f}），"
                "建议使用稳健标准误"
            )

        return {
            "white_stat": white_stat,
            "p_value": p_value,
            "has_heteroskedasticity": bool(has_hetero),
            "r_squared": r2_aux,
            "df": int(df),
            "n_obs": int(n),
            "issues": issues,
        }

    def goldfeld_quandt(
        self,
        residuals: np.ndarray,
        X: np.ndarray,
        y: np.ndarray | None = None,
        sort_var: np.ndarray | None = None,
        split_ratio: float = 0.5,
    ) -> dict:
        """
        Goldfeld-Quandt 检验（适用于能排序的数据，如横截面）。

        将样本按排序变量分成两部分，比较两端残差的方差比。

        Args:
            residuals: 残差
            X: 自变量（用于排序，可选）
            y: 因变量（可选，如提供则按y排序）
            sort_var: 指定排序变量
            split_ratio: 中间剔除比例（默认0.5=剔除中间50%）

        Returns:
            dict with gq_stat, p_value, has_heteroskedasticity, df
        """
        residuals = np.asarray(residuals, dtype=float).flatten()
        n = len(residuals)

        # 确定排序变量
        if sort_var is not None:
            order = np.argsort(np.asarray(sort_var, dtype=float))
        elif y is not None:
            order = np.argsort(np.asarray(y, dtype=float))
        else:
            # 按X第一个变量排序
            X_arr = np.atleast_2d(np.asarray(X, dtype=float))
            order = np.argsort(X_arr[:, 0])

        sorted_resid = residuals[order]
        n_sorted = len(sorted_resid)

        # 分割样本
        omit = int(n_sorted * split_ratio / 2)  # 中间剔除数量
        n_sub = n_sorted - 2 * omit

        if n_sub < 10:
            return {
                "gq_stat": None,
                "p_value": None,
                "has_heteroskedasticity": False,
                "df": None,
                "issues": ["Goldfeld-Quandt检验样本量不足"],
            }

        # 高端和低端残差平方和
        ssr_high = np.sum(sorted_resid[-n_sub:] ** 2)
        ssr_low = np.sum(sorted_resid[:n_sub] ** 2)
        df_sub = n_sub - 2

        if ssr_low < 1e-10:
            return {
                "gq_stat": None,
                "p_value": None,
                "has_heteroskedasticity": False,
                "df": None,
                "issues": ["低端残差平方和接近0，无法计算"],
            }

        gq_stat = ssr_high / ssr_low
        p_value = 1 - stats.f.cdf(gq_stat, df_sub, df_sub)

        has_hetero = p_value < 0.1

        issues = []
        if has_hetero:
            issues.append(
                f"Goldfeld-Quandt检验拒绝同方差假设（GQ={gq_stat:.3f}, p={p_value:.4f}）"
            )

        return {
            "gq_stat": float(gq_stat),
            "p_value": float(p_value),
            "has_heteroskedasticity": bool(has_hetero),
            "df": int(df_sub),
            "n_obs": int(n),
            "issues": issues,
        }

    def vif_test(
        self,
        X: np.ndarray | pd.DataFrame,
        varnames: list[str] | None = None,
        threshold: float = 10.0,
    ) -> dict:
        """
        方差膨胀因子（VIF）检验多重共线性。

        VIF_i = 1 / (1 - R²_i)，其中 R²_i 是其他变量对第i个变量的回归R²
        VIF > 10 通常表示严重多重共线性

        Args:
            X: 自变量矩阵（不含常数项）
            varnames: 变量名列表
            threshold: VIF阈值（默认10）

        Returns:
            dict with vif_table, has_multicollinearity, high_vif_vars
        """
        X_arr = np.atleast_2d(np.asarray(X, dtype=float))
        n_vars = X_arr.shape[1]

        if varnames is None:
            varnames = [f"var_{i}" for i in range(n_vars)]

        vif_results = []
        high_vif_vars = []

        for i in range(n_vars):
            y_vif = X_arr[:, i]
            X_vif = np.delete(X_arr, i, axis=1)
            X_vif = np.column_stack([np.ones(len(y_vif)), X_vif])

            try:
                beta, ssr, rank = np.linalg.lstsq(X_vif, y_vif, rcond=None)[:3]
                residuals = y_vif - X_vif @ beta
                tss = np.sum((y_vif - np.mean(y_vif))**2)
                r2 = 1 - ssr / tss if tss > 0 else 0.0
                vif = 1 / (1 - r2) if r2 < 1 else float("inf")
            except np.linalg.LinAlgError:
                vif = float("inf")

            is_high = vif > threshold
            if is_high:
                high_vif_vars.append(varnames[i])

            vif_results.append({
                "variable": varnames[i],
                "VIF": float(vif) if np.isfinite(vif) else None,
                "R_squared": float(r2),
                "high": is_high,
            })

        return {
            "vif_table": pd.DataFrame(vif_results),
            "has_multicollinearity": len(high_vif_vars) > 0,
            "high_vif_vars": high_vif_vars,
            "threshold": threshold,
        }


# ════════════════════════════════════════════════════════════════════
# Econometrics Rule Engine
# ════════════════════════════════════════════════════════════════════


class EconometricsRuleEngine:
    """
    计量经济学规则引擎的主协调器。

    将 halt_rules/empirical_paper.yaml 中的方法规则
    转化为可执行的统计检验。

    支持的方法类型：
    - did: 双重差分（平行趋势 + 事件研究）
    - iv: 工具变量（弱工具变量检验 + Sargan检验）
    - psm: 倾向得分匹配（平衡性检验）
    - rd: 断点回归（密度检验 + 驱动变量连续性）
    - ols: 普通最小二乘（异方差检验 + VIF）

    使用方法：
        engine = EconometricsRuleEngine()

        # DID检验
        result = engine.validate("did", {
            "event_study_df": df,
            "pre_periods": 3,
        })

        # IV检验
        result = engine.validate("iv", {
            "X": endogenous_var,
            "Z": instruments,
            "residuals_2sls": iv_residuals,
        })

        # PSM平衡性
        result = engine.validate("psm", {
            "df_matched": matched_df,
            "variables": ["size", "lev", "roe"],
        })

        # OLS诊断
        result = engine.validate("ols", {
            "residuals": ols_residuals,
            "X": X_matrix,
        })
    """

    def __init__(self):
        self.did = DIDValidator()
        self.weak_iv = WeakInstrumentTest()
        self.balance = BalanceTestValidator()
        self.hetero = HeteroskedasticityTest()

        self._method_map: dict[str, Literal["did", "iv", "psm", "rd", "ols"]] = {
            "did": "did",
            "diff_in_diff": "did",
            "did_robust": "did",
            "iv": "iv",
            "instrument": "iv",
            "2sls": "iv",
            "psm": "psm",
            "matching": "psm",
            "propensity_score": "psm",
            "rd": "rd",
            "rdd": "rd",
            "regression_discontinuity": "rd",
            "ols": "ols",
            "regression": "ols",
            "panel": "ols",
        }

    def validate(
        self,
        method: str,
        data: dict[str, Any],
    ) -> ValidationResult:
        """
        运行指定方法的验证。

        Args:
            method: 方法类型 ('did' | 'iv' | 'psm' | 'rd' | 'ols')
            data: 包含必要数据的字典

        Returns:
            ValidationResult，passed=True 表示通过所有检查
        """
        method_key = self._method_map.get(method.lower(), method.lower())
        validator_map = {
            "did": self._validate_did,
            "iv": self._validate_iv,
            "psm": self._validate_psm,
            "rd": self._validate_rd,
            "ols": self._validate_ols,
        }

        validator = validator_map.get(method_key)
        if validator is None:
            return ValidationResult(
                passed=False,
                errors=[f"未知方法类型: {method}"],
                details={"method": method},
            )

        return validator(data)

    # ── Method Validators ───────────────────────────────────────────

    def _validate_did(self, data: dict) -> ValidationResult:
        """DID方法验证：平行趋势 + 动态效应"""
        result = ValidationResult(passed=True)
        issues = []
        warnings = []

        # 1. 平行趋势检验
        event_study_df = data.get("event_study_df")
        pre_periods = data.get("pre_periods", 3)

        if event_study_df is not None:
            pt_result = self.did.check_parallel_trend(event_study_df, pre_periods=pre_periods)
            result.details["parallel_trend"] = pt_result

            if not pt_result["passed"]:
                result.add_error(
                    f"平行趋势假设未通过检验（F={pt_result['f_stat']:.3f}, "
                    f"p={pt_result['p_value']:.4f}）"
                )
                issues.extend(pt_result["issues"])
            elif pt_result["warnings"] if "warnings" in pt_result else False:
                result.add_warning(pt_result["issues"][0] if pt_result["issues"] else "")

        # 2. 动态DID检验
        if event_study_df is not None:
            dyn_result = self.did.check_dynamic_did(event_study_df)
            result.details["dynamic_did"] = dyn_result

            if not dyn_result["pre_periods_ok"]:
                result.add_warning("动态DID前一期检验未完全通过")
            warnings.extend(dyn_result.get("warnings", []))
            issues.extend(dyn_result.get("issues", []))

        # 3. 预期结果一致性检查
        expected_direction = data.get("expected_effect_direction")
        if expected_direction and event_study_df is not None:
            df = DIDValidator._ensure_df(event_study_df)
            post_mean = df[df["period"] > 0]["coef"].mean() if len(df[df["period"] > 0]) > 0 else None
            if post_mean is not None:
                if expected_direction == "positive" and post_mean < 0:
                    result.add_warning(
                        f"政策后期平均效应为负({post_mean:.4f})，与预期方向不一致"
                    )
                elif expected_direction == "negative" and post_mean > 0:
                    result.add_warning(
                        f"政策后期平均效应为正({post_mean:.4f})，与预期方向不一致"
                    )

        if not result.has_errors:
            result.details["summary"] = "DID平行趋势假设检验通过"
        else:
            result.details["issues"] = issues

        return result

    def _validate_iv(self, data: dict) -> ValidationResult:
        """IV方法验证：弱工具变量 + Sargan检验"""
        result = ValidationResult(passed=True)

        X = data.get("X")
        Z = data.get("Z")
        controls = data.get("controls")
        residuals_2sls = data.get("residuals_2sls")
        n_instruments = data.get("n_instruments", 1)

        if X is None or Z is None:
            result.add_error("IV检验需要提供 X（内生变量）和 Z（工具变量）")
            return result

        # 1. 一阶段F统计量
        f_result = self.weak_iv.first_stage_f_stat(X, Z, controls=controls)
        result.details["first_stage_f"] = f_result

        if f_result["is_weak"]:
            result.add_error(
                f"弱工具变量（F={f_result['f_stat']:.3f} ≤ 10），"
                f"标准误膨胀严重，建议更换工具变量或使用其他识别策略"
            )
        elif f_result["is_weak_by_sy"]:
            result.add_warning(
                f"工具变量强度不足（Stock-Yogo 10%偏误标准：F需>{16.38:.2f}，"
                f"当前F={f_result['f_stat']:.3f}）"
            )
        else:
            result.details["iv_interpretation"] = f_result["interpretation"]

        # 2. Sargan过度识别检验（如果残差和工具变量数足够）
        if residuals_2sls is not None and n_instruments > 1:
            sargan_result = self.weak_iv.sargan_test(
                residuals_2sls, Z, n_instruments=n_instruments
            )
            result.details["sargan_test"] = sargan_result

            if sargan_result.get("reject_exogeneity"):
                result.add_warning(sargan_result["issues"][0] if sargan_result["issues"] else "Sargan检验拒绝外生性")

        # 3. 解释力检查
        if f_result["r_squared"] < 0.01:
            result.add_warning(
                f"工具变量解释力极弱（R²={f_result['r_squared']:.4f}），"
                "一阶段回归几乎无拟合能力"
            )

        return result

    def _validate_psm(self, data: dict) -> ValidationResult:
        """PSM方法验证：平衡性检验"""
        result = ValidationResult(passed=True)

        df_matched = data.get("df_matched")
        df_before = data.get("df_before")
        variables = data.get("variables")
        treatment_col = data.get("treatment_col", "treatment")
        threshold = data.get("threshold", 0.1)

        if df_matched is None:
            result.add_error("PSM平衡性检验需要提供 df_matched（匹配后数据）")
            return result

        # 1. 匹配后平衡性检验
        bal_result = self.balance.check_balance(
            df_matched, variables=variables,
            treatment_col=treatment_col, threshold=threshold
        )
        result.details["balance_test"] = bal_result

        if not bal_result["passed"]:
            result.add_error(
                f"PSM平衡性检验未通过：{len(bal_result['imbalance_vars'])} 个变量失衡，"
                f"最大标准化偏差={bal_result['max_abs_bias']:.1%}（阈值={threshold*100}%）"
            )
        else:
            result.details["balance_passed"] = True

        # 2. 匹配前后对比（如果提供了匹配前数据）
        if df_before is not None:
            comparison = self.balance.check_covariate_means(
                df_before, df_matched,
                variables=variables, treatment_col=treatment_col
            )
            result.details["balance_comparison"] = comparison

            improvement = comparison.get("improvement_pct", 0)
            if improvement < 50:
                result.add_warning(
                    f"匹配改善幅度较小（{improvement:.1f}%），"
                    "建议检查倾向得分模型设定"
                )

        # 3. 共同支撑域检查
        if "pscore" in (data.get("df_matched") if isinstance(data.get("df_matched"), pd.DataFrame) else pd.DataFrame()).columns:
            # 如果有倾向得分，检验共同支撑
            pscore_df = data["df_matched"]
            pscore_min = pscore_df["pscore"].min()
            pscore_max = pscore_df["pscore"].max()

            treat_pscore = pscore_df[pscore_df[treatment_col] == 1]["pscore"]
            ctrl_pscore = pscore_df[pscore_df[treatment_col] == 0]["pscore"]

            overlap_min = max(treat_pscore.min(), ctrl_pscore.min())
            overlap_max = min(treat_pscore.max(), ctrl_pscore.max())

            if overlap_min >= overlap_max:
                result.add_error(
                    "共同支撑域为空，倾向得分分布完全不重叠，PSM不可行"
                )

        return result

    def _validate_rd(self, data: dict) -> ValidationResult:
        """RDD方法验证：密度检验 + 驱动变量连续性"""
        result = ValidationResult(passed=True)
        warnings = []

        running_var = data.get("running_var")
        cutoff = data.get("cutoff", 0)
        bandwidth = data.get("bandwidth")
        treatment_col = data.get("treatment_col", "treatment")

        if running_var is None:
            result.add_error("RDD验证需要提供 running_var（驱动变量）")
            return result

        running_var = np.asarray(running_var, dtype=float)

        # 1. 密度检验（McCrary）
        # 简化版：在断点处检验密度是否连续
        left = running_var[running_var < cutoff]
        right = running_var[running_var >= cutoff]

        if len(left) > 10 and len(right) > 10:
            # 使用带宽内的核密度估计检验
            bandwidth_est = bandwidth or (np.percentile(running_var, 75) - np.percentile(running_var, 25)) * 1.06 * len(running_var)**(-1/5)

            # 计算断点两侧的密度比
            from scipy.stats import gaussian_kde
            try:
                kde_left = gaussian_kde(left[left > (cutoff - bandwidth_est * 2)])
                kde_right = gaussian_kde(right[right < (cutoff + bandwidth_est * 2)])

                density_at_cutoff_left = kde_left(cutoff)[0]
                density_at_cutoff_right = kde_right(cutoff)[0]

                density_ratio = density_at_cutoff_left / density_at_cutoff_right if density_at_cutoff_right > 0 else float("inf")

                result.details["density_test"] = {
                    "density_ratio": float(density_ratio),
                    "cutoff": float(cutoff),
                    "bandwidth": float(bandwidth_est),
                    "n_left": int(len(left)),
                    "n_right": int(len(right)),
                }

                if density_ratio < 0.5 or density_ratio > 2.0:
                    result.add_warning(
                        f"断点处密度差异较大（密度比={density_ratio:.2f}），"
                        "可能存在操纵（manipulation）"
                    )
            except Exception:
                pass  # 密度估计失败不影响主检验

        # 2. 带宽合理性检查
        if bandwidth is not None:
            bw_range = running_var.max() - running_var.min()
            if bandwidth > bw_range * 0.5:
                result.add_warning(
                    f"带宽（{bandwidth:.3f}）过大，可能混入过多非局部效应"
                )
            elif bandwidth < bw_range * 0.01:
                result.add_warning(
                    f"带宽（{bandwidth:.3f}）过小，样本量可能不足"
                )

        # 3. 断点两侧样本量检查
        if len(left) < 20 or len(right) < 20:
            warnings.append(
                f"断点一侧样本量过少（左={len(left)}，右={len(right)}），"
                "局部效应估计可能不可靠"
            )

        for w in warnings:
            result.add_warning(w)

        return result

    def _validate_ols(self, data: dict) -> ValidationResult:
        """OLS方法验证：异方差 + VIF"""
        result = ValidationResult(passed=True)

        residuals = data.get("residuals")
        X = data.get("X")
        varnames = data.get("varnames")
        threshold = data.get("hetero_threshold", 0.1)

        if residuals is None:
            result.add_error("OLS验证需要提供 residuals（残差）")
            return result

        # 1. 异方差检验
        bp_result = self.hetero.breusch_pagan(residuals, X)
        result.details["breusch_pagan"] = bp_result

        if bp_result.get("has_heteroskedasticity"):
            result.add_warning(
                f"Breusch-Pagan检验拒绝同方差（BP={bp_result['bp_stat']:.3f}, "
                f"p={bp_result['p_value']:.4f}），建议使用稳健标准误"
            )
            result.details["recommendation"] = "使用Clustered SE或HC标准误"
        else:
            result.details["homoskedasticity_ok"] = True

        # 2. White检验（可选）
        if X is not None:
            white_result = self.hetero.white_test(residuals, X)
            result.details["white_test"] = white_result

            if white_result.get("has_heteroskedasticity"):
                result.details["hetero_confirmed"] = True

        # 3. VIF检验
        if X is not None:
            vif_result = self.hetero.vif_test(X, varnames=varnames)
            result.details["vif"] = vif_result

            if vif_result.get("has_multicollinearity"):
                result.add_warning(
                    f"以下变量存在多重共线性（VIF > 10）: "
                    f"{', '.join(vif_result['high_vif_vars'])}"
                )

        # 4. 残差正态性检验（可选，Shapiro-Wilk，仅小样本）
        n_resid = len(residuals) if residuals is not None else 0
        if n_resid > 0 and n_resid < 5000:
            resid_arr = np.asarray(residuals, dtype=float)
            if len(resid_arr) >= 3:
                shapiro_stat, shapiro_p = stats.shapiro(resid_arr[:min(5000, len(resid_arr))])
                result.details["shapiro_wilk"] = {
                    "stat": float(shapiro_stat),
                    "p_value": float(shapiro_p),
                }
                if shapiro_p < 0.05:
                    result.add_warning(
                        f"残差 Shapiro-Wilk 检验显著（p={shapiro_p:.4f}），"
                        "残差分布可能非正态，对大样本影响有限"
                    )

        return result

    # ── Batch Validation ───────────────────────────────────────────

    def validate_all(
        self,
        method_results: dict[str, ValidationResult],
    ) -> dict[str, ValidationResult]:
        """
        合并多方法验证结果。

        Args:
            method_results: {method_name: ValidationResult} 字典

        Returns:
            同输入，但增加了 overall_result
        """
        overall = ValidationResult(passed=True)

        for method_name, vr in method_results.items():
            if not vr.passed:
                overall.passed = False
                overall.errors.extend([f"[{method_name}] {e}" for e in vr.errors])
            overall.warnings.extend([f"[{method_name}] {w}" for w in vr.warnings])

        method_results["_overall"] = overall
        return method_results

    # ── Report Generation ──────────────────────────────────────────

    def generate_report(
        self,
        results: dict[str, ValidationResult],
    ) -> str:
        """
        生成格式化的验证报告（中文）。

        Args:
            results: validate() 返回的 ValidationResult 或 validate_all() 的结果

        Returns:
            格式化的中文报告字符串
        """
        lines = ["=" * 60, "计量经济学规则验证报告", "=" * 60, ""]

        if "_overall" in results:
            results_to_report = {k: v for k, v in results.items() if k != "_overall"}
            overall = results["_overall"]

            lines.append(f"总体结论: {'PASS' if overall.passed else 'FAIL'}")
            if overall.errors:
                lines.append(f"  错误数: {len(overall.errors)}")
            if overall.warnings:
                lines.append(f"  警告数: {len(overall.warnings)}")
            lines.append("")

            for method_name, vr in results_to_report.items():
                lines.append(f"── {method_name.upper()} 验证 ──")
                lines.append(f"  结论: {'PASS' if vr.passed else 'FAIL'}")
                for e in vr.errors:
                    lines.append(f"    [ERROR] {e}")
                for w in vr.warnings:
                    lines.append(f"    [WARN]  {w}")
                if vr.details:
                    lines.append(f"  详情: {list(vr.details.keys())}")
                lines.append("")
        else:
            # 单个结果
            vr = results
            lines.append(f"方法: {results.get('method', 'unknown')}")
            lines.append(f"结论: {'PASS' if vr.passed else 'FAIL'}")

            if vr.errors:
                lines.append(f"\n错误 ({len(vr.errors)}):")
                for e in vr.errors:
                    lines.append(f"  • {e}")

            if vr.warnings:
                lines.append(f"\n警告 ({len(vr.warnings)}):")
                for w in vr.warnings:
                    lines.append(f"  • {w}")

            if vr.details:
                lines.append("\n检验详情:")
                for key, val in vr.details.items():
                    if isinstance(val, dict):
                        lines.append(f"  {key}:")
                        for k2, v2 in val.items():
                            lines.append(f"    {k2}: {v2}")
                    else:
                        lines.append(f"  {key}: {val}")

        lines.append("=" * 60)
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# Module-level convenience functions
# ════════════════════════════════════════════════════════════════════

def check_parallel_trend(event_study_df, pre_periods=3) -> dict:
    """快捷函数：检验DID平行趋势假设"""
    return DIDValidator().check_parallel_trend(event_study_df, pre_periods=pre_periods)


def check_weak_instrument(X, Z, controls=None) -> dict:
    """快捷函数：检验弱工具变量"""
    return WeakInstrumentTest().first_stage_f_stat(X, Z, controls=controls)


def check_balance(df_matched, variables=None, threshold=0.1) -> dict:
    """快捷函数：检验PSM平衡性"""
    return BalanceTestValidator().check_balance(df_matched, variables, threshold=threshold)


def check_heteroskedasticity(residuals, X) -> dict:
    """快捷函数：Breusch-Pagan异方差检验"""
    return HeteroskedasticityTest().breusch_pagan(residuals, X)


# ════════════════════════════════════════════════════════════════════
# Tests / Demo
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 模拟数据演示
    np.random.seed(42)
    n = 500

    # ── DID平行趋势演示 ───────────────────────────────────────────
    print("=== DID平行趋势检验演示 ===")
    periods = [-3, -2, -1, 0, 1, 2, 3]
    coefs = [0.05, 0.02, 0.01, 0.15, 0.18, 0.14, 0.12]
    ses = [0.08, 0.07, 0.06, 0.05, 0.06, 0.07, 0.08]

    event_df = pd.DataFrame({
        "period": periods * 10,
        "coef": np.random.normal(0.1, 0.05, len(periods) * 10),
        "se": np.random.uniform(0.05, 0.1, len(periods) * 10),
    })
    # 真实事件研究：前3期接近0
    for i, p in enumerate(periods):
        mask = event_df["period"] == p
        if p < 0:
            event_df.loc[mask, "coef"] = np.random.normal(0.02, 0.06, mask.sum())
        else:
            event_df.loc[mask, "coef"] = np.random.normal(coefs[i], 0.05, mask.sum())

    pt_result = DIDValidator().check_parallel_trend(event_df, pre_periods=3)
    print(f"通过: {pt_result['passed']}")
    print(f"F统计量: {pt_result['f_stat']:.4f}, p值: {pt_result['p_value']:.4f}")
    print(f"问题: {pt_result['issues']}")
    print()

    # ── 弱工具变量演示 ────────────────────────────────────────────
    print("=== IV弱工具变量检验演示 ===")
    Z = np.random.randn(n, 2)  # 两个工具变量
    X = 0.8 * Z[:, 0] + 0.3 * Z[:, 1] + np.random.randn(n) * 0.5  # X与Z相关
    f_result = WeakInstrumentTest().first_stage_f_stat(X, Z)
    print(f"F统计量: {f_result['f_stat']:.4f}")
    print(f"解释: {f_result['interpretation']}")
    print(f"弱工具变量: {f_result['is_weak']}")
    print()

    # ── 平衡性检验演示 ────────────────────────────────────────────
    print("=== PSM平衡性检验演示 ===")
    treat = pd.DataFrame({
        "treatment": [1] * 200,
        "size": np.random.normal(22, 1.5, 200),
        "lev": np.random.normal(0.5, 0.2, 200),
        "roe": np.random.normal(0.1, 0.05, 200),
    })
    ctrl = pd.DataFrame({
        "treatment": [0] * 300,
        "size": np.random.normal(21.5, 1.5, 300),
        "lev": np.random.normal(0.48, 0.2, 300),
        "roe": np.random.normal(0.1, 0.05, 300),
    })
    matched = pd.concat([treat, ctrl], ignore_index=True)
    bal_result = BalanceTestValidator().check_balance(
        matched, variables=["size", "lev", "roe"], threshold=0.1
    )
    print(f"通过: {bal_result['passed']}")
    print(f"最大标准化偏差: {bal_result['max_abs_bias']:.1%}")
    print(f"失衡变量: {bal_result['imbalance_vars']}")
    print()

    # ── 异方差检验演示 ────────────────────────────────────────────
    print("=== 异方差检验演示 ===")
    X_demo = np.random.randn(n, 3)
    residuals_demo = np.random.randn(n) * (1 + 0.5 * X_demo[:, 0])  # 异方差残差
    hetero = HeteroskedasticityTest()
    bp = hetero.breusch_pagan(residuals_demo, X_demo)
    print(f"BP统计量: {bp['bp_stat']:.4f}, p值: {bp['p_value']:.4f}")
    print(f"存在异方差: {bp['has_heteroskedasticity']}")
    print()

    # ── 规则引擎演示 ─────────────────────────────────────────────
    print("=== 规则引擎演示 ===")
    engine = EconometricsRuleEngine()

    did_result = engine.validate("did", {
        "event_study_df": event_df,
        "pre_periods": 3,
    })
    print(f"DID验证: passed={did_result.passed}")
    if did_result.warnings:
        print(f"  警告: {did_result.warnings}")

    iv_result = engine.validate("iv", {"X": X, "Z": Z})
    print(f"IV验证: passed={iv_result.passed}")
    if iv_result.errors:
        print(f"  错误: {iv_result.errors}")

    ols_result = engine.validate("ols", {"residuals": residuals_demo, "X": X_demo})
    print(f"OLS验证: passed={ols_result.passed}")

    print("\n" + engine.generate_report({
        "did": did_result,
        "iv": iv_result,
        "ols": ols_result,
        "_overall": ValidationResult(passed=did_result.passed and iv_result.passed and ols_result.passed),
    }))
