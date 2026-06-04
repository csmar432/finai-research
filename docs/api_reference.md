# API Reference

> Complete API documentation for the core modules of the research workflow system.

---

## Table of Contents

1. [AgentOrchestrator](#agentorchestrator)
2. [ProvenanceTracker](#provenanttracker)
3. [MCPToolRegistry](#mcptoolregistry)
4. [CalibrationDataset & CalibrationAnalyzer](#calibrationdataset--calibrationanalyzer)
5. [EconometricsRuleEngine](#econometricsruleengine)
6. [JournalTemplateSelector](#journaltemplateselector)
7. [EventMonitor](#eventmonitor)

---

## AgentOrchestrator

**File**: `scripts/core/orchestrator.py`

Professional agent orchestration engine with pipeline execution, parallel agents, and HITL gates.

### Class: `AgentOrchestrator`

```python
from scripts.core.orchestrator import AgentOrchestrator, PipelineStage, PipelineStep
from scripts.core.llm_gateway import LLMGateway

orchestrator = AgentOrchestrator(gateway=gateway)
```

#### `__init__(gateway: LLMGateway)`

Initialize the orchestrator with an LLM gateway.

```python
gateway = LLMGateway()
orchestrator = AgentOrchestrator(gateway=gateway)
```

#### `register(agent: BaseAgent) -> None`

Register a professional agent (DeepResearchAgent Agent Registry pattern).

```python
from scripts.core.agents.base import AgentConfig
from scripts.core.agents.paper_agents import OutlineAgent

orchestrator.register(OutlineAgent(AgentConfig(
    name="outline",
    role="论文大纲设计专家",
    goal="将研究想法转化为结构化论文大纲",
), gateway))
```

#### `run_pipeline(name: str, input_data: dict) -> PipelineResult`

Execute a multi-stage pipeline.

```python
from scripts.core.orchestrator import PipelineStep, PipelineStage

steps = [
    PipelineStep(stage=PipelineStage.OUTLINE, agent_name="outline"),
    PipelineStep(stage=PipelineStage.LITERATURE, agent_name="literature"),
    PipelineStep(stage=PipelineStage.WRITING, agent_name="writing"),
]

result = orchestrator.run_pipeline(
    pipeline_name="paper_pipeline",
    steps=steps,
    input_data={"topic": "碳排放权交易对企业绿色创新的影响", "venue": "经济研究"}
)
print(f"Success: {result.success}, Latency: {result.total_latency_ms}ms")
```

#### `run_parallel(agent_names: list[str], input_data: dict) -> dict[str, AgentResult]`

Run multiple agents in parallel (independent stages only).

```python
results = orchestrator.run_parallel(
    agent_names=["literature", "plotting"],
    input_data={"outline": outline_result}
)
```

#### `register_default_agents() -> None`

Register PaperOrchestra's standard 5-agent pipeline:
1. `outline` — OutlineAgent
2. `literature` — LiteratureReviewAgent
3. `plotting` — PlottingAgent
4. `writing` — SectionWritingAgent
5. `refinement` — ContentRefinementAgent

```python
orchestrator.register_default_agents()
print(orchestrator.list_agents())
# ['outline', 'literature', 'plotting', 'writing', 'refinement', 'data_fetch']
```

#### `register_financial_agents() -> ParallelAnalystOrchestrator`

Register financial analyst agents for research report generation.

```python
analyst_orchestrator = orchestrator.register_financial_agents()
```

#### `cancel_agent(agent_name: str, reason: str) -> bool`

Cancel a running agent by name.

```python
orchestrator.cancel_agent("literature", reason="Timeout")
```

### Enum: `PipelineStage`

```python
class PipelineStage(Enum):
    OUTLINE = "outline"
    LITERATURE = "literature"
    PLOTTING = "plotting"
    WRITING = "writing"
    REFINEMENT = "refinement"
    EVALUATION = "evaluation"
    FINANCIAL_ANALYSIS = "financial_analysis"
    REPORT_WRITING = "report_writing"
```

### Dataclass: `PipelineResult`

```python
@dataclass
class PipelineResult:
    pipeline_name: str
    success: bool
    stage_results: dict[PipelineStage, AgentResult]
    final_context: dict[str, Any]
    total_latency_ms: float
    hitl_paused_at: PipelineStage | None = None
    evolution_events: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
```

---

## ProvenanceTracker

**File**: `scripts/core/provenance.py`

Track the data lineage of every chart and table, from raw API calls to final output.

### Class: `ProvenanceTracker`

```python
from scripts.core.provenance import ProvenanceTracker, ProvenanceNode
```

#### `__init__(session_id: str = "")`

Initialize the provenance tracker.

```python
tracker = ProvenanceTracker(session_id="carbon_trading_2024")
```

#### `register_data_source(node_id: str, source: str, mcp_server: str, mcp_tool: str, api_params: dict, description: str) -> str`

Register a data source node.

```python
tracker.register_data_source(
    node_id="tushare_daily",
    source="MCP:user_tushare",
    mcp_server="user-tushare",
    mcp_tool="get_daily_quote",
    api_params={"ts_code": "000001.SZ", "start_date": "20240101"},
    description="平安银行日线行情"
)
```

#### `register_transformation(node_id: str, transformation: str, parent_ids: list[str], description: str) -> str`

Register a data transformation node (cleaning, merging, aggregation).

```python
tracker.register_transformation(
    node_id="cleaned_data",
    transformation="dropna + rename columns",
    parent_ids=["tushare_daily"],
    description="数据清洗"
)
```

#### `register_chart(node_id: str, title: str, data_source_ref: str, chart_type: str, output_path: str) -> str`

Register a chart node.

```python
tracker.register_chart(
    node_id="fig1_price",
    title="平安银行股价走势图",
    data_source_ref="cleaned_data",
    chart_type="line",
    output_path="output/figures/stock_price.png"
)
```

#### `register_table(node_id: str, title: str, data_source_ref: str, table_type: str, output_path: str) -> str`

Register a table node.

```python
tracker.register_table(
    node_id="tab1_regression",
    title="回归分析结果",
    data_source_ref="merged_data",
    table_type="regression",
    output_path="output/tables/regression.tex"
)
```

#### `get_lineage(node_id: str) -> list[ProvenanceNode]`

Get the complete lineage from root nodes to the target node.

```python
lineage = tracker.get_lineage("fig1_price")
for node in lineage:
    print(f"{node.node_type}: {node.description}")
```

#### `get_latex_provenance(node_id: str | None = None, include_checksum: bool = True) -> str`

Generate LaTeX-formatted provenance comments.

```python
print(tracker.get_latex_provenance())
# % ===== Data Provenance =====
# % Session: carbon_trading_2024
# % \ provenance{
# %   session = {carbon_trading_2024},
# %   data_source 0: tushare_daily {
# %     description = {平安银行日线行情},
# %     mcp_server = {user-tushare},
# % ...
```

#### `to_graphviz(direction: str = "TB") -> str`

Generate Graphviz DOT format provenance graph.

```python
dot = tracker.to_graphviz(direction="LR")
```

#### `save(filepath: str) -> None` / `load(filepath: str) -> ProvenanceTracker`

Save and load tracker state.

```python
tracker.save("provenance/session_001.json")
tracker = ProvenanceTracker.load("provenance/session_001.json")
```

### Dataclass: `ProvenanceNode`

```python
@dataclass
class ProvenanceNode:
    node_id: str                                    # Unique identifier
    node_type: str                                   # "data_source" | "transformation" | "chart" | "table"
    description: str                                 # Description
    source_file: Optional[str] = None                # Source file
    source_line: Optional[int] = None               # Source line number
    mcp_server: Optional[str] = None                 # MCP server name
    mcp_tool: Optional[str] = None                  # MCP tool name
    api_params: Optional[dict] = None               # API call parameters
    timestamp: str = ""                              # ISO timestamp
    checksum: Optional[str] = None                   # SHA256 checksum
    parent_ids: list[str] = field(default_factory=list)   # Parent node IDs
    metadata: dict = field(default_factory=dict)            # Extra metadata
```

### Decorators

```python
@register_chart(title="股价走势图", data_source="tushare_daily", chart_type="line")
def generate_chart(data):
    # ... chart generation code ...
    return fig

@register_data_source(source="MCP:user_tushare", mcp_server="user-tushare", mcp_tool="get_daily_quote")
def fetch_stock_data(ts_code: str):
    # ... data fetching code ...
    return data
```

---

## MCPToolRegistry

**File**: `scripts/core/mcp_tool_market.py`

Searchable registry for all MCP servers under `mcp_servers/`.

### Class: `ToolMetadata`

```python
@dataclass
class ToolMetadata:
    name: str
    description: str
    input_schema: dict
    mcp_server: str
    category: str
    quality_score: float          # 0.0–1.0
    is_mock: bool
    requires_api_key: bool
    tags: list[str] = field(default_factory=list)
    last_updated: str = ""
    example_params: Optional[dict] = None
```

### Class: `MCPToolRegistry`

```python
from scripts.core.mcp_tool_market import MCPToolRegistry, ToolMetadata
```

#### `__init__()`

Initialize an empty registry.

```python
registry = MCPToolRegistry()
```

#### `from_directory(path: str | Path) -> MCPToolRegistry` (classmethod)

Scan a directory and build the registry.

```python
registry = MCPToolRegistry.from_directory("mcp_servers")
print(f"Loaded {len(registry)} tools")
```

#### `search(query: str, category: str | None = None, max_results: int = 10) -> list[ToolMetadata]`

Full-text search across name, description, and tags.

```python
results = registry.search("gdp", category="macro_data")
for tool in results:
    print(f"[{tool.quality_score:.2f}] {tool.mcp_server}::{tool.name}")
```

#### `get_by_server(server: str) -> list[ToolMetadata]`

Get all tools from a specific MCP server.

```python
tools = registry.get_by_server("user-tushare")
```

#### `get_by_category(category: str) -> list[ToolMetadata]`

Get all tools in a specific category.

```python
financial_tools = registry.get_by_category("financial")
```

#### `get_marketplace_report() -> dict`

Generate marketplace statistics.

```python
report = registry.get_marketplace_report()
print(f"Total: {report['total_tools']} tools")
print(f"Top 5: {report['top_5_by_quality']}")
```

**Report structure:**
```python
{
    "total_tools": 142,
    "total_servers": 25,
    "by_category": {"financial": 38, "macro_data": 45, ...},
    "by_server": {"user-tushare": 12, ...},
    "category_avg_quality": {"market_data": 0.72, ...},
    "requires_api_key": 8,
    "mock_tools": 15,
    "top_5_by_quality": [...],
    "generated_at": "2026-06-02T12:00:00"
}
```

#### `to_json() -> dict`

Export registry as JSON-serializable dict.

```python
data = registry.to_json()
```

#### `print_catalog(category: str | None = None) -> None`

Print formatted catalog to console.

```python
registry.print_catalog()           # All tools
registry.print_catalog("financial") # Financial only
```

### Global Singleton

```python
from scripts.core.mcp_tool_market import get_default_registry

registry = get_default_registry()  # Cached instance
```

### CLI Usage

```bash
# Show all tools
python scripts/core/mcp_tool_market.py --dir mcp_servers

# Search
python scripts/core/mcp_tool_market.py --search "gdp" --report

# By category
python scripts/core/mcp_tool_market.py --category financial

# By server
python scripts/core/mcp_tool_market.py --server user-tushare

# Export JSON
python scripts/core/mcp_tool_market.py --json > registry.json
```

---

## CalibrationDataset & CalibrationAnalyzer

**File**: `scripts/core/reviewer_calibration.py`

Measure LLM reviewer accuracy against human-labeled benchmark datasets.

### Class: `CalibrationDataset`

```python
from scripts.core.reviewer_calibration import (
    CalibrationDataset, CalibrationAnalyzer, CalibrationResult
)
```

#### `__init__()`

Initialize an empty calibration dataset.

```python
dataset = CalibrationDataset()
```

#### `add_sample(sample: CalibrationSample) -> None`

Add a single calibration sample.

```python
from scripts.core.reviewer_calibration import CalibrationSample

sample = CalibrationSample(
    sample_id="test_001",
    paper_abstract="This paper studies...",
    human_scores={
        "methodology_rigor": 8.0,
        "novelty": 7.5,
        "clarity": 8.0,
        "reproducibility": 7.5,
        "significance": 8.0,
        "overall": 8.0,
    },
    human_recommendation="accept",
    venue="JFE",
    year=2024
)
dataset.add_sample(sample)
```

#### `load_builtin_dataset() -> CalibrationDataset` (classmethod)

Load the built-in 20-sample benchmark dataset.

```python
dataset = CalibrationDataset.load_builtin_dataset()
print(f"Loaded {len(dataset.samples)} samples")
```

#### `load_from_json(path: str) -> None`

Load dataset from JSON file.

```python
dataset.load_from_json("data/calibration/my_benchmark.json")
```

#### `save_to_json(path: str) -> None`

Save dataset to JSON file.

```python
dataset.save_to_json("data/calibration/my_benchmark.json")
```

#### `get_benchmark_stats() -> dict`

Get benchmark dataset statistics.

```python
stats = dataset.get_benchmark_stats()
print(stats)
# {'n_samples': 20, 'recommendation_counts': {'accept': 8, 'reject': 6, 'borderline': 6}, ...}
```

### Class: `CalibrationAnalyzer`

#### `__init__(dataset: CalibrationDataset)`

Initialize analyzer with a calibration dataset.

```python
analyzer = CalibrationAnalyzer(dataset)
```

#### `evaluate_reviewer(reviewer) -> CalibrationResult`

Evaluate an LLMReviewer instance.

```python
from scripts.core.llm_reviewer import LLMReviewer

reviewer = LLMReviewer()
result = analyzer.evaluate_reviewer(reviewer)
print(f"Balanced Accuracy: {result.balanced_accuracy:.1%}")
```

**Returns:** `CalibrationResult` with fields:
```python
@dataclass
class CalibrationResult:
    balanced_accuracy: float  # 0.0–1.0
    overall_accuracy: float    # 0.0–1.0
    per_dimension: dict       # {dim: {"mae": float, "acc_within_1": float, "corr": float}}
    confusion_matrix: dict     # {actual_class: {predicted_class: count}}
    recommendations: dict      # {sample_id: {"predicted": str, "actual": str, "correct": bool}}
    benchmark_name: str
    n_samples: int
```

#### `generate_calibration_report(result: CalibrationResult) -> str`

Generate human-readable calibration report.

```python
report = analyzer.generate_calibration_report(result)
print(report)
```

**Example output:**
```
============================================================
LLM Reviewer Calibration Report
============================================================
Benchmark : builtin_20
Samples   : 20

Overall Metrics
----------------------------------------
  Balanced Accuracy : 75.0%
  Overall Accuracy : 80.0%

Confusion Matrix
----------------------------------------
  Actual        Accept   Reject Borderline
  accept            6       1          1
  reject            1       4          1
  borderline        1       1          4

Per-Dimension Metrics
----------------------------------------
  Dimension                   MAE    ±1    ±2   Corr
  Methodology Rigor        0.85   75.0% 90.0%  0.82
  ...
```

### Dataclass: `CalibrationSample`

```python
@dataclass
class CalibrationSample:
    sample_id: str
    paper_abstract: str
    human_scores: dict       # {dimension: score (1-10)}
    human_recommendation: str  # accept / reject / borderline
    venue: str
    year: int
```

---

## EconometricsRuleEngine

**File**: `scripts/core/econometrics_rules.py`

Automated validation of econometric methods in empirical research papers.

### Class: `EconometricsRuleEngine`

```python
from scripts.core.econometrics_rules import EconometricsRuleEngine, ValidationResult
```

#### `__init__()`

Initialize the econometrics rule engine.

```python
engine = EconometricsRuleEngine()
```

#### `validate(method: str, params: dict) -> ValidationResult`

Run validation for a specific econometric method.

```python
# Validate DID parallel trends
result = engine.validate("did", {
    "event_study_df": df,  # DataFrame with [period, coef, se]
    "pre_periods": 3,
})

# Validate IV instruments
result = engine.validate("iv", {
    "first_stage_f_stat": 24.5,
    "stock_yogo_threshold": 16.38,
})

# Validate PSM propensity score matching
result = engine.validate("psm", {
    "matched_df": df,
    "balance_threshold": 0.1,  # Max std. mean diff after matching
})

# Validate OLS heteroskedasticity
result = engine.validate("ols", {
    "residuals": residuals,
    "fitted_values": fitted,
})
```

#### `validate_did_parallel_trend(event_study_df, pre_periods: int) -> ValidationResult`

Validate DID parallel trends assumption via event study.

```python
result = engine.validate_did_parallel_trend(df, pre_periods=3)
print(result.summary())
```

#### `validate_iv_strength(first_stage_f: float, stock_yogo: float = 16.38) -> ValidationResult`

Validate IV instrument strength (Stock-Yogo threshold).

```python
result = engine.validate_iv_strength(first_stage_f=24.5)
print(result.summary())
```

#### `validate_psm_balance(matched_df, threshold: float = 0.1) -> ValidationResult`

Validate PSM propensity score matching balance.

```python
result = engine.validate_psm_balance(df, threshold=0.1)
print(result.summary())
```

### Dataclass: `ValidationResult`

```python
@dataclass
class ValidationResult:
    passed: bool                           # Whether all checks passed
    warnings: list[str] = field(default_factory=list)   # Warning messages
    errors: list[str] = field(default_factory=list)     # Error messages
    details: dict[str, Any] = field(default_factory=dict)  # Test details

    def add_warning(self, msg: str)
    def add_error(self, msg: str)
    @property
    def has_warnings(self) -> bool
    @property
    def has_errors(self) -> bool
    def summary(self) -> str
```

### Validation Methods

| Method | Description | Key Parameters |
|--------|-------------|----------------|
| `did` | Parallel trends for difference-in-differences | `event_study_df`, `pre_periods` |
| `iv` | Instrumental variables strength | `first_stage_f_stat`, `stock_yogo_threshold` |
| `psm` | Propensity score matching balance | `matched_df`, `balance_threshold` |
| `ols` | Heteroskedasticity in OLS | `residuals`, `fitted_values` |

---

## JournalTemplateSelector

**File**: `scripts/journal_template.py`

Manage LaTeX templates for financial and economics journals.

### Class: `JournalTemplate`

```python
from scripts.journal_template import JournalTemplate, get_template
```

#### `get_template(journal: str) -> JournalTemplate`

Get template by journal name.

```python
# English top journals
jfe = get_template("JFE")
jf = get_template("JF")
rfs = get_template("RFS")

# Chinese top journals
jjyj = get_template("经济研究")
glsj = get_template("管理世界")
jryj = get_template("金融研究")
```

#### `generate_example(output_path: str | Path) -> Path`

Generate an example file from the template.

```python
path = template.generate_example("output/paper.tex")
print(f"Generated: {path}")
```

#### `compile(tex_path: str | Path, engine: str = "pdflatex", passes: int = 2) -> bool`

Compile a LaTeX file using the template's format.

```python
success = template.compile("output/paper.tex")
```

### Template Attributes

```python
@dataclass
class JournalTemplate:
    name: str                      # Display name
    short_name: str               # Short code (e.g., "JFE")
    category: str                 # Category (financial/accounting/economics)
    description: str              # Description
    latex_code: str              # Main template code
    bibliography_style: str       # Bibliography format
    required_packages: list[str]  # Required LaTeX packages
    page_limit: str | None     # Page limit
    author_notes: bool = False    # Has author notes
    blind_review: bool = True     # Supports blind review
    url: str = ""                # Journal website
```

### Available Templates

| Journal | Short | Category | Page Limit |
|---------|-------|----------|------------|
| Journal of Financial Economics | JFE | 金融 | ~50 pages (double column) |
| Journal of Finance | JF | 金融 | ~50 pages (double column) |
| Review of Financial Studies | RFS | 金融 | ~60 pages (double column) |
| 经济研究 | 经济研究 | 经济 | ~20000 words |
| 管理世界 | 管理世界 | 经济 | ~20000 words |
| 金融研究 | 金融研究 | 金融 | ~20000 words |

### CLI Usage

```bash
# List all templates
python scripts/journal_template.py --list

# Generate a template
python scripts/journal_template.py --generate JFE output/paper.tex
```

---

## EventMonitor

**File**: `scripts/event_monitor.py`

Monitor financial events and trigger research pipelines automatically.

### Class: `EventMonitor`

```python
from scripts.event_monitor import EventMonitor
```

#### `__init__(check_interval: int = 300, auto_trigger: bool = False, config_path: str = "config/project_config.json")`

Initialize the event monitor.

```python
monitor = EventMonitor(
    check_interval=300,      # Check every 5 minutes
    auto_trigger=False,      # Require human approval
    config_path="config/project_config.json"
)
```

#### `add_event_handler(event_type: str, handler: Callable, **kwargs) -> None`

Register an event handler.

```python
def on_earnings(event):
    symbol = event["symbol"]
    print(f"Earnings released for {symbol}")
    # Trigger research pipeline
    return result

monitor.add_event_handler(
    event_type="earnings",
    handler=on_earnings
)
```

#### `add_custom_event(name: str, check_function: Callable, handler: Callable) -> None`

Register a custom event type.

```python
def check_earnings_season():
    # Check if we're in earnings season
    return is_earnings_season()

monitor.add_custom_event(
    name="earnings_season",
    check_function=check_earnings_season,
    handler=on_earnings
)
```

#### `start() -> None`

Start the monitoring loop.

```python
monitor.start()
```

#### `stop() -> None`

Stop the monitoring loop.

```python
monitor.stop()
```

#### `get_events(limit: int = 100) -> list[dict]`

Get recent events from the queue.

```python
events = monitor.get_events(limit=50)
for event in events:
    print(f"{event['timestamp']}: {event['event_type']}")
```

#### `get_history(days: int = 7) -> list[dict]`

Get event history for the past N days.

```python
history = monitor.get_history(days=30)
```

#### `clear_events() -> None`

Clear the event queue.

```python
monitor.clear_events()
```

### Event Types

| Type | Description | Trigger |
|------|-------------|---------|
| `earnings` | Quarterly/annual earnings releases | Symbol-based |
| `macro_release` | GDP, CPI, PMI announcements | Country + indicator |
| `policy` | Policy announcements matching keywords | Keyword-based |
| `custom` | User-defined event check functions | Function-based |

### Event Object Structure

```python
{
    "event_id": "evt_001",
    "event_type": "earnings",
    "timestamp": "2024-04-15T09:30:00",
    "symbol": "000001.SZ",
    "trigger": "Q1 2024 earnings release",
    "metadata": {
        "estimate": 1.25,
        "actual": 1.32,
        "beat": True
    }
}
```

### CLI Usage

```bash
# Test mode (no real data)
python scripts/event_monitor.py --interval 60 --test

# Production mode
python scripts/event_monitor.py --interval 300

# Auto-trigger (no approval required)
python scripts/event_monitor.py --interval 300 --auto-trigger

# One-shot check
python scripts/event_monitor.py --check-once
```

---

## Additional Modules

### DataFetcher

**File**: `scripts/research_framework/data_fetcher.py`

Unified data fetching with MCP fallback chain.

```python
from scripts.research_framework.data_fetcher import DataFetcher

fetcher = DataFetcher()

# Auto-selects best available data source
data = fetcher.get_stock_data("000001.SZ")

# Macro data
macro = fetcher.get_macro_data("china_gdp")
```

### LLMGateway

**File**: `scripts/core/llm_gateway.py`

Unified LLM gateway with multi-model routing.

```python
from scripts.core.llm_gateway import LLMGateway

gateway = LLMGateway()
response = gateway.chat("Analyze this paper abstract...")
```

### ResearchSession

**File**: `scripts/core/session.py`

Session management for research workflows.

```python
from scripts.core.session import ResearchSession, SessionConfig

session = ResearchSession(SessionConfig(
    session_id="carbon_trading_analysis",
    user_goal="分析碳排放权交易对企业绿色创新的影响",
    workspace_root=".",
    verbose=True
))
result = session.run("获取相关文献")
```

### SetupWizard

**File**: `scripts/setup_wizard.py`

首次运行引导系统，基于研究方向推荐 API Key 和 MCP 服务器配置。

#### 核心函数

##### `check_and_guide_setup(topic: str | None = None) -> dict`

由 `AgentPipeline` 自动调用，检测配置状态并返回引导信息。

```python
from scripts.setup_wizard import check_and_guide_setup

result = check_and_guide_setup(topic="关税政策对A股的影响")
# result = {
#     "needs_setup": True,
#     "missing": ["DEEPSEEK_API_KEY", "TUSHARE_API_KEY"],
#     "guidance": "..."   # 格式化的配置指南文本
# }
```

##### `get_current_status() -> dict[str, ConfigStatus]`

检测所有配置项的当前状态（已设置/未设置/脱敏值）。

##### `get_all_configs() -> list[ConfigStatus]`

返回完整配置项列表（含优先级、说明、适用方向）。

##### `DIRECTION_REQUIREMENTS`

研究方向 → 配置映射表：

| Direction | Label | 推荐配置 |
|-----------|-------|---------|
| `a_share` | A股研究 | DEEPSEEK_API_KEY, TUSHARE_API_KEY |
| `macro` | 宏观经济研究 | DEEPSEEK_API_KEY, BRAVE_SEARCH_API_KEY |
| `empirical_paper` | 实证学术论文 | DEEPSEEK_API_KEY, TUSHARE_API_KEY, BRAVE_SEARCH_API_KEY |
| `quantitative` | 量化投资研究 | DEEPSEEK_API_KEY, TUSHARE_API_KEY, EODHD_API_KEY |
| `financial_report` | 金融研究报告撰写 | DEEPSEEK_API_KEY, RELAY_API_KEY, TUSHARE_API_KEY, BRAVE_SEARCH_API_KEY |

#### CLI 用法

```bash
# 交互式引导（推荐首次使用）
python scripts/setup_wizard.py --guided

# 查看当前配置状态
python scripts/setup_wizard.py --status

# 指定研究方向快速配置
python scripts/setup_wizard.py --direction a_share --key DEEPSEEK_API_KEY=xxx

# 验证配置有效性
python scripts/setup_wizard.py --validate

# 生成 .env.local 模板
python scripts/setup_wizard.py --template
```

#### 与 AgentPipeline 的集成

`AgentPipeline.run()` 启动时自动调用 `check_and_suggest_setup()`：

```python
pipeline = AgentPipeline()
# 输入研究主题后，系统自动检测并提示缺失配置
result = pipeline.run("关税政策对A股的影响")
# 输出示例：
# ============================================================
#   [配置提示] 研究工作流配置检测
# ============================================================
#   缺失 [必须] DEEPSEEK_API_KEY — DeepSeek API Key（中文LLM调用，必需）
#   缺失 [推荐] TUSHARE_API_KEY — Tushare Pro API Key（A股数据）
#   ...
#   快速配置: python scripts/setup_wizard.py --guided
# ============================================================
```
