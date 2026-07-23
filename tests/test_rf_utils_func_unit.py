"""Functional tests for simple research_framework utility functions."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import(modname, filepath):
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
def med():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.mediation",
                  "scripts/research_framework/mediation.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def mod():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.moderation",
                  "scripts/research_framework/moderation.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def vk():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.vuong_kob",
                  "scripts/research_framework/vuong_kob.py")
    if _p in sys.path:
        sys.path.remove(_p)


@pytest.fixture(scope="module")
def ep():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    yield _import("scripts.research_framework.exact_permutation",
                  "scripts/research_framework/exact_permutation.py")
    if _p in sys.path:
        sys.path.remove(_p)


class TestMediation:
    def test_mediation_result_dataclass(self, med):
        import dataclasses
        fields = dataclasses.fields(med.MediationResult)
        assert len(fields) > 0

    def test_classify_mediation_function_exists(self, med):
        # Just verify the function exists and is callable
        assert callable(med.classify_mediation)


class TestModeration:
    def test_moderation_analysis_class_exists(self, mod):
        assert hasattr(mod, "ModerationAnalysis")

    def test_moderation_result_dataclass(self, mod):
        import dataclasses
        fields = dataclasses.fields(mod.ModerationResult)
        # moderation_result has fields like method, main_effect_X, etc.
        assert len(fields) > 0


class TestVuongKob:
    def test_vuong_test_class_exists(self, vk):
        assert hasattr(vk, "VuongTest")

    def test_vuong_result_dataclass(self, vk):
        import dataclasses
        fields = dataclasses.fields(vk.VuongResult)
        assert len(fields) > 0

    def test_oaxaca_blinder_class_exists(self, vk):
        assert hasattr(vk, "OaxacaBlinderDecomposition")


class TestExactPermutation:
    def test_exact_permutation_test_callable(self, ep):
        assert callable(ep.exact_permutation_test)

    def test_exact_permutation_result_dataclass(self, ep):
        import dataclasses
        fields = dataclasses.fields(ep.ExactPermutationResult)
        assert len(fields) > 0
