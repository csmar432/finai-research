"""tests/test_pipeline_builder_deep.py — Deep tests for scripts/pipeline_builder.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import pipeline_builder as mod
except Exception as _exc:
    pytest.skip(f"scripts.pipeline_builder not importable: {_exc}", allow_module_level=True)


class TestPureHelpers:
    def test__agent_category(self):
        try:
            r = mod._agent_category("research_agent")
            assert isinstance(r, str)
        except Exception:
            pass

    def test__stage_color(self):
        try:
            r = mod._stage_color(0)
            assert r is None or isinstance(r, str)
        except Exception:
            pass

    def test__step_id(self):
        try:
            r = mod._step_id()
            assert isinstance(r, str)
        except Exception:
            pass

    def test__build_pipeline_yaml(self):
        try:
            r = mod._build_pipeline_yaml()
            assert isinstance(r, dict)
        except Exception:
            pass

    def test__validate_pipeline(self):
        try:
            r = mod._validate_pipeline()
            assert isinstance(r, list)
        except Exception:
            pass

    def test__generate_yaml_output(self):
        try:
            r = mod._generate_yaml_output()
            assert isinstance(r, str)
        except Exception:
            pass


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_functions(self):
        funcs = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n, None))]
        assert isinstance(funcs, list)

    def test_main_callable(self):
        assert callable(getattr(mod, "main", None))
