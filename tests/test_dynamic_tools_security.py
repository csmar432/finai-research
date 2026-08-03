"""Security regression tests for LLM-generated dynamic tools."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from scripts.core.dynamic_tools import DynamicToolManager


def test_dynamic_tool_creation_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FINAI_ALLOW_UNSAFE_DYNAMIC_TOOLS", raising=False)
    manager = DynamicToolManager(MagicMock(), registry_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="disabled by default"):
        manager.create_from_nl("return one")


def test_loading_registry_never_executes_source_in_host(tmp_path):
    marker = tmp_path / "executed"
    source = (
        f'@__import__("pathlib").Path({str(marker)!r}).write_text("unsafe")\n'
        "def generated():\n"
        "    return 1\n"
    )
    (tmp_path / "generated.json").write_text(
        json.dumps({
            "metadata": {
                "name": "generated",
                "description": "security regression",
                "created_at": 0.0,
                "created_by": "llm",
                "version": 1,
                "parent_tool": None,
                "tags": [],
            },
            "source_code": source,
        }),
        encoding="utf-8",
    )

    manager = DynamicToolManager(MagicMock(), registry_dir=str(tmp_path))

    assert "generated" in manager.list_tools()
    assert not marker.exists()


def test_loaded_dynamic_tool_execution_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FINAI_ALLOW_UNSAFE_DYNAMIC_TOOLS", raising=False)
    (tmp_path / "generated.json").write_text(
        json.dumps({
            "metadata": {
                "name": "generated",
                "description": "security regression",
                "created_at": 0.0,
                "created_by": "llm",
                "version": 1,
                "parent_tool": None,
                "tags": [],
            },
            "source_code": "def generated():\n    return 1\n",
        }),
        encoding="utf-8",
    )
    manager = DynamicToolManager(MagicMock(), registry_dir=str(tmp_path))

    result = manager.execute("generated", {})

    assert result["success"] is False
    assert "disabled" in result["error"]


def test_llm_generated_figure_execution_is_disabled_by_default(tmp_path, monkeypatch):
    from scripts.core.agents.paper_agents import PlottingAgent

    monkeypatch.delenv("FINAI_ALLOW_UNSAFE_DYNAMIC_TOOLS", raising=False)
    result = PlottingAgent._execute_figure_code(
        object(), "figure_1", "raise RuntimeError('executed')", str(tmp_path), {}
    )

    assert result["success"] is False
    assert "disabled by default" in result["error"]
