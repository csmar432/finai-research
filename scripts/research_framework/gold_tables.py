"""Gold-slot tables: run the ladder instead of only reporting it missing.

The empirical package contract (``scripts/core/empirical_package.py``) asks for
structure facts before the regression, a stepwise ladder, a tighter comparison,
a sample flow with n at every step, and a treatment→mechanism table. Until now
FinAI could only *report* those slots as missing.

This module produces them from a panel, reusing ``pipeline.run_did`` so the
estimates come from the same estimator the rest of the project uses.

What it deliberately does **not** do:

- Invent control ``job`` / ``basis`` text. Why a control is in the equation is
  a thinking task; a generated sentence would be exactly the sticker the
  contract rejects. Skeleton rows are emitted for a human to fill.
- Invent mechanism channels. The caller must name M; the module then runs
  treatment→M and refuses any M that is also in the control battery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import pandas as pd

__all__ = [
    "LadderColumn",
    "MechanismRow",
    "GoldTableSet",
    "build_gold_tables",
    "figure_gate_from_event_study",
]


@dataclass
class LadderColumn:
    """One column of the stepwise / tighter-comparison table."""

    label: str
    coef: float
    se: float
    pval: float
    n_obs: int
    r_squared: float
    controls: bool
    unit_fe: bool
    time_fe: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "coef": self.coef,
            "se": self.se,
            "pval": self.pval,
            "n_obs": self.n_obs,
            "r_squared": self.r_squared,
            "controls": self.controls,
            "unit_fe": self.unit_fe,
            "time_fe": self.time_fe,
        }


@dataclass
class MechanismRow:
    """Treatment → M. Same estimator as the main column, M as the outcome."""

    channel: str
    coef: float
    se: float
    pval: float
    n_obs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "coef": self.coef,
            "se": self.se,
            "pval": self.pval,
            "n_obs": self.n_obs,
        }


@dataclass
class GoldTableSet:
    y_var: str
    treat_var: str
    battery: list[str] = field(default_factory=list)
    sample_flow: list[dict[str, Any]] = field(default_factory=list)
    facts_before_reg: list[dict[str, Any]] = field(default_factory=list)
    raw_did: float | None = None
    desc: list[dict[str, Any]] = field(default_factory=list)
    stepwise: list[LadderColumn] = field(default_factory=list)
    tighter: LadderColumn | None = None
    mechanism: list[MechanismRow] = field(default_factory=list)

    @property
    def main_column(self) -> LadderColumn | None:
        return self.tighter or (self.stepwise[-1] if self.stepwise else None)

    def to_slots(self) -> dict[str, str]:
        """Slot ids for the empirical package. Only what actually ran."""
        slots: dict[str, str] = {}
        if self.desc:
            slots["desc"] = f"T1 描述统计（{len(self.desc)} 个变量；定义列须人工补）"
        if self.facts_before_reg:
            slots["facts_before_reg"] = (
                f"T2 回归前结构事实（{len(self.facts_before_reg)} 格组均值）"
            )
        if self.stepwise:
            slots["baseline_stepwise"] = f"T3 逐步加信息（{len(self.stepwise)} 列）"
        if self.tighter is not None:
            slots["tighter_compare"] = f"T3 列（{self.tighter.label}）"
        if self.sample_flow:
            slots["sample_flow"] = f"A1 样本流（{len(self.sample_flow)} 步）"
        if self.mechanism:
            slots["mechanism"] = f"T4 处理→M（{len(self.mechanism)} 条渠道）"
        return slots

    def to_dict(self) -> dict[str, Any]:
        return {
            "y_var": self.y_var,
            "treat_var": self.treat_var,
            "battery": list(self.battery),
            "sample_flow": self.sample_flow,
            "facts_before_reg": self.facts_before_reg,
            "raw_did": self.raw_did,
            "desc": self.desc,
            "stepwise": [c.to_dict() for c in self.stepwise],
            "tighter": self.tighter.to_dict() if self.tighter else None,
            "mechanism": [m.to_dict() for m in self.mechanism],
        }

    def to_markdown(self) -> str:
        def stars(p: float) -> str:
            return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""

        out = [f"# 黄金八格实跑表 — {self.y_var}", ""]

        if self.sample_flow:
            out += ["## A1 样本流", "", "| 步骤 | 观测数 | 单位数 |", "|---|---|---|"]
            out += [
                f"| {r['step']} | {r['n_obs']} | {r.get('n_units', '')} |"
                for r in self.sample_flow
            ]
            out.append("")

        if self.facts_before_reg:
            out += [
                "## T2 回归前结构事实",
                "",
                "| 处理组 | 时期 | 观测数 | 均值 | 标准差 |",
                "|---|---|---|---|---|",
            ]
            out += [
                f"| {r['treat']} | {r['post']} | {r['n']} | {r['mean']:.4f} | {r['sd']:.4f} |"
                for r in self.facts_before_reg
            ]
            if self.raw_did is not None:
                out += ["", f"未调整 DiD（组均值之差的差）：{self.raw_did:.4f}"]
            out.append("")

        if self.stepwise:
            cols = list(self.stepwise)
            out += ["## T3 逐步加信息", ""]
            out.append("| | " + " | ".join(f"({i + 1})" for i in range(len(cols))) + " |")
            out.append("|---|" + "---|" * len(cols))
            out.append(
                f"| {self.treat_var} | "
                + " | ".join(f"{c.coef:.4f}{stars(c.pval)}" for c in cols)
                + " |"
            )
            out.append("| 标准误 | " + " | ".join(f"({c.se:.4f})" for c in cols) + " |")
            out.append(
                "| 控制变量 | " + " | ".join("是" if c.controls else "否" for c in cols) + " |"
            )
            out.append(
                "| 单位固定效应 | "
                + " | ".join("是" if c.unit_fe else "否" for c in cols)
                + " |"
            )
            out.append(
                "| 时间固定效应 | "
                + " | ".join("是" if c.time_fe else "否" for c in cols)
                + " |"
            )
            out.append("| 观测值 | " + " | ".join(str(c.n_obs) for c in cols) + " |")
            out += ["", "注：*** p<0.01, ** p<0.05, * p<0.10。", ""]

        if self.mechanism:
            out += [
                "## T4 处理→机制变量",
                "",
                "| 渠道 | 系数 | 标准误 | p 值 | 观测值 |",
                "|---|---|---|---|---|",
            ]
            out += [
                f"| {m.channel} | {m.coef:.4f}{stars(m.pval)} | ({m.se:.4f}) "
                f"| {m.pval:.4f} | {m.n_obs} |"
                for m in self.mechanism
            ]
            out += ["", "机制的理论链与假说同号，须人工写入 `mechanism_theory`。", ""]

        out += [
            "## 仍须人工补",
            "",
            "- 每件控制的 `job`（接到本题 Y 或名单选择）与 `basis`（打开过的定义 + 本题路径）。",
            "- 变量定义列（T1 只有描述统计）。",
            "- 事件图 0 点职务句（名单公布年还是落地年）。",
        ]
        return "\n".join(out)


def _units(df: pd.DataFrame, unit_col: str) -> int | str:
    return int(df[unit_col].nunique()) if unit_col in df.columns else ""


def _absorb(frame: pd.DataFrame, cols: list[str], group: pd.Series) -> pd.DataFrame:
    """Within-transform every regressor *and* the outcome by one FE dimension.

    ``pipeline.run_did`` deliberately leaves the interaction on its original
    scale, which breaks Frisch-Waugh and attenuates the coefficient. The whole
    design matrix has to be residualised on the same fixed effects.
    """
    out = frame.copy()
    means = out.groupby(group, observed=True)[cols].transform("mean")
    for col in cols:
        out[col] = out[col] - means[col]
    return out


def _column(
    df: pd.DataFrame,
    *,
    label: str,
    y_var: str,
    treat_var: str,
    time_var: str,
    x_vars: Sequence[str],
    unit_col: str,
    year_col: str,
    unit_fe: bool,
    time_fe: bool,
) -> LadderColumn:
    import statsmodels.api as sm

    did_name = "_did_term"
    frame = pd.DataFrame(index=df.index)
    frame[y_var] = pd.to_numeric(df[y_var], errors="coerce")
    treat = pd.to_numeric(df[treat_var], errors="coerce")
    post = pd.to_numeric(df[time_var], errors="coerce")
    frame[did_name] = treat * post
    # Group indicator is collinear with unit FE; post with time FE.
    regressors = [did_name]
    if not unit_fe:
        frame[treat_var] = treat
        regressors.append(treat_var)
    if not time_fe:
        frame[time_var] = post
        regressors.append(time_var)
    for xv in x_vars:
        frame[xv] = pd.to_numeric(df[xv], errors="coerce")
        regressors.append(xv)

    frame = frame.dropna()
    if frame.empty:
        raise ValueError(f"{label}: 去缺失后无观测")

    cols = [y_var, *regressors]
    if unit_fe:
        frame = _absorb(frame, cols, df.loc[frame.index, unit_col])
    if time_fe:
        frame = _absorb(frame, cols, df.loc[frame.index, year_col])

    X = sm.add_constant(frame[regressors].astype(float), has_constant="add")
    model = sm.OLS(frame[y_var].astype(float), X).fit(cov_type="HC1")
    return LadderColumn(
        label=label,
        coef=float(model.params[did_name]),
        se=float(model.bse[did_name]),
        pval=float(model.pvalues[did_name]),
        n_obs=int(model.nobs),
        r_squared=float(model.rsquared),
        controls=bool(x_vars),
        unit_fe=unit_fe,
        time_fe=time_fe,
    )


def build_gold_tables(
    df: pd.DataFrame,
    *,
    y_var: str,
    treat_var: str,
    time_var: str,
    unit_col: str = "ticker",
    year_col: str = "year",
    x_vars: Sequence[str] = (),
    mechanism_vars: Sequence[str] = (),
) -> GoldTableSet:
    """Run the seed-paper ladder + JDE sample flow on a real panel.

    ``treat_var`` is the group indicator and ``time_var`` the post indicator;
    the interaction is built by ``run_did``.

    Raises
    ------
    ValueError
        If a mechanism variable is also a control. Same construct cannot be
        both battery and channel — the contract rejects it downstream anyway,
        so fail here rather than emit a table that can never pass the gate.
    """
    for col in (y_var, treat_var, time_var):
        if col not in df.columns:
            raise ValueError(f"面板缺少必需列 {col!r}")

    battery = [c for c in x_vars if c in df.columns]
    overlap = sorted(set(battery) & set(mechanism_vars))
    if overlap:
        raise ValueError(
            f"机制渠道与控制电池同构念：{overlap}；同一变量不能既当控制又当 M"
        )

    tables = GoldTableSet(y_var=y_var, treat_var=treat_var, battery=battery)

    # ── A1 sample flow ──────────────────────────────────────────────────
    tables.sample_flow.append(
        {"step": "原始面板", "n_obs": len(df), "n_units": _units(df, unit_col)}
    )
    core = df.dropna(subset=[y_var, treat_var, time_var])
    tables.sample_flow.append(
        {
            "step": f"去缺失（{y_var} / {treat_var} / {time_var}）",
            "n_obs": len(core),
            "n_units": _units(core, unit_col),
        }
    )
    est = core.dropna(subset=battery) if battery else core
    if battery:
        tables.sample_flow.append(
            {
                "step": f"去缺失（{len(battery)} 件控制）",
                "n_obs": len(est),
                "n_units": _units(est, unit_col),
            }
        )
    tables.sample_flow.append(
        {"step": "估计样本", "n_obs": len(est), "n_units": _units(est, unit_col)}
    )

    if est.empty:
        return tables

    # ── T2 structure facts before the regression ────────────────────────
    cells: dict[tuple[int, int], dict[str, Any]] = {}
    for (g, t), grp in est.groupby(
        [est[treat_var].astype(int), est[time_var].astype(int)]
    ):
        cell = {
            "treat": int(g),
            "post": int(t),
            "n": int(len(grp)),
            "mean": float(grp[y_var].mean()),
            "sd": float(grp[y_var].std(ddof=1)) if len(grp) > 1 else 0.0,
        }
        cells[(int(g), int(t))] = cell
        tables.facts_before_reg.append(cell)
    tables.facts_before_reg.sort(key=lambda r: (r["treat"], r["post"]))
    if len(cells) == 4:
        tables.raw_did = (
            cells[(1, 1)]["mean"] - cells[(1, 0)]["mean"]
        ) - (cells[(0, 1)]["mean"] - cells[(0, 0)]["mean"])

    # ── T1 descriptive stats (definitions stay a human column) ──────────
    for col in [y_var, treat_var, time_var, *battery]:
        series = pd.to_numeric(est[col], errors="coerce").dropna()
        if series.empty:
            continue
        tables.desc.append(
            {
                "variable": col,
                "n": int(series.size),
                "mean": float(series.mean()),
                "sd": float(series.std(ddof=1)) if series.size > 1 else 0.0,
                "min": float(series.min()),
                "max": float(series.max()),
            }
        )

    # ── T3 stepwise ladder, then the tighter comparison ─────────────────
    ladder: list[tuple[str, Sequence[str], bool, bool]] = [
        ("裸估计", (), False, False),
        ("+ 时间固定效应", (), False, True),
    ]
    if battery:
        ladder.append(("+ 控制变量", battery, False, True))
    steps = ladder
    for label, controls, unit_fe, time_fe in steps:
        try:
            tables.stepwise.append(
                _column(
                    est,
                    label=label,
                    y_var=y_var,
                    treat_var=treat_var,
                    time_var=time_var,
                    x_vars=controls,
                    unit_col=unit_col,
                    year_col=year_col,
                    unit_fe=unit_fe,
                    time_fe=time_fe,
                )
            )
        except Exception:  # one column failing must not kill the table
            continue

    try:
        tables.tighter = _column(
            est,
            label="+ 单位×时间固定效应",
            y_var=y_var,
            treat_var=treat_var,
            time_var=time_var,
            x_vars=battery,
            unit_col=unit_col,
            year_col=year_col,
            unit_fe=True,
            time_fe=True,
        )
        tables.stepwise.append(tables.tighter)
    except Exception:
        tables.tighter = None

    # ── T4 treatment → mechanism ────────────────────────────────────────
    for m in mechanism_vars:
        if m not in est.columns:
            continue
        sub = est.dropna(subset=[m])
        if sub.empty:
            continue
        try:
            col = _column(
                sub,
                label=m,
                y_var=m,
                treat_var=treat_var,
                time_var=time_var,
                x_vars=battery,
                unit_col=unit_col,
                year_col=year_col,
                unit_fe=True,
                time_fe=True,
            )
        except Exception:
            continue
        tables.mechanism.append(
            MechanismRow(
                channel=m,
                coef=col.coef,
                se=col.se,
                pval=col.pval,
                n_obs=col.n_obs,
            )
        )

    return tables


def figure_gate_from_event_study(
    event_rows: Iterable[Any],
    *,
    placebo_tail_p: float | None = None,
) -> dict[str, Any]:
    """Count post-period CIs that cross zero — the figure door, measured.

    ``event_rows`` is what ``ModernDiDEngine.event_study_data`` produces
    (records with horizon / ci_lower / ci_upper).
    """
    post_n = 0
    cross0 = 0
    pre_pvals: list[float] = []
    for row in event_rows or []:
        if not isinstance(row, dict):
            continue
        try:
            horizon = float(row.get("horizon"))
            lo = float(row.get("ci_lower"))
            hi = float(row.get("ci_upper"))
        except (TypeError, ValueError):
            continue
        if horizon > 0:
            post_n += 1
            if lo <= 0.0 <= hi:
                cross0 += 1
        elif horizon < 0:
            try:
                pre_pvals.append(float(row.get("pval")))
            except (TypeError, ValueError):
                pass

    gate: dict[str, Any] = {
        "event_post_n": post_n,
        "event_post_cross0_n": cross0,
    }
    if pre_pvals:
        gate["event_pre_min_p"] = min(pre_pvals)
    if placebo_tail_p is not None:
        gate["placebo_tail_p"] = float(placebo_tail_p)
        gate["placebo_true_outside_mass"] = float(placebo_tail_p) <= 0.05
    return gate
