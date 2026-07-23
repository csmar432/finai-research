"""Minimal unit tests for scripts/core/analyst.py.

Covers dataclasses/enums from the consolidated analyst module without
instantiating heavy LLM-backed agents or orchestrators.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def analyst():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.core import analyst as a
    yield a
    if _p in sys.path:
        sys.path.remove(_p)


# ───────────────────────── module surface ─────────────────────────


class TestAnalystModuleSurface:
    def test_module_imports(self, analyst):
        assert analyst is not None

    def test_exposes_analyst_agents_block(self, analyst):
        for name in [
            "AnalystType",
            "AnalystConfig",
            "AnalystResult",
            "DupontDecomposition",
            "DCFScenario",
            "AccrualsAnalysis",
            "AnalystFactory",
        ]:
            assert hasattr(analyst, name), f"missing {name}"

    def test_exposes_ai_parliament_block(self, analyst):
        for name in [
            "MemberType",
            "MemberConfig",
            "DebateRound",
            "RebuttalRound",
            "Verdict",
            "AIParliament",
        ]:
            assert hasattr(analyst, name), f"missing {name}"

    def test_exposes_multi_agent_block(self, analyst):
        for name in [
            "TaskStatus",
            "ExecutionMode",
            "Agent",
            "Task",
            "Workflow",
            "MultiAgentOrchestrator",
        ]:
            assert hasattr(analyst, name), f"missing {name}"

    def test_exposes_collaboration_block(self, analyst):
        for name in [
            "OperationType",
            "Operation",
            "UserPresence",
            "PaperSnapshot",
            "ConflictResolution",
            "CollaborationServer",
        ]:
            assert hasattr(analyst, name), f"missing {name}"

    def test_exposes_specialized_agents_block(self, analyst):
        for name in [
            "AgentTask",
            "ReviewFinding",
            "AgentReviewResult",
            "ProofreaderAgent",
            "AdversarialQAAgent",
            "LiteratureGapAgent",
            "DataAuditAgent",
        ]:
            assert hasattr(analyst, name), f"missing {name}"


# ───────────────────────── analyst_agents dataclasses ─────────────────────────


class TestAnalystTypeEnum:
    def test_values(self, analyst):
        assert analyst.AnalystType.FUNDAMENTAL_MARKET.value == "fundamental_market"
        assert analyst.AnalystType.VALUATION.value == "valuation"
        assert analyst.AnalystType.RISK.value == "risk"


class TestAnalystConfig:
    def test_init(self, analyst):
        cfg = analyst.AnalystConfig(
            analyst_type=analyst.AnalystType.VALUATION,
            name="v",
            role="valuation analyst",
            focus_areas=["DCF"],
            tools=["tushare"],
            max_iterations=3,
            temperature=0.2,
        )
        assert cfg.analyst_type is analyst.AnalystType.VALUATION
        assert cfg.max_iterations == 3
        assert cfg.focus_areas == ["DCF"]

    def test_fields(self, analyst):
        names = {f.name for f in dataclasses.fields(analyst.AnalystConfig)}
        assert {"analyst_type", "name", "role", "focus_areas",
                "tools", "max_iterations", "temperature"} <= names


class TestAnalystResult:
    def test_init(self, analyst):
        r = analyst.AnalystResult(
            analyst_type=analyst.AnalystType.RISK,
            status="ok",
            findings={"beta": 1.1},
            confidence=0.9,
            key_points=["k"],
            warnings=["w"],
            latency_ms=10.0,
        )
        assert r.analyst_type is analyst.AnalystType.RISK
        assert r.findings["beta"] == 1.1
        assert r.latency_ms == 10.0


class TestDupontDecomposition:
    def test_init(self, analyst):
        d = analyst.DupontDecomposition(
            company="ABC",
            year=2024,
            roe=0.18,
            net_margin=0.10,
            asset_turnover=1.0,
            equity_multiplier=1.8,
            roa=0.10,
            comparison={},
        )
        assert d.company == "ABC"
        assert d.year == 2024
        assert d.roe == pytest.approx(0.18)


class TestDCFScenario:
    def test_init(self, analyst):
        s = analyst.DCFScenario(
            name="base",
            revenue_growth=0.05,
            operating_margin=0.20,
            terminal_growth=0.02,
            wacc=0.08,
            equity_value=1_000_000.0,
            target_price=12.5,
            upside=0.10,
        )
        assert s.name == "base"
        assert s.target_price == pytest.approx(12.5)


class TestAccrualsAnalysis:
    def test_init(self, analyst):
        a = analyst.AccrualsAnalysis(
            year=2023,
            total_accruals=0.05,
            abnormal_accruals=0.01,
            discretionary_accruals=0.005,
            is_suspicious=False,
        )
        assert a.year == 2023
        assert a.is_suspicious is False


# ───────────────────────── ai_parliament dataclasses ─────────────────────────


class TestMemberTypeEnum:
    def test_values(self, analyst):
        assert analyst.MemberType.CHAIR.value == "chair"
        assert analyst.MemberType.MEMBER_FINANCE.value == "member_finance"


class TestMemberConfig:
    def test_init(self, analyst):
        c = analyst.MemberConfig(
            member_type=analyst.MemberType.MEMBER_FINANCE,
            name="finance-member",
            role="finance reviewer",
            model="gpt-4",
            expertise=["valuation"],
            perspective="long-term",
        )
        assert c.member_type is analyst.MemberType.MEMBER_FINANCE
        assert "valuation" in c.expertise


class TestDebateRound:
    def test_init(self, analyst):
        d = analyst.DebateRound(
            round_number=1,
            speaker=analyst.MemberType.CHAIR,
            content="opening",
            timestamp=0.0,
        )
        assert d.round_number == 1
        assert d.content == "opening"


class TestRebuttalRound:
    def test_init(self, analyst):
        r = analyst.RebuttalRound(
            round_num=2,
            member_type=analyst.MemberType.MEMBER_STATISTICS,
            response_to_summary="I disagree",
            strength="strong",
        )
        assert r.round_num == 2
        assert r.strength == "strong"


class TestVerdict:
    def test_init(self, analyst):
        v = analyst.Verdict(
            score=8.5,
            recommendation="accept",
            summary="good",
            key_strengths=["s1"],
            key_weaknesses=["w1"],
            debate_rounds=[],
            rebuttal_rounds=[],
            disputed=False,
            all_arguments=[],
        )
        assert v.score == pytest.approx(8.5)
        assert v.recommendation == "accept"
        assert v.disputed is False


# ───────────────────────── multi_agent dataclasses ─────────────────────────


class TestTaskStatusEnum:
    def test_values(self, analyst):
        assert analyst.TaskStatus.PENDING.value == "pending"
        assert analyst.TaskStatus.COMPLETED.value == "completed"
        assert analyst.TaskStatus.FAILED.value == "failed"


class TestExecutionModeEnum:
    def test_values(self, analyst):
        assert analyst.ExecutionMode.SEQUENTIAL.value == "sequential"
        assert analyst.ExecutionMode.PARALLEL.value == "parallel"


class TestAgentDataclass:
    def test_init(self, analyst):
        ag = analyst.Agent(
            agent_id="a1",
            name="alpha",
            role="researcher",
            capabilities=["search"],
            system_prompt="be concise",
            max_concurrent=2,
        )
        assert ag.agent_id == "a1"
        assert ag.max_concurrent == 2


class TestTaskDataclass:
    def test_init(self, analyst):
        t = analyst.Task(
            task_id="t1",
            name="t",
            description="do something",
            required_capabilities=["search"],
            input_data={"q": "x"},
            status=analyst.TaskStatus.PENDING,
        )
        assert t.task_id == "t1"
        assert t.status is analyst.TaskStatus.PENDING
        assert t.assigned_agent_id is None
        assert t.result is None


class TestWorkflowDataclass:
    def test_init(self, analyst):
        ag = analyst.Agent(
            agent_id="a1", name="alpha", role="r",
            capabilities=[], system_prompt="", max_concurrent=1,
        )
        w = analyst.Workflow(
            workflow_id="w1",
            name="wf",
            description="d",
            agents=[ag],
            tasks=[],
            execution_mode=analyst.ExecutionMode.SEQUENTIAL,
            dependencies={},
        )
        assert w.workflow_id == "w1"
        assert w.execution_mode is analyst.ExecutionMode.SEQUENTIAL


# ───────────────────────── collaboration dataclasses ─────────────────────────


class TestOperationTypeEnum:
    def test_values(self, analyst):
        assert analyst.OperationType.INSERT.value == "insert"
        assert analyst.OperationType.DELETE.value == "delete"
        assert analyst.OperationType.SECTION_ADD.value == "section_add"


class TestOperationDataclass:
    def test_init(self, analyst):
        op = analyst.Operation(
            op_id="o1",
            user_id="u1",
            paper_id="p1",
            section="intro",
            op_type=analyst.OperationType.INSERT,
            position=0,
            content="hello",
            length=5,
            timestamp=1.0,
            version=1,
            parent_op_id=None,
        )
        assert op.op_id == "o1"
        assert op.op_type is analyst.OperationType.INSERT
        assert op.parent_op_id is None


class TestUserPresence:
    def test_init(self, analyst):
        u = analyst.UserPresence(
            user_id="u1",
            paper_id="p1",
            section="intro",
            cursor_position=10,
            selection_start=10,
            selection_end=20,
            color="#ff0000",
            last_seen=1.0,
            is_active=True,
        )
        assert u.cursor_position == 10
        assert u.is_active is True


class TestPaperSnapshot:
    def test_init(self, analyst):
        s = analyst.PaperSnapshot(
            version=1,
            paper_id="p1",
            content={"intro": "hello"},
            author_id="u1",
            timestamp=0.0,
            message="init",
            parent_version=0,
        )
        assert s.version == 1
        assert s.parent_version == 0
        assert s.content["intro"] == "hello"


class TestConflictResolution:
    def test_init(self, analyst):
        c = analyst.ConflictResolution(
            resolved=True,
            winning_version=2,
            losing_version=1,
            resolution_type="auto",
            merged_content="merged",
            conflict_regions=[],
            suggestion="keep both",
        )
        assert c.resolved is True
        assert c.winning_version == 2


# ───────────────────────── specialized_agents dataclasses ─────────────────────────


class TestAgentTaskEnum:
    def test_values(self, analyst):
        assert analyst.AgentTask.PROOFREAD.value == "proofread"
        assert analyst.AgentTask.ADVERSARIAL_QA.value == "adversarial_qa"


class TestReviewFinding:
    def test_init(self, analyst):
        f = analyst.ReviewFinding(
            severity="warning",
            category="writing",
            location="sec:intro:1",
            description="typo",
            suggestion="fix it",
            line_ref=10,
        )
        assert f.severity == "warning"
        assert f.line_ref == 10

    def test_init_with_defaults(self, analyst):
        f = analyst.ReviewFinding(
            severity="info",
            category="format",
            location="sec:m:0",
            description="d",
        )
        assert f.suggestion is None
        assert f.line_ref is None


class TestAgentReviewResult:
    def test_init(self, analyst):
        r = analyst.AgentReviewResult(
            agent=analyst.AgentTask.PROOFREAD,
            findings=[],
            summary="ok",
            pass_flag=True,
            review_time_seconds=1.0,
            raw_response="raw",
        )
        assert r.agent is analyst.AgentTask.PROOFREAD
        assert r.pass_flag is True
        assert r.findings == []
