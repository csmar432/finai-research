"""Unit tests for scripts.research_directions.asset_pricing module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def MODULE_ABBREV():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.research_directions import asset_pricing as m

    yield m
    if _p in sys.path:
        sys.path.remove(_p)


def test_module_imports(MODULE_ABBREV):
    assert MODULE_ABBREV is not None
    assert hasattr(MODULE_ABBREV, "AssetPricingDirection")


def test_get_registry(MODULE_ABBREV):
    factory = MODULE_ABBREV.get_registry()()
    assert factory is not None
    assert hasattr(factory, "list_all")
    directions = factory.list_all()
    assert isinstance(directions, list)
    assert len(directions) > 0


def test_direction_class_exists(MODULE_ABBREV):
    cls = MODULE_ABBREV.AssetPricingDirection
    assert cls is not None
    assert isinstance(cls, type)


def test_direction_slug_registered(MODULE_ABBREV):
    factory = MODULE_ABBREV.get_registry()()
    all_dirs = factory.list_all()
    assert "asset_pricing" in all_dirs
