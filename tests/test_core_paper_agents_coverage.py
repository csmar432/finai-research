"""Behavior coverage for the three deterministic paper-agent paths."""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

from scripts.core.agents import paper_agents as pa
from scripts.core.agents.base import AgentCancelledError, BaseAgent, CancellationToken, HaltDecision


class Gateway:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def register_agent(self, *_args):
        return None

    def generate(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        return SimpleNamespace(response=self.response, model_used="fake", latency_ms=1, tokens_used=2)


def config(name):
    return pa.AgentConfig(name=name, role="role", goal="goal", backstory="context", max_iterations=1)


class DummyAgent(BaseAgent):
    def __init__(self, mode="approve", **kwargs):
        cfg = config("dummy")
        cfg.max_iterations = 2
        super().__init__(cfg, Gateway(""))
        self.mode, self.calls = mode, 0

    def act(self, context):
        self.calls += 1
        if self.mode == "error":
            raise RuntimeError("act error")
        return {"calls": self.calls, "tokens_used": 1}

    def reflect(self, result):
        if self.mode == "reject":
            return {"halt": HaltDecision.REJECTED, "feedback": "reject"}
        if self.mode == "revise" and self.calls == 1:
            return {"halt": HaltDecision.REVISE, "feedback": "again"}
        if self.mode == "reflect_error":
            raise RuntimeError("reflect error")
        return {"halt": HaltDecision.APPROVED, "feedback": "ok"}


def test_base_agent_run_decisions_and_json_parser():
    approved = DummyAgent().run({})
    assert approved.status == "approved" and approved.tokens_used == 1
    revised = DummyAgent("revise").run({})
    assert revised.status == "approved" and revised.iterations == 2
    rejected = DummyAgent("reject").run({})
    assert rejected.status == "error"
    failed = DummyAgent("error").run({})
    assert failed.status == "approved" and "error" in failed.output
    reflect_failed = DummyAgent("reflect_error").run({})
    assert reflect_failed.status == "error"
    cancelled = CancellationToken()
    cancelled.cancel("stop")
    try:
        DummyAgent().run({}, cancel_token=cancelled)
    except AgentCancelledError as exc:
        assert "stop" in str(exc)
    assert DummyAgent()._parse_json_response("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert DummyAgent()._parse_json_response("prefix [1, 2] suffix") == [1, 2]


def test_outline_agent_act_and_reflect_branches():
    outline = {"meta": {"contribution_statement": "new"},
               "chapters": [{"chapter_id": i, "title": "Method"} for i in range(7)],
               "figure_plan": [], "literature_plan": {}}
    agent = pa.OutlineAgent(config("outline"), Gateway(json.dumps(outline)))
    result = agent.act({"topic": "topic", "venue": "JF", "idea": "idea", "field": "finance"})
    assert result["outline"] == outline
    assert agent.reflect(result)["halt"] == pa.HaltDecision.APPROVED
    assert agent.reflect({"outline": {"raw": True}})["flags"] == ["format_error"]
    assert agent.reflect({"outline": {}})["flags"] == ["incomplete_structure"]
    assert agent.reflect({"outline": {"meta": {}, "chapters": [], "figure_plan": [], "literature_plan": {}}})["flags"] == ["too_short"]


def test_literature_agent_search_verify_and_graph(monkeypatch):
    class Verifier:
        def verify(self, candidate):
            return {"verified": True, "source": "test", "levenshtein_score": .95, "abstract": "abs"}

    agent = pa.LiteratureReviewAgent(config("literature"), Gateway("[]"), citation_verifier=Verifier())
    agent._search_candidates = lambda query, limit: [{"title": "Paper", "authors": ["A"], "year": 2024,
                                                       "doi": "10/x", "venue": "J"}]
    result = agent.act({"search_queries": ["q"]})
    assert result["coverage"] == 1 and result["coverage_stats"]["total"] == 1
    assert result["citation_graph"]["total_papers"] == 1
    assert agent.reflect(result)["halt"] == pa.HaltDecision.REVISE  # fewer than five
    assert agent._parse_authors({"authors": "A, B"}) == ["A", "B"]
    assert agent._parse_authors({"authors": [{"name": "A"}]}) == ["A"]
    assert agent._parse_year({"published": "bad"}) == 2024
    assert agent._build_citation_graph([])["total_papers"] == 0

    class MCPResult:
        def __init__(self, data):
            self.success, self.data = True, data
    fake_gateway_module = types.SimpleNamespace(
        MCPResult=MCPResult,
        call_mcp_tool=lambda *_args, **_kwargs: MCPResult([{
            "title": "Found", "authors": [{"name": "A"}], "published": "2023-01-01",
            "url": "u", "snippet": "J"
        }]),
    )
    monkeypatch.setitem(sys.modules, "scripts.core.llm_gateway", fake_gateway_module)
    agent._search_candidates = pa.LiteratureReviewAgent._search_candidates.__get__(agent)
    candidates = agent._search_candidates("query", 2)
    assert candidates[0]["title"] == "Found" and candidates[0]["year"] == 2023


def test_section_writing_context_and_reflect():
    text = "word " * 220
    agent = pa.SectionWritingAgent(config("writing"), Gateway(text))
    result = agent.act({"outline": {"chapters": [{"chapter_id": 1, "title": "Method",
                                                     "summary": "s", "key_points": ["p"]}]},
                        "citations": [{"authors": ["A"], "year": 2024, "title": "T", "verified": True}],
                        "empirical_data": {"method": {"n": 1}}})
    assert result["chapter_count"] == 1 and result["total_word_count"] >= 200
    assert agent.reflect(result)["halt"] == pa.HaltDecision.APPROVED
    assert agent.reflect({"chapters": []})["flags"] == ["empty_output"]
    assert agent._build_citation_context([]).startswith("（暂无")
    assert "A (2024)" in agent._build_citation_context([{"authors": ["A"], "year": 2024, "title": "T"}])
    assert "暂无实证" in agent._build_empirical_context({}, {"title": "Method"})
    all_titles = list(agent.CHAPTER_PROMPTS)
    all_result = agent.act({"outline": {"chapters": [{"chapter_id": i, "title": title,
                                                         "summary": "s", "key_points": []}
                                                        for i, title in enumerate(all_titles)]}})
    assert all_result["chapter_count"] == len(all_titles)


def test_refinement_plotting_and_data_fetch_fallbacks(monkeypatch, tmp_path):
    review = {"verdict": "approve", "violations": [], "overall_comments": "ok",
              "scores": {"overall": 8}}
    # Force the documented single-reviewer fallback without any external LLM.
    class BrokenParliament:
        def __init__(self, **_kwargs):
            raise RuntimeError("unavailable")
    monkeypatch.setitem(sys.modules, "scripts.core.ai_parliament", types.SimpleNamespace(AIParliament=BrokenParliament))
    refinement = pa.ContentRefinementAgent(config("refine"), Gateway(json.dumps(review)))
    result = refinement.act({"draft": "x" * 13000, "chapter": "Method"})
    assert result["_audit"]["was_truncated"] is True
    assert refinement.reflect(result)["halt"] == pa.HaltDecision.APPROVED
    assert refinement.reflect({"review": {"verdict": "revise", "violations": [{"rule": "r", "issue": "i", "suggestion": "s"}], "scores": {"overall": 4}}})["halt"] == pa.HaltDecision.REVISE

    plotting = pa.PlottingAgent(config("plot"), Gateway("print('CAPTION: c')"))
    empty = plotting.act({"figure_plan": [], "output_dir": str(tmp_path)})
    assert empty["total_figures"] == 0
    assert plotting.reflect(empty)["flags"] == ["no_figures"]
    assert plotting._execute_figure_code("f", "print(1)", str(tmp_path), {})["success"] is False
    assert plotting._execute_figure_code("f", "", str(tmp_path), {})["error"] == "No code provided"
    assert plotting._generate_figure_code("f", "desc", {}, {}) == "print('CAPTION: c')"
    monkeypatch.setenv("FINAI_ALLOW_UNSAFE_DYNAMIC_TOOLS", "1")
    executed = plotting._execute_figure_code("f", "print('SAVED_FILE: out.png')\nprint('CAPTION: cap')", str(tmp_path), {})
    assert executed["success"] and executed["files"] == ["out.png"] and executed["caption"] == "cap"

    class DataGateway(Gateway):
        def call_mcp_tool(self, *_args):
            return SimpleNamespace(success=True, data={"value": 1})
    fetcher = pa.DataFetchAgent(config("data"), DataGateway(""))
    fetched = fetcher.act({"provinces": ["湖北"], "indicators": ["GDP"], "years": ["2024"],
                           "fetch_summary": True, "fetch_rankings": True})
    assert fetched["summary"] == {"value": 1}
    assert fetched["provinces"]["湖北"]["2024"]["GDP"] == {"value": 1}
    assert set(fetched["rankings"]) == {"GDP_2024", "RD经费_2024", "高新技术企业_2024", "技术合同_2024"}
