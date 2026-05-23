"""ToolSelector: Tool registry and routing for the economic research agent.

Provides:
- ToolCapability registry (MCP tools + Python scripts)
- Task-type-based tool selection with cost and VPN filtering
- Fallback execution chain
- MCP and script invocation layer
"""

from __future__ import annotations

import importlib
import time
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any

from scripts.core.memory import ResearchMemory
from scripts.core.planner import Task, TaskType


# ─── Cost Tier ──────────────────────────────────────────────────────────────────


class CostTier(Enum):
    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Cost ordering: FREE < LOW < MEDIUM < HIGH
_COST_ORDER: dict[CostTier, int] = {
    CostTier.FREE: 0,
    CostTier.LOW: 1,
    CostTier.MEDIUM: 2,
    CostTier.HIGH: 3,
}


# ─── Core DataClasses ───────────────────────────────────────────────────────────


@dataclass
class ToolCapability:
    """
    Describes a single available tool.

    Attributes
    ----------
    name : str
        Unique identifier for the tool.
    task_types : list[TaskType]
        Task types this tool can handle.
    inputs : list[str]
        Required input field names.
    outputs : list[str]
        Output field names produced by the tool.
    priority : int
        Priority rank — smaller number means higher priority.
    cost : CostTier
        Cost tier for this tool.
    requires_vpn : bool
        Whether this tool requires an active VPN connection.
    description : str
        Human-readable description.
    callable : Any, optional
        A reference to the callable Python function / module for script tools.
    """

    name: str
    task_types: list[TaskType]
    inputs: list[str]
    outputs: list[str]
    priority: int
    cost: CostTier
    requires_vpn: bool
    description: str
    callable: Any | None = None


@dataclass
class ToolSelection:
    """
    Result of tool selection — describes a chosen tool and why it was chosen.
    """

    tool_name: str
    confidence: float  # 0.0–1.0
    reason: str
    estimated_cost: str  # human-readable, matches CostTier.value
    requires_vpn: bool
    callable: Any | None = None


@dataclass
class ToolResult:
    """
    Result of tool execution.
    """

    success: bool
    output: Any
    tool_name: str
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False


# ─── Tool Registry ──────────────────────────────────────────────────────────────


class ToolSelector:
    """
    Registry of all available tools (MCP + Python scripts) and selection logic.

    Selection strategy
    ------------------
    1. Filter by TaskType match (tool.task_types contains task.task_type).
    2. Exclude VPN-required tools when VPN is unavailable.
    3. Sort by priority ascending, then cost tier ascending (FREE → LOW → MEDIUM → HIGH).
    4. Assign confidence = 1.0 for first-ranked candidate, 0.8 for others.
    """

    TOOL_REGISTRY: dict[str, ToolCapability] = {}

    _registry_initialized = False

    # ── Registry initialization ──────────────────────────────────────────────

    @classmethod
    def _init_registry(cls):
        """Populate TOOL_REGISTRY with all known tools (idempotent)."""
        if cls._registry_initialized:
            return

        # ── MCP Tools ───────────────────────────────────────────────────────────

        cls.TOOL_REGISTRY["arxiv"] = ToolCapability(
            name="arxiv",
            task_types=[TaskType.LITERATURE, TaskType.DATA_FETCH],
            inputs=["query", "max_results"],
            outputs=["papers"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="ArXiv论文检索和下载",
        )

        cls.TOOL_REGISTRY["financial"] = ToolCapability(
            name="financial",
            task_types=[TaskType.DATA_FETCH],
            inputs=["ticker", "data_type"],
            outputs=["price", "fundamentals", "macro"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="宏观经济、行情、crypto（yfinance/FRED）",
        )

        cls.TOOL_REGISTRY["finviz_sec"] = ToolCapability(
            name="finviz_sec",
            task_types=[TaskType.DATA_FETCH, TaskType.ANALYSIS],
            inputs=["ticker", "action"],
            outputs=["screening", "fundamentals", "sec_filings"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="美股筛选、90+基本面、SEC文件",
        )

        cls.TOOL_REGISTRY["brave_search"] = ToolCapability(
            name="brave_search",
            task_types=[TaskType.LITERATURE, TaskType.DATA_FETCH],
            inputs=["query"],
            outputs=["search_results"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="财经新闻、政策文件网络检索",
        )

        cls.TOOL_REGISTRY["fetch"] = ToolCapability(
            name="fetch",
            task_types=[TaskType.DATA_FETCH],
            inputs=["url"],
            outputs=["content"],
            priority=3,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="网页正文抓取",
        )

        cls.TOOL_REGISTRY["eastmoney_reports"] = ToolCapability(
            name="eastmoney_reports",
            task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
            inputs=["query", "industry"],
            outputs=["research_reports"],
            priority=2,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="东方财富研报",
        )

        cls.TOOL_REGISTRY["context7"] = ToolCapability(
            name="context7",
            task_types=[TaskType.CODE],
            inputs=["library", "query"],
            outputs=["documentation"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="官方API文档查询",
        )

        # ── Python Script Tools ─────────────────────────────────────────────────

        cls.TOOL_REGISTRY["fetch_a_stock"] = ToolCapability(
            name="fetch_a_stock",
            task_types=[TaskType.DATA_FETCH],
            inputs=["code", "start_date", "end_date"],
            outputs=["df"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="A股日线数据（akshare）",
            callable=None,  # loaded dynamically via _call_script
        )

        cls.TOOL_REGISTRY["econometrics_regression"] = ToolCapability(
            name="econometrics_regression",
            task_types=[TaskType.ANALYSIS],
            inputs=["df", "formula", "cluster"],
            outputs=["results", "table"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="OLS/DID回归（statsmodels）",
            callable=None,
        )

        cls.TOOL_REGISTRY["literature_search"] = ToolCapability(
            name="literature_search",
            task_types=[TaskType.LITERATURE],
            inputs=["query", "max_results"],
            outputs=["papers", "review"],
            priority=1,
            cost=CostTier.FREE,
            requires_vpn=False,
            description="文献检索→下载→综述",
            callable=None,
        )

        cls.TOOL_REGISTRY["paper_write"] = ToolCapability(
            name="paper_write",
            task_types=[TaskType.WRITING],
            inputs=["topic", "section", "outline"],
            outputs=["content"],
            priority=1,
            cost=CostTier.LOW,
            requires_vpn=False,
            description="论文章节写作（调用LLM）",
            callable=None,
        )

        cls.TOOL_REGISTRY["report_generator"] = ToolCapability(
            name="report_generator",
            task_types=[TaskType.WRITING, TaskType.VISUALIZATION],
            inputs=["company", "data", "format"],
            outputs=["report", "charts"],
            priority=1,
            cost=CostTier.LOW,
            requires_vpn=False,
            description="研报生成+可视化图表",
            callable=None,
        )

        cls.TOOL_REGISTRY["llm_sentiment"] = ToolCapability(
            name="llm_sentiment",
            task_types=[TaskType.ANALYSIS],
            inputs=["texts"],
            outputs=["sentiments"],
            priority=2,
            cost=CostTier.LOW,
            requires_vpn=True,
            description="批量情感分析（LLMProcessor）",
            callable=None,
        )

        cls._registry_initialized = True

    # ── Initialization ──────────────────────────────────────────────────────────

    def __init__(self, memory: ResearchMemory):
        self.memory = memory
        self._availability_cache: dict[str, bool] = {}
        self._vpn_available: bool | None = None

        # Ensure registry is populated
        self._init_registry()

    # ── Selection ───────────────────────────────────────────────────────────────

    def select(
        self, task: Task, context: list["ResearchMemory"]
    ) -> list[ToolSelection]:
        """
        Select the best tools for a given task, sorted by priority and cost.

        Parameters
        ----------
        task : Task
            The task to select tools for.
        context : list[ContextUnit]
            Current session context (not currently used for filtering,
            but available for future context-aware selection).

        Returns
        -------
        list[ToolSelection]
            Tools ranked by priority and cost. Empty list if no tool matches.
        """
        vpn_ok = self._check_vpn()

        # 1. Filter: task type match + VPN constraint
        candidates: list[ToolCapability] = []
        for tool in self.TOOL_REGISTRY.values():
            if task.task_type not in tool.task_types:
                continue
            if tool.requires_vpn and not vpn_ok:
                continue
            candidates.append(tool)

        if not candidates:
            return []

        # 2. Sort: priority asc, then cost asc
        candidates.sort(key=lambda t: (_COST_ORDER[t.cost], t.priority))

        # 3. Build ToolSelection list with confidence
        selections = []
        for i, cap in enumerate(candidates):
            confidence = 1.0 if i == 0 else 0.8
            reason = self._build_reason(cap, task)
            selections.append(ToolSelection(
                tool_name=cap.name,
                confidence=confidence,
                reason=reason,
                estimated_cost=cap.cost.value,
                requires_vpn=cap.requires_vpn,
                callable=cap.callable,
            ))

        return selections

    def _build_reason(self, cap: ToolCapability, task: Task) -> str:
        """Build a human-readable reason for selecting this tool."""
        task_type_names = [tt.value for tt in cap.task_types]
        return (
            f"Tool '{cap.name}' handles {task_type_names} "
            f"with priority={cap.priority}, cost={cap.cost.value}. "
            f"Description: {cap.description}"
        )

    # ── Execution ───────────────────────────────────────────────────────────────

    def execute(self, selection: ToolSelection, inputs: dict) -> ToolResult:
        """
        Execute the selected tool with the given inputs.

        Tries the primary selection first. On failure, attempts fallback by
        re-selecting a lower-priority tool for the same task (caller should
        retry with next selection in the list).

        Parameters
        ----------
        selection : ToolSelection
            The tool to execute.
        inputs : dict
            Input parameters for the tool.

        Returns
        -------
        ToolResult
            Structured result (success=True or success=False with error message).
        """
        tool_name = selection.tool_name
        cap = self.TOOL_REGISTRY.get(tool_name)

        if cap is None:
            return ToolResult(
                success=False,
                output=None,
                tool_name=tool_name,
                error=f"Tool '{tool_name}' not found in registry",
            )

        start = time.time()

        # Check availability
        if not self._check_tool_availability(tool_name):
            return ToolResult(
                success=False,
                output=None,
                tool_name=tool_name,
                error=f"Tool '{tool_name}' is not currently available",
                latency_ms=(time.time() - start) * 1000,
            )

        # Determine tool category
        mcp_tools = {
            "arxiv", "financial", "finviz_sec", "brave_search",
            "fetch", "eastmoney_reports", "context7",
        }
        script_tools = {
            "fetch_a_stock", "econometrics_regression", "literature_search",
            "paper_write", "report_generator", "llm_sentiment",
        }

        try:
            if tool_name in mcp_tools:
                output = self._call_mcp(tool_name, inputs)
            elif tool_name in script_tools:
                output = self._call_script(tool_name, inputs)
            else:
                output = self._call_script(tool_name, inputs)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                success=False,
                output=None,
                tool_name=tool_name,
                error=str(exc),
                latency_ms=(time.time() - start) * 1000,
            )

        return ToolResult(
            success=True,
            output=output,
            tool_name=tool_name,
            latency_ms=(time.time() - start) * 1000,
        )

    # ── Tool Invocation ─────────────────────────────────────────────────────────

    def _call_mcp(self, tool_name: str, params: dict) -> Any:
        """
        Call an MCP tool by name.

        MCP tools are invoked via the MCP CLI or server process.
        This is a stub implementation that raises NotImplementedError.
        Real MCP invocation requires the MCP server running; callers should
        mock this method in tests.
        """
        # MCP tool routing would go through the MCP server here.
        # Example (pseudo-code):
        #   mcp_server = get_mcp_server(tool_name)
        #   return mcp_server.call(tool_name, params)
        raise NotImplementedError(
            f"MCP invocation for '{tool_name}' not implemented. "
            "Set up the MCP server for this tool and mock in tests."
        )

    def _call_script(self, tool_name: str, params: dict) -> Any:
        """
        Invoke a Python script tool by dynamically importing its module.

        Tool name → module mapping:
            fetch_a_stock            → scripts.data_pipeline (function: fetch_stock_data)
            econometrics_regression  → scripts.econometrics (function: run_regression)
            literature_search        → scripts.literature_search (function: search)
            paper_write              → scripts.paper_write (function: write_section)
            report_generator         → scripts.report_generator (function: generate)
            llm_sentiment            → scripts.review_layer (function: batch_sentiment)

        This is a stub; the actual module/function is loaded via importlib.
        Raises NotImplementedError so callers can mock it in tests.
        """
        _SCRIPT_MAP: dict[str, tuple[str, str]] = {
            "fetch_a_stock": ("scripts.data_pipeline", "fetch_stock_data"),
            "econometrics_regression": ("scripts.econometrics", "run_regression"),
            "literature_search": ("scripts.literature_search", "search"),
            "paper_write": ("scripts.paper_write", "write_section"),
            "report_generator": ("scripts.report_generator", "generate_report"),
            "llm_sentiment": ("scripts.review_layer", "batch_sentiment"),
        }

        mapping = _SCRIPT_MAP.get(tool_name)
        if mapping is None:
            raise NotImplementedError(
                f"No script mapping defined for tool '{tool_name}'"
            )

        module_name, func_name = mapping
        try:
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            return func(**params)
        except (ImportError, AttributeError) as exc:
            raise NotImplementedError(
                f"Failed to import or call script tool '{tool_name}' "
                f"({module_name}.{func_name}): {exc}"
            ) from exc

    # ── Availability Checks ─────────────────────────────────────────────────────

    def _check_vpn(self) -> bool:
        """
        Check whether VPN is available by pinging api.b.ai.

        Returns cached result after first check.
        """
        if self._vpn_available is not None:
            return self._vpn_available

        try:
            req = urllib.request.Request(
                "https://api.b.ai/",
                method="HEAD",
                timeout=5,
            )
            with urllib.request.urlopen(req) as resp:
                self._vpn_available = resp.status == 200
        except Exception:
            self._vpn_available = False

        return self._vpn_available

    def _check_tool_availability(self, tool_name: str) -> bool:
        """
        Check whether a tool is currently available.

        Results are cached per tool name.
        """
        if tool_name in self._availability_cache:
            return self._availability_cache[tool_name]

        # Default: tools are available unless proven otherwise.
        # For MCP tools, a real availability check would ping the MCP server.
        # For script tools, availability means the module can be imported.
        available = self._probe_tool(tool_name)
        self._availability_cache[tool_name] = available
        return available

    def _probe_tool(self, tool_name: str) -> bool:
        """
        Probe a single tool for availability.

        MCP tools: assume available if VPN is up.
        Script tools: check import succeeds.
        """
        mcp_tools = {
            "arxiv", "financial", "finviz_sec", "brave_search",
            "fetch", "eastmoney_reports", "context7",
        }

        if tool_name in mcp_tools:
            # MCP tools are considered available if we have a network path
            return True

        # Script tool — check import
        _SCRIPT_MAP = {
            "fetch_a_stock": ("scripts.data_pipeline", "fetch_stock_data"),
            "econometrics_regression": ("scripts.econometrics", "run_regression"),
            "literature_search": ("scripts.literature_search", "search"),
            "paper_write": ("scripts.paper_write", "write_section"),
            "report_generator": ("scripts.report_generator", "generate_report"),
            "llm_sentiment": ("scripts.review_layer", "batch_sentiment"),
        }

        mapping = _SCRIPT_MAP.get(tool_name)
        if mapping is None:
            return False

        module_name, _ = mapping
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False
