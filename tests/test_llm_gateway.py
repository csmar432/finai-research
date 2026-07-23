"""Tests for scripts/core/llm_gateway.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import time
from unittest.mock import MagicMock, patch

import pytest

# ─── Mock ai_router so we can import llm_gateway ───────────────────────────────


class FakeAIResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture(autouse=True)
def mock_ai_router():
    """Mock the ai_router module so LLMGateway can be instantiated."""
    router_mock = MagicMock()
    router_mock.chat.return_value = FakeAIResult(
        response="Test response text",
        model_used="test-model",
        model_key="test-key",
        task_type="general",
        cached=False,
        fallback_tried=["test-key"],
    )
    router_mock.clear_cache = MagicMock()
    router_mock.classifier = MagicMock()
    router_mock.classifier.classify = MagicMock(return_value=MagicMock())
    router_mock.bridge = MagicMock()
    router_mock.bridge._get_client = MagicMock(return_value=None)
    router_mock.bridge.supports_streaming = MagicMock(return_value=False)

    # Build a dedicated mock module so any lazy `import scripts.ai_router`
    # inside llm_gateway.__init__ resolves to *our* router_mock consistently,
    # regardless of which Python / patch.dict / coverage version is running.
    ai_router_mock = MagicMock()
    ai_router_mock.AI = router_mock
    ai_router_mock.AIRouter = MagicMock(return_value=router_mock)
    ai_router_mock.Task = MagicMock()
    ai_router_mock._TASK_ROUTING = {}

    with patch.dict("sys.modules", {"scripts.ai_router": ai_router_mock}):
        with patch("scripts.ai_router.AI", router_mock):
            with patch("scripts.ai_router.AIRouter", return_value=router_mock):
                with patch("scripts.ai_router.Task", MagicMock()):
                    with patch("scripts.ai_router._TASK_ROUTING", {}):
                        yield router_mock


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestMCPResultDataclass:
    """Test 1: MCPResult dataclass — all fields accessible."""

    def test_mcp_result_success_default(self):
        from scripts.core.llm_gateway import MCPResult

        result = MCPResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None
        assert result.server == ""
        assert result.tool == ""
        assert result.latency_ms == 0.0
        assert result.is_mock is False

    def test_mcp_result_full_fields(self):
        from scripts.core.llm_gateway import MCPResult

        result = MCPResult(
            success=True,
            data={"foo": "bar"},
            error=None,
            server="user-yfinance",
            tool="get_stock_info",
            latency_ms=123.4,
            is_mock=True,
        )
        assert result.success is True
        assert result.data == {"foo": "bar"}
        assert result.server == "user-yfinance"
        assert result.tool == "get_stock_info"
        assert result.latency_ms == 123.4
        assert result.is_mock is True

    def test_mcp_result_failure(self):
        from scripts.core.llm_gateway import MCPResult

        result = MCPResult(success=False, error="Server not found")
        assert result.success is False
        assert result.error == "Server not found"
        assert result.is_mock is False


class TestCallMCPTool:
    """Test 2: call_mcp_tool function."""

    @patch("scripts.core.llm_gateway._call_via_venv_subprocess")
    @patch("scripts.core.llm_gateway._get_mcp_server_cmd")
    def test_call_mcp_tool_via_venv_subprocess(self, mock_get_cmd, mock_subprocess):
        """When venv subprocess succeeds, return MCPResult with is_mock=False."""
        mock_subprocess.return_value = {"price": 150.0}
        mock_get_cmd.return_value = None  # Fall back to stdio path won't be taken

        from scripts.core.llm_gateway import call_mcp_tool

        result = call_mcp_tool("user-yfinance", "get_yf_quote", {"ticker": "AAPL"})
        assert result.success is True
        assert result.data == {"price": 150.0}
        assert result.server == "user-yfinance"
        assert result.tool == "get_yf_quote"
        assert result.is_mock is False
        mock_subprocess.assert_called_once()

    @patch("scripts.core.llm_gateway._call_via_venv_subprocess")
    def test_call_mcp_tool_via_venv_with_mock_flag(self, mock_subprocess):
        """Venv subprocess path returns success with the result dict.

        Note: is_mock is not set by the venv path; it is only checked
        in the stdio subprocess path.
        """
        mock_subprocess.return_value = {"price": 150.0, "_mock": True}

        from scripts.core.llm_gateway import call_mcp_tool

        result = call_mcp_tool("user-yfinance", "get_yf_quote", {"ticker": "AAPL"})
        assert result.success is True
        assert result.data == {"price": 150.0, "_mock": True}

    @patch("scripts.core.llm_gateway._call_via_venv_subprocess")
    def test_call_mcp_tool_via_venv_nested_mock_flag(self, mock_subprocess):
        """Venv subprocess path accepts any dict return, including nested _mock."""
        mock_subprocess.return_value = {
            "nested": {"_mock": True, "price": 150.0}
        }

        from scripts.core.llm_gateway import call_mcp_tool

        result = call_mcp_tool("user-yfinance", "get_yf_quote", {"ticker": "AAPL"})
        assert result.success is True
        assert result.data == {"nested": {"_mock": True, "price": 150.0}}

    @patch("scripts.core.llm_gateway._call_via_venv_subprocess")
    def test_call_mcp_tool_server_not_found(self, mock_subprocess):
        """When server not found in mcp.json, return error result."""
        mock_subprocess.return_value = None  # venv subprocess returns None
        mock_get_cmd = MagicMock(return_value=None)

        from scripts.core import llm_gateway

        with patch.object(llm_gateway, "_get_mcp_server_cmd", mock_get_cmd):
            result = llm_gateway.call_mcp_tool("unknown-server", "some_tool", {})
        assert result.success is False
        assert "not found" in result.error

    @patch("scripts.core.llm_gateway._call_via_venv_subprocess")
    def test_call_mcp_tool_returns_latency(self, mock_subprocess):
        """Latency field is populated."""
        mock_subprocess.return_value = {"result": "ok"}

        from scripts.core.llm_gateway import call_mcp_tool

        start = time.time()
        result = call_mcp_tool("user-yfinance", "get_yf_quote", {})
        elapsed = (time.time() - start) * 1000
        assert result.latency_ms >= 0
        assert result.latency_ms <= elapsed + 100  # Allow some tolerance


class TestLLMGatewayInit:
    """Test 3: LLMGateway.__init__."""

    def test_init_with_mock_memory(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory, use_cache=True)
            assert gateway.memory is mock_memory
            assert gateway._use_cache is True
            assert gateway.stats is not None

    def test_init_without_cache(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory, use_cache=False)
            assert gateway._use_cache is False


class TestLLMGatewayGenerate:
    """Test 4: generate method."""

    def test_generate_returns_llm_call_result(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            # Patch the gateway's router attribute to use the mock
            gateway.router = mock_ai_router

            result = gateway.generate("分析茅台财务数据")

        assert result.response == "Test response text"
        assert result.model_used == "test-model"
        mock_memory.short_term.append.assert_called_once()

    def test_generate_records_cost_stats(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            gateway.router = mock_ai_router

            assert gateway.stats.total_calls == 0
            gateway.generate("分析财务数据")
            assert gateway.stats.total_calls == 1
            assert gateway.stats.total_cost_usd > 0

    def test_generate_with_system_prompt(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            gateway.router = mock_ai_router
            gateway.generate("分析", system="你是一个专业的金融分析师。")

        mock_ai_router.chat.assert_called_once()
        call_kwargs = mock_ai_router.chat.call_args.kwargs
        assert call_kwargs["system_prompt"] == "你是一个专业的金融分析师。"

    def test_generate_token_estimation(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            gateway.router = mock_ai_router
            result = gateway.generate("short prompt")

        assert result.tokens_used >= 0


class TestAgentRegistry:
    """Test agent registry integration."""

    def test_register_and_get_allowed_tools(self):
        from scripts.core.llm_gateway import _agent_registry

        _agent_registry.register("ar_test_a", ["tool_a", "tool_b"])
        allowed = _agent_registry.get_allowed_tools("ar_test_a")
        assert allowed == {"tool_a", "tool_b"}
        # Unregistered agent returns None (unrestricted)
        assert _agent_registry.get_allowed_tools("unknown") is None

    def test_is_tool_allowed_restricted(self):
        from scripts.core.llm_gateway import _agent_registry

        _agent_registry.register("ar_test_b", ["tool_a"])
        assert _agent_registry.is_tool_allowed("ar_test_b", "tool_a") is True
        assert _agent_registry.is_tool_allowed("ar_test_b", "tool_b") is False

    def test_is_tool_allowed_unrestricted(self):
        from scripts.core.llm_gateway import _agent_registry

        # Empty list = unrestricted
        _agent_registry.register("ar_test_c", [])
        assert _agent_registry.get_allowed_tools("ar_test_c") is None
        assert _agent_registry.is_tool_allowed("ar_test_c", "any_tool") is True

    def test_unregister(self):
        from scripts.core.llm_gateway import _agent_registry

        _agent_registry.register("ar_test_d", ["tool_x"])
        assert _agent_registry.get_allowed_tools("ar_test_d") == {"tool_x"}
        _agent_registry.unregister("ar_test_d")
        assert _agent_registry.get_allowed_tools("ar_test_d") is None


class TestLLMGatewayToolEnforcement:
    """Test execute_tool with allowed_tools whitelist."""

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_execute_tool_blocked_by_whitelist(self, mock_call, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            gateway.register_agent("analyst", ["allowed_tool"])
            result = gateway.execute_tool(
                server="test-server",
                tool="forbidden_tool",
                arguments={},
                agent_name="analyst",
            )

        assert result.success is False
        assert "not allowed" in result.error
        mock_call.assert_not_called()

    @patch("scripts.core.llm_gateway.call_mcp_tool")
    def test_execute_tool_allowed(self, mock_call, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway, MCPResult

        mock_call.return_value = MCPResult(success=True, data={"ok": True})
        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            gateway.register_agent("exec_test_agent", ["allowed_tool"])
            result = gateway.execute_tool(
                server="test-server",
                tool="allowed_tool",
                arguments={"key": "value"},
                agent_name="exec_test_agent",
            )

        assert result.success is True
        mock_call.assert_called_once()


class TestCostStats:
    """Test CostStats dataclass."""

    def test_cost_stats_record_cached(self):
        from scripts.core.llm_gateway import CostStats

        stats = CostStats()
        stats.record(cached=True, latency_ms=100.0)
        assert stats.total_calls == 1
        assert stats.cached_calls == 1
        assert stats.total_cost_usd == 0.001

    def test_cost_stats_record_not_cached(self):
        from scripts.core.llm_gateway import CostStats

        stats = CostStats()
        stats.record(cached=False, latency_ms=200.0)
        assert stats.total_calls == 1
        assert stats.cached_calls == 0
        assert stats.total_cost_usd == 0.01

    def test_cost_stats_thread_safety(self):
        from scripts.core.llm_gateway import CostStats
        import threading

        stats = CostStats()

        def increment():
            for _ in range(100):
                stats.record(cached=False, latency_ms=10.0)

        threads = [threading.Thread(target=increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert stats.total_calls == 1000
        # Use approximate comparison for floating-point
        assert abs(stats.total_cost_usd - 10.0) < 0.001


class TestLLMGatewayChat:
    """Test backward-compatible chat() wrapper."""

    def test_chat_returns_airesult(self, mock_ai_router):
        from scripts.core.llm_gateway import LLMGateway

        mock_memory = MagicMock()
        mock_memory.short_term = MagicMock()
        mock_memory.short_term.append = MagicMock()

        with patch("scripts.ai_router.AI", mock_ai_router):
            gateway = LLMGateway(mock_memory)
            result = gateway.chat(user_input="hello")

        assert hasattr(result, "response")
        assert hasattr(result, "model_used")
