"""ProgressiveClarifier tests (rename from NoraOrchestrator, 2026-06-27).

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

from scripts.core.progressive_clarifier import (
    ProgressiveClarifier,
    ClarificationStage,
    ClarificationState,
    ResearchProfile,
    VariableSet,
    VariableCandidate,
)


@pytest.fixture
def tmp_session(tmp_path) -> Path:
    return tmp_path / "clarify_session"


# ─── Lifecycle ────────────────────────────────────────────────────────────────


def test_start_creates_session(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    state = clarifier.start("碳排放权交易对企业绿色创新的影响")

    assert state.topic == "碳排放权交易对企业绿色创新的影响"
    assert state.current_stage == ClarificationStage.QUESTION_TYPE
    assert not state.is_complete
    assert state.progress_pct == 0.0
    assert (tmp_session / "session_state.json").exists()


def test_start_rejects_empty_topic(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session)
    with pytest.raises(ValueError, match="non-empty"):
        clarifier.start("   ")


def test_next_question_returns_question_text(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, cli_mode=False)
    state = clarifier.start("test topic")

    question, options = clarifier.next_question(state)
    assert "实证" in question or "综述" in question
    assert len(options) >= 2  # 至少 2 个数字选项


# ─── Answer Submission ───────────────────────────────────────────────────────


def test_submit_answer_records_and_persists(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, cli_mode=False)
    state = clarifier.start("test topic")

    clarifier.submit_answer(state, "1")  # 实证研究
    assert state.answers[ClarificationStage.QUESTION_TYPE.value] == "1"
    assert (tmp_session / "01_question_type.json").exists()


def test_submit_answer_rejects_empty_when_not_auto_ack(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    state = clarifier.start("test topic")

    with pytest.raises(RuntimeError, match="empty answer not allowed"):
        clarifier.submit_answer(state, "   ")


def test_auto_ack_mode_accepts_empty(tmp_session):
    """仅测试用 auto_ack，生产必须 False。"""
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("test topic")
    # 不抛异常
    clarifier.submit_answer(state, "")
    assert state.answers[ClarificationStage.QUESTION_TYPE.value] == ""


# ─── Advance & Lock ──────────────────────────────────────────────────────────


def test_advance_through_all_stages_locks_profile(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("DID study of carbon trading")

    answers = {
        ClarificationStage.QUESTION_TYPE: "1",
        ClarificationStage.IDENTIFICATION: "1",  # DID
        ClarificationStage.SAMPLE: "2010-2022 中国 A 股上市公司",
        ClarificationStage.VARIABLES: "因变量 Y：绿色专利\n控制变量：Size, Lev, ROA",
        ClarificationStage.VENUE: "1",  # 经济研究
    }
    for stage, ans in answers.items():
        state.current_stage = stage
        clarifier.submit_answer(state, ans)
        state = clarifier.advance(state)

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
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("test")
    state.profile = ResearchProfile(topic="test", locked_at=time.time())
    state.needs_user_input = False

    returned = clarifier.advance(state)
    assert returned is state
    assert state.is_complete


# ─── Rollback ────────────────────────────────────────────────────────────────


def test_rollback_clears_later_answers(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("test")

    # 完成所有阶段
    for stage, ans in [
        (ClarificationStage.QUESTION_TYPE, "1"),
        (ClarificationStage.IDENTIFICATION, "2"),
        (ClarificationStage.SAMPLE, "2015-2020 美国 S&P 500"),
        (ClarificationStage.VARIABLES, "Y: stock return"),
        (ClarificationStage.VENUE, "2"),
    ]:
        state.current_stage = stage
        clarifier.submit_answer(state, ans)
        state = clarifier.advance(state)
    assert state.is_complete

    # 回退到 SAMPLE 阶段
    state = clarifier.rollback(state, ClarificationStage.SAMPLE)
    assert not state.is_complete
    assert state.current_stage == ClarificationStage.SAMPLE
    # VARIABLES 和 VENUE 答案应被清除
    assert ClarificationStage.VARIABLES.value not in state.answers
    assert ClarificationStage.VENUE.value not in state.answers
    # 但 SAMPLE 答案保留
    assert ClarificationStage.SAMPLE.value in state.answers


# ─── Resume ──────────────────────────────────────────────────────────────────


def test_resume_restores_state(tmp_session):
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("resumable topic")

    # 完成 QUESTION_TYPE 后 advance（进入 IDENTIFICATION）
    state.current_stage = ClarificationStage.QUESTION_TYPE
    clarifier.submit_answer(state, "1")
    state = clarifier.advance(state)
    # 完成 IDENTIFICATION 后 advance（进入 SAMPLE）
    state.current_stage = ClarificationStage.IDENTIFICATION
    clarifier.submit_answer(state, "1")
    state = clarifier.advance(state)

    # 模拟中断 → 恢复
    new_clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    resumed = new_clarifier.resume(tmp_session)

    assert resumed.topic == "resumable topic"
    assert resumed.current_stage == ClarificationStage.SAMPLE
    assert resumed.answers[ClarificationStage.QUESTION_TYPE.value] == "1"
    assert resumed.answers[ClarificationStage.IDENTIFICATION.value] == "1"


def test_resume_raises_when_no_session(tmp_path):
    clarifier = ProgressiveClarifier(output_dir=tmp_path / "nonexistent", cli_mode=False)
    with pytest.raises(FileNotFoundError):
        clarifier.resume(tmp_path / "nonexistent")


# ─── Variable Parsing ───────────────────────────────────────────────────────


def test_parse_variables_extracts_dependent_and_control():
    clarifier = ProgressiveClarifier(output_dir=Path("/tmp"), cli_mode=False)
    text = """因变量 Y：TFP_OP
核心解释变量 X：DID
控制变量：
- Size
- Lev
- ROA
- Age"""

    variables = clarifier._parse_variables(text)
    assert len(variables.dependent) == 1
    assert variables.dependent[0].name == "TFP_OP"
    assert len(variables.control) >= 4


def test_parse_variables_handles_empty():
    clarifier = ProgressiveClarifier(output_dir=Path("/tmp"), cli_mode=False)
    variables = clarifier._parse_variables("")
    assert len(variables.dependent) == 0
    assert len(variables.control) == 0


# ─── Profile Normalization ───────────────────────────────────────────────────


def test_normalize_choice_handles_chinese_keywords():
    clarifier = ProgressiveClarifier(output_dir=Path("/tmp"), cli_mode=False)
    assert clarifier._normalize_choice("实证研究", {"1": "empirical", "实证": "empirical"}, "default") == "empirical"
    assert clarifier._normalize_choice("3", {"1": "A", "3": "C"}, "default") == "C"
    assert clarifier._normalize_choice("", {"1": "A"}, "default") == "default"


def test_extract_year_range():
    clarifier = ProgressiveClarifier(output_dir=Path("/tmp"), cli_mode=False)
    assert clarifier._extract_year_range("2010-2022 中国 A 股") == "2010-2022"
    assert clarifier._extract_year_range("2015—2020 美国") == "2015-2020"
    assert clarifier._extract_year_range("无年份") == ""


def test_extract_geography_and_unit():
    clarifier = ProgressiveClarifier(output_dir=Path("/tmp"), cli_mode=False)
    assert clarifier._extract_geography("2010-2022 中国 A 股上市公司") == "China A-share"
    assert clarifier._extract_geography("2015-2020 美国 S&P 500") == "USA-S&P"
    assert clarifier._extract_geography("2010-2020 省级面板") == "China-province"
    assert clarifier._extract_geography("家庭数据") == "China-household"

    assert clarifier._extract_unit("A 股上市公司") == "firm"
    assert clarifier._extract_unit("省级面板") == "province"
    assert clarifier._extract_unit("国家级") == "country"


# ─── Critical Audit Requirements ─────────────────────────────────────────────


def test_no_silent_fallback_in_real_mode(tmp_session):
    """回归测试：auto_ack=False 时必须禁止悄悄用空答案推进。"""
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=False, cli_mode=False)
    state = clarifier.start("critical test")

    # 模拟 5 轮全部留空（silent fallback 行为）
    with pytest.raises(RuntimeError):
        clarifier.submit_answer(state, "")

    # 即使填空字符串也不行
    with pytest.raises(RuntimeError):
        clarifier.submit_answer(state, "  \t\n")


def test_real_pipeline_does_not_use_mock_when_profile_missing(tmp_session):
    """架构守卫：缺失 profile 的状态不能用于流水线（让流水线有理由拒绝）。"""
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("test")
    # 未完成所有 5 轮
    clarifier.submit_answer(state, "1")
    state = clarifier.advance(state)  # 进入下一阶段
    assert not state.is_complete
    # profile 必须为 None
    assert state.profile is None


def test_completed_session_has_audit_trail(tmp_session):
    """完成的会话必须留有审计痕迹（每阶段单独 JSON）。"""
    clarifier = ProgressiveClarifier(output_dir=tmp_session, auto_ack=True, cli_mode=False)
    state = clarifier.start("audit trail test")

    for stage, ans in [
        (ClarificationStage.QUESTION_TYPE, "1"),
        (ClarificationStage.IDENTIFICATION, "1"),
        (ClarificationStage.SAMPLE, "2010-2020 中国 A 股"),
        (ClarificationStage.VARIABLES, "Y: TFP\nX: DID"),
        (ClarificationStage.VENUE, "1"),
    ]:
        state.current_stage = stage
        clarifier.submit_answer(state, ans)
        state = clarifier.advance(state)

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
