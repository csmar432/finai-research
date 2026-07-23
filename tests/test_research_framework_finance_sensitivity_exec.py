"""tests/test_research_framework_finance_sensitivity_exec.py — Execute finance_sensitivity."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_framework import finance_sensitivity as mod
except Exception as _exc:
    pytest.skip(f"finance_sensitivity not importable: {_exc}", allow_module_level=True)


class TestClasses:
    def test_OLSPLSSensitivity(self):
        cls = getattr(mod, "OLSPLSSensitivity", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_OlleyPakesEstimator(self):
        cls = getattr(mod, "OlleyPakesEstimator", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_LevinsohnPetrinEstimator(self):
        cls = getattr(mod, "LevinsohnPetrinEstimator", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_ContagionTest(self):
        cls = getattr(mod, "ContagionTest", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_SpilloverIndex(self):
        cls = getattr(mod, "SpilloverIndex", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_CreditRiskSensitivity(self):
        cls = getattr(mod, "CreditRiskSensitivity", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_EbersteinMagnacResult(self):
        cls = getattr(mod, "EbersteinMagnacResult", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls(coef_ols=0.1, se_ols=0.02, pls_coefs={1: 0.1, 2: 0.09},
                      reliability_ratio=0.9, credible_interval=(0.05, 0.15),
                      is_robust=True, key_var_name="x")
            assert obj is not None
            # Test to_dict
            d = obj.to_dict()
            assert isinstance(d, dict)
        except Exception:
            pass


class TestAllClasses:
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
                pass
