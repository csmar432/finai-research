"""Unit tests for scripts.research_directions._legacy_registry module.

The legacy registry module preserves the original inline dataclass literals
(about 1,972 lines) as a ``_LEGACY_INIT_REGISTRY_SOURCE`` string. These tests
verify the structure of the preserved source code rather than executing it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def MODULE_ABBREV():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.research_directions import _legacy_registry as m

    yield m
    if _p in sys.path:
        sys.path.remove(_p)


def test_module_imports(MODULE_ABBREV):
    assert MODULE_ABBREV is not None
    assert MODULE_ABBREV.__name__ == "scripts.research_directions._legacy_registry"


def test_legacy_source_attribute_exists(MODULE_ABBREV):
    """The preserved source string is exposed as a module-level constant."""
    assert hasattr(MODULE_ABBREV, "_LEGACY_INIT_REGISTRY_SOURCE")


def test_legacy_source_is_string(MODULE_ABBREV):
    assert isinstance(MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE, str)


def test_legacy_source_substantial(MODULE_ABBREV):
    """The preserved source is non-trivial (the inline impl was ~1.9k lines)."""
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    assert len(src) > 50_000


def test_legacy_source_has_registry_assignments(MODULE_ABBREV):
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    # Count `cls._registry[...] = ResearchDirection(...)` blocks
    matches = re.findall(r'cls\._registry\["([^"]+)"\]', src)
    assert len(matches) >= 30, f"Expected ≥30 directions, found {len(matches)}"


def test_legacy_source_contains_known_directions(MODULE_ABBREV):
    """Sanity-check that the well-known direction keys are in the preserved source."""
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    expected_keys = [
        "carbon_trading",
        "green_bond",
        "esg_factor_pricing",
        "fintech_bank_efficiency",
        "tariff_policy_trade_flow",
        "minimum_wage_employment",
    ]
    for k in expected_keys:
        assert f'cls._registry["{k}"]' in src, f"Missing direction key: {k}"


def test_legacy_source_has_required_fields(MODULE_ABBREV):
    """Every ResearchDirection entry declares direction_name, display_name, etc."""
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    expected_fields = [
        "direction_name",
        "display_name",
        "literature_theme",
        "difficulty",
        "estimated_pages",
        "keywords",
        "sub_topics",
        "references",
    ]
    for f in expected_fields:
        # Each field name appears at least once for every direction.
        # 40 directions * 1 = at least 40 occurrences total.
        count = src.count(f)
        assert count >= 30, f"Field '{f}' appears only {count} times"


def test_legacy_source_has_40_directions(MODULE_ABBREV):
    """The legacy registry contained exactly 40 ResearchDirection entries."""
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    keys = re.findall(r'cls\._registry\["([^"]+)"\]', src)
    assert len(keys) == 40, f"Expected 40 directions, found {len(keys)}"


def test_legacy_source_unique_keys(MODULE_ABBREV):
    """All direction keys are unique (no duplicates)."""
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    keys = re.findall(r'cls\._registry\["([^"]+)"\]', src)
    assert len(keys) == len(set(keys)), "Duplicate direction keys found"


def test_legacy_source_difficulty_values(MODULE_ABBREV):
    """Each direction has a difficulty of 'intermediate' or 'advanced'."""
    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    difficulties = re.findall(r'difficulty="(intermediate|advanced)"', src)
    assert len(difficulties) >= 30, f"Expected ≥30 difficulty tags, found {len(difficulties)}"


def test_legacy_source_no_top_level_functions(MODULE_ABBREV):
    """The module should not export executable callables (only the source string)."""
    callable_exports = []
    for name in dir(MODULE_ABBREV):
        if name.startswith("__"):
            continue
        obj = getattr(MODULE_ABBREV, name)
        if callable(obj) and not isinstance(obj, type):
            callable_exports.append(name)
    assert callable_exports == [], f"Unexpected callables: {callable_exports}"


def test_legacy_source_pythonic(MODULE_ABBREV):
    """The preserved source is valid Python syntax."""
    import ast

    src = MODULE_ABBREV._LEGACY_INIT_REGISTRY_SOURCE
    # ast.parse expects statements at the proper indent level
    # Indent all lines by 8 spaces and prepend with a def
    indented = "\n".join("        " + line for line in src.split("\n"))
    wrapper = f"def _init_registry_legacy(cls):\n{indented}\n"
    try:
        ast.parse(wrapper)
    except SyntaxError as e:
        pytest.fail(f"Legacy source has syntax error: {e}")
