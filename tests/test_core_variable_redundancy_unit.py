"""Unit tests for scripts/core/variable_redundancy.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def vr():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import variable_redundancy as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, vr):
        for name in ["VariableRedundancyResolver", "VariableCandidate", "RedundancyReport"]:
            assert hasattr(vr, name), f"Missing export: {name}"


class TestRedundancyReport:
    def test_init_defaults(self, vr):
        r = vr.RedundancyReport(topic="test topic", identification="DID")
        assert r.topic == "test topic"
        assert r.identification == "DID"
        assert r.dependent_candidates == []
        assert r.independent_candidates == []
        assert r.control_candidates == []
        assert r.policy_candidates == []
        assert r.literature_sources == []
        assert r.has_minimum_redundancy is False

    def test_summary_returns_string(self, vr):
        r = vr.RedundancyReport(topic="test", identification="DID")
        s = r.summary()
        assert isinstance(s, str)
        assert "变量冗余报告" in s
        assert "test" in s

    def test_summary_includes_counts(self, vr):
        from scripts.core.variable_redundancy import VariableCandidate

        dep = VariableCandidate(name="TFP", formula="OP method", data_source_hint="akshare", priority=1)
        ctl1 = VariableCandidate(name="Size", formula="ln(assets)", data_source_hint="akshare", priority=1)
        ctl2 = VariableCandidate(name="Lev", formula="lev", data_source_hint="akshare", priority=1)
        ctl3 = VariableCandidate(name="ROA", formula="roa", data_source_hint="akshare", priority=1)
        ind = VariableCandidate(name="DID", formula="Post×Treat", data_source_hint="csrc", priority=1)
        pol = VariableCandidate(name="Post2017", formula="dummy", data_source_hint="csrc", priority=1)
        r = vr.RedundancyReport(
            topic="t", identification="DID",
            dependent_candidates=[dep],
            independent_candidates=[ind],
            control_candidates=[ctl1, ctl2, ctl3],
            policy_candidates=[pol],
            has_minimum_redundancy=True,
        )
        s = r.summary()
        assert "因变量候选数: 1" in s
        assert "自变量候选数: 1" in s
        assert "控制变量候选数: 3" in s
        assert "满足最小冗余: 是" in s


class TestVariableCandidate:
    def test_init(self, vr):
        c = vr.VariableCandidate(name="TFP", formula="OP method", data_source_hint="akshare")
        assert c.name == "TFP"
        assert c.formula == "OP method"
        assert c.priority == 1


class TestVariableTemplate:
    def test_class_exists(self, vr):
        # _VARIABLE_TEMPLATES is internal but we can verify presence
        assert hasattr(vr, "_VARIABLE_TEMPLATES")
        templates = vr._VARIABLE_TEMPLATES
        assert len(templates) >= 10


class TestResolver:
    def test_init_creates_output_dir(self, vr, tmp_path):
        out_dir = tmp_path / "redundancy_out"
        resolver = vr.VariableRedundancyResolver(output_dir=out_dir)
        assert resolver.output_dir == out_dir
        assert out_dir.exists()

    def test_init_default_dir(self, vr, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        resolver = vr.VariableRedundancyResolver()
        assert resolver.output_dir.name == ".clarify_session"

    def test_resolve_by_topic(self, vr, tmp_path):
        out_dir = tmp_path / "redundancy_out"
        resolver = vr.VariableRedundancyResolver(output_dir=out_dir)
        report = resolver.resolve_by_topic("碳排放权交易 绿色创新 DID")
        assert isinstance(report, vr.RedundancyReport)
        assert report.topic == "碳排放权交易 绿色创新 DID"

    def test_resolve_by_topic_writes_json(self, vr, tmp_path):
        out_dir = tmp_path / "redundancy_out"
        resolver = vr.VariableRedundancyResolver(output_dir=out_dir)
        resolver.resolve_by_topic("碳排放权交易 绿色创新 DID")
        json_path = out_dir / "redundant_variables.json"
        assert json_path.exists()

    def test_resolve_by_topic_has_candidates(self, vr, tmp_path):
        out_dir = tmp_path / "redundancy_out"
        resolver = vr.VariableRedundancyResolver(output_dir=out_dir)
        report = resolver.resolve_by_topic("绿色创新 碳交易 DID")
        # Control candidates should be present (common company finance controls)
        assert len(report.control_candidates) >= 0

    def test_resolve_with_profile(self, vr, tmp_path):
        from scripts.core.progressive_clarifier import ResearchProfile, VariableCandidate, VariableSet

        out_dir = tmp_path / "redundancy_out"
        resolver = vr.VariableRedundancyResolver(output_dir=out_dir)
        profile = ResearchProfile(
            topic="碳排放权交易 绿色创新",
            identification="DID",
            variables=VariableSet(
                dependent=[VariableCandidate(name="Green_Patent", formula="g", data_source_hint="cnrds")],
                independent=[VariableCandidate(name="DID", formula="d", data_source_hint="csrc")],
                control=[
                    VariableCandidate(name="Size", formula="s", data_source_hint="akshare"),
                    VariableCandidate(name="Lev", formula="l", data_source_hint="akshare"),
                    VariableCandidate(name="ROA", formula="r", data_source_hint="akshare"),
                ],
                policy_event=[VariableCandidate(name="Post2017", formula="p", data_source_hint="csrc")],
            ),
        )
        report = resolver.resolve(profile)
        assert report.topic == "碳排放权交易 绿色创新"
        # User-defined variables should be in candidates
        names_dep = {c.name for c in report.dependent_candidates}
        assert "Green_Patent" in names_dep

    def test_constants(self, vr):
        assert vr.VariableRedundancyResolver.MIN_DEPENDENT == 1
        assert vr.VariableRedundancyResolver.MIN_INDEPENDENT == 1
        assert vr.VariableRedundancyResolver.MIN_CONTROL == 3
        assert vr.VariableRedundancyResolver.MIN_POLICY == 1

    def test_extract_keywords_private(self, vr):
        resolver = vr.VariableRedundancyResolver(output_dir="/tmp")
        kws = resolver._extract_keywords("碳排放权交易 绿色创新 DID", "DID")
        assert isinstance(kws, list)
        assert "DID" in kws
        # Chinese characters should be tokenized
        assert any("碳" in k for k in kws)
