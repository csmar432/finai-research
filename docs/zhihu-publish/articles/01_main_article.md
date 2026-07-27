# 我用 6 个月做了个开源项目：让 AI 帮你跑完 43 类实证模型、生成可投稿的 LaTeX 论文草稿

> 一句话：告诉你研究主题，我帮你从文献综述 → 实证设计 → 数据获取 → 论文草稿 → LaTeX 编译。
> 草稿必须经研究者审阅后投稿——AI 不替代作者，只加速流程。

---

## 一、为什么做这个项目？

去年我读研二，写第一篇工作论文时，最大的痛点不是 idea，而是被这些事耗死：

- 📚 文献综述：找 50 篇论文 + 提炼引文网络 → 1 周
- 📊 数据获取：跨多个数据库（CSMAR / Wind / 国泰安 / Tushare）拼表格 → 3 天
- 📈 实证分析：DID/IV/RDD/PSM 不同模型要查不同包 → 1 周
- ✍️ 论文写作：LaTeX 模板对版式、参考文献对 BibTeX → 1 周
- 🔍 对抗 review：自己写的稿子自己看不出问题 → 反复改

这套流程走完，3 个月过去了，idea 还可能已经被人抢发。

**核心问题**：研究者的核心价值是 idea 和识别策略，不是重复劳动。
**我的答案**：把这套流程封装成可复用的工具——**FinResearch Agent**。

---

## 二、它能做什么？（一句话能力地图）

> **43 个数据源 + 47 种因果识别方法 + 30 个期刊模板 + 8 步研究流水线 + OpenSSF Gold 21/21 + MIT 协议**

![项目数据快照](assets/figure_00_overview.png)

### 1. 数据获取：43 个 MCP 服务器

我整合了 43 个 MCP 服务器目录，覆盖：

- **A股数据**：Tushare / Wind / CSMAR / EastMoney 研报（无需 API Key 也能用 akshare 兜底）
- **美股/港股**：yfinance / SEC EDGAR / Polygon
- **宏观**：World Bank / IMF / OECD / BEA / FRED / CEIC
- **学术文献**：OpenAlex / arXiv / Semantic Scholar / NBER / Context7（全文）
- **中文**：CNKI / Wanfang / CSSCI / SIPO 专利 / 海关数据
- **新闻 / 研报**：NewsAPI / Brave Search / EastMoney 研报

> **每个数据需求都有 4 层 fallback**：付费 API → 免费 API → 本地缓存 → 模拟数据（需用户授权）。
> 项目内已实现 `data_provenance` 模块，每次取数记录来源与时间戳，不静默造数据。

![43 MCP 数据源分布](assets/figure_02_mcp.png)

### 2. 实证分析：47 种因果识别方法（覆盖 JF / JFE / RFS / 经济研究 / 金融研究）

- **DID 系**：标准 DID、Bacon 分解、Callaway-Sant'Anna (CS 2021)、Sun-Abraham、Borusyak-Jaravel-Spinks、dCdH、合成 DID (Arkhangelsky 2021)
- **IV / GMM**：面板 IV、Jackknife IV、Arellano-Bond、Blundell-Bond
- **RDD / PSM**：精确 / 模糊 / 局部线性 RDD；多种匹配算法
- **现代方法**：三重差分、面板分位数、交互固定效应 (Bai 2009)、局部投影 DID (Jordà 2005)、空间回归 (SDM/SAR/SEM)
- **敏感性**：Honest DiD (Rambachan-Roth 2023)、Oster Bounds、Wild Cluster Bootstrap
- **稳健性**：19 类自动化检验（`RobustnessRunner.run_comprehensive("full")`）

> **独立验证状态**：标准 DID / Bacon / CS(2021) / 事件研究 / 空间回归（部分）有独立测试，**12,520 个 test 函数** 保证方法实现正确性。

### 3. 论文写作：30 种期刊模板 + 对抗性 review

- **英文顶刊**：JF / JFE / RFS / JAE / JPE / Econometrica
- **中文顶刊**：经济研究 / 金融研究 / 管理世界 / 会计研究 / 中国工业经济
- **LaTeX 双格式**：自动生成 `.tex` + `.bib`，本地编译可投稿草稿
- **对抗 review**：自动跑多轮严格评审，检查识别策略、统计推断、理论贡献

![88 期刊模板分布](assets/figure_04_journals.png)

---

## 三、它是怎么工作的？8 步流水线

```
0. 系统自检 → 1. 想法生成 → 2. 文献综述 → 3. 新颖性验证
   → 4. 实证设计 → 5. 数据获取 → 6. 实证分析 → 7. 论文写作 → 8. 对抗 review
```

**每个阶段都有"强制交互 checkpoint"**——AI 不会自动跳到下一步，必须研究者确认。
**每个数据点都有 provenance**——来源、时间戳、API 版本全记录。

---

## 四、实测演示：从一句话到 LaTeX 草稿

```bash
# 1. 健康检查
python scripts/health_check.py
# → ✅ MCP 就绪 / ✅ LLM 可用 / ✅ 依赖完整

# 2. 一句话启动
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"

# 3. 8 步流水线自动运行，每步暂停等你确认
# 想法 → 文献 → 新颖性 → 设计 → 数据 → 实证 → 写作 → review
```

**真实产出**：8,000-15,000 字 LaTeX 草稿 + 6-10 张图表（≥300 DPI）+ 完整 BibTeX。

---

## 五、工程实践：为什么不是又一个 Demo？

我做这个项目时，工程标准按**生产级**要求：

![OpenSSF Gold 21/21 认证](assets/figure_03_openssf.png)

| 维度 | 标准 | 实测 |
|------|------|------|
| 代码质量 | ruff + mypy strict | ✅ 通过 |
| 测试覆盖 | pytest 框架 | ✅ **12,520 个 test 函数** |
| 依赖审计 | pip-audit | ✅ 0 高危漏洞 |
| 安全合规 | OpenSSF Best Practices | ✅ **21/21 Gold** |
| CI/CD | GitHub Actions | ✅ 7 个 workflow 全绿 |
| 文档 | README + CONTRIBUTING + ADR | ✅ 完整 |
| License | MIT | ✅ 开源可商用 |

![系统健康检查雷达图](assets/figure_01_health.png)

> **GitHub Actions 上 7 个 PR-1~PR-7 全部合并，16/16 CI 全绿**——这是工程化项目的标志，不是 demo 脚本。

---

## 六、目标用户：谁适合用？

✅ **经管硕博生**：写工作论文 / 毕业论文的初稿生成
✅ **青年学者**：探索新 idea 的可行性预判
✅ **量化研究员**：跨数据库整合的快捷脚本
✅ **AI + 金融跨界开发者**：参考 MCP 集成模式

⚠️ **不适合**：

- 想要一键投稿的（AI 草稿必须人工核实）
- 不愿审稿的研究者（违反学术规范）
- 数据/方法都已确定的（脚本会显得"过度自动化"）

---

## 七、开源与贡献

- **GitHub**：https://github.com/csmar432/finai-research
- **协议**：MIT
- **状态**：v1.0（持续迭代）
- **Star / Fork / Issue**：欢迎使用反馈、Bug 报告、功能建议

### 适合贡献的方向

🐛 **Issue**：跑流程时遇到的 Bug、最希望加的 MCP 服务器、期刊模板
🔧 **PR**：新的计量方法实现（需附论文 DOI + 测试）、新期刊模板
📚 **文档**：教程、ADR、最佳实践

> **项目治理**：所有 P0 修复走 7 个独立 PR 流程；新增方法需 paper DOI + 单测；不会"随便 merge"。

---

## 八、写在最后：AI 是助手，不是作者

我做了这个项目 6 个月，越来越确信一件事：

> **AI 不会替代研究者，但会用 AI 的研究会替代不会用 AI 的。**

工具能帮你跑数据、套模板，但 idea、识别策略、理论贡献仍需要你的脑子。
FinResearch Agent 的定位是**"研究者的瑞士军刀"**——把重复劳动自动化，把思考留给你。

---

⭐ 如果你觉得有用，欢迎：

1. **Star** 仓库 → https://github.com/csmar432/finai-research
2. **Fork** 改造成你的版本
3. **提 Issue** 反馈 Bug / 想要的功能
4. **评论区告诉我**你的研究方向，我看看能不能帮你定制

我会持续更新这个项目，下一步计划：

- [ ] 加更多 LLM provider（Anthropic / Gemini）
- [ ] 加更多期刊（JoE / Restud）
- [ ] 加中文写作专版（更适合经管顶刊）

#开源 #AI工具 #经济金融 #论文写作 #量化研究 #LLM #Agent
