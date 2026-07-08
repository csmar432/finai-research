# How to Cite FinAI Research Workflow

> **Recommended citation styles for academic papers**.
> If you used FinAI in a published paper, please cite it — it helps the project grow.

---

## 1. BibTeX (most common)

```bibtex
@software{finai_research_workflow_2026,
  author    = {{csmar432}},
  title     = {{FinAI Research Workflow: An End-to-End AI Agent Pipeline for Economic and Financial Research}},
  year      = {2026},
  month     = jun,
  version   = {0.1.0},
  url       = {https://github.com/csmar432/finai-research},
  doi       = {10.5281/zenodo.PENDING},  % NOTE: PENDING. Replace after Zenodo release (https://zenodo.org)
  note      = {44 MCP data sources, 42 econometric methods, 17 AI skills, 44 journal templates}
}
```

## 2. APA (7th edition)

```
csmar432. (2026). FinAI Research Workflow (Version 0.1.0) [Computer software].
https://github.com/csmar432/finai-research
```

## 3. Chicago (Author-Date)

```
csmar432. 2026. "FinAI Research Workflow." Version 0.1.0.
https://github.com/csmar432/finai-research.
```

## 4. MLA (9th edition)

```
csmar432. "FinAI Research Workflow." Version 0.1.0, 2026,
github.com/csmar432/finai-research.
```

## 5. Chinese GB/T 7714

```
csmar432. FinAI Research Workflow: 经济金融领域端到端AI智能体流水线
[软件]. 版本 0.1.0. 2026.
https://github.com/csmar432/finai-research.
```

## 6. Acknowledgement Text (适合论文致谢/Acknowledgement)

```
This work used FinAI Research Workflow (csmar432 2026), an open-source
AI agent pipeline for economic and financial research. The author thanks
the FinAI contributors for their work.
```

中文版：

```
本研究使用了 FinAI Research Workflow（csmar432 2026），一个面向经济
金融研究的开源 AI 智能体流水线。感谢 FinAI 贡献者的开源工作。
```

---

## 7. 在论文中如何描述 FinAI 的使用

**Method section 推荐写法（英文）**：

> "We implement the empirical analysis using FinAI Research Workflow
> (csmar432 2026), an open-source AI agent that integrates 43 data
> sources and 42 econometric methods. The agent's Callaway-Sant'Anna
> staggered DiD estimator is used to estimate group-time average treatment
> effects ATT(g, t)..."

**中文版（适合经济研究/金融研究）**：

> "本文使用 FinAI Research Workflow（csmar432 2026）这一开源 AI 智能体
> 实施实证分析。该工具集成了 43 个数据源和 42 种计量方法。
> 我们采用其内置的 Callaway-Sant'Anna 多期 DID 估计量，
> 计算组-时平均处理效应 ATT(g, t)..."

---

## 8. Zenodo DOI（推荐）

发布到 Zenodo 后，每个 release 都有独立 DOI。引用时建议引用**特定版本**：

```
DOI: 10.5281/zenodo.PENDING  (replace with actual after Zenodo release — see https://zenodo.org)
```

**为什么用 Zenodo？**
- 每个 release 永久可引用
- 符合 DataCite 标准
- 期刊（尤其是 JF/JFE）接受软件引用时偏好 Zenodo DOI

---

## 9. BibTeX for specific components

如果只用了部分功能，可只引用：

```bibtex
% 如果只用了 modern_did 模块
@misc{finai_modern_did_2026,
  author = {{csmar432}},
  title  = {{FinAI Research Workflow: Modern DiD module}},
  year   = {2026},
  url    = {https://github.com/csmar432/finai-research/blob/main/scripts/research_framework/modern_did.py}
}

% 如果只用了 China policy events
@misc{finai_china_events_2026,
  author = {{csmar432}},
  title  = {{FinAI Research Workflow: China Policy Events Library}},
  year   = {2026},
  url    = {https://github.com/csmar432/finai-research/blob/main/scripts/research_framework/china_policy_events.py}
}
```

---

## 10. 致谢模板（中文期刊版）

```
致谢：本研究使用 FinAI Research Workflow（csmar432 2026）作为实证分析
工具。感谢 FinAI 开源社区提供的方法库和数据接口支持。
```

---

## 11. 致谢模板（英文顶刊版）

```
Acknowledgements: This work used FinAI Research Workflow
(https://github.com/csmar432/finai-research), an open-source
AI agent for economic and financial research. We thank the FinAI
contributors for making this tool publicly available. All errors are
our own.
```

---

## 12. FAQ

**Q: 必须引用吗？**
A: 不是必须，但强烈推荐。这能帮助工具被更多人看到，也帮助我们申请 Zenodo 引用统计。

**Q: 在 SSRN/RePEc 工作论文上怎么引用？**
A: 在 abstract 末尾加 "Software: FinAI Research Workflow (csmar432 2026)."

**Q: 在中文顶刊（经济研究/金融研究）怎么引用？**
A: 在 "本文使用的数据来源" 或 "研究方法" 段落描述，并在参考文献中按 GB/T 7714 格式列出。

**Q: 如果不出版只是用了工具？**
A: 不需要引用。但如果你想支持这个项目，可以 ⭐ star GitHub repo！
