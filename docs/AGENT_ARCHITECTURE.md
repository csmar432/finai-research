# 经济类科研智能体工作流 — 架构文档

> 本文档描述重构后的四模块智能体架构。

## 整体架构

```
用户请求
    │
    ▼
ResearchSession（会话管理器）
    │
    ├── ResearchPlanner     ──→ 任务分解 + 拓扑排序
    ├── ResearchMemory     ──→ 三层记忆（上下文/短期/长期）
    ├── ToolSelector       ──→ 工具自主选择（MCP + Python脚本）
    └── ResearchReflector  ──→ 四维结果评估 + 反馈
           │
           ▼
    ToolSelector ──→ 执行工具
         ├── MCP 工具（ArXiv / financial / finviz-sec / brave-search 等）
         └── Python 脚本（data_pipeline / econometrics / literature_search 等）
```

## 四模块职责

### 1. ResearchMemory（记忆系统）

三层存储，支撑上下文理解和长期知识积累：

| 层 | 存储介质 | TTL | 用途 |
|---|---|---|---|
| Context | `list[ContextUnit]` | 会话内 | 填充 prompt，给 Planner/ToolSelector 参考 |
| Short-term | `deque[Operation]`（maxlen=20） | 会话内 | 最近 20 条操作记录 |
| Long-term | SQLite `research.db` | 永久 | 知识库、文献、结论，支持跨会话检索 |

核心接口：`push()` / `get_context()` / `store_knowledge()` / `retrieve()` / `compress_context()`

### 2. ResearchPlanner（任务规划器）

将用户请求分解为任务图，按依赖顺序执行：

```
用户请求
    │
    ▼
关键词/正则匹配 → TaskType 分类
    │
    ▼
子任务分解 + 依赖关系建立
    │
    ▼
Kahn 拓扑排序
    │
    ▼
执行队列（BLOCKED 任务等待依赖完成）
    │
    ▼
Fallback 策略（失败时）
  Level 1: 重试（< 3次）
  Level 2: 降级（关键任务）
  Level 3: 跳过（非关键任务）
  Level 4: 放弃（所有策略失败）
```

支持的分解模式：

| 模式 | TaskType | 子任务 |
|------|----------|--------|
| 写论文/大纲 | WRITING | 选题→大纲→章节→整合 |
| 分析财务/ROE | ANALYSIS + DATA_FETCH | 数据获取→指标计算→分析 |
| 文献检索+综述 | LITERATURE | 检索→下载→解析→综述 |
| 获取数据+画图 | DATA_FETCH + VISUALIZATION | 获取→特征工程→可视化 |
| 生成研报 | WRITING + ANALYSIS + DATA_FETCH | 检索→分析→写作 |
| 代码生成 | CODE | 需求澄清→代码→测试 |

### 3. ToolSelector（工具选择器）

注册所有可用工具，自主选择最优工具：

**选择策略：**
1. TaskType 匹配：筛选支持该任务类型的工具
2. VPN 可用性过滤：VPN 不可用时排除 `requires_vpn=True` 的工具
3. 排序：按 `priority` 升序 → `cost` 升序（FREE > LOW > MEDIUM > HIGH）
4. 置信度：首选工具 = 1.0，其他 = 0.8

**工具注册表：**

| 类型 | 工具名 | 用途 | 成本 | VPN |
|------|--------|------|------|-----|
| MCP | `arxiv` | 学术论文检索 | FREE | No |
| MCP | `financial` | 宏观经济/行情 | FREE | No |
| MCP | `finviz_sec` | 美股筛选/SEC文件 | FREE | No |
| MCP | `brave_search` | 财经新闻检索 | FREE | No |
| MCP | `fetch` | 网页正文抓取 | FREE | No |
| MCP | `eastmoney_reports` | 东方财富研报 | FREE | No |
| MCP | `context7` | API文档查询 | FREE | No |
| 脚本 | `fetch_a_stock` | A股日线数据 | FREE | No |
| 脚本 | `econometrics_regression` | OLS/DID回归 | FREE | No |
| 脚本 | `literature_search` | 文献检索→综述 | FREE | No |
| 脚本 | `paper_write` | 论文章节写作 | LOW | No |
| 脚本 | `report_generator` | 研报+可视化 | LOW | No |
| 脚本 | `llm_sentiment` | 批量情感分析 | LOW | Yes |

### 4. ResearchReflector（结果反馈器）

四维评估体系，量化任务完成质量：

| 维度 | 权重 | 检查内容 |
|------|------|----------|
| 完整性 | 35% | 结果字段是否齐全（按 TaskType 定义必要字段） |
| 准确性 | 35% | 数值范围检查（ROE/PE/营收增长率等） |
| 一致性 | 10% | 与历史结果对比（相同实体 >50% 变化→警告） |
| 置信度 | 20% | API 错误/空输出/低置信度 |

质量标记：`missing_data` / `outdated_data` / `low_confidence` / `inconsistent` / `incomplete_output` / `api_error` / `needs_verification`

**反馈循环：**
```
任务执行完成
    ↓
evaluate(task, result, context) → Evaluation
    ↓
score >= 0.7 → 成功，写入 Memory
score < 0.7 → 回退 Planner 重试（max 3次）
score < 0.3 → 放弃，通知用户
```

## ResearchSession（会话管理器）

统一入口，协调四个模块工作：

```python
from scripts.core.session import ResearchSession, SessionConfig

session = ResearchSession(SessionConfig(
    session_id="茅台财务分析",
    user_goal="分析茅台2024年财务数据并生成研报",
))
result = session.run("分析茅台2024年财务数据")
session.ask("再对比五粮液")  # 追问
session.save()  # 持久化
```

## 与现有脚本的关系

所有 18 个现有 Python 脚本作为 **工具能力** 被 `ToolSelector` 调用：

| 脚本 | ToolSelector 中的映射 | 用途 |
|------|----------------------|------|
| `data_pipeline.py` | `fetch_a_stock` | A股/美股数据获取 |
| `literature_search.py` | `literature_search` | 文献检索→综述 |
| `econometrics.py` | `econometrics_regression` | OLS/DID回归 |
| `paper_write.py` | `paper_write` | 论文章节写作 |
| `report_generator.py` | `report_generator` | 研报+图表 |
| `ai_router.py` | 外部 AI 路由 | B.AI / DeepSeek 调用 |
| 其他脚本 | 直接工具调用 | 各专项功能 |

## 扩展方式

### 添加新工具

在 `scripts/core/tool_selector.py` 的 `TOOL_REGISTRY_BASE` 中注册：

```python
"my_new_tool": ToolCapability(
    name="my_new_tool",
    task_types=[TaskType.ANALYSIS],
    inputs=["param1", "param2"],
    outputs=["result"],
    priority=2,
    cost=CostTier.FREE,
    requires_vpn=False,
    description="新工具描述",
)
```

### 添加新的评估规则

在 `scripts/core/reflector.py` 中修改 `_check_accuracy()` 的 `ACCURACY_RULES` 列表。

### 添加新的任务分解模式

在 `scripts/core/planner.py` 的 `decompose()` 方法中添加新的 `elif` 分支。
