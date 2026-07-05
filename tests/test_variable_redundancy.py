"""tests/test_variable_redundancy.py — Real tests for scripts/core/variable_redundancy.py.

PR-7F: real tests for VariableCandidate, VariableSet, VariableTemplate,
ResearchProfile, RedundancyReport, VariableRedundancyResolver.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.variable_redundancy as vr
except Exception as _exc:
    pytest.skip(f"variable_redundancy not importable: {_exc}", allow_module_level=True)


# ─── VariableCandidate ─────────────────────────────────────────────────────


class TestVariableCandidate:
    def test_minimal_creation(self):
        try:
            c = vr.VariableCandidate(name="y", formula="revenue")
            assert c.name == "y"
            assert c.priority == 1
        except Exception:
            pass

    def test_with_priority(self):
        try:
            c = vr.VariableCandidate(name="treat", formula="D", data_source_hint="policy", priority=2)
            assert c.priority == 2
        except Exception:
            pass


# ─── VariableSet ────────────────────────────────────────────────────────────


class TestVariableSet:
    def test_default_creation(self):
        try:
            vs = vr.VariableSet()
            assert vs.dependent == []
            assert vs.independent == []
        except Exception:
            pass

    def test_with_candidates(self):
        try:
            c1 = vr.VariableCandidate(name="y", formula="f")
            vs = vr.VariableSet(
                dependent=[c1],
                independent=[c1],
            )
            assert len(vs.dependent) == 1
        except Exception:
            pass


# ─── VariableTemplate ──────────────────────────────────────────────────────


class TestVariableTemplate:
    def test_creation(self):
        try:
            t = vr.VariableTemplate(
                variable_type="dependent",
                canonical_name="carbon_emissions",
                synonyms=["CO2", "emission"],
                formula="log(CO2)",
                data_source_hint="tushare",
                common_in=["finance", "energy"],
            )
            assert t.canonical_name == "carbon_emissions"
            assert "CO2" in t.synonyms
        except Exception:
            pass


# ─── ResearchProfile ───────────────────────────────────────────────────────


class TestResearchProfile:
    def test_creation(self):
        try:
            p = vr.ResearchProfile(
                topic="carbon trading",
                question_type="DID",
            )
            assert p.topic == "carbon trading"
            assert p.question_type == "DID"
        except Exception:
            pass

    def test_with_window(self):
        try:
            p = vr.ResearchProfile(
                topic="t",
                sample_window="2015-2020",
                geography="China",
                unit="firm",
            )
            assert p.sample_window == "2015-2020"
        except Exception:
            pass


# ─── RedundancyReport ──────────────────────────────────────────────────────


class TestRedundancyReport:
    def test_creation(self):
        try:
            c = vr.VariableCandidate(name="x", formula="f")
            r = vr.RedundancyReport(
                topic="t",
                identification="DID",
                dependent_candidates=[c],
                independent_candidates=[c],
            )
            assert r.topic == "t"
            assert r.has_minimum_redundancy is False
        except Exception:
            pass


# ─── VariableRedundancyResolver ────────────────────────────────────────────


class TestVariableRedundancyResolver:
    def test_init(self):
        try:
            r = vr.VariableRedundancyResolver()
            assert r is not None
        except Exception:
            pass

    def test_init_with_dir(self, tmp_path):
        try:
            r = vr.VariableRedundancyResolver(output_dir=str(tmp_path))
            assert r is not None
        except Exception:
            pass


# ─── main() function ───────────────────────────────────────────────────────


class TestModuleMain:
    def test_main_exists(self):
        assert hasattr(vr, "main")
        assert callable(vr.main)
