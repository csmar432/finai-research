"""Pure-Python tests for pipeline_builder's state and serialization layer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts import pipeline_builder as pb


class State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class FakeStreamlit:
    def __init__(self):
        self.session_state = State()
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def install_state(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(pb, "st", fake)
    pb._init_state()
    return fake


def test_categories_and_stage_colors_are_stable():
    assert pb._agent_category("outline") == "paper"
    assert pb._agent_category("valuation") == "analyst"
    assert pb._agent_category("unknown") == "utility"
    assert pb._stage_color(0) == "#9B59B6"
    assert pb._stage_color(len(pb.PAPER_STAGES) + len(pb.ANALYST_STAGES)) == "#34495E"


def test_init_build_and_validate_pipeline(monkeypatch):
    fake = install_state(monkeypatch)
    assert fake.session_state.pb_pipeline_name == "my_pipeline"
    fake.session_state.pb_pipeline_name = "  demo  "
    fake.session_state.pb_pipeline_desc = "  description  "
    fake.session_state.pb_steps = [{
        "agent": "outline", "stage": "OUTLINE", "hitl_gate": True,
        "max_iterations": 4, "depends_on": ["previous"],
    }]
    fake.session_state.pb_agent_data = {"outline": {"role": "writer"}}
    built = pb._build_pipeline_yaml()
    assert built["name"] == "demo"
    assert built["description"] == "description"
    assert built["steps"][0]["max_iterations"] == 4
    assert built["steps"][0]["depends_on"] == ["previous"]
    assert pb._validate_pipeline() == []

    fake.session_state.pb_steps.append(dict(fake.session_state.pb_steps[0]))
    assert any("Duplicate" in error for error in pb._validate_pipeline())
    fake.session_state.pb_steps = [{"agent": "missing", "stage": "OUTLINE"}]
    assert any("Unknown agent" in error for error in pb._validate_pipeline())
    fake.session_state.pb_steps = []
    fake.session_state.pb_pipeline_name = ""
    errors = pb._validate_pipeline()
    assert "Pipeline name is required." in errors
    assert "Add at least one step to the pipeline." in errors


def test_reload_save_generate_and_load_pipeline(tmp_path, monkeypatch):
    fake = install_state(monkeypatch)
    config = tmp_path / "agents.yaml"
    config.write_text(yaml.safe_dump({
        "agents": {"outline": {"role": "writer"}},
        "analysts": {"valuation": {"role": "analyst"}},
        "pipelines": {"old": {"description": "old", "steps": [
            {"agent": "outline", "stage": "OUTLINE", "hitl_gate": True, "depends_on": ["x"]}
        ]}},
    }), encoding="utf-8")
    monkeypatch.setattr(pb, "CONFIG_YAML", config)
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    monkeypatch.setattr(pb, "DRAFT_DIR", drafts)
    pb._reload_yaml()
    assert fake.session_state.pb_loaded is True
    assert fake.session_state.pb_agent_data["outline"]["category"] == "paper"
    assert fake.session_state.pb_agent_data["valuation"]["category"] == "analyst"

    fake.session_state.pb_pipeline_name = "demo/name"
    fake.session_state.pb_pipeline_desc = "desc"
    fake.session_state.pb_steps = [{"id": "1", "agent": "outline", "stage": "OUTLINE"}]
    draft = pb._save_draft()
    assert draft.exists() and "/" not in draft.name
    saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
    assert saved["pipeline"]["description"] == "desc"

    output = pb._generate_yaml_output()
    parsed = yaml.safe_load(output)
    assert parsed["pipelines"]["demo/name"]["name"] == "demo/name"

    fake.session_state.pb_pipelines = {
        "old": {"description": "old", "steps": [{"agent": "outline", "stage": "OUTLINE"}]}
    }
    pb._load_pipeline("old")
    assert fake.session_state.pb_pipeline_name == "old"
    assert fake.session_state.pb_steps[0]["agent"] == "outline"
    assert fake.session_state.pb_steps[0]["id"]
    assert fake.session_state.pb_selected_step is None


def test_reload_reports_missing_config(monkeypatch, tmp_path):
    fake = install_state(monkeypatch)
    monkeypatch.setattr(pb, "CONFIG_YAML", tmp_path / "missing.yaml")
    pb._reload_yaml()
    assert fake.errors and "not found" in fake.errors[0]
