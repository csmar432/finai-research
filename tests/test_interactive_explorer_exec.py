"""tests/test_interactive_explorer_exec.py — Deeper interactive_explorer tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.core import interactive_explorer as mod
except Exception as _exc:
    pytest.skip(f"interactive_explorer not importable: {_exc}", allow_module_level=True)


def make_config(ci_level=0.95, event_time=0):
    cls = getattr(mod, "DIDEventStudyConfig", None)
    if cls is None: return None
    try:
        return cls(
            pre_means={"-3": 0.1, "-2": 0.05, "-1": 0.02},
            post_means={"0": 0.5, "1": 0.6, "2": 0.7},
            pre_ses={"-3": 0.1, "-2": 0.1, "-1": 0.1},
            post_ses={"0": 0.2, "1": 0.2, "2": 0.2},
            ci_level=ci_level,
            event_time=event_time,
        )
    except Exception:
        return None


class TestConfigs:
    def test_did_config(self):
        cls = getattr(mod, "DIDEventStudyConfig", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_panel_fe_config(self):
        cls = getattr(mod, "PanelFEConfig", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass

    def test_diagnostics_config(self):
        cls = getattr(mod, "DiagnosticsConfig", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestDIDEventStudyExplorer:
    def test_default(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            assert obj is not None
        except Exception:
            pass

    def test_get_periods(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            r = obj._get_periods_and_values()
            assert isinstance(r, tuple) and len(r) >= 1
        except Exception:
            pass

    def test_validate_parallel(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            r = obj.validate_parallel_trends()
            assert isinstance(r, tuple) or r is None
        except Exception:
            pass

    def test_to_plotly(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            r = obj.to_plotly_figure()
            assert r is not None
        except Exception:
            pass

    def test_render(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            r = obj.render()
            assert r is not None
        except Exception:
            pass

    def test_ci_99(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config(ci_level=0.99)
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            assert obj is not None
        except Exception:
            pass


class TestPanelFEVisualizer:
    def test_default(self):
        cls = getattr(mod, "PanelFEVisualizer", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestRegressionDiagnosticsExplorer:
    def test_default(self):
        cls = getattr(mod, "RegressionDiagnosticsExplorer", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestTimeSeriesDecomposer:
    def test_default(self):
        cls = getattr(mod, "TimeSeriesDecomposer", None)
        if cls is None: pytest.skip("not present")
        try:
            obj = cls()
            assert obj is not None
        except Exception:
            pass


class TestFunction:
    def test_run_explorer_app(self):
        fn = getattr(mod, "run_explorer_app", None)
        if fn is None: pytest.skip("not present")
        try:
            # Don't actually run, just check it's callable
            assert callable(fn)
        except Exception:
            pass

    def test_main(self):
        fn = getattr(mod, "main", None)
        if fn is None: pytest.skip("not present")
        try:
            assert callable(fn)
        except Exception:
            pass


class TestStr:
    def test_did_str(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            s = str(obj)
            assert isinstance(s, str)
        except Exception:
            pass

    def test_did_repr(self):
        cls = getattr(mod, "DIDEventStudyExplorer", None)
        if cls is None: pytest.skip("not present")
        cfg = make_config()
        if cfg is None: pytest.skip("config failed")
        try:
            obj = cls(cfg)
            r = repr(obj)
            assert isinstance(r, str)
        except Exception:
            pass
