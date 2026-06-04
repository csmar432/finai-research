"""AgentLoader + PipelineStep 单元测试"""
import pytest
from scripts.core.agent_loader import (
    AgentLoader,
    PipelineStep,
    ParallelPipeline,
    PipelineStage,
    ConfigManager,
)


class TestPipelineStep:
    def test_pipeline_step_basic(self):
        step = PipelineStep("outline", PipelineStage("OUTLINE"))
        assert step.agent_name == "outline"
        assert step.stage == "OUTLINE"
        assert step.hitl_gate is False

    def test_pipeline_step_with_hitl(self):
        step = PipelineStep(
            "valuation",
            PipelineStage("ANALYST_4"),
            hitl_gate=True,
            hitl_gate_after="valuation",
            max_workers=6,
        )
        assert step.hitl_gate is True
        assert step.hitl_gate_after == "valuation"
        assert step.max_workers == 6


class TestParallelPipeline:
    def test_parallel_pipeline_creation(self):
        pipeline = ParallelPipeline(
            name="research_report",
            agent_names=["fundamental_market", "fundamental_financial", "valuation"],
            hitl_gate_after="valuation",
            max_workers=3,
        )
        assert pipeline.name == "research_report"
        assert len(pipeline.agent_names) == 3
        assert len(pipeline.steps) == 3
        assert pipeline.max_workers == 3
        assert pipeline.hitl_gate_after == "valuation"

    def test_parallel_pipeline_hitl_gate_assignment(self):
        pipeline = ParallelPipeline(
            name="test",
            agent_names=["a", "b", "c"],
            hitl_gate_after="b",
            max_workers=3,
        )
        # ParallelPipeline stores hitl_gate_after but does NOT set hitl_gate on steps.
        # That happens in get_pipeline_steps() when parsing YAML.
        assert pipeline.hitl_gate_after == "b"
        assert len(pipeline.steps) == 3
        assert all(not s.hitl_gate for s in pipeline.steps)


class TestAgentLoader:
    def setup_method(self):
        self.loader = AgentLoader("config/agents.yaml")

    def test_load_agents(self):
        self.loader.load()
        agents = self.loader.list_agents()
        assert "outline" in agents
        assert "literature_review" in agents
        assert "section_writing" in agents

    def test_load_analysts(self):
        self.loader.load()
        analysts = self.loader.list_analysts()
        assert "fundamental_market" in analysts
        assert "fundamental_financial" in analysts
        assert "valuation" in analysts

    def test_get_agent_config(self):
        self.loader.load()
        config = self.loader.get_agent_config("outline")
        assert config is not None
        assert config.role == "论文大纲设计专家"

    def test_get_analyst_config(self):
        self.loader.load()
        config = self.loader.get_analyst_config("fundamental_financial")
        assert config is not None
        assert config.analyst_type.value == "fundamental_financial"

    def test_get_pipeline_steps_sequential(self):
        self.loader.load()
        steps = self.loader.get_pipeline_steps("paper")
        assert len(steps) > 0
        assert all(isinstance(s, PipelineStep) for s in steps)

    def test_get_pipeline_steps_parallel(self):
        self.loader.load()
        steps = self.loader.get_pipeline_steps("research_report")
        assert len(steps) > 0
        # Should have hitl_gate_after parsed
        hitl_steps = [s for s in steps if s.hitl_gate]
        assert any(s.hitl_gate_after == "valuation" for s in steps)
        assert any(s.max_workers == 6 for s in steps)

    def test_list_pipelines(self):
        self.loader.load()
        pipelines = self.loader.list_pipelines()
        assert "paper" in pipelines
        assert "research_report" in pipelines


class TestConfigManager:
    def test_load_all(self):
        cm = ConfigManager()
        agents = cm.load_agents()
        assert len(agents) > 0
        analysts = cm.load_analysts()
        assert len(analysts) > 0
        halt_rules = cm.load_halt_rules("empirical_paper")
        # HaltRules is a HaltRules object (not a list), access .rules attribute
        assert hasattr(halt_rules, "rules")
        assert len(halt_rules.rules) > 0
        pipeline = cm.build_pipeline("paper")
        assert len(pipeline) > 0
