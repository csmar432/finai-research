"""Unit tests for scripts/quantitative_factor_library.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def qfl():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import quantitative_factor_library as q
    yield q
    if _p in sys.path:
        sys.path.remove(_p)


class TestEventStudyResult:
    def test_init(self, qfl):
        e = qfl.EventStudyResult(
            event_date="2024-01-01",
            window=(-1, 1),
            n_estimate=200,
            n_event=50,
            car=0.05,
            car_se=0.02,
            car_tstat=2.5,
            car_pval=0.013,
            aar=0.01,
            aar_tstat=1.5,
            bhar=0.04,
            bhar_se=0.025,
            model="market_model",
            abnormal_returns=[0.01, 0.02, -0.005],
            cumulative_ar=[0.01, 0.03, 0.025],
            daily_stats=[],
        )
        assert e.event_date == "2024-01-01"
        assert e.alpha is None
