# FAQ & 故障排查指南

> 本文档覆盖「论文-研报工作流」使用过程中的常见问题。
> 最后更新：2026-06-09

---

## 目录

1. [安装与配置](#1-安装与配置)
2. [API Key 问题](#2-api-key-问题)
3. [MCP 服务器问题](#3-mcp-服务器问题)
4. [数据获取问题](#4-数据获取问题)
5. [论文写作与 LaTeX](#5-论文写作与-latex)
6. [计量方法与回归](#6-计量方法与回归)
7. [测试与 CI](#7-测试与-ci)
8. [性能问题](#8-性能问题)
9. [其他](#9-其他)

---

## 1. 安装与配置

### Q1: `pip install` 失败，提示 `No module named 'xxx'`

**原因**：依赖未安装或 Python 版本不匹配。

**解决**：
```bash
# 确认 Python 版本 >= 3.11
python3 --version

# 安装全部依赖
pip install -e .

# 仅安装核心依赖（不含深度学习等重型包）
pip install pandas numpy scikit-learn statsmodels matplotlib seaborn

# 检查缺失的包
python3 -c "import pkg_resources; [pkg_resources.get_distribution(p).project_name for p in pkg_resources.working_set]"
```

---

### Q2: `scripts/health_check.py` 报错 `ModuleNotFoundError`

**原因**：`PYTHONPATH` 未设置。

**解决**：
```bash
# 方案1：设置 PYTHONPATH（推荐）
export PYTHONPATH="$(pwd):$PYTHONPATH"

# 方案2：使用 python -m
python3 -m scripts.health_check

# 方案3：运行安装向导
python3 scripts/setup_wizard.py --guided
```

---

### Q3: macOS 上 `scripts/health_check.py` 报错 `Permission denied`

**原因**：Homebrew 安装的 Python 没有写入权限。

**解决**：
```bash
# 使用系统 Python 或 conda
/usr/bin/python3 scripts/health_check.py

# 或者创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

### Q4: Docker 构建失败 `COPY failed: file not found`

**原因**：`docker-compose.yml` 中引用的文件不存在。

**解决**：
```bash
# 验证所有引用的文件存在
python3 -c "
import re
with open('docker-compose.yml') as f:
    content = f.read()
for m in re.finditer(r'context:\s+(.+?)\n\s+dockerfile:\s+(.+?)\n', content):
    ctx = m.group(1).strip()
    df = m.group(2).strip()
    from pathlib import Path
    ok = (Path(ctx)/df).exists()
    print(f'{'✅' if ok else '❌'} {ctx}/{df}')
"
```

---

## 2. API Key 问题

### Q5: 提示 `DEEPSEEK_API_KEY is not set`，无法生成论文

**原因**：DeepSeek API Key 未配置。

**解决**：
```bash
# 方案1：复制环境变量模板
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxxxx

# 方案2：设置环境变量
export DEEPSEEK_API_KEY=sk-xxxxx

# 方案3：使用 B.AI 中转（无需 Key）
export RELAY_API_KEY=your_relay_key
```

> 获取 DeepSeek API Key：https://platform.deepseek.com/api_keys

---

### Q6: `TUSHARE_TOKEN` 缺失，A股数据无法获取

**原因**：Tushare Pro Token 未配置。

**解决**：
```bash
# 注册 Tushare Pro：https://tushare.pro/register
# 在 .env 中填入
TUSHARE_TOKEN=your_token_here

# 无 Token 时，系统自动 fallback 到 akshare（免费）
# 查看 fallback 数据：
python3 -c "from scripts.research_framework.data_fetcher import DataFetcher; f = DataFetcher(); print(f.get_fallback_status())"
```

---

### Q7: `BRAVE_SEARCH_API_KEY` 缺失，文献检索失败

**解决**：
```bash
# Brave Search（英文文献）
# 免费注册：https://brave.com/search/api/
export BRAVE_SEARCH_API_KEY=your_brave_key

# 无 Key 时，自动使用 ArXiv/OpenAlex（免费）
```

---

## 3. MCP 服务器问题

### Q8: MCP 服务器连接失败 `Connection refused`

**原因**：MCP 服务器未启动或端口被占用。

**解决**：
```bash
# 方式1：使用 Docker Compose 启动所有服务
docker-compose up -d

# 方式2：检查哪些服务在运行
docker-compose ps

# 方式3：单独启动单个服务
docker-compose up -d mcp_financial

# 方式4：本地运行（无需 Docker）
cd mcp_servers/user_financial
python3 server.py
```

---

### Q9: MCP 服务器健康检查失败

**诊断**：
```bash
# 检查健康检查日志
docker-compose logs mcp_financial | grep -i health

# 测试 MCP 服务器是否响应
curl http://localhost:8000/health 2>/dev/null || \
curl http://localhost:8001/health 2>/dev/null

# 检查端口占用
lsof -i :8000 -i :8001 2>/dev/null | grep LISTEN
```

---

### Q10: `user_tushare` 无法连接

**原因**：Tushare API 限流或 Token 失效。

**解决**：
```bash
# 检查 Token 是否有效
python3 -c "
import tushare as ts
ts.set_token('your_token')
pro = ts.pro_api()
print(pro.trade_cal(ts_code='000001.SZ', start_date='20240101', end_date='20240110'))
"

# 查看限流信息
# Tushare Pro 免费用户：每分钟 200 次，每日 100,000 次
```

---

## 4. 数据获取问题

### Q11: A股数据返回空值或 NaN

**常见原因**：
1. 股票代码格式错误（应为 `000001.SZ` 而非 `000001`）
2. 日期范围超出 Tushare 限制
3. 无交易数据的停牌日期

**解决**：
```python
from scripts.research_framework.data_fetcher import DataFetcher

fetcher = DataFetcher()
# 正确格式
df = fetcher.get_stock_daily("000001.SZ", "20240101", "20241231")

# 检查数据质量
print(f"数据量: {len(df)}, 空值: {df.isnull().sum().sum()}")
```

---

### Q12: 宏观数据缺失（GDP/CPI/M2）

**原因**：`akshare` 数据源更新延迟。

**解决**：
```python
# 使用 World Bank 备选
from mcp_servers.user_financial.server import get_wb_indicator

gdp = get_wb_indicator(country_code="CHN", indicator="NY.GDP.MKTP.CD")
print(gdp)
```

---

### Q13: `Permission denied` 写入 `data/` 目录

**原因**：`data/` 目录权限不足。

**解决**：
```bash
# 方案1：修改权限
chmod -R u+rw data/

# 方案2：使用用户目录
export DATA_DIR=~/finai_data
mkdir -p $DATA_DIR
```

---

## 5. 论文写作与 LaTeX

### Q14: LaTeX 编译失败 `! LaTeX Error: File 'xxx.sty' not found`

**原因**：缺失 LaTeX 包。

**解决**：
```bash
# macOS（使用 MacTeX）
brew install --cask mactex

# Linux（使用 TeX Live）
sudo apt install texlive-full

# 验证安装
pdflatex --version

# 或者仅安装必要包
tlmgr install natbib amsmath amssymb graphicx
```

---

### Q15: 中文论文编译后乱码

**原因**：未使用 `uplatex` 或 XeLaTeX 引擎。

**解决**：
```bash
# 使用 XeLaTeX 编译中文
xelatex paper.tex

# 或使用 uplatex
uplatex paper.tex && pbibtex paper && uplatex paper.tex && uplatex paper.tex
```

---

### Q16: LaTeX 表格超出页面宽度

**解决**：
```latex
% 方案1：调整列宽
\begin{tabular}{p{3cm}p{3cm}p{3cm}}

% 方案2：缩小字体
\begin{small}
\begin{tabular}{...}
\end{small}

% 方案3：横向旋转页面
\usepackage{rotating}
\begin{sidewaystable}
...
\end{sidewaystable}
```

---

### Q17: 参考文献格式错误

**解决**：
```bash
# 检查 .bib 文件
python3 scripts/core/provenance.py --validate-bib references.bib

# 使用正确的 bibliography style
\bibliographystyle{econ}      % 经济研究风格
\bibliographystyle{aea}       % AER 风格
\bibliographystyle{Chicago}  % 芝加哥风格
```

---

## 6. 计量方法与回归

### Q18: DID 回归报错 `ValueError: 'unit' not found in dataframe`

**原因**：数据中没有 `unit` 和 `time` 列。

**解决**：
```python
from scripts.research_framework.modern_did import CallawaySantAnna

cs = CallawaySantAnna()
df = cs.prepare_data(
    data=raw_df,
    unit_col="firm_id",    # 替代 unit
    time_col="year",       # 替代 time
    treatment_col="treated",
    outcome_col="outcome"
)
result = cs.fit(df)
```

---

### Q19: 面板数据豪斯曼检验失败

**原因**：随机效应假设被拒绝（应使用固定效应）。

**自动判断**：
```python
from scripts.research_framework.regression_engine import PanelRegression

reg = PanelRegression(data=panel_df, unit="firm_id", time="year")
result = reg.hausman_test()  # 自动选择 FE vs RE
print(f"建议使用: {'固定效应' if result.reject else '随机效应'}")
```

---

### Q20: 工具变量弱相关（F统计量 < 10）

**诊断**：
```python
from scripts.research_framework.robustness_runner import WeakInstrumentTest

wit = WeakInstrumentTest()
test_result = wit.check_weak_iv(iv_model)
print(f"F统计量: {test_result.f_stat:.2f}")
print(f"建议: {'使用更强工具变量' if test_result.f_stat < 10 else '工具变量有效'}")
```

---

### Q21: Stata 比较验证失败

**原因**：Stata 未安装或未在 PATH 中。

**解决**：
```bash
# macOS 安装 Stata
# 参考：https://www.stata.com/download/

# 或使用 R 作为替代
python3 scripts/validate_econometrics.py --compare r --method did

# 跳过 Stata 比较
python3 scripts/validate_econometrics.py --python-only
```

---

## 7. 测试与 CI

### Q22: `pytest` 报 `ModuleNotFoundError`

**解决**：
```bash
# 确保在项目根目录
cd /path/to/论文-研报工作流

# 设置 PYTHONPATH
export PYTHONPATH="$(pwd):$PYTHONPATH"

# 运行测试
python3 -m pytest tests/ -x -q
```

---

### Q23: 测试内存不足（OOM killed）

**原因**：一次性运行 1498 个测试，内存耗尽。

**解决**：
```bash
# 分批运行
python3 -m pytest tests/test_llm_reviewer.py -q
python3 -m pytest tests/test_modern_did.py -q
python3 -m pytest tests/test_econometrics.py -q

# 使用内存限制
python3 -m pytest tests/ --maxprocesses=2 -q

# 跳过重型测试
python3 -m pytest tests/ -q --ignore=tests/test_orchestrator_comprehensive.py
```

---

### Q24: GitHub Actions CI 失败

**诊断**：
```bash
# 本地模拟 CI
docker-compose -f .github/workflows/ci.yml run test

# 检查 .github/workflows/ci.yml 中的步骤
cat .github/workflows/ci.yml | grep -A5 "run:"
```

---

## 8. 性能问题

### Q25: 大规模面板数据（> 100万行）处理缓慢

**优化方案**：
```python
# 使用 DuckDB 加速
import duckdb
conn = duckdb.connect("data/cache.duckdb")

# 启用并行处理
conn.execute("SET threads=8")

# 使用 Chunked 处理
for chunk in pd.read_csv("large_file.csv", chunksize=100000):
    result = process(chunk)
```

---

### Q26: LLM API 调用超时

**解决**：
```python
# 增加超时时间
from scripts.core.llm_gateway import LLMWrapper

llm = LLMWrapper(timeout=120)  # 120秒超时

# 或使用本地模型
llm = LLMWrapper(provider="ollama", model="llama3")
```

---

### Q27: MCP 数据获取速度慢

**优化**：
```python
# 启用缓存
from scripts.core.data_cache import DataCache

cache = DataCache(backend="duckdb")
df = cache.get_or_fetch(
    key="stock_daily_000001_2024",
    fetch_fn=lambda: tushare_api_call(),
    ttl=3600  # 1小时缓存
)
```

---

## 9. 其他

### Q28: 项目启动报错 `UnicodeDecodeError`

**原因**：文件路径或内容包含特殊字符。

**解决**：
```python
# 设置 UTF-8 编码
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 或在 .env 中设置
PYTHONIOENCODING=utf-8
```

---

### Q29: `scripts/run_research.py` 报 `FileNotFoundError`

**原因**：`run_research.py` 可能是占位符脚本。

**解决**：
```bash
# 使用主入口
python3 scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"

# 或使用交互式向导
python3 scripts/setup_wizard.py --interactive
```

---

### Q30: 如何获取帮助？

| 渠道 | 说明 |
|------|------|
| 本文档 | 先查阅 FAQ |
| `scripts/health_check.py` | 系统诊断 |
| `scripts/mcp_diagnostic.py` | MCP 服务诊断 |
| GitHub Issues | 报告 Bug |
| `docs/tutorials/01-quickstart.md` | 快速入门 |

---

### Q31: `ReviewerCalibrator` 偏见探测结果异常

**症状**：偏见严重度全是 0 或检测不到偏见。

**诊断**：
```python
from scripts.core.reviewer_calibrator import ReviewerCalibrator, BiasType, BiasInstance, BiasReport

calibrator = ReviewerCalibrator()

# 模拟测试偏见
history = [
    {
        "review": {
            "dimension_scores": {
                "methodology": 7.0, "novelty": 8.0, "writing": 6.5,
                "theory": 7.5, "reproducibility": 7.0,
            },
            "overall_score": 7.2,
            "metadata": {"journal": "JF"},
        }
    },
    {
        "review": {
            "dimension_scores": {
                "methodology": 6.0, "novelty": 6.2, "writing": 6.1,
                "theory": 6.3, "reproducibility": 6.0,
            },
            "overall_score": 6.1,
            "metadata": {"journal": "JF"},
        }
    },
    # 3个以上评分集中在6-7分，触发趋中偏见
]
report = calibrator.detect_biases(history)
print(f"检测到偏见: {len(report.detected_biases)}")
for b in report.detected_biases:
    print(f"  [{b.severity:.0%}] {b.bias_type.value}")
```

---

### Q32: `CalibratorFeedbackLoop` 生成的 prompt 调整不生效

**原因**：LLM 没有使用调整后的 prompt。

**诊断**：
```python
from scripts.core.reviewer_calibrator import (
    CalibratorFeedbackLoop, ReviewerCalibrator,
    BiasType, BiasInstance, BiasReport
)

loop = CalibratorFeedbackLoop(ReviewerCalibrator())
bias = BiasInstance(BiasType.CENTRAL_TENDENCY, 0.8, "分数集中在6-7",
                    ["all"], {}, "扩展评分范围")
report = BiasReport(1, [bias], 0.8, True, {}, {})

adj = loop.generate_prompt_adjustments(report)
print(f"生成 {len(adj)} 条调整")
for a in adj:
    print(f"  {a['severity_tag']}: {a['prompt_adjustment']}")

# 验证增强后的 prompt
enhanced = loop.build_adjusted_system_prompt(adj, base_prompt="You are a helpful reviewer.")
print(f"\n增强后 prompt 长度: {len(enhanced)} 字符")
print(f"增强后行数: {enhanced.count(chr(10))} 行")
```

---

### Q33: `BiasHistoryDB` 导出 CSV 为空

**原因**：偏见记录未正确写入。

**诊断**：
```python
from scripts.core.reviewer_calibrator import BiasHistoryDB
import tempfile, os

db_path = ".bias_history.db"
db = BiasHistoryDB(db_path)

# 查看数据库内容
import sqlite3
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM bias_records")
print(f"偏见记录数: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM review_metadata")
print(f"评审记录数: {cursor.fetchone()[0]}")

conn.close()

# 重新导出
db.export_csv("bias_export.csv")
print(f"CSV 大小: {os.path.getsize('bias_export.csv')} bytes")
```

---

### Q45: `journal_templates_multilang.py` 模板缺失

**诊断**：
```python
from scripts.journal_templates_multilang import get_all_templates, get_template

templates = get_all_templates()
print(f"可用模板数: {len(templates)}")

# 列出日文模板
japanese = [t for t in templates if t.language == "Japanese"]
print(f"日文模板: {[t.journal_code for t in japanese]}")

# 列出德文模板
german = [t for t in templates if t.language == "German"]
print(f"德文模板: {[t.journal_code for t in german]}")
```

---

### Q35: MCP Schema 验证失败

**诊断**：
```bash
# 验证所有 MCP 服务器的 schema
python3 scripts/mcp_schema_check.py

# 输出格式
# ✅ server_name/handler_name — 参数匹配
# ❌ server_name/handler_name — 参数不匹配（missing/extra/type_mismatch）
```

---

## 快速诊断命令汇总

```bash
# 1. 系统健康检查
python3 scripts/health_check.py

# 2. MCP 服务诊断
python3 scripts/mcp_diagnostic.py

# 3. 数据源检查
python3 scripts/data_source_checker.py

# 4. 想法-数据验证
python3 scripts/idea_data_checker.py

# 5. MCP Schema 验证（检查 tool 参数 vs handler 匹配）
python3 scripts/mcp_schema_check.py

# 6. CI 辅助验证（Dockerfile + MCP schema）
python3 scripts/ci_verify.py

# 7. 计量验证（DID）
python3 scripts/validate_econometrics.py --method did --compare python

# 8. Reviewer 偏见探测演示
python3 -c "
from scripts.core.reviewer_calibrator import ReviewerCalibrator
c = ReviewerCalibrator()
h = [{'review': {'dimension_scores': {'methodology':7,'novelty':6.2,'writing':6.3,'theory':6.4,'reproducibility':6.1},'overall_score':6.4,'metadata':{'journal':'JF'}}} for _ in range(5)]
r = c.detect_biases(h)
print(f'偏见数: {len(r.detected_biases)}')
for b in r.detected_biases:
    print(f'  [{b.severity:.0%}] {b.bias_type.value}: {b.description[:40]}')
"

# 9. 偏见反馈环演示
python3 scripts/core/reviewer_calibrator.py --loop-demo

# 10. 运行测试套件
python3 -m pytest tests/ -x -q
