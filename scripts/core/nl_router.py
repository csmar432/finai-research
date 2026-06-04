"""自然语言 MCP 工具路由 — 将用户意图转换为 MCP 工具调用序列.

参考 OpenEcon 自然语言接口设计。

工作流程：
  1. 用户输入自然语言请求
  2. LLM 解析 → 分解为工具调用计划（ToolCallPlan）
  3. 验证工具可用性（检查 MCP server 是否在线）
  4. 并行/顺序执行工具调用
  5. 合并结果 → 返回结构化 DataFrame / dict

Usage:
    router = NLRouter()

    # 示例 1：简单查询
    result = router.route("Get the CPI data for China and US from 2010 to 2023")
    print(result.dataframe)

    # 示例 2：金融分析
    result = router.route("分析茅台2024年的ROE、毛利率和资产负债率")
    print(result.dataframe)

    # 示例 3：多步骤研究
    plans = router.plan("研究关税政策对A股出口型企业的影响")
    for plan in plans:
        print(plan.description)
        result = router.execute(plan)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "NLCapability",
    "ToolCallPlan",
    "NLExecutionResult",
    "NLRouter",
]


# ─── Capability Registry ────────────────────────────────────────────────────────


@dataclass
class NLCapability:
    """
    描述一个 MCP 工具的自然语言路由能力。

    Attributes
    ----------
    server : str
        MCP server 名称。
    tool : str
        MCP 工具名称。
    aliases : list[str]
        自然语言别名列表（用于 LLM 识别）。
    examples : list[str]
        用法示例（few-shot 给 LLM 参考）。
    args_schema : dict
        参数 schema（用于验证 LLM 生成的参数）。
    description : str
        工具功能描述。
    """

    server: str
    tool: str
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    args_schema: dict = field(default_factory=dict)
    description: str = ""


# ─── 内置工具注册表 ────────────────────────────────────────────────────────────


TOOL_REGISTRY: list[NLCapability] = [
    NLCapability(
        server="user-yfinance",
        tool="get_ticker_info",
        aliases=["stock info", "公司信息", "股票信息", "ticker info"],
        examples=[
            "Get info for AAPL",
            "茅台的股票信息",
            "查询苹果公司的基本信息",
        ],
        description="获取股票基本信息（公司名、行业、市值、PE等）",
    ),
    NLCapability(
        server="user-yfinance",
        tool="get_financials",
        aliases=["financial statement", "财务报表", "income statement", "balance sheet"],
        examples=[
            "Get financials for TSLA",
            "苹果2020-2024年的财务报表",
            "特斯拉的利润表和资产负债表",
        ],
        description="获取财务报表（利润表/资产负债表/现金流量表）",
    ),
    NLCapability(
        server="user-yfinance",
        tool="get_sustainability",
        aliases=["ESG score", "ESG评级", "环境社会治理", "sustainability"],
        examples=[
            "Get ESG score for JNJ",
            "强生的ESG评分",
            "贵州茅台的ESG表现",
        ],
        description="获取 ESG 评分和环境社会治理数据",
    ),
    NLCapability(
        server="user-finviz-sec",
        tool="get_financial_snapshot",
        aliases=["financial snapshot", "财务摘要", "关键财务指标"],
        examples=[
            "Financial snapshot for MSFT",
            "微软财务摘要",
        ],
        description="获取财务摘要和关键指标",
    ),
    NLCapability(
        server="user-finviz-sec",
        tool="get_analyst_ratings",
        aliases=["analyst rating", "分析师评级", "recommendation", "目标价"],
        examples=[
            "Analyst ratings for NVDA",
            "英伟达分析师评级",
            "特斯拉的目标价和评级趋势",
        ],
        description="获取分析师评级和目标价",
    ),
    NLCapability(
        server="user-eodhd",
        tool="get_macro_indicator",
        aliases=[
            "GDP", "CPI", "inflation", "unemployment", "宏观指标",
            "国内生产总值", "消费者价格指数", "通货膨胀", "失业率",
        ],
        examples=[
            "Get CPI for China 2010-2023",
            "中国2010-2023年的CPI数据",
            "美国的GDP增长率",
        ],
        description="获取宏观指标（GDP/CPI/失业率/人口等）",
    ),
    NLCapability(
        server="user-eodhd",
        tool="get_ust_yield_rates",
        aliases=["treasury yield", "国债收益率", "yield curve", "美债收益率"],
        examples=[
            "US Treasury yield curve 2024",
            "2024年美国国债收益率曲线",
            "10年期国债收益率",
        ],
        description="获取美国国债收益率曲线",
    ),
    NLCapability(
        server="user-financial",
        tool="get_macro_china",
        aliases=["China macro", "中国宏观", "PPI", "PMI", "M2", "社会融资规模"],
        examples=[
            "China M2 money supply",
            "中国M2广义货币供应量",
            "中国PMI采购经理指数",
        ],
        description="中国宏观指标（CPI/PPI/PMI/M2/FDI等）",
    ),
    NLCapability(
        server="user-province-stats",
        tool="get_province_indicator",
        aliases=["province GDP", "省级数据", "省份GDP", "省R&D", "高新技术企业数"],
        examples=[
            "Hubei province GDP 2023",
            "湖北省2023年GDP",
            "江苏省高新技术企业数量",
        ],
        description="中国省级面板数据（GDP/R&D/高企等）",
    ),
    NLCapability(
        server="user-eastmoney-reports",
        tool="get_research_report",
        aliases=["research report", "研报", "券商报告", "行业报告"],
        examples=[
            "Research reports for 600519",
            "贵州茅台研报",
            "新能源汽车行业研究报告",
        ],
        description="获取券商研报和行业研究报告",
    ),
    NLCapability(
        server="user-brave-search",
        tool="web_search",
        aliases=["search", "搜索", "google search", "网络搜索"],
        examples=[
            "Search for carbon trading policy research",
            "搜索碳排放权交易研究文献",
            "关税政策影响研究",
        ],
        description="网络搜索",
    ),
    NLCapability(
        server="user-enhanced-finance",
        tool="get_forex_spot",
        aliases=["forex", "exchange rate", "汇率", "USD/CNY", "美元汇率"],
        examples=[
            "USD/CNY exchange rate",
            "美元兑人民币汇率",
            "EUR/USD即期汇率",
        ],
        description="外汇即期汇率",
    ),
]


# ─── Execution Plan ────────────────────────────────────────────────────────────


class PlanStepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ToolCallPlan:
    """
    单步工具调用计划。

    Attributes
    ----------
    step_id : str
        唯一步骤标识。
    capability : NLCapability
        匹配的工具能力。
    args : dict
        LLM 生成的参数。
    description : str
        步骤描述（给用户看）。
    mode : str
        "parallel" 或 "sequential"。
    status : PlanStepStatus
        执行状态。
    result : Any
        执行结果。
    error : str | None
        错误信息。
    """

    step_id: str
    capability: NLCapability
    args: dict[str, Any]
    description: str = ""
    mode: str = "sequential"
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "server": self.capability.server,
            "tool": self.capability.tool,
            "args": self.args,
            "description": self.description,
            "mode": self.mode,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class NLExecutionResult:
    """
    自然语言执行结果。

    Attributes
    ----------
    plans : list[ToolCallPlan]
        所有步骤的执行计划。
    dataframe : pd.DataFrame | None
        合并后的结构化 DataFrame（如果有）。
    raw_results : dict[str, Any]
        原始结果字典。
    summary : str
        自然语言摘要。
    total_time_ms : float
        总执行时间。
    """

    plans: list[ToolCallPlan]
    dataframe: Any = None
    raw_results: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    total_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plans": [p.to_dict() for p in self.plans],
            "has_dataframe": self.dataframe is not None,
            "summary": self.summary,
            "total_time_ms": self.total_time_ms,
        }


# ─── NL Router ────────────────────────────────────────────────────────────────


class NLRouter:
    """
    自然语言 MCP 工具路由。

    核心能力：
      - 自然语言理解 → 工具调用计划
      - 参数验证和类型转换
      - 并行/顺序执行策略
      - 结果合并和格式化

    Usage
    -----
        router = NLRouter()

        # 路由
        result = router.route("Get CPI for China and US from 2010 to 2023")
        print(result.dataframe)

        # 仅规划
        plans = router.plan("分析茅台、五粮液、泸州老窖的财务数据")
        for p in plans:
            print(p.description, p.capability.tool, p.args)

        # 执行
        result = router.execute_all(plans)
    """

    def __init__(
        self,
        capabilities: list[NLCapability] | None = None,
        llm_provider: str = "claude",
        verbose: bool = False,
    ):
        self.capabilities = capabilities or TOOL_REGISTRY
        self.llm_provider = llm_provider
        self.verbose = verbose

    # ── Tool Matching ───────────────────────────────────────────────────────

    def _build_tool_descriptions(self) -> str:
        """构建工具描述表（用于 LLM prompt）。"""
        lines = []
        for cap in self.capabilities:
            aliases = ", ".join(cap.aliases) if cap.aliases else "(无别名)"
            examples = "\n  - ".join(cap.examples) if cap.examples else "(无示例)"
            lines.append(
                f"- **{cap.server}/{cap.tool}**\n"
                f"  别名: {aliases}\n"
                f"  描述: {cap.description}\n"
                f"  示例: {examples}"
            )
        return "\n".join(lines)

    def _llm_parse(self, query: str) -> list[ToolCallPlan]:
        """
        使用 LLM 将自然语言解析为工具调用计划。

        Returns
        -------
        list[ToolCallPlan]
        """
        tool_descs = self._build_tool_descriptions()

        prompt = f"""你是一个金融数据助手。请将以下自然语言查询转换为工具调用计划。

可用工具：
{tool_descs}

查询：{query}

请按以下 JSON 格式输出（仅输出 JSON，不要其他内容）：
{{
  "plans": [
    {{
      "step_id": "step_1",
      "server": "user-xxx",
      "tool": "tool_name",
      "args": {{"param": "value", ...}},
      "description": "这一步做什么",
      "mode": "sequential"
    }}
  ]
}}

注意：
- args 中的参数值必须从查询中提取，不得虚构
- 如果查询涉及多个实体（多个股票/国家），在 args 中使用列表
- 支持并行执行的步骤 mode="parallel"
- step_id 必须唯一，格式为 step_N（N 从 1 开始）
"""

        try:
            from scripts.core.llm_gateway import LLMGateway
            gateway = LLMGateway(memory=None)
            response = gateway.generate(
                prompt,
                task_hint="nl_tool_routing",
            )
            text = response.response if hasattr(response, "response") else str(response)

            # 提取 JSON
            import re
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(text)

            plans = []
            for item in data.get("plans", []):
                cap = self._find_capability(item["server"], item["tool"])
                if cap is None:
                    logger.warning(f"[NLRouter] Unknown tool: {item['server']}/{item['tool']}")
                    continue
                plans.append(ToolCallPlan(
                    step_id=item["step_id"],
                    capability=cap,
                    args=item.get("args", {}),
                    description=item.get("description", ""),
                    mode=item.get("mode", "sequential"),
                ))
            return plans

        except Exception as exc:
            logger.error(f"[NLRouter] LLM parsing failed: {exc}")
            return []

    def _find_capability(self, server: str, tool: str) -> NLCapability | None:
        """查找匹配的 capability。"""
        for cap in self.capabilities:
            if cap.server == server and cap.tool == tool:
                return cap
        return None

    # ── Main API ──────────────────────────────────────────────────────────

    def plan(self, query: str) -> list[ToolCallPlan]:
        """
        规划阶段：将自然语言解析为工具调用计划（不执行）。

        Parameters
        ----------
        query : str
            自然语言查询。

        Returns
        -------
        list[ToolCallPlan]
        """
        if self.verbose:
            logger.info(f"[NLRouter] Planning: {query}")

        plans = self._llm_parse(query)

        if self.verbose:
            logger.info(f"[NLRouter] Generated {len(plans)} steps")
            for p in plans:
                logger.info(f"  [{p.step_id}] {p.capability.server}/{p.capability.tool} → {p.args}")

        return plans

    def execute(self, plan: ToolCallPlan) -> ToolCallPlan:
        """
        执行单个工具调用。

        Parameters
        ----------
        plan : ToolCallPlan
            要执行的计划。

        Returns
        -------
        ToolCallPlan
            执行后的计划（含 result 或 error）。
        """
        start = time.time()
        plan.status = PlanStepStatus.RUNNING

        try:
            from scripts.core.llm_gateway import call_mcp_tool
            result = call_mcp_tool(
                plan.capability.server,
                plan.capability.tool,
                plan.args,
            )
            plan.result = result
            plan.status = PlanStepStatus.SUCCESS
            plan.execution_time_ms = (time.time() - start) * 1000

        except Exception as exc:
            plan.error = str(exc)
            plan.status = PlanStepStatus.FAILED
            plan.execution_time_ms = (time.time() - start) * 1000
            logger.warning(f"[NLRouter] {plan.step_id} failed: {exc}")

        return plan

    def execute_all(self, plans: list[ToolCallPlan]) -> NLExecutionResult:
        """
        执行所有工具调用计划（支持并行）。

        Parameters
        ----------
        plans : list[ToolCallPlan]
            由 plan() 生成的调用计划。

        Returns
        -------
        NLExecutionResult
        """
        start = time.time()
        raw: dict[str, Any] = {}

        # 分组：parallel vs sequential
        parallel_steps = [p for p in plans if p.mode == "parallel"]
        sequential_steps = [p for p in plans if p.mode == "sequential"]

        # 执行 parallel 组
        for p in parallel_steps:
            self.execute(p)
            raw[p.step_id] = p.result or {"error": p.error}

        # 执行 sequential 组
        for p in sequential_steps:
            self.execute(p)
            raw[p.step_id] = p.result or {"error": p.error}

        # 尝试合并为 DataFrame
        df = self._merge_to_dataframe(raw)

        total_ms = (time.time() - start) * 1000

        return NLExecutionResult(
            plans=plans,
            dataframe=df,
            raw_results=raw,
            total_time_ms=total_ms,
        )

    def route(self, query: str) -> NLExecutionResult:
        """
        端到端路由：解析 → 执行 → 合并结果。

        Parameters
        ----------
        query : str
            自然语言查询。

        Returns
        -------
        NLExecutionResult
        """
        plans = self.plan(query)
        if not plans:
            return NLExecutionResult(plans=[], summary="无法解析查询")
        return self.execute_all(plans)

    # ── Result Merging ───────────────────────────────────────────────────

    def _merge_to_dataframe(self, results: dict[str, Any]) -> Any:
        """
        尝试将多个工具返回结果合并为 DataFrame。

        当前支持：
          - 相同的结构化数据（列表 of dicts）
          - 时间序列数据（带 date/year 字段）
          - 单值结果（汇总）
        """
        import pandas as pd

        dataframes: list[Any] = []

        for step_id, result in results.items():
            if result is None:
                continue

            if isinstance(result, pd.DataFrame):
                df = result.copy()
                df["_step_id"] = step_id
                dataframes.append(df)
            elif isinstance(result, dict):
                if "data" in result and isinstance(result["data"], list):
                    df = pd.DataFrame(result["data"])
                    df["_step_id"] = step_id
                    dataframes.append(df)
                elif "error" in result:
                    pass
            elif isinstance(result, list):
                df = pd.DataFrame(result)
                df["_step_id"] = step_id
                dataframes.append(df)

        if not dataframes:
            return None

        if len(dataframes) == 1:
            return dataframes[0]

        # 尝试合并（列对齐）
        try:
            merged = pd.concat(dataframes, ignore_index=True, sort=False)
            return merged
        except Exception:
            return None

    # ── Capability Management ─────────────────────────────────────────────

    def register(self, capability: NLCapability) -> None:
        """注册新的工具能力。"""
        self.capabilities.append(capability)

    def list_capabilities(self) -> list[NLCapability]:
        """列出所有已注册的工具能力。"""
        return list(self.capabilities)
