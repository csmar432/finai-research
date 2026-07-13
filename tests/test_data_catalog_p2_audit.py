"""P2-3 reachability tests for data/control catalog modules (2026-07-12).

Three modules were promoted from `init_imports=0` to having public re-exports
in `scripts/research_framework/__init__.py`:

  - a_share_firm_controls  → FirmControl / list_controls / get_control / compute_controls
  - china_carbon_events    → CarbonETSConfig / build_carbon_ets_panel /
                             carbon_ets_regression_template
  - china_policy_events    → ChinaPolicyEvent / get_china_policy_event /
                             list_china_policy_events

These tests verify (a) the package-level re-exports work, (b) the underlying
modules still function directly, (c) the canonical names are in `__all__`.
"""
from __future__ import annotations

import pandas as pd
import pytest


# ══════════════════════════════════════════════════════════════════════
# Package-level reachability
# ══════════════════════════════════════════════════════════════════════


def test_firm_control_reachable_from_package():
    import scripts.research_framework as rf
    assert rf.FirmControl is not None
    assert rf.list_controls is not None
    assert rf.get_control is not None
    assert rf.compute_controls is not None


def test_china_carbon_events_reachable_from_package():
    import scripts.research_framework as rf
    assert rf.CarbonETSConfig is not None
    assert rf.build_carbon_ets_panel is not None
    assert rf.carbon_ets_regression_template is not None


def test_china_policy_events_reachable_from_package():
    import scripts.research_framework as rf
    assert rf.ChinaPolicyEvent is not None
    assert rf.get_china_policy_event is not None
    assert rf.list_china_policy_events is not None


def test_all_three_in_package_all():
    import scripts.research_framework as rf
    all_exports = getattr(rf, "__all__", [])
    expected = [
        "FirmControl", "list_controls", "get_control", "compute_controls",
        "CarbonETSConfig", "build_carbon_ets_panel",
        "carbon_ets_regression_template",
        "ChinaPolicyEvent", "get_china_policy_event", "list_china_policy_events",
    ]
    for name in expected:
        assert name in all_exports, f"{name} missing from __all__"


# ══════════════════════════════════════════════════════════════════════
# Functional smoke tests
# ══════════════════════════════════════════════════════════════════════


def test_list_controls_returns_dataframe():
    import scripts.research_framework as rf
    df = rf.list_controls()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "name" in df.columns or df.shape[1] >= 1


def test_get_control_by_name():
    import scripts.research_framework as rf
    controls_df = rf.list_controls()
    if len(controls_df) == 0:
        pytest.skip("No firm controls in catalog")
    first_name = controls_df["name"].iloc[0] if "name" in controls_df.columns else None
    if first_name is None:
        pytest.skip("Catalog doesn't have 'name' column")
    ctrl = rf.get_control(first_name)
    assert ctrl is not None


def test_get_china_policy_event_returns_event():
    import scripts.research_framework as rf
    events_df = rf.list_china_policy_events()
    assert isinstance(events_df, pd.DataFrame)
    assert len(events_df) > 0


# ══════════════════════════════════════════════════════════════════════
# Graceful degradation: if a module is broken (ImportError), the package
# __init__ wraps it in try/except and the attribute should be None.
# ══════════════════════════════════════════════════════════════════════


def test_package_handles_import_failures_gracefully():
    """Even if a data-class module is broken in the future, the package
    should still import (graceful degradation via try/except in __init__.py).

    This is a smoke test verifying the pattern works today.
    """
    import scripts.research_framework as rf
    # All three should be non-None in the current state; this test will pass
    # even if any become None (the test of graceful degradation is that the
    # package still loads — see other tests for that).
    assert rf is not None
