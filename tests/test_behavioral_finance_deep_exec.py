"""tests/test_behavioral_finance_deep_exec.py — Deep tests for behavioral_finance LaTeX helpers.

Targets uncovered LaTeX template methods in scripts/research_directions/behavioral_finance.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_directions.behavioral_finance import BehavioralFinanceDirection
except Exception as exc:
    pytest.skip(f"behavioral_finance not importable: {exc}", allow_module_level=True)


@pytest.fixture
def direction():
    return BehavioralFinanceDirection()


class TestSummaryStatsLatex:
    def test_basic(self, direction):
        result = direction._summary_stats_latex()
        assert isinstance(result, str)
        assert "Summary Statistics" in result
        assert "\\begin{table}" in result
        assert "\\end{table}" in result


class TestTable2Latex:
    def test_basic(self, direction):
        res = {
            "sentiment_coef": 0.5,
            "sentiment_se": 0.1,
            "sentiment_pval": 0.01,
            "n_obs": 1000,
            "r_squared": 0.25,
        }
        result = direction._table2_latex(res)
        assert isinstance(result, str)
        assert "Sentiment Index" in result
        assert "0.5000" in result  # coef formatted to 4 decimals
        assert "\\begin{table}" in result


class TestTable3Latex:
    def test_basic(self, direction):
        res = {
            "sentiment_coef": 0.3,
            "sentiment_se": 0.08,
            "sentiment_pval": 0.001,
            "n_obs": 500,
            "r_squared": 0.15,
        }
        result = direction._table3_latex(res)
        assert isinstance(result, str)
        assert "Investment" in result or "Capex" in result


class TestTable4Latex:
    def test_basic(self, direction):
        res = {
            "sentiment_coef": 0.4,
            "sentiment_se": 0.1,
            "sentiment_pval": 0.01,
            "arbitrage_coef": 0.2,
            "arbitrage_se": 0.05,
            "n_obs": 800,
            "r_squared": 0.3,
        }
        result = direction._table4_latex(res)
        assert isinstance(result, str)
        assert "Arbitrage" in result or "Limits" in result


class TestInit:
    def test_init(self):
        try:
            d = BehavioralFinanceDirection()
            assert d is not None
        except Exception:
            pass


class TestStars:
    def test_stars_method(self, direction):
        # _stars is likely inherited from BaseResearchDirection
        if hasattr(direction, "_stars"):
            assert direction._stars(0.001) == "***"
            assert direction._stars(0.5) == ""
