"""Unit tests for scripts/core/progressive_clarifier.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def pc():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import progressive_clarifier as m
    yield m
    if _p in sys.path:
        sys.path.remove(_p)


class TestModuleExports:
    def test_all_exports_present(self, pc):
        for name in [
            "ClarificationState",
            "ClarificationStage",
            "ResearchProfile",
            "ProgressiveClarifier",
            "VariableCandidate",
        ]:
            assert hasattr(pc, name), f"Missing export: {name}"


class TestClarificationStage:
    def test_stages(self, pc):
        stages = list(pc.ClarificationStage)
        assert len(stages) == 6
        assert pc.ClarificationStage.INTAKE.value == "intake"
        assert pc.ClarificationStage.QUESTION_TYPE.value == "question_type"
        assert pc.ClarificationStage.IDENTIFICATION.value == "identification"
        assert pc.ClarificationStage.SAMPLE.value == "sample"
        assert pc.ClarificationStage.VARIABLES.value == "variables"
        assert pc.ClarificationStage.VENUE.value == "venue"


class TestVariableCandidate:
    def test_init_defaults(self, pc):
        vc = pc.VariableCandidate(name="TFP", formula="OP", data_source_hint="akshare")
        assert vc.name == "TFP"
        assert vc.formula == "OP"
        assert vc.priority == 1

    def test_init_custom_priority(self, pc):
        vc = pc.VariableCandidate(name="X", formula="f", data_source_hint="d", priority=2)
        assert vc.priority == 2


class TestVariableSet:
    def test_default_init(self, pc):
        vs = pc.VariableSet()
        assert vs.dependent == []
        assert vs.independent == []
        assert vs.control == []
        assert vs.policy_event == []


class TestResearchProfile:
    def test_default_init(self, pc):
        p = pc.ResearchProfile(topic="test topic")
        assert p.topic == "test topic"
        assert p.question_type == ""
        assert p.identification == ""
        assert p.sample_window == ""
        assert p.geography == ""
        assert p.unit == ""
        assert p.venue == ""
        assert p.variables is not None
        assert p.raw_answers == {}
        assert p.locked_at == 0.0

    def test_full_init(self, pc):
        p = pc.ResearchProfile(
            topic="test",
            question_type="empirical",
            identification="DID",
            sample_window="2010-2022",
            geography="China A-share",
            unit="firm",
            venue="经济研究",
        )
        assert p.question_type == "empirical"
        assert p.identification == "DID"
        assert p.venue == "经济研究"


class TestClarificationState:
    def test_init_defaults(self, pc):
        s = pc.ClarificationState(topic="t")
        assert s.topic == "t"
        assert s.current_stage == pc.ClarificationStage.QUESTION_TYPE
        assert s.answers == {}
        assert s.history == []
        assert s.profile is None
        assert s.needs_user_input is True

    def test_is_complete_false(self, pc):
        s = pc.ClarificationState(topic="t")
        assert s.is_complete is False

    def test_is_complete_true(self, pc):
        s = pc.ClarificationState(
            topic="t",
            profile=pc.ResearchProfile(topic="t"),
        )
        assert s.is_complete is True

    def test_progress_pct_zero(self, pc):
        s = pc.ClarificationState(topic="t")
        assert s.progress_pct == 0.0

    def test_progress_pct_partial(self, pc):
        s = pc.ClarificationState(topic="t")
        s.answers = {"question_type": "1"}
        assert s.progress_pct == 20.0

    def test_progress_pct_full(self, pc):
        s = pc.ClarificationState(topic="t")
        s.answers = {
            "question_type": "1",
            "identification": "1",
            "sample": "1",
            "variables": "1",
            "venue": "1",
        }
        assert s.progress_pct == 100.0


class TestProgressiveClarifier:
    def test_init(self, pc, tmp_path):
        out_dir = tmp_path / "clarify"
        clarifier = pc.ProgressiveClarifier(output_dir=out_dir)
        assert clarifier.output_dir == out_dir
        assert clarifier.auto_ack is False
        assert clarifier.cli_mode is True

    def test_init_default(self, pc, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        clarifier = pc.ProgressiveClarifier()
        assert clarifier.output_dir.name == ".clarify_session"

    def test_init_auto_ack(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        assert clarifier.auto_ack is True

    def test_init_no_cli(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, cli_mode=False)
        assert clarifier.cli_mode is False

    def test_start_validates_topic(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path)
        with pytest.raises(ValueError):
            clarifier.start("")
        with pytest.raises(ValueError):
            clarifier.start("   ")

    def test_start_returns_state(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path)
        state = clarifier.start("碳排放权交易对绿色创新的影响")
        assert isinstance(state, pc.ClarificationState)
        assert state.topic == "碳排放权交易对绿色创新的影响"
        assert state.current_stage == pc.ClarificationStage.QUESTION_TYPE

    def test_next_question_incomplete(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, cli_mode=False)
        state = clarifier.start("test topic")
        question, options = clarifier.next_question(state)
        assert isinstance(question, str)
        assert isinstance(options, list)
        assert len(options) >= 1  # question_type has options

    def test_next_question_complete(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, cli_mode=False)
        state = pc.ClarificationState(
            topic="t",
            profile=pc.ResearchProfile(topic="t"),
        )
        question, options = clarifier.next_question(state)
        assert "画像已锁定" in question
        assert options == []

    def test_submit_answer_empty_raises(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path)
        state = clarifier.start("test topic")
        with pytest.raises(RuntimeError):
            clarifier.submit_answer(state, "")

    def test_submit_answer_strips_and_records(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        state = clarifier.start("test topic")
        clarifier.submit_answer(state, "  1  ")
        assert state.answers["question_type"] == "1"
        assert len(state.history) == 1

    def test_submit_answer_after_complete_raises(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        state = pc.ClarificationState(
            topic="t",
            profile=pc.ResearchProfile(topic="t"),
        )
        with pytest.raises(RuntimeError):
            clarifier.submit_answer(state, "answer")

    def test_advance_step_by_step(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        state = clarifier.start("test")
        assert state.current_stage == pc.ClarificationStage.QUESTION_TYPE

        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        assert state.current_stage == pc.ClarificationStage.IDENTIFICATION

        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        assert state.current_stage == pc.ClarificationStage.SAMPLE

        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        assert state.current_stage == pc.ClarificationStage.VARIABLES

        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        assert state.current_stage == pc.ClarificationStage.VENUE

        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        assert state.profile is not None
        assert state.is_complete is True

    def test_advance_complete_returns_same(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path)
        state = pc.ClarificationState(
            topic="t",
            profile=pc.ResearchProfile(topic="t"),
        )
        result = clarifier.advance(state)
        assert result is state

    def test_rollback_clears_subsequent_answers(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        state = clarifier.start("test")
        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        clarifier.submit_answer(state, "1")
        # Rollback to QUESTION_TYPE
        state = clarifier.rollback(state, pc.ClarificationStage.QUESTION_TYPE)
        assert state.current_stage == pc.ClarificationStage.QUESTION_TYPE
        assert "identification" not in state.answers
        assert "sample" not in state.answers

    def test_rollback_complete_resets(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path)
        state = pc.ClarificationState(
            topic="t",
            profile=pc.ResearchProfile(topic="t"),
        )
        state = clarifier.rollback(state, pc.ClarificationStage.SAMPLE)
        assert state.profile is None
        assert state.current_stage == pc.ClarificationStage.SAMPLE

    def test_extract_options(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        question = "Line 1\n1) Option A\n2) Option B\n3) Option C"
        options = clarifier._extract_options(question)
        assert len(options) == 3
        assert "Option A" in options[0]

    def test_normalize_choice_digit(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        result = clarifier._normalize_choice("1", {"1": "A", "2": "B"}, default="X")
        assert result == "A"

    def test_normalize_choice_keyword(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        result = clarifier._normalize_choice("I want 实测", {"实测": "empirical"}, default="X")
        assert result == "empirical"

    def test_normalize_choice_default(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        result = clarifier._normalize_choice("zzz unknown", {"1": "A"}, default="X")
        assert result == "X"

    def test_normalize_choice_empty(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        result = clarifier._normalize_choice("", {"1": "A"}, default="X")
        assert result == "X"

    def test_extract_year_range(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        assert clarifier._extract_year_range("2010-2022 数据") == "2010-2022"
        assert clarifier._extract_year_range("2010—2022 数据") == "2010-2022"
        assert clarifier._extract_year_range("2010–2022 数据") == "2010-2022"
        assert clarifier._extract_year_range("no years here") == ""

    def test_extract_geography(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        assert clarifier._extract_geography("中国A股上市公司") == "China A-share"
        assert clarifier._extract_geography("S&P 500") == "USA-S&P"
        assert clarifier._extract_geography("省级面板") == "China-province"
        assert clarifier._extract_geography("家庭数据") == "China-household"
        assert clarifier._extract_geography("未知地区") == ""

    def test_extract_unit(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        assert clarifier._extract_unit("公司层面") == "firm"
        assert clarifier._extract_unit("A 股数据") == "firm"
        assert clarifier._extract_unit("S&P 500") == "firm"
        assert clarifier._extract_unit("firm level") == "firm"
        assert clarifier._extract_unit("省级面板") == "province"
        assert clarifier._extract_unit("province level") == "province"
        assert clarifier._extract_unit("国家层面") == "country"
        assert clarifier._extract_unit("country level") == "country"
        assert clarifier._extract_unit("家庭数据") == "household"
        assert clarifier._extract_unit("household level") == "household"
        assert clarifier._extract_unit("未知") == ""

    def test_parse_variables_empty(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        vs = clarifier._parse_variables("")
        assert isinstance(vs, pc.VariableSet)
        assert vs.dependent == []

    def test_parse_variables_inline(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        text = "因变量 Y：TFP\n核心解释变量 X：DID\n控制变量：Size, Lev, ROA"
        vs = clarifier._parse_variables(text)
        assert len(vs.dependent) >= 1
        assert any(c.name == "TFP" for c in vs.dependent)
        assert len(vs.independent) >= 1
        assert any(c.name == "DID" for c in vs.independent)
        assert len(vs.control) >= 3
        assert any(c.name == "Size" for c in vs.control)

    def test_parse_variables_multiline(self, pc):
        clarifier = pc.ProgressiveClarifier(output_dir="/tmp")
        text = "控制变量：\n- Size\n- Lev\n- ROA\n- Age"
        vs = clarifier._parse_variables(text)
        assert len(vs.control) >= 4

    def test_resume_nonexistent_raises(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            clarifier.resume(tmp_path / "nonexistent_session")

    def test_resume_roundtrip(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        state = clarifier.start("test topic")
        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        # Now resume
        resumed = clarifier.resume(tmp_path)
        assert resumed.topic == "test topic"
        assert resumed.current_stage == pc.ClarificationStage.IDENTIFICATION
        assert resumed.answers == {"question_type": "1"}

    def test_build_profile_via_full_run(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, auto_ack=True)
        state = clarifier.start("test")
        # 1=empirical, 1=DID, sample with year range and geography
        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)
        clarifier.submit_answer(state, "2010-2022 中国A股上市公司")
        state = clarifier.advance(state)
        clarifier.submit_answer(
            state,
            "因变量 Y：TFP\n核心解释变量 X：DID\n控制变量：Size, Lev, ROA",
        )
        state = clarifier.advance(state)
        clarifier.submit_answer(state, "1")
        state = clarifier.advance(state)

        assert state.profile is not None
        assert state.profile.question_type == "empirical"
        assert state.profile.identification == "DID"
        assert state.profile.sample_window == "2010-2022"
        assert state.profile.geography == "China A-share"
        assert state.profile.unit == "firm"
        assert state.profile.venue == "经济研究"
        assert state.profile.locked_at > 0


class TestRunInteractiveRequiresCLI:
    def test_run_interactive_requires_cli_mode(self, pc, tmp_path):
        clarifier = pc.ProgressiveClarifier(output_dir=tmp_path, cli_mode=False)
        with pytest.raises(RuntimeError):
            clarifier.run_interactive("test")
