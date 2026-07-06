"""tests/test_policy_database_smoke.py — Smoke tests for scripts/research_framework/policy_database.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework.policy_database import (
        PolicyDatabase,
        DEFAULT_DB_PATH,
        load_policy_database,
    )
except Exception as _exc:
    pytest.skip(f"policy_database not importable: {_exc}", allow_module_level=True)


# 测试用临时 JSON 数据库
TMP_DB_PATH = ROOT / "tests" / "_test_policy_database.json"


@pytest.fixture(scope="module")
def db_with_data():
    """提供一个含 3 条样例政策的 PolicyDatabase。"""
    sample = {
        "version": "1.0",
        "policies": [
            {
                "id": "POL-2015-新环保法",
                "name": "新环保法",
                "english_name": "New Environmental Protection Law",
                "category": "环境与能源政策",
                "policy_level": "national",
                "start_date": "2015-01-01",
                "description": "中华人民共和国环境保护法（2014修订）",
                "identification_strategy": "DID",
                "treated_units": "全国",
                "control_units": "无对照组（全国性政策）",
                "typical_variables": "重污染企业绩效、绿色创新",
                "key_confounders": ["同时期其他环保政策", "宏观经济周期"],
                "difficulty": "medium-high",
                "notes": "全国性政策难以找对照组",
                "literature_example": "Chen et al. (2018, JFE)",
                "data_availability": "CSMAR, Wind",
            },
            {
                "id": "POL-2013-营改增",
                "name": "营改增",
                "english_name": "Replace Business Tax with VAT",
                "category": "财税体制改革",
                "policy_level": "regional",
                "start_date": "2012-01-01",
                "description": "营业税改增值税试点",
                "identification_strategy": "DID (staggered)",
                "treated_units": "上海→全国",
                "control_units": "其他地区/行业",
                "typical_variables": "企业税负、固定资产投资",
                "key_confounders": ["地方财政自主权"],
                "difficulty": "medium",
                "notes": "三阶段 rollout",
                "literature_example": "Fan & Liu (2020)",
                "data_availability": "CSMAR, 税务年鉴",
            },
            {
                "id": "POL-2018-科创板",
                "name": "科创板设立",
                "english_name": "STAR Market Launch",
                "category": "资本市场改革",
                "policy_level": "national",
                "start_date": "2019-07-22",
                "description": "上海证券交易所科创板正式开市",
                "identification_strategy": "Event Study",
                "treated_units": "科创板上市公司",
                "control_units": "创业板/中小板上市公司",
                "typical_variables": "IPO 抑价、长期股票收益",
                "key_confounders": ["注册制改革预期"],
                "difficulty": "medium",
                "notes": "事件日明确",
                "literature_example": "Tian & Zheng (2021)",
                "data_availability": "CSMAR, Wind",
            },
        ],
    }
    with open(TMP_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False)
    db = PolicyDatabase(TMP_DB_PATH)
    db.load()
    yield db
    # 清理
    if TMP_DB_PATH.exists():
        TMP_DB_PATH.unlink()


class TestModuleLevel:
    def test_loads(self):
        assert PolicyDatabase is not None
        assert callable(load_policy_database)
        assert DEFAULT_DB_PATH.exists(), f"Default DB path missing: {DEFAULT_DB_PATH}"


class TestLoadRealDatabase:
    def test_load_real_database(self):
        """验证默认数据库可加载。"""
        if not DEFAULT_DB_PATH.exists():
            pytest.skip(f"Default DB missing: {DEFAULT_DB_PATH}")
        db = PolicyDatabase()
        db.load()
        assert db.total > 0
        assert db._loaded is True


class TestBasicQueries:
    def test_total(self, db_with_data):
        assert db_with_data.total == 3

    def test_get_by_id(self, db_with_data):
        p = db_with_data.get_by_id("POL-2015-新环保法")
        assert p is not None
        assert p["name"] == "新环保法"

    def test_get_by_id_missing(self, db_with_data):
        assert db_with_data.get_by_id("POL-XXXX-不存在") is None

    def test_get_by_name(self, db_with_data):
        p = db_with_data.get_by_name("营改增")
        assert p is not None
        assert p["id"] == "POL-2013-营改增"


class TestFilters:
    def test_filter_by_category(self, db_with_data):
        env_policies = db_with_data.filter_by_category("环境与能源政策")
        assert len(env_policies) == 1
        assert env_policies[0]["id"] == "POL-2015-新环保法"

    def test_filter_by_level(self, db_with_data):
        national = db_with_data.filter_by_level("national")
        assert len(national) == 2

    def test_filter_by_difficulty(self, db_with_data):
        medium_high = db_with_data.filter_by_difficulty("medium-high")
        assert len(medium_high) == 1

    def test_filter_by_identification(self, db_with_data):
        did = db_with_data.filter_by_identification("DID")
        # 3 条政策都有 DID 元素 (含 "DID (staggered)"、"DID")
        assert len(did) == 2

    def test_filter_by_year_range(self, db_with_data):
        policies_2014_plus = db_with_data.filter_by_year_range(start_year=2014)
        assert all(p["start_date"] >= "2014" for p in policies_2014_plus)


class TestSearch:
    def test_search_keyword(self, db_with_data):
        # "环保" 匹配新环保法
        results = db_with_data.search("环保")
        assert any(p["id"] == "POL-2015-新环保法" for p in results)

    def test_search_no_match(self, db_with_data):
        results = db_with_data.search("xxxxxxxnonexxxxxxx")
        assert results == []


class TestRecommendDesign:
    def test_recommend_by_id(self, db_with_data):
        rec = db_with_data.recommend_design("POL-2015-新环保法")
        assert "policy_name" in rec
        assert rec["policy_name"] == "新环保法"
        assert rec["recommended_identification"] == "DID"

    def test_recommend_not_found(self, db_with_data):
        rec = db_with_data.recommend_design("POL-XXXX-不存在")
        assert "error" in rec


class TestSummary:
    def test_summary_table(self, db_with_data):
        s = db_with_data.summary_table()
        assert s["total_policies"] == 3
        assert "by_category" in s
        assert "by_level" in s
        assert "by_difficulty" in s


class TestToDataframe:
    def test_to_dataframe(self, db_with_data):
        df = db_with_data.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "id" in df.columns
        assert "name" in df.columns
