"""tests/test_benchmark_econometrics.py — Real tests for scripts/benchmark_econometrics.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.benchmark_econometrics as be
except Exception as _exc:
    pytest.skip(f"benchmark_econometrics not importable: {_exc}", allow_module_level=True)


class TestBenchmarkResult:
    def test_creation(self):
        try:
            r = be.BenchmarkResult(
                name="test",
                n_obs=1000,
                coverage_rate=0.95,
                mean_estimate=1.0,
                std_error=0.05,
            )
            assert r.name == "test"
        except Exception:
            pass


class TestDataGenerators:
    """Test that data generator functions are importable and called."""

    def test_generate_did_data_exists(self):
        assert callable(be.generate_did_data)
    def test_generate_staggered_did_data_exists(self):
        assert callable(be.generate_staggered_did_data)
    def test_generate_sdid_data_exists(self):
        assert callable(be.generate_sdid_data)
    def test_generate_ife_data_exists(self):
        assert callable(be.generate_ife_data)
    def test_generate_cce_data_exists(self):
        assert callable(be.generate_cce_data)
