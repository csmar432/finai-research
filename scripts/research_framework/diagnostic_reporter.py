"""DiagnosticReporter: 诊断结果自动决策引擎。

将所有诊断检验结果统一汇总，输出 PASS / WARN / FAIL 标记及自动决策建议。

用法：
    from scripts.research_framework.diagnostic_reporter import DiagnosticReporter
    reporter = DiagnosticReporter(regression_result)
    reporter.add_test("vif", vif_result)
    reporter.add_test("parallel_trends", pt_result)
    report = reporter.generate()
    print(report.to_latex())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

__all__ = [
    "DiagnosticDecision",
    "DiagnosticCheck",
    "DiagnosticReport",
    "DiagnosticReporter",
]

_log = logging.getLogger("diagnostic_reporter")
_log.setLevel(logging.INFO)


class DiagnosticDecision(str, Enum):
    PASS = "PASS"      # 诊断通过
    WARN = "WARN"      # 警告（边缘）
    FAIL = "FAIL"      # 诊断失败


@dataclass
class DiagnosticCheck:
    """单个诊断检验项。"""

    name: str          # 检验名称（英文）
    name_zh: str       # 检验名称（中文）
    category: str      # 类别
    decision: DiagnosticDecision
    value: float       # 检验统计量值
    threshold: str     # 阈值说明
    pval: float | None = None
    recommendation: str = ""  # 决策建议
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "name_zh": self.name_zh,
            "category": self.category,
            "decision": self.decision.value,
            "value": self.value,
            "threshold": self.threshold,
            "pval": self.pval,
            "recommendation": self.recommendation,
        }


@dataclass
class DiagnosticReport:
    """综合诊断报告。"""

    checks: list[DiagnosticCheck] = field(default_factory=list)
    baseline: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def add(self, check: DiagnosticCheck) -> None:
        self.checks.append(check)

    @property
    def n_pass(self) -> int:
        return sum(1 for c in self.checks if c.decision == DiagnosticDecision.PASS)

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.decision == DiagnosticDecision.WARN)

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.decision == DiagnosticDecision.FAIL)

    @property
    def overall(self) -> DiagnosticDecision:
        if self.n_fail > 0:
            return DiagnosticDecision.FAIL
        elif self.n_warn > 0:
            return DiagnosticDecision.WARN
        return DiagnosticDecision.PASS

    def to_dataframe(self) -> pd.DataFrame:
        """DataFrame 汇总表格。"""
        rows = []
        for c in self.checks:
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(c.decision.value, "?")
            rows.append({
                "类别": c.category,
                "检验": c.name_zh,
                "结果": icon,
                "数值": f"{c.value:.4f}" if isinstance(c.value, float) else str(c.value),
                "阈值": c.threshold,
                "p值": f"{c.pval:.4f}" if c.pval is not None else "—",
                "决策": c.decision.value,
                "建议": c.recommendation,
            })
        return pd.DataFrame(rows)

    def to_latex(self) -> str:
        """生成 LaTeX 诊断报告表格。"""
        icon_map = {"PASS": "\\color{green}\\checkmark",
                    "WARN": "\\color{orange}\\textbullet",
                    "FAIL": "\\color{red}\\textbf{X}"}
        lines = [
            "\\begin{longtable}{p{3cm}p{3.5cm}c>{\\centering}p{1.5cm}>{\\centering}p{2cm}>{\\centering}p{4cm}}",
            "\\caption{Diagnostic Report} \\label{tab:diagnostics}\\\\",
            "\\toprule",
            "\\textbf{Category} & \\textbf{Test} & \\textbf{Decision} & \\textbf{Value} & \\textbf{p-value} & \\textbf{Recommendation} \\\\",
            "\\midrule",
            "\\endfirsthead",
            "\\midrule",
            "\\caption*{(Continued)} \\\\",
            "\\toprule",
            "\\textbf{Category} & \\textbf{Test} & \\textbf{Decision} & \\textbf{Value} & \\textbf{p-value} & \\textbf{Recommendation} \\\\",
            "\\midrule",
            "\\endhead",
            "\\bottomrule",
            "\\endfoot",
        ]
        for c in self.checks:
            icon = icon_map.get(c.decision.value, "?")
            val_str = f"{c.value:.4f}" if isinstance(c.value, float) else str(c.value)
            pval_str = f"{c.pval:.4f}" if c.pval is not None else "—"
            lines.append(
                r"\addlinespace"
                rf"    {c.category} & {c.name_zh} & {icon} & "
                f"{val_str} & {pval_str} & {c.recommendation} \\"
            )
        lines.append("\\end{longtable}")
        return "\n".join(lines)

    def summary_text(self) -> str:
        """文本格式汇总。"""
        overall_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(self.overall.value, "?")
        parts = [
            f"## 诊断报告总评：{overall_icon} {self.overall.value}",
            f"通过 {self.n_pass} | 警告 {self.n_warn} | 失败 {self.n_fail}",
            "",
        ]
        for c in self.checks:
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(c.decision.value, "?")
            pval_str = f"p={c.pval:.4f}" if c.pval is not None else ""
            parts.append(f"{icon} [{c.category}] {c.name_zh}: {c.value:.4f} {pval_str}")
            parts.append(f"   建议: {c.recommendation}")
        return "\n".join(parts)


class DiagnosticReporter:
    """诊断结果自动决策引擎。"""

    def __init__(self, model_name: str = "", baseline: dict | None = None):
        self.model_name = model_name
        self.baseline = baseline or {}
        self._checks: list[DiagnosticCheck] = []
        self._metadata: dict = {}

    def add(self, check: DiagnosticCheck) -> "DiagnosticReporter":
        """链式添加诊断项。"""
        self._checks.append(check)
        return self

    def add_check(
        self,
        name: str,
        name_zh: str,
        category: str,
        value: float,
        threshold: str,
        pval: float | None = None,
        decision: DiagnosticDecision | None = None,
        recommendation: str = "",
        details: dict | None = None,
        **_kwargs,
    ) -> "DiagnosticReporter":
        """直接添加诊断项（无需手动创建 dataclass）。"""
        if decision is None:
            decision = self._auto_decide(name, value, pval)
        check = DiagnosticCheck(
            name=name,
            name_zh=name_zh,
            category=category,
            decision=decision,
            value=value,
            threshold=threshold,
            pval=pval,
            recommendation=recommendation,
            details=details or {},
        )
        self._checks.append(check)
        return self

    def _auto_decide(self, name: str, value: float, pval: float | None) -> DiagnosticDecision:
        """根据检验名称和值自动判断 PASS/WARN/FAIL。"""
        name_lower = name.lower()

        # VIF（多重共线性）
        if "vif" in name_lower:
            if value < 5:
                return DiagnosticDecision.PASS
            elif value < 10:
                return DiagnosticDecision.WARN
            else:
                return DiagnosticDecision.FAIL

        # Moran I（空间自相关）
        if "moran" in name_lower:
            if pval is not None and pval < 0.05:
                return DiagnosticDecision.FAIL
            return DiagnosticDecision.PASS

        # Breusch-Pagan / White（异方差）
        if any(x in name_lower for x in ["breusch", "white", "heterosk"]):
            if pval is not None and pval < 0.01:
                return DiagnosticDecision.FAIL
            elif pval is not None and pval < 0.05:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.PASS

        # Durbin-Watson（自相关）
        if "durbin" in name_lower or "dwatson" in name_lower:
            if 1.5 < value < 2.5:
                return DiagnosticDecision.PASS
            elif 1.0 < value < 3.0:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        # Shapiro-Wilk / Jarque-Bera（正态性）
        if any(x in name_lower for x in ["shapiro", "jarque", "normality"]):
            if pval is not None and pval < 0.01:
                return DiagnosticDecision.FAIL
            elif pval is not None and pval < 0.05:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.PASS

        # 平行趋势（p值越高越好）
        if "parallel" in name_lower or "trend" in name_lower:
            if pval is not None and pval > 0.1:
                return DiagnosticDecision.PASS
            elif pval is not None and pval > 0.05:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        # 安慰剂检验（p值应该不显著）
        if "placebo" in name_lower or "placebo" in name_lower:
            if pval is not None and pval > 0.1:
                return DiagnosticDecision.PASS
            elif pval is not None and pval > 0.05:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        # Honest DiD breakdown
        if "honest" in name_lower or "rr" in name_lower:
            if value > 2 * abs(self.baseline.get("coef", 1)):
                return DiagnosticDecision.PASS
            elif value > abs(self.baseline.get("coef", 1)):
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        # McCrary 密度检验
        if "mccrary" in name_lower or "density" in name_lower:
            if pval is not None and pval > 0.1:
                return DiagnosticDecision.PASS
            return DiagnosticDecision.FAIL

        # LR / Wald 检验
        if "lr" in name_lower or "wald" in name_lower:
            if pval is not None and pval < 0.05:
                return DiagnosticDecision.PASS
            elif pval is not None and pval < 0.1:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        # F统计量（模型整体显著性）
        if "f_stat" in name_lower or "fstat" in name_lower:
            if pval is not None and pval < 0.01:
                return DiagnosticDecision.PASS
            elif pval is not None and pval < 0.05:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        # R²
        if "r2" in name_lower or "rsquared" in name_lower:
            if value > 0.3:
                return DiagnosticDecision.PASS
            elif value > 0.1:
                return DiagnosticDecision.WARN
            return DiagnosticDecision.FAIL

        return DiagnosticDecision.WARN

    def add_vif(self, vif_dict: dict[str, float]) -> "DiagnosticReporter":
        """批量添加 VIF 检验结果。"""
        for var, vif in vif_dict.items():
            threshold = "VIF < 5 (PASS), 5-10 (WARN), > 10 (FAIL)"
            if vif < 5:
                rec = f"变量 {var} 无共线性问题"
            elif vif < 10:
                rec = f"变量 {var} 存在中等共线性，建议关注"
            else:
                rec = f"变量 {var} 共线性严重（VIF={vif:.1f}），建议移除或合并"
            self.add_check(
                name=f"vif_{var}", name_zh=f"VIF ({var})",
                category="D. 多重共线性",
                value=vif, threshold=threshold,
                decision=self._auto_decide("vif", vif, None),
                recommendation=rec,
            )
        return self

    def add_normality(self, name: str, stat: float, pval: float) -> "DiagnosticReporter":
        """添加正态性检验。"""
        threshold = "p > 0.05 (PASS)"
        rec = "残差服从正态分布" if pval > 0.05 else "残差不服从正态分布，建议使用稳健标准误"
        self.add_check(
            name=f"normality_{name}", name_zh=f"正态性检验 ({name})",
            category="D. 多重共线性",
            value=stat, threshold=threshold, pval=pval,
            decision=self._auto_decide(f"normality_{name}", stat, pval),
            recommendation=rec,
        )
        return self

    def add_heterosk(self, name: str, stat: float, pval: float) -> "DiagnosticReporter":
        """添加异方差检验。"""
        threshold = "p > 0.05 (PASS, 无异方差)"
        rec = "无异方差问题" if pval > 0.05 else f"存在异方差（p={pval:.4f}），建议使用稳健标准误"
        self.add_check(
            name=f"heterosk_{name}", name_zh=f"异方差检验 ({name})",
            category="B. 异方差与自相关",
            value=stat, threshold=threshold, pval=pval,
            decision=self._auto_decide(f"heterosk_{name}", stat, pval),
            recommendation=rec,
        )
        return self

    def add_autocorr(self, dw_stat: float) -> "DiagnosticReporter":
        """添加自相关检验。"""
        threshold = "DW ∈ [1.5, 2.5] (PASS)"
        rec = "无自相关问题" if 1.5 < dw_stat < 2.5 else f"DW={dw_stat:.3f}，可能存在自相关，建议使用聚类SE"
        self.add_check(
            name="durbin_watson", name_zh="Durbin-Watson 自相关检验",
            category="B. 异方差与自相关",
            value=dw_stat, threshold=threshold,
            decision=self._auto_decide("durbin_watson", dw_stat, None),
            recommendation=rec,
        )
        return self

    def add_moran_i(self, i_stat: float, pval: float) -> "DiagnosticReporter":
        """添加 Moran I 空间自相关检验。"""
        threshold = "p > 0.05 (PASS, 无空间自相关)"
        rec = "残差无空间自相关" if pval > 0.05 else f"存在空间自相关（I={i_stat:.4f}, p={pval:.4f}），建议使用空间回归"
        self.add_check(
            name="moran_i", name_zh="Moran I 空间自相关检验",
            category="G. 数据质量",
            value=i_stat, threshold=threshold, pval=pval,
            decision=self._auto_decide("moran_i", i_stat, pval),
            recommendation=rec,
        )
        return self

    def add_parallel_trends(self, f_stat: float, pval: float) -> "DiagnosticReporter":
        """添加平行趋势检验。"""
        threshold = "p > 0.05 (PASS, 平行趋势成立)"
        rec = "平行趋势成立，基准DID估计可靠" if pval > 0.05 else f"平行趋势不成立（p={pval:.4f}），建议使用合成DID或三重差分"
        self.add_check(
            name="parallel_trends", name_zh="平行趋势检验",
            category="A. 平行趋势与预处理",
            value=f_stat, threshold=threshold, pval=pval,
            decision=self._auto_decide("parallel_trends", f_stat, pval),
            recommendation=rec,
        )
        return self

    def add_placebo(self, stat: float, pval: float) -> "DiagnosticReporter":
        """添加安慰剂检验。"""
        threshold = "p > 0.1 (PASS, 安慰剂效应不显著)"
        rec = "安慰剂效应不显著，处理效应真实" if pval > 0.1 else f"安慰剂效应显著（p={pval:.4f}），结果可能虚假"
        self.add_check(
            name="placebo_test", name_zh="安慰剂检验",
            category="A. 平行趋势与预处理",
            value=stat, threshold=threshold, pval=pval,
            decision=self._auto_decide("placebo", stat, pval),
            recommendation=rec,
        )
        return self

    def add_mccrary(self, stat: float, pval: float) -> "DiagnosticReporter":
        """添加 McCrary 密度检验。"""
        threshold = "p > 0.1 (PASS, 无排序)"
        rec = "断点处无排序，处理分配是连续的" if pval > 0.1 else f"存在排序（McCrary p={pval:.4f}），RDD设计可能被操纵"
        self.add_check(
            name="mccrary_density", name_zh="McCrary 密度检验",
            category="G. 数据质量",
            value=stat, threshold=threshold, pval=pval,
            decision=self._auto_decide("mccrary", stat, pval),
            recommendation=rec,
        )
        return self

    def add_spatial_lr(self, stat: float, pval: float, against: str) -> "DiagnosticReporter":
        """添加空间 LR 检验。"""
        threshold = "p < 0.05 (选择 SDM)"
        rec = f"SDM 优于 {against}（LR p={pval:.4f}），保留空间滞后项"
        self.add_check(
            name=f"lr_sdm_vs_{against}", name_zh=f"LR 检验 (SDM vs {against})",
            category="G. 数据质量",
            value=stat, threshold=threshold, pval=pval,
            decision=DiagnosticDecision.PASS if (pval is not None and pval < 0.05) else DiagnosticDecision.WARN,
            recommendation=rec,
        )
        return self

    def add_honest_did(self, breakdown: float) -> "DiagnosticReporter":
        """添加 Honest DiD breakdown 值。"""
        base = abs(self.baseline.get("coef", 1))
        threshold = f"breakdown > 2×|coef| = {2*base:.4f} (PASS)"
        rec = f"breakdown={breakdown:.4f}，在较大平行趋势违背下结果仍稳健"
        self.add_check(
            name="honest_did", name_zh="Honest DiD 敏感性分析",
            category="F. 推断稳健性",
            value=breakdown, threshold=threshold,
            decision=self._auto_decide("honest_did", breakdown, None),
            recommendation=rec,
        )
        return self

    def add_ar2(self, ar2_pval: float) -> "DiagnosticReporter":
        """添加 Arellano-Bond AR(2) 检验。"""
        threshold = "p > 0.05 (PASS, 残差无二阶自相关)"
        rec = "残差无二阶自相关，动态面板 GMM 估计有效" if ar2_pval > 0.05 else f"存在二阶自相关（AR(2) p={ar2_pval:.4f}），GMM 估计量不一致"
        self.add_check(
            name="ar2_test", name_zh="Arellano-Bond AR(2) 检验",
            category="C. 内生性与工具变量",
            value=ar2_pval, threshold=threshold, pval=ar2_pval,
            decision=DiagnosticDecision.PASS if ar2_pval > 0.05 else DiagnosticDecision.FAIL,
            recommendation=rec,
        )
        return self

    def add_weak_iv(
        self,
        stock_yogo_f: float | None = None,
        kp_f: float | None = None,
    ) -> "DiagnosticReporter":
        """Add weak instrument diagnostic for both Stock-Yogo and Kleibergen-Paap.

        Stock-Yogo F assumes homoskedasticity; Kleibergen-Paap does not.
        For financial data (almost always heteroskedastic), prefer KP-F.

        Args:
            stock_yogo_f: Stock-Yogo F-statistic (from linearmodels).
            kp_f: Kleibergen-Paap rk Wald F-statistic (heteroskedasticity-robust).
        """
        # ── Stock-Yogo F ────────────────────────────────────────────────
        if stock_yogo_f is not None:
            threshold = "F > 10 (PASS, assumes homoskedasticity)"
            rec = (
                f"工具变量强度足够（F={stock_yogo_f:.1f}）"
                if stock_yogo_f > 10
                else f"Stock-Yogo F={stock_yogo_f:.1f} < 10：弱工具变量，建议增加工具变量或使用 LIML"
            )
            self.add_check(
                name="weak_iv_stock_yogo",
                name_zh="弱工具变量检验 (Stock-Yogo F)",
                category="C. 内生性与工具变量",
                value=stock_yogo_f,
                threshold=threshold,
                decision=(
                    DiagnosticDecision.PASS
                    if stock_yogo_f > 10
                    else DiagnosticDecision.FAIL
                ),
                recommendation=rec,
            )

        # ── Kleibergen-Paap rk F ────────────────────────────────────────
        if kp_f is not None:
            threshold = "KP F > 10 (PASS, robust to heteroskedasticity)"
            rec = (
                f"工具变量强度足够（KP-F={kp_f:.1f}）"
                if kp_f > 10
                else f"KP-F={kp_f:.1f} < 10：弱工具变量，建议增加工具变量或使用 LIML"
            )
            self.add_check(
                name="weak_iv_kp",
                name_zh="弱工具变量检验 (Kleibergen-Paap rk F)",
                category="C. 内生性与工具变量",
                value=kp_f,
                threshold=threshold,
                decision=(
                    DiagnosticDecision.PASS if kp_f > 10 else DiagnosticDecision.FAIL
                ),
                recommendation=rec,
            )
        return self

    def add_two_way_clustering(
        self,
        cluster_vars: list[str],
        n_cl1: int,
        n_cl2: int,
        dof: int,
    ) -> "DiagnosticReporter":
        """Add two-way clustered SE diagnostic entry.

        Args:
            cluster_vars: Names of the two clustering dimensions detected.
            n_cl1: Number of clusters in dimension 1 (e.g., firms).
            n_cl2: Number of clusters in dimension 2 (e.g., years).
            dof: Degrees of freedom used for t-distribution inference.
        """
        has_firm = any("firm" in v.lower() or "ticker" in v.lower() for v in cluster_vars)
        has_year = any("year" in v.lower() or "time" in v.lower() for v in cluster_vars)

        if has_firm and has_year:
            note = f"Two-way clustered SE (firm × year), DOF = {dof}"
            rec = "使用双向聚类标准误 (firm × year)，同时控制组内相关和时序相关"
        else:
            note = f"Two-way clustered SE ({' × '.join(cluster_vars)}), DOF = {dof}"
            rec = f"使用双向聚类标准误 ({' × '.join(cluster_vars)})，推断更保守"

        self.add_check(
            name="two_way_clustered_se",
            name_zh=f"双向聚类标准误 ({' × '.join(cluster_vars)})",
            category="E. 推断方法",
            value=float(min(n_cl1, n_cl2)),
            threshold=f"G1={n_cl1}, G2={n_cl2}, DOF={dof}",
            decision=DiagnosticDecision.PASS,
            recommendation=rec,
            details={
                "note": note,
                "cluster_vars": cluster_vars,
                "n_cl1": n_cl1,
                "n_cl2": n_cl2,
                "dof": dof,
                "method": "Cameron-Gelbach-Miller (2011)",
                "reference": "Cameron, Gelbach & Miller (2011), REStud",
            },
        )
        return self

    def add_from_diagnostic(
        self,
        diag: dict,
        cluster_vars: list[str] | None = None,
    ) -> "DiagnosticReporter":
        """Auto-detect and add diagnostics from a regression diagnostic dict.

        Detects two-way clustering if 'cov_type' == 'two_way_clustered'.

        Args:
            diag: Diagnostic dict from RegressionEngine.did() or ols().
            cluster_vars: Optional list of cluster variable names for the note.
        """
        cov_type = diag.get("cov_type", "")

        if cov_type == "two_way_clustered":
            n_cl1 = diag.get("n_cl1", 0)
            n_cl2 = diag.get("n_cl2", 0)
            dof = diag.get("dof", 1)
            cvars = cluster_vars or [f"cluster1 (G={n_cl1})", f"cluster2 (G={n_cl2})"]
            self.add_two_way_clustering(cvars, n_cl1, n_cl2, dof)

        return self

    def generate(self) -> DiagnosticReport:
        """生成诊断报告。"""
        has_two_way = any(
            c.name == "two_way_clustered_se" for c in self._checks
        )
        report = DiagnosticReport(
            checks=self._checks,
            baseline=self.baseline,
            metadata={
                "model": self.model_name,
                "n_checks": len(self._checks),
                "two_way_clustered": has_two_way,
            },
        )
        _log.info(
            f"[DiagnosticReporter] Generated report: "
            f"PASS={report.n_pass} WARN={report.n_warn} FAIL={report.n_fail} "
            f"→ Overall: {report.overall.value}"
        )
        return report
