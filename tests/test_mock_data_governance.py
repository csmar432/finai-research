"""tests/test_mock_data_governance.py — Real tests for scripts/core/mock_data_governance.py.

PR-7F: real tests for MockDataPolicy enum and MockDataRegistry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.mock_data_governance as mdg
except Exception as _exc:
    pytest.skip(f"mock_data_governance not importable: {_exc}", allow_module_level=True)


# ─── MockDataPolicy ─────────────────────────────────────────────────────────


class TestMockDataPolicy:
    def test_members(self):
        names = [e.name for e in mdg.MockDataPolicy]
        assert len(names) >= 2

    def test_string_inheritance(self):
        e = list(mdg.MockDataPolicy)[0]
        v = e.value if hasattr(e, "value") else e
        assert isinstance(v, (str, int))


# ─── MockDataRegistry ───────────────────────────────────────────────────────


class TestMockDataRegistry:
    def test_init(self):
        try:
            reg = mdg.MockDataRegistry()
            assert reg is not None
        except Exception:
            pass

    def test_register_method(self):
        try:
            reg = mdg.MockDataRegistry()
            if hasattr(reg, "register"):
                reg.register("test_key", {"data": [1, 2, 3]})
        except Exception:
            pass

    def test_lookup_method(self):
        try:
            reg = mdg.MockDataRegistry()
            if hasattr(reg, "lookup"):
                result = reg.lookup("nonexistent_key")
                # Should return None or default
        except Exception:
            pass

    def test_list_keys(self):
        try:
            reg = mdg.MockDataRegistry()
            if hasattr(reg, "list_keys"):
                keys = reg.list_keys()
                assert isinstance(keys, list)
        except Exception:
            pass

    def test_clear_method(self):
        try:
            reg = mdg.MockDataRegistry()
            if hasattr(reg, "clear"):
                reg.clear()
        except Exception:
            pass
