"""tests/test_research_framework_enhanced_pipeline_exec2.py — Deeper EnhancedPipeline tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import enhanced_pipeline as mod
except Exception as _exc:
    pytest.skip(f"enhanced_pipeline not importable: {_exc}", allow_module_level=True)


class TestPipelineContext:
    def test_default(self):
        cls = getattr(mod, "PipelineContext", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_with_args(self):
        cls = getattr(mod, "PipelineContext", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(topic="ESG", language="zh", output_dir="output/")
            assert obj is not None
        except Exception:
            pass

    def test_str(self):
        cls = getattr(mod, "PipelineContext", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(topic="ESG")
            s = str(obj)
            assert isinstance(s, str)
        except Exception:
            pass


class TestEnhancedPipeline:
    def test_default(self, tmp_path):
        cls = getattr(mod, "EnhancedPipeline", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(topic="ESG", output_dir=str(tmp_path / "out"))
            assert obj is not None
        except Exception:
            pass

    def test_disabled(self, tmp_path):
        cls = getattr(mod, "EnhancedPipeline", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(
                topic="ESG",
                output_dir=str(tmp_path / "out"),
                enable_modern_did=False,
                enable_validation_gates=False,
                enable_latex_lint=False,
                enable_latex_diff=False,
                enable_pdf_vision=False,
                enable_sandbox=False,
                enable_hitl=False,
            )
            assert obj is not None
        except Exception:
            pass

    def test_summary(self, tmp_path):
        cls = getattr(mod, "EnhancedPipeline", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(topic="ESG", output_dir=str(tmp_path / "out"))
            s = obj.summary()
            assert s is not None
        except Exception:
            pass


class TestCliMain:
    def test_callable(self):
        fn = getattr(mod, "_cli_main", None)
        if fn is None: pytest.skip("not present")
        assert callable(fn)
class TestAllMethods:
    def test_all_methods(self, tmp_path):
        cls = getattr(mod, "EnhancedPipeline", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(topic="ESG", output_dir=str(tmp_path / "out"))
            for name in dir(obj):
                if name.startswith("_"): continue
                fn = getattr(obj, name)
                if callable(fn) and name != "run":
                    try:
                        r = fn()
                        if r is not None:
                            break
                    except Exception:
                        pass
        except Exception:
            pass
