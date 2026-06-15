# 废弃文件与目录清单

> 本文件记录项目中已废弃的文件、脚本和目录，供追溯参考。
> 这些内容已被新版本替代，请勿在新开发中使用。

---

## 废弃脚本（scripts/）

| 废弃脚本 | 替代版本 | 废弃原因 |
|----------|----------|----------|
| `econometrics.py` | `research_framework/econometrics_extended.py` | 功能已整合到 econometrics_extended.py |
| `econometrics_advanced.py` | `research_framework/econometrics_extended.py` | 功能已整合到 econometrics_extended.py |
| `export_hubei_data.py` | `fetch_provincial_stats.py` | 功能已整合到 fetch_provincial_stats.py |
| `generate_hubei_excel.py` | `generate_hubei_excel_v2.py` | v1 版本，已由 v2 替代 |
| `fetch_msci_cyh.py` | `fetch_msci_esg.py` | 仅演示数据，应使用 fetch_msci_esg.py |
| `fetch_msci_esg_v2.py` | `fetch_msci_esg.py` | 仅演示数据，应使用 fetch_msci_esg.py |
| `entity_list_data_fetcher.py` | `universal_data_fetcher.py` | 已被 universal_data_fetcher.py 整合替代 |
| `financial_report_structure.py` | `demo_research_report.py` | 功能已整合到 demo_research_report.py |
| `report_generator.py` | `demo_research_report.py` | 功能已整合到 demo_research_report.py |
| `professional_review_agent.py` | `scripts/core/reviewer.py` | 已被核心模块 reviewer.py 替代 |
| `review_layer.py` | `scripts/core/reviewer.py` | 功能已整合到 core/reviewer.py |

> 注：`scripts/DEPRECATED.md` 是内部版本，与本文件同步。

---

## 废弃数据文件（data/）

| 废弃文件 | 说明 |
|----------|------|
| `data/msci_esg_ratings.json` | 已删除（数据结构过时） |
| `data/national_province_data_2026.json` | 已删除（被 national_province_data_*.json 替代） |
| `data/todos.db` | 已删除（SQLite 任务数据库，不再使用） |

---

## 废弃配置

| 废弃文件/目录 | 说明 |
|----------|------|
| `data/event_trigger_state.json.bak` | 备份文件，可安全删除 |
| `data/alternative_data/` 下各子目录 | 占位目录，待填充真实数据 |

---

## 废弃 MCP 服务器

> 以下服务器曾被考虑但最终未实现或已被替代方案覆盖。

| 废弃服务器 | 替代方案 |
|----------|----------|
| 无 | — |

---

## 版本说明

- 本文件创建于 v1.6.1（2026-06-10）
- 与 `scripts/DEPRECATED.md` 保持同步
- 废弃内容仅作历史参考，不影响当前系统运行
