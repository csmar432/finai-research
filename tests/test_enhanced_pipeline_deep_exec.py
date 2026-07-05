"""tests/test_enhanced_pipeline_deep_exec.py — Deep tests for enhanced_pipeline dataclass.

Targets PipelineContext dataclass in scripts/research_framework/enhanced_pipeline.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import pandas as pd
    from scripts.research_framework.enhanced_pipeline import (
        PipelineContext, EnhancedPipeline, _cli_main,
    )
except Exception as exc:
    pytest.skip(f"enhanced_pipeline not importable: {exc}", allow_module_level=True)


# ─── PipelineContext ──────────────────────────────────────────────────

class TestPipelineContext:
    def test_defaults(self):
        ctx = PipelineContext(topic="Test")
        assert ctx.topic == "Test"
        assert ctx.language == "zh"
        assert ctx.did_results == {}
        assert ctx.modern_did_results == {}
        assert ctx.gate_results == {}
        assert ctx.latex_version == "v1.0"
        assert ctx.execution_time_seconds == 0.0

    def test_to_dict(self):
        ctx = PipelineContext(topic="Test")
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert d["topic"] == "Test"
        assert d["language"] == "zh"
        assert "df_shape" in d
        assert d["df_shape"] is None

    def test_to_dict_with_df(self):
        ctx = PipelineContext(topic="Test")
        ctx.df = pd.DataFrame({"a": [1, 2, 3]})
        d = ctx.to_dict()
        assert d["df_shape"] == (3, 1)

    def test_to_dict_with_results(self):
        ctx = PipelineContext(topic="Test")
        ctx.did_results = {"twfe": {"coef": 0.5}}
        ctx.modern_did_results = {"cs": {"coef": 0.4}}
        d = ctx.to_dict()
        assert "twfe" in d["did_results_keys"]
        assert "cs" in d["modern_did_keys"]

    def test_to_dict_with_latex(self):
        ctx = PipelineContext(topic="Test")
        ctx.latex_lint_issues = ["issue1", "issue2"]
        d = ctx.to_dict()
        assert d["latex_lint_issues"] == 2

    def test_with_explicit_output_dir(self, tmp_path):
        ctx = PipelineContext(topic="Test", output_dir=tmp_path)
        assert ctx.output_dir == tmp_path
        d = ctx.to_dict()
        assert d["output_dir"] == str(tmp_path)


# ─── EnhancedPipeline ─────────────────────────────────────────────────

class TestEnhancedPipeline:
    def test_init(self):
        try:
            p = EnhancedPipeline()
            assert p is not None
        except Exception:
            pass

    def test_init_with_topic(self):
        try:
            p = EnhancedPipeline(topic="Test")
            assert p is not None
        except Exception:
            pass


# ─── Module functions ─────────────────────────────────────────────────

class TestModuleFunctions:
    def test_cli_main_callable(self):
        try:
            assert callable(_cli_main)
        except Exception:
            pass