"""
研究设计文档版本化模块（Design Doc Versioning）
论文-研报工作流 · FinResearch Agent

【背景：此模块要防止的缺陷】
在一个 8 阶段的实证研究流水线中（design → data → analysis → writing），
REFIED_DESIGN.md 通常在第 1 阶段（design）一次性写好。但随着研究推进，
主题、样本、方法、数据源、被解释变量经常会发生调整（例如：碳排放权交易 →
GTFP / 绿色经济增长；DID → 工具变量；Tushare → CSMAR）。
历史上这类变更从未被记录到设计文档中，导致：
  1. 最终论文与设计文档出现静默偏差（silent scope drift）
  2. 审稿人/读者无法追溯研究设计的演变轨迹
  3. 研究者本人也可能忘记早期假设的调整路径

【本模块的作用】
提供 DesignDocVersioning 类，在以下任一关键字段变更时（title /
dependent_variable / sample / identification_method / data_sources）自动
记录一个新版本快照：
  - version: 1-based 自增
  - timestamp: ISO8601 UTC 时间戳
  - title / dependent_variable / sample / identification_method / data_sources
  - change_reason: 本次变更原因
  - changed_fields: 相对上一版本发生变更的字段名列表

可输出 Markdown 演变轨迹小节，供论文附录或附录文件使用，确保研究设计
演变的完全可追溯性。

【用法】
    from scripts.research_framework.design_doc import new_versioning

    # 创建版本管理器（持久化到 <project_dir>/design_history.jsonl）
    v = new_versioning(project_dir="papers/my_project")

    # 第 1 阶段：设计初始
    v.record(
        title="碳排放权交易对企业绿色创新的影响",
        dependent_variable="ln_green_patents",
        sample="2015-2022年A股重污染行业上市公司",
        identification_method="DID (双重差分)",
        data_sources=["tushare", "csmar"],
        change_reason="初始设计"
    )

    # 第 3 阶段：主题调整
    v.record(
        title="碳排放权交易对GTFP的影响",
        dependent_variable="gtfp",
        sample="2010-2021年省级面板",
        identification_method="Spatial DID",
        data_sources=["user-financial", "china_statistical_yearbook"],
        change_reason="根据数据可获得性，将样本由企业级调整为省级；识别策略升级为空间DID"
    )

    # 在论文附录中插入演变轨迹
    print(v.render_evolution_markdown())

    # 健康检查：是否发生实质性变更？
    if v.has_diverged():
        v.print_report()
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── ANSI Colors（与 scripts/data_source_checker.py 保持一致） ─────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def c(text: str, color: str) -> str:
    """给文本上色，便于在终端突出显示。"""
    return f"{color}{text}{RESET}"


# ── 数据模型 ────────────────────────────────────────────────────────────────


@dataclass
class DesignSnapshot:
    """研究设计的单个版本快照。

    Attributes:
        version: 1-based 版本号。
        timestamp: ISO8601 UTC 时间戳（例如 "2026-07-12T15:30:45+00:00"）。
        title: 论文/研究主题。
        dependent_variable: 被解释变量（Y）。
        sample: 样本描述（行业、地区、时间区间）。
        identification_method: 识别策略（DID / IV / RDD / PSM / Synthetic Control 等）。
        data_sources: 数据源列表（如 ["tushare", "csmar"]）。
        change_reason: 本次版本相对上一版本的变更原因。
        changed_fields: 相对上一版本发生变更的字段名列表；首次记录为 ["initial"]，
            无变更时为 []。
    """

    version: int
    timestamp: str
    title: str
    dependent_variable: str
    sample: str
    identification_method: str
    data_sources: list[str] = field(default_factory=list)
    change_reason: str = ""
    changed_fields: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """转为 dict，便于 JSON 序列化。注意拷贝可变字段以避免外部修改。"""
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "title": self.title,
            "dependent_variable": self.dependent_variable,
            "sample": self.sample,
            "identification_method": self.identification_method,
            "data_sources": list(self.data_sources),
            "change_reason": self.change_reason,
            "changed_fields": list(self.changed_fields),
        }


# ── 核心管理器 ──────────────────────────────────────────────────────────────


# 构成"实质性变更"的字段（has_diverged 用于此判断）
MATERIAL_FIELDS = ("title", "dependent_variable", "identification_method")

# 所有可被 diff 跟踪的字段
TRACKED_FIELDS = (
    "title",
    "dependent_variable",
    "sample",
    "identification_method",
    "data_sources",
)


class DesignDocVersioning:
    """研究设计文档版本管理器。

    在内存中维护一个有序快照列表，可选地持久化到 JSONL 文件。
    每次 record() 调用会创建一个新快照，自动 diff 出 changed_fields。

    Args:
        project_dir: 项目目录（可选）。若提供，则持久化到
            ``<project_dir>/design_history.jsonl``；若为 None 则只保留在内存。
    """

    def __init__(self, project_dir: str | Path | None = None) -> None:
        self._snapshots: list[DesignSnapshot] = []
        self._project_dir: Optional[Path] = Path(project_dir) if project_dir else None
        if self._project_dir is not None:
            self._project_dir.mkdir(parents=True, exist_ok=True)

    # ── 持久化路径 ──────────────────────────────────────────────────────────

    @property
    def persistence_path(self) -> Optional[Path]:
        """JSONL 持久化文件路径（未配置 project_dir 时为 None）。"""
        if self._project_dir is None:
            return None
        return self._project_dir / "design_history.jsonl"

    # ── 记录快照 ────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        title: str,
        dependent_variable: str,
        sample: str,
        identification_method: str,
        data_sources: list[str],
        change_reason: str = "",
    ) -> DesignSnapshot:
        """记录一个新快照。

        会自动：
          - 设置 version（1-based，自增）
          - 设置 timestamp（ISO8601 UTC）
          - diff 出 changed_fields

        Args:
            title: 论文/研究主题。
            dependent_variable: 被解释变量。
            sample: 样本描述。
            identification_method: 识别策略。
            data_sources: 数据源列表。
            change_reason: 本次变更原因。

        Returns:
            刚创建的 DesignSnapshot。
        """
        previous = self._snapshots[-1] if self._snapshots else None
        new_version = (previous.version + 1) if previous else 1
        timestamp = _now_iso8601_utc()
        data_sources_list = list(data_sources)

        if previous is None:
            changed_fields = ["initial"]
        else:
            changed_fields = _diff_snapshots(
                previous,
                {
                    "title": title,
                    "dependent_variable": dependent_variable,
                    "sample": sample,
                    "identification_method": identification_method,
                    "data_sources": data_sources_list,
                },
            )
            if not changed_fields:
                print(
                    c(
                        f"  [design_doc] v{new_version}：无字段变更，仍记录快照。",
                        YELLOW,
                    )
                )

        snapshot = DesignSnapshot(
            version=new_version,
            timestamp=timestamp,
            title=title,
            dependent_variable=dependent_variable,
            sample=sample,
            identification_method=identification_method,
            data_sources=data_sources_list,
            change_reason=change_reason,
            changed_fields=changed_fields,
        )

        self._snapshots.append(snapshot)
        self._persist_one(snapshot)
        return snapshot

    # ── 加载历史 ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """从持久化 JSONL 文件加载历史到内存。

        文件不存在时静默返回（首次使用场景）。已存在的内存快照会被清空后
        从文件重建，确保文件是真相源。
        """
        path = self.persistence_path
        if path is None or not path.exists():
            return

        self._snapshots = []
        with path.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as exc:
                    print(
                        c(
                            f"  [design_doc] 跳过第 {lineno} 行（JSON 解析失败: {exc}）",
                            YELLOW,
                        )
                    )
                    continue
                self._snapshots.append(
                    DesignSnapshot(
                        version=int(data["version"]),
                        timestamp=str(data["timestamp"]),
                        title=str(data["title"]),
                        dependent_variable=str(data["dependent_variable"]),
                        sample=str(data["sample"]),
                        identification_method=str(data["identification_method"]),
                        data_sources=list(data.get("data_sources", [])),
                        change_reason=str(data.get("change_reason", "")),
                        changed_fields=list(data.get("changed_fields", [])),
                    )
                )

    # ── 查询接口 ────────────────────────────────────────────────────────────

    def latest(self) -> Optional[DesignSnapshot]:
        """最新版本快照（无历史时为 None）。"""
        return self._snapshots[-1] if self._snapshots else None

    def history(self) -> list[DesignSnapshot]:
        """返回所有快照的浅拷贝（避免外部修改内部状态）。"""
        return list(self._snapshots)

    # ── 实质性变更检测 ──────────────────────────────────────────────────────

    def has_diverged(self) -> bool:
        """是否在执行过程中发生实质性变更。

        判定规则：
          1. 必须有多于 1 个版本（即确实发生过修订）；且
          2. 在所有快照的 changed_fields 中，至少出现过一次
             "title"、"dependent_variable" 或 "identification_method"
             中的任意一项。

        sample 与 data_sources 的变更被视为非实质性（不影响研究身份）。
        """
        if len(self._snapshots) <= 1:
            return False
        for snap in self._snapshots:
            for field_name in MATERIAL_FIELDS:
                if field_name in snap.changed_fields:
                    return True
        return False

    # ── Markdown 渲染 ───────────────────────────────────────────────────────

    def render_evolution_markdown(self) -> str:
        """渲染研究设计演变轨迹 Markdown 段，可插入论文附录。

        Returns:
            形如：

                ## 研究设计演变轨迹 (Design Evolution Trail)

                | 版本 | 时间 | 变更字段 | 变更原因 |
                |---|---|---|---|
                | v1 | 2026-07-12T10:00:00+00:00 | initial | 初始设计 |
                | v2 | 2026-07-13T11:00:00+00:00 | title, dependent_variable | 主题调整 |

                **当前设计（v{latest}）：**
                - 主题：...
                - 被解释变量：...
                - 样本：...
                - 识别策略：...
                - 数据源：...
        """
        if not self._snapshots:
            return (
                "## 研究设计演变轨迹 (Design Evolution Trail)\n\n"
                "_尚无任何设计版本记录。_"
            )

        if len(self._snapshots) == 1:
            latest = self._snapshots[0]
            return (
                "## 研究设计演变轨迹 (Design Evolution Trail)\n\n"
                "研究设计在执行过程中保持稳定，无重大变更。\n\n"
                f"**当前设计（v{latest.version}，{_short_ts(latest.timestamp)}）：**\n"
                f"- 主题：{latest.title}\n"
                f"- 被解释变量：{latest.dependent_variable}\n"
                f"- 样本：{latest.sample}\n"
                f"- 识别策略：{latest.identification_method}\n"
                f"- 数据源：{', '.join(latest.data_sources) if latest.data_sources else '（未指定）'}\n"
            )

        lines: list[str] = ["## 研究设计演变轨迹 (Design Evolution Trail)", ""]
        lines.append("| 版本 | 时间 | 变更字段 | 变更原因 |")
        lines.append("|---|---|---|---|")
        for snap in self._snapshots:
            fields = ", ".join(snap.changed_fields) if snap.changed_fields else "—"
            reason = snap.change_reason or "—"
            # 管道符转义，避免破坏 Markdown 表格
            reason_escaped = reason.replace("|", "\\|")
            fields_escaped = fields.replace("|", "\\|")
            lines.append(
                f"| v{snap.version} | {_short_ts(snap.timestamp)} | "
                f"{fields_escaped} | {reason_escaped} |"
            )

        lines.append("")
        latest = self._snapshots[-1]
        lines.append(f"**当前设计（v{latest.version}，{_short_ts(latest.timestamp)}）：**")
        lines.append(f"- 主题：{latest.title}")
        lines.append(f"- 被解释变量：{latest.dependent_variable}")
        lines.append(f"- 样本：{latest.sample}")
        lines.append(f"- 识别策略：{latest.identification_method}")
        lines.append(
            f"- 数据源：{', '.join(latest.data_sources) if latest.data_sources else '（未指定）'}"
        )
        lines.append("")
        return "\n".join(lines)

    # ── 终端报告 ────────────────────────────────────────────────────────────

    def print_report(self) -> None:
        """打印 ANSI 高亮的研究设计演变报告。

        - has_diverged() 为 True 时，整体使用 YELLOW 突出，并提示需要披露演变轨迹。
        - has_diverged() 为 False 时，使用 CYAN / GREEN 显示稳定状态。
        """
        diverged = self.has_diverged()
        border_color = YELLOW if diverged else CYAN
        header_color = YELLOW if diverged else CYAN

        print()
        print(c("═" * 64, border_color))
        title = "  研究设计演变轨迹  Design Evolution Trail  "
        print(c("║", border_color) + c(title.center(58), header_color) + c(" ║", border_color))
        print(c("═" * 64, border_color))
        print()

        if not self._snapshots:
            print(c("  ⚠ 尚无任何设计版本记录", YELLOW))
            print()
            return

        if diverged:
            print(
                c(
                    "  ⚠ 研究设计在执行中发生实质性变更，请确保最终论文披露演变轨迹并更新设计文档。",
                    YELLOW,
                )
            )
            print()

        # 表格化输出
        print(
            f"  {c('版本', CYAN):<8} {c('时间', CYAN):<22} "
            f"{c('变更字段', CYAN):<32} {c('变更原因', CYAN)}"
        )
        print(c("  " + "─" * 60, border_color))
        for snap in self._snapshots:
            fields = ", ".join(snap.changed_fields) if snap.changed_fields else "—"
            reason = snap.change_reason or "—"
            v_color = YELLOW if "initial" not in snap.changed_fields and snap.changed_fields else CYAN
            print(
                f"  {c(f'v{snap.version}', v_color):<8} "
                f"{c(_short_ts(snap.timestamp), CYAN):<22} "
                f"{c(fields[:30], v_color):<32} {c(reason[:40], CYAN)}"
            )
        print()

        # 当前设计摘要
        latest = self._snapshots[-1]
        print(c("  当前设计（v{})".format(latest.version), BOLD))
        print(f"    主题：{latest.title}")
        print(f"    被解释变量：{latest.dependent_variable}")
        print(f"    样本：{latest.sample}")
        print(f"    识别策略：{latest.identification_method}")
        print(
            f"    数据源：{', '.join(latest.data_sources) if latest.data_sources else '（未指定）'}"
        )
        print()
        print(c("  实质性变更：" + ("是" if diverged else "否"), YELLOW if diverged else GREEN))
        print()

    # ── 内部：JSONL 持久化 ──────────────────────────────────────────────────

    def _persist_one(self, snapshot: DesignSnapshot) -> None:
        """追加一条 JSON 行到持久化文件。"""
        path = self.persistence_path
        if path is None:
            return
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot.as_dict(), ensure_ascii=False) + "\n")


# ── 工具函数 ────────────────────────────────────────────────────────────────


def new_versioning(project_dir: str | Path | None = None) -> DesignDocVersioning:
    """便捷工厂：创建并返回一个 DesignDocVersioning 实例。

    Args:
        project_dir: 可选项目目录，传 None 时不持久化。

    Returns:
        DesignDocVersioning 实例。
    """
    return DesignDocVersioning(project_dir=project_dir)


def _now_iso8601_utc() -> str:
    """当前时间的 ISO8601 UTC 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _short_ts(ts: str) -> str:
    """压缩时间戳到 19 字符（YYYY-MM-DDTHH:MM:SS），便于表格展示。"""
    if len(ts) >= 19:
        return ts[:19]
    return ts


def _diff_snapshots(previous: DesignSnapshot, new_fields: dict) -> list[str]:
    """对比新旧字段，返回发生变更的字段名列表（保持 TRACKED_FIELDS 顺序）。"""
    changed: list[str] = []
    for field_name in TRACKED_FIELDS:
        old_value = getattr(previous, field_name)
        new_value = new_fields[field_name]
        if field_name == "data_sources":
            if list(old_value) != list(new_value):
                changed.append(field_name)
        else:
            if str(old_value) != str(new_value):
                changed.append(field_name)
    return changed


__all__ = [
    "DesignSnapshot",
    "DesignDocVersioning",
    "new_versioning",
    "MATERIAL_FIELDS",
    "TRACKED_FIELDS",
]
