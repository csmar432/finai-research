# 经济类科研智能体工作流 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有脚本合集重构为真正的科研智能体，增加 Planner（任务规划）、Memory（记忆持久化）、ToolSelector（工具自主选择）、Reflection（结果反馈）四个核心模块，并清理 GitHub 上传障碍。

**Architecture:**

```
ResearchSession（会话管理器）
    │
    ├── Planner        → 任务分解 + 执行流 + 回退策略
    ├── Memory         → 短期会话 + 长期知识库（SQLite）
    ├── ToolSelector   → MCP工具路由 + 直接API路由
    └── Reflection     → 结果评估 + 成功判定 + 反馈写入Memory

现有18个脚本模块作为"工具能力"被 ToolSelector 调用：
    data_pipeline / literature_search / econometrics /
    review_layer / paper_write / paper_submit /
    report_generator / model_train / etc.
```

**Tech Stack:** Python 3.10+, SQLite3 (stdlib), Threading + Queue, json, dataclasses, re

**范围边界：**
- 新增：4个核心模块 + 1个会话管理 + 3个集成测试 + 完整文档
- 不改：现有18个脚本的功能逻辑（仅调整输入输出接口以适配新架构）
- 不含：量化回测模块（已明确移除）

---

## 文件结构（重构后）

```
scripts/
    core/                          # ★ 新增：核心智能体模块
    │   ├── __init__.py
    │   ├── session.py              # ResearchSession（会话管理器）
    │   ├── planner.py             # ResearchPlanner（任务规划器）
    │   ├── memory.py              # ResearchMemory（记忆系统）
    │   ├── tool_selector.py        # ToolSelector（工具选择器）
    │   └── reflector.py           # ResearchReflector（结果反馈器）
    │
    ├── agent.py                   # ★ 新增：统一入口（Agent主类）
    ├── ai_router.py               # 修改：适配 ToolSelector
    ├── data_pipeline.py           # 修改：adapter模式暴露工具能力
    ├── literature_search.py        # 修改：返回结构化结果
    ├── literature_manager.py       # 修改：对接 Memory 长期记忆
    ├── econometrics.py             # 修改：返回可评估结果
    ├── review_layer.py            # 修改：接受 planner 上下文
    ├── paper_write.py             # 修改：接受 session 状态
    ├── paper_full_pipeline.py      # 修改：重命名为 orchestrator.py
    ├── paper_submit.py             # 修改：接受 reflection 反馈
    ├── report_generator.py         # 修改：接受 tool_selector 结果
    ├── model_train.py              # 修改：接受 session 配置
    ├── generate_empirical_tables.py  # 修改：返回结构化结果
    ├── generate_docx_tables.py     # 修改：无变化（输出工具）
    ├── paper_reader.py             # 修改：无变化（数据工具）
    ├── paper_tools.py              # 修改：无变化（工具集）
    ├── paper_visualizer.py         # 修改：无变化（输出工具）
    ├── cleanup_paper_index.py      # 修改：无变化（维护工具）
    └── keychain_setup.py           # 修改：无变化（密钥工具）
```

---

## Task 1: ResearchMemory（记忆系统）

**Files:**
- Create: `scripts/core/memory.py`
- Create: `scripts/core/__init__.py`
- Modify: `scripts/literature_manager.py`（知识库持久化）
- Test: `scripts/core/test_memory.py`

**核心设计：**

| 层 | 存储 | TTL | 内容 |
|---|---|---|---|
| 上下文（Context） | `Memory.context` dict | 会话内 | 最近 N 条任务+结果 |
| 短期（Short-term） | `Memory.short_term` deque | 会话内 | 最近 20 条操作记录 |
| 长期（Long-term） | SQLite `research.db` | 永久 | 知识库、文献、发现、结论 |

**核心接口：**

```python
class ResearchMemory:
    def __init__(self, session_id: str, db_path: str = ".cache/research.db"):
        self.session_id = session_id
        self.context: list[ContextUnit] = []  # 当前会话上下文
        self.short_term: deque[Operation] = deque(maxlen=20)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def push(self, task: str, result: Any, metadata: dict):
        """记录任务执行结果到所有层"""

    def get_context(self, max_items: int = 10) -> list[ContextUnit]:
        """获取最近上下文，用于填充prompt"""

    def store_knowledge(self, key: str, value: Any, tags: list[str]):
        """存入长期知识库，标签检索"""

    def retrieve(self, query: str, tags: list[str] | None = None, limit: int = 5):
        """语义检索长期知识库"""

    def compress_context(self):
        """当 context 超长时，用 LLM 压缩摘要"""

    def save_session(self):
        """将会话状态序列化到磁盘"""

    @staticmethod
    def load_session(session_id: str, db_path: str = ".cache/research.db"):
        """恢复历史会话"""

class ContextUnit(NamedTuple):
    timestamp: float
    task: str
    result: Any
    evaluation: str | None  # Reflection 写入
    tools_used: list[str]
```

- [ ] **Step 1: 创建 `scripts/core/__init__.py`**

```python
from scripts.core.memory import ResearchMemory, ContextUnit
from scripts.core.session import ResearchSession
from scripts.core.planner import ResearchPlanner, Task, TaskStatus, TaskType
from scripts.core.tool_selector import ToolSelector, ToolResult
from scripts.core.reflector import ResearchReflector, Evaluation

__all__ = [
    "ResearchMemory", "ContextUnit",
    "ResearchSession",
    "ResearchPlanner", "Task", "TaskStatus", "TaskType",
    "ToolSelector", "ToolResult",
    "ResearchReflector", "Evaluation",
]
```

- [ ] **Step 2: 创建 `scripts/core/memory.py` — ResearchMemory 类**

实现：
1. `__init__`: 创建/连接 SQLite `research.db`，建表（contexts / knowledge / sessions）
2. `push()`: 写入 context + short_term，TTL 判断写入 long_term
3. `get_context()`: 返回最近 max_items 条，含 evaluation 字段（Reflection 后补填）
4. `store_knowledge()`: 存入 knowledge 表（key/value/tags/timestamp/session_id）
5. `retrieve()`: SQL LIKE 模糊匹配 tags + key/value
6. `compress_context()`: 当 context > 20 项时，调用 LLM 摘要压缩
7. `save_session()` / `load_session()`: JSON 序列化会话状态
8. `_init_db()`: 建表（if not exists）

建表 SQL：
```sql
CREATE TABLE IF NOT EXISTS contexts (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    timestamp REAL,
    task TEXT,
    result TEXT,       -- JSON serialized
    evaluation TEXT,
    tools_used TEXT,   -- JSON list
    UNIQUE(session_id, timestamp)
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    key TEXT,
    value TEXT,        -- JSON serialized
    tags TEXT,         -- JSON list
    timestamp REAL,
    UNIQUE(session_id, key)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL,
    updated_at REAL,
    state TEXT,        -- JSON serialized full state
    summary TEXT       -- 压缩后的会话摘要
);

CREATE INDEX IF NOT EXISTS idx_knowledge_tags ON knowledge(tags);
CREATE INDEX IF NOT EXISTS idx_contexts_session ON contexts(session_id);
```

- [ ] **Step 3: 修改 `scripts/literature_manager.py` — 对接 Memory**

在 `save_paper()` 中自动调用 `memory.store_knowledge(key=f"paper:{arxiv_id}", tags=["literature", "paper"])`。

在 `search_papers()` 结果中返回前，存入 `memory.short_term`。

- [ ] **Step 4: 创建 `scripts/core/test_memory.py`**

```python
import tempfile, shutil, os
from scripts.core.memory import ResearchMemory, ContextUnit

def test_memory_push_and_retrieve():
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        mem.push("分析茅台财务", {"revenue": 100}, {"tools": ["fetch_a_financial"]})
        ctx = mem.get_context(limit=1)
        assert len(ctx) == 1
        assert "茅台" in ctx[0].task
        mem.save_session()
        restored = ResearchMemory.load_session("test-session", db_path=db)
        assert len(restored.get_context()) == 1
    finally:
        shutil.rmtree(tmpdir)

def test_compress_context():
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        for i in range(25):
            mem.push(f"任务{i}", {"result": f"结果{i}"}, {"tools": ["test"]})
        assert len(mem.context) == 25
        mem.compress_context()
        assert len(mem.context) <= 3  # 压缩后不超过3条
    finally:
        shutil.rmtree(tmpdir)
```

- [ ] **Step 5: Commit**

```bash
git add scripts/core/memory.py scripts/core/__init__.py scripts/core/test_memory.py
git commit -m "feat(agent): add ResearchMemory with SQLite long-term knowledge store"
```

---

## Task 2: ResearchPlanner（任务规划器）

**Files:**
- Create: `scripts/core/planner.py`
- Test: `scripts/core/test_planner.py`

**核心设计：**

```python
class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    RETRY = "retry"

class TaskType(Enum):
    DATA_FETCH      = "data_fetch"      # 获取数据
    LITERATURE      = "literature"      # 文献检索
    ANALYSIS        = "analysis"         # 数据分析
    WRITING         = "writing"          # 论文/研报写作
    CODE            = "code"             # 代码生成
    VISUALIZATION   = "visualization"    # 图表生成
    REVIEW          = "review"           # 审稿/润色
    ORCHESTRATE     = "orchestrate"      # 组合任务

@dataclass
class Task:
    id: str
    description: str           # 原始任务描述
    task_type: TaskType
    status: TaskStatus
    subtasks: list[Task]
    dependencies: list[str]    # 依赖的 task.id 列表
    result: Any = None
    error: str | None = None
    retry_count: int = 0
    created_at: float
    finished_at: float | None = None

class ResearchPlanner:
    def __init__(self, memory: ResearchMemory):
        self.memory = memory
        self.tasks: dict[str, Task] = {}
        self._task_counter = 0

    def decompose(self, user_request: str) -> list[Task]:
        """
        将用户请求分解为任务图。
        返回根任务列表（主任务 + 子任务树）。
        """

    def execute(self, task_graph: list[Task]) -> dict[str, Any]:
        """
        按依赖顺序执行任务图。
        失败时触发回退策略。
        """

    def _fallback(self, failed_task: Task) -> Task | None:
        """
        回退策略：
        1. 重试（API临时失败）
        2. 降级（工具不可用）
        3. 跳过（非关键任务）
        4. 放弃（关键任务失败）
        """
```

**分解规则（基于关键词+正则）：**

| 模式 | 任务类型 | 子任务生成 |
|---|---|---|
| 写论文/设计大纲 | `WRITING` | 选题→大纲→各章节→整合 |
| 分析财务/ROE | `ANALYSIS` + `DATA_FETCH` | 数据获取→指标计算→分析 |
| 文献检索+综述 | `LITERATURE` | 检索→下载→解析→综述 |
| 获取数据+画图 | `DATA_FETCH` + `VISUALIZATION` | 获取→特征工程→可视化 |
| 生成研报 | `WRITING` + `ANALYSIS` + `DATA_FETCH` | 检索→分析→写作 |
| 代码生成 | `CODE` | 需求澄清→代码→测试 |

**执行引擎（拓扑排序）：**

```python
def execute(self, task_graph: list[Task]) -> dict[str, Any]:
    # 1. 拓扑排序（ Kahn 算法）
    # 2. 按序执行，dependencies 未完成则 BLOCKED
    # 3. 子任务失败 → 调用 _fallback()
    # 4. 结果写入 memory.push()
    # 5. 返回 {task_id: result}
```

- [ ] **Step 1: 创建 `scripts/core/planner.py`**

实现 `ResearchPlanner` 类：
1. `decompose()` — 关键词规则 + 正则匹配 → Task 列表 + 依赖关系
2. `execute()` — 拓扑排序执行引擎
3. `_fallback()` — 4级回退策略（重试/降级/跳过/放弃）
4. `get_status()` — 返回任务图状态摘要
5. `_estimate_task_type()` — 根据关键词推断 TaskType

- [ ] **Step 2: 创建 `scripts/core/test_planner.py`**

```python
from scripts.core.planner import ResearchPlanner, TaskType, TaskStatus
from scripts.core.memory import ResearchMemory
import tempfile, os

def test_decompose_paper():
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("帮我写一篇深度学习量化交易的论文，目标NeurIPS")
    assert len(tasks) >= 3
    assert any(t.task_type == TaskType.WRITING for t in tasks)

def test_decompose_analysis():
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("分析苹果公司2024年的ROE和毛利率")
    assert any(t.task_type == TaskType.DATA_FETCH for t in tasks)
    assert any(t.task_type == TaskType.ANALYSIS for t in tasks)

def test_topological_order():
    mem = ResearchMemory("test", db_path=":memory:")
    planner = ResearchPlanner(mem)
    tasks = planner.decompose("检索文献并写综述")
    # DATA_FETCH 依赖 LITERATURE 的输出
    lit_task = next(t for t in tasks if t.task_type == TaskType.LITERATURE)
    fetch_task = next(t for t in tasks if t.task_type == TaskType.DATA_FETCH)
    assert fetch_task.id in [d for d in lit_task.dependencies]
```

- [ ] **Step 3: Commit**

```bash
git add scripts/core/planner.py scripts/core/test_planner.py
git commit -m "feat(agent): add ResearchPlanner with task decomposition and fallback"
```

---

## Task 3: ToolSelector（工具选择器）

**Files:**
- Create: `scripts/core/tool_selector.py`
- Create: `scripts/core/test_tool_selector.py`

**核心设计：**

```python
@dataclass
class ToolCapability:
    name: str
    task_types: list[TaskType]  # 能处理的TaskType
    inputs: list[str]            # 需要的输入字段
    outputs: list[str]           # 产出的输出字段
    priority: int                 # 优先级（数字越小优先级越高）
    cost: str                    # "free" | "low" | "medium" | "high"
    requires_vpn: bool
    description: str

class ToolSelector:
    TOOL_REGISTRY: dict[str, ToolCapability] = {
        # MCP 工具
        "arxiv": ToolCapability(
            name="arxiv", task_types=[TaskType.LITERATURE, TaskType.DATA_FETCH],
            inputs=["query", "max_results"],
            outputs=["papers"],
            priority=1, cost="free", requires_vpn=False,
            description="ArXiv论文检索和下载"
        ),
        "financial": ToolCapability(
            name="financial", task_types=[TaskType.DATA_FETCH],
            inputs=["ticker", "data_type"],
            outputs=["price", "fundamentals", "macro"],
            priority=1, cost="free", requires_vpn=False,
            description="宏观经济、行情、crypto（yfinance/FRED）"
        ),
        "finviz_sec": ToolCapability(
            name="finviz_sec", task_types=[TaskType.DATA_FETCH, TaskType.ANALYSIS],
            inputs=["ticker", "action"],
            outputs=["screening", "fundamentals", "sec_filings"],
            priority=1, cost="free", requires_vpn=False,
            description="美股筛选、90+基本面、SEC文件"
        ),
        "brave_search": ToolCapability(
            name="brave_search", task_types=[TaskType.LITERATURE, TaskType.DATA_FETCH],
            inputs=["query"],
            outputs=["search_results"],
            priority=2, cost="free", requires_vpn=False,
            description="财经新闻、政策文件网络检索"
        ),
        "fetch": ToolCapability(
            name="fetch", task_types=[TaskType.DATA_FETCH],
            inputs=["url"],
            outputs=["content"],
            priority=3, cost="free", requires_vpn=False,
            description="网页正文抓取"
        ),
        "eastmoney_reports": ToolCapability(
            name="eastmoney_reports", task_types=[TaskType.DATA_FETCH, TaskType.LITERATURE],
            inputs=["query", "industry"],
            outputs=["research_reports"],
            priority=2, cost="free", requires_vpn=False,
            description="东方财富研报"
        ),
        "context7": ToolCapability(
            name="context7", task_types=[TaskType.CODE],
            inputs=["library", "query"],
            outputs=["documentation"],
            priority=1, cost="free", requires_vpn=False,
            description="官方API文档查询"
        ),
        # Python 脚本工具
        "fetch_a_stock": ToolCapability(
            name="fetch_a_stock", task_types=[TaskType.DATA_FETCH],
            inputs=["code", "start_date", "end_date"],
            outputs=["df"],
            priority=1, cost="free", requires_vpn=False,
            description="A股日线数据（akshare）"
        ),
        "econometrics_regression": ToolCapability(
            name="econometrics_regression", task_types=[TaskType.ANALYSIS],
            inputs=["df", "formula", "cluster"],
            outputs=["results", "table"],
            priority=1, cost="free", requires_vpn=False,
            description="OLS/DID回归（statsmodels）"
        ),
        "literature_search": ToolCapability(
            name="literature_search", task_types=[TaskType.LITERATURE],
            inputs=["query", "max_results"],
            outputs=["papers", "review"],
            priority=1, cost="free", requires_vpn=False,
            description="文献检索→下载→综述"
        ),
        "paper_write": ToolCapability(
            name="paper_write", task_types=[TaskType.WRITING],
            inputs=["topic", "section", "outline"],
            outputs=["content"],
            priority=1, cost="low", requires_vpn=False,
            description="论文章节写作（调用LLM）"
        ),
        "report_generator": ToolCapability(
            name="report_generator", task_types=[TaskType.WRITING, TaskType.VISUALIZATION],
            inputs=["company", "data", "format"],
            outputs=["report", "charts"],
            priority=1, cost="low", requires_vpn=False,
            description="研报生成+可视化图表"
        ),
        "llm_sentiment": ToolCapability(
            name="llm_sentiment", task_types=[TaskType.ANALYSIS],
            inputs=["texts"],
            outputs=["sentiments"],
            priority=2, cost="low", requires_vpn=True,
            description="批量情感分析（LLMProcessor）"
        ),
    }

    def __init__(self, memory: ResearchMemory):
        self.memory = memory
        self._mcp_available: dict[str, bool] = {}
        self._script_available: dict[str, bool] = {}

    def select(self, task: Task, context: list[ContextUnit]) -> list[ToolSelection]:
        """
        根据任务类型和上下文选择最佳工具链。
        返回优先级排序的工具列表。
        """

    def execute(self, selection: ToolSelection, inputs: dict) -> ToolResult:
        """
        执行选中的工具，返回结构化结果。
        失败时触发 fallback 到下一优先级工具。
        """

    def _call_mcp(self, tool_name: str, params: dict) -> Any:
        """通过 MCP 协议调用工具"""

    def _call_script(self, tool_name: str, params: dict) -> Any:
        """通过 scripts/ 调用 Python 脚本工具"""

    def _check_availability(self):
        """启动时检查所有工具可用性，结果缓存"""
```

**选择策略：**

1. **TaskType → 工具候选集**：从 `TOOL_REGISTRY` 中筛选 `task_types` 匹配的
2. **上下文过滤**：检查前置任务产出是否满足 `inputs` 要求
3. **VPN 可用性**：标记 `requires_vpn=False` 优先
4. **成本排序**：free > low > medium > high
5. **优先级排序**：同类型按 `priority` 升序

- [ ] **Step 1: 创建 `scripts/core/tool_selector.py`**

实现 `ToolSelector` 类 + `ToolCapability` 数据类：
1. `TOOL_REGISTRY` 静态注册表
2. `select()` — 筛选 → 排序 → 返回 `list[ToolSelection]`
3. `execute()` — 执行首选 + fallback 链
4. `_call_mcp()` — subprocess 调用 MCP CLI（`/opt/anaconda3/bin/finviz-sec-mcp` 等）
5. `_call_script()` — importlib 动态导入 + 函数调用
6. `_check_availability()` — 启动时 ping 所有工具

- [ ] **Step 2: 创建 `scripts/core/test_tool_selector.py`**

```python
from scripts.core.tool_selector import ToolSelector, ToolCapability, TaskType
from scripts.core.memory import ResearchMemory

def test_select_for_data_fetch():
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    from scripts.core.planner import Task
    task = Task(id="t1", description="获取苹果股价", task_type=TaskType.DATA_FETCH,
                status=None, subtasks=[], dependencies=[], created_at=0)
    selections = selector.select(task, [])
    assert len(selections) >= 1
    assert any(s.tool_name in ("financial", "finviz_sec", "fetch_a_stock") for s in selections)

def test_select_for_literature():
    mem = ResearchMemory("test", db_path=":memory:")
    selector = ToolSelector(mem)
    from scripts.core.planner import Task
    task = Task(id="t2", description="检索深度学习量化交易文献",
                task_type=TaskType.LITERATURE,
                status=None, subtasks=[], dependencies=[], created_at=0)
    selections = selector.select(task, [])
    assert any(s.tool_name in ("arxiv", "literature_search", "brave_search") for s in selections)
```

- [ ] **Step 3: Commit**

```bash
git add scripts/core/tool_selector.py scripts/core/test_tool_selector.py
git commit -m "feat(agent): add ToolSelector with MCP and script tool registry"
```

---

## Task 4: ResearchReflector（结果反馈器）

**Files:**
- Create: `scripts/core/reflector.py`
- Create: `scripts/core/test_reflector.py`

**核心设计：**

```python
@dataclass
class Evaluation:
    task_id: str
    success: bool
    score: float              # 0.0–1.0
    feedback: str             # 自然语言反馈
    suggestions: list[str]    # 改进建议
    quality_flags: list[str]  # ["low_confidence", "missing_data", "incomplete"]
    timestamp: float

class ResearchReflector:
    def __init__(self, memory: ResearchMemory):
        self.memory = memory
        self._llm = None  # 延迟初始化

    def evaluate(self, task: Task, result: Any, context: list[ContextUnit]) -> Evaluation:
        """
        评估任务执行结果，返回 Evaluation 对象。
        """

    def reflect(self, session: ResearchSession) -> str:
        """
        会话结束时的整体反思，返回改进建议摘要。
        """

    def _check_completeness(self, task: Task, result: Any) -> tuple[bool, str]:
        """检查结果完整性"""

    def _check_accuracy(self, task: Task, result: Any) -> tuple[bool, str]:
        """检查结果准确性（基于领域规则）"""

    def _check_consistency(self, task: Task, result: Any, context: list[ContextUnit]) -> tuple[bool, str]:
        """检查与历史结果的一致性"""

    def _infer_quality_flags(self, task: Task, result: Any) -> list[str]:
        """推断质量标记"""
```

**评估维度：**

| 维度 | 检查方法 | 阈值 |
|---|---|---|
| 完整性 | 结果字段是否齐全 | 缺失 > 30% → fail |
| 准确性 | 数值范围检查、逻辑一致性 | 超出合理范围 → warn |
| 一致性 | 与 memory 中历史结果对比 | 矛盾 → warn |
| 数据新鲜度 | 数据截止日期 | 超过 30 天 → warn |
| 置信度 | LLM 返回的置信标记 | 低置信 → suggest retry |

**质量标记（Quality Flags）：**

```python
QUALITY_FLAGS = {
    "missing_data": "关键数据缺失",
    "outdated_data": "数据超过30天未更新",
    "low_confidence": "LLM置信度低于0.7",
    "inconsistent": "与历史结果矛盾",
    "incomplete_output": "输出不完整",
    "api_error": "API调用失败",
    "needs_verification": "建议人工核查",
}
```

**反馈循环流程：**

```
任务执行完成
    ↓
Reflection.evaluate(task, result, context)
    ↓
Evaluation(score, quality_flags)
    ↓
┌─ score >= 0.7 → 写入 Memory.context（evaluation=feedback）
├─ score < 0.7 且可修复 → 回退 Planner 重试（max 3次）
├─ score < 0.3 → 放弃，标记 BLOCKED，通知用户
└─ quality_flags 包含 inconsistency → 追加验证步骤
```

- [ ] **Step 1: 创建 `scripts/core/reflector.py`**

实现 `ResearchReflector` 类 + `Evaluation` 数据类：
1. `evaluate()` — 完整性 → 准确性 → 一致性 → 置信度，四维评估
2. `_check_completeness()` — 按 task_type 检查必要字段
3. `_check_accuracy()` — 数值合理性（ROE 0-100%、PE > 0 等）
4. `_check_consistency()` — 查 memory 中同一实体的历史值
5. `_infer_quality_flags()` — 规则推断 + LLM 辅助判断
6. `reflect()` — 汇总全会话所有 evaluation，生成改进建议

- [ ] **Step 2: 创建 `scripts/core/test_reflector.py`**

```python
from scripts.core.reflector import ResearchReflector, Evaluation
from scripts.core.memory import ResearchMemory
from scripts.core.planner import Task, TaskType, TaskStatus

def test_evaluate_financial_data():
    mem = ResearchMemory("test", db_path=":memory:")
    reflector = ResearchReflector(mem)
    task = Task(id="t1", description="分析茅台ROE",
                task_type=TaskType.ANALYSIS, status=TaskStatus.DONE,
                subtasks=[], dependencies=[], created_at=0)
    result = {"roe": 25.3, "revenue_growth": 15.2, "data_source": "akshare"}
    eval_result = reflector.evaluate(task, result, [])
    assert eval_result.success is True
    assert eval_result.score >= 0.7

def test_evaluate_incomplete_result():
    mem = ResearchMemory("test", db_path=":memory:")
    reflector = ResearchReflector(mem)
    task = Task(id="t2", description="获取财报",
                task_type=TaskType.DATA_FETCH, status=TaskStatus.DONE,
                subtasks=[], dependencies=[], created_at=0)
    result = {"revenue": None}  # 缺失关键字段
    eval_result = reflector.evaluate(task, result, [])
    assert "missing_data" in eval_result.quality_flags

def test_quality_flag_inconsistency():
    mem = ResearchMemory("test", db_path=":memory:")
    mem.push("分析苹果PE", {"pe": 25.0}, {"tools": ["financial"]})
    reflector = ResearchReflector(mem)
    task = Task(id="t3", description="再次分析苹果PE",
                task_type=TaskType.ANALYSIS, status=TaskStatus.DONE,
                subtasks=[], dependencies=[], created_at=0)
    result = {"pe": 150.0}  # 与历史 25.0 严重不一致
    eval_result = reflector.evaluate(task, result, mem.get_context())
    assert "inconsistent" in eval_result.quality_flags
```

- [ ] **Step 3: Commit**

```bash
git add scripts/core/reflector.py scripts/core/test_reflector.py
git commit -m "feat(agent): add ResearchReflector with four-dimensional evaluation"
```

---

## Task 5: ResearchSession（会话管理器）

**Files:**
- Create: `scripts/core/session.py`
- Modify: `scripts/core/memory.py`（补充 session 状态序列化）
- Test: `scripts/core/test_session.py`

**核心设计：**

```python
@dataclass
class SessionConfig:
    session_id: str
    user_goal: str                    # 用户原始目标
    workspace_root: Path
    auto_save: bool = True
    max_context_items: int = 20
    max_retries: int = 3
    model: str = "cursor"             # cursor | deepseek | b_ai
    verbose: bool = False

class ResearchSession:
    """
    会话管理器，串联四个核心模块。
    用户的主入口类。
    """
    def __init__(self, config: SessionConfig):
        self.config = config
        self.memory = ResearchMemory(config.session_id)
        self.planner = ResearchPlanner(self.memory)
        self.tool_selector = ToolSelector(self.memory)
        self.reflector = ResearchReflector(self.memory)
        self._task_results: dict[str, Any] = {}

    def run(self, user_request: str) -> dict[str, Any]:
        """
        主流程：
        1. Planner.decompose(user_request)
        2. 按拓扑序执行每个 Task
           └─ ToolSelector.select() → ToolSelector.execute()
           └─ Reflection.evaluate() → feedback
           └─ Memory.push(task, result, evaluation)
           └─ Planner._fallback()（如失败）
        3. 返回全任务结果
        """

    def ask(self, followup: str) -> str:
        """
        追问/补充指令，在当前会话状态上继续。
        """

    def status(self) -> SessionStatus:
        """返回当前会话状态（进行中/完成/失败）"""

    def save(self):
        """手动保存会话"""

    @staticmethod
    def resume(session_id: str) -> ResearchSession:
        """恢复历史会话"""
```

**交互模式：**

```python
# 方式1：完整会话
session = ResearchSession(SessionConfig(
    session_id="茅台财务分析_20260523",
    user_goal="分析贵州茅台2024年财务数据和投资价值"
))
result = session.run("帮我分析")
print(result["summary"])

# 方式2：追问
followup = session.ask("再对比一下五粮液")
print(followup)

# 方式3：恢复
old = ResearchSession.resume("茅台财务分析_20260523")
```

- [ ] **Step 1: 创建 `scripts/core/session.py`**

实现 `ResearchSession`：
1. `__init__()` — 初始化四个模块 + 会话配置
2. `run()` — 主流程：decompose → execute → evaluate → push → fallback
3. `ask()` — 在当前会话上追加任务（理解 followup 与主目标的关联）
4. `status()` — 返回 `SessionStatus` 枚举
5. `save()` / `resume()` — 持久化接口

- [ ] **Step 2: 补充 `scripts/core/memory.py` 的序列化**

在 `ResearchMemory` 中补充：
```python
def to_dict(self) -> dict: ...
def from_dict(cls, data: dict) -> ResearchMemory: ...
```

- [ ] **Step 3: 创建 `scripts/core/test_session.py`**

```python
from scripts.core.session import ResearchSession, SessionConfig
from scripts.core.planner import TaskType

def test_end_to_end_session():
    config = SessionConfig(
        session_id="test-session",
        user_goal="分析苹果公司财务数据",
        workspace_root=Path("."),
    )
    session = ResearchSession(config)
    # Mock ToolSelector to avoid real API calls
    import scripts.core.tool_selector as ts
    orig_select = ts.ToolSelector.select
    ts.ToolSelector.select = lambda self, task, ctx: []
    try:
        result = session.run("分析苹果公司财务数据")
        assert "tasks" in result
        assert session.status().state == "completed"
    finally:
        ts.ToolSelector.select = orig_select

def test_resume_session():
    config = SessionConfig(session_id="resume-test", user_goal="test")
    session = ResearchSession(config)
    session.run("test task")
    session.save()
    restored = ResearchSession.resume("resume-test")
    assert len(restored.memory.get_context()) > 0
```

- [ ] **Step 4: Commit**

```bash
git add scripts/core/session.py
git commit -m "feat(agent): add ResearchSession orchestrating all four modules"
```

---

## Task 6: Agent 统一入口

**Files:**
- Create: `scripts/agent.py`
- Modify: `scripts/ai_router.py`（适配 ToolSelector）
- Modify: `scripts/data_pipeline.py`（adapter 模式暴露工具能力）

- [ ] **Step 1: 创建 `scripts/agent.py`**

```python
#!/usr/bin/env python3
"""
科研智能体统一入口
==================
Usage:
    python scripts/agent.py                    # 交互模式
    python scripts/agent.py --session "会话ID"  # 指定会话
    python scripts/agent.py --resume          # 恢复上次会话
    python scripts/agent.py --status         # 查看所有会话状态
"""

import argparse
from pathlib import Path
from scripts.core.session import ResearchSession, SessionConfig

def main():
    parser = argparse.ArgumentParser(description="经济类科研智能体")
    parser.add_argument("--session", "-s", type=str, help="会话ID")
    parser.add_argument("--resume", "-r", action="store_true", help="恢复上次会话")
    parser.add_argument("--status", action="store_true", help="查看会话状态")
    parser.add_argument("--goal", "-g", type=str, help="直接指定研究目标")
    args = parser.parse_args()

    if args.status:
        from scripts.core.memory import ResearchMemory
        # 列出所有会话
        ...

    if args.resume:
        # 读取最近会话 ID
        ...

    if args.goal:
        session_id = args.session or f"session_{datetime.now().strftime('%Y%m%d_%H%M')}"
        config = SessionConfig(
            session_id=session_id,
            user_goal=args.goal,
            workspace_root=Path("."),
        )
        session = ResearchSession(config)
        result = session.run(args.goal)
        print(result["summary"])

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 修改 `scripts/ai_router.py`**

将 `LLMBridge._get_model_name()` 中的模型名映射与 `ToolSelector` 的工具能力对齐。无需大改，仅确认路径兼容。

- [ ] **Step 3: Commit**

```bash
git add scripts/agent.py scripts/ai_router.py scripts/data_pipeline.py
git commit -m "feat(agent): add unified agent entry point and adapter integrations"
```

---

## Task 7: GitHub 上传前清理

**Files:**
- Modify: `.gitignore`
- Create: `LICENSE`（MIT）
- Create: `CONTRIBUTING.md`
- Create: `.github/workflows/ci.yml`
- Check: `.env.example`（确认无真实Key）

**清理检查清单：**

- [ ] **Step 1: 检查真实 Key 是否还在代码中**

```bash
cd /Users/xuzheyi/Desktop/论文-研报工作流
rg "sk-[a-zA-Z0-9]{32,}" --hidden -l 2>/dev/null
rg "sk-proj-[a-zA-Z0-9_-]{40,}" --hidden -l 2>/dev/null
```

如果有任何匹配，这些文件需要清理。

- [ ] **Step 2: 确认 `.gitignore` 覆盖所有敏感文件**

```bash
cat .gitignore
# 确认包含：
# .env
# .env.local
# .cache/
# .venv/
# __pycache__/
# scripts/core/test_*.py（测试文件不提交）
```

- [ ] **Step 3: 创建 `LICENSE`（MIT）**

```bash
# 在项目根目录创建 MIT LICENSE
```

- [ ] **Step 4: 创建 `.github/workflows/ci.yml`**

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest scripts/core/test_memory.py -v
          pytest scripts/core/test_planner.py -v
          pytest scripts/core/test_tool_selector.py -v
          pytest scripts/core/test_reflector.py -v
          pytest scripts/core/test_session.py -v
      - name: Lint
        run: ruff check scripts/core/
```

- [ ] **Step 5: 创建 `CONTRIBUTING.md`**

简要说明 PR 流程、测试要求、代码风格。

- [ ] **Step 6: 初始 commit**

```bash
git add -A
git commit -m "feat: initial commit — economic research agent framework

Add four core agent modules:
- ResearchMemory: SQLite-backed knowledge store
- ResearchPlanner: task decomposition with fallback
- ToolSelector: MCP + script tool routing
- ResearchReflector: four-dimensional result evaluation

And unified ResearchSession orchestrator.

Includes: 18 existing scripts (10452 lines) adapted as tool capabilities."
```

---

## Task 8: 集成测试与文档

**Files:**
- Create: `scripts/core/test_integration.py`
- Create: `docs/AGENT_ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `QUICKSTART.md`

- [ ] **Step 1: 创建 `scripts/core/test_integration.py`**

端到端集成测试：完整模拟一个研究会话（无真实API调用，用mock）

```python
def test_full_research_session():
    """模拟完整研究会话：文献检索 → 分析 → 写作"""
    # Mock 所有外部调用
    # 验证：Planner → ToolSelector → Memory → Reflection 全链路
```

- [ ] **Step 2: 创建 `docs/AGENT_ARCHITECTURE.md`**

文档内容：
1. 架构图（ASCII art）
2. 四个模块详细说明
3. 模块间交互流程
4. 扩展方式（如何添加新工具/新评估规则）
5. 与现有18个脚本的关系

- [ ] **Step 3: 更新 `README.md`**

新增：
1. 四模块架构图
2. Agent 使用示例（3个代码示例）
3. "Architecture" 章节链接到 `docs/AGENT_ARCHITECTURE.md`

- [ ] **Step 4: 更新 `QUICKSTART.md`**

新增 Agent 使用章节：
```python
from scripts.agent import ResearchSession, SessionConfig
session = ResearchSession(SessionConfig(
    session_id="我的研究",
    user_goal="分析茅台财务数据并写研报"
))
result = session.run("分析茅台财务数据")
```

---

## 实施顺序与依赖

```
Task 1 (Memory)     ──┐
Task 2 (Planner)     ──┤── 先并行实现（无依赖）
Task 3 (ToolSelector) ──┤
Task 4 (Reflection)   ──┘
        │
        └─────────────→ Task 5 (Session) ──→ Task 6 (Agent) ──→ Task 7 (GitHub) ──→ Task 8 (Docs)
```

---

## Self-Review 检查

**Spec 覆盖检查：**

| Spec 要求 | 对应 Task |
|---|---|
| Planner（任务分解+执行顺序） | Task 2 ✅ |
| Memory（记忆持久化） | Task 1 ✅ |
| ToolSelector（工具自主选择） | Task 3 ✅ |
| Reflection（结果反馈） | Task 4 ✅ |
| 会话管理（状态持久化） | Task 5 ✅ |
| 统一 Agent 入口 | Task 6 ✅ |
| GitHub 上传（Key清理+LICENSE） | Task 7 ✅ |
| 文档更新 | Task 8 ✅ |
| 移除量化回测 | ❌ 未包含 — 需要额外 Task 9 |
| 统计检验封装 | ❌ 未包含 — 需在 Task 1-3 中补充到 econometrics.py |

**占位符扫描：** 无"TBD"、"TODO"（除注释中的"待实现"说明外）

**类型一致性：** 所有 dataclass 字段在所有文件中一致使用

**额外发现：**
- `tariff_research/` 子项目应确认是否纳入主 repo（建议排除，单独 repo）
- `.cache/` 目录应加入 `.gitignore`
- 测试文件 `scripts/core/test_*.py` 应在 `.gitignore` 中排除或单独 `tests/` 目录

---

**Plan complete and saved to `docs/plans/2026-05-23-agent-workflow.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch one subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks sequentially in this session using executing-plans

Which approach?
