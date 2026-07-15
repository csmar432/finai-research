"""Unit tests for scripts/setup_wizard.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def sw():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts import setup_wizard as s
    yield s
    if _p in sys.path:
        sys.path.remove(_p)


class TestConfigStatus:
    def test_init(self, sw):
        cfg = sw.ConfigStatus(
            var_name="TUSHARE_TOKEN",
            is_set=False,
            is_sensitive=True,
            current_value="",
            priority=1,
            description="Tushare Pro API token",
            for_directions=["digital_finance"],
        )
        assert cfg.var_name == "TUSHARE_TOKEN"
        assert cfg.is_sensitive is True
        assert cfg.placeholder == ""


class TestDirectionConfig:
    def test_init(self, sw):
        d = sw.DirectionConfig(
            direction="digital_finance",
            label="Digital Finance",
            description="Research on digital finance and fintech",
            required=["TUSHARE_TOKEN"],
            recommended=["DEEPSEEK_API_KEY"],
            nice=["WIND_API_KEY"],
            mcp_servers=["user-tushare"],
        )
        assert d.direction == "digital_finance"
        assert "TUSHARE_TOKEN" in d.required


class TestMCPStatus:
    def test_init(self, sw):
        m = sw.MCPStatus(
            server_id="user-tushare",
            name="Tushare MCP",
            installed=True,
            enabled=True,
            needs_api_key=True,
            api_key_var="TUSHARE_TOKEN",
            description="Chinese A-stock data",
            for_directions=["digital_finance"],
        )
        assert m.server_id == "user-tushare"
        assert m.needs_api_key is True


class TestAllConfigs:
    def test_dict_exists(self, sw):
        assert hasattr(sw, "ALL_CONFIGS")
        assert isinstance(sw.ALL_CONFIGS, (dict, list))
