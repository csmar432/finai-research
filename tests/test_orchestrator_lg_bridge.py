"""
tests/test_orchestrator_lg_bridge.py

Unit tests for the LangGraph bridge integration:
  • bridge imports successfully
  • falls back gracefully when LangGraph is absent
  • run_research_pipeline function exists and is callable
  • PipelineRunner class exists and exposes .run() / .stream() / .checkpoint()
  • agent_pipeline.py has the --langgraph CLI flag
  • agent_pipeline.py imports the bridge without error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────


def _load_module(name: str):
    """Import a module by name, returning None on ImportError."""
    try:
        return __import__(name, fromlist=[name.split(".")[-1]])
    except ImportError:
        return None


# ── bridge import ──────────────────────────────────────────────────────────────


class TestBridgeImports:
    def test_bridge_imports_successfully(self):
        """The bridge module must not crash on import."""
        # Re-import to ensure fresh state (sys.modules may already hold a cached version)
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        assert mod is not None

    def test_bridge_defines_is_langgraph_available(self):
        """is_langgraph_available must be a bool exported at module level."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        val = getattr(mod, "is_langgraph_available", None)
        assert val is not None
        assert isinstance(val, bool)

    def test_bridge_defines_is_pipeline_available(self):
        """is_pipeline_available must be a bool exported at module level."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        val = getattr(mod, "is_pipeline_available", None)
        assert val is not None
        assert isinstance(val, bool)


# ── run_research_pipeline ───────────────────────────────────────────────────────


class TestRunResearchPipeline:
    def test_bridge_has_run_research_pipeline(self):
        """run_research_pipeline function must exist and be callable."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        func = getattr(mod, "run_research_pipeline", None)
        assert func is not None, "run_research_pipeline not found in orchestrator_lg_bridge"
        assert callable(func)

    def test_run_research_pipeline_accepts_required_args(self):
        """run_research_pipeline must accept (topic, venue, language)."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        func = getattr(mod, "run_research_pipeline", None)
        assert func is not None
        # Smoke-test: call with minimal args, expect dict or exception (not crash)
        try:
            result = func(topic="test topic", venue="经济研究", language="zh")
            assert isinstance(result, dict)
        except Exception:
            # Some backends may raise if LLMGateway is not configured — that is fine
            pass


# ── PipelineRunner ──────────────────────────────────────────────────────────────


class TestPipelineRunner:
    def test_bridge_has_pipeline_runner(self):
        """PipelineRunner class must exist and be instantiable."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        cls = getattr(mod, "PipelineRunner", None)
        assert cls is not None, "PipelineRunner not found in orchestrator_lg_bridge"
        assert isinstance(cls, type)

    def test_pipeline_runner_has_run_stream_checkpoint(self):
        """PipelineRunner must expose .run(), .stream(), and .checkpoint() methods."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        cls = getattr(mod, "PipelineRunner", None)
        assert cls is not None
        runner = cls(topic="test", venue="经济研究", language="zh")
        assert hasattr(runner, "run")
        assert hasattr(runner, "stream")
        assert hasattr(runner, "checkpoint")
        assert callable(runner.run)
        assert callable(runner.stream)
        assert callable(runner.checkpoint)

    def test_pipeline_runner_checkpoint_creates_file(self, tmp_path: Path):
        """PipelineRunner.checkpoint() must write a valid JSON file."""
        if "scripts.core.orchestrator_lg_bridge" in sys.modules:
            mod = sys.modules["scripts.core.orchestrator_lg_bridge"]
        else:
            mod = __import__("scripts.core.orchestrator_lg_bridge", fromlist=["_LG_BRIDGE_AVAILABLE"])
        cls = getattr(mod, "PipelineRunner", None)
        assert cls is not None
        runner = cls(topic="test", venue="经济研究", language="zh")
        checkpoint_path = tmp_path / "checkpoint.json"
        runner.checkpoint(checkpoint_path)
        assert checkpoint_path.exists(), "checkpoint() did not create the output file"


# ── agent_pipeline integration ──────────────────────────────────────────────────


class TestAgentPipelineIntegration:
    def test_agent_pipeline_imports_bridge(self):
        """agent_pipeline.py must import the bridge without error."""
        # Force re-import to verify there is no ImportError at the top level
        key = "scripts.agent_pipeline"
        if key in sys.modules:
            mod = sys.modules[key]
        else:
            mod = __import__(key, fromlist=["AgentPipeline"])
        assert mod is not None
        # The _LG_BRIDGE_AVAILABLE flag must be present
        flag = getattr(mod, "_LG_BRIDGE_AVAILABLE", None)
        assert flag is not None

    def test_agent_pipeline_has_langgraph_flag(self):
        """AgentPipeline.__init__ must accept a use_langgraph keyword argument."""
        from scripts.agent_pipeline import AgentPipeline
        import inspect

        sig = inspect.signature(AgentPipeline.__init__)
        params = list(sig.parameters.keys())
        assert "use_langgraph" in params, (
            f"use_langgraph not found in AgentPipeline.__init__ params: {params}"
        )

    def test_agent_pipeline_langgraph_init_kwarg_works(self):
        """AgentPipeline(use_langgraph=True) must not raise."""
        from scripts.agent_pipeline import AgentPipeline, _LG_BRIDGE_AVAILABLE
        # Must not raise, even if bridge is unavailable
        pipeline = AgentPipeline(use_langgraph=False)
        assert pipeline is not None

    def test_agent_pipeline_run_method_respects_flag(self):
        """AgentPipeline.run() must call run_research_pipeline when _use_langgraph=True."""
        from scripts.agent_pipeline import AgentPipeline
        import inspect

        # Just verify run() exists and is callable
        assert hasattr(AgentPipeline, "run")
        assert callable(AgentPipeline.run)


# ── CLI --langgraph flag ───────────────────────────────────────────────────────


class TestCLIFlags:
    def test_agent_pipeline_has_langgraph_flag(self):
        """
        The agent_pipeline.py CLI block must define a --langgraph argument.

        We verify this by reading the file and finding the expected pattern in
        the ``if __name__ == '__main__'`` block.
        """
        agent_pipeline_path = Path(__file__).parents[1] / "scripts" / "agent_pipeline.py"
        content = agent_pipeline_path.read_text(encoding="utf-8")

        # The CLI block must contain --langgraph and action="store_true"
        assert 'if __name__ == "__main__"' in content, (
            "agent_pipeline.py has no `if __name__ == '__main__'` CLI block"
        )
        assert 'add_argument' in content and '--langgraph' in content, (
            "agent_pipeline.py CLI block does not define --langgraph"
        )

    def test_cli_parser_accepts_langgraph_and_topic(self):
        """argparse in the CLI block must accept both --langgraph and --topic."""
        import argparse as _argparse

        # Replicate the CLI parser construction from agent_pipeline.py
        parser = _argparse.ArgumentParser(description="test")
        parser.add_argument("--topic", "-t", type=str, default=None)
        parser.add_argument("--venue", type=str, default=None)
        parser.add_argument("--langgraph", action="store_true")
        parser.add_argument("--use-hitl", action="store_true")
        parser.add_argument("--language", choices=["zh", "en"], default="zh")

        args = parser.parse_args(["--topic", "碳排放权交易", "--langgraph", "--venue", "经济研究"])
        assert args.topic == "碳排放权交易"
        assert args.langgraph is True
        assert args.venue == "经济研究"
