"""Tests for VariableRedundancyResolver and DataGate (PR2, Audit 2026-06-27)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.core.variable_redundancy import (
    VariableRedundancyResolver,
    RedundancyReport,
)
from scripts.core.data_gate import (
    DataGate,
    DataGateLevel,
    DataGateResult,
    RealDataError,
)
from scripts.core.progressive_clarifier import (
    ResearchProfile,
    VariableCandidate,
    VariableSet,
)


# ─── VariableRedundancyResolver Tests ─────────────────────────────────────────


def test_resolve_by_topic_carbon_trading():
    """碳排放主题应匹配到绿色专利、TFP、DID 等变量。"""
    resolver = VariableRedundancyResolver(output_dir=Path("/tmp/vr_test"))
    report = resolver.resolve_by_topic(
        "碳排放权交易对企业绿色创新的影响", identification="DID"
    )

    assert report.topic == "碳排放权交易对企业绿色创新的影响"
    assert len(report.dependent_candidates) >= 1
    assert len(report.control_candidates) >= 3
    assert report.has_minimum_redundancy is True
    # 绿色专利应被匹配
    dep_names = [v.name for v in report.dependent_candidates]
    assert "Green_Patent" in dep_names or "TFP_OP" in dep_names


def test_resolve_by_topic_esg_finance():
    """ESG 主题应匹配 ESG 评分、ROA 等变量。"""
    resolver = VariableRedundancyResolver(output_dir=Path("/tmp/vr_test2"))
    report = resolver.resolve_by_topic(
        "企业ESG表现与融资成本", identification="IV"
    )

    assert len(report.dependent_candidates) >= 1
    ctl_names = [v.name for v in report.control_candidates]
    assert "Size" in ctl_names
    assert "Lev" in ctl_names


def test_resolve_with_user_defined_variables():
    """用户已定义的变量优先级最高，不会被模板覆盖。"""
    profile = ResearchProfile(
        topic="数字金融对中小企业创新的影响",
        question_type="empirical",
        identification="DID",
    )
    profile.variables.dependent.append(
        VariableCandidate(
            name="Innovation_Index",
            formula="Composite innovation score",
            data_source_hint="问卷调查",
            priority=1,
        )
    )

    resolver = VariableRedundancyResolver(output_dir=Path("/tmp/vr_test3"))
    report = resolver.resolve(profile)

    dep_names = [v.name for v in report.dependent_candidates]
    assert "Innovation_Index" in dep_names
    # Innovation_Index 不应被替换为 Patent
    assert "Innovation_Index" in dep_names


def test_extract_keywords_chinese():
    """中文主题提取关键词。"""
    resolver = VariableRedundancyResolver(output_dir=Path("/tmp"))
    tokens = resolver._extract_keywords("碳排放权交易对绿色创新的影响", "DID")

    assert "碳" in tokens
    assert "碳排放" in tokens or "碳排" in tokens
    assert "DID" in tokens


def test_extract_keywords_english():
    """英文主题提取关键词。"""
    resolver = VariableRedundancyResolver(output_dir=Path("/tmp"))
    tokens = resolver._extract_keywords("Carbon trading innovation policy", "DID")

    assert "carbon" in tokens
    assert "trading" in tokens
    # DID identification 不转为小写（保留原始大小写）
    assert any(t.lower() == "did" for t in tokens)


def test_minimum_redundancy_threshold():
    """使用已知主题时，模板库应补充至少 3 个控制变量。"""
    profile = ResearchProfile(
        topic="碳排放权交易对企业绿色创新的影响",
        question_type="empirical",
        identification="DID",
    )
    # 只有 2 个用户定义控制变量
    profile.variables.control.append(VariableCandidate("X", "formula", "source", 1))
    profile.variables.control.append(VariableCandidate("Y", "formula", "source", 1))

    resolver = VariableRedundancyResolver(output_dir=Path("/tmp/vr_test4"))
    report = resolver.resolve(profile)

    # 碳排放主题会触发模板匹配，补充至少 3 个控制变量
    assert len(report.control_candidates) >= 3
    # 政策候选可能为空（"数字金融"主题无政策模板匹配）
    # 只要因变量 + 自变量 + 控制变量 ≥ 阈值即可
    assert report.has_minimum_redundancy is True


def test_redundancy_report_persists(tmp_path):
    """冗余报告应持久化到 JSON。"""
    resolver = VariableRedundancyResolver(output_dir=tmp_path)
    report = resolver.resolve_by_topic("测试主题", identification="DID")

    report_file = tmp_path / "redundant_variables.json"
    assert report_file.exists()

    data = json.loads(report_file.read_text())
    assert data["topic"] == "测试主题"
    assert data["has_minimum_redundancy"] is not None
    assert "dependent_candidates" in data


# ─── DataGate Tests ──────────────────────────────────────────────────────────────


def test_data_gate_missing_session_fails(tmp_path):
    """session_state.json 不存在 → 未就绪。"""
    gate = DataGate(session_dir=tmp_path, level=DataGateLevel.CHECKPOINT_ONLY)
    result = gate.check()

    assert result.is_ready is False
    assert any("session_state.json" in m for m in result.missing)


def test_data_gate_with_clarify_session_ready(tmp_path):
    """session_state.json + redundant_variables.json 存在 → 就绪。"""
    # 模拟 5 轮 完成
    (tmp_path / "session_state.json").write_text(json.dumps({
        "topic": "test",
        "current_stage": "venue",
        "answers": {},
        "is_complete": True,
    }))
    (tmp_path / "redundant_variables.json").write_text(json.dumps({
        "topic": "test",
        "has_minimum_redundancy": True,
        "dependent_candidates": [{"name": "TFP"}],
        "independent_candidates": [{"name": "DID"}],
        "control_candidates": [
            {"name": "Size"}, {"name": "Lev"}, {"name": "ROA"},
        ],
        "policy_candidates": [{"name": "Post"}],
    }))

    gate = DataGate(session_dir=tmp_path, level=DataGateLevel.PROVENANCE)
    result = gate.check()

    assert result.is_ready is True
    assert len(result.missing) == 0


def test_data_gate_warns_about_mock_data(tmp_path):
    """数据目录含 _mock 文件 → mock_ratio > 0 → 未就绪。"""
    (tmp_path / "session_state.json").write_text(json.dumps({
        "topic": "test",
        "current_stage": "venue",
        "answers": {},
        "is_complete": True,
    }))
    (tmp_path / "redundant_variables.json").write_text(json.dumps({
        "topic": "test",
        "has_minimum_redundancy": True,
        "dependent_candidates": [{"name": "TFP"}],
        "independent_candidates": [{"name": "DID"}],
        "control_candidates": [
            {"name": "Size"}, {"name": "Lev"}, {"name": "ROA"},
        ],
        "policy_candidates": [{"name": "Post"}],
    }))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "panel_mock_data.csv").write_text("a,b\n1,2\n")

    gate = DataGate(session_dir=tmp_path, level=DataGateLevel.PROVENANCE)
    result = gate.check()

    # mock_ratio > 0 → 数据未就绪
    assert result.is_ready is False
    assert result.mock_ratio > 0
    assert any("mock" in w.lower() for w in result.warnings)


def test_data_gate_enforce_raises(tmp_path):
    """enforce() 在未就绪时应抛 RealDataError。"""
    gate = DataGate(session_dir=tmp_path, level=DataGateLevel.FULL)
    with pytest.raises(RealDataError):
        gate.enforce()


def test_data_gate_writes_gate_files(tmp_path):
    """check() 应写 gate.json 和 blocked.json。"""
    gate = DataGate(session_dir=tmp_path)
    gate.check()

    assert (tmp_path / "gate.json").exists()
    # blocked.json 只在 is_ready=False 时写入
    assert (tmp_path / "blocked.json").exists()


def test_data_gate_full_result_has_block_message():
    """未就绪时 block_message 不为空。"""
    result = DataGateResult(
        is_ready=False,
        level=DataGateLevel.PROVENANCE,
        gate_file=Path("/tmp/gate.json"),
        missing=["session_state.json 不存在"],
        warnings=["mock 数据"],
        mock_ratio=0.5,
    )

    msg = result.block_message
    assert len(msg) > 0
    assert "session_state.json" in msg
    assert "模拟数据" in msg or "mock" in msg.lower()


def test_is_pipeline_blocked(tmp_path):
    """is_pipeline_blocked() 应返回 blocked.json 是否存在。"""
    from scripts.core.data_gate import DataGate
    assert DataGate.is_pipeline_blocked(tmp_path) is False

    (tmp_path / "blocked.json").write_text(json.dumps({"blocked": True}))
    assert DataGate.is_pipeline_blocked(tmp_path) is True


# ─── Integration: 5 轮 + VariableRedundancy + DataGate ────────────────────────


def test_full_pipeline_nora_to_datagate(tmp_path):
    """端到端：5 轮 完成 → 变量冗余解析 → DataGate 通过。"""
    # 1. 5 轮 完成
    (tmp_path / "session_state.json").write_text(json.dumps({
        "topic": "数字金融对中小企业创新的影响",
        "current_stage": "venue",
        "answers": {},
        "is_complete": True,
    }))

    # 2. 变量冗余解析
    resolver = VariableRedundancyResolver(output_dir=tmp_path)
    report = resolver.resolve_by_topic(
        "数字金融对中小企业创新的影响", identification="DID"
    )
    assert report.has_minimum_redundancy is True

    # 3. DataGate 检查
    gate = DataGate(session_dir=tmp_path, level=DataGateLevel.PROVENANCE)
    result = gate.check()

    assert result.is_ready is True
    assert len(result.missing) == 0