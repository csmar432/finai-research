"""negative_result_handler.py — 负显著/弱显著结果处理器

当基准回归的核心处理效应不显著（或仅弱显著）时，实证研究**不应直接进入
论文写作**。本模块把「结果不显著后应该做什么」固化为一个可检查的决策门，
对应审计报告中的 A4/A5/A6/C2/E3：

  - A4 未实施现代 DID（CS / Sun-Abraham / Borusyak）
  - A5 缺机制分析
  - A6 缺空间溢出
  - C2 异质性分析不足
  - E3 负面结果被包装成中性发现，却未展开机制分化

【设计原则】
- 只诊断 + 给出必须补齐的清单，不臆造结果。
- 阈值可配置：p<0.05 显著；0.05≤p<0.10 弱显著；p≥0.10 不显著。
- 输出结构化 `NegativeResultVerdict`，供 pipeline 在写作前做硬门。

【用法】
    from scripts.research_framework.negative_result_handler import assess_result
    verdict = assess_result(
        baseline_p=0.804, baseline_coef=-0.26,
        did_type="twfe",
        has_mechanism=False, has_heterogeneity=False,
        has_spatial=False, has_modern_did=False,
    )
    if verdict.should_block_writing:
        print(verdict.render())
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── ANSI Colors ────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


# ── 显著性分级 ──────────────────────────────────────────────────────────────────

SIG_STRONG = "significant"        # p < 0.05
SIG_WEAK = "weak"                 # 0.05 <= p < 0.10
SIG_NULL = "insignificant"        # p >= 0.10


def classify_significance(
    p_value: float, *, strong: float = 0.05, weak: float = 0.10
) -> str:
    if p_value < strong:
        return SIG_STRONG
    if p_value < weak:
        return SIG_WEAK
    return SIG_NULL


# ── 决策结果 ────────────────────────────────────────────────────────────────────


@dataclass
class RequiredAction:
    code: str
    label: str
    rationale: str
    done: bool = False


@dataclass
class NegativeResultVerdict:
    significance: str
    baseline_p: float
    baseline_coef: float
    did_type: str
    should_block_writing: bool
    required_actions: list[RequiredAction] = field(default_factory=list)
    allowed_narratives: list[str] = field(default_factory=list)
    forbidden_narratives: list[str] = field(default_factory=list)
    summary_message: str = ""

    def missing_actions(self) -> list[RequiredAction]:
        return [a for a in self.required_actions if not a.done]

    def render(self) -> str:
        lines = []
        bar = "═" * 64
        lines.append(c(bar, CYAN))
        lines.append(c("  负显著结果处理器 · 决策报告", CYAN))
        lines.append(c(bar, CYAN))
        lines.append("")
        sig_label = {
            SIG_STRONG: c("显著 (p<0.05)", GREEN),
            SIG_WEAK: c("弱显著 (0.05≤p<0.10)", YELLOW),
            SIG_NULL: c("不显著 (p≥0.10)", RED),
        }[self.significance]
        lines.append(f"  基准处理效应: coef={self.baseline_coef:+.4f}, "
                     f"p={self.baseline_p:.3f} → {sig_label}")
        lines.append(f"  当前识别策略: {self.did_type}")
        lines.append("")

        missing = self.missing_actions()
        if missing:
            lines.append(c(f"  写作前必须补齐 {len(missing)} 项：", BOLD))
            for a in missing:
                lines.append(f"    {c('☐', RED)} [{a.code}] {a.label}")
                lines.append(f"        {c(a.rationale, DIM)}")
            lines.append("")
        done = [a for a in self.required_actions if a.done]
        if done:
            lines.append(c(f"  已完成 {len(done)} 项：", GREEN))
            for a in done:
                lines.append(f"    {c('☑', GREEN)} [{a.code}] {a.label}")
            lines.append("")

        if self.allowed_narratives:
            lines.append(c("  ✅ 可采用的论文叙事：", GREEN))
            for n in self.allowed_narratives:
                lines.append(f"    • {n}")
            lines.append("")
        if self.forbidden_narratives:
            lines.append(c("  ⛔ 禁止的论文叙事：", RED))
            for n in self.forbidden_narratives:
                lines.append(f"    • {n}")
            lines.append("")

        verdict = (
            c("❌ 阻止进入写作阶段", RED)
            if self.should_block_writing
            else c("✅ 可进入写作阶段", GREEN)
        )
        lines.append(f"  结论: {verdict}")
        lines.append(c("─" * 64, CYAN))
        return "\n".join(lines)


# ── 核心处理器 ──────────────────────────────────────────────────────────────────

# 现代 DID 估计器标识：只要不是这些就视为传统 TWFE
_MODERN_DID_TYPES = {
    "cs", "callaway", "callaway-santanna", "callaway_santanna",
    "sun-abraham", "sunabraham", "sun_abraham",
    "borusyak", "did_imputation", "gardner", "dcdh", "de_chaisemartin",
}


def _is_modern_did(did_type: str) -> bool:
    return did_type.strip().lower().replace(" ", "") in {
        t.replace(" ", "") for t in _MODERN_DID_TYPES
    }


class NegativeResultHandler:
    """负显著结果处理器。

    根据基准显著性 + 已完成的稳健性/机制/异质性/现代 DID 情况，
    判定是否允许进入写作阶段，并列出必须补齐的动作清单。
    """

    def __init__(
        self,
        *,
        baseline_p: float,
        baseline_coef: float,
        did_type: str = "twfe",
        is_staggered: bool = True,
        has_modern_did: bool = False,
        has_mechanism: bool = False,
        has_heterogeneity: bool = False,
        has_spatial: bool = False,
        has_placebo: bool = False,
        strong: float = 0.05,
        weak: float = 0.10,
    ) -> None:
        self.baseline_p = baseline_p
        self.baseline_coef = baseline_coef
        self.did_type = did_type
        self.is_staggered = is_staggered
        self.has_modern_did = has_modern_did or _is_modern_did(did_type)
        self.has_mechanism = has_mechanism
        self.has_heterogeneity = has_heterogeneity
        self.has_spatial = has_spatial
        self.has_placebo = has_placebo
        self.strong = strong
        self.weak = weak

    def assess(self) -> NegativeResultVerdict:
        sig = classify_significance(self.baseline_p, strong=self.strong, weak=self.weak)
        actions: list[RequiredAction] = []

        # 弱显著或不显著都要走强化流程；显著则仅提示常规稳健性。
        needs_escalation = sig in (SIG_WEAK, SIG_NULL)

        if needs_escalation:
            # A4: 交错处理必须上现代 DID
            if self.is_staggered:
                actions.append(
                    RequiredAction(
                        code="A4",
                        label="实施现代交错 DID（Callaway-Sant'Anna / Sun-Abraham / Borusyak）",
                        rationale="交错处理下传统 TWFE 有负权重偏误；平均效应不显著更需排除是估计量假象。",
                        done=self.has_modern_did,
                    )
                )
            # A5: 机制分析
            actions.append(
                RequiredAction(
                    code="A5",
                    label="补充机制分析（中介/机制变量回归，至少 2-3 条路径）",
                    rationale="负/弱结果的论文靠机制分解解释『为何平均效应被稀释』，否则无信息量。",
                    done=self.has_mechanism,
                )
            )
            # C2: 异质性
            actions.append(
                RequiredAction(
                    code="C2",
                    label="扩展异质性分析（分组/分位数/交互项）",
                    rationale="平均效应不显著可能是异质效应相互抵消；需展示子样本方向差异。",
                    done=self.has_heterogeneity,
                )
            )
            # A6: 空间溢出（仅在声明了空间假设时；此处作为建议项）
            actions.append(
                RequiredAction(
                    code="A6",
                    label="检验空间溢出（若研究设计含 SAR/SDM 或邻接暴露假设）",
                    rationale="政策的净效应可能通过溢出泄漏到对照组，导致平均效应被低估。",
                    done=self.has_spatial,
                )
            )
            # 安慰剂（识别可信度）
            actions.append(
                RequiredAction(
                    code="C5",
                    label="随机化安慰剂检验（打乱处理城市/年份 ≥500 次）",
                    rationale="不显著结论同样需要证明识别策略无系统性偏误。",
                    done=self.has_placebo,
                )
            )

        should_block = needs_escalation and any(not a.done for a in actions)

        # 叙事约束
        allowed: list[str] = []
        forbidden: list[str] = []
        if sig == SIG_NULL:
            allowed = [
                "如实报告『未发现稳健显著的平均处理效应』",
                "在机制层面展开：为何平均效应被稀释（异质性抵消 / 溢出 / 制度约束）",
                "把政策含义写成『在何种条件下政策才可能有效』",
            ]
            forbidden = [
                "声称政策『显著促进』结果变量",
                "把 0.05≤p<0.10 的系数表述为『证实了正向效应』",
                "把『不显著』直接等同于『政策无效』（需区分功效不足 vs 真无效）",
            ]
        elif sig == SIG_WEAK:
            allowed = [
                "表述为『存在边际/弱证据』，并强调对设定的敏感性",
                "用现代 DID + 机制分析佐证弱效应的稳健性",
            ]
            forbidden = [
                "把弱显著（p≈0.10）写成主结论级别的『显著』",
                "只报告线性趋势设定下转正的那一个规格而隐藏其他不显著规格",
            ]
        else:  # strong
            allowed = ["正常报告显著效应，并配套常规稳健性检验"]

        sig_txt = {
            SIG_STRONG: "显著",
            SIG_WEAK: "弱显著",
            SIG_NULL: "不显著",
        }[sig]
        n_missing = sum(1 for a in actions if not a.done)
        summary = (
            f"[{'阻止写作' if should_block else '可写作'}] "
            f"基准 p={self.baseline_p:.3f}（{sig_txt}），"
            f"待补齐 {n_missing}/{len(actions)} 项"
        )

        return NegativeResultVerdict(
            significance=sig,
            baseline_p=self.baseline_p,
            baseline_coef=self.baseline_coef,
            did_type=self.did_type,
            should_block_writing=should_block,
            required_actions=actions,
            allowed_narratives=allowed,
            forbidden_narratives=forbidden,
            summary_message=summary,
        )


# ── 便捷函数 ────────────────────────────────────────────────────────────────────


def assess_result(
    *,
    baseline_p: float,
    baseline_coef: float,
    did_type: str = "twfe",
    is_staggered: bool = True,
    has_modern_did: bool = False,
    has_mechanism: bool = False,
    has_heterogeneity: bool = False,
    has_spatial: bool = False,
    has_placebo: bool = False,
) -> NegativeResultVerdict:
    """一行调用：评估负显著结果并返回决策。"""
    return NegativeResultHandler(
        baseline_p=baseline_p,
        baseline_coef=baseline_coef,
        did_type=did_type,
        is_staggered=is_staggered,
        has_modern_did=has_modern_did,
        has_mechanism=has_mechanism,
        has_heterogeneity=has_heterogeneity,
        has_spatial=has_spatial,
        has_placebo=has_placebo,
    ).assess()
