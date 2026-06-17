# FinResearch Agent

> 经济金融领域 AI 学术研究工作流。从研究想法到可投稿论文，集成 MCP 数据获取、因果推断、LaTeX 排版和对抗性 review 循环。

## 核心能力

- **数据获取**：43 个 MCP 数据服务器，覆盖 A股/美股/宏观/学术论文
- **因果推断**：DID / IV / RDD / PSM / 面板 GMM 等 42 种计量方法
- **论文写作**：支持 JF / JFE / RFS / 经济研究 / 金融研究 等中英文顶刊格式
- **智能 Review**：多轮对抗性评审循环，自动检查实证严谨性

## 快速开始

```bash
python scripts/agent_pipeline.py --topic "碳排放权交易对企业绿色创新的影响"
python scripts/health_check.py --json
```

## 研究流程

```
想法发现 → 文献综述 → 新颖性验证 → 实证设计 → 数据获取 → 论文写作 → 对抗性Review
```

## 文档导航

- [快速入门教程](tutorials/01-quickstart.md)
- [研究方向设计](tutorials/03-research-directions.md)
- [MCP 工具市场](tutorials/04-mcp-marketplace.md)
- [事件驱动研究](tutorials/05-event-driven-research.md)
- [API 参考](api_reference.md)
- [架构设计](ARCHITECTURE.md)
- [使用指南](../USAGE_GUIDE.md)

## 可用研究方向

| 方向 | 政策事件 | 计量方法 |
|------|---------|---------|
| 绿色金融 | 绿色金融改革试验区 | CS/SunAb DID + GMM |
| 碳经济学 | 全国碳市场启动 | CS DID + SDID |
| 数字金融 | 数字货币试点 | GMM + RDD |
| ESG | MSCI 评级纳入 | PSM-DID |
| 企业金融 | 注册制改革 | Bacon 分解 |
| 行为金融 | 交易机制改革 | Fama-MacBeth |
| 金融科技 | 金融科技试点 | IV + PSM |
| 宏观经济 | 货币政策传导 | Panel VAR |
| 房地产金融 | 限购限贷政策 | 三重差分 |
| 国际金融 | 汇率制度改革 | 合成控制 |
| 政治经济金融 | 产业政策 | IV + 交互固定效应 |

## 链接

- [项目主页](https://github.com/YOUR_USERNAME/finai-research-workflow)
- [使用指南](../USAGE_GUIDE.md)
- [安装配置](tutorials/01-quickstart.md)
