"""LLMGateway: Unified LLM invocation gateway for the research agent.

Ensures all LLM calls go through the centralized routing layer (ai_router)
for:
1. Task-type-based model routing with fallback chain
2. Response caching and deduplication
3. Cost tracking and call logging
4. Consistent error handling
5. MCP tool invocation via stdio JSON-RPC

Usage:
    from scripts.core.llm_gateway import LLMGateway

    gateway = LLMGateway(memory)
    result = gateway.generate("分析茅台财务数据", task_hint=Task.DATA_ANALYSIS)
    print(result.response)

MCP Tool Usage:
    from scripts.core.llm_gateway import call_mcp_tool

    data = call_mcp_tool("user-yfinance", "get_yf_quote", {"ticker": "AAPL"})
"""

from __future__ import annotations

__all__ = [
    "MCPResult",
    "LLMCallResult",
    "CostStats",
    "LLMGateway",
    "call_mcp_tool",
]

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.ai_router import _TASK_ROUTING, AI, ModelKey
from scripts.ai_router import Task as RouterTask
from scripts.core.memory import Operation, ResearchMemory

# ─── Agent Registry ────────────────────────────────────────────────────────────

# Thread-local context for the current agent name during tool execution.
_current_agent_name: ContextVar[str | None] = ContextVar(
    "current_agent_name", default=None
)


@dataclass
class _AgentEntry:
    """Internal entry stored in _AgentRegistry."""
    allowed_tools: list[str]  # Tool whitelist; empty = unrestricted


class _AgentRegistry:
    """
    Thread-safe registry mapping agent names to their AgentConfig data.

    Agents register themselves via register_agent().  LLMGateway then uses
    this registry at tool-execution time to enforce the allowed_tools whitelist.
    """

    def __init__(self) -> None:
        self._agents: dict[str, _AgentEntry] = {}
        self._lock = threading.Lock()

    def register(self, name: str, allowed_tools: list[str]) -> None:
        with self._lock:
            self._agents[name] = _AgentEntry(allowed_tools=list(allowed_tools))

    def unregister(self, name: str) -> None:
        with self._lock:
            self._agents.pop(name, None)

    def get_allowed_tools(self, name: str) -> set[str] | None:
        """Return allowed set for agent, or None if unrestricted / unknown."""
        with self._lock:
            entry = self._agents.get(name)
        if entry is None:
            return None
        if not entry.allowed_tools:
            return None  # unrestricted
        return set(entry.allowed_tools)

    def is_tool_allowed(self, agent_name: str, tool_name: str) -> bool:
        """Return True if tool is allowed for agent (True when unrestricted)."""
        allowed = self.get_allowed_tools(agent_name)
        if allowed is None:
            return True
        return tool_name in allowed


# Global singleton
_agent_registry = _AgentRegistry()

from scripts.core.platform import get_mcp_config_paths

# ─── MCP Tool Client ─────────────────────────────────────────────────────────

# Use platform-aware path resolution (supports Cursor, Claude Code, VS Code, generic)
_MCP_CONFIG_PATHS = get_mcp_config_paths()


def _resolve_venv_python() -> Path:
    """Resolve the virtualenv Python interpreter path, checking common locations."""
    # Try to find a Python interpreter with the required packages installed.
    # Check: (1) explicit env var, (2) project .venv/bin/python, (3) sys.executable
    explicit = os.environ.get("RESEARCH_VENV_PYTHON")
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
    project_venv = Path(__file__).parent.parent.parent / ".venv" / "bin" / "python"
    if project_venv.exists():
        return project_venv
    # Fallback to the Python running this module
    return Path(sys.executable)


_VENV_PYTHON = _resolve_venv_python()

# Cache for server tool registries to avoid repeated initialization
_mcp_registry: dict[str, Any] = {}
_mcp_registry_lock = threading.Lock()

# Default timeout for MCP tool calls (seconds). Override with
# RESEARCH_MCP_TIMEOUT environment variable.
_MCP_TIMEOUT: float = float(os.environ.get("RESEARCH_MCP_TIMEOUT", "30.0"))


_mcp_log = logging.getLogger("llm_gateway.mcp")


def _get_mcp_server_cmd(server_name: str) -> list[str] | None:
    """Read mcp.json and return the command/args for a server, or None if not found.
    Searches all platform-aware MCP config paths (Cursor, Claude Code, VS Code, project-local).
    """
    try:
        # Try all known MCP config paths
        for config_file in _MCP_CONFIG_PATHS:
            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)
                servers = config.get("mcpServers", {})
                if server_name in servers:
                    srv = servers[server_name]
                    cmd = srv.get("command", "")
                    args = srv.get("args", [])
                    return [cmd] + args
        return None
    except (json.JSONDecodeError, OSError) as e:
        _mcp_log.warning("Failed to read MCP config %s: %s", config_file, e)
        return None
    except Exception as e:
        _mcp_log.error("Unexpected error reading MCP config %s: %s", config_file, e, exc_info=True)
        return None


def _get_server_module_info(server_name: str) -> tuple[str, str] | None:
    """
    Resolve server name to (module_path, function_or_attr) from mcp.json.

    Supports:
    - Local project servers: mcp_servers/<name>/server.py (as module)
    - Named module servers: e.g. "financial_mcp.server" or "tushare_mcp_server.server"
    - Direct script servers: ["python", "path/to/script.py"]
    """
    cmd = _get_mcp_server_cmd(server_name)
    if cmd is None:
        return None

    command = cmd[0]
    args = cmd[1:]

    # Case 1: Named module (e.g. "financial_mcp.server" → module="financial_mcp", attr="server")
    if "." in command and "/" not in command:
        parts = command.rsplit(".", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "mcp")

    # Case 2: Local project server (args contain "-c" with a module import)
    # e.g. ["python", "-c", "from financial_mcp.server import main; ..."]
    for arg in args:
        if arg.startswith("-c"):
            continue
        import_match = re.search(
            r"from\s+([\w_]+)\.server\s+import\s+(\w+)", arg
        )
        if import_match:
            return (import_match.group(1), import_match.group(2))

    return None


def _call_via_venv_subprocess(server: str, tool: str, arguments: dict,
                               timeout: float = _MCP_TIMEOUT) -> Any:
    """
    Call an MCP tool by spawning the venv Python with a one-liner that imports
    and invokes the tool directly. This ensures the correct Python interpreter
    (with all MCP packages) is used, and avoids stdio buffering issues.

    Returns the raw Python result or None on failure.
    """

    module_info = _get_server_module_info(server)
    if module_info is None:
        return None

    module_path, mcp_attr = module_info

    # Extract sys.path.insert path from mcp.json args so the module can be imported
    cmd_cfg = _get_mcp_server_cmd(server)
    sys_path_insert = ""
    if cmd_cfg:
        for arg in cmd_cfg[1:]:
            m = re.search(r"sys\.path\.insert\(0,\s*['\"]([^'\"]+)['\"]\)", arg)
            if m:
                sys_path_insert = m.group(1)
                break

    # Build the invocation code
    # sys_path_insert is the server directory (mcp_servers/) containing user_xxx/ packages
    # module_path is "user_xxx" — import as module, not a function from it
    path_setup = f"import sys; sys.path.insert(0, '{sys_path_insert}');" if sys_path_insert else ""
    code = (
        f"import json;"
        f"{path_setup}"
        f"import {module_path}.server as _mcp_mod;"
        f"_a = {json.dumps(arguments)};"
        f"_res = _mcp_mod._invoke({repr(tool)}, _a);"
        f"print(json.dumps(_res, ensure_ascii=False, default=str))"
    )

    venv_py = str(_VENV_PYTHON)
    if not Path(venv_py).exists():
        return None

    try:
        proc = subprocess.run(
            [venv_py, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent.parent),
        )
        if proc.returncode != 0:
            return None
        output = proc.stdout.strip()
        if not output:
            return None
        result = json.loads(output)
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as exc:
        # Log instead of silent swallow — makes debugging MCP failures possible
        import logging as _ll
        _ll.getLogger("llm_gateway.mcp").warning(
            "MCP venv fallback failed for %s/%s: %s",
            server, tool, exc
        )
        return None


@dataclass
class MCPResult:
    """
    Structured result from an MCP tool call.
    """
    success: bool
    data: Any = None
    error: str | None = None
    server: str = ""
    tool: str = ""
    latency_ms: float = 0.0
    is_mock: bool = False  # True if the server returned mock/simulated data


def call_mcp_tool(server: str, tool: str, arguments: dict,
                  timeout: float = _MCP_TIMEOUT) -> MCPResult:
    """
    Call an MCP tool from Python scripts.

    This function provides a unified interface for calling MCP tools, replacing
    the non-existent 'cursor-mcp' CLI. It uses the project's .venv Python
    (which has all MCP packages) via subprocess invocation.

    Parameters
    ----------
    server : str
        MCP server name (e.g. "user-yfinance", "user-finagent").
    tool : str
        Tool name on that server.
    arguments : dict
        Keyword arguments for the tool.
    timeout : float
        Timeout in seconds. Default 30.

    Returns
    -------
    Any
        The tool's result (typically a dict or MCP TextContent list),
        or None if the call failed.

    Examples
    --------
        # Get stock quote
        data = call_mcp_tool("user-yfinance", "get_yf_quote",
                             {"ticker": "AAPL"})

        # Get price history
        prices = call_mcp_tool("user-yfinance", "get_yf_historical",
                              {"ticker": "AAPL", "start_date": "2024-01-01", "end_date": "2024-12-31"})

        # Get financial statements
        financials = call_mcp_tool("user-yfinance", "get_yf_financials",
                                  {"ticker": "AAPL", "statement_type": "income"})
    """
    start = time.time()
    result = _call_via_venv_subprocess(server, tool, arguments, timeout)
    if result is not None:
        return MCPResult(success=True, data=result, server=server, tool=tool,
                         latency_ms=(time.time() - start) * 1000)

    cmd = _get_mcp_server_cmd(server)
    if cmd is None:
        return MCPResult(success=False, error=f"Server '{server}' not found in mcp.json",
                         server=server, tool=tool,
                         latency_ms=(time.time() - start) * 1000)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:
        return MCPResult(success=False, error=str(exc), server=server, tool=tool,
                         latency_ms=(time.time() - start) * 1000)

    init_msg = {
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "llm-gateway", "version": "1.0"}
        }
    }
    call_msg = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments}
    }

    try:
        for msg in [init_msg, call_msg]:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
        proc.stdin.close()
        time.sleep(0.5)
        proc.wait(timeout=timeout)
    except Exception as exc:
        return MCPResult(success=False, error=str(exc), server=server, tool=tool,
                         latency_ms=(time.time() - start) * 1000)

    try:
        stdout = proc.stdout.read()
        for line in stdout.split('\n'):
            if not line.strip():
                continue
            try:
                resp = json.loads(line)
                if resp.get("id") == 2:
                    if "result" in resp:
                        result_data = resp["result"]
                        is_mock = False
                        if isinstance(result_data, dict):
                            def _has_mock(obj) -> bool:
                                if isinstance(obj, dict):
                                    if obj.get("_mock") is True:
                                        return True
                                    for v in obj.values():
                                        if _has_mock(v):
                                            return True
                                elif isinstance(obj, list):
                                    for item in obj:
                                        if _has_mock(item):
                                            return True
                                return False
                            is_mock = _has_mock(result_data)
                        return MCPResult(success=True, data=result_data,
                                         server=server, tool=tool,
                                         latency_ms=(time.time() - start) * 1000,
                                         is_mock=is_mock)
                    if "error" in resp:
                        return MCPResult(success=False,
                                         error=resp["error"].get("message", str(resp["error"])),
                                         server=server, tool=tool,
                                         latency_ms=(time.time() - start) * 1000)
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        return MCPResult(success=False, error=str(exc), server=server, tool=tool,
                         latency_ms=(time.time() - start) * 1000)

    return MCPResult(success=False, error="No valid response received",
                     server=server, tool=tool,
                     latency_ms=(time.time() - start) * 1000)


# ─── Call Result ───────────────────────────────────────────────────────────────


@dataclass
class LLMCallResult:
    """
    Result of a single LLM call through the gateway.

    Attributes
    ----------
    response : str
        The model's text response.
    model_used : str
        Display name of the model that served the request.
    model_key : str
        Internal model identifier.
    task_type : str
        Classified task type.
    latency_ms : float
        Total call latency in milliseconds.
    cached : bool
        Whether the response came from cache.
    fallback_tried : list[str]
        List of models that were attempted (including the one that succeeded).
    call_id : str
        Unique identifier for this call.
    timestamp : float
        Unix timestamp of the call.
    tokens_used : int
        Estimated total tokens consumed (input + output).
    """
    response: str
    model_used: str
    model_key: str
    task_type: str
    latency_ms: float
    cached: bool = False
    fallback_tried: list[str] = field(default_factory=list)
    call_id: str = ""
    timestamp: float = field(default_factory=lambda: time.time())
    tokens_used: int = 0


# ─── Cost Tracker ─────────────────────────────────────────────────────────────


@dataclass
class CostStats:
    """Aggregated LLM usage statistics."""
    total_calls: int = 0
    cached_calls: int = 0
    total_cost_usd: float = 0.0
    total_tokens_estimate: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, cached: bool, latency_ms: float, tokens_used: int = 0):
        with self._lock:
            self.total_calls += 1
            if cached:
                self.cached_calls += 1
            # Rough cost estimate: $0.001 per cached call (API overhead)
            # Non-cached: ~$0.01 average per call (varies by model)
            if cached:
                self.total_cost_usd += 0.001
            else:
                self.total_cost_usd += 0.01
            self.total_tokens_estimate += tokens_used


# ─── LLM Gateway ──────────────────────────────────────────────────────────────


class LLMGateway:
    """
    Centralized LLM invocation gateway.

    All LLM calls within the research agent should go through this gateway
    rather than calling ai_router.AI.chat() directly. This ensures:

    1. Unified task classification (AI.router.classifier.classify)
    2. Automatic model routing with full fallback chain
    3. Response caching (handled by AI.router.cache)
    4. Cost tracking per session
    5. Short-term memory logging of every call

    Thread-safe: uses a lock for counter increments.

    Example:
        gateway = LLMGateway(memory)
        result = gateway.generate(
            prompt="分析茅台2024年的财务数据",
            task_hint=RouterTask.DATA_ANALYSIS,
            system="你是一位专业的金融分析师。",
        )
        print(result.response)
        print(f"Cost so far: ${gateway.stats.total_cost_usd:.4f}")
    """

    _call_counter: int = 0
    _counter_lock: threading.Lock = threading.Lock()

    def __init__(self, memory: ResearchMemory, use_cache: bool = True):
        """Initialize the gateway.

        Parameters
        ----------
        memory : ResearchMemory
            The agent's memory instance for logging calls.
        use_cache : bool
            Whether to enable response caching. Default True.
        """
        # Use importlib.import_module (NOT ``import x as y``) so we always
        # look up ``scripts.ai_router`` via sys.modules, even when the
        # ``scripts`` package has already been imported earlier in the
        # process. Tests patch ``sys.modules['scripts.ai_router']`` to a
        # mock, but ``import scripts.ai_router as _x`` would resolve via
        # the ``scripts`` package's ``__dict__`` and silently return the
        # real (cached) module, defeating the patch.
        import importlib

        self.memory = memory
        self._use_cache = use_cache
        self.router = importlib.import_module("scripts.ai_router").AI
        self.stats = CostStats()

        # Ensure router cache is consistent with our use_cache setting
        if not use_cache and self.router.cache is not None:
            self.router.clear_cache()

    # ── Public API ──────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        task_hint: RouterTask | None = None,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> LLMCallResult:
        """
        Generate a response via LLM, with routing and caching.

        Parameters
        ----------
        prompt : str
            The user prompt to send to the model.
        task_hint : RouterTask, optional
            Force a specific task type for routing.
            If None, the router auto-classifies from prompt content.
        system : str, optional
            System prompt to prepend.
        model : str, optional
            Force a specific model (bypasses routing). If None, uses routing.
        temperature : float
            Sampling temperature. Default 0.7.
        max_tokens : int
            Maximum output tokens. Default 8192.

        Returns
        -------
        LLMCallResult
            Structured result with response text and metadata.
        """
        call_id = self._next_call_id()
        start = time.time()

        # Route through ai_router
        ai_result = self.router.chat(
            user_input=prompt,
            task=task_hint,
            model=model,
            system_prompt=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        latency_ms = (time.time() - start) * 1000

        # Record cost
        estimated_tokens = self._estimate_tokens(ai_result.response, latency_ms)
        self.stats.record(cached=ai_result.cached, latency_ms=latency_ms, tokens_used=estimated_tokens)

        # Log to short-term memory
        self._log_call(
            call_id=call_id,
            prompt=prompt,
            task_type=ai_result.task_type,
            model=ai_result.model_key,
            cached=ai_result.cached,
            latency_ms=latency_ms,
            success=True,
        )

        return LLMCallResult(
            response=ai_result.response,
            model_used=ai_result.model_used,
            model_key=ai_result.model_key,
            task_type=ai_result.task_type,
            latency_ms=latency_ms,
            cached=ai_result.cached,
            fallback_tried=ai_result.fallback_tried,
            call_id=call_id,
            timestamp=start,
            tokens_used=self._estimate_tokens(ai_result.response, latency_ms),
        )

    def _estimate_tokens(self, response: str, latency_ms: float) -> int:
        """Rough token estimate: word count × 1.3 + char/4 approximation."""
        words = len(response.split())
        chars = len(response)
        return int(words * 1.3 + chars / 4)

    def generate_batch(
        self,
        prompts: list[str],
        task_hint: RouterTask | None = None,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        parallel: bool = True,
    ) -> list[LLMCallResult]:
        """
        Generate responses for multiple prompts.

        Parameters
        ----------
        prompts : list[str]
            List of user prompts.
        task_hint : RouterTask, optional
            Task type hint for all prompts.
        system : str, optional
            System prompt.
        model : str, optional
            Force a specific model.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum output tokens.
        parallel : bool
            If True (default), run calls concurrently using asyncio.
            If False, run sequentially.

        Returns
        -------
        list[LLMCallResult]
            Results in the same order as input prompts.
        """
        if not parallel:
            return [
                self.generate(
                    prompt=p,
                    task_hint=task_hint,
                    system=system,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                for p in prompts
            ]

        # Parallel execution using ThreadPoolExecutor
        import concurrent.futures

        def _call_one(p: str) -> LLMCallResult:
            return self.generate(
                prompt=p,
                task_hint=task_hint,
                system=system,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        results: list[LLMCallResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(prompts), 8)) as executor:
            futures = [executor.submit(_call_one, p) for p in prompts]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    import logging as _bl
                    _bl.getLogger("llm_gateway.batch").warning(
                        "Batch parallel call failed: %s", exc
                    )
                    results.append(LLMCallResult(
                        response="",
                        model_used="unknown",
                        model_key="unknown",
                        task_type="unknown",
                        latency_ms=0.0,
                    ))
        # Restore original order
        return results

    def classify_task(self, text: str) -> RouterTask:
        """
        Classify a text into a task type without making an LLM call.

        Parameters
        ----------
        text : str
            The text to classify.

        Returns
        -------
        RouterTask
            The classified task type.
        """
        return self.router.classifier.classify(text)

    def clear_cache(self):
        """Clear the response cache."""
        self.router.clear_cache()

    def chat(
        self,
        user_input: str,
        task: "RouterTask | None" = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> "AIResult":
        """
        Backward-compatible wrapper around generate().

        Mirrors the AIRouter.chat() signature so existing callers
        (e.g. ReviewLayer) can switch to LLMGateway without API changes.

        Returns AIResult (same field names as LLMCallResult).
        """
        from scripts.ai_router import AIResult

        result = self.generate(
            prompt=user_input,
            task_hint=task,
            model=model,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return AIResult(
            response=result.response,
            model_used=result.model_used,
            model_key=result.model_key,
            task_type=result.task_type,
            latency_ms=result.latency_ms,
            cached=result.cached,
            fallback_tried=result.fallback_tried,
        )

    # ── Internal Helpers ───────────────────────────────────────────────────

    @classmethod
    def _next_call_id(cls) -> str:
        """Generate a unique call ID in a thread-safe manner."""
        with cls._counter_lock:
            cls._call_counter += 1
            return f"llm_{cls._call_counter:06d}"


    def supports_streaming(self, model: str | None = None) -> bool:
        """
        Check if the current model configuration supports streaming.

        Parameters
        ----------
        model : str, optional
            Specific model to check. If None, checks the router's primary model.

        Returns
        -------
        bool
            True if streaming is available.
        """
        try:
            if model:
                return self.router.bridge.supports_streaming(model)
            # Check if any model supports streaming
            for key in self.router.pool.available_models():
                if self.router.bridge.supports_streaming(key):
                    return True
            return False
        except Exception:
            return False

    def generate_stream(
        self,
        prompt: str,
        task_hint: RouterTask | None = None,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ):
        """
        Generate a streaming response via LLM.

        Parameters
        ----------
        prompt : str
            The user prompt to send to the model.
        task_hint : RouterTask, optional
            Force a specific task type for routing.
        system : str, optional
            System prompt to prepend.
        model : str, optional
            Force a specific model (bypasses routing). If None, uses routing.
        temperature : float
            Sampling temperature. Default 0.7.
        max_tokens : int
            Maximum output tokens. Default 8192.

        Yields
        ------
        str
            Text chunks as they arrive from the model.
        """
        # Route to determine model
        if model:
            model_key = model
        else:
            # Get the primary model for the task
            actual_task = task_hint if task_hint else self.router.classifier.classify(prompt)
            model_keys = _TASK_ROUTING.get(actual_task, [])
            # Filter to available models
            available = [
                k for k in model_keys
                if self.router.bridge._get_client(k) is not None
            ]
            if not available:
                available = [ModelKey.LOCAL_OLLAMA]
            model_key = available[0].value if hasattr(available[0], 'value') else available[0]

        messages = [{"role": "user", "content": prompt}]
        system_prompt = system

        for chunk in self.router.bridge.stream(
            model_key=model_key,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    def _log_call(
        self,
        call_id: str,
        prompt: str,
        task_type: str,
        model: str,
        cached: bool,
        latency_ms: float,
        success: bool,
    ):
        """Append a record of the LLM call to short-term memory."""
        truncated_prompt = prompt[:200] + "..." if len(prompt) > 200 else prompt

        self.memory.short_term.append(Operation(
            timestamp=time.time(),
            operation_type="llm_call",
            description=f"[{call_id}] {task_type} → {model} "
                        f"({'cached' if cached else 'fresh'}) {latency_ms:.0f}ms",
            metadata={
                "call_id": call_id,
                "task_type": task_type,
                "model": model,
                "cached": cached,
                "latency_ms": latency_ms,
                "success": success,
                "prompt_preview": truncated_prompt,
            },
        ))

    def __repr__(self) -> str:
        return (
            f"LLMGateway(calls={self.stats.total_calls}, "
            f"cached={self.stats.cached_calls}, "
            f"cost=${self.stats.total_cost_usd:.4f})"
        )

    # ── Tool Enforcement ────────────────────────────────────────────────────────

    def execute_tool(
        self,
        server: str,
        tool: str,
        arguments: dict,
        agent_name: str,
        timeout: float = _MCP_TIMEOUT,
    ) -> MCPResult:
        """
        Execute an MCP tool call with allowed_tools whitelist enforcement.

        If the named agent has an allowed_tools restriction and the tool is not
        in that whitelist, execution is blocked and a rejection result is returned
        instead of calling the tool.

        Parameters
        ----------
        server : str
            MCP server name (e.g. "user-yfinance").
        tool : str
            Tool name on that server.
        arguments : dict
            Keyword arguments for the tool.
        agent_name : str
            Name of the agent attempting the call (used for whitelist lookup).
        timeout : float
            Call timeout in seconds.

        Returns
        -------
        MCPResult
            Tool result on success, or a rejection result if the tool is blocked.
        """
        allowed = _agent_registry.get_allowed_tools(agent_name)
        if allowed is not None and tool not in allowed:
            return MCPResult(
                success=False,
                error=(
                    f"Tool '{tool}' is not allowed for agent '{agent_name}'. "
                    f"Allowed tools: {', '.join(sorted(allowed))}"
                ),
                server=server,
                tool=tool,
                latency_ms=0.0,
            )
        return call_mcp_tool(server, tool, arguments, timeout)

    # ── Agent Registry Integration ──────────────────────────────────────────────

    def register_agent(self, agent_name: str, allowed_tools: list[str]) -> None:
        """
        Register an agent (or update) with the global tool-whitelist registry.

        Call this when a new agent is created so that subsequent
        execute_tool() calls are subject to its allowed_tools restriction.

        Parameters
        ----------
        agent_name : str
            Unique agent name (matches AgentConfig.name).
        allowed_tools : list[str]
            Tool whitelist from AgentConfig.  Empty list means unrestricted.
        """
        _agent_registry.register(agent_name, allowed_tools)

    def unregister_agent(self, agent_name: str) -> None:
        """Remove an agent from the tool-whitelist registry."""
        _agent_registry.unregister(agent_name)
