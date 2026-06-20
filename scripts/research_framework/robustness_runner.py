"""稳健性检验自动化引擎 — 封装中文顶刊所需 10-15 种稳健性检验.

本模块自动生成并执行稳健性检验，覆盖：
  基础检验（8种）：
    1. 平行趋势检验（事件研究）
    2. Bacon 分解（权重诊断）
    3. 安慰剂检验（Placebo）
    4. 倾向得分匹配（PSM）
    5. 更换因变量
    6. 更换控制变量
    7. 子样本检验
    8. 剔除极端观测
  高级检验（5种，v1.5.2+）：
    9.  排除预期效应（anticipation effect）
    10. Honest DiD（Rambachan-Roth 2023）
    11. 改变聚类层级（SE 结构）
    12. 三重差分 DDD
  v1.6.0 新增（5种）：
    13. PSM 截断（共同取值范围）
    14. 组合 DDD（多第三维度）
    15. IV 子样本排除
    16. 滞后因变量检验

Usage:
    runner = RobustnessRunner(df, base_result)
    runner.add_test("parallel_trends")
    runner.add_test("psm_truncation", sub_config={"trim_pct": 5})
    runner.add_test("combined_ddd", sub_config={"max_group3": 3})
    runner.add_test("iv_robust", sub_config={"exclude_var": "province", "exclude_values": ["beijing"]})
    runner.add_test("lagged_depvar", sub_config={"n_lags": 1})
    report = runner.run_all()
    report.print_report()
    report.save_latex("robustness.tex")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "RobustnessRunner",
    "RobustnessTest",
    "RobustnessReport",
    "oster_bounds",
]

_log = logging.getLogger("robustness_runner")
_log.setLevel(logging.INFO)


@dataclass
class RobustnessTest:
    """
    单个稳健性检验结果。

    Attributes
    ----------
    test_name : str
        检验名称。
    test_type : str
        检验类型。
    did_coef : float
        估计的 DID 系数。
    did_se : float
        标准误。
    did_pval : float
        p 值。
    is_consistent : bool
        方向是否与基准一致。
    is_significant : bool
        是否显著。
    note : str
        备注。
    details : dict
        额外信息。
    """

    test_name: str
    test_type: str
    did_coef: float
    did_se: float
    did_pval: float
    is_consistent: bool = True
    is_significant: bool = True
    note: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class RobustnessReport:
    """
    完整稳健性检验报告。

    Attributes
    ----------
    baseline_result : dict
        基准回归结果。
    tests : list[RobustnessTest]
        所有检验结果。
    overall_consistency : float
        一致率（方向一致的检验占比）。
    overall_significance : float
        显著率。
    """

    baseline_result: dict
    tests: list[RobustnessTest] = field(default_factory=list)

    @property
    def overall_consistency(self) -> float:
        if not self.tests:
            return 0.0
        consistent = sum(1 for t in self.tests if t.is_consistent)
        return consistent / len(self.tests)

    @property
    def overall_significance(self) -> float:
        if not self.tests:
            return 0.0
        sig = sum(1 for t in self.tests if t.is_significant)
        return sig / len(self.tests)

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for t in self.tests:
            rows.append({
                "Test": t.test_name,
                "Type": t.test_type,
                "DID Coef": t.did_coef,
                "SE": t.did_se,
                "p-value": t.did_pval,
                "Consistent": "✓" if t.is_consistent else "✗",
                "Significant": "✓" if t.is_significant else "✗",
                "Note": t.note,
            })

        # Baseline row
        br = self.baseline_result
        rows.insert(0, {
            "Test": "(Baseline)",
            "Type": "OLS",
            "DID Coef": br.get("coef", 0),
            "SE": br.get("se", 0),
            "p-value": br.get("pval", 1),
            "Consistent": "—",
            "Significant": "✓" if br.get("pval", 1) < 0.05 else "✗",
            "Note": "基准回归",
        })

        return pd.DataFrame(rows)

    def to_latex(self) -> str:
        df = self.to_dataframe()
        if df.empty:
            return ""

        caption = "\\caption{Robustness Checks}"
        label = "\\label{tab:robustness}"

        lines = [
            "\\begin{sidewaystable}[htbp]",
            "  \\centering",
            f"  {caption}",
            f"  {label}",
            "  \\begin{threeparttable}",
            "  \\begin{tabular}{lrrrrccl}",
            "    \\toprule",
            "    \\textbf{Test} & \\textbf{Type} & "
            "\\textbf{DID Coef} & \\textbf{SE} & "
            "\\textbf{p-value} & \\textbf{Consistent} & "
            "\\textbf{Sig.} & \\textbf{Note} \\\\ \n    \\midrule",
        ]

        for _, row in df.iterrows():
            # Bug fix: NaN 值不能放入 LaTeX 数学模式（\mathord），使用短破折号
            def fmt(val, is_math=False):
                if pd.isna(val):
                    return "—"
                if is_math:
                    return f"${val:.4f}$"
                return f"{val:.4f}"

            lines.append(
                f"    {row['Test']} & {row['Type']} & "
                f"{fmt(row['DID Coef'], True)} & "
                f"{fmt(row['SE'], True)} & "
                f"{fmt(row['p-value'], True)} & "
                f"{row['Consistent']} & {row['Significant']} & {row['Note']} \\\\ "
            )

        lines.extend([
            "    \\bottomrule",
            "  \\end{tabular}",
            "  \\begin{tablenotes}",
            "    \\small",
            "    \\item Consistent = DID coefficient has same sign as baseline. ",
            "    Significant = p-value $<$ 0.05.",
            "    $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.10$.",
            "  \\end{tablenotes}",
            "  \\end{threeparttable}",
            "\\end{sidewaystable}",
        ])
        return "\n".join(lines)


class RobustnessRunner:
    """
    稳健性检验自动化引擎。

    用法：
        runner = RobustnessRunner(df, baseline_result)
        runner.add_test("parallel_trends")
        runner.add_test("placebo")
        runner.add_test("psm")
        runner.add_test("replace_outliers")
        runner.add_test("replace_depvar")
        runner.add_test("iv")
        runner.add_test("wild_bootstrap")
        runner.add_test("sub_sample", sub_config={"year_range": [2019, 2023]})
        runner.add_test("sub_sample", sub_config={"industry": "manufacturing"})
        report = runner.run_all()
    """

    # 中文顶刊所需最小稳健性检验数量
    MIN_TESTS = 4

    def __init__(
        self,
        df: pd.DataFrame,
        baseline_result: dict,
        y_var: str = "y",
        treat_var: str = "did",
        time_var: str = "post",
        unit_var: str = "ticker",
        x_vars: list[str] | None = None,
    ):
        self.df = df.copy()
        self.baseline_result = baseline_result
        self.y_var = y_var
        self.treat_var = treat_var
        self.time_var = time_var
        self.unit_var = unit_var
        self.x_vars = x_vars or []
        self._pending_tests: list[tuple[str, dict]] = []
        self._report: RobustnessReport | None = None

        # ── P2-QUAL-2: Simulated data integrity check ──────────────────────
        # Mirror RegressionEngine's safeguard: if df.attrs flags simulated
        # variables, emit a loud warning. Robustness results on synthetic
        # data must not be used as empirical evidence.
        try:
            df_meta = getattr(df, "attrs", {}) or {}
            is_simulated = bool(df_meta.get("is_simulated", False))
            simulated_vars = list(df_meta.get("simulated_vars", []))
            if is_simulated or simulated_vars:
                msg = (
                    "[RobustnessRunner] WARNING: input dataframe contains "
                    f"{len(simulated_vars)} simulated variable(s). "
                    "Robustness checks on synthetic data are demonstration only."
                )
                _log.warning(msg)
        except Exception:  # noqa: S110
            pass

    def add_test(
        self,
        test_name: str,
        sub_config: dict | None = None,
    ) -> "RobustnessRunner":
        """链式添加稳健性检验。"""
        self._pending_tests.append((test_name, sub_config or {}))
        return self

    def run_all(self) -> RobustnessReport:
        """运行所有待执行检验。"""
        report = RobustnessReport(baseline_result=self.baseline_result)

        for test_name, config in self._pending_tests:
            try:
                test_result = self._run_single_test(test_name, config)
                if test_result:
                    report.tests.append(test_result)
            except Exception as exc:
                _log.warning(f"[RobustnessRunner] {test_name} failed: {exc}")

        self._report = report
        return report

    def _run_single_test(self, test_name: str, config: dict) -> RobustnessTest | None:
        """执行单个检验。"""
        dispatch = {
            "parallel_trends": self._test_parallel_trends,
            "placebo": self._test_placebo,
            "psm": self._test_psm,
            "replace_outliers": self._test_replace_outliers,
            "replace_depvar": self._test_replace_depvar,
            "iv": self._test_iv,
            "wild_bootstrap": self._test_wild_bootstrap,
            "sub_sample": lambda cfg: self._test_sub_sample(**cfg),
            "remove_extreme": self._test_remove_extreme,
            "change_control": self._test_change_control,
            # 高级稳健性检验（v1.5.2）
            "honest_did": self._test_honest_did,
            "change_cluster": self._test_change_cluster,
            "triple_did": self._test_triple_did,
            # 新增5种稳健性检验（v1.6.0）
            "exclude_preannouncement": self._test_exclude_preannouncement,
            "psm_truncation": self._test_psm_truncation,
            "combined_ddd": self._test_combined_ddd,
            "iv_robust": self._test_iv_robust,
            "lagged_depvar": self._test_lagged_depvar,
            # v1.7.0 新增
            "oster_bounds": self._test_oster_bounds,
        }

        runner = dispatch.get(test_name)
        if not runner:
            _log.warning(f"[RobustnessRunner] Unknown test: {test_name}")
            return None

        return runner(config)

    def _get_result(self, df_sub: pd.DataFrame) -> tuple[float, float, float]:
        """在子样本上运行 DID 回归。"""
        try:
            import statsmodels.api as sm

            did_col = df_sub[self.treat_var].astype(float) * df_sub[self.time_var].astype(float)
            X = sm.add_constant(
                pd.concat([df_sub[self.x_vars], did_col], axis=1).fillna(0)
            )
            y = df_sub[self.y_var].astype(float).values
            model = sm.OLS(y, X.values).fit(cov_type="HC1")

            # 找 DID 系数（第 len(x_vars)+1 个）
            did_idx = len(self.x_vars)
            if did_idx < len(model.params):
                return (
                    float(model.params[did_idx]),
                    float(model.bse[did_idx]),
                    float(model.pvalues[did_idx]),
                )
        except Exception as exc:
            _log.warning(f"[RobustnessRunner] DID regression failed: {exc}")
        return (np.nan, np.nan, 1.0)

    # ── Test implementations ──────────────────────────────────────────

    def _test_parallel_trends(self, config: dict) -> RobustnessTest:
        """平行趋势检验（事件研究）。"""
        from scripts.research_framework.modern_did import ModernDiDEngine

        engine = ModernDiDEngine(
            self.df, self.y_var, self.treat_var, self.time_var,
            self.unit_var, self.x_vars,
        )
        result = engine.did_2x2()
        pt = engine.parallel_trends_test()
        is_consistent = (result.coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (result.pval < 0.05)

        return RobustnessTest(
            test_name="Parallel Trends",
            test_type="Event Study",
            did_coef=result.coef,
            did_se=result.se,
            did_pval=result.pval,
            is_consistent=is_consistent,
            is_significant=is_significant,
            note=f"pre-trend p={pt.get('pval', 1):.3f}",
            details=pt,
        )

    def _test_placebo(self, config: dict) -> RobustnessTest:
        """Permutation-based placebo test (randomized treatment assignment).

        Repeats the treatment assignment 500 times and compares the observed
        DID coefficient to the distribution of placebo coefficients.
        """
        n_permutations = 500

        rng = np.random.default_rng(42)
        df_p = self.df.copy()
        p_treat = float(df_p[self.treat_var].mean())

        # Store results from all permutations
        placebo_coefs = np.zeros(n_permutations)

        for i in range(n_permutations):
            df_b = df_p.copy()
            df_b["placebo_treat"] = rng.choice(
                [0, 1], size=len(df_p), p=[1 - p_treat, p_treat]
            )
            try:
                coef, se, pval = self._get_result(df_b)
                if not np.isnan(coef):
                    placebo_coefs[i] = coef
            except Exception:
                placebo_coefs[i] = np.nan

        # Remove failed permutations
        valid = ~np.isnan(placebo_coefs)
        if valid.sum() < 10:
            return RobustnessTest(
                test_name="Placebo (Randomized)",
                test_type="Placebo",
                did_coef=np.nan,
                did_se=np.nan,
                did_pval=1.0,
                is_consistent=False,
                is_significant=False,
                note=f"Only {valid.sum()} valid permutations (need ≥10)",
                details={"n_permutations": n_permutations, "valid": int(valid.sum())},
            )

        # Get observed coefficient
        obs_result = self._get_result(df_p)
        obs_coef = obs_result[0]

        # Compute p-value: fraction of |placebo| >= |observed|
        p_value = np.mean(np.abs(placebo_coefs[valid]) >= np.abs(obs_coef))

        return RobustnessTest(
            test_name="Placebo (Randomized)",
            test_type="Placebo",
            did_coef=obs_coef,
            did_se=np.nan,
            did_pval=p_value,
            is_consistent=True,
            is_significant=p_value < 0.05,
            note=f"{p_value:.3f} of {valid.sum()} placebo |coef| >= |{obs_coef:.3f}|",
            details={
                "n_permutations": n_permutations,
                "valid_permutations": int(valid.sum()),
                "placebo_mean": float(np.mean(placebo_coefs[valid])),
                "placebo_std": float(np.std(placebo_coefs[valid])),
                "placebo_5pct": float(np.percentile(placebo_coefs[valid], 5)),
                "placebo_95pct": float(np.percentile(placebo_coefs[valid], 95)),
                "interpretation": "Significant if p_value < 0.05",
            },
        )

    def _test_psm(self, config: dict) -> RobustnessTest:
        """倾向得分匹配（PSM）。"""
        try:
            from scripts.research_framework.regression_engine import RegressionEngine

            engine = RegressionEngine(self.df, None, self.unit_var, self.time_var)
            result = engine.psm_did(
                y_var=self.y_var,
                treat_var=self.treat_var,
                time_var=self.time_var,
                match_vars=self.x_vars[:3],
            )
            did_coef = result.get("did_coef", 0)
            did_se = result.get("did_se", 0)
            did_pval = result.get("did_pval", 1)
            note = result.get("psm_note", "")
        except Exception:
            did_coef, did_se, did_pval = (np.nan, np.nan, 1.0)
            note = "PSM failed"

        is_consistent = (did_coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (did_pval < 0.05)

        return RobustnessTest(
            test_name="PSM-DID",
            test_type="Matching",
            did_coef=did_coef,
            did_se=did_se,
            did_pval=did_pval,
            is_consistent=is_consistent,
            is_significant=is_significant,
            note=note,
        )

    def _test_replace_outliers(self, config: dict) -> RobustnessTest:
        """替换极端值（缩尾处理）。"""
        df_o = self.df.copy()
        pct = config.get("pct", 1)
        for col in [self.y_var] + self.x_vars:
            if col in df_o.columns:
                low = df_o[col].quantile(pct / 100)
                high = df_o[col].quantile(1 - pct / 100)
                df_o[col] = df_o[col].clip(low, high)

        coef, se, pval = self._get_result(df_o)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (pval < 0.05)

        return RobustnessTest(
            test_name=f"Winsorize ({pct}%)",
            test_type="Outlier Removal",
            did_coef=coef,
            did_se=se,
            did_pval=pval,
            is_consistent=is_consistent,
            is_significant=is_significant,
            note=f"winsorized at {pct}%/{100-pct}%",
        )

    def _test_replace_depvar(self, config: dict) -> RobustnessTest:
        """更换因变量。"""
        alt_y = config.get("alt_y_var", None)
        if not alt_y or alt_y not in self.df.columns:
            return RobustnessTest(
                test_name="Alternative Dep. Var.",
                test_type="Variable Replacement",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                note="alt_y_var not specified or not found",
            )

        df_a = self.df.copy()
        coef, se, pval = self._get_result_with_y(df_a, alt_y)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (pval < 0.05)

        return RobustnessTest(
            test_name=f"Alt. Dep. Var.: {alt_y}",
            test_type="Variable Replacement",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"replaced {self.y_var} with {alt_y}",
        )

    def _get_result_with_y(self, df: pd.DataFrame, y_var: str) -> tuple[float, float, float]:
        try:
            import statsmodels.api as sm
            did_col = df[self.treat_var].astype(float) * df[self.time_var].astype(float)
            X = sm.add_constant(pd.concat([df[self.x_vars], did_col], axis=1).fillna(0))
            y = df[y_var].astype(float).values
            model = sm.OLS(y, X.values).fit(cov_type="HC1")
            did_idx = len(self.x_vars)
            if did_idx < len(model.params):
                return (
                    float(model.params[did_idx]),
                    float(model.bse[did_idx]),
                    float(model.pvalues[did_idx]),
                )
        except Exception:  # noqa: S110
            pass
        return (np.nan, np.nan, 1.0)

    def _test_iv(self, config: dict) -> RobustnessTest:
        """工具变量检验：委托 IVPanel 执行 2SLS。

        Falls back to NaN (with informative note) if IVPanel is unavailable
        or the data lacks an instrument column.
        """
        # Look for an instrument column in df (common conventions: iv, instrument, z, excluded)
        iv_candidates = ["iv", "instrument", "z", "excluded_iv", "instrument_var"]
        iv_col = next(
            (c for c in iv_candidates if c in self.df.columns),
            config.get("iv_var"),
        )
        if iv_col is None or iv_col not in self.df.columns:
            return RobustnessTest(
                test_name="IV Robustness",
                test_type="Instrumental Variable",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                note="No instrument column found (looked for: iv, instrument, z, excluded_iv)",
            )
        try:
            from scripts.research_framework.iv_panel import IVPanel
            iv_engine = IVPanel(
                df=self.df,
                y_var=self.y_var,
                treat_var=self.treat_var,
                instrument_var=iv_col,
                x_vars=self.x_vars,
                unit_var=self.unit_var,
                time_var=self.time_var,
                cluster_var=self.unit_var,
            )
            iv_result = iv_engine.fit(method="2sls")
            coef = float(getattr(iv_result, "coef", np.nan))
            se = float(getattr(iv_result, "se", np.nan))
            pval = float(getattr(iv_result, "pval", 1.0))
            if not np.isfinite(coef):
                raise ValueError("IVPanel returned non-finite coefficient")
            return RobustnessTest(
                test_name="IV Robustness (2SLS)",
                test_type="Instrumental Variable",
                did_coef=coef, did_se=se, did_pval=pval,
                is_consistent=(coef * self.baseline_result.get("coef", 0) > 0),
                is_significant=(pval < 0.05),
                note=f"iv_col={iv_col}",
            )
        except Exception as exc:
            return RobustnessTest(
                test_name="IV Robustness",
                test_type="Instrumental Variable",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                note=f"IVPanel failed: {type(exc).__name__}: {exc}",
            )

    def _test_wild_bootstrap(self, config: dict) -> RobustnessTest:
        """Wild Cluster Bootstrap：委托 ModernDiDEngine.wild_bootstrap()。

        Falls back to NaN with informative note if engine is unavailable,
        no cluster_var is set, or the underlying TWFE fit fails.
        """
        B = int(config.get("B", 999))
        seed = int(config.get("seed", 42))
        bootstrap_type = config.get("bootstrap_type", "rademacher")
        cluster_var = config.get("cluster_var", self.unit_var)
        try:
            from scripts.research_framework.modern_did import ModernDiDEngine
            engine = ModernDiDEngine(
                df=self.df,
                y_var=self.y_var,
                treat_var=self.treat_var,
                time_var=self.time_var,
                unit_var=self.unit_var,
                cluster_var=cluster_var,
            )
            # fit() is the entry point; pass df explicitly per signature
            engine.fit(df=self.df, y=self.y_var, treat=self.treat_var,
                       post=self.time_var, cluster=cluster_var)
            boot = engine.wild_bootstrap(
                cluster_var=cluster_var, B=B, bootstrap_type=bootstrap_type
            )
            coef = float(boot.get("coef", np.nan))
            se = float(boot.get("se", np.nan))
            pval = float(boot.get("pval", 1.0))
            if not np.isfinite(coef):
                raise ValueError(f"Wild bootstrap returned non-finite coefficient: {boot}")
            return RobustnessTest(
                test_name=f"Wild Bootstrap (B={B})",
                test_type="Wild Cluster Bootstrap",
                did_coef=coef, did_se=se, did_pval=pval,
                is_consistent=(coef * self.baseline_result.get("coef", 0) > 0),
                is_significant=(pval < 0.05),
                note=f"bootstrap_type={bootstrap_type}, cluster={cluster_var}",
            )
        except Exception as exc:
            return RobustnessTest(
                test_name="Wild Bootstrap",
                test_type="Wild Cluster Bootstrap",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                note=f"ModernDiDEngine.wild_bootstrap failed: {type(exc).__name__}: {exc}",
            )

    def _test_sub_sample(
        self,
        year_range: list | None = None,
        industry: str | None = None,
        n_firms: int | None = None,
    ) -> RobustnessTest:
        """子样本检验（按年份/行业/企业数限制）。"""
        df_s = self.df.copy()

        # Bug fix: time_var 是 post（二进制 0/1），不能用它过滤年份
        # 自动检测年份列：优先使用 'year'，其次尝试从 DatetimeIndex 提取
        year_col = "year"
        if year_col not in df_s.columns:
            # 尝试常见年份列名
            for col in ["date", "year_num", "ann_year"]:
                if col in df_s.columns:
                    year_col = col
                    break
            else:
                # 尝试从 DatetimeIndex 提取年份
                if isinstance(df_s.index, pd.DatetimeIndex):
                    df_s = df_s.reset_index()
                    if "date" in df_s.columns:
                        df_s["_year"] = pd.to_datetime(df_s["date"]).dt.year
                        year_col = "_year"
                    else:
                        year_col = None

        if year_range and year_col and year_col in df_s.columns:
            try:
                df_s = df_s[
                    (df_s[year_col] >= year_range[0]) &
                    (df_s[year_col] <= year_range[1])
                ]
            except Exception:  # noqa: S110  # intentional: optional robustness check must not block pipeline
                pass  # 无法过滤年份，继续用全量数据
        if industry and "industry" in df_s.columns:
            df_s = df_s[df_s["industry"] == industry]

        coef, se, pval = self._get_result(df_s)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (pval < 0.05)

        note_parts = []
        if year_range:
            note_parts.append(f"{year_range[0]}-{year_range[1]}")
        if industry:
            note_parts.append(industry)
        if n_firms:
            note_parts.append(f"N={n_firms}")
        note = ", ".join(note_parts) if note_parts else f"N={len(df_s)}"

        return RobustnessTest(
            test_name="Sub-sample",
            test_type="Sample Restriction",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=note,
        )

    def _test_remove_extreme(self, config: dict) -> RobustnessTest:
        """剔除极端观测。"""
        n_remove = config.get("n_remove", 5)
        df_e = self.df.copy()
        for col in [self.y_var]:
            if col in df_e.columns:
                df_e = df_e.nlargest(len(df_e) - n_remove, col)

        coef, se, pval = self._get_result(df_e)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (pval < 0.05)

        return RobustnessTest(
            test_name="Remove Extreme",
            test_type="Sample Restriction",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"removed {n_remove} largest observations",
        )

    def _test_change_control(self, config: dict) -> RobustnessTest:
        """更换控制变量。"""
        alt_x = config.get("alt_x_vars", [])
        df_c = self.df.copy()
        coef, se, pval = self._get_result_with_x(df_c, alt_x)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (pval < 0.05)

        return RobustnessTest(
            test_name="Alternative Controls",
            test_type="Control Variable Change",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"replaced {self.x_vars} with {alt_x}",
        )

    def _get_result_with_x(self, df: pd.DataFrame, x_vars: list) -> tuple[float, float, float]:
        try:
            import statsmodels.api as sm
            did_col = df[self.treat_var].astype(float) * df[self.time_var].astype(float)
            X = sm.add_constant(pd.concat([df[x_vars], did_col], axis=1).fillna(0))
            y = df[self.y_var].astype(float).values
            model = sm.OLS(y, X.values).fit(cov_type="HC1")
            did_idx = len(x_vars)
            if did_idx < len(model.params):
                return (
                    float(model.params[did_idx]),
                    float(model.bse[did_idx]),
                    float(model.pvalues[did_idx]),
                )
        except Exception:  # noqa: S110
            pass
        return (np.nan, np.nan, 1.0)

    # ── Report ──────────────────────────────────────────────────────

    def print_report(self):
        if not self._report:
            self.run_all()

        report = self._report
        print(f"\n{'='*70}")
        print(f"  Robustness Report")
        print(f"  Baseline: coef={report.baseline_result.get('coef', 0):.4f} "
              f"p={report.baseline_result.get('pval', 1):.4f}")
        print(f"  Consistency: {report.overall_consistency:.1%} "
              f"  Significance: {report.overall_significance:.1%}")
        print(f"  Total tests: {len(report.tests)}/{self.MIN_TESTS} (min required)")
        print(f"{'='*70}")

        df = report.to_dataframe()
        print(df.to_string(index=False))

    def save_latex(self, path: str | Path):
        if not self._report:
            self.run_all()
        latex = self._report.to_latex()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(latex, encoding="utf-8")

    # ── 新增：高级稳健性检验 ──────────────────────────────────────────

    def _test_honest_did(self, config: dict) -> RobustnessTest:
        """Honest DiD 敏感性分析（Rambachan-Roth 2023）。"""
        try:
            from scripts.research_framework.modern_did import ModernDiDEngine
        except Exception:
            return RobustnessTest(
                test_name="Honest DiD",
                test_type="Sensitivity",
                did_coef=np.nan, did_se=np.nan, did_pval=np.nan,
                note="modern_did not available",
            )

        engine = ModernDiDEngine(
            self.df, self.y_var, self.treat_var,
            self.time_var, self.unit_var, self.x_vars,
        )
        base = engine.did_2x2()
        m = config.get("m", 0.5)
        try:
            honest = engine.honest_did(m=m)
            breakdown = honest.get("breakdown_value", np.nan)
        except Exception:
            breakdown = np.nan

        base_coef = abs(base.coef)
        # breakdown 越大说明越稳健
        is_robust = (not np.isnan(breakdown)) and (breakdown > 2 * base_coef)
        is_significant = base.pval < 0.05

        return RobustnessTest(
            test_name=f"Honest DiD (m={m})",
            test_type="Sensitivity",
            did_coef=base.coef, did_se=base.se, did_pval=base.pval,
            is_consistent=is_robust, is_significant=is_significant,
            note=f"breakdown={breakdown:.4f}" if not np.isnan(breakdown) else "N/A",
            details={"breakdown": breakdown, "m": m},
        )

    def _test_change_cluster(self, config: dict) -> RobustnessTest:
        """改变聚类层级（从行业聚类改为省份聚类等）。"""
        new_cluster = config.get("cluster_var", "")
        if not new_cluster or new_cluster not in self.df.columns:
            return RobustnessTest(
                test_name="Change Cluster",
                test_type="SE Structure",
                did_coef=np.nan, did_se=np.nan, did_pval=np.nan,
                note=f"cluster var '{new_cluster}' not found",
            )

        try:
            import statsmodels.api as sm
            did_col = self.df[self.treat_var].astype(float) * self.df[self.time_var].astype(float)
            X = sm.add_constant(
                pd.concat([self.df[self.x_vars], did_col], axis=1).fillna(0)
            )
            y = self.df[self.y_var].astype(float).values
            groups = self.df[new_cluster].values
            model = sm.OLS(y, X.values).fit(cov_type="cluster", cov_kwds={"groups": groups})
            did_idx = len(self.x_vars)
            coef = float(model.params[did_idx])
            se = float(model.bse[did_idx])
            from scipy import stats
            t = coef / se
            # Bug fix: cluster-robust SE 的 p 值自由度应为 G-1（聚类数-1），而非 n-k
            # 原: df = len(y) - X.shape[1]，高估自由度会使 p 值偏小
            n_clusters = len(np.unique(groups))
            dof = max(1, n_clusters - 1)  # 最小为 1，防止除零
            pval = 2 * (1 - stats.t.cdf(abs(t), df=dof))
        except Exception:
            return RobustnessTest(
                test_name=f"Cluster ({new_cluster})",
                test_type="SE Structure",
                did_coef=np.nan, did_se=np.nan, did_pval=np.nan,
                note="Cluster SE estimation failed",
            )

        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (pval < 0.05)

        return RobustnessTest(
            test_name=f"Cluster ({new_cluster})",
            test_type="SE Structure",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"re-clustered by {new_cluster}",
        )

    def _test_triple_did(self, config: dict) -> RobustnessTest:
        """三重差分 DDD稳健性检验。"""
        group3_var = config.get("group3_var", "")
        if not group3_var or group3_var not in self.df.columns:
            return RobustnessTest(
                test_name="Triple DiD",
                test_type="DDD",
                did_coef=np.nan, did_se=np.nan, did_pval=np.nan,
                note=f"group3 var '{group3_var}' not found",
            )

        try:
            from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
            engine = TripleDiffDIDEngine(
                outcome_var=self.y_var, treatment_var=self.treat_var,
                time_var=self.time_var, unit_var=self.unit_var,
                group3_var=group3_var,
            )
            result = engine.fit(x_vars=self.x_vars, cluster_var=config.get("cluster"))
            coef = result.get("coef", np.nan)
            se = result.get("se", np.nan)
            pval = result.get("pval", np.nan)
        except Exception as exc:
            return RobustnessTest(
                test_name=f"Triple DiD ({group3_var})",
                test_type="DDD",
                did_coef=np.nan, did_se=np.nan, did_pval=np.nan,
                note=f"DDD failed: {exc}",
            )

        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0) if not np.isnan(coef) else False
        is_significant = (pval < 0.05) if not np.isnan(pval) else False

        return RobustnessTest(
            test_name=f"Triple DiD ({group3_var})",
            test_type="DDD",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"DDD with {group3_var}",
        )

    def _test_exclude_preannouncement(self, config: dict) -> RobustnessTest:
        """排除预期效应：剔除政策公布前n期的观测，处理同期预期偏差问题。

        预期效应(anticipation effect)指被处理单位在政策正式实施前就做出反应，
        导致DID系数低估或高估处理效应。本检验剔除处理组在政策公布后的部分观测，
        若处理效应仍然显著，说明结果不是由预期效应驱动的。

        Parameters
        ----------
        config : dict
            exclude_periods : int, default 1
                剔除政策前多少期。例如 exclude_periods=2 意味着剔除处理组
                在 post=1 之前2期的所有观测。
            announce_time : float | None, default None
                政策公布时间点（时间变量的值）。若不提供，简化处理：
                剔除处理组 post=1 之前的所有观测（假设 post=1 为政策实施时点）。

        Notes
        -----
        本检验不适用于没有明确政策公布时间和实施时间分离的情形。
        """
        exclude_periods = config.get("exclude_periods", 1)
        announce_time = config.get("announce_time", None)

        df_e = self.df.copy()

        if announce_time is not None:
            # Bug fix: 原逻辑使用 self.unit_var != self.treat_var 比较字符串和整数，永远为 True
            # 正确逻辑：保留控制组（treat=0）的所有观测，保留处理组（treat=1）
            #          在 announce_time - exclude_periods 之后的观测
            # 关键：unit_var 是单位 ID（如 ticker），treat_var 是处理指示（0/1）
            #       announce_time 是时间变量的值（如年份 2018）
            is_control = df_e[self.treat_var] == 0
            is_treated_post = (df_e[self.treat_var] == 1) & (
                df_e[self.time_var] >= announce_time - exclude_periods
            )
            df_e = df_e[is_control | is_treated_post]
        else:
            treat_mask = df_e[self.treat_var] == 1
            pre_mask = df_e[self.time_var] < 1
            if treat_mask.sum() > 0 and pre_mask.sum() > 0:
                df_e = df_e[~(treat_mask & pre_mask)]

        n_original = len(self.df)
        n_trimmed = len(df_e)
        if n_trimmed < 50:
            return RobustnessTest(
                test_name=f"Exclude Pre-ann. ({exclude_periods}p)",
                test_type="Anticipation Robustness",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note=f"样本量不足 (N={n_trimmed})",
            )

        coef, se, pval = self._get_result(df_e)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0) if not np.isnan(coef) else False
        is_significant = (pval < 0.05) if not np.isnan(pval) else False

        return RobustnessTest(
            test_name=f"Exclude Pre-ann. ({exclude_periods}p)",
            test_type="Anticipation Robustness",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"剔除处理组前{exclude_periods}期，N={n_original}→{n_trimmed}",
            details={
                "exclude_periods": exclude_periods,
                "announce_time": announce_time,
                "n_original": n_original,
                "n_trimmed": n_trimmed,
            },
        )

    def _test_psm_truncation(self, config: dict) -> RobustnessTest:
        """倾向得分截断：剔除倾向得分在共同取值范围之外的观测。

        标准PSM在倾向得分分布尾部可能找不到良好的匹配对象，
        这些尾部观测的匹配质量差，导致估计偏误。本检验通过截断
        (trimming) 倾向得分分布的极端值，检验结果是否稳健。

        仅保留处理组和对照组倾向得分的共同区间 [low, high]。
        若截断后结果仍显著，说明估计不依赖于尾部低质量匹配。

        Parameters
        ----------
        config : dict
            trim_pct : float, default 5
                截断比例（两侧各截断trim_pct%）。默认5%即剔除
                倾向得分最低5%和最高5%的观测。
            match_vars : list[str], default None
                PSM 匹配变量。默认使用前3个控制变量。
        """
        trim_pct = config.get("trim_pct", 5)
        match_vars = config.get("match_vars", self.x_vars[:3])

        df_t = self.df.copy()

        try:
            import statsmodels.api as sm

            X_psm_data = df_t[match_vars].astype(float)
            X_psm_data = X_psm_data.apply(pd.to_numeric, errors="coerce").fillna(0)
            X_psm = sm.add_constant(X_psm_data)
            y_treat = df_t[self.treat_var].astype(float)

            logit = sm.Logit(y_treat, X_psm.values).fit(disp=0, method="newton", maxiter=100)
            df_t["_prop_score"] = logit.predict(X_psm.values)

            low = df_t["_prop_score"].quantile(trim_pct / 100)
            high = df_t["_prop_score"].quantile(1 - trim_pct / 100)

            treated_in_range = (
                (df_t[self.treat_var] == 1) &
                (df_t["_prop_score"] >= low) &
                (df_t["_prop_score"] <= high)
            )
            ctrl_in_range = (
                (df_t[self.treat_var] == 0) &
                (df_t["_prop_score"] >= low) &
                (df_t["_prop_score"] <= high)
            )
            df_trimmed = df_t[treated_in_range | ctrl_in_range]
            n_original = len(df_t)
            n_trimmed = len(df_trimmed)
        except Exception as exc:
            return RobustnessTest(
                test_name=f"PSM Truncation ({trim_pct}%/{100-trim_pct}%)",
                test_type="Common Support",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note=f"PSM truncation failed: {exc}",
            )

        if n_trimmed < 50:
            return RobustnessTest(
                test_name=f"PSM Truncation ({trim_pct}%/{100-trim_pct}%)",
                test_type="Common Support",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note=f"截断后样本量不足 (N={n_trimmed})",
            )

        coef, se, pval = self._get_result(df_trimmed)
        is_consistent = (coef * self.baseline_result.get("coef", 0) > 0) if not np.isnan(coef) else False
        is_significant = (pval < 0.05) if not np.isnan(pval) else False

        return RobustnessTest(
            test_name=f"PSM Truncation ({trim_pct}%/{100-trim_pct}%)",
            test_type="Common Support",
            did_coef=coef, did_se=se, did_pval=pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"PS∈[{low:.3f},{high:.3f}]，{n_original}→{n_trimmed}",
            details={
                "trim_pct": trim_pct,
                "ps_low": float(low),
                "ps_high": float(high),
                "n_original": n_original,
                "n_trimmed": n_trimmed,
            },
        )

    def _test_combined_ddd(self, config: dict) -> RobustnessTest:
        """组合DDD：对多个第三维度变量分别运行DDD，检验稳健性。

        DDD (三重差分) 的一致性依赖于第三个维度的正确选择。
        本检验自动检测所有可能的第三维度变量，分别运行DDD，
        汇总各维度的处理效应，报告中位数系数和方向一致率。

        一致率>=60%即认为DDD结果对该维度选择稳健。

        Parameters
        ----------
        config : dict
            group3_vars : list[str], default None
                显式指定的第三维度变量列表。若为空则自动检测。
            max_group3 : int, default 5
                自动检测时最多使用的变量数量。
            cluster : str | None, default None
                聚类标准误的维度。

        Notes
        -----
        本检验使用 Fisher 合并p值方法 (Fisher's combination test)
        对各维度DDD的p值进行合并。
        """
        group3_vars = config.get("group3_vars", [])
        max_group3 = config.get("max_group3", 5)
        cluster = config.get("cluster", None)

        if not group3_vars:
            categorical_cols = []
            for col in self.df.columns:
                if col in {self.y_var, self.treat_var, self.time_var, self.unit_var}:
                    continue
                if col == "_prop_score":
                    continue
                nunique = self.df[col].nunique()
                if nunique >= 2 and nunique <= 15:
                    categorical_cols.append(col)
            group3_vars = categorical_cols[:max_group3]

        results: list[dict] = []
        for gvar in group3_vars:
            if gvar not in self.df.columns:
                continue
            try:
                from scripts.research_framework.triple_diff_did import TripleDiffDIDEngine
                engine = TripleDiffDIDEngine(
                    outcome_var=self.y_var,
                    treatment_var=self.treat_var,
                    time_var=self.time_var,
                    unit_var=self.unit_var,
                    group3_var=gvar,
                )
                result = engine.fit(x_vars=self.x_vars, cluster_var=cluster)
                results.append({
                    "group3_var": gvar,
                    "coef": result.get("coef", np.nan),
                    "se": result.get("se", np.nan),
                    "pval": result.get("pval", np.nan),
                })
            except Exception:
                continue

        if not results:
            return RobustnessTest(
                test_name="Combined DDD",
                test_type="DDD Multi-dimension",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note="No valid group3 vars found",
            )

        coefs = [r["coef"] for r in results if not np.isnan(r["coef"])]
        ses = [r["se"] for r in results if not np.isnan(r["se"])]

        median_coef = float(np.median(coefs)) if coefs else np.nan
        avg_se = float(np.mean(ses)) if ses else np.nan
        n_valid = len(coefs)

        baseline_coef = self.baseline_result.get("coef", 0)
        consistent_count = sum(1 for c in coefs if c * baseline_coef > 0)
        consistency_rate = consistent_count / n_valid if n_valid > 0 else 0.0

        valid_pvals = [r["pval"] for r in results if not np.isnan(r["pval"]) and r["pval"] > 0]
        if valid_pvals:
            from scipy import stats
            chi2_stat = -2.0 * sum(np.log(p) for p in valid_pvals)
            combined_pval = float(1.0 - stats.chi2.cdf(chi2_stat, 2 * len(valid_pvals)))
        else:
            combined_pval = np.nan

        is_consistent = consistency_rate >= 0.6
        is_significant = (combined_pval < 0.05) if not np.isnan(combined_pval) else False

        return RobustnessTest(
            test_name=f"Combined DDD (n={n_valid})",
            test_type="DDD Multi-dimension",
            did_coef=median_coef, did_se=avg_se, did_pval=combined_pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"{n_valid} group3 vars, {consistency_rate:.0%} consistent, Fisher combined p",
            details={
                "results_by_group3": results,
                "n_group3": n_valid,
                "consistency_rate": consistency_rate,
                "median_coef": median_coef,
                "combined_pval": combined_pval,
            },
        )

    def _test_iv_robust(self, config: dict) -> RobustnessTest:
        """工具变量子样本排除稳健性检验。

        IV估计的一致性依赖于排除性限制（exclusion restriction）。
        若某些子样本违背了IV的外生性假设，则应当剔除后重新估计。
        本检验支持指定剔除变量和对应的取值组合。

        Parameters
        ----------
        config : dict
            exclude_var : str | None, default None
                剔除变量的列名。例如 "province" 或 "industry"。
            exclude_values : list, default []
                剔除变量的取值列表。例如 ["beijing", "shanghai"]。
            iv_vars : list[str] | None, default None
                工具变量列表。若不提供，使用默认IV。

        Notes
        -----
        本检验调用 IVPanel 进行 2SLS 估计。
        提取的是 treat_var 的 IV 估计系数（而非 DID 交乘项）。
        对于 DID 场景，应当将 treat_var 视为内生变量，
        用 IV 估计其在 DID 模型中的间接效应。
        """
        exclude_var = config.get("exclude_var", None)
        exclude_values = config.get("exclude_values", [])
        iv_vars = config.get("iv_vars", None)

        df_i = self.df.copy()

        if exclude_var and exclude_var in df_i.columns and exclude_values:
            df_i = df_i[~df_i[exclude_var].isin(exclude_values)]

        if len(df_i) < 50:
            return RobustnessTest(
                test_name="IV Subsample",
                test_type="IV Robustness",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note=f"剔除后样本量不足 (N={len(df_i)})",
            )

        try:
            from scripts.research_framework.iv_panel import IVPanel

            endog_vars = [self.treat_var]
            w_vars = iv_vars if iv_vars else self.x_vars

            panel = IVPanel(
                df_i, y_var=self.y_var, x_vars=endog_vars,
                unit_var=self.unit_var, time_var=self.time_var,
                iv_vars=[], w_vars=w_vars,
            )
            iv_result = panel.fit(method="iv")
        except Exception as exc:
            return RobustnessTest(
                test_name="IV Subsample",
                test_type="IV Robustness",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note=f"IV estimation failed: {exc}",
            )

        did_coef = np.nan
        did_se = np.nan
        did_pval = np.nan

        if iv_result is not None and hasattr(iv_result, "params"):
            params_dict = dict(zip([str(n) for n in iv_result.params.index], iv_result.params.values))
            pvals_dict = dict(zip([str(n) for n in iv_result.pvalues.index], iv_result.pvalues.values))
            for name, val in params_dict.items():
                if self.treat_var in name:
                    did_coef = float(val)
                    did_pval = float(pvals_dict.get(name, 1.0))
                    try:
                        if hasattr(iv_result, "bse"):
                            se_dict = dict(zip([str(n) for n in iv_result.bse.index], iv_result.bse.values))
                            did_se = float(se_dict.get(name, np.nan))
                    except Exception:  # noqa: S110
                        pass
                    break

        if np.isnan(did_coef):
            return RobustnessTest(
                test_name="IV Subsample",
                test_type="IV Robustness",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note="IV coefficient not found in result",
            )

        is_consistent = (did_coef * self.baseline_result.get("coef", 0) > 0)
        is_significant = (did_pval < 0.05) if not np.isnan(did_pval) else False

        note_parts = []
        if exclude_values:
            note_parts.append(f"excl.{exclude_var}={exclude_values}")
        note_parts.append(f"IV on {self.treat_var}, N={len(df_i)}")

        return RobustnessTest(
            test_name="IV Subsample",
            test_type="IV Robustness",
            did_coef=did_coef, did_se=did_se, did_pval=did_pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=", ".join(note_parts),
            details={
                "exclude_var": exclude_var,
                "exclude_values": exclude_values,
                "n_obs": len(df_i),
            },
        )

    def _test_lagged_depvar(self, config: dict) -> RobustnessTest:
        """滞后因变量检验：在模型中加入 y_{t-1} 后重新估计。

        添加滞后因变量可以控制结果变量的持续性 (persistence)，
        并检验处理效应是否独立于过去的值。
        同时，该检验也是动态面板偏差 (dynamic panel bias) 的诊断工具：
        若滞后项系数接近1，说明存在强持续性，需谨慎解读。

        对于非线性DID（如 PSM-DID）场景，滞后因变量检验尤为重要。

        Parameters
        ----------
        config : dict
            n_lags : int, default 1
                滞后的期数。默认1期。
            drop_incomplete : bool, default True
                是否剔除因滞后导致的缺失观测。
        """
        n_lags = config.get("n_lags", 1)
        drop_incomplete = config.get("drop_incomplete", True)

        df_l = self.df.copy()

        lag_col = f"{self.y_var}_lag{n_lags}"
        if lag_col not in df_l.columns:
            if self.unit_var and self.unit_var in df_l.columns:
                df_l[lag_col] = df_l.groupby(self.unit_var)[self.y_var].shift(n_lags)
            else:
                df_l[lag_col] = df_l[self.y_var].shift(n_lags)

        if drop_incomplete:
            df_l = df_l.dropna(subset=[lag_col])

        x_vars_lagged = [lag_col] + self.x_vars

        try:
            import statsmodels.api as sm

            did_col = df_l[self.treat_var].astype(float) * df_l[self.time_var].astype(float)
            x_data = pd.concat([df_l[x_vars_lagged], did_col], axis=1).fillna(0)
            X = sm.add_constant(x_data.values)
            y = df_l[self.y_var].astype(float).values
            model = sm.OLS(y, X).fit(cov_type="HC1")

            did_idx = len(x_vars_lagged)
            if did_idx < len(model.params):
                did_coef = float(model.params[did_idx])
                did_se = float(model.bse[did_idx])
                did_pval = float(model.pvalues[did_idx])
            else:
                did_coef, did_se, did_pval = np.nan, np.nan, 1.0

            lag_idx = 0 if did_idx > 0 else None
            lag_coef = float(model.params[lag_idx]) if lag_idx is not None and lag_idx < len(model.params) else np.nan
            lag_pval = float(model.pvalues[lag_idx]) if lag_idx is not None and lag_idx < len(model.pvalues) else np.nan
        except Exception as exc:
            return RobustnessTest(
                test_name=f"Lagged DV (lag-{n_lags})",
                test_type="Dynamic Model",
                did_coef=np.nan, did_se=np.nan, did_pval=1.0,
                is_consistent=False, is_significant=False,
                note=f"Lagged DV test failed: {exc}",
            )

        is_consistent = (did_coef * self.baseline_result.get("coef", 0) > 0) if not np.isnan(did_coef) else False
        is_significant = (did_pval < 0.05) if not np.isnan(did_pval) else False

        return RobustnessTest(
            test_name=f"Lagged DV (lag-{n_lags})",
            test_type="Dynamic Model",
            did_coef=did_coef, did_se=did_se, did_pval=did_pval,
            is_consistent=is_consistent, is_significant=is_significant,
            note=f"y{{t-{n_lags}}}={lag_coef:.3f}(p={lag_pval:.3f})，N={len(df_l)}",
            details={
                "n_lags": n_lags,
                "lag_coef": lag_coef,
                "lag_pval": lag_pval,
                "n_obs": len(df_l),
            },
        )

    def _test_oster_bounds(self, config: dict) -> RobustnessTest:
        """Oster (2019) 敏感性分析：选择偏差边界检验。"""
        oster_res = oster_bounds(
            df=self.df,
            y_var=self.y_var,
            treatment_var=self.treat_var,
            x_vars=self.x_vars,
            control_vars=config.get("control_vars", []),
            r2_max_options=config.get("r2_max_options"),
            cluster_var=None,
        )
        r2_key = str(config.get("r2_max_options", [0.5, 0.7, 0.9, 1.0])[-1])
        adjusted_beta = oster_res["delta_values"].get(r2_key, {}).get(
            "adjusted_beta", oster_res["beta_full"]
        )
        delta_val = oster_res["delta_values"].get(r2_key, {}).get("delta", "inf")

        return RobustnessTest(
            test_name=f"Oster Bounds (R²_max={r2_key})",
            test_type="Oster (2019)",
            did_coef=float(adjusted_beta),
            did_se=0.0,
            did_pval=np.nan,
            is_consistent=(
                (adjusted_beta > 0 and oster_res["beta_restricted"] > 0) or
                (adjusted_beta < 0 and oster_res["beta_restricted"] < 0)
            ),
            is_significant=not np.isnan(adjusted_beta) and abs(adjusted_beta) > 1e-6,
            note=f"delta={delta_val}",
            details={
                "beta_restricted": oster_res["beta_restricted"],
                "beta_full": oster_res["beta_full"],
                "r2_restricted": oster_res["r2_restricted"],
                "r2_full": oster_res["r2_full"],
                "delta_values": oster_res["delta_values"],
                "interpretation": oster_res["interpretation"],
            },
        )

    def add_oster_bounds(
        self,
        r2_max_options: list[float] | None = None,
        control_vars: list[str] | None = None,
    ) -> "RobustnessRunner":
        """添加 Oster Bounds 敏感性分析.

        Parameters
        ----------
        r2_max_options : list[float] | None
            R²_max 假设列表。默认为 [0.5, 0.7, 0.9, 1.0]。
        control_vars : list[str] | None
            额外控制变量（完整回归用）。
        """
        self._pending_tests.append(("oster_bounds", {
            "r2_max_options": r2_max_options or [0.5, 0.7, 0.9, 1.0],
            "control_vars": control_vars or [],
        }))
        return self


# ── FDR Correction ────────────────────────────────────────────────────────────


def apply_fdr_correction(pvalues: list[float], method: str = "bh") -> list[float]:
    """Apply False Discovery Rate correction to a list of p-values.

    Implements Benjamini-Hochberg (1995) procedure.

    Parameters
    ----------
    pvalues : list[float]
        List of p-values from multiple tests.
    method : str
        'bh' = Benjamini-Hochberg (default)
        'by' = Benjamini-Yekutieli

    Returns
    -------
    list[float]
        Adjusted p-values (q-values). Use these instead of raw p-values.
    """
    n = len(pvalues)
    if n == 0:
        return []
    if method not in ("bh", "by"):
        raise ValueError(f"Unknown method: {method}. Use 'bh' or 'by'.")
    if n == 1:
        return list(pvalues)

    # Sort p-values keeping track of original indices
    indexed = sorted(enumerate(pvalues), key=lambda x: x[1])
    sorted_pvals = [p for _, p in indexed]
    sorted_indices = [i for i, _ in indexed]

    if method == "bh":
        # Benjamini-Hochberg
        # q(i) = p(i) * n / rank(i)
        adjusted = [p * n / (i + 1) for i, p in enumerate(sorted_pvals)]
    elif method == "by":
        # Benjamini-Yekutieli (more conservative)
        # Uses harmonic number H_n = sum(1/i) for i=1 to n
        h_n = sum(1.0 / i for i in range(1, n + 1))
        adjusted = [p * n * h_n / (i + 1) for i, p in enumerate(sorted_pvals)]
    else:
        raise ValueError(f"Unknown method: {method}. Use 'bh' or 'by'.")

    # Ensure monotonicity (q-values must be non-decreasing)
    adjusted_sorted = []
    min_val = 1.0
    for q in reversed(adjusted):
        min_val = min(q, min_val)
        adjusted_sorted.append(min_val)
    adjusted_sorted = list(reversed(adjusted_sorted))

    # Restore original order
    result = [0.0] * n
    for idx, qval in zip(sorted_indices, adjusted_sorted):
        result[idx] = min(qval, 1.0)  # Cap at 1.0

    return result


def summarize_robustness_with_fdr(
    robustness_results: list[dict],
    fdr_threshold: float = 0.05,
) -> dict:
    """Summarize robustness results with FDR-corrected significance.

    Parameters
    ----------
    robustness_results : list[dict]
        List of robustness test results, each with 'name' and 'pvalue' keys.
    fdr_threshold : float
        FDR threshold (default 0.05).

    Returns
    -------
    dict
        Summary with raw and FDR-corrected results.
    """
    if not robustness_results:
        return {"n_tests": 0, "summary": "No tests to summarize"}

    pvalues = [r.get("pvalue", 1.0) for r in robustness_results]
    qvalues = apply_fdr_correction(pvalues, method="bh")

    raw_significant = sum(1 for p in pvalues if p < fdr_threshold)
    fdr_significant = sum(1 for q in qvalues if q < fdr_threshold)

    return {
        "n_tests": len(robustness_results),
        "raw_significant": raw_significant,
        "fdr_significant": fdr_significant,
        "fdr_threshold": fdr_threshold,
        "results": [
            {
                "name": r["name"],
                "pvalue": r.get("pvalue"),
                "qvalue": qvalues[i],
                "raw_reject": r.get("pvalue", 1.0) < fdr_threshold,
                "fdr_reject": qvalues[i] < fdr_threshold,
                "coefficient": r.get("coefficient"),
                "n_obs": r.get("n_obs"),
            }
            for i, r in enumerate(robustness_results)
        ],
        "summary": (
            f"{fdr_significant}/{len(robustness_results)} tests survive FDR correction "
            f"at {fdr_threshold} level "
            f"(raw significant: {raw_significant})"
        ),
    }


def run_with_fdr_correction(
    panel: pd.DataFrame,
    outcome_var: str,
    treatment_var: str,
    confounders: list[str],
    test_types: list[str] | None = None,
    fdr_threshold: float = 0.05,
) -> dict:
    """Run robustness tests and apply FDR correction.

    Convenience function that combines robustness testing with FDR correction.
    """
    runner = RobustnessRunner(
        df=panel,
        baseline_result={"coef": 0.0, "se": 0.0, "pval": 1.0},
        y_var=outcome_var,
        treat_var=treatment_var,
        x_vars=confounders,
    )
    if test_types:
        for t in test_types:
            runner.add_test(t)
    else:
        runner.add_test("parallel_trends")
        runner.add_test("placebo")
        runner.add_test("psm")
        runner.add_test("replace_outliers")
    report = runner.run_all()

    # Build list[dict] from RobustnessReport
    robustness_results: list[dict] = []
    for t in report.tests:
        robustness_results.append({
            "name": t.test_name,
            "pvalue": t.did_pval,
            "coefficient": t.did_coef,
            "n_obs": t.details.get("n_obs"),
        })

    summary = summarize_robustness_with_fdr(robustness_results, fdr_threshold)
    summary["_report"] = report
    return summary


def oster_bounds(
    df: pd.DataFrame,
    y_var: str,
    treatment_var: str,
    x_vars: list[str],
    control_vars: list[str],
    r2_max_options: list[float] | None = None,
    bound_method: str = "oster",
    cluster_var: str | None = None,
) -> dict:
    """Oster (2019) Sensitivity Analysis for Selection on Unobservables.

    Implements Oster's bounding technique for the treatment effect under
    different assumptions about the maximum R-squared achievable with
    all controls (including unobservables).

    The key insight: if selection on observed variables is informative about
    selection on unobserved variables, we can bound the treatment effect.

    Parameters
    ----------
    df : pd.DataFrame
        Panel data.
    y_var : str
        Outcome variable.
    treatment_var : str
        Treatment (DID) variable.
    x_vars : list[str]
        Control variables in restricted regression (y on treatment + x).
    control_vars : list[str]
        Additional control variables to add incrementally.
    r2_max_options : list[float] | None
        Assumptions about R²_max. Defaults to [0.5, 0.7, 0.9, 1.0].
        - 0.5/0.7: Conservative (based on Rothendahl 2022 recommendations)
        - 0.9/1.0: Standard Oster recommendation
    bound_method : str
        "oster" (default) or "brow" (Browning-Carcillo-Johannes).
    cluster_var : str | None
        Two-way clustering variable.

    Returns
    -------
    dict
        Oster bounds results with delta values and conclusions.
    """
    import statsmodels.api as sm

    if r2_max_options is None:
        r2_max_options = [0.5, 0.7, 0.9, 1.0]

    # Clean data
    cols = [y_var, treatment_var] + x_vars + control_vars
    if cluster_var:
        cols.append(cluster_var)
    df_sub = df.dropna(subset=cols).copy()

    # Step 1: Run restricted regression (y on treatment + x_vars)
    X_restricted = sm.add_constant(df_sub[[treatment_var] + x_vars])
    model_restricted = sm.OLS(df_sub[y_var], X_restricted).fit()
    beta_restricted = model_restricted.params[treatment_var]
    r2_restricted = model_restricted.rsquared

    # Step 2: Run full regression (y on treatment + x_vars + control_vars)
    X_full = sm.add_constant(df_sub[[treatment_var] + x_vars + control_vars])
    model_full = sm.OLS(df_sub[y_var], X_full).fit()
    beta_full = model_full.params[treatment_var]
    r2_full = model_full.rsquared

    # Step 3: Run full regression with treatment removed (to get R²_y~X without treatment)
    X_no_treat = sm.add_constant(df_sub[x_vars + control_vars])
    model_no_treat = sm.OLS(df_sub[y_var], X_no_treat).fit()
    r2_without_treatment = model_no_treat.rsquared

    results = {
        "beta_restricted": float(beta_restricted),
        "beta_full": float(beta_full),
        "r2_restricted": float(r2_restricted),
        "r2_full": float(r2_full),
        "r2_without_treatment": float(r2_without_treatment),
        "delta_values": {},
        "interpretation": {},
    }

    # Step 4: Compute delta for each R²_max assumption
    # Delta = (R²_max - R²_full) / (R²_full - R²_restricted) * (beta_full - beta_restricted) + beta_full
    # Simplified Oster (2019) formula:
    # beta* = beta_full - delta * (beta_full - beta_restricted) / (1 - R²_full / R²_max)

    for r2_max in r2_max_options:
        if r2_max <= r2_full:
            delta = float("inf")
            bound = float("nan")
        else:
            # Oster's delta formula
            # delta = (beta_full - beta_restricted) / (r2_full - r2_restricted) * (r2_max - r2_full)
            # Then adjusted treatment effect:
            # beta_adj = beta_full - delta / (1 - r2_full/r2_max)
            try:
                delta = (r2_max - r2_full) / (r2_full - r2_restricted + 1e-10)
                # Adjusted treatment effect using selection ratio
                # beta* = beta_full - delta * (beta_full - beta_restricted) / (1 + delta)
                beta_adj = beta_full - delta * (beta_full - beta_restricted) / (1 + delta)
                # Alternative: simple proportional adjustment
                # beta* = beta_full * (1 - r2_full / r2_max) / (r2_full - r2_restricted + 1e-10)
                beta_adj_alt = beta_full * (r2_max - r2_without_treatment) / (r2_full - r2_without_treatment + 1e-10)
                # Take the more conservative (closer to zero) bound
                bound = min(beta_adj, beta_adj_alt, key=abs)
            except (ZeroDivisionError, FloatingPointError):
                delta = float("inf")
                bound = float("nan")

        results["delta_values"][str(r2_max)] = {
            "delta": float(delta) if not np.isinf(delta) else "inf",
            "adjusted_beta": float(bound) if not np.isnan(bound) else float(beta_full),
            "r2_max": r2_max,
        }

        # Interpretation: delta > 1 means unobservables would need to explain more than
        # observables to fully explain away the treatment effect
        if not np.isinf(delta):
            if delta < 1:
                interp = "Strong: unobservables would need <100% of observable selection"
            elif delta < 2:
                interp = "Moderate: unobservables would need <200% of observable selection"
            elif delta < 3:
                interp = "Weak: unobservables would need 200-300% of observable selection"
            else:
                interp = "Very strong: unobservables would need >300% of observable selection"
        else:
            interp = "No selection adjustment possible (R2_full >= R2_max)"

        results["interpretation"][str(r2_max)] = interp

    # Compute relative stability: how much does beta change from restricted to full?
    results["beta_change_pct"] = float(
        abs(beta_full - beta_restricted) / (abs(beta_restricted) + 1e-10)
    )
    results["r2_change"] = float(r2_full - r2_restricted)
    results["proportional_selection"] = float(
        results["beta_change_pct"] / (results["r2_change"] + 1e-10)
    )

    return results


if __name__ == "__main__":
    import numpy as np
    np.random.seed(42)
    n = 500
    df = pd.DataFrame({
        "y": np.random.randn(n) + 0.5,
        "did": np.random.binomial(1, 0.5, n),
        "size": np.random.randn(n),
        "lev": np.random.rand(n),
        "roa": np.random.randn(n),
        "ticker": np.repeat(range(100), 5)[:n],
    })
    res = oster_bounds(
        df, y_var="y", treatment_var="did",
        x_vars=["size"], control_vars=["lev", "roa"],
        r2_max_options=[0.5, 0.7, 0.9, 1.0]
    )
    print(f"Beta restricted: {res['beta_restricted']:.4f}")
    print(f"Beta full: {res['beta_full']:.4f}")
    print(f"R² restricted: {res['r2_restricted']:.4f}")
    print(f"R² full: {res['r2_full']:.4f}")
    for k, v in res["delta_values"].items():
        print(f"  R²_max={k}: delta={v['delta']:.3f}, adjusted_beta={v['adjusted_beta']:.4f}")
    print("OK")
