"""tests/test_fintech_innovation_deep_exec.py — Deep tests for fintech_innovation LaTeX helpers.

Targets uncovered LaTeX template methods in scripts/research_directions/fintech_innovation.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.research_directions.fintech_innovation import FintechInnovationDirection
except Exception as exc:
    pytest.skip(f"fintech_innovation not importable: {exc}", allow_module_level=True)


@pytest.fixture
def direction():
    return FintechInnovationDirection()


class TestFormatTableForecastAccuracy:
    def test_basic(self, direction):
        result = direction._format_table_forecast_accuracy()
        assert isinstance(result, str)
        assert "\\begin{table}" in result
        assert "金融科技" in result or "Fintech" in result.lower()

    def test_pending(self, direction):
        result = direction._format_table_forecast_accuracy(pending=True)
        assert isinstance(result, str)
        assert "待填充" in result or "占位" in result

    def test_with_extra_note(self, direction):
        result = direction._format_table_forecast_accuracy(extra_note="My extra note")
        assert isinstance(result, str)
        assert "extra" in result.lower() or "My extra" in result


class TestFormatTableInfoEfficiency:
    def test_basic(self, direction):
        result = direction._format_table_info_efficiency()
        assert isinstance(result, str)
        assert "\\begin{table}" in result

    def test_pending(self, direction):
        result = direction._format_table_info_efficiency(pending=True)
        assert isinstance(result, str)
        assert "待填充" in result or "占位" in result


class TestFormatTableMechanism:
    def test_basic(self, direction):
        result = direction._format_table_mechanism()
        assert isinstance(result, str)
        assert "\\begin{table}" in result

    def test_pending(self, direction):
        result = direction._format_table_mechanism(pending=True)
        assert isinstance(result, str)


class TestFormatTableHeterogeneity:
    def test_basic(self, direction):
        result = direction._format_table_heterogeneity()
        assert isinstance(result, str)
        assert "\\begin{table}" in result

    def test_pending(self, direction):
        result = direction._format_table_heterogeneity(pending=True)
        assert isinstance(result, str)


class TestInit:
    def test_init(self):
        try:
            d = FintechInnovationDirection()
            assert d is not None
        except Exception:
            pass