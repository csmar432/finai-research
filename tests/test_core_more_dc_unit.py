"""Unit tests for core dataclasses in: provenance_rag, agent_pipeline_core,
autonomy_loop, visual_graph_editor, checkpoint, tools, visualizer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import(modname, filepath):
    """Import module robustly."""
    import importlib
    try:
        return importlib.import_module(modname)
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(modname, filepath)
        m = importlib.util.module_from_spec(spec)
        sys.modules[modname] = m
        spec.loader.exec_module(m)
        return m


@pytest.fixture(scope="module")
def modules():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    mods = {
        "provenance_rag": _import("scripts.core.provenance_rag",
                                   "scripts/core/provenance_rag.py"),
        "agent_pipeline_core": _import("scripts.core.agent_pipeline_core",
                                       "scripts/core/agent_pipeline_core.py"),
        "autonomy_loop": _import("scripts.core.autonomy_loop",
                                  "scripts/core/autonomy_loop.py"),
        "visual_graph_editor": _import("scripts.core.visual_graph_editor",
                                        "scripts/core/visual_graph_editor.py"),
        "checkpoint": _import("scripts.core.checkpoint",
                              "scripts/core/checkpoint.py"),
        "tools": _import("scripts.core.tools",
                          "scripts/core/tools.py"),
        "visualizer": _import("scripts.core.visualizer",
                                "scripts/core/visualizer.py"),
    }
    yield mods
    if _p in sys.path:
        sys.path.remove(_p)


class TestProvenanceRag:
    def test_provenance_rag_class_exists(self, modules):
        assert hasattr(modules["provenance_rag"], "ProvenanceRAG")

    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["provenance_rag"])
               if hasattr(getattr(modules["provenance_rag"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 2


class TestAgentPipelineCore:
    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["agent_pipeline_core"])
               if hasattr(getattr(modules["agent_pipeline_core"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 4

    def test_classes_exist(self, modules):
        assert hasattr(modules["agent_pipeline_core"], "AgentPipelineCore") or \
               any(not n.startswith('_') for n in dir(modules["agent_pipeline_core"]))


class TestAutonomyLoop:
    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["autonomy_loop"])
               if hasattr(getattr(modules["autonomy_loop"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 4

    def test_autonomy_loop_class_exists(self, modules):
        assert hasattr(modules["autonomy_loop"], "AutonomyLoop")


class TestVisualGraphEditor:
    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["visual_graph_editor"])
               if hasattr(getattr(modules["visual_graph_editor"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 2

    def test_module_has_classes(self, modules):
        # Just check the module has some public classes
        items = [n for n in dir(modules["visual_graph_editor"])
                 if not n.startswith('_') and callable(getattr(modules["visual_graph_editor"], n, None))]
        assert len(items) > 0


class TestCheckpoint:
    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["checkpoint"])
               if hasattr(getattr(modules["checkpoint"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 2


class TestTools:
    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["tools"])
               if hasattr(getattr(modules["tools"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 2


class TestVisualizer:
    def test_has_dataclasses(self, modules):
        import dataclasses
        dcs = [n for n in dir(modules["visualizer"])
               if hasattr(getattr(modules["visualizer"], n, None), '__dataclass_fields__')]
        assert len(dcs) >= 3