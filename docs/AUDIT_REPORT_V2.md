# 深度审计报告 — 第二轮（PR-1~4 merge 后）

**日期**: 2026-07-13
**审计范围**: `/Users/xuzheyi/Desktop/论文-研报工作流`
**审计重点**: 跨平台兼容 + 流程完整性
**审计员**: FinResearch Agent (深审计)
**审计背景**: PR-1~4 (install_ux / perf_correctness / method_parity / docs_clarity) 已 merge；用户授权 PAT 完成推送 + 继续深度审计。

---

## 一、总体结论

PR-1~4 修复了用户最早报告的 4 类问题（pip/apt 冲突、入口脚本找不到、silent mock、cache key 错误）。但深度审计发现 **17 项新问题**，主要集中在三个方向：

1. **跨平台兼容**（🔴 严重 4 项）：Windows venv 路径硬编码、subprocess.run 缺 encoding、`LC_ALL=C` 破坏中文、R/Stata 验证子进程编码
2. **用户交互流**（🔴 严重 3 项）：研究方向无澄清、模拟数据无授权、数据加载后无确认
3. **中断与长任务**（🟡 中等 3 项）：stage 进度丢失、streamlit Popen 孤立、MCP subprocess 泄漏

---

## 二、🔴 P0 — 必须修复（阻断性）

### P0-1. Windows venv 路径硬编码 `bin/pip`
- **文件**: `scripts/core/sandbox_executor.py:243`
- **现象**: `pip_executable = str(venv_path / "bin" / "pip")`
- **影响**: Windows 上 venv 路径是 `Scripts\pip.exe`，必抛 `FileNotFoundError`，**沙箱创建完全不可用**
- **影响面**: 所有 Windows 用户（Claude Code / Codex 实测反馈）
- **修复**: `sys.executable -m pip install`，或双分支 `bin/pip` (Unix) / `Scripts\pip.exe` (Windows)

### P0-2. `agent_pipeline.py --topic` 缺少研究方向澄清
- **文件**: `scripts/agent_pipeline.py:1551-1621` (main) + `scripts/agent_pipeline.py:2994-3013`
- **现象**: CLI 接收 `--topic` 后直接调 `AgentPipeline.run()`，**没有任何"主题细化 / 候选方向枚举 / 让用户挑选"环节**
- **设计意图 vs 实际**: `start_research.py` 有 5 轮 `ProgressiveClarifier`，但 `agent_pipeline.py` 完全跳过
- **影响**: 用户反馈"几乎完全自动化"的根因之一
- **修复**: `main()` 在解析 `--topic` 后、`AgentPipeline(config=...)` 前调用 `ProgressiveClarifier.run_interactive(topic)`，画像写入 `output/.clarify_session/research_profile.json`

### P0-3. 数据加载后无强制 HITL
- **文件**: `scripts/research_framework/pipeline.py:543-567` (`_run_full_pipeline`)
- **现象**: `[1/6]` 阶段若无 `panel_data.csv` 直接 `_build_demo_panel()` 生成 16 能源股 × 7 年随机数据，**完全不询问用户**；`ProvenanceTracker` 记录模拟字段是落盘后追加的
- **影响**: 用户报告的"数据"环节被压缩为一次性生成所有 DID 系数
- **修复**: 在 `[1/6]` 完成后立即 `_hitl_pause("data_loaded", ...)` 打印 `tracker.summary()` + 四选项（继续 / 重抓 / 补充 / 中止）。该函数已定义 (`pipeline.py:867-961`) 但未调用

### P0-4. 关键 `subprocess.run` 缺 `encoding=`
- **文件**:
  - `scripts/event_monitor.py:550`
  - `scripts/core/agents/paper_agents.py:1182` (同时 `/tmp/plot_*.py` 在 Windows 无效)
  - `scripts/core/sandbox.py:808`
  - `scripts/research_framework/pipeline.py:773` (`subprocess.call` 裸调用)
  - `scripts/cli.py:284`
  - `scripts/validate_econometrics.py:227, 270, 309, 372` (R/Stata 验证)
- **影响**: Windows cmd 默认 cp936 解码 MCP stdout 的 UTF-8 → `UnicodeDecodeError`；`/tmp` 在中文用户名 Windows 上不存在
- **修复**: 所有 `capture_output=True` 处加 `encoding="utf-8", errors="replace"`；`/tmp` → `tempfile.gettempdir()`；env 注入 `LC_ALL=C.UTF-8` + `PYTHONIOENCODING=utf-8`

---

## 三、🟡 P1 — 应当修复（质量问题）

### P1-1. `LC_ALL=C` 破坏中文 stdout
- **文件**: `scripts/core/normalize.py:185` — `os.environ.setdefault("LC_ALL", "C")`
- **影响**: 中文路径 / 中文 log 在 print 时报 `UnicodeEncodeError`（stdout=cp1252）；影响"中文路径研究"主流程
- **修复**: 改为 `C.UTF-8`

### P1-2. sandbox success.txt 双向缺编码
- **文件**: `scripts/core/sandbox_executor.py:463` (write) / `:378` (read)
- **影响**: 子进程以 cp936 写"0/1"，父进程用 UTF-8 读 → `return_code` 误判
- **修复**: 两端 `encoding="utf-8"`

### P1-3. DataGate 阻塞时 EOFError 静默落入退出
- **文件**: `scripts/start_research.py:142-156`
- **现象**: 非 TTY 环境（Cursor Agent / Claude Code）捕获 `EOFError` 后只打印"跳过交互"就 `return 0`
- **影响**: 下游脚本误判为"画像已锁定可继续"，**用户反馈"几乎完全自动化"的根因之一**
- **修复**: EOFError 分支返回非 0 退出码 + 写 `output/.clarify_session/BLOCKED.md`

### P1-4. `_run_idea_data_validation` 只 print 不询问
- **文件**: `scripts/agent_pipeline.py:1085-1119`
- **现象**: 发现 `data_gap` 想法时只 print"请在 data/ 目录补充所需数据文件"，然后 `return validated`
- **修复**: 在 gap / auth_needed 分支调 `_hitl_pause("data_validated", ...)` 触发真正的四选项交互

### P1-5. `run_pipeline` 阶段间无 HITL 暂停
- **文件**: `scripts/agent_pipeline.py:1813-1817`
- **现象**: `_orchestrator.run_pipeline(steps=...)` 一次性跑完 outline → literature → plotting → writing → refinement；用户对单个阶段产物**无审阅机会**
- **修复**: `PipelineStage.hitl_gate` 字段默认开 + `main()` 默认 `config.use_hitl = True`

### P1-6. `cmd_skip_clarify` 画像流于形式
- **文件**: `scripts/start_research.py:206-244`
- **现象**: 跳过 5 轮澄清后用 `multi` 策略 + `2010-2022` 默认窗口落盘画像，但**没标 `skipped_clarify: True`**；下游 `pipeline.py` 读取 `args.tickers`/`args.years` 是另一套默认值
- **修复**: 画像文件头加 `⚠️ SKIPPED CLARIFY` banner；下游读取时检测该 banner 强制要求 `--force`

### P1-7. `HITLGate.hold()` 在非 Cursor 终端静默挂起
- **文件**: `scripts/core/hitl_gate.py:231` + `scripts/agent_pipeline.py:1732-1736`
- **现象**: gate 写入 SQLite 后**无 UI 提示**等待 approve/reject；非 Cursor 终端 `_handle_interactive` 不被调用，pipeline 直接卡死
- **修复**: 同时 `print(cyan(f"⏸ 等待审批 gate={gid}…"))` + 提供 `scripts/hitl_approve_cli.py` CLI 命令手动批准

### P1-8. `paid_source_notifier` 在 `--strict-llm` 模式被吞掉
- **文件**: `scripts/core/paid_source_notifier.py:208-209`
- **现象**: 默认 `_SUPPRESSED = os.environ.get("FINAI_SUPPRESS_PAID_WARNINGS") == "1"`；当 `agent_pipeline.py` 因 LLM 不可用退出 4 时，付费源警告已被吞
- **修复**: 在 `run_diagnostic()` 后、`_llm_actually_available` 前遍历 `PAID_SOURCE_REGISTRY` 集中打印

### P1-9. `open()` 缺 `encoding=`（50+ 处）
- **写入**:
  - `scripts/core/llm_reviewer.py:1421`
  - `scripts/core/self_evolution.py:546, 561`
  - `scripts/core/checkpoint.py:1078`
  - `scripts/core/visual_graph_editor.py:29`
  - `scripts/core/tool_selector.py:3264`
  - `scripts/parse_mcp_data.py:82, 91`
  - `scripts/us_esg_formatter.py:30, 601`
  - `scripts/core/sandbox.py:795, 944, 973`
  - `scripts/audit_guard.py:1476`
  - `scripts/sync_numbers.py:32`
  - `scripts/update_related_stars.py:221`
- **影响**: Windows + 中文路径 `UnicodeDecodeError`
- **修复**: 文本 `open()` 显式 `encoding="utf-8"`

### P1-10. checkpoint 与 hitl_gate 双源真相
- **文件**: `scripts/core/checkpoint.py:918-941` + `scripts/core/hitl_gate.py:514-540`
- **现象**: `CheckpointableOrchestrator._capture_hitl_state` 与 `HITLGate.get_state` 并行序列化同一份 gate；恢复时两套并行反序列化；`checkpoint.py:179` 漏了 `feedback` / `approved_by`
- **影响**: `--resume` 时审批记录可能丢失
- **修复**: 让 `HITLGate.get_state()` 成为唯一权威源

---

## 四、🟢 P2 — 可选修复（体验改进）

### P2-1. `agent_pipeline.py:2420` subprocess.run 缺 encoding + GUI 进程跨平台不稳
- **修复**: 加 `encoding="utf-8"` + 检测 `os.name=='nt'` 时跳过 GUI

### P2-2. `health_check.py:674` `env_path.read_text()` 无 encoding
- **修复**: `read_text(encoding="utf-8")`

### P2-3. `event_monitor.py:1640` `open(log_path, "a")` 缺 encoding
- **修复**: `encoding="utf-8"`

### P2-4. `os.fork()` 守护进程路径已加 Windows 防护 (`event_monitor.py:1604-1611`) ✅
- 维持现状

### P2-5. checkpoint 缺 atexit/SIGINT flush
- **文件**: `scripts/core/checkpoint.py`
- **现象**: Ctrl+C 时 stage in-progress 丢失
- **修复**: 注册 `signal.signal(SIGINT, ...)` + `atexit.register(...)` 触发 flush

### P2-6. streamlit Popen 孤立（无 kill）
- **文件**: `scripts/agent_pipeline.py:761` + `scripts/paper_full_pipeline.py:332`
- **修复**: 保存 Popen 句柄，在 finally / atexit 中 `proc.terminate()`

### P2-7. llm_gateway MCP subprocess 泄漏
- **文件**: `scripts/core/llm_gateway.py:340`
- **修复**: 长连接对象使用 `try/finally` 或 `atexit` 关闭

---

## 五、修复优先级矩阵

| 优先级 | 项数 | 主要影响 |
|---|---|---|
| P0 | 4 | Windows 沙箱完全不可用、研究方向无澄清、模拟数据无授权、subprocess 中文崩溃 |
| P1 | 10 | LC_ALL 破坏中文、DataGate 静默、阶段无 HITL、画像 banner、gate 卡死 |
| P2 | 7 | 体验改进 |

---

## 六、最小修复路径（按工作量排序）

**工作量估计**: 🟢 <30 行 / 🟡 30-100 行 / 🔴 >100 行

| 序 | ID | 文件 | 工作量 | 说明 |
|---|---|---|---|---|
| 1 | P1-1 | `scripts/core/normalize.py:185` | 🟢 | `LC_ALL=C` → `C.UTF-8` |
| 2 | P1-2 | `scripts/core/sandbox_executor.py:378, 463` | 🟢 | success.txt 两端加 `encoding="utf-8"` |
| 3 | P0-1 | `scripts/core/sandbox_executor.py:243` | 🟢 | `bin/pip` → `sys.executable -m pip` 或平台分支 |
| 4 | P0-3 | `scripts/research_framework/pipeline.py:543-567` | 🟢 | `[1/6]` 后插入 `_hitl_pause("data_loaded", ...)` |
| 5 | P1-3 | `scripts/start_research.py:152-153` | 🟢 | EOFError 返回非 0 + 写 BLOCKED.md |
| 6 | P1-4 | `scripts/agent_pipeline.py:1085-1119` | 🟡 | gap 分支调 input() 三选项 |
| 7 | P1-5 | `scripts/agent_pipeline.py:2994` | 🟢 | `config.use_hitl = True` 默认 |
| 8 | P1-6 | `scripts/start_research.py:206-244` | 🟡 | skip-clarify 画像加 banner |
| 9 | P0-4 | 6 处 subprocess.run | 🟡 | 加 `encoding="utf-8", errors="replace"` |
| 10 | P1-9 | 50+ 处 open() | 🔴 | 批量补 `encoding="utf-8"` |
| 11 | P0-2 | `scripts/agent_pipeline.py:1551` | 🟡 | main() 前调 ProgressiveClarifier |
| 12 | P2-5/6/7 | checkpoint + Popen + MCP | 🟡 | atexit / finally 清理 |

---

## 七、CI 建议

1. **Windows 矩阵**: `.github/workflows/` 新增 `windows-latest` 矩阵，专门捕获 P0-1 / P0-4
2. **encoding 回归测试**: `tests/test_platform_lock.py` 应纳入前 4 项 P0 回归
3. **CI Verify 加项**: `scripts/ci_verify.py` 加 `--check-encoding` 扫描所有 `open(` / `subprocess.run` 缺 encoding 的位置

---

## 八、已完成的修复（PR-1~4 回顾）

| PR | 主要内容 | merge commit |
|---|---|---|
| PR-1 install_ux | 拆 extras、修入口脚本、统一 `_PROJECT_ROOT`、Mock 隔离、doctor | 571329a |
| PR-2 perf_correctness | LLM cache key、单次 diag、MCP 长连接、回归 baseline 缓存、robustness 内容指纹、token-bucket | 2adeb85 |
| PR-3 method_parity | 560 exact permutation、BMP/Kolari/符号秩、伪事件日、国庆 calendar qualifier | 20ac63e |
| PR-4 docs_clarity | README Quick Start 重写、SETUP_GUIDE wheel vs source、INSTALL.md、QUICKSTART venv | bcbd3e5 |

---

## 九、下一步建议

1. **立即**: 落地 P0-1 (Windows venv) + P0-3 (data HITL) + P1-1 (LC_ALL) — 这三项最影响 Windows 用户
2. **短期**: P0-4 (subprocess encoding) + P1-2 (success.txt) — 影响所有平台稳定性
3. **中期**: P0-2 (研究方向澄清) + P1-5 (阶段 HITL 默认开) — 影响用户控制感
4. **长期**: P1-9 (open() encoding 全量) + P2-5/6/7 (进程清理) — 防御性

---

**审计结束**