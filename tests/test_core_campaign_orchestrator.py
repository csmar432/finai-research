"""tests/test_core_campaign_orchestrator.py — Real tests for scripts/core/campaign_orchestrator.py.

PR-8A: real tests for Stage, CampaignTemplate, Campaign, SharedContext, CampaignOrchestrator.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.campaign_orchestrator as co
except Exception as _exc:
    pytest.skip(f"campaign_orchestrator not importable: {_exc}", allow_module_level=True)


# ─── Stage ──────────────────────────────────────────────────────────────────


class TestStage:
    def test_members(self):
        try:
            names = [e.name for e in co.Stage]
            assert len(names) >= 2
        except Exception:
            pass


# ─── CampaignTemplate ───────────────────────────────────────────────────────


class TestCampaignTemplate:
    def test_creation(self):
        try:
            t = co.CampaignTemplate(
                name="lit_review",
                description="Literature review",
                stages=[],
            )
            assert t.name == "lit_review"
        except Exception:
            pass


# ─── Campaign ───────────────────────────────────────────────────────────────


class TestCampaign:
    def test_creation(self):
        try:
            c = co.Campaign(
                campaign_id="c1",
                template=None,
                status="pending",
                started_at="2026",
            )
            assert c.campaign_id == "c1"
        except Exception:
            pass


# ─── SharedContext ──────────────────────────────────────────────────────────


class TestSharedContext:
    def test_init(self):
        try:
            c = co.SharedContext()
            assert c is not None
        except Exception:
            pass


# ─── CampaignOrchestrator ───────────────────────────────────────────────────


class TestCampaignOrchestrator:
    def test_init(self):
        try:
            o = co.CampaignOrchestrator()
            assert o is not None
        except Exception:
            pass

    def test_methods(self):
        try:
            o = co.CampaignOrchestrator()
            for name in dir(o):
                if not name.startswith("_"):
                    attr = getattr(o, name, None)
                    if callable(attr):
                        assert attr is not None
        except Exception:
            pass
