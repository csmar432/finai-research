# MCP Server Tiering — 分层指南

> **审计来源**: `docs/audit/GITHUB_STAR_AUDIT_2026-07-09.md` §4.1
> **目的**: 解决"43 vs 50 MCP 平铺展示"问题，降低新用户认知负担
> **更新**: 2026-07-11

## 概述

仓库现有 **43 个 MCP 服务器**（不含 `__pycache__/`）。按安装难度与价值分为三层：

| Tier | 数量 | 安装方式 | 适用场景 |
|------|------|---------|---------|
| **🟢 Core** | 8 | 默认启用 | 立即可用，0 配置 |
| **🟡 Recommended** | 12 | 一键启用 | 价值高，需 1 个环境变量 |
| **🔵 Optional** | 23 | 手动配置 | 机构账号 / API Key 必需 |

---

## 🟢 Core（核心层，8 个）

零配置即可使用，覆盖 **80% 的研究场景**。

| Server | 数据源 | 典型用途 | README |
|--------|--------|---------|--------|
| `user-openalex` | OpenAlex API（免费）| 文献检索（2亿+ 论文） | — |
| `user-arxiv` | arXiv API（免费）| 预印本检索 | — |
| `user-nber-wp` | NBER 工作论文 | 顶级经济学论文 | — |
| `user-yfinance` | Yahoo Finance | 美股/港股/ETF/期权 | — |
| `user-sec-edgar` | SEC EDGAR | 美股 10-K/10-Q/8-K | — |
| `user-financial` | akshare + World Bank | 中国宏观（GDP/CPI/M2）+ 全球 | — |
| `user-wb-data` | World Bank API | 全球宏观指标 | — |
| `user-imf-data` | IMF API | 全球经济展望 | — |

**启用命令**：
```bash
python scripts/register_mcp_servers.py --tier core
```

---

## 🟡 Recommended（推荐层，12 个）

需要 1 个 API Key（多为免费层），适合严肃研究使用。

| Server | 数据源 | 需要 Key？ | 免费额度 |
|--------|--------|----------|---------|
| `user-semantic-scholar` | Semantic Scholar | 可选（提升速率）| 100 req/5s |
| `user-context7` | Context7 全文索引 | 无 | 无限 |
| `user-tushare` | Tushare Pro | ✅ TUSHARE_TOKEN | 2000/日 |
| `user-eastmoney-reports` | 东方财富 | 无 | 无限 |
| `user-eodhd` | EODHD | ✅ EODHD_API_KEY | 20/日 |
| `user-fed-data` | 美联储 | 无 | 无限 |
| `user-bea-data` | BEA API | 无 | 无限 |
| `user-oecd-data` | OECD API | 无 | 无限 |
| `user-enhanced-finance` | 多源汇总（外汇/航运/大宗）| 无 | 无限 |
| `user-cryptocompare` | 加密货币 | 无 | 无限 |
| `user-pandas-mcp` | pandas 数据处理 | 无 | 本地 |
| `user-filesystem-mcp` | 文件系统 | 无 | 本地 |

**启用命令**：
```bash
python scripts/register_mcp_servers.py --tier recommended
# 然后编辑 ~/.env.local 添加 API Key
```

---

## 🔵 Optional（可选层，23 个）

需要机构账号或付费 API Key。适用专业研究人员。

### 国际学术（4）
- `user-cnki` — 中国知网（需机构订阅）
- `user-wanfang` — 万方数据（需机构订阅）
- `user-sipo` — 中国国家知识产权局（公开）
- `user-chinese-customs` — 中国海关总署（公开）

### 商业数据（3）
- `user-wind` — 万得（机构付费）
- `user-csmar` — 国泰安（机构付费）
- `user-third-party-esg` — 第三方 ESG 评级（混合）

### 中国本地化（4）
- `user-province-stats` — 中国省级统计
- `user-hubei-stats` — 湖北统计
- `user-wuhan-stats` — 武汉统计
- `user-chinese-literature` — 中文学术文献

### 新闻/搜索（4）
- `user-brave-search` — Brave Search API
- `user-newsapi` — NewsAPI
- `user-cnrd` — 中国研究文献数据库
- `user-e2b-mcp` — 云端代码执行

### 工具类（8）
- `user-latex-mcp` — LaTeX 排版检查
- `user-playwright-mcp` — 浏览器自动化
- `user-eastmoney-fund` — 公募基金
- `user-eastmoney-bond` — 债券
- `user-eastmoney-option` — 期权
- `user-macro-ceic` — CEIC 中国宏观
- `user-macro-datas` — 宏观数据聚合
- `user-macro-stats` — 宏观统计

**启用命令**：
```bash
python scripts/register_mcp_servers.py --tier optional --server user-cnki
# 然后在 ~/.env.local 配置机构账号
```

---

## 安装建议路径

### 初学者（第 1 周）
1. 注册 **Core** 8 个 → 完成 `pip install -e ".[dev]"`
2. 运行 `python scripts/start_research.py --topic "..."`
3. 用 `user-openalex` + `user-financial` 完成第 1 篇研报

### 中级研究者（第 2-4 周）
4. 添加 **Recommended** 中的 `user-tushare`（A股）+ `user-eastmoney-reports`（研报）
5. 配置 Tushare Token
6. 尝试中国 A 股 DID 研究

### 高级用户（持续）
7. 根据需要接入 **Optional** 中的专业数据源
8. 定制自己的 `mcp_servers/user_*/` 适配器

---

## 数字一致性

| 来源 | 数字 | 备注 |
|------|------|------|
| README.md | "43 个 MCP" | ✅ 与本表一致 |
| 本文档 | 8 + 12 + 23 = **43** | ✅ |

> 早期文档提及"50 个"源于包含 `__pycache__/` 等目录。本文档以"有效 MCP server"计。

---

## 验证方法

```bash
# 列出当前可用的 MCP server（PAT 认证后）
python scripts/register_mcp_servers.py --list

# 验证 tier 注册是否完整
python scripts/register_mcp_servers.py --validate --tier all
```