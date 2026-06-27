"""NoraOrchestrator tests (PR1, Audit 2026-06-27).

覆盖：
  - 5 轮顺序
  - 每轮必须 answer，不允许 silent fallback
  - rollback / resume 断点续传
  - 画像锁定后不可再修改
  - 变量解析
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from scripts.core.nora_orchestrator import (
    NoraOrchestrator,
    NoraStage,
    NoraState,
    ResearchProfile,
    VariableSet,
    VariableCandidate,
)


@pytest.fixture
def tmp_session(tmp_path) -> Path:
    return tmp_path / "nora_session"


# ─── Lifecycle ────────────────────────────────────────────────────────────────


def test_start_creates_session(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    state = orch.start("碳排放权交易对企业绿色创新的影响")

    assert state.topic == "碳排放权交易对企业绿色创新的影响"
    assert state.current_stage == NoraStage.QUESTION_TYPE
    assert not state.is_complete
    assert state.progress_pct == 0.0
    assert (tmp_session / "session_state.json").exists()


def test_start_rejects_empty_topic(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session)
    with pytest.raises(ValueError, match="non-empty"):
        orch.start("   ")


def test_next_question_returns_question_text(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, cli_mode=False)
    state = orch.start("test topic")

    question, options = orch.next_question(state)
    assert "实证" in question or "综述" in question
    assert len(options) >= 2  # 至少 2 个数字选项


# ─── Answer Submission ───────────────────────────────────────────────────────


def test_submit_answer_records_and_persists(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, cli_mode=False)
    state = orch.start("test topic")

    orch.submit_answer(state, "1")  # 实证研究
    assert state.answers[NoraStage.QUESTION_TYPE.value] == "1"
    assert (tmp_session / "01_question_type.json").exists()


def test_submit_answer_rejects_empty_when_not_auto_ack(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    state = orch.start("test topic")

    with pytest.raises(RuntimeError, match="empty answer not allowed"):
        orch.submit_answer(state, "   ")


def test_auto_ack_mode_accepts_empty(tmp_session):
    """仅测试用 auto_ack，生产必须 False。"""
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("test topic")
    # 不抛异常
    orch.submit_answer(state, "")
    assert state.answers[NoraStage.QUESTION_TYPE.value] == ""


# ─── Advance & Lock ──────────────────────────────────────────────────────────


def test_advance_through_all_stages_locks_profile(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("DID study of carbon trading")

    answers = {
        NoraStage.QUESTION_TYPE: "1",
        NoraStage.IDENTIFICATION: "1",  # DID
        NoraStage.SAMPLE: "2010-2022 中国 A 股上市公司",
        NoraStage.VARIABLES: "因变量 Y：绿色专利\n控制变量：Size, Lev, ROA",
        NoraStage.VENUE: "1",  # 经济研究
    }
    for stage, ans in answers.items():
        state.current_stage = stage
        orch.submit_answer(state, ans)
        state = orch.advance(state)

    assert state.is_complete
    assert state.profile is not None
    profile = state.profile
    assert profile.question_type == "empirical"
    assert profile.identification == "DID"
    assert profile.sample_window == "2010-2022"
    assert profile.geography == "China A-share"
    assert profile.unit == "firm"
    assert profile.venue == "经济研究"
    assert len(profile.variables.dependent) == 1
    assert len(profile.variables.control) == 3


def test_advance_after_complete_is_noop(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("test")
    state.profile = ResearchProfile(topic="test", locked_at=time.time())
    state.needs_user_input = False

    returned = orch.advance(state)
    assert returned is state
    assert state.is_complete


# ─── Rollback ────────────────────────────────────────────────────────────────


def test_rollback_clears_later_answers(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("test")

    # 完成所有阶段
    for stage, ans in [
        (NoraStage.QUESTION_TYPE, "1"),
        (NoraStage.IDENTIFICATION, "2"),
        (NoraStage.SAMPLE, "2015-2020 美国 S&P 500"),
        (NoraStage.VARIABLES, "Y: stock return"),
        (NoraStage.VENUE, "2"),
    ]:
        state.current_stage = stage
        orch.submit_answer(state, ans)
        state = orch.advance(state)
    assert state.is_complete

    # 回退到 SAMPLE 阶段
    state = orch.rollback(state, NoraStage.SAMPLE)
    assert not state.is_complete
    assert state.current_stage == NoraStage.SAMPLE
    # VARIABLES 和 VENUE 答案应被清除
    assert NoraStage.VARIABLES.value not in state.answers
    assert NoraStage.VENUE.value not in state.answers
    # 但 SAMPLE 答案保留
    assert NoraStage.SAMPLE.value in state.answers


# ─── Resume ──────────────────────────────────────────────────────────────────


def test_resume_restores_state(tmp_session):
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("resumable topic")

    # 完成 QUESTION_TYPE 后 advance（进入 IDENTIFICATION）
    state.current_stage = NoraStage.QUESTION_TYPE
    orch.submit_answer(state, "1")
    state = orch.advance(state)
    # 完成 IDENTIFICATION 后 advance（进入 SAMPLE）
    state.current_stage = NoraStage.IDENTIFICATION
    orch.submit_answer(state, "1")
    state = orch.advance(state)

    # 模拟中断 → 恢复
    new_orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    resumed = new_orch.resume(tmp_session)

    assert resumed.topic == "resumable topic"
    assert resumed.current_stage == NoraStage.SAMPLE
    assert resumed.answers[NoraStage.QUESTION_TYPE.value] == "1"
    assert resumed.answers[NoraStage.IDENTIFICATION.value] == "1"


def test_resume_raises_when_no_session(tmp_path):
    orch = NoraOrchestrator(output_dir=tmp_path / "nonexistent", cli_mode=False)
    with pytest.raises(FileNotFoundError):
        orch.resume(tmp_path / "nonexistent")


# ─── Variable Parsing ───────────────────────────────────────────────────────


def test_parse_variables_extracts_dependent_and_control():
    orch = NoraOrchestrator(output_dir=Path("/tmp"), cli_mode=False)
    text = """因变量 Y：TFP_OP
核心解释变量 X：DID
控制变量：
- Size
- Lev
- ROA
- Age"""

    variables = orch._parse_variables(text)
    assert len(variables.dependent) == 1
    assert variables.dependent[0].name == "TFP_OP"
    assert len(variables.control) >= 4


def test_parse_variables_handles_empty():
    orch = NoraOrchestrator(output_dir=Path("/tmp"), cli_mode=False)
    variables = orch._parse_variables("")
    assert len(variables.dependent) == 0
    assert len(variables.control) == 0


# ─── Profile Normalization ───────────────────────────────────────────────────


def test_normalize_choice_handles_chinese_keywords():
    orch = NoraOrchestrator(output_dir=Path("/tmp"), cli_mode=False)
    assert orch._normalize_choice("实证研究", {"1": "empirical", "实证": "empirical"}, "default") == "empirical"
    assert orch._normalize_choice("3", {"1": "A", "3": "C"}, "default") == "C"
    assert orch._normalize_choice("", {"1": "A"}, "default") == "default"


def test_extract_year_range():
    orch = NoraOrchestrator(output_dir=Path("/tmp"), cli_mode=False)
    assert orch._extract_year_range("2010-2022 中国 A 股") == "2010-2022"
    assert orch._extract_year_range("2015—2020 美国") == "2015-2020"
    assert orch._extract_year_range("无年份") == ""


def test_extract_geography_and_unit():
    orch = NoraOrchestrator(output_dir=Path("/tmp"), cli_mode=False)
    assert orch._extract_geography("2010-2022 中国 A 股上市公司") == "China A-share"
    assert orch._extract_geography("2015-2020 美国 S&P 500") == "USA-S&P"
    assert orch._extract_geography("2010-2020 省级面板") == "China-province"
    assert orch._extract_geography("家庭数据") == "China-household"

    assert orch._extract_unit("A 股上市公司") == "firm"
    assert orch._extract_unit("省级面板") == "province"
    assert orch._extract_unit("国家级") == "country"


# ─── Critical Audit Requirements ─────────────────────────────────────────────


def test_no_silent_fallback_in_real_mode(tmp_session):
    """回归测试：auto_ack=False 时必须禁止悄悄用空答案推进。"""
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    state = orch.start("critical test")

    # 模拟 5 轮全部留空（silent fallback 行为）
    with pytest.raises(RuntimeError):
        orch.submit_answer(state, "")

    # 即使填空字符串也不行
    with pytest.raises(RuntimeError):
        orch.submit_answer(state, "  \t\n")


def test_real_pipeline_does_not_use_mock_when_profile_missing(tmp_session):
    """架构守卫：缺失 profile 的状态不能用于流水线（让流水线有理由拒绝）。"""
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("test")
    # 未完成所有 5 轮
    orch.submit_answer(state, "1")
    state = orch.advance(state)  # 进入下一阶段
    assert not state.is_complete
    # profile 必须为 None
    assert state.profile is None


def test_completed_session_has_audit_trail(tmp_session):
    """完成的会话必须留有审计痕迹（每阶段单独 JSON）。"""
    orch = NoraOrchestrator(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = orch.start("audit trail test")

    for stage, ans in [
        (NoraStage.QUESTION_TYPE, "1"),
        (NoraStage.IDENTIFICATION, "1"),
        (NoraStage.SAMPLE, "2010-2020 中国 A 股"),
        (NoraStage.VARIABLES, "Y: TFP\nX: DID"),
        (NoraStage.VENUE, "1"),
    ]:
        state.current_stage = stage
        orch.submit_answer(state, ans)
        state = orch.advance(state)

    # 验证 5 个 ack 文件全部存在
    for fname in [
        "01_question_type.json",
        "02_identification.json",
        "03_sample.json",
        "04_variables.json",
        "05_venue.json",
    ]:
        assert (tmp_session / fname).exists(), f"Missing audit file: {fname}"
        data = json.loads((tmp_session / fname).read_text())
        assert "answer" in data
        assert "ts" in data