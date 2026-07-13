"""
候选数据源注册表 + 评分卡 (DataSource Candidate Registry & Scorecard)
论文-研报工作流 · FinResearch Agent

────────────────────────────────────────────────────────────────────
【防反模式 (Anti-Pattern this module prevents)】
────────────────────────────────────────────────────────────────────
当首选数据源（CEADs、CSMAR、Wind、CEIC、某个公开CSV……）临时不可用时，
旧版本的 fetcher 会**静默**回退到某一个替代数据集，过程中既不：
    (a) 枚举所有可能的替代候选，
    (b) 也没有让用户评审候选的取舍，
    (c) 更没有记录为什么选择这个而不是那个。

这在严肃实证研究里几乎一定是失误——研究者在投稿前可能完全意识不到
主变量来自哪个具体数据源、被替代过几次、缺失值被哪种规则填补。

本模块提供了一个"候选注册表 + 评分卡"：
    1. 让调用方显式地注册 N 个候选数据源（必须 >= 1），
    2. 由 caller / LLM 人工评估每个候选在 5 个维度的子分（0–1），
    3. 自动补齐可客观决定的子分（availability、license_openness），
    4. 计算加权总分并按降序排名，
    5. **永不自动选择**：当有 >= 2 个 viable 候选时，强制要求用户决策。

────────────────────────────────────────────────────────────────────
【必须人工提供 vs 自动推导的子分】
────────────────────────────────────────────────────────────────────
自动推导（不要让 LLM 编造精确数字）：
    - availability    — 从 SourceAvailability 枚举直接映射
    - license_openness — 从 license 字符串匹配关键词（CC BY/CC0/MIT/public domain）

必须由调用方 / 研究者 / LLM **显式提供**（默认 0.5 中性）：
    - coverage_match  — 时空覆盖是否覆盖研究需要的时间窗与地理范围
    - indicator_fit   — 候选源的指标（被解释/解释变量）是否真的可用
    - credibility     — 是否有同行评议/官方发布背景

理由：coverage / indicator / credibility 都需要领域知识与对研究设计的
精确理解，编造数字会引入"伪客观"的评分。本模块只对 availability 和
license 做客观映射，对其余维度等待真实输入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── ANSI Colors (match scripts/data_source_checker.py style) ──────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


# ── Enums ─────────────────────────────────────────────────────────────────────


class SourceAvailability(str, Enum):
    """数据源可用性枚举。"""

    PUBLIC_FREE = "public_free"            # 完全公开，免费，无需任何账号
    PUBLIC_REGISTER = "public_register"    # 公开但需要免费注册（如 CEIC Lite）
    RESTRICTED_LOGIN = "restricted_login"  # 仅登录/订阅用户可用（机构/IP 限制）
    PAID = "paid"                          # 商业付费（Wind/CSMAR 完整版）
    UNAVAILABLE = "unavailable"            # 已下线 / 接口废弃 / URL 不可达


# ── Scoring dataclasses ───────────────────────────────────────────────────────


@dataclass
class CandidateScore:
    """单个候选数据源的多维度评分卡。

    所有 sub-score 取值 [0.0, 1.0]。总分由 weights 字典加权得到 [0.0, 1.0]。

    `availability` 与 `license_openness` 由 registry 自动从候选属性推导；
    `coverage_match`、`indicator_fit`、`credibility` 必须由调用方显式
    传入（若未传则默认 0.5 中性）。
    """

    availability: float
    license_openness: float
    coverage_match: float
    indicator_fit: float
    credibility: float

    weights: dict = field(default_factory=lambda: {
        "availability": 0.25,
        "license_openness": 0.15,
        "coverage_match": 0.20,
        "indicator_fit": 0.25,
        "credibility": 0.15,
    })

    @property
    def weighted_total(self) -> float:
        """加权总分（0–1），按 weights 字典线性加权。"""
        total = 0.0
        for key, w in self.weights.items():
            v = getattr(self, key, 0.0)
            # 防御性 clamp：保证子分在 [0, 1]
            v = max(0.0, min(1.0, float(v)))
            total += v * w
        return total

    def as_dict(self) -> dict:
        """序列化为 dict，便于 JSON 持久化。包含权重与总分。"""
        return {
            "availability": self.availability,
            "license_openness": self.license_openness,
            "coverage_match": self.coverage_match,
            "indicator_fit": self.indicator_fit,
            "credibility": self.credibility,
            "weighted_total": self.weighted_total,
            "weights": dict(self.weights),
        }


# ── Candidate & result dataclasses ────────────────────────────────────────────


@dataclass
class DataSourceCandidate:
    """单个候选数据源。"""

    name: str                                      # 人类可读名，如 "CEADs 中国碳核算数据库"
    url: str                                       # 主页/下载入口 URL
    availability: SourceAvailability
    license: str                                   # "CC BY 4.0" / "unknown" / "proprietary" …
    temporal_coverage: str                         # 如 "1997–2022" / "annual 2000–"
    geographic_coverage: str                       # 如 "中国 30 省" / "全球"
    indicator_description: str                     # 此源具体能提供哪些指标
    citation: str = ""                             # 推荐引用（DOI / paper / 机构）
    notes: str = ""                                # 任何附加上下文（费用、登录方式等）
    score: Optional[CandidateScore] = None         # 若已预评分则附上


@dataclass
class CandidateRegistryResult:
    """注册表产出：已排序候选列表 + 推荐项 + 是否需用户决策。"""

    research_need: str
    candidates: list                              # list[DataSourceCandidate], 已按 weighted_total 降序
    recommended: Optional[DataSourceCandidate]    # 仅作为建议，不自动提交
    requires_user_decision: bool                   # >=2 viable 候选时恒为 True
    summary_message: str                          # 面向用户的中文总结


# ── Helpers: objective sub-score mapping ──────────────────────────────────────

_AVAILABILITY_SUBSCORE: dict[SourceAvailability, float] = {
    SourceAvailability.PUBLIC_FREE: 1.0,
    SourceAvailability.PUBLIC_REGISTER: 0.8,
    SourceAvailability.RESTRICTED_LOGIN: 0.4,
    SourceAvailability.PAID: 0.3,
    SourceAvailability.UNAVAILABLE: 0.0,
}

# License keywords → openness score. Order matters (most → least).
_LICENSE_OPENNESS_RULES: list = [
    # (match_substring_lower, openness_score)
    (("cc0", "public domain", "公有领域"), 1.0),
    (("cc by", "cc-by", "cc by-sa", "cc by-nc", "cc by-nd"), 0.95),
    (("cc ", "creative commons"), 0.9),
    (("mit", "bsd", "apache", "gpl", "lgpl", "open data"), 0.9),
    (("free for non-commercial", "学术使用"), 0.7),
    (("restricted", "proprietary", "商业使用禁止", "all rights reserved"), 0.2),
    (("unknown", ""), 0.4),
]


def _availability_subscore(avail: SourceAvailability) -> float:
    return _AVAILABILITY_SUBSCORE.get(avail, 0.0)


def _license_subscore(license_str: str) -> float:
    """从 license 字符串启发式推导 openness 子分 [0, 1]。"""
    if license_str is None:
        return 0.4
    s = license_str.strip().lower()
    if not s:
        return 0.4
    for keywords, score in _LICENSE_OPENNESS_RULES:
        for kw in keywords:
            if kw in s:
                return score
    # 任何未知但非空字符串 → 中等偏保守
    return 0.5


# ── Registry class ────────────────────────────────────────────────────────────


class DataSourceCandidateRegistry:
    """候选数据源注册表 + 评分卡 + 排序。

    使用流程：
        1. 实例化时传入 `research_need`（自然语言描述需要什么数据）
        2. 反复调用 `add_candidate(...)` 注入候选
        3. （可选）调用 `score_candidate(...)` 让 registry 补齐 availability / license 子分
        4. 调用 `rank()` 返回 CandidateRegistryResult（已排序）
        5. 调用 `print_report(...)` 给用户看决策面板
    """

    def __init__(self, research_need: str) -> None:
        self.research_need: str = research_need
        self._candidates: list[DataSourceCandidate] = []
        self._last_result: Optional[CandidateRegistryResult] = None

    # ── mutation ──────────────────────────────────────────────────────────────

    def add_candidate(self, candidate: DataSourceCandidate) -> None:
        """添加一个候选。可重复调用。重复 name 会被替换。"""
        for i, existing in enumerate(self._candidates):
            if existing.name == candidate.name:
                self._candidates[i] = candidate
                return
        self._candidates.append(candidate)

    # ── scoring ───────────────────────────────────────────────────────────────

    def score_candidate(self, candidate: DataSourceCandidate) -> CandidateScore:
        """为单个候选生成/补齐 CandidateScore。

        自动推导（不要伪造）：
            - availability    ← SourceAvailability 枚举映射
            - license_openness ← license 字符串关键词匹配

        必须由调用方显式传入（否则默认 0.5 中性）：
            - coverage_match
            - indicator_fit
            - credibility

        若 candidate.score 已存在且对应字段已填（不为 None 且 != 0.5 default），
        则保留原值；否则使用 0.5 中性默认值。
        """
        existing = candidate.score
        availability = _availability_subscore(candidate.availability)
        license_openness = _license_subscore(candidate.license)

        # 若已有 score，沿用已显式提供的子分；否则全部默认 0.5
        def _keep_or_default(attr: str) -> float:
            if existing is not None:
                v = getattr(existing, attr, 0.5)
                # 0.5 视为"未填"，统一退回中性默认；其他值视为调用方已填
                return float(v) if v is not None else 0.5
            return 0.5

        coverage_match = _keep_or_default("coverage_match")
        indicator_fit = _keep_or_default("indicator_fit")
        credibility = _keep_or_default("credibility")

        return CandidateScore(
            availability=availability,
            license_openness=license_openness,
            coverage_match=coverage_match,
            indicator_fit=indicator_fit,
            credibility=credibility,
        )

    # ── ranking ───────────────────────────────────────────────────────────────

    def rank(self) -> CandidateRegistryResult:
        """对所有候选自动补齐 score，按 weighted_total 降序排序，构造结果。

        - recommended = 排序后的第一名（仅作为"建议"），但仍需用户决策
        - requires_user_decision = True 当 viable 候选数（availability != UNAVAILABLE）>= 2
        - 仅 1 个 viable 候选时 requires_user_decision = False（其它都是不可用的）
        """
        for cand in self._candidates:
            cand.score = self.score_candidate(cand)

        # 按 weighted_total 降序；同分则按 name 字典序稳定排序。
        # Viable 候选（availability != UNAVAILABLE）始终排在 UNAVAILABLE 之前——
        # 这样 "recommended" 始终指向一个当前可用的数据源，不会推荐一个下线的源。
        def _rank_key(c: DataSourceCandidate) -> tuple:
            score = c.score.weighted_total if c.score else 0.0
            is_viable = 0 if c.availability != SourceAvailability.UNAVAILABLE else 1
            return (is_viable, -score, c.name)

        ranked = sorted(self._candidates, key=_rank_key)

        viable = [c for c in ranked if c.availability != SourceAvailability.UNAVAILABLE]
        requires_decision = len(viable) >= 2

        recommended: Optional[DataSourceCandidate] = ranked[0] if ranked else None

        if not self._candidates:
            summary = "⚠ 未注册任何候选数据源。请先调用 add_candidate(...)。"
        elif not viable:
            summary = (
                "❌ 所有候选当前都不可用 (UNAVAILABLE)。"
                "请重新接入数据源或更换研究方向。"
            )
        elif len(viable) == 1:
            summary = (
                f"ℹ 仅 1 个 viable 候选（{viable[0].name}），"
                f"无歧义，但仍建议用户确认（推荐项: {recommended.name if recommended else 'N/A'}）。"
            )
        else:
            summary = (
                f"⚠ 已注册 {len(self._candidates)} 个候选，其中 {len(viable)} 个 viable。"
                f"系统推荐: {recommended.name if recommended else 'N/A'}，"
                f"但**严禁自动选择**——请用户从下表决策。"
            )

        self._last_result = CandidateRegistryResult(
            research_need=self.research_need,
            candidates=ranked,
            recommended=recommended,
            requires_user_decision=requires_decision,
            summary_message=summary,
        )
        return self._last_result

    # ── reporting ─────────────────────────────────────────────────────────────

    def print_report(self, result: Optional[CandidateRegistryResult] = None) -> None:
        """打印候选面板。Boxed ANSI report，方便用户在终端直接阅读决策。"""
        if result is None:
            result = self.rank()

        bar = "═" * 72
        print()
        print(c(bar, CYAN))
        title = "  数据源候选评分卡 (DataSource Candidate Scorecard)  "
        print(c("║", CYAN) + c(title.center(68), CYAN) + c(" ║", CYAN))
        print(c(bar, CYAN))
        print()
        print(f"  📌 研究需要: {c(self.research_need, BOLD)}")
        print(f"  📊 已注册候选数: {len(result.candidates)}")
        print()

        if not result.candidates:
            print(c("  ⚠ 无候选。请先调用 add_candidate(...) 注入候选。", YELLOW))
            print()
            return

        # 表头
        header = (
            f"  {'Rank':<5}{'Name':<32}{'Score':<8}"
            f"{'Avail':<10}{'License':<14}{'Coverage':<22}{'IndicatorFit'}"
        )
        print(c(header, BOLD))
        print(c("  " + "─" * 95, CYAN))

        for i, cand in enumerate(result.candidates, start=1):
            score = cand.score.weighted_total if cand.score else 0.0
            avail_icon = _availability_icon(cand.availability)
            license_short = _truncate(cand.license, 12)
            coverage_short = _truncate(f"{cand.temporal_coverage} | {cand.geographic_coverage}", 20)

            # 子分括号
            sub = ""
            if cand.score is not None:
                sub = (
                    f"(av={cand.score.availability:.2f},"
                    f"lc={cand.score.license_openness:.2f},"
                    f"cv={cand.score.coverage_match:.2f},"
                    f"in={cand.score.indicator_fit:.2f},"
                    f"cr={cand.score.credibility:.2f})"
                )

            row = (
                f"  #{i:<4}{_truncate(cand.name, 30):<32}"
                f"{score:<8.3f}{avail_icon:<10}{license_short:<14}"
                f"{coverage_short:<22}"
            )
            print(row)
            if sub:
                print(c(f"      └─ sub-scores {sub}", CYAN))
            print(f"      └─ indicator: {_truncate(cand.indicator_description, 70)}")
            if cand.citation:
                print(f"      └─ citation:  {cand.citation}")
            if cand.notes:
                print(f"      └─ notes:     {_truncate(cand.notes, 70)}")
            print()

        # 推荐 + 用户决策
        print(c("  " + "─" * 95, CYAN))
        print()
        if result.recommended is not None:
            score = result.recommended.score.weighted_total if result.recommended.score else 0.0
            print(f"  🏆 系统建议（仅供参考）: {c(result.recommended.name, BOLD)} (score={score:.3f})")
            print()

        if result.requires_user_decision:
            print(c(
                "  ⚠ 需用户决策：请从以上候选中选择，系统不自动选择。",
                YELLOW + BOLD,
            ))
            print(c(
                "     → 直接告诉 agent 你选择第几个候选 (e.g. '用 #2'),"
                " 或要求补全某些候选的 coverage / indicator / credibility 子分后重排。",
                YELLOW,
            ))
        else:
            print(c("  ✓ 仅 1 个 viable 候选，系统可直接继续；但建议研究者复核。", GREEN))
        print()
        print(f"  📝 summary: {result.summary_message}")
        print()
        print(c(bar, CYAN))
        print()


# ── Module-level convenience ──────────────────────────────────────────────────


def build_registry(
    research_need: str,
    candidates: list,
) -> CandidateRegistryResult:
    """一键构造并排名：research_need + 候选列表 → CandidateRegistryResult。

    不直接打印，等价于：
        reg = DataSourceCandidateRegistry(research_need)
        for c in candidates: reg.add_candidate(c)
        return reg.rank()
    """
    reg = DataSourceCandidateRegistry(research_need)
    for c in candidates:
        reg.add_candidate(c)
    return reg.rank()


# ── Private formatting helpers ────────────────────────────────────────────────


_AVAILABILITY_ICONS: dict = {
    SourceAvailability.PUBLIC_FREE: "🟢 free",
    SourceAvailability.PUBLIC_REGISTER: "🟡 register",
    SourceAvailability.RESTRICTED_LOGIN: "🟠 login",
    SourceAvailability.PAID: "🔴 paid",
    SourceAvailability.UNAVAILABLE: "⚫ N/A",
}


def _availability_icon(avail: SourceAvailability) -> str:
    return _AVAILABILITY_ICONS.get(avail, "?")


def _truncate(s: str, n: int) -> str:
    if s is None:
        return ""
    s = str(s)
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


__all__ = [
    "SourceAvailability",
    "CandidateScore",
    "DataSourceCandidate",
    "CandidateRegistryResult",
    "DataSourceCandidateRegistry",
    "build_registry",
    "c",
]
