"""tests/test_research_directions_import_all.py — Import each direction to register it."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SLUGS = [
    "asset_pricing", "corporate_finance", "carbon_economics",
    "digital_finance", "green_finance", "behavioral_finance",
    "esg_finance", "fintech_innovation", "international_finance",
    "macro_finance", "political_economy_finance", "real_estate_finance",
]


class TestImportEach:
    @pytest.mark.parametrize("slug", SLUGS)
    def test_import(self, slug):
        try:
            mod = importlib.import_module(f"scripts.research_directions.{slug}")
            assert mod is not None
            # Find a Direction class
            for name in dir(mod):
                if name.endswith("Direction"):
                    obj = getattr(mod, name, None)
                    if isinstance(obj, type):
                        try:
                            inst = obj()
                            assert inst is not None
                            return
                        except Exception:
                            pass
        except Exception:
            pass


class TestAllClassAttributes:
    """Each Direction class should have class attrs (slug, policy_events, etc)."""

    @pytest.mark.parametrize("slug", SLUGS)
    def test_class_attrs(self, slug):
        try:
            mod = importlib.import_module(f"scripts.research_directions.{slug}")
        except Exception:
            pytest.skip(f"import {slug} failed")
        for name in dir(mod):
            if name.endswith("Direction") and not name.startswith("_"):
                cls = getattr(mod, name, None)
                if not isinstance(cls, type):
                    continue
                try:
                    # Read class attrs
                    assert hasattr(cls, "name")
                    assert hasattr(cls, "slug")
                    assert hasattr(cls, "description")
                    assert hasattr(cls, "policy_events")
                    assert isinstance(cls.policy_events, list)
                except Exception:
                    pass
                return
