# Tutorial 3: Research Directions System

> Learn how to use, browse, and extend the research directions framework.

---

## Overview

The research directions system (`scripts/research_directions/`) is a unified framework for multi-domain financial economics research. It provides:

- **Pre-built research templates** for 8 directions (carbon economics, green finance, macro finance, asset pricing, corporate finance, digital finance, and 2 YAML-defined directions)
- **Methodology chains** with econometric step-by-step guidance
- **Data acquisition strategies** via MCP tools
- **Auto-registration** — new directions register themselves automatically
- **Keyword search** — find directions by topic or research interest
- **LLM-based recommendation** — suggest directions from natural language descriptions

---

## Directory Structure

```
scripts/research_directions/
├── __init__.py           # Core: DirectionFactory, BaseResearchDirection, Registry
├── directions.yaml       # YAML-defined directions (carbon_trading, green_bond)
├── carbon_economics.py   # CarbonEconomicsDirection class
├── green_finance.py      # GreenFinanceDirection class
├── macro_finance.py      # MacroFinanceDirection class
├── asset_pricing.py      # AssetPricingDirection class
├── corporate_finance.py  # CorporateFinanceDirection class
└── digital_finance.py    # DigitalFinanceDirection class
```

---

## Listing Available Directions

### From the Command Line

```bash
python -m scripts.research_directions --list
```

### From Python

```python
from scripts.research_directions import DirectionFactory

# List all registered directions
all_directions = DirectionFactory.list_all()
for name in all_directions:
    print(f"  - {name}")
```

### Sample Output

```
Available Research Directions:
  - carbon_economics     (碳经济学)
  - green_finance        (绿色金融)
  - macro_finance        (宏观金融)
  - asset_pricing        (资产定价)
  - corporate_finance    (公司金融)
  - digital_finance     (数字金融)
  - carbon_trading       (碳交易试点效应)
  - green_bond           (绿色债券溢价)
```

---

## Searching Directions by Keyword

```python
from scripts.research_directions import DirectionFactory

# Search by keyword
results = DirectionFactory.search_directions("carbon emission")
for d in results:
    print(f"  [{d.slug}] {d.name}: {d.description}")

# Search multiple keywords
results = DirectionFactory.search_directions("ESG 绿色创新")
```

---

## Loading and Using a Direction

### Basic Usage

```python
from scripts.research_directions import DirectionFactory, get_registry

# Get a specific direction by slug
direction = DirectionFactory.get_direction("carbon_economics")

print(f"Name: {direction.name}")
print(f"Description: {direction.description}")
print(f"Policy events: {direction.policy_events}")

# Run the full pipeline: data -> panel -> regression -> tables
data = direction.fetch_data(topic="碳排放对企业创新的影响")
panel = direction.build_panel(data)
reg_results = direction.run_regressions(panel)
tables = direction.format_tables(reg_results)
figures = direction.get_figure_plan()

print(f"Regression status: {reg_results.get('status')}")
print(f"Tables: {list(tables.keys())}")
print(f"Figures: {[f['figure_id'] for f in figures]}")
```

### Using the Registry Directly

```python
from scripts.research_directions import get_registry

registry = get_registry()

# List all registered directions
for slug, direction in registry._registry.items():
    print(f"  {slug}: {direction.name}")
    print(f"    Keywords: {direction.keywords}")
    print(f"    Difficulty: {direction.difficulty}")
    print(f"    Methods: {[s.step_name for s in direction.methodology_chain.steps]}")
```

---

## Direction Details

### Python-Defined Directions

#### 1. Carbon Economics (`carbon_economics`)

**Research focus**: Carbon trading pilot effects, climate risk, green innovation incentives

**Policy events**:
- 2011: 发改委碳交易试点启动
- 2013: 北京/上海/深圳碳交易启动
- 2017: 全国碳交易市场启动
- 2021: 全国碳市场正式上线

**Data strategy**: Primary (CSMAR/Wind), Secondary (MCP macro), Last resort (ABORT)

**Methods**: DIDRegression, HeterogeneityAnalysis, PlaceboTest

```python
from scripts.research_directions import DirectionFactory

direction = DirectionFactory.get_direction("carbon_economics")
# Returns: CarbonEconomicsDirection
```

#### 2. Green Finance (`green_finance`)

**Research focus**: Green credit policy effects, ESG and financing constraints, green bond issuance

**Policy events**: 2012 银监会绿色信贷指引

**Data strategy**: Primary (Tushare), Secondary (MCP macro), Tertiary (CSMAR/Wind)

```python
direction = DirectionFactory.get_direction("green_finance")
# Returns: GreenFinanceDirection
```

#### 3. Macro Finance (`macro_finance`)

**Research focus**: Monetary policy transmission, bank competition, macro-financial linkages

**Policy events**: 2015 利率市场化改革完成, 2019 LPR改革, 2022 美联储加息周期

**Data strategy**: Primary (FRED via MCP), Secondary (EODHD), Tertiary (manual)

```python
direction = DirectionFactory.get_direction("macro_finance")
# Returns: MacroFinanceDirection
```

#### 4. Asset Pricing (`asset_pricing`)

**Research focus**: ESG factor and stock returns, carbon risk pricing, factor momentum

**Data strategy**: Primary (yfinance), Secondary (Tushare)

```python
direction = DirectionFactory.get_direction("asset_pricing")
# Returns: AssetPricingDirection
```

#### 5. Corporate Finance (`corporate_finance`)

**Research focus**: Capital structure adjustment speed, M&A performance, ESG and corporate decisions

**Policy events**: 2015 并购重组市场化改革, 2020 注册制改革

**Data strategy**: Primary (Tushare), Secondary (MCP macro)

```python
direction = DirectionFactory.get_direction("corporate_finance")
# Returns: CorporateFinanceDirection
```

#### 6. Digital Finance (`digital_finance`)

**Research focus**: Digital finance penetration, fintech competition, e-commerce and SME financing

**Policy events**: 2015 国务院推进互联网+行动, 2016 G20数字普惠金融原则

**Data strategy**: Primary (Tushare), Secondary (MCP macro), Tertiary (CSMAR)

```python
direction = DirectionFactory.get_direction("digital_finance")
# Returns: DigitalFinanceDirection
```

---

### YAML-Defined Directions

These directions are defined in `directions.yaml` and loaded lazily by `DirectionFactory._load_from_yaml()`.

#### 7. Carbon Trading (`carbon_trading`)

**Display name**: 碳交易试点效应

**Research theme**: 研究碳排放权交易试点政策对企业减排行为的影响

**Methodology chain**:
1. 断点回归设计 (RDD) — 以碳交易试点门槛设定为断点
2. 安慰剂检验 (PlaceboTest)
3. 异质性分析 — 按行业、规模、所有制分组

**Data requirements**: 企业排放数据、碳配额分配信息、CSMAR/Wind财务数据、国家知识产权局专利数据

**Keywords**: 碳交易, 碳排放权, RDD, 断点回归, 减排, 绿色创新

**Difficulty**: intermediate | Estimated pages: 35

```python
direction = DirectionFactory.get_direction("carbon_trading")
# Returns: ResearchDirection (from YAML)
```

#### 8. Green Bond (`green_bond`)

**Display name**: 绿色债券溢价

**Research theme**: 研究绿色债券相较于普通债券是否存在绿色溢价或认证溢价

**Methodology chain**:
1. 事件研究法 (Event Study) — 绿色债券发行公告日CAR
2. 利差分析 (OLSRegression)
3. 动态效应检验 (PanelRegression)

**Data requirements**: Wind/Thomson Reuters绿色债券数据、中债估值中心数据、公司年报

**Keywords**: 绿色债券, 信用利差, 认证溢价, 事件研究

**Difficulty**: intermediate | Estimated pages: 30

```python
direction = DirectionFactory.get_direction("green_bond")
# Returns: ResearchDirection (from YAML)
```

---

## Adding a New Research Direction

### Option 1: Python Class (Recommended for Complex Logic)

Create a new file in `scripts/research_directions/`:

```python
"""MyCustomDirection: Brief description.

Research focus:
    1. Topic one
    2. Topic two

Data strategy:
    - Primary: user-tushare (requires TUSHARE_TOKEN)
    - Secondary: user-financial (macro)
    - Last resort: ABORT with clear error
"""

from __future__ import annotations

from scripts.research_directions import (
    BaseResearchDirection,
    get_registry,
)


class MyCustomDirection(BaseResearchDirection):
    """Custom research direction."""

    name = "我的研究方向"
    slug = "my_custom"
    description = "研究方向描述"
    policy_events = [
        (2020, "政策事件名称"),
    ]

    def fetch_data(self, topic: str, **kwargs) -> dict | None:
        data = {}
        # Try MCP tools first
        result = self._fetch_via_mcp(
            "tushare", "get_stock_basic", {"list_status": "L"}
        )
        if result:
            data["stocks"] = result
        if not data:
            self._require_data_source("my_custom", allow_none=False)
            return None
        return data

    def build_panel(self, data: dict) -> dict | None:
        return {"df": data.get("stocks", []), "description": "..."}

    def run_regressions(self, panel: dict) -> dict:
        return {"status": "success", "tables": {}}

    def format_tables(self, reg_results: dict) -> dict[str, str]:
        return {}

    def get_figure_plan(self) -> list[dict]:
        return [
            {"figure_id": "Figure_1", "description": "...", "generation_method": "matplotlib"}
        ]


# Auto-register
get_registry().register(MyCustomDirection())
```

### Option 2: YAML Entry (Recommended for Standard Empirical)

Add an entry to `scripts/research_directions/directions.yaml`:

```yaml
my_direction:
  direction_name: my_direction
  display_name: 我的研究方向
  literature_theme: "研究X对Y的影响。"
  methodology_chain:
    steps:
      - step_name: 双重差分法 (DID)
        econometric_class: DIDRegression
        notes: 以某政策事件为外生冲击，构造处理组和对照组。
        data_needed: ["政策实施前后企业面板数据", "处理组/对照组标识"]
        packages: []
      - step_name: 稳健性检验
        econometric_class: RobustnessTest
        notes: 替换核心变量、改变样本范围、PSM倾向得分匹配。
        data_needed: ["替代变量数据"]
        packages: []
  data_requirements:
    面板数据: CSMAR上市公司数据
    政策数据: 政策文件整理
  expected_output: DID回归表、安慰剂检验、异质性分析。
  keywords: ["关键词1", "关键词2"]
  sub_topics: ["子主题1", "子主题2"]
  references:
    - "Author et al. (Year, Journal) — Title"
  difficulty: intermediate
  estimated_pages: 30
```

Then call `DirectionFactory._load_from_yaml()` to register it, or restart the process.

---

## MCP Data Integration

Each direction uses `_fetch_via_mcp()` to get real-time data:

```python
# Available MCP servers and tools per direction:
#
# user-tushare:
#   get_stock_basic, get_daily_quote, get_financial_report,
#   get_margin_data, get_index_data, get_concept_stocks
#
# user-financial:
#   get_macro_china (cpi, gdp, m2, pmi, ...),
#   get_macro_usa, get_macro_uk, get_macro_japan, get_wb_indicator
#
# user-eodhd:
#   get_ust_yield_rates, get_economic_events, get_economic_indicators
#
# user-yfinance:
#   get_ticker_info, get_stock_history, get_financial_data
```

---

## Next Steps

- [Tutorial 4: MCP Tool Marketplace](04-mcp-marketplace.md)
- [Tutorial 5: Event-Driven Research](05-event-driven-research.md)
- [API Reference: DirectionFactory](../api_reference.md#directionfactory)
