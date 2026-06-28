# Mock Data Policy（模拟数据策略）

> **版本**: 2026-06-28 · **影响范围**: 5 个 MCP 服务器
> **生效条件**: 默认（用户无需配置）

---

## 背景

2026-06-28 深度审计发现 5 个 MCP 服务器返回的是**模拟/硬编码/公开数据快照**，而非实时 API 数据。存在科研诚信风险：

| 服务器 | 风险等级 | 数据来源 |
|---|---|---|
| `user_nber_wp` | 🔴 高 | **编造的 paper_id**（w32456/w32098/w31567）+ 硬编码引用计数 |
| `user_bea_data` | 🔴 高 | 硬编码 GDP（$27.36T），无论 `year` 参数 |
| `user_csmar` | 🟡 中 | 文件头自承认"提供模拟数据用于演示" |
| `user_wuhan_stats` | 🟡 中 | 武汉市统计局公开年度报告的**数据快照**（非实时 API）|
| `user_macro_datas` | 🟡 中 | 马克数据网/科技部公报的**数据快照**（非实时 API）|

---

## 默认行为（Default）

**所有这 5 个服务器默认 `MCP_MOCK_MODE=disabled`**。

调用任何 mock 工具会返回：

```json
{
  "error": "[user-nber-wp] 模拟数据已被禁用（默认模式; 设置 MCP_MOCK_MODE=allow 临时启用）",
  "tool": "handle_search",
  "status": "disabled",
  "default_mode_reason": "P0 科研诚信修复 2026-06-28: 默认禁用所有模拟数据，避免用户基于伪造数据发表错误结论",
  "to_enable_temporarily": "MCP_MOCK_MODE=allow",
  "data_source": "MOCK_DISABLED"
}
```

---

## 三种模式

通过环境变量 `MCP_MOCK_MODE` 控制：

| 模式 | 行为 | 适用场景 |
|---|---|---|
| `disabled` (默认) | **拒绝执行**，返回错误 | 生产研究、论文写作、任何拟发表输出 |
| `confirm` | 返回确认提示，要求 LLM 在请求中含批准关键词（"确认"、"confirm" 等）| LLM agent 自动交互场景 |
| `allow` | 直接通过，无任何提示 | 演示、UI 测试、教学 |

设置示例：

```bash
# 演示场景
export MCP_MOCK_MODE=allow
python scripts/agent_pipeline.py --topic "..."

# 生产研究（默认）
unset MCP_MOCK_MODE
python scripts/agent_pipeline.py --topic "..."
```

---

## 何时**禁止**使用 Mock 数据

| 场景 | 允许 mock？ |
|---|---|
| 演示 pipeline 流程 | ✅ 允许（`MCP_MOCK_MODE=allow`）|
| 教学示例 | ✅ 允许 |
| 单元测试 | ✅ 允许 |
| **论文写作 / 拟发表输出** | ❌ **禁止** |
| **实证研究回归** | ❌ **禁止** |
| **正式数据获取** | ❌ **禁止** |

---

## 替代方案

如果需要这些服务器的真实数据：

| 需求 | 替代服务器 |
|---|---|
| NBER 工作论文 | `user_openalex`, `user-arxiv`, `user-semantic-scholar` |
| 美国 GDP / BEA 数据 | `user-fed-data`, `user-bea-data` (需 BEA_API_KEY)|
| CSMAR 中国上市公司数据 | `user-csmar` (需机构账号 CSMAR_API_KEY)|
| 中国省/市统计 | `user-province-stats`, `user-hubei-stats`, `user-wuhan-stats` (公开年报快照) |

---

## 修复历史

| 日期 | 修复 |
|---|---|
| 2026-06-28 | 默认 MCP_MOCK_MODE 从 `confirm` 改为 `disabled` |
| 2026-06-28 | `user_wuhan_stats` 和 `user_macro_datas` 新增 `check_mock_permission` 拦截 |
| 2026-06-28 | README 增加顶部红色警告 |
