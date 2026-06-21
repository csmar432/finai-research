# 废弃脚本注册表

> 本文件记录项目中已废弃的脚本及其替代方案。
> 由审计修复（v0.1.x）生成于 2026-06-21。

## 活跃使用但已标记废弃

以下脚本因历史原因被其他脚本引用，仍可使用但不推荐在新代码中调用：

### `scripts/review_layer.py`

- **状态**: 废弃但被 `paper_write.py`、`paper_reader.py` 引用
- **废弃日期**: 2026-06-09
- **替代**: `scripts/core/llm_reviewer.py`（LLM-based）和 `scripts/core/dual_reviewer.py`（对抗性双审）
- **说明**: `ReviewLayer` 提供 DeepSeek 审查 + GPT 修复双阶段流水线。
  被 3 个脚本引用（`paper_write.py`、`paper_reader.py`、`review_layer.py` 自身导入测试）。
  在这些引用迁移完成前，保留原文件不变。
- **迁移优先级**: 中

---

## 完全废弃（已归档至 `scripts/deprecated/`）

以下脚本已从项目主目录移除，完整内容保存在 `scripts/deprecated/` 目录中：

### `scripts/deprecated/research_workflow_v2.py`

- **原位置**: `scripts/research_workflow.py`
- **废弃日期**: 2026-06-21（v0.1.x 审计）
- **替代**: `scripts/agent_pipeline.py`（AgentPipeline 主入口）
- **说明**: 1076 行的独立 step-by-step 工作流。
  包含选题确认、数据准备、分析确认、写作确认 4 个手动确认步骤。
  已被 AgentPipeline 完全覆盖。
- **迁移优先级**: 低（无人引用）
- **使用旧版本**: `scripts/deprecated/research_workflow.py`（旧版 673 行，废弃时间 2026-06-09）

---

## 使用说明

如需查看废弃脚本的完整内容：

```bash
# 查看废弃脚本列表
cat scripts/DEPRECATED.md

# 查看废弃脚本内容（示例）
cat scripts/deprecated/research_workflow_v2.py

# 如果确实需要恢复某个废弃脚本（不推荐）
git show HEAD:scripts/research_workflow.py
```

## 添加新的废弃脚本

当脚本被废弃时，执行以下步骤：

1. 将脚本移动到 `scripts/deprecated/` 目录（使用 `git mv`）
2. 在文件顶部添加 DEPRECATED 头注释
3. 在本注册表中添加记录
4. 更新所有引用该脚本的代码（使用替代脚本）

```bash
# 示例：废弃 scripts/old_script.py
git mv scripts/old_script.py scripts/deprecated/old_script.py
```
