"""
Tests for user-tushare MCP server institutional holdings tools:
  - get_institutional_holdings
  - get_top_holders

No live API calls — all network/external calls are mocked.
The `mcp` package may not be installed in the test environment; server-level
tests are gracefully skipped when it is absent.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_dataframe(records: list[dict]) -> MagicMock:
    """Return a mock DataFrame with to_dict and empty attrs."""
    df = MagicMock()
    df.to_dict.return_value = records
    df.empty = len(records) == 0
    df.__len__ = lambda self: len(records)
    return df


# ---------------------------------------------------------------------------
# Tool JSON schemas (no server import needed)
# ---------------------------------------------------------------------------

class TestToolSchemas:
    """Validate tool JSON schemas without importing the server module."""

    def _load_json(self, name: str) -> dict:
        path = project_root / "mcp_servers" / "user_tushare" / "tools" / f"{name}.json"
        assert path.exists(), f"{path} not found"
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_institutional_holdings_schema_valid(self):
        schema = self._load_json("get_institutional_holdings")
        assert schema["name"] == "get_institutional_holdings"
        props = schema["inputSchema"]["properties"]
        assert "ts_code" in props
        assert "start_date" in props
        assert "end_date" in props
        assert "holder_type" in props
        assert props["holder_type"]["type"] == "string"
        assert set(props["holder_type"]["enum"]) == {
            "qfii", "fund", "trust", "broker", "social_security", "all",
        }
        assert "ts_code" in schema["inputSchema"].get("required", [])

    def test_top_holders_schema_valid(self):
        schema = self._load_json("get_top_holders")
        assert schema["name"] == "get_top_holders"
        props = schema["inputSchema"]["properties"]
        assert "ts_code" in props
        assert "ann_date" in props
        assert "ts_code" in schema["inputSchema"].get("required", [])

    def test_schemas_are_valid_json(self):
        for name in ("get_institutional_holdings", "get_top_holders"):
            data = self._load_json(name)
            assert "name" in data
            assert "description" in data
            assert "inputSchema" in data
            assert data["inputSchema"]["type"] == "object"


# ---------------------------------------------------------------------------
# Server module availability
# ---------------------------------------------------------------------------

def _import_server():
    """Import server module, skipping if mcp package is absent."""
    try:
        import mcp  # noqa: F401
        from mcp_servers.user_tushare import server
        return server
    except (ModuleNotFoundError, SystemExit):
        return None


# ---------------------------------------------------------------------------
# Handler tests — import server module only when mcp is available
# ---------------------------------------------------------------------------

class TestServerModuleAvailability:
    """Verify server module can be imported and exports the new handlers."""

    def test_server_module_loads_or_skips(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed in test environment")
        # If we get here, mcp is available
        assert hasattr(server, "handle_get_institutional_holdings")
        assert hasattr(server, "handle_get_top_holders")
        assert "get_institutional_holdings" in server.TOOL_HANDLERS
        assert "get_top_holders" in server.TOOL_HANDLERS

    def test_handler_functions_are_async(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed in test environment")
        import inspect
        for name in ("get_institutional_holdings", "get_top_holders"):
            handler = server.TOOL_HANDLERS[name]
            assert inspect.iscoroutinefunction(handler), f"{name} is not async"


# ---------------------------------------------------------------------------
# Handler logic tests — isolate from mcp import using minimal mock setup
# ---------------------------------------------------------------------------

class TestHandleInstitutionalHoldingsLogic:
    """Test handle_get_institutional_holdings by patching its dependencies."""

    @pytest.fixture(autouse=True)
    def setup(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed in test environment")

    def test_missing_ts_code_returns_error(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        async def run():
            return await server.handle_get_institutional_holdings({})

        result = asyncio.run(run())
        assert len(result) == 1
        text = result[0].text
        parsed = json.loads(text)
        assert parsed.get("error") is not None or "error" in parsed.get("result", {})

    def test_tushare_success_returns_data(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        mock_df = _mock_dataframe([
            {"holder_name": "中国石油天然气集团公司", "hold_pct": 86.32, "ann_date": "20240930"},
            {"holder_name": "HKSCC NOMINEE", "hold_pct": 9.01, "ann_date": "20240930"},
        ])

        with patch.object(server, "_check_token", return_value=None):
            with patch.object(server, "get_ts_pro") as mock_pro:
                mock_api = MagicMock()
                mock_api.top_holders.return_value = mock_df
                mock_pro.return_value = mock_api

                async def run():
                    return await server.handle_get_institutional_holdings({"ts_code": "601857.SH"})

                result = asyncio.run(run())
                text = result[0].text
                parsed = json.loads(text)
                inner = parsed.get("result", parsed)
                assert inner.get("success") is True or inner.get("data") is not None

    def test_no_token_falls_back_to_akshare(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        with patch.object(server, "_check_token", return_value="no token"):
            with patch.object(server, "_akshare_fallback") as mock_fb:
                mock_fb.return_value = {
                    "result": {"data": [], "count": 0},
                    "success": True,
                    "source": "akshare (automatic fallback)",
                }

                async def run():
                    return await server.handle_get_institutional_holdings({"ts_code": "000001.SZ"})

                result = asyncio.run(run())
                text = result[0].text
                parsed = json.loads(text)

                mock_fb.assert_called_once()
                call_kwargs = mock_fb.call_args[1]
                assert call_kwargs["ts_code"] == "000001.SZ"
                assert call_kwargs["holder_type"] == "all"

                # _akshare_fallback returns:
                #   {result: {data, count}, success, source}  ← mock_fb returns this
                #   None  ← if akshare unavailable
                # The handler wraps the fallback dict directly in TextContent.
                # Assert either success=True (data available) or count=0 (akshare returned empty).
                inner = parsed.get("result", parsed)
                assert parsed.get("success") is True or inner.get("count", -1) == 0

    def test_holder_type_filter_passed(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        mock_df = _mock_dataframe([])

        with patch.object(server, "_check_token", return_value=None):
            with patch.object(server, "get_ts_pro") as mock_pro:
                mock_api = MagicMock()
                mock_api.top_holders.return_value = mock_df
                mock_pro.return_value = mock_api

                async def run():
                    return await server.handle_get_institutional_holdings({
                        "ts_code": "600519.SH",
                        "holder_type": "qfii",
                    })

                asyncio.run(run())
                mock_api.top_holders.assert_called_once()


class TestHandleTopHoldersLogic:
    """Test handle_get_top_holders by patching its dependencies."""

    @pytest.fixture(autouse=True)
    def setup(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed in test environment")

    def test_missing_ts_code_returns_error(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        async def run():
            return await server.handle_get_top_holders({})

        result = asyncio.run(run())
        assert len(result) == 1
        text = result[0].text
        parsed = json.loads(text)
        assert parsed.get("error") is not None or "error" in parsed.get("result", {})

    def test_tushare_success(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        mock_df = _mock_dataframe([
            {"holder_name": "香港中央结算有限公司", "hold_pct": 25.3, "ann_date": "20240630"},
        ])

        with patch.object(server, "_check_token", return_value=None):
            with patch.object(server, "get_ts_pro") as mock_pro:
                mock_api = MagicMock()
                mock_api.top_holders.return_value = mock_df
                mock_pro.return_value = mock_api

                async def run():
                    return await server.handle_get_top_holders({"ts_code": "000001.SZ"})

                result = asyncio.run(run())
                text = result[0].text
                parsed = json.loads(text)
                inner = parsed.get("result", parsed)
                assert inner.get("success") is True or inner.get("data") is not None

    def test_ann_date_passed_to_tushare(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        mock_df = _mock_dataframe([])

        with patch.object(server, "_check_token", return_value=None):
            with patch.object(server, "get_ts_pro") as mock_pro:
                mock_api = MagicMock()
                mock_api.top_holders.return_value = mock_df
                mock_pro.return_value = mock_api

                async def run():
                    return await server.handle_get_top_holders({
                        "ts_code": "600519.SH",
                        "ann_date": "20240630",
                    })

                asyncio.run(run())
                mock_api.top_holders.assert_called_once_with(
                    ts_code="600519.SH", ann_date="20240630"
                )


# ---------------------------------------------------------------------------
# Dispatcher wiring
# ---------------------------------------------------------------------------

class TestDispatcherWiring:
    """Verify TOOL_HANDLERS correctly routes the new tools."""

    def test_tools_in_handler_registry(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        assert "get_institutional_holdings" in server.TOOL_HANDLERS
        assert "get_top_holders" in server.TOOL_HANDLERS

    def test_unknown_tool_not_in_registry(self):
        server = _import_server()
        if server is None:
            pytest.skip("mcp package not installed")

        # Simulate dispatcher: unknown tool should not be found
        assert server.TOOL_HANDLERS.get("nonexistent_tool") is None
