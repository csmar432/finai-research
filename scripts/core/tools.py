"""LangChain-style @tool decorator for standardized tool definitions.

This module provides:
- @tool decorator for registering functions as tools
- Tool class with JSON schema generation
- ToolRegistry for global tool management
- MCP adapter for tool invocation
- Integration with existing ToolSelector

Example:
    ```python
    from scripts.core.tools import tool, ToolRegistry

    @tool(name="search_arxiv", description="Search ArXiv for papers")
    async def search_arxiv(
        query: str = Field(description="Search query"),
        max_results: int = Field(default=10, description="Max results"),
    ) -> list[dict]:
        ...

    registry = ToolRegistry()
    registry.register(search_arxiv)
    ```
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, get_type_hints

from pydantic import BaseModel, Field

try:
    pass
except ImportError:  # pragma: no cover
    pass  # type: ignore[assignment,no-redef]


# ─── Type Variables ───────────────────────────────────────────────────────────

F = TypeVar("F", bound=Callable[..., Any])


# ─── Tool Result ──────────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """Structured result from tool execution, compatible with ToolSelector's ToolResult."""

    success: bool
    data: Any | None = None
    error: str | None = None
    tool_name: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any, tool_name: str = "", **kwargs: Any) -> ToolResult:
        """Create a successful result."""
        return cls(success=True, data=data, tool_name=tool_name, **kwargs)

    @classmethod
    def fail(cls, error: str, tool_name: str = "", **kwargs: Any) -> ToolResult:
        """Create a failed result."""
        return cls(success=False, error=error, tool_name=tool_name, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tool_name": self.tool_name,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


# ─── Tool Class ───────────────────────────────────────────────────────────────


@dataclass
class Tool:
    """
    Standardized tool definition, similar to LangChain's Tool.

    Attributes
    ----------
    name : str
        Unique identifier for the tool.
    description : str
        Human-readable description of what the tool does.
    parameters : dict
        JSON schema for the tool's input parameters.
    fn : Callable
        The actual function to execute (sync or async).
    is_async : bool
        Whether the function is async.
    return_annotation : type | None
        The return type annotation.
    docstring : str
        Original docstring of the function.
    examples : list[dict] | None
        Example inputs/outputs for the tool.
    tags : list[str] | None
        Tags for categorization.
    metadata : dict[str, Any]
        Additional metadata for the tool.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    is_async: bool = False
    return_annotation: type | None = None
    docstring: str = ""
    examples: list[dict[str, Any]] | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Auto-detect async
        if not self.is_async:
            self.is_async = asyncio.iscoroutinefunction(self.fn)

    def run(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool synchronously.

        Parameters
        ----------
        **kwargs : dict
            Input parameters for the tool.

        Returns
        -------
        ToolResult
            Structured result with success/data/error.
        """
        start = time.time()
        try:
            if self.is_async:
                result = asyncio.run(self.fn(**kwargs))
            else:
                result = self.fn(**kwargs)
            return ToolResult.ok(result, tool_name=self.name, latency_ms=(time.time() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(str(exc), tool_name=self.name, latency_ms=(time.time() - start) * 1000)

    async def run_async(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool asynchronously.

        Parameters
        ----------
        **kwargs : dict
            Input parameters for the tool.

        Returns
        -------
        ToolResult
            Structured result with success/data/error.
        """
        start = time.time()
        try:
            if self.is_async:
                result = await self.fn(**kwargs)
            else:
                result = self.fn(**kwargs)
            return ToolResult.ok(result, tool_name=self.name, latency_ms=(time.time() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(str(exc), tool_name=self.name, latency_ms=(time.time() - start) * 1000)

    def to_mcp_format(self) -> dict[str, Any]:
        """
        Convert tool to MCP (Model Context Protocol) tool format.

        Returns
        -------
        dict
            MCP-compatible tool definition.
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
            "tags": self.tags or [],
            "examples": self.examples or [],
        }


# ─── JSON Schema Generation ───────────────────────────────────────────────────


def generate_json_schema(
    func: Callable[..., Any],
    args_schema: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """
    Generate JSON schema from function signature or Pydantic model.

    Parameters
    ----------
    func : Callable
        The function to generate schema from.
    args_schema : type[BaseModel] | None
        Optional Pydantic model for explicit schema.

    Returns
    -------
    dict
        JSON schema dictionary.
    """
    if args_schema is not None:
        return args_schema.model_json_schema()

    # Extract from function signature
    hints = get_type_hints(func)
    sig = inspect.signature(func)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        # Determine type
        type_annotation = hints.get(param_name, param.annotation if param.annotation != inspect.Parameter.empty else Any)

        # Convert Python type to JSON schema type
        json_type = _python_type_to_json_type(type_annotation)

        # Get description from docstring
        description = _get_param_description(func, param_name)

        prop: dict[str, Any] = {"type": json_type}
        if description:
            prop["description"] = description

        # Handle default values
        if param.default != inspect.Parameter.empty:
            prop["default"] = _serialize_default(param.default, type_annotation)
        else:
            required.append(param_name)

        properties[param_name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


def _python_type_to_json_type(py_type: type) -> str:
    """Convert Python type annotation to JSON schema type string."""
    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    # Handle Optional types
    origin = getattr(py_type, "__origin__", None)
    if origin is type(None):
        return "string"

    # Handle Optional[T] (Union with None)
    if origin is type(None) or (hasattr(py_type, "__args__") and type(None) in getattr(py_type, "__args__", ())):
        return "string"

    # Handle Union types
    if origin is not None:
        args = getattr(py_type, "__args__", ())
        if args:
            return _python_type_to_json_type(args[0])

    # Handle generic types (List[T], Dict[K, V])
    if hasattr(py_type, "__origin__"):
        origin = py_type.__origin__
        if origin is list:
            return "array"
        if origin is dict:
            return "object"
        # Try to get first type argument
        args = getattr(py_type, "__args__", ())
        if args:
            return _python_type_to_json_type(args[0])

    # Check direct type mapping
    for py_t, json_t in type_map.items():
        if py_t == py_type:
            return json_t

    # Handle Optional[str] specifically
    if py_type is str or py_type is None:
        return "string"

    return "string"  # Default to string for unknown types


def _get_param_description(func: Callable, param_name: str) -> str:
    """Extract parameter description from function docstring."""
    doc = inspect.getdoc(func) or ""
    lines = doc.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{param_name}:") or stripped.startswith(f"{param_name} :"):
            # Try to get description from next lines
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line:
                    return next_line.rstrip(".").strip()
            # Extract description after colon
            if ":" in stripped:
                return stripped.split(":", 1)[1].strip().rstrip(".").strip()
    return ""


def _serialize_default(default: Any, annotation: type) -> Any:
    """Serialize default value for JSON schema."""
    if default is None:
        return None
    if isinstance(default, (str, int, float, bool, list, dict)):
        return default
    return str(default)


# ─── Tool Decorator ───────────────────────────────────────────────────────────


def tool(
    name: str = "",
    description: str = "",
    args_schema: type[BaseModel] | None = None,
    return_direct: bool = False,
    examples: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
) -> Callable[[F], F]:
    """
    Decorator similar to LangChain's @tool for defining standardized tools.

    Parameters
    ----------
    name : str
        Tool name. Defaults to function name if empty.
    description : str
        Tool description. Defaults to function docstring if empty.
    args_schema : type[BaseModel] | None
        Optional Pydantic model for explicit parameter schema.
    return_direct : bool
        If True, return the raw function output instead of ToolResult.
    examples : list[dict] | None
        Example inputs/outputs.
    tags : list[str] | None
        Tags for categorization.

    Returns
    -------
    Callable
        Decorated function with tool metadata.

    Example
    -------
    ```python
    from pydantic import Field

    @tool(name="search_arxiv", description="Search ArXiv papers")
    async def search_arxiv(
        query: str = Field(description="Search query"),
        max_results: int = Field(default=10, ge=1, le=100),
    ) -> list[dict]:
        \"\"\"Search ArXiv for academic papers.

        Args:
            query: Search query string.
            max_results: Maximum number of results (1-100).
        \"\"\"
        ...
    ```
    """

    def decorator(func: F) -> F:
        # Determine tool name
        tool_name = name or func.__name__

        # Determine description
        tool_description = description or inspect.getdoc(func) or ""

        # Generate JSON schema
        parameters = generate_json_schema(func, args_schema)

        # Detect async
        is_async = asyncio.iscoroutinefunction(func)

        # Get return annotation
        hints = get_type_hints(func)
        return_annotation = hints.get("return")

        # Attach metadata to function
        func._tool_metadata = {  # type: ignore[attr-defined]
            "name": tool_name,
            "description": tool_description,
            "parameters": parameters,
            "is_async": is_async,
            "return_annotation": return_annotation,
            "return_direct": return_direct,
            "examples": examples or [],
            "tags": tags or [],
            "func": func,
        }

        # Create Tool instance and attach
        _tool = Tool(
            name=tool_name,
            description=tool_description,
            parameters=parameters,
            fn=func,
            is_async=is_async,
            return_annotation=return_annotation,
            docstring=inspect.getdoc(func) or "",
            examples=examples,
            tags=tags,
        )
        func._tool = _tool  # type: ignore[attr-defined]

        return func

    return decorator


# ─── Tool Registry ───────────────────────────────────────────────────────────


class ToolRegistry:
    """
    Global registry of all registered tools.

    Provides tool registration, lookup, and auto-discovery from decorated functions.

    Example
    -------
    ```python
    registry = ToolRegistry()

    # Register a tool
    registry.register(my_tool_function)

    # Get a tool
    t = registry.get_tool("search_arxiv")

    # List all tools
    names = registry.list_tools()

    # Check if tool exists
    if registry.has_tool("fetch"):
        ...
    ```
    """

    _instance: ToolRegistry | None = None

    def __init__(
        self,
        tools: dict[str, Tool] | None = None,
        auto_register_builtins: bool = True,
    ) -> None:
        self._tools: dict[str, Tool] = tools.copy() if tools else {}
        self._func_to_tool: dict[Callable, Tool] = {}

        # Singleton pattern: register global instance
        if ToolRegistry._instance is None:
            ToolRegistry._instance = self

        # Auto-register built-in tools
        if auto_register_builtins:
            self._register_builtin_tools()

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        """Get the global ToolRegistry instance, creating if necessary."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, func: Callable | Tool, name: str | None = None) -> None:
        """
        Register a tool from a decorated function or Tool instance.

        Parameters
        ----------
        func : Callable | Tool
            A @tool decorated function or a Tool instance.
        name : str | None
            Optional name override.
        """
        if isinstance(func, Tool):
            t = func
        elif hasattr(func, "_tool"):
            t = func._tool  # type: ignore[attr-defined]
        elif hasattr(func, "_tool_metadata"):
            # Create Tool from metadata
            meta = func._tool_metadata  # type: ignore[attr-defined]
            t = Tool(
                name=meta.get("name", func.__name__),
                description=meta.get("description", ""),
                parameters=meta.get("parameters", {}),
                fn=meta.get("func", func),
                is_async=meta.get("is_async", False),
                return_annotation=meta.get("return_annotation"),
                examples=meta.get("examples"),
                tags=meta.get("tags"),
            )
        else:
            # Raw function - create tool from signature
            t = Tool(
                name=name or func.__name__,
                description=inspect.getdoc(func) or "",
                parameters=generate_json_schema(func),
                fn=func,
                is_async=asyncio.iscoroutinefunction(func),
            )

        tool_name = name or t.name
        self._tools[tool_name] = t
        self._func_to_tool[t.fn] = t

    def register_tool(self, t: Tool) -> None:
        """Register a Tool instance directly."""
        self._tools[t.name] = t
        self._func_to_tool[t.fn] = t

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.

        Returns
        -------
        bool
            True if tool was removed, False if not found.
        """
        if name in self._tools:
            t = self._tools.pop(name)
            self._func_to_tool.pop(t.fn, None)
            return True
        return False

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists."""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_tools_by_tag(self, tag: str) -> list[Tool]:
        """Get all tools with a specific tag."""
        return [t for t in self._tools.values() if tag in (t.tags or [])]

    def get_tools_by_prefix(self, prefix: str) -> list[Tool]:
        """Get all tools whose names start with a prefix."""
        return [t for t in self._tools.values() if t.name.startswith(prefix)]

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute(self, name: str, **kwargs: Any) -> ToolResult:
        """
        Execute a tool by name.

        Parameters
        ----------
        name : str
            Tool name.
        **kwargs : dict
            Input parameters.

        Returns
        -------
        ToolResult
            Structured result.
        """
        t = self.get_tool(name)
        if t is None:
            return ToolResult.fail(f"Tool '{name}' not found", tool_name=name)

        return t.run(**kwargs)

    async def execute_async(self, name: str, **kwargs: Any) -> ToolResult:
        """
        Execute a tool asynchronously by name.

        Parameters
        ----------
        name : str
            Tool name.
        **kwargs : dict
            Input parameters.

        Returns
        -------
        ToolResult
            Structured result.
        """
        t = self.get_tool(name)
        if t is None:
            return ToolResult.fail(f"Tool '{name}' not found", tool_name=name)

        return await t.run_async(**kwargs)

    # ── MCP Format ─────────────────────────────────────────────────────────────

    def to_mcp_tools(self) -> list[dict[str, Any]]:
        """Convert all tools to MCP format."""
        return [t.to_mcp_format() for t in self._tools.values()]

    def get_mcp_tool(self, name: str) -> dict[str, Any] | None:
        """Get a single tool in MCP format."""
        t = self.get_tool(name)
        return t.to_mcp_format() if t else None

    # ── Built-in Tools ────────────────────────────────────────────────────────

    def _register_builtin_tools(self) -> None:
        """Register built-in example tools."""
        # Import built-in tools
        from scripts.core import tools

        for attr_name in dir(tools):
            attr = getattr(tools, attr_name)
            if hasattr(attr, "_tool"):
                self.register(attr)


# ─── MCP Adapter ──────────────────────────────────────────────────────────────


class MCPAdapter:
    """
    Adapter for converting @tool decorated functions to MCP tool format.

    Integrates with ToolSelector for MCP tool invocation.

    Example
    -------
    ```python
    adapter = MCPAdapter(registry)

    # Convert registry to MCP tools
    mcp_tools = adapter.to_mcp_tools()

    # Invoke a tool via MCP protocol
    result = await adapter.invoke("search_arxiv", {"query": "machine learning"})
    ```
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry.get_instance()

    def to_mcp_tools(self) -> list[dict[str, Any]]:
        """Convert all registered tools to MCP tool definitions."""
        return self.registry.to_mcp_tools()

    def get_tool_definition(self, name: str) -> dict[str, Any] | None:
        """Get MCP tool definition for a specific tool."""
        return self.registry.get_mcp_tool(name)

    async def invoke(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Invoke a tool using MCP protocol.

        Parameters
        ----------
        tool_name : str
            Name of the tool to invoke.
        arguments : dict
            Tool arguments.

        Returns
        -------
        ToolResult
            Tool execution result.
        """
        return await self.registry.execute_async(tool_name, **arguments)

    def invoke_sync(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Invoke a tool synchronously using MCP protocol.

        Parameters
        ----------
        tool_name : str
            Name of the tool to invoke.
        arguments : dict
            Tool arguments.

        Returns
        -------
        ToolResult
            Tool execution result.
        """
        return self.registry.execute(tool_name, **arguments)


# ─── ToolSelector Integration ────────────────────────────────────────────────


class ToolSelectorBridge:
    """
    Bridge between @tool decorators and existing ToolSelector.

    Provides `register_tools_from_decorator()` method for seamless integration.
    """

    def __init__(self, tool_selector: Any) -> None:
        self.selector = tool_selector
        self.registry = ToolRegistry.get_instance()

    def register_tools_from_decorator(self) -> None:
        """
        Register all @tool decorated functions with the ToolSelector.

        This adds tool capabilities from the decorator metadata to the existing
        ToolSelector registry, maintaining backward compatibility.
        """
        from scripts.core.tool_selector import CostTier, ToolCapability

        for tool_name, t in self.registry._tools.items():
            if hasattr(t.fn, "_tool_metadata"):
                meta = t.fn._tool_metadata

                # Map tags to task types (simplified mapping)
                task_types = self._tags_to_task_types(meta.get("tags", []))
                inputs = self._extract_inputs(meta.get("parameters", {}))
                outputs = ["result"]  # Default output

                cap = ToolCapability(
                    name=tool_name,
                    task_types=task_types,
                    inputs=inputs,
                    outputs=outputs,
                    priority=1,  # Default priority
                    cost=CostTier.FREE,  # Default cost
                    requires_vpn=False,
                    description=meta.get("description", ""),
                    callable=t.fn,
                )

                # Add to ToolSelector registry
                self.selector.TOOL_REGISTRY[tool_name] = cap
                self.selector.TOOL_REGISTRY_BASE[tool_name] = cap

    def _tags_to_task_types(self, tags: list[str]) -> list[Any]:
        """Map tool tags to TaskType enum values."""
        try:
            from scripts.core.planner import TaskType
        except ImportError:
            return []

        tag_mapping: dict[str, list[TaskType]] = {
            "search": [TaskType.LITERATURE],
            "data": [TaskType.DATA_FETCH],
            "analysis": [TaskType.ANALYSIS],
            "writing": [TaskType.WRITING],
            "code": [TaskType.CODE],
        }

        result: list[TaskType] = []
        for tag in tags:
            if tag in tag_mapping:
                result.extend(tag_mapping[tag])

        return result if result else [TaskType.DATA_FETCH]  # Default

    def _extract_inputs(self, parameters: dict[str, Any]) -> list[str]:
        """Extract required input names from JSON schema."""
        return parameters.get("required", list(parameters.get("properties", {}).keys()))


# ─── Built-in Tool Examples ───────────────────────────────────────────────────


@tool(
    name="arxiv_search",
    description="Search ArXiv for academic papers. Returns paper metadata including title, authors, abstract, and PDF URL.",
    tags=["search", "literature", "academic"],
    examples=[
        {"query": "transformer attention mechanism", "max_results": 5},
        {"query": "reinforcement learning trading", "max_results": 10},
    ],
)
async def arxiv_search(
    query: str = Field(description="Search query for ArXiv papers"),
    max_results: int = Field(default=10, ge=1, le=100, description="Maximum number of results"),
    category: str | None = Field(default=None, description="ArXiv category filter (e.g., cs.LG, q-fin.ST)"),
) -> list[dict[str, Any]]:
    """
    Search ArXiv for academic papers.

    Args:
        query: Search query string for finding relevant papers.
        max_results: Maximum number of results to return (1-100).
        category: Optional ArXiv category to filter results.

    Returns:
        List of paper metadata dictionaries with title, authors, abstract, and URL.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-arxiv
        Tool: semantic_search
    """
    # MCP adapter would call the actual ArXiv tool here
    # This is a placeholder signature for the decorator
    raise NotImplementedError(
        "arxiv_search must be called via MCP adapter. "
        "Use call_mcp_tool('user-arxiv', 'semantic_search', ...) instead."
    )


@tool(
    name="brave_search",
    description="Search the web using Brave Search. Useful for finding news, policies, and general information.",
    tags=["search", "web", "news"],
    examples=[
        {"query": "China GDP 2025 forecast", "count": 10},
        {"query": "Federal Reserve interest rate decision", "count": 5},
    ],
)
async def brave_search(
    query: str = Field(description="Web search query"),
    count: int = Field(default=10, ge=1, le=50, description="Number of results to return"),
    focus: str | None = Field(default=None, description="Focus area: news, videos, images, or documents"),
) -> list[dict[str, Any]]:
    """
    Search the web using Brave Search API.

    Args:
        query: The search query string.
        count: Number of results to return.
        focus: Optional focus filter (news, videos, etc.).

    Returns:
        List of search results with title, url, and description.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-brave-search
        Tool: brave_web_search
    """
    raise NotImplementedError(
        "brave_search must be called via MCP adapter. "
        "Use call_mcp_tool('user-brave-search', 'brave_web_search', ...) instead."
    )


@tool(
    name="fetch_webpage",
    description="Fetch and extract content from a URL. Returns the main text content of the webpage.",
    tags=["fetch", "web", "content"],
    examples=[
        {"url": "https://arxiv.org/abs/2103.14030"},
        {"url": "https://www.example.com/article"},
    ],
)
async def fetch_webpage(
    url: str = Field(description="URL to fetch content from"),
    selector: str | None = Field(default=None, description="CSS selector to extract specific elements"),
    max_length: int = Field(default=10000, ge=100, le=100000, description="Maximum content length"),
) -> dict[str, Any]:
    """
    Fetch webpage content.

    Args:
        url: The URL to fetch.
        selector: Optional CSS selector for specific content extraction.
        max_length: Maximum length of extracted text.

    Returns:
        Dictionary with url, title, content, and metadata.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-playwright-mcp
        Tool: (browser automation)
    """
    raise NotImplementedError(
        "fetch_webpage must be called via MCP adapter. "
        "Use call_mcp_tool('user-playwright-mcp', '...', ...) instead."
    )


@tool(
    name="get_stock_price",
    description="Get real-time or historical stock price data. Supports A-shares, Hong Kong stocks, and US stocks.",
    tags=["data", "stock", "finance"],
    examples=[
        {"symbol": "AAPL", "period": "1d", "interval": "5m"},
        {"symbol": "000001.SZ", "period": "1mo", "interval": "1d"},
    ],
)
async def get_stock_price(
    symbol: str = Field(description="Stock symbol (e.g., AAPL, 000001.SZ, 0700.HK)"),
    period: str = Field(default="1mo", description="Time period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y, max"),
    interval: str = Field(default="1d", description="Data interval: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo"),
    start_date: str | None = Field(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Field(default=None, description="End date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """
    Get stock price data.

    Args:
        symbol: Stock ticker symbol.
        period: Time period for historical data.
        interval: Data granularity.
        start_date: Custom start date (overrides period).
        end_date: Custom end date (overrides period).

    Returns:
        Dictionary with price data, volume, and metadata.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-yfinance
        Tool: get_yf_historical
    """
    raise NotImplementedError(
        "get_stock_price must be called via MCP adapter. "
        "Use call_mcp_tool('user-yfinance', 'get_yf_historical', ...) instead."
    )


@tool(
    name="get_macro_indicator",
    description="Get macroeconomic indicators such as GDP, CPI, interest rates, and trade data.",
    tags=["data", "macro", "economics"],
    examples=[
        {"country": "US", "indicator": "gdp", "period": "quarterly"},
        {"country": "CN", "indicator": "cpi", "period": "monthly"},
    ],
)
async def get_macro_indicator(
    country: str = Field(description="Country code (US, CN, JP, DE, UK, etc.)"),
    indicator: str = Field(description="Indicator name: gdp, cpi, ppi, unemployment, interest_rate, etc."),
    period: str = Field(default="quarterly", description="Data frequency: monthly, quarterly, annual"),
    start_date: str | None = Field(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Field(default=None, description="End date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """
    Get macroeconomic indicator data.

    Args:
        country: ISO country code.
        indicator: Economic indicator name.
        period: Data frequency.
        start_date: Optional start date.
        end_date: Optional end date.

    Returns:
        Dictionary with indicator values and metadata.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-financial / user-wb-data / user-imf-data
        Tool: get_macro_china / get_wb_indicator / get_imf_ifs
    """
    raise NotImplementedError(
        "get_macro_indicator must be called via MCP adapter. "
        "Use call_mcp_tool('user-financial', 'get_macro_china', ...) instead."
    )


@tool(
    name="run_regression",
    description="Run statistical regression analysis (OLS, DID, Panel) on provided data.",
    tags=["analysis", "statistics", "econometrics"],
    examples=[
        {"formula": "Y ~ X1 + X2", "data_type": "cross_section"},
        {"formula": "Y ~ treated + post + treated:post", "data_type": "panel", "cluster": "firm_id"},
    ],
)
async def run_regression(
    formula: str = Field(description="Regression formula (e.g., 'Y ~ X1 + X2')"),
    data: list[dict] | None = Field(default=None, description="Data as list of dictionaries"),
    data_path: str | None = Field(default=None, description="Path to CSV file"),
    method: str = Field(default="ols", description="Regression method: ols, did, panel, glm"),
    cluster: str | None = Field(default=None, description="Cluster variable for robust SE"),
    fixed_effects: list[str] | None = Field(default=None, description="Fixed effects variables"),
) -> dict[str, Any]:
    """
    Run statistical regression.

    Args:
        formula: Regression formula string.
        data: Input data as list of dicts.
        data_path: Path to CSV data file.
        method: Regression method (ols, did, panel, glm).
        cluster: Variable name for clustered standard errors.
        fixed_effects: List of fixed effects variables.

    Returns:
        Dictionary with regression results, coefficients, and statistics.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-e2b-mcp
        Tool: (code execution for statistical analysis)
    """
    raise NotImplementedError(
        "run_regression must be called via MCP adapter. "
        "Use call_mcp_tool('user-e2b-mcp', '...', ...) instead."
    )


@tool(
    name="generate_report",
    description="Generate financial research report with charts and analysis.",
    tags=["writing", "report", "finance"],
    examples=[
        {"company": "Apple Inc", "report_type": "equity_research"},
        {"industry": "Semiconductors", "report_type": "industry_analysis"},
    ],
)
async def generate_report(
    company: str | None = Field(default=None, description="Company name or ticker"),
    industry: str | None = Field(default=None, description="Industry name"),
    report_type: str = Field(default="equity_research", description="Report type: equity_research, industry_analysis, macro_outlook"),
    format: str = Field(default="markdown", description="Output format: markdown, docx, latex, pdf"),
    include_charts: bool = Field(default=True, description="Include data visualizations"),
    data: dict | None = Field(default=None, description="Preprocessed data dictionary"),
) -> dict[str, Any]:
    """
    Generate financial research report.

    Args:
        company: Company name or ticker.
        industry: Industry name for industry reports.
        report_type: Type of report to generate.
        format: Output format.
        include_charts: Whether to include charts.
        data: Optional preprocessed data.

    Returns:
        Dictionary with report content and file path.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-latex-mcp
        Tool: latex_compile / latex_to_pdf
    """
    raise NotImplementedError(
        "generate_report must be called via MCP adapter. "
        "Use call_mcp_tool('user-latex-mcp', 'latex_compile', ...) instead."
    )


@tool(
    name="get_research_report",
    description="Get institutional research reports from East Money (东方财富). Covers A-shares, industries, and macro.",
    tags=["data", "research", "finance"],
    examples=[
        {"ts_code": "000001.SZ", "max_results": 10},
        {"industry": "银行", "max_results": 20},
    ],
)
async def get_research_report(
    ts_code: str | None = Field(default=None, description="A-share ticker (e.g., 000001.SZ)"),
    industry: str | None = Field(default=None, description="Industry name"),
    max_results: int = Field(default=20, ge=1, le=100, description="Maximum reports to return"),
    start_date: str | None = Field(default=None, description="Start date (YYYYMMDD)"),
    end_date: str | None = Field(default=None, description="End date (YYYYMMDD)"),
) -> list[dict[str, Any]]:
    """
    Get research reports from East Money.

    Args:
        ts_code: Stock ticker code.
        industry: Industry name.
        max_results: Maximum number of reports.
        start_date: Filter by start date.
        end_date: Filter by end date.

    Returns:
        List of research report metadata and summaries.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-eastmoney-reports
        Tool: get_research_report
    """
    raise NotImplementedError(
        "get_research_report must be called via MCP adapter. "
        "Use call_mcp_tool('user-eastmoney-reports', 'get_research_report', ...) instead."
    )


@tool(
    name="analyze_sentiment",
    description="Analyze sentiment from text data using NLP models. Supports financial news, social media, and documents.",
    tags=["analysis", "nlp", "sentiment"],
    examples=[
        {"text": "Stock price surged on strong earnings", "source": "news"},
        {"texts": ["Positive outlook", "Negative trend"], "source": "social_media"},
    ],
)
async def analyze_sentiment(
    text: str | None = Field(default=None, description="Single text to analyze"),
    texts: list[str] | None = Field(default=None, description="Batch of texts to analyze"),
    source: str = Field(default="news", description="Text source: news, social_media, filings, reports"),
    model: str | None = Field(default=None, description="Sentiment model to use"),
    aggregate: bool = Field(default=False, description="Aggregate results for batch input"),
) -> dict[str, Any]:
    """
    Analyze sentiment in text data.

    Args:
        text: Single text input.
        texts: Batch text input.
        source: Type of text source.
        model: Optional sentiment model name.
        aggregate: Whether to aggregate batch results.

    Returns:
        Dictionary with sentiment scores and labels.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-openalex / user-newsapi
        Tool: (sentiment analysis via LLM)
    """
    raise NotImplementedError(
        "analyze_sentiment must be called via MCP adapter. "
        "Use call_mcp_tool('user-openalex', '...', ...) instead."
    )


@tool(
    name="document_qa",
    description="Answer questions based on document content using RAG (Retrieval-Augmented Generation).",
    tags=["analysis", "nlp", "rag"],
    examples=[
        {"question": "What are the main risk factors?", "document": "annual_report.pdf"},
        {"question": "Summarize the key findings", "document_url": "https://example.com/paper.pdf"},
    ],
)
async def document_qa(
    question: str = Field(description="Question to answer"),
    document: str | None = Field(default=None, description="Path to local document"),
    document_url: str | None = Field(default=None, description="URL to remote document"),
    document_text: str | None = Field(default=None, description="Direct document text"),
    max_context_length: int = Field(default=4000, ge=100, le=16000, description="Max context tokens"),
    top_k: int = Field(default=5, ge=1, le=20, description="Number of context chunks to retrieve"),
) -> dict[str, Any]:
    """
    Answer questions based on document content.

    Args:
        question: The question to answer.
        document: Local file path to document.
        document_url: URL to fetch document from.
        document_text: Direct text input.
        max_context_length: Maximum context length.
        top_k: Number of relevant chunks to retrieve.

    Returns:
        Dictionary with answer and supporting context.

    Note:
        This function must be called via MCP adapter, not directly.
        Direct invocation will raise NotImplementedError.
        Server: user-context7 / user-filesystem-mcp
        Tool: (RAG document QA)
    """
    raise NotImplementedError(
        "document_qa must be called via MCP adapter. "
        "Use call_mcp_tool('user-context7', '...', ...) instead."
    )


# ─── Utility Functions ────────────────────────────────────────────────────────


def create_tool_from_function(
    func: Callable,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> Tool:
    """
    Create a Tool instance from a raw function.

    Parameters
    ----------
    func : Callable
        The function to convert.
    name : str | None
        Tool name (defaults to function name).
    description : str | None
        Tool description (defaults to docstring).
    tags : list[str] | None
        Tool tags.

    Returns
    -------
    Tool
        Tool instance.
    """
    return Tool(
        name=name or func.__name__,
        description=description or inspect.getdoc(func) or "",
        parameters=generate_json_schema(func),
        fn=func,
        is_async=asyncio.iscoroutinefunction(func),
        docstring=inspect.getdoc(func) or "",
        tags=tags,
    )


def get_tool_metadata(func: Callable) -> dict[str, Any] | None:
    """
    Get tool metadata from a decorated function.

    Parameters
    ----------
    func : Callable
        The decorated function.

    Returns
    -------
    dict | None
        Tool metadata dictionary, or None if not decorated.
    """
    return getattr(func, "_tool_metadata", None)


def is_tool(func: Callable) -> bool:
    """
    Check if a function is decorated with @tool.

    Parameters
    ----------
    func : Callable
        The function to check.

    Returns
    -------
    bool
        True if the function has @tool decorator.
    """
    return hasattr(func, "_tool_metadata") or hasattr(func, "_tool")


# ─── Module Exports ───────────────────────────────────────────────────────────

__all__ = [
    # Core classes
    "Tool",
    "ToolResult",
    "ToolRegistry",
    # Decorator
    "tool",
    # Integration
    "MCPAdapter",
    "ToolSelectorBridge",
    # Utilities
    "create_tool_from_function",
    "get_tool_metadata",
    "is_tool",
    "generate_json_schema",
    # Built-in tools
    "arxiv_search",
    "brave_search",
    "fetch_webpage",
    "get_stock_price",
    "get_macro_indicator",
    "run_regression",
    "generate_report",
    "get_research_report",
    "analyze_sentiment",
    "document_qa",
]
