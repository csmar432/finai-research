# 文档总览 (docs/)

> 这里是项目文档的总入口。子目录结构：
>
> - `tutorials/` — 分步骤入门与方向教程
> - `adr/` — 架构决策记录 (Architecture Decision Records)
> - `audit/` — 项目历史审计文档
> - `manual/` — 各类操作手册
> - `blog/` — 公开宣传材料
> - 其他教程与排错文档

---

## MCP 数量：动态生成

本项目文档中提及的 MCP 服务器总数使用 `{{MCP_COUNT}}` 占位符统一表示，
**实际数字由 [`scripts/count_mcp.py`](../scripts/count_mcp.py) 自动扫描**
`mcp_servers/user_*` 目录后写入 `.docs-cache/MCP_COUNT.txt`。

### 为什么这样做

- 仓库历史上多处文档（CLAUDE.md、README、ADR、Docker 指南等）声明的 MCP 数量
  在 `41 / 43 / 44 / 50` 之间反复漂移，导致读者困惑。
- 通过占位符 + SSOT（single source of truth）脚本，**新增/删除 MCP 目录后只要再跑一次**
  即可让所有引用 `{{MCP_COUNT}}` 的文档自动同步：

  ```bash
  python scripts/count_mcp.py     # 输出数字并写入 .docs-cache/MCP_COUNT.txt
  ```

### CI 集成建议（待添加）

- 在 CI 流程里跑 `python scripts/count_mcp.py` 后，用 `sed` 或 CI 变量替换
  把 `{{MCP_COUNT}}` 替换为实际数字，生成发布版 markdown。
- 或者直接接受占位符留在文档中（开发版），让读者自行查阅
  `.docs-cache/MCP_COUNT.txt`。

### 依赖关系

| 角色 | 文件 | 用途 |
|------|------|------|
| 真理源 | `scripts/count_mcp.py` | 扫描 `mcp_servers/user_*` 目录，输出数字 |
| 缓存 | `.docs-cache/MCP_COUNT.txt` | 被其他脚本/CI 消费 |
| 占位符 | `{{MCP_COUNT}}` | 文档中所有出现 MCP 总数的位置 |
| 复用 | `scripts/count_assets.py::count_mcp_servers()` | 自动统计脚本内部委托给 `count_mcp.py` |
