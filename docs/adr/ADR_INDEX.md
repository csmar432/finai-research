# ADR 同步状态

> 本文件记录所有 ADR（架构决策记录）的当前实现状态。
> 上次同步：2026-06-09

---

## ADR-001: 七层数据 Fallback 策略

**状态**: ✅ **已实现**

| 项目 | 状态 | 对应模块 |
|------|------|---------|
| 7层 Fallback 链 | ✅ | `scripts/research_framework/data_fetcher.py` → `CachedDataFetcher.fetch_with_fallback()` |
| 层级1: MCP Primary | ✅ | 41个 MCP 服务器 |
| 层级2: MCP Secondary (akshare) | ✅ | `user-financial` 等 |
| 层级3: CSMAR | ✅ | `user-csmar` |
| 层级4: Wind | ✅ | `user-wind` |
| 层级5: Manual File | ✅ | `data/user_uploaded/` |
| 层级6: Simulated Data（需授权） | ✅ | `scripts/research_framework/data_fetcher.py` 中的 `is_simulated_data` 标注 |
| 层级7: Abort with DataUnavailableError | ✅ | 异常类定义 |
| ProvenanceChain 数字溯源 | ✅ | `scripts/core/provenance.py` |
| 数字注入向量数据库 | ✅ | `scripts/core/provenance_rag.py` (v0.1.0) |

**实现说明**：所有数据获取必须经过 `CachedDataFetcher.fetch_with_fallback()` 方法。模拟数据会被标记，用户可见警告。

---

## ADR-002: ProvenanceChain 数据溯源设计

**状态**: ✅ **已实现**

| 项目 | 状态 | 对应模块 |
|------|------|---------|
| ProvenanceNode 数据结构 | ✅ | `scripts/core/provenance.py` |
| ProvenanceLink 边 | ✅ | `scripts/core/provenance.py` |
| Pipeline 版本追踪 | ✅ | `scripts/core/checkpoint.py` → `PipelineTelemetry` |
| 图表级 Provenance 报告 | ✅ | `ProvenanceChain.export_figure_provenance_report()` |
| 数字提取（8类）| ✅ | `scripts/core/provenance_rag.py` → `NumberExtractor` |
| ChromaDB 向量模式 | ✅ | `scripts/core/provenance_rag.py` → `ProvenanceRAG` |
| SQLite 回退模式 | ✅ | `scripts/core/provenance_rag.py` → `ProvenanceRAG` |
| 静默 Random Fallback 警告 | ✅ | v0.1.0 修复：`is_random_fallback` + `check_fallback_warning()` |

**实现说明**：v0.1.0 增加了 `provenance_rag.py`，支持对图表中的数字进行向量化溯源检索，并通过 `check_fallback_warning()` 消除静默 fallback。

---

## ADR-003: SEPL 自我进化协议

**状态**: ✅ **已实现**

| 项目 | 状态 | 对应模块 |
|------|------|---------|
| 四阶段循环 | ✅ | `scripts/core/self_evolution.py` → `SelfEvolutionEngine` |
| Propose → Optimize 循环 | ✅ | `run_evolution_cycle()` |
| Prompt 自动校准 | ✅ | `scripts/core/reviewer_calibrator.py` → `CalibratorFeedbackLoop` |
| Gate 校准 | ✅ | `scripts/core/evolution_gate.py` |
| 持久化 | ✅ | `scripts/core/self_evolution.py` → SQLite/JSON 持久化 |
| Hook 系统 | ✅ | `scripts/core/self_evolution.py` → `EvolutionHook` |
| 遥测 | ✅ | `scripts/core/checkpoint.py` → `PipelineTelemetry` |
| BiasHistoryDB 偏见趋势分析 | ✅ | `scripts/core/reviewer_calibrator.py` → `BiasHistoryDB` (v0.1.0) |
| PersistentCalibratorFeedbackLoop | ✅ | `scripts/core/reviewer_calibrator.py` (v0.1.0) |

**实现说明**：v0.1.0 新增了 `PersistentCalibratorFeedbackLoop` 和 `BiasHistoryDB`，使 SEPL 的 Optimize 阶段能够基于历史偏见数据进行自动 prompt 调整。

---

## ADR-004: HITL 人工审核门

**状态**: ✅ **已实现**

| 项目 | 状态 | 对应模块 |
|------|------|---------|
| HITL Gate 基础版 | ✅ | `scripts/core/hitl_gate.py` |
| HITL Gate 增强版（4种决策类型）| ✅ | `scripts/core/enhanced_hitl_gate.py` |
| 4种决策：approve/edit/reject/respond | ✅ | `enhanced_hitl_gate.py` → `DecisionType` |
| Command 结构 | ✅ | `enhanced_hitl_gate.py` → `HITLCommand` |
| 超时自动回退 | ✅ | `enhanced_hitl_gate.py` |
| CheckpointManager 集成 | ✅ | `scripts/core/checkpoint.py` |
| 自动评分规则 | ✅ | `scripts/core/auto_review_rules.py` (v0.1.0) |
| QualityGates 质量下限 | ✅ | `scripts/core/quality_gates.py` (v0.1.0) |

**实现说明**：v0.1.0 新增了 `QualityGates`（论文写作过程质量下限）和 `AutoReviewRules`（自动评分引擎），使 HITL 在人工审核前增加了自动质量门控层。

---

## ADR-005: MCP 工具市场架构

**状态**: ✅ **已实现**

| 项目 | 状态 | 对应模块 |
|------|------|---------|
| 工具注册表 | ✅ | `scripts/core/mcp_tool_market.py` → `ToolRegistry` |
| 动态注册 | ✅ | `ToolRegistry.register()` |
| 工具选择器 | ✅ | `scripts/core/tool_selector.py` |
| Schema 验证 | ✅ | `scripts/mcp_schema_check.py` (v0.1.0) |
| 41个 MCP 服务器 | ✅ | `mcp_servers/` |
| 216个工具 inputSchema.description | ✅ | 全部补全 (v0.1.0) |
| 工具 Capabilities | ✅ | `mcp_servers/*/tools/*.json` |

---

## 待实现的 ADR

暂无。已识别但未实现的特性为"实时协作"（`collaboration.py` + `presence_server.py` 存在但未集成），属大型工程，建议按需实现。

---

## 更新日志

- 2026-06-09: v0.1.0 更新，新增 QualityGates、AutoReviewRules；ADR-004 同步状态更新
- 2026-06-09: v0.1.0 更新，新增 provenance_rag.py、BiasHistoryDB、PersistentCalibratorFeedbackLoop；ADR-002/003 同步状态更新
