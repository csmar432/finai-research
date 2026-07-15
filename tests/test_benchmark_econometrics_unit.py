"""Unit tests for scripts/benchmark_econometrics.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def be():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    # Use importlib to load directly (handles CI xdist worker subprocesses
    # where scripts.__init__ may not have eagerly imported all modules)
    import importlib
    try:
        mod = importlib.import_module("scripts.benchmark_econometrics")
    except ImportError:
        # Fall back to direct file load if package import fails
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "scripts.benchmark_econometrics",
            "scripts/benchmark_econometrics.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["scripts.benchmark_econometrics"] = mod
        spec.loader.exec_module(mod)
    yield mod
    if _p in sys.path:
        sys.path.remove(_p)


class TestBenchmarkResult:
    def test_init(self, be):
        r = be.BenchmarkResult(
            method="DID",
            project_estimate=0.15,
            reference_estimate=0.16,
            max_abs_diff=0.01,
            tolerance=0.05,
            passed=True,
            details={"n_obs": 1000},
            elapsed_ms=120.5,
        )
        assert r.method == "DID"
        assert r.passed is True
        assert abs(r.project_estimate - 0.15) < 1e-9

    def test_default_details_and_elapsed(self, be):
        r = be.BenchmarkResult(
            method="RDD",
            project_estimate=0.1,
            reference_estimate=0.1,
            max_abs_diff=0.0,
            tolerance=0.01,
            passed=True,
        )
        assert r.details == {}
        assert r.elapsed_ms == 0.0
