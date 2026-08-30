"""TOPIC.md integrity: detect hard data/ID requirements vs proxy laundering.

Test-user runs shipped causal PDFs while substituting city patents for firm
patents, overseas revenue for customs, interest coverage for bond spreads.
This module flags those hard gaps so host mode can fail-closed on empirics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.core.empirical_data_root import (
    EmpiricalDataRoot,
    find_candidate_files,
    resolve_empirical_data_root,
)

__all__ = [
    "HardRequirement",
    "TopicIntegrityReport",
    "assess_topic_integrity",
]


@dataclass(frozen=True)
class HardRequirement:
    key: str
    label: str
    pattern: re.Pattern[str]
    # Path keywords that suggest a local panel may cover the requirement
    file_keywords: tuple[str, ...]
    # Phrases that indicate the agent already used a forbidden proxy
    proxy_patterns: tuple[re.Pattern[str], ...] = ()


_HARD: tuple[HardRequirement, ...] = (
    HardRequirement(
        key="firm_green_patents",
        label="企业级绿色专利（非城市/省份聚合）",
        pattern=re.compile(
            r"(企业.?级.?绿色.?专利|firm[- ]?level.*green.*patent|"
            r"绿色专利.*企业|企业绿色专利|上市公司.*绿色专利)",
            re.I,
        ),
        file_keywords=("绿色专利", "green_patent", "patent", "ipc", "绿色"),
        proxy_patterns=(
            re.compile(r"(城市|地级市|省级).{0,12}(绿色)?专利", re.I),
            re.compile(r"city[- ]level.*patent", re.I),
        ),
    ),
    HardRequirement(
        key="customs_hs",
        label="海关/HS 贸易明细（非海外营收代理）",
        pattern=re.compile(
            r"(海关|HS.?码|HS code|customs|进出口明细|贸易明细)",
            re.I,
        ),
        file_keywords=("海关", "customs", "hs", "进出口", "trade"),
        proxy_patterns=(
            re.compile(r"(海外营收|境外收入|overseas.?revenue).{0,20}(代理|proxy|替代)", re.I),
            re.compile(r"用.{0,8}(海外|境外).{0,8}(营收|收入).{0,8}(代替|替代)", re.I),
        ),
    ),
    HardRequirement(
        key="bond_spreads",
        label="债券利差/信用利差（非利息保障倍数代理）",
        pattern=re.compile(
            r"(债券利差|信用利差|credit.?spread|bond.?spread|公司债.?利差)",
            re.I,
        ),
        file_keywords=("利差", "spread", "债券", "bond", "信用债"),
        proxy_patterns=(
            re.compile(r"(利息保障|interest.?coverage).{0,20}(代理|proxy|替代)", re.I),
            re.compile(r"用.{0,8}利息保障.{0,8}(代替|替代).{0,8}利差", re.I),
        ),
    ),
    HardRequirement(
        key="carbon_quota",
        label="碳配额/碳交易微观数据",
        pattern=re.compile(
            r"(碳配额|碳排放权|碳交易.*企业|ETS.*firm|碳市场.*配额)",
            re.I,
        ),
        file_keywords=("碳", "carbon", "ets", "配额", "cea"),
        proxy_patterns=(),
    ),
)


@dataclass
class TopicIntegrityReport:
    requirements: list[str] = field(default_factory=list)
    satisfied: list[str] = field(default_factory=list)
    hard_gaps: list[str] = field(default_factory=list)
    proxy_warnings: list[str] = field(default_factory=list)
    data_root_note: str = ""
    candidate_files: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok_for_causal_empirics(self) -> bool:
        return not self.hard_gaps

    def to_skipped_items(self) -> list[dict]:
        items = []
        for gap in self.hard_gaps:
            items.append(
                {
                    "item": f"empirics:{gap}",
                    "reason": (
                        f"TOPIC 硬性要求「{gap}」在本地实证数据根中未找到可匹配面板；"
                        "禁止用代理变量完成因果实证并交付 PDF。"
                    ),
                    "fix_hint": (
                        "将匹配面板放入 FINAI_EMPIRICAL_DATA_ROOT，或收窄 TOPIC 去掉该硬性要求；"
                        "写作管线可继续，但不得声称已完成该识别。"
                    ),
                }
            )
        return items


def assess_topic_integrity(
    topic_text: str,
    *,
    data_root: EmpiricalDataRoot | None = None,
    artifact_text: str = "",
) -> TopicIntegrityReport:
    """Assess TOPIC hard requirements against local empirical root (+ optional artifacts)."""
    text = topic_text or ""
    root = data_root or resolve_empirical_data_root()
    report = TopicIntegrityReport(
        data_root_note=(
            f"{root.path} (source={root.source}, available={root.available})"
            if root.path
            else "FINAI_EMPIRICAL_DATA_ROOT unset / missing"
        )
    )
    blob = text + "\n" + (artifact_text or "")

    for req in _HARD:
        if not req.pattern.search(text):
            continue
        report.requirements.append(req.key)
        hits = find_candidate_files(list(req.file_keywords), root) if root.available else []
        report.candidate_files[req.key] = [str(h) for h in hits[:10]]
        if hits:
            report.satisfied.append(req.key)
        else:
            report.hard_gaps.append(req.key)
        for pp in req.proxy_patterns:
            if pp.search(blob):
                report.proxy_warnings.append(
                    f"{req.key}: artifact/TOPIC suggests forbidden proxy ({req.label})"
                )
                break
    return report
