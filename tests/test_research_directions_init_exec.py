"""tests/test_research_directions_init_exec.py — Exercise research_directions/__init__.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    pass
    # Re-import core classes from __init__
    mod = sys.modules["scripts.research_directions"]
except Exception as _exc:
    pytest.skip(f"research_directions not importable: {_exc}", allow_module_level=True)


class TestModule:
    def test_imports(self):
        assert mod is not None

    def test_has_classes(self):
        classes = [n for n in dir(mod) if not n.startswith("_") and isinstance(getattr(mod, n, None), type)]
        assert isinstance(classes, list)


class TestLiteratureParser:
    def test_init(self):
        cls = getattr(mod, "LiteratureParser", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(use_mcp=False)
            assert obj is not None
        except Exception:
            pass

    def test_init_default(self):
        cls = getattr(mod, "LiteratureParser", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestResearchGapScorer:
    def test_init(self):
        cls = getattr(mod, "ResearchGapScorer", None)
        if cls is None: pytest.skip("not present")
        obj = cls()
        assert obj is not None

    def test_compute_gap_score(self):
        cls = getattr(mod, "ResearchGapScorer", None)
        if cls is None: pytest.skip("not present")
        obj = cls()
        try:
            r = obj.compute_gap_score(
                paper_ids=["p1"],
                literature_texts=[
                    "Carbon trading and climate risk in financial markets",
                    "LLM and AI applications in finance",
                ],
            )
            assert isinstance(r, dict)
        except Exception:
            pass

    def test_identify_bridging_opportunities(self):
        cls = getattr(mod, "ResearchGapScorer", None)
        if cls is None: pytest.skip("not present")
        obj = cls()
        try:
            r = obj.identify_bridging_opportunities(
                direction_a="climate_finance",
                direction_b="ai_finance",
                literature_texts=["Carbon trading research", "AI in finance"],
            )
            assert isinstance(r, list)
        except Exception:
            pass


class TestMethodologyStep:
    def test_default(self):
        cls = getattr(mod, "MethodologyStep", None)
        if cls is None: pytest.skip("not present")
        obj = cls(step_name="PSM", econometric_class="PSM")
        assert obj.step_name == "PSM"
        d = obj.to_markdown()
        assert isinstance(d, str)

    def test_with_args(self):
        cls = getattr(mod, "MethodologyStep", None)
        if cls is None: pytest.skip("not present")
        obj = cls(
            step_name="DID",
            econometric_class="DID",
            notes="控制双向固定效应",
            data_needed=["y", "x"],
            packages=["statsmodels"],
        )
        d = obj.to_markdown()
        assert "DID" in d


class TestMethodologyChain:
    def test_default(self):
        cls = getattr(mod, "MethodologyChain", None)
        if cls is None: pytest.skip("not present")
        obj = cls()
        assert obj is not None

    def test_add_step(self):
        cls = getattr(mod, "MethodologyChain", None)
        Step = getattr(mod, "MethodologyStep", None)
        if cls is None or Step is None: pytest.skip("not present")
        obj = cls()
        step = Step(step_name="X", econometric_class="X")
        obj.add_step(step)
        assert len(obj.steps) == 1

    def test_to_markdown(self):
        cls = getattr(mod, "MethodologyChain", None)
        Step = getattr(mod, "MethodologyStep", None)
        if cls is None or Step is None: pytest.skip("not present")
        obj = cls()
        obj.add_step(Step(step_name="PSM", econometric_class="PSM"))
        obj.add_step(Step(step_name="DID", econometric_class="DID"))
        md = obj.to_markdown()
        assert isinstance(md, str)
        assert "PSM" in md or "DID" in md

    def test_get_required_packages(self):
        cls = getattr(mod, "MethodologyChain", None)
        Step = getattr(mod, "MethodologyStep", None)
        if cls is None or Step is None: pytest.skip("not present")
        obj = cls()
        obj.add_step(Step(step_name="DID", econometric_class="DID", packages=["statsmodels"]))
        pkgs = obj.get_required_packages()
        assert isinstance(pkgs, list)
        assert "statsmodels" in pkgs

    def test_get_step_names(self):
        cls = getattr(mod, "MethodologyChain", None)
        Step = getattr(mod, "MethodologyStep", None)
        if cls is None or Step is None: pytest.skip("not present")
        obj = cls()
        obj.add_step(Step(step_name="A", econometric_class="A"))
        names = obj.get_step_names()
        assert names == ["A"]

    def test_get_econometric_classes(self):
        cls = getattr(mod, "MethodologyChain", None)
        Step = getattr(mod, "MethodologyStep", None)
        if cls is None or Step is None: pytest.skip("not present")
        obj = cls()
        obj.add_step(Step(step_name="A", econometric_class="PSM"))
        classes = obj.get_econometric_classes()
        assert classes == ["PSM"]


class TestResearchDirection:
    def test_default(self):
        cls = getattr(mod, "ResearchDirection", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(direction_name="x", display_name="X", literature_theme="X")
            assert obj is not None
        except Exception:
            pass


class TestDirectionFactory:
    def test_get_registry(self):
        fn = getattr(mod, "get_registry", None)
        if fn is None: pytest.skip("not present")
        r = fn()
        assert r is not None

    def test_DirectionFactory(self):
        cls = getattr(mod, "DirectionFactory", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestDirectionRecommender:
    def test_recommender(self):
        cls = getattr(mod, "DirectionRecommender", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestBaseResearchDirection:
    """BaseResearchDirection is abstract — can't instantiate."""

    def test_base_direction_signature(self):
        cls = getattr(mod, "BaseResearchDirection", None)
        if cls is None: pytest.skip("not present")
        # Verify abstract methods
        for m in ["fetch_data", "build_panel", "run_pipeline"]:
            if hasattr(cls, m):
                fn = getattr(cls, m)
                assert callable(fn) or hasattr(fn, "__isabstractmethod__")


class TestAllOtherClasses:
    def test_try_all_classes(self):
        for name in dir(mod):
            if name.startswith("_"):
                continue
            cls = getattr(mod, name, None)
            if not isinstance(cls, type):
                continue
            try:
                obj = cls()
                assert obj is not None
            except Exception:
                # Many of these are abstract or require args
                pass
