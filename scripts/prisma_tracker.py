"""PRISMA Flow Diagram Tracker.

PRISMA (Preferred Reporting Items for Systematic Reviews and Meta-Analyses)
is the standard protocol for conducting and reporting systematic literature reviews.

This module implements:
- PRISMA flow diagram stages
- Automatic document counting
- Exclusion reason tracking
- Report generation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── PRISMA Stages ──────────────────────────────────────────────────────────────


class PRISMAStage(Enum):
    """PRISMA flow diagram stages."""
    IDENTIFICATION = "identification"       # Records identified
    SCREENING = "screening"                 # Records screened
    ELIGIBILITY = "eligibility"             # Full-text assessed
    INCLUDED = "included"                  # Studies included


@dataclass
class PRISMARecord:
    """A single record in the PRISMA flow."""
    id: str
    source: str                             # e.g., "PubMed", "arXiv", "OpenAlex"
    date_added: datetime
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int = 0
    doi: str = ""
    status: str = "pending"                # pending, included, excluded
    exclusion_reason: str = ""             # If excluded
    notes: str = ""


@dataclass
class PRISMAFlow:
    """PRISMA flow diagram data."""
    # Stage 1: Identification
    records_database: int = 0              # Records from databases
    records_register: int = 0             # Records from registers
    records_other: int = 0                 # Records from other sources
    duplicates_removed: int = 0           # Duplicates removed

    # Stage 2: Screening
    records_screened: int = 0             # Records screened
    records_excluded: int = 0             # Records excluded (no abstract)

    # Stage 3: Eligibility
    full_text_assessed: int = 0          # Full-text assessed
    full_text_excluded: int = 0           # Full-text excluded
    exclusion_reasons: dict[str, int] = field(default_factory=dict)

    # Stage 4: Included
    studies_included: int = 0              # Studies included
    quantitative_synthesis: int = 0        # Studies in quantitative synthesis

    # Records
    records: list[PRISMARecord] = field(default_factory=list)

    def total_records(self) -> int:
        """Total records before deduplication."""
        return self.records_database + self.records_register + self.records_other

    def records_after_dedup(self) -> int:
        """Records after duplicate removal."""
        return self.total_records() - self.duplicates_removed

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "identification": {
                "records_database": self.records_database,
                "records_register": self.records_register,
                "records_other": self.records_other,
                "total": self.total_records(),
                "duplicates_removed": self.duplicates_removed,
            },
            "screening": {
                "records_screened": self.records_screened,
                "records_excluded": self.records_excluded,
                "passed_to_eligibility": self.records_screened - self.records_excluded,
            },
            "eligibility": {
                "full_text_assessed": self.full_text_assessed,
                "full_text_excluded": self.full_text_excluded,
                "exclusion_reasons": self.exclusion_reasons,
                "passed_to_included": self.full_text_assessed - self.full_text_excluded,
            },
            "included": {
                "studies_included": self.studies_included,
                "quantitative_synthesis": self.quantitative_synthesis,
            },
        }


# ─── PRISMA Tracker ─────────────────────────────────────────────────────────────


class PRISMATracker:
    """
    PRISMA Flow Diagram Tracker.

    Implements PRISMA 2020 guidelines for systematic literature reviews.
    Tracks all stages of the review process with automatic counting
    and report generation.
    """

    def __init__(self, topic: str):
        self.topic = topic
        self.flow = PRISMAFlow()
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        # Exclusion reason categories (PRISMA 2020)
        self.EXCLUSION_CATEGORIES = {
            "inappropriate_population": "不合适的研究人群",
            "inappropriate_intervention": "不合适的干预措施",
            "inappropriate_outcome": "不合适的结局指标",
            "wrong_study_design": "错误的研究设计",
            "duplicate": "重复发表",
            "unavailable_data": "无法获取全文",
            "non_english": "非英语文献",
            "abstract_only": "仅为摘要",
            "wrong_time_period": "超出时间范围",
            "other": "其他原因",
        }

    def add_records(
        self,
        count: int,
        source: str = "database",
        records: list[dict] | None = None,
    ) -> int:
        """
        Add records to the identification stage.

        Parameters
        ----------
        count : int
            Number of records to add.
        source : str
            Source of records: "database", "register", or "other".
        records : list, optional
            Detailed record information.

        Returns
        -------
        int
            New total record count.
        """
        if source == "database":
            self.flow.records_database += count
        elif source == "register":
            self.flow.records_register += count
        else:
            self.flow.records_other += count

        # Add detailed records if provided
        if records:
            for r in records:
                self.flow.records.append(PRISMARecord(
                    id=r.get("id", f"rec_{len(self.flow.records)}"),
                    source=source,
                    date_added=datetime.now(),
                    title=r.get("title", ""),
                    abstract=r.get("abstract", ""),
                    authors=r.get("authors", []),
                    year=r.get("year", 0),
                    doi=r.get("doi", ""),
                ))

        self.updated_at = datetime.now()
        return self.flow.total_records()

    def remove_duplicates(self, count: int):
        """Record duplicate removal."""
        self.flow.duplicates_removed += count
        self.updated_at = datetime.now()

    def screen_records(
        self,
        screened: int,
        excluded: int = 0,
        exclusion_reasons: dict[str, int] | None = None,
    ):
        """
        Update screening stage.

        Parameters
        ----------
        screened : int
            Total records screened.
        excluded : int
            Records excluded at screening.
        exclusion_reasons : dict
            Breakdown of exclusion reasons.
        """
        self.flow.records_screened = screened
        self.flow.records_excluded = excluded
        self.updated_at = datetime.now()

    def assess_eligibility(
        self,
        assessed: int,
        excluded: int,
        exclusion_reasons: dict[str, int],
    ):
        """
        Update eligibility assessment stage.

        Parameters
        ----------
        assessed : int
            Full-text articles assessed.
        excluded : int
            Articles excluded.
        exclusion_reasons : dict
            Breakdown of exclusion reasons.
        """
        self.flow.full_text_assessed = assessed
        self.flow.full_text_excluded = excluded
        self.flow.exclusion_reasons = exclusion_reasons
        self.updated_at = datetime.now()

    def include_studies(
        self,
        included: int,
        quantitative: int | None = None,
    ):
        """
        Update included studies count.

        Parameters
        ----------
        included : int
            Studies included in review.
        quantitative : int, optional
            Studies in quantitative synthesis (meta-analysis).
        """
        self.flow.studies_included = included
        self.flow.quantitative_synthesis = quantitative if quantitative else included
        self.updated_at = datetime.now()

    def update_record_status(
        self,
        record_id: str,
        status: str,
        exclusion_reason: str = "",
    ):
        """Update individual record status."""
        for record in self.flow.records:
            if record.id == record_id:
                record.status = status
                record.exclusion_reason = exclusion_reason
                break
        self.updated_at = datetime.now()

    def generate_diagram(self) -> str:
        """Generate PRISMA flow diagram in text format."""
        lines = []
        lines.append("```")
        lines.append("┌─────────────────────────────────────────────────────────────────────────┐")
        lines.append("│                    PRISMA Flow Diagram                                 │")
        lines.append("├─────────────────────────────────────────────────────────────────────────┤")
        lines.append("│ IDENTIFICATION                                                      │")
        lines.append("│                                                                     │")
        lines.append("│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │")
        lines.append("│  │ Records from    │  │ Records from    │  │ Records from    │        │")
        lines.append("│  │ databases       │  │ registers       │  │ other sources   │        │")
        lines.append(f"│  │ (n = {self.flow.records_database:>5})  │  │ (n = {self.flow.records_register:>5})  │  │ (n = {self.flow.records_other:>5})  │        │")
        lines.append("│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘        │")
        lines.append("│           │                      │                      │                  │")
        lines.append("│           └──────────────────────┼──────────────────────┘                  │")
        lines.append("│                                  │                                     │")
        lines.append(f"│                    Total records (n = {self.flow.total_records():>5})                     │")
        lines.append("│                                                                     │")
        lines.append("│                                  │                                     │")
        lines.append(f"│              Duplicates removed (n = {self.flow.duplicates_removed:>5})                       │")
        lines.append("│                                  │                                     │")
        lines.append(f"│                    Records after dedup (n = {self.flow.records_after_dedup():>5})                      │")
        lines.append("├─────────────────────────────────────────────────────────────────────────┤")
        lines.append("│ SCREENING                                                           │")
        lines.append("│                                                                     │")
        lines.append(f"│              Records screened (n = {self.flow.records_screened:>5})                          │")
        lines.append("│                                  │                                     │")
        lines.append(f"│        Records excluded (n = {self.flow.records_excluded:>5})                             │")
        lines.append("│                                  │                                     │")
        lines.append(f"│        Full-text assessed (n = {self.flow.full_text_assessed:>5})                         │")
        lines.append("├─────────────────────────────────────────────────────────────────────────┤")
        lines.append("│ ELIGIBILITY                                                         │")
        lines.append("│                                                                     │")
        lines.append(f"│      Full-text assessed (n = {self.flow.full_text_assessed:>5})                                │")
        lines.append("│                                  │                                     │")
        lines.append(f"│           Excluded (n = {self.flow.full_text_excluded:>5})                                   │")
        lines.append("│                                                                     │")

        # Exclusion reasons
        if self.flow.exclusion_reasons:
            for reason, count in self.flow.exclusion_reasons.items():
                reason_name = self.EXCLUSION_CATEGORIES.get(reason, reason)
                lines.append(f"│    - {reason_name}: {count}                                               │")

        lines.append("├─────────────────────────────────────────────────────────────────────────┤")
        lines.append("│ INCLUDED                                                            │")
        lines.append("│                                                                     │")
        lines.append(f"│         Studies included (n = {self.flow.studies_included:>5})                            │")
        lines.append("│                                                                     │")
        if self.flow.quantitative_synthesis > 0:
            lines.append(f"│    (with {self.flow.quantitative_synthesis} in quantitative synthesis)                       │")
        lines.append("└─────────────────────────────────────────────────────────────────────────┘")
        lines.append("```")

        return "\n".join(lines)

    def generate_report(self) -> str:
        """Generate complete PRISMA report."""
        lines = []
        lines.append(f"# PRISMA 流程报告: {self.topic}")
        lines.append("")
        lines.append(f"**生成时间**: {self.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Flow diagram
        lines.append("## 流程图")
        lines.append("")
        lines.append(self.generate_diagram())
        lines.append("")

        # Summary statistics
        lines.append("## 统计摘要")
        lines.append("")
        lines.append("| 阶段 | 数量 |")
        lines.append("|------|------|")
        lines.append(f"| 数据库检索 | {self.flow.records_database} |")
        lines.append(f"| 注册库 | {self.flow.records_register} |")
        lines.append(f"| 其他来源 | {self.flow.records_other} |")
        lines.append(f"| 去重 | {self.flow.duplicates_removed} |")
        lines.append(f"| 筛选 | {self.flow.records_screened} |")
        lines.append(f"| 全文评估 | {self.flow.full_text_assessed} |")
        lines.append(f"| 纳入研究 | {self.flow.studies_included} |")

        if self.flow.exclusion_reasons:
            lines.append("")
            lines.append("### 排除原因")
            lines.append("")
            lines.append("| 原因 | 数量 |")
            lines.append("|------|------|")
            for reason, count in self.flow.exclusion_reasons.items():
                reason_name = self.EXCLUSION_CATEGORIES.get(reason, reason)
                lines.append(f"| {reason_name} | {count} |")

        return "\n".join(lines)

    def export_json(self, path: str):
        """Export PRISMA data to JSON."""
        data = {
            "topic": self.topic,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "flow": self.flow.to_dict(),
            "exclusion_categories": self.EXCLUSION_CATEGORIES,
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_json(self, path: str):
        """Import PRISMA data from JSON."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.topic = data.get("topic", self.topic)
        self.created_at = datetime.fromisoformat(data["created_at"])
        self.updated_at = datetime.fromisoformat(data["updated_at"])

        flow_data = data["flow"]
        self.flow.records_database = flow_data["identification"]["records_database"]
        self.flow.records_register = flow_data["identification"]["records_register"]
        self.flow.records_other = flow_data["identification"]["records_other"]
        self.flow.duplicates_removed = flow_data["identification"]["duplicates_removed"]
        self.flow.records_screened = flow_data["screening"]["records_screened"]
        self.flow.records_excluded = flow_data["screening"]["records_excluded"]
        self.flow.full_text_assessed = flow_data["eligibility"]["full_text_assessed"]
        self.flow.full_text_excluded = flow_data["eligibility"]["full_text_excluded"]
        self.flow.exclusion_reasons = flow_data["eligibility"].get("exclusion_reasons", {})
        self.flow.studies_included = flow_data["included"]["studies_included"]
        self.flow.quantitative_synthesis = flow_data["included"]["quantitative_synthesis"]


# ─── CLI Interface ──────────────────────────────────────────────────────────────


def main():
    """CLI interface for PRISMA tracker."""
    import argparse

    parser = argparse.ArgumentParser(description="PRISMA Flow Diagram Tracker")
    parser.add_argument("--topic", type=str, required=True, help="Research topic")
    parser.add_argument("--add", type=int, help="Add records")
    parser.add_argument("--source", choices=["database", "register", "other"], default="database")
    parser.add_argument("--dedup", type=int, help="Remove duplicates")
    parser.add_argument("--screen", nargs=2, type=int, metavar=("SCREENED", "EXCLUDED"), help="Screen records")
    parser.add_argument("--eligibility", nargs="+", help="Assess eligibility (assessed excluded [reason:count...])")
    parser.add_argument("--include", type=int, help="Studies included")
    parser.add_argument("--export", type=str, help="Export to JSON")
    parser.add_argument("--import", dest="import_path", type=str, help="Import from JSON")
    parser.add_argument("--report", action="store_true", help="Generate report")
    args = parser.parse_args()

    tracker = PRISMATracker(args.topic)

    # Import if specified
    if args.import_path:
        tracker.import_json(args.import_path)

    # Operations
    if args.add:
        tracker.add_records(args.add, args.source)

    if args.dedup:
        tracker.remove_duplicates(args.dedup)

    if args.screen:
        screened, excluded = args.screen
        tracker.screen_records(screened, excluded)

    if args.eligibility:
        assessed = int(args.eligibility[0])
        excluded = int(args.eligibility[1])
        reasons = {}
        if len(args.eligibility) > 2:
            for item in args.eligibility[2:]:
                if ":" in item:
                    reason, count = item.split(":")
                    reasons[reason] = int(count)
        tracker.assess_eligibility(assessed, excluded, reasons)

    if args.include:
        tracker.include_studies(args.include)

    if args.export:
        tracker.export_json(args.export)
        print(f"Exported to {args.export}")

    if args.report:
        print(tracker.generate_report())


if __name__ == "__main__":
    main()
