"""Empirical package contract + write-gate (portable, not paper-specific).

Distilled from the local 实证分析 architecture layer: a DID/empirical paper
is a *package* of slots, not a single TWFE table plus a restriction sentence.

This module does **not** copy journal phrasebooks or project-specific locks.
It encodes only reusable contracts:

1. Gold slots (structure facts → stepwise → tighter compare → robust matrix
   → T→M mechanism table → sample flow).
2. ``variable_jobs``: every control has a job attached to *this* Y, plus a
   non-sticker ``basis``.
3. Mechanism channels must be disjoint from the control battery.
4. Write-gate conjunction: significant main column ∧ jobs ∧ live mechanism
   ∧ genre-appropriate fourth piece (clean event/placebo figures for policy
   DID; tighter compare for cross-section).

Writing-only tracks without a package file soft-skip. A present package that
fails the conjunction blocks the writing pre-gate.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "GOLD_SLOTS",
    "CORE_OVERLAY_SLOTS",
    "THINKING_QUESTIONS",
    "PackageFinding",
    "EmpiricalPackageReport",
    "empty_package",
    "validate_package",
    "audit_manuscript",
    "write_gate",
    "find_package_path",
    "load_package",
    "check_empirical_package",
    "package_from_pipeline_ctx",
    "thinking_questions",
]

GOLD_SLOTS: tuple[str, ...] = (
    "desc",
    "facts_before_reg",
    "baseline_stepwise",
    "tighter_compare",
    "robust_matrix",
    "mechanism",
    "sample_flow",
)
# Optional unless the Y is a constructed transform.
OPTIONAL_GOLD_SLOTS: tuple[str, ...] = ("measure_dict",)

CORE_OVERLAY_SLOTS: tuple[str, ...] = (
    "parallel_trends",
    "placebo",
    "exclusive",
    "psm",
    "hetero",
)

MODES = frozenset({"gold", "core", "forum", "cross_section"})
UNITS = frozenset({"county", "city", "firm", "household", "right", "other"})

THINKING_QUESTIONS: tuple[str, ...] = (
    "处理改的是哪一端（政府 / 企业 / 农户 / 市场）？缺该端微观时换哪个观察点才能印出独立于控制的 M？",
    "本题 Y 的构念一句是什么？控制的职务必须接到这句，而不是接到近邻论文的 Y。",
    "每个控制挡的是名单选择，还是本题 Y 的事前环境？写不出职务就删。",
    "刊上同名控制用的是哪个公式？名字一样、分母不同，是两件东西。",
    "该变量是事前环境，还是最终结果（通常是 Y 或 M，不是控制）？",
    "表行能否写成中文构念？禁止把 Phone / ICT / Is 印成表行。",
    "basis 是否接到本题（打开过的定义 + 本题路径）？只写「借鉴×× / 年鉴有 / 减少遗漏偏误」是贴纸。",
    "机制渠道与控制电池是否同构念？同一活动换分母不能既控制又机制。",
    "机制是处理→点名 M 的表，还是道歉段 / 节标题 / 把主 Y 切片？政策 DID 不得 dropped 机制。",
    "第四件随体裁：政策 DID 要事件图处理后 CI 不跨 0；截面要更紧比较站住。过一扇门不能交。",
)

_STICKER_EXACT = re.compile(
    r"^(借鉴\S+|年鉴有|减少遗漏偏误|用份额|显著|参考已有研究|参考已有文献)$"
)
_CODE_ROW = re.compile(
    r"^(Phone|ICT|Is|Sav|Hos|Welfare|lnLoan|pred_loan|Budget)$",
    re.I,
)
_MEMO_PHRASES = (
    "不应解释为",
    "本文不是",
    "过闸",
    "杀线",
    "主张纪律",
    "升为主结果",
    "按种子文",
    "按八格交出",
    "把对象推进到",
)
_DOI_IN_BIB = re.compile(r"(?i)\bdoi\s*[:=]|https?://doi\.org/")
_HYP_DIAGNOSTIC = re.compile(
    r"H\s*[1-4].{0,40}(平行趋势|倾向得分|PSM|泊松|PPML|匹配|样本单元)"
)


@dataclass
class PackageFinding:
    severity: str  # error | warning
    code: str
    message: str


@dataclass
class EmpiricalPackageReport:
    passed: bool
    summary_message: str
    skipped: bool = False
    findings: list[PackageFinding] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_gate_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "summary_message": self.summary_message,
            "skipped": self.skipped,
            "details": {
                **self.details,
                "findings": [asdict(f) for f in self.findings],
            },
        }


def thinking_questions() -> tuple[str, ...]:
    return THINKING_QUESTIONS


def empty_package(*, mode: str = "gold", unit: str = "firm") -> dict[str, Any]:
    """Scaffold a package. Questions first; do not copy example channel names."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    if unit not in UNITS:
        raise ValueError(f"unit must be one of {sorted(UNITS)}")
    slots = {name: "" for name in GOLD_SLOTS}
    if mode == "core":
        for name in CORE_OVERLAY_SLOTS:
            slots[name] = ""
    return {
        "mode": mode,
        "unit": unit,
        "y_construct": "",
        "x_construct": "",
        "battery": [],
        "variable_jobs": [],
        "slots": slots,
        "dropped": [],
        "main_col": "",
        "main_p": None,
        "mechanism_channels": [],
        "mechanism_methods": [],
        "mechanism_lock": [],
        "mechanism_theory": "",
        "figure_gate": {},
        "null_effect": False,
    }


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", (text or "").lower())


def _dropped_slots(pkg: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in pkg.get("dropped") or []:
        if isinstance(item, Mapping) and item.get("slot"):
            out[str(item["slot"])] = str(item.get("reason") or "").strip()
    return out


def _slot_filled(slots: Mapping[str, Any], name: str) -> bool:
    raw = slots.get(name)
    if raw is None or raw == "":
        return False
    if isinstance(raw, Mapping):
        return bool(raw.get("table") or raw.get("path") or raw.get("status") == "ran")
    return bool(str(raw).strip())


def _is_sticker_basis(basis: str, y_construct: str) -> bool:
    s = (basis or "").strip()
    if len(s) < 8:
        return True
    if _STICKER_EXACT.match(s):
        return True
    if s.startswith("借鉴") and (not y_construct or y_construct not in s) and "本题" not in s:
        return True
    if s in {"年鉴有", "减少遗漏偏误"}:
        return True
    return False


def _job_connects(job: str, y_construct: str, x_construct: str) -> bool:
    text = (job or "").strip()
    if len(text) < 4:
        return False
    anchors = [y_construct, x_construct, "选择", "申报", "名单", "处理", "Y"]
    if any(a and a in text for a in anchors):
        return True
    stem = re.sub(r"(对数|率|比重|存量|规模)$", "", y_construct or "")
    return bool(stem and len(stem) >= 2 and stem in text)


def validate_package(pkg: Mapping[str, Any]) -> list[PackageFinding]:
    findings: list[PackageFinding] = []
    mode = str(pkg.get("mode") or "")
    if mode not in MODES:
        findings.append(PackageFinding("error", "mode", f"mode 必须是 {sorted(MODES)} 之一"))
        return findings

    unit = str(pkg.get("unit") or "")
    if unit not in UNITS:
        findings.append(PackageFinding("error", "unit", f"unit 必须是 {sorted(UNITS)} 之一"))

    y_construct = str(pkg.get("y_construct") or "").strip()
    x_construct = str(pkg.get("x_construct") or "").strip()
    if not y_construct:
        findings.append(PackageFinding("error", "y_construct", "必须写本题 Y 构念（中文一句）"))
    if not x_construct:
        findings.append(PackageFinding("error", "x_construct", "必须写本题处理构念（中文一句）"))

    battery = [str(x).strip() for x in (pkg.get("battery") or []) if str(x).strip()]
    if len(battery) < 3 and mode != "forum":
        findings.append(
            PackageFinding("error", "battery", "非论坛稿控制电池至少 3 件，且每件要有职务")
        )

    jobs = [j for j in (pkg.get("variable_jobs") or []) if isinstance(j, Mapping)]
    job_by_name = {_norm(str(j.get("name") or "")): j for j in jobs}
    for name in battery:
        job = job_by_name.get(_norm(name))
        if job is None:
            findings.append(
                PackageFinding("error", "variable_jobs", f"电池项 {name!r} 没有 variable_jobs")
            )
            continue
        table_row = str(job.get("table_row") or "").strip()
        if not table_row or _CODE_ROW.match(table_row):
            findings.append(
                PackageFinding(
                    "error",
                    "table_row",
                    f"{name!r} 的 table_row 须是中文构念，不能是 {table_row or '空'}",
                )
            )
        job_text = str(job.get("job") or "")
        if not _job_connects(job_text, y_construct, x_construct):
            findings.append(
                PackageFinding(
                    "error",
                    "job",
                    f"{name!r} 的 job 必须接到本题 Y / 处理 / 选择，不能只写「减少遗漏偏误」",
                )
            )
        basis = str(job.get("basis") or "")
        if _is_sticker_basis(basis, y_construct):
            findings.append(
                PackageFinding(
                    "error",
                    "basis",
                    f"{name!r} 的 basis 是贴纸（借鉴/年鉴有/遗漏偏误），须接到本题路径",
                )
            )

    slots = pkg.get("slots") if isinstance(pkg.get("slots"), Mapping) else {}
    dropped = _dropped_slots(pkg)
    required = list(GOLD_SLOTS)
    if mode == "core":
        required.extend(CORE_OVERLAY_SLOTS)
    for name in required:
        if _slot_filled(slots, name):
            continue
        reason = dropped.get(name, "")
        if name == "mechanism" and mode == "core":
            findings.append(
                PackageFinding(
                    "error",
                    "mechanism_required",
                    "政策 DID（core）必须有处理→独立 M 的机制表，不得 dropped",
                )
            )
            continue
        if name == "psm" and reason:
            continue  # 吕铁式：排他金融政策可 drop PSM
        if name in OPTIONAL_GOLD_SLOTS and reason:
            continue
        if reason:
            if len(reason) < 6:
                findings.append(
                    PackageFinding("error", "dropped", f"slots.{name} 的 dropped 理由过短")
                )
            continue
        findings.append(
            PackageFinding("error", "slot", f"slots.{name} 未填且未写 dropped 理由")
        )

    channels = [str(c).strip() for c in (pkg.get("mechanism_channels") or []) if str(c).strip()]
    lock = {_norm(str(x)) for x in (pkg.get("mechanism_lock") or [])}
    battery_norm = {_norm(x) for x in battery}
    overlap = [_norm(c) for c in channels if _norm(c) in battery_norm or _norm(c) in lock]
    if overlap:
        findings.append(
            PackageFinding(
                "error",
                "mechanism_overlap",
                f"机制渠道与控制/lock 同构念：{overlap}。同一构念不能既进电池又进 M",
            )
        )
    if mode == "core" and not channels:
        findings.append(
            PackageFinding("error", "mechanism_channels", "政策 DID 须点名至少一条独立 M")
        )
    theory = str(pkg.get("mechanism_theory") or "").strip()
    if mode == "core" and (not theory or "借鉴" in theory and "→" not in theory):
        findings.append(
            PackageFinding(
                "error",
                "mechanism_theory",
                "须一句处理→M→本题 Y 的理论链，且与假说同号；不能只写借鉴",
            )
        )
    methods = [str(m).strip() for m in (pkg.get("mechanism_methods") or []) if str(m).strip()]
    if mode == "core" and channels and len(methods) < 2:
        findings.append(
            PackageFinding(
                "error",
                "mechanism_methods",
                "活渠道须两种测法（如 jiangting / sobel / did_x_m）并印在机制表上",
            )
        )

    if not str(pkg.get("main_col") or "").strip():
        findings.append(PackageFinding("error", "main_col", "必须点名主栏（哪一列是交卷列）"))

    return findings


def write_gate(pkg: Mapping[str, Any]) -> list[PackageFinding]:
    """Four-way conjunction. Passing one door is not enough."""
    findings = validate_package(pkg)
    mode = str(pkg.get("mode") or "")
    null_effect = bool(pkg.get("null_effect"))
    main_p = pkg.get("main_p")
    if main_p is None:
        findings.append(PackageFinding("error", "main_p", "交主结果必须记录 main_p"))
    else:
        try:
            pval = float(main_p)
        except (TypeError, ValueError):
            findings.append(PackageFinding("error", "main_p", "main_p 无法转为浮点数"))
        else:
            if pval > 0.10 and not null_effect:
                findings.append(
                    PackageFinding(
                        "error",
                        "main_insignificant",
                        f"主栏 p={pval} > 0.10：不显著不能写成「研究发现」，继续规格搜索",
                    )
                )

    fig = pkg.get("figure_gate") if isinstance(pkg.get("figure_gate"), Mapping) else {}
    dropped = _dropped_slots(pkg)
    if mode == "core" and not null_effect:
        post_n = int(fig.get("event_post_n") or 0)
        cross0 = int(fig.get("event_post_cross0_n") or 0)
        outside = fig.get("placebo_true_outside_mass")
        event0_job = str(fig.get("event0_job") or "").strip()
        if post_n <= 0 or cross0 > 0:
            findings.append(
                PackageFinding(
                    "error",
                    "figure_gate",
                    "政策 DID 事件图处理后多数 CI 不得跨 0；TWFE 显著但图不干净不能交",
                )
            )
        if outside is not True:
            findings.append(
                PackageFinding(
                    "error",
                    "placebo_figure",
                    "安慰剂真实系数须在灰堆/核密度主体之外（placebo_true_outside_mass=true）",
                )
            )
        if not event0_job:
            findings.append(
                PackageFinding(
                    "error",
                    "event0_job",
                    "0 点须有职务句（公布年还是落地年，为何最高/最低）",
                )
            )
    elif mode == "cross_section":
        slots = pkg.get("slots") if isinstance(pkg.get("slots"), Mapping) else {}
        if not _slot_filled(slots, "tighter_compare") and "tighter_compare" not in dropped:
            findings.append(
                PackageFinding(
                    "error",
                    "tighter_compare",
                    "截面稿第四件是更紧比较，不要套事件图门",
                )
            )
    return findings


def audit_manuscript(text: str, pkg: Mapping[str, Any] | None = None) -> list[PackageFinding]:
    findings: list[PackageFinding] = []
    body = text or ""
    for phrase in _MEMO_PHRASES:
        if phrase in body:
            findings.append(
                PackageFinding(
                    "error",
                    "memo_voice",
                    f"正文出现备忘录腔 {phrase!r}：摘要/结论第一句应是研究发现，限制嵌方法",
                )
            )
    bib = body
    for marker in ("参考文献", "References", "Bibliography"):
        if marker in body:
            bib = body[body.find(marker) :]
            break
    if _DOI_IN_BIB.search(bib) and ("参考文献" in body or "References" in body):
        findings.append(
            PackageFinding(
                "error",
                "bib_doi",
                "正文参考文献表不要写 DOI；DOI 留 docs/ 或 BibTeX 后台",
            )
        )
    if _HYP_DIAGNOSTIC.search(body):
        findings.append(
            PackageFinding(
                "error",
                "hypothesis_diagnostic",
                "假说不要写成平行趋势/PSM/泊松/匹配等识别诊断",
            )
        )
    if "依然成立" in body and pkg is not None:
        fig = pkg.get("figure_gate") if isinstance(pkg.get("figure_gate"), Mapping) else {}
        cross0 = int(fig.get("event_post_cross0_n") or 0)
        outside = fig.get("placebo_true_outside_mass")
        if cross0 > 0 or outside is False:
            findings.append(
                PackageFinding(
                    "error",
                    "still_holds",
                    "图门未过时摘要不得写「依然成立」",
                )
            )
    if re.search(r"^#{1,3}\s*.*(作用机制|机制分析)", body, re.M):
        if not re.search(r"(表\s*\d|\\begin\{table\}|coef|系数)", body):
            findings.append(
                PackageFinding(
                    "warning",
                    "mechanism_section",
                    "有机制节标题但未见表/系数：机制必须是处理→M 的表，不是道歉段",
                )
            )
    return findings


def find_package_path(search_dirs: Iterable[str | Path] | None = None) -> Path | None:
    names = (
        "empirical_package.json",
        "docs/empirical_package.json",
    )
    roots = [Path(p) for p in (search_dirs or ()) if p]
    for root in roots:
        if root.is_file() and root.name.endswith(".json"):
            return root
        for name in names:
            cand = root / name
            if cand.is_file():
                return cand
        nested = root / "fin-refinement" / "empirical_package.json"
        if nested.is_file():
            return nested
        nested = root / "fin-experiments" / "empirical_package.json"
        if nested.is_file():
            return nested
    return None


def load_package(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("empirical_package.json 必须是对象")
    return dict(data)


def check_empirical_package(
    *,
    package: Mapping[str, Any] | None = None,
    manuscript: str | None = None,
    search_dirs: Iterable[str | Path] | None = None,
    package_path: str | Path | None = None,
) -> EmpiricalPackageReport:
    """Writing pre-gate adapter: skip if no package; fail-closed if one exists."""
    pkg: Mapping[str, Any] | None = package
    found: Path | None = Path(package_path) if package_path else None
    if pkg is None:
        found = found or find_package_path(search_dirs)
        if found is None:
            return EmpiricalPackageReport(
                passed=True,
                skipped=True,
                summary_message=(
                    "[empirical_package] skipped: no empirical_package.json "
                    "on writing-only track (compat soft-pass)"
                ),
            )
        try:
            pkg = load_package(found)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return EmpiricalPackageReport(
                passed=False,
                summary_message=f"[empirical_package] failed to load {found}: {exc}",
                details={"path": str(found)},
            )

    findings = write_gate(pkg)
    if manuscript:
        findings.extend(audit_manuscript(manuscript, pkg))
    errors = [f for f in findings if f.severity == "error"]
    passed = not errors
    loc = str(found) if found else "in-memory"
    summary = (
        f"[empirical_package] write-gate passed ({loc})"
        if passed
        else f"[empirical_package] write-gate blocked ({len(errors)} errors) @ {loc}"
    )
    return EmpiricalPackageReport(
        passed=passed,
        skipped=False,
        summary_message=summary,
        findings=findings,
        details={"path": loc, "mode": pkg.get("mode"), "n_errors": len(errors)},
    )


def package_from_pipeline_ctx(ctx: Any) -> dict[str, Any]:
    """Honest scaffold from EnhancedPipeline context. Missing slots stay dropped."""
    results = getattr(ctx, "modern_did_results", None) or {}
    topic = str(getattr(ctx, "topic", "") or "")
    main_p = None
    main_col = ""
    for key, val in results.items() if isinstance(results, Mapping) else []:
        if not isinstance(val, Mapping):
            continue
        for pk in ("pval", "p", "pvalue", "p_value"):
            if pk in val:
                try:
                    main_p = float(val[pk])
                    main_col = str(key)
                except (TypeError, ValueError):
                    continue
                break
        if main_col:
            break

    ran_baseline = bool(results)
    robust = getattr(ctx, "robustness_report", None)
    ran_robust = robust is not None and bool(getattr(robust, "__len__", lambda: True)())
    pkg = empty_package(mode="core", unit="firm")
    pkg["y_construct"] = topic or "未点名 Y"
    pkg["x_construct"] = "处理（流水线未点名官方名单/时点）"
    pkg["main_col"] = main_col or "did"
    pkg["main_p"] = main_p
    pkg["slots"]["baseline_stepwise"] = "enhanced_pipeline.modern_did" if ran_baseline else ""
    pkg["slots"]["robust_matrix"] = "enhanced_pipeline.robustness_runner" if ran_robust else ""
    pkg["slots"]["parallel_trends"] = str(
        getattr(ctx, "parallel_trends_method", "") or "event_study"
    )
    pkg["dropped"] = [
        {"slot": "desc", "reason": "enhanced_pipeline 未生成变量定义表，须设计轨补全"},
        {"slot": "facts_before_reg", "reason": "流水线未跑回归前结构事实表"},
        {"slot": "tighter_compare", "reason": "未自动跑 within / 更局部 FE 梯子"},
        {"slot": "mechanism", "reason": "流水线未估计处理→独立 M；写稿前必须补机制表"},
        {"slot": "sample_flow", "reason": "未记录逐步流失 n"},
        {"slot": "placebo", "reason": "未跑随机安慰剂密度"},
        {"slot": "exclusive", "reason": "未跑排他政策"},
        {"slot": "psm", "reason": "未跑 PSM；有排他金融政策时可保留此 dropped"},
        {"slot": "hetero", "reason": "未跑两条异质"},
    ]
    # Honest: core still fails mechanism_required — that is the point.
    return pkg


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Empirical package write-gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("questions", help="Print the 10 thinking questions")
    sc = sub.add_parser("scaffold", help="Print an empty package JSON")
    sc.add_argument("--mode", default="gold", choices=sorted(MODES))
    sc.add_argument("--unit", default="firm", choices=sorted(UNITS))
    au = sub.add_parser("audit", help="Validate a package and optional manuscript")
    au.add_argument("package", help="Path to empirical_package.json")
    au.add_argument("--manuscript", default="", help="Optional draft path")
    args = parser.parse_args(argv)

    if args.cmd == "questions":
        for i, q in enumerate(THINKING_QUESTIONS, 1):
            print(f"{i}. {q}")
        return 0
    if args.cmd == "scaffold":
        print(json.dumps(empty_package(mode=args.mode, unit=args.unit), ensure_ascii=False, indent=2))
        return 0

    manuscript = ""
    if args.manuscript:
        manuscript = Path(args.manuscript).read_text(encoding="utf-8")
    report = check_empirical_package(package_path=args.package, manuscript=manuscript or None)
    print(report.summary_message)
    for finding in report.findings:
        print(f"  [{finding.severity}] {finding.code}: {finding.message}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
