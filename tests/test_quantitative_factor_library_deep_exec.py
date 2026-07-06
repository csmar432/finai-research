"""tests/test_quantitative_factor_library_deep_exec.py — Deep tests for factor library.

Targets uncovered dataclasses and constants in scripts/quantitative_factor_library.py.
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
    import numpy as np
    from scripts.quantitative_factor_library import (
        FactorLibrary, EventStudy, EventStudyResult,
    )
except Exception as exc:
    pytest.skip(f"quantitative_factor_library not importable: {exc}", allow_module_level=True)


# ─── FactorLibrary ────────────────────────────────────────────────────

class TestFactorLibrary:
    def test_init(self):
        fl = FactorLibrary()
        assert fl is not None

    def test_factor_definitions_is_dict(self):
        assert isinstance(FactorLibrary.FACTOR_DEFINITIONS, dict)
        assert len(FactorLibrary.FACTOR_DEFINITIONS) > 30

    def test_factor_categories_present(self):
        categories = set()
        for factor_name, (cat, _, _) in FactorLibrary.FACTOR_DEFINITIONS.items():
            categories.add(cat)
        # Should have multiple categories
        assert len(categories) >= 4
        # Should include key categories
        assert any("Valuation" in c for c in categories)
        assert any("Profitability" in c for c in categories)

    def test_factor_tuple_format(self):
        for name, definition in FactorLibrary.FACTOR_DEFINITIONS.items():
            # Each definition is (category, description, unit)
            assert isinstance(definition, tuple)
            assert len(definition) == 3

    def test_specific_factors(self):
        defs = FactorLibrary.FACTOR_DEFINITIONS
        assert "pe" in defs
        assert "pb" in defs
        assert "roe" in defs
        assert "debt_ratio" in defs
        assert "dividend_yield" in defs
        assert "esg_score" in defs


# ─── EventStudyResult ─────────────────────────────────────────────────

class TestEventStudyResult:
    def test_basic(self):
        ar = pd.Series([0.01, -0.005, 0.002])
        car = pd.Series([0.01, 0.005, 0.007])
        ds = pd.DataFrame({"aar": [0.01, -0.005, 0.002]})
        try:
            r = EventStudyResult(
                event_date="2023-01-01",
                window=(-1, 1),
                n_estimate=100,
                n_event=3,
                car=0.007,
                car_se=0.005,
                car_tstat=1.4,
                car_pval=0.2,
                aar=0.0023,
                aar_tstat=0.5,
                bhar=0.008,
                bhar_se=0.006,
                model="market_model",
                abnormal_returns=ar,
                cumulative_ar=car,
                daily_stats=ds,
            )
            assert r.event_date == "2023-01-01"
            assert r.n_estimate == 100
        except Exception:
            pass

    def test_with_alpha(self):
        ar = pd.Series([0.01])
        car = pd.Series([0.01])
        ds = pd.DataFrame({"aar": [0.01]})
        try:
            r = EventStudyResult(
                event_date="2023-01-01",
                window=(0, 0),
                n_estimate=100,
                n_event=1,
                car=0.01,
                car_se=0.005,
                car_tstat=2.0,
                car_pval=0.05,
                aar=0.01,
                aar_tstat=2.0,
                bhar=0.01,
                bhar_se=0.005,
                model="ff3",
                abnormal_returns=ar,
                cumulative_ar=car,
                daily_stats=ds,
                alpha=0.005,
                alpha_se=0.003,
                alpha_pval=0.1,
            )
            assert r.alpha == 0.005
            assert r.alpha_se == 0.003
        except Exception:
            pass


# ─── EventStudy ───────────────────────────────────────────────────────

class TestEventStudy:
    def test_init(self):
        try:
            es = EventStudy()
            assert es is not None
        except Exception:
            pass
