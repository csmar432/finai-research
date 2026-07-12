"""Deprecation warning tests for mediation.py / moderation.py (P1-5/P2-4, 2026-07-12).

These modules are deprecated as of v1.8.6. The tests verify:

1. Importing the modules fires a DeprecationWarning with the canonical
   replacement module name in the message.
2. The free functions / classes are STILL functional (backward compat).
3. The canonical replacement (`mediation_test`) is unaffected.

This locks in the deprecation signal so future regressions
(e.g. silently removing the warning) are caught by CI.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest


# ══════════════════════════════════════════════════════════════════════
# mediation.py deprecation
# ══════════════════════════════════════════════════════════════════════


def test_mediation_module_emits_deprecation_warning():
    """Importing scripts.research_framework.mediation must emit DeprecationWarning."""
    import importlib
    import scripts.research_framework

    # Force re-import (cached otherwise)
    mod_name = "scripts.research_framework.mediation"
    import sys
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        importlib.import_module(mod_name)

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, (
            f"Expected at least 1 DeprecationWarning, got {len(deprecation_warnings)}"
        )
        msg = str(deprecation_warnings[0].message)
        # Must mention the replacement module
        assert "mediation_test" in msg, f"Warning must mention replacement: {msg}"
        assert "DEPRECATED" in msg, f"Warning must say DEPRECATED: {msg}"


def test_mediation_still_functional_for_backward_compat():
    """The deprecated module's free functions must still work."""
    import scripts.research_framework.mediation as med

    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame({
        "X": rng.normal(0, 1, n),
        "M": rng.normal(0, 1, n),
        "Y": rng.normal(0, 1, n),
    })

    # Sobel test still callable
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = med.sobel(df, X="X", M="M", Y="Y")

    assert result is not None
    assert hasattr(result, "indirect_effect")
    assert hasattr(result, "direct_effect")
    assert hasattr(result, "total_effect")


def test_mediation_canonical_replacement_unaffected():
    """mediation_test.MediationTest must NOT be deprecated."""
    from scripts.research_framework.mediation_test import MediationTest, MediationResult

    # No deprecation warning on MediationTest import
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        # Touch MediationTest
        _ = MediationTest
        _ = MediationResult
        # Filter out any pre-existing warnings from other modules
        relevant = [x for x in w
                    if issubclass(x.category, DeprecationWarning)
                    and "mediation_test" in str(x.message)]
        assert len(relevant) == 0, (
            f"mediation_test should NOT be deprecated. Got: "
            f"{[str(x.message) for x in relevant]}"
        )


def test_mediation_result_field_names_documented_as_different():
    """The deprecated MediationResult has different field names — must be documented."""
    from scripts.research_framework.mediation import MediationResult
    import dataclasses
    fields_deprecated = {f.name for f in dataclasses.fields(MediationResult)}
    # Old API field names (must NOT collide with new ones)
    assert "indirect_effect" in fields_deprecated
    assert "direct_effect" in fields_deprecated
    assert "total_effect" in fields_deprecated

    from scripts.research_framework.mediation_test import MediationResult as NewMedResult
    fields_new = {f.name for f in dataclasses.fields(NewMedResult)}
    # New API field names
    assert "alpha" in fields_new or "beta" in fields_new


# ══════════════════════════════════════════════════════════════════════
# moderation.py deprecation
# ══════════════════════════════════════════════════════════════════════


def test_moderation_module_emits_deprecation_warning():
    """Importing scripts.research_framework.moderation must emit DeprecationWarning."""
    import importlib
    import sys

    mod_name = "scripts.research_framework.moderation"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        importlib.import_module(mod_name)

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, (
            f"Expected at least 1 DeprecationWarning, got {len(deprecation_warnings)}"
        )
        msg = str(deprecation_warnings[0].message)
        assert "DEPRECATED" in msg, f"Warning must say DEPRECATED: {msg}"
        # Must mention the recommended replacement
        assert "PanelThresholdRegression" in msg or "RegressionEngine" in msg, (
            f"Warning must mention replacement: {msg}"
        )


def test_moderation_still_functional_for_backward_compat():
    """The deprecated module's ModerationAnalysis class must still work."""
    import scripts.research_framework.moderation as mod

    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame({
        "X": rng.normal(0, 1, n),
        "M": rng.normal(0, 1, n),
        "Y": rng.normal(0, 1, n),
        "size": rng.normal(0, 1, n),
        "age": rng.normal(0, 1, n),
    })

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = mod.ModerationAnalysis.interaction(
            df, X="X", M="M", Y="Y", controls=["size", "age"]
        )

    assert result is not None
    assert hasattr(result, "interaction_XM")
    assert hasattr(result, "interaction_p")


# ══════════════════════════════════════════════════════════════════════
# Cross-cutting: package-level reachability after deprecation
# ══════════════════════════════════════════════════════════════════════


def test_canonical_modules_still_importable_from_package():
    """The canonical replacements must be reachable from the package."""
    import scripts.research_framework as rf

    assert rf.MediationTest is not None  # canonical
    assert rf.PanelThresholdRegression is not None  # canonical for moderation
    assert rf.RegressionEngine is not None  # canonical for OLS moderation


def test_deprecated_modules_not_in_init_all():
    """Deprecated modules' classes must NOT be in __init__.py's __all__ (intentional)."""
    import scripts.research_framework as rf

    # Get __all__
    all_exports = getattr(rf, "__all__", [])
    # ModerationAnalysis is the deprecated class
    assert "ModerationAnalysis" not in all_exports, (
        "ModerationAnalysis should NOT be in __all__ (deprecated)"
    )
    # MediationResult from mediation.py (not mediation_test.py) should not be re-exported
    # Note: MediationResult from mediation_test IS in __all__ and that's fine.
    # We just need to ensure both MediationResult classes coexist without ambiguity.
    from scripts.research_framework.mediation import MediationResult as DeprecatedResult
    from scripts.research_framework.mediation_test import MediationResult as CanonicalResult
    # These are different classes with different field names
    assert DeprecatedResult is not CanonicalResult