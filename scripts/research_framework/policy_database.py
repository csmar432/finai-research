"""
policy_database.py — 中国政策实验数据库读取器

提供对中国主要准自然实验政策清单的结构化读取和查询。

Usage:
    from scripts.research_framework.policy_database import PolicyDatabase

    db = PolicyDatabase()
    db.load()

    # 按类别查询
    env_policies = db.filter_by_category("环境与能源政策")
    for p in env_policies:
        print(p["name"], p["difficulty"])

    # 按难度查询
    medium_policies = db.filter_by_difficulty("medium")

    # 按识别策略查询
    rdd_policies = db.filter_by_identification("RDD")

    # 搜索关键词
    results = db.search("碳")
    for p in results:
        print(p["name"], p["id"])

    # 生成推荐研究设计
    print(db.recommend_design("碳排放权交易"))
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

__all__ = ["PolicyDatabase", "load_policy_database"]

_log = logging.getLogger("policy_database")
_log.setLevel(logging.INFO)

# Default path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "policy_experiments" / "policy_database.json"


class PolicyDatabase:
    """
    中国政策实验数据库读取器。

    Attributes
    ----------
    policies : list[dict]
        所有政策条目。
    metadata : dict
        数据库元数据。

    Examples
    --------
    >>> db = PolicyDatabase()
    >>> db.load()
    >>> p = db.get_by_id("POL-2015-新环保法")
    >>> print(p["treated_units"])
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.policies: list[dict] = []
        self.metadata: dict = {}
        self._loaded = False

    def load(self) -> None:
        """加载政策数据库。"""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Policy database not found: {self.db_path}")

        with open(self.db_path, encoding="utf-8") as f:
            data = json.load(f)

        self.policies = data.get("policies", [])
        self.metadata = data.get("metadata", {})
        self._loaded = True
        _log.info(f"Loaded {len(self.policies)} policies from {self.db_path}")

    @property
    def total(self) -> int:
        return len(self.policies)

    def get_by_id(self, policy_id: str) -> dict | None:
        """通过ID获取政策。"""
        for p in self.policies:
            if p.get("id") == policy_id:
                return p
        return None

    def get_by_name(self, name: str) -> dict | None:
        """通过名称精确匹配获取政策。"""
        for p in self.policies:
            if p.get("name") == name or p.get("english_name") == name:
                return p
        return None

    def filter_by_category(self, category: str) -> list[dict]:
        """按政策类别筛选（如"环境与能源政策"、"资本市场改革"）。"""
        return [p for p in self.policies if p.get("category") == category]

    def filter_by_level(self, level: str) -> list[dict]:
        """按政策层级筛选（national / regional）。"""
        return [p for p in self.policies if p.get("policy_level") == level]

    def filter_by_difficulty(self, difficulty: str) -> list[dict]:
        """按研究难度筛选（low / medium / medium-high / high）。"""
        return [p for p in self.policies if p.get("difficulty") == difficulty]

    def filter_by_identification(self, method: str) -> list[dict]:
        """按识别策略筛选（如"DID"、"RDD"、"IV"、"合成控制法"）。"""
        method_lower = method.lower()
        results = []
        for p in self.policies:
            strategy = p.get("identification_strategy", "")
            if isinstance(strategy, str) and method_lower in strategy.lower():
                results.append(p)
        return results

    def filter_by_year_range(
        self, start_year: int | None = None, end_year: int | None = None
    ) -> list[dict]:
        """按政策时间范围筛选（基于start_date）。"""
        results = []
        for p in self.policies:
            start = p.get("start_date", "")
            if not start:
                continue
            year = int(start[:4])
            if start_year is not None and year < start_year:
                continue
            if end_year is not None and year > end_year:
                continue
            results.append(p)
        return results

    def search(self, keyword: str) -> list[dict]:
        """在政策名称、描述、机制、变量中搜索关键词。"""
        kw = keyword.lower()
        results = []
        for p in self.policies:
            fields = [
                p.get("name", ""),
                p.get("english_name", ""),
                p.get("description", ""),
                p.get("mechanism", ""),
                p.get("treated_units", ""),
                p.get("control_units", ""),
                p.get("typical_variables", ""),
                p.get("category", ""),
                p.get("sub_category", ""),
            ]
            if any(kw in str(f).lower() for f in fields):
                results.append(p)
        return results

    def recommend_design(self, policy_name_or_id: str) -> dict[str, Any]:
        """
        根据政策推荐研究设计框架。

        Returns a structured research design recommendation including:
        - Recommended identification strategy
        - Recommended control group
        - Key confounders to address
        - Typical outcome variables
        - Data sources
        - Notes on identification validity
        """
        p = self.get_by_id(policy_name_or_id)
        if p is None:
            p = self.get_by_name(policy_name_or_id)
        if p is None:
            matches = self.search(policy_name_or_id)
            if matches:
                p = matches[0]
        if p is None:
            return {"error": f"Policy not found: {policy_name_or_id}"}

        return {
            "policy_id": p.get("id"),
            "policy_name": p.get("name"),
            "category": p.get("category"),
            "period": f"{p.get('start_date', '')} to {p.get('end_date', '')}",
            "recommended_identification": p.get("identification_strategy"),
            "treated_units": p.get("treated_units"),
            "control_units": p.get("control_units"),
            "outcome_variables": p.get("typical_variables"),
            "data_sources": p.get("data_availability"),
            "key_confounders": p.get("key_confounders", []),
            "difficulty": p.get("difficulty"),
            "notes": p.get("notes"),
            "literature_reference": p.get("literature_example"),
            "geographic_scope": p.get("geographic_scope"),
        }

    def summary_table(self) -> dict[str, Any]:
        """生成政策数据库摘要表。"""
        return {
            "total_policies": self.total,
            "by_category": self._group_by("category"),
            "by_level": self._group_by("policy_level"),
            "by_difficulty": self._group_by("difficulty"),
            "by_identification": {
                "DID": len(self.filter_by_identification("DID")),
                "RDD": len(self.filter_by_identification("RDD")),
                "IV": len(self.filter_by_identification("IV")),
                "合成控制法": len(self.filter_by_identification("合成控制法")),
            },
        }

    def _group_by(self, field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.policies:
            val = p.get(field, "Unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts

    def to_dataframe(self) -> "pandas.DataFrame":
        """导出为pandas DataFrame（便于筛选和排序）。"""
        import pandas as pd

        rows = []
        for p in self.policies:
            rows.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "category": p.get("category"),
                "sub_category": p.get("sub_category"),
                "level": p.get("policy_level"),
                "start_date": p.get("start_date"),
                "end_date": p.get("end_date"),
                "difficulty": p.get("difficulty"),
                "identification": p.get("identification_strategy"),
                "treated_units": p.get("treated_units", "")[:50],
                "typical_variables": p.get("typical_variables", "")[:50],
            })
        return pd.DataFrame(rows)


def load_policy_database(db_path: str | Path | None = None) -> PolicyDatabase:
    """便捷函数：加载政策数据库。"""
    db = PolicyDatabase(db_path)
    db.load()
    return db


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="政策实验数据库查询工具")
    parser.add_argument("--search", "-s", help="搜索关键词")
    parser.add_argument("--category", "-c", help="按类别筛选")
    parser.add_argument("--method", "-m", help="按识别策略筛选 (DID/RDD/IV)")
    parser.add_argument("--difficulty", "-d", help="按难度筛选 (low/medium/high)")
    parser.add_argument("--recommend", "-r", help="推荐研究设计（输入政策ID或名称）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有政策")
    parser.add_argument("--summary", action="store_true", help="显示摘要统计")
    parser.add_argument(
        "--export-csv",
        "-e",
        metavar="FILE",
        help="导出为CSV文件",
    )

    args = parser.parse_args()

    db = PolicyDatabase()
    db.load()

    if args.list:
        print(f"\n{'='*70}")
        print(f"  政策实验数据库 — 共 {db.total} 个政策")
        print(f"{'='*70}")
        for p in db.policies:
            print(f"\n[{p['id']}] {p['name']}")
            print(f"  类别: {p['category']} | 难度: {p['difficulty']} | 识别: {p['identification_strategy']}")
            print(f"  时间: {p['start_date']} ~ {p['end_date']}")
            print(f"  描述: {p['description'][:60]}...")

    elif args.search:
        results = db.search(args.search)
        print(f"\n搜索 '{args.search}' → {len(results)} 个结果")
        for p in results:
            print(f"  [{p['id']}] {p['name']}")

    elif args.category:
        results = db.filter_by_category(args.category)
        print(f"\n类别 '{args.category}' → {len(results)} 个政策")
        for p in results:
            print(f"  [{p['id']}] {p['name']}")

    elif args.method:
        results = db.filter_by_identification(args.method)
        print(f"\n识别策略 '{args.method}' → {len(results)} 个政策")
        for p in results:
            print(f"  [{p['id']}] {p['name']}")

    elif args.difficulty:
        results = db.filter_by_difficulty(args.difficulty)
        print(f"\n难度 '{args.difficulty}' → {len(results)} 个政策")
        for p in results:
            print(f"  [{p['id']}] {p['name']}")

    elif args.recommend:
        rec = db.recommend_design(args.recommend)
        if "error" in rec:
            print(rec["error"])
        else:
            print(f"\n{'='*70}")
            print(f"  研究设计推荐: {rec['policy_name']}")
            print(f"{'='*70}")
            print(f"\n识别策略: {rec['recommended_identification']}")
            print(f"处理组: {rec['treated_units']}")
            print(f"对照组: {rec['control_units']}")
            print(f"典型因变量: {rec['outcome_variables']}")
            print(f"数据来源: {rec['data_sources']}")
            print(f"主要混淆因素: {', '.join(rec['key_confounders'])}")
            print(f"文献参考: {rec['literature_reference']}")
            print(f"难度: {rec['difficulty']}")
            print(f"注意事项: {rec['notes']}")

    elif args.summary:
        s = db.summary_table()
        print(f"\n{'='*50}")
        print(f"  数据库摘要")
        print(f"{'='*50}")
        print(f"\n总政策数: {s['total_policies']}")
        print(f"\n按类别:")
        for cat, n in s["by_category"].items():
            print(f"  {cat}: {n}")
        print(f"\n按层级:")
        for level, n in s["by_level"].items():
            print(f"  {level}: {n}")
        print(f"\n按难度:")
        for diff, n in s["by_difficulty"].items():
            print(f"  {diff}: {n}")
        print(f"\n按识别策略:")
        for method, n in s["by_identification"].items():
            print(f"  {method}: {n}")

    elif args.export_csv:
        df = db.to_dataframe()
        df.to_csv(args.export_csv, index=False, encoding="utf-8-sig")
        print(f"已导出至 {args.export_csv}")

    else:
        print("用法: python policy_database.py --list | --search KEY | --category CAT | --method DID | --recommend NAME | --summary")
        print("\n示例:")
        print("  python policy_database.py --list")
        print("  python policy_database.py --search 碳")
        print("  python policy_database.py --category 环境与能源政策")
        print("  python policy_database.py --method DID")
        print("  python policy_database.py --recommend 新环保法")
        print("  python policy_database.py --export-csv policies.csv")
