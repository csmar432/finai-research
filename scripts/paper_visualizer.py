#!/usr/bin/env python3
"""
论文图表生成器
==============
根据论文内容，DeepSeek 设计并生成：
- 架构图（.svg / .dot）
- 实验结果可视化
- 表格生成

用法：
  python scripts/paper_visualizer.py --type architecture --topic "深度学习 量化"
  python scripts/paper_visualizer.py --type comparison --results "实验数据"
  python scripts/paper_visualizer.py --type table --data "对比数据"
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from scripts.ai_router import Task
from scripts.core.llm_gateway import LLMGateway

VIS_DIR = SCRIPT_DIR / "knowledge" / "visualizations"
VIS_DIR.mkdir(parents=True, exist_ok=True)

# Global gateway instance for visualization tasks
_gateway = LLMGateway(memory=None, use_cache=False)


def generate_architecture_diagram(
    topic: str,
    method_desc: str = "",
) -> str:
    """
    生成模型架构图的 Graphviz DOT 代码。
    """
    prompt = f"""你是一位专业的论文图表设计师。请为以下研究方法设计一个清晰的 **模型架构图**（用 Graphviz DOT 语言描述）。

## 研究主题/方法
{topic}

## 方法描述（如果有）
{method_desc}

## 输出要求

请生成完整的 Graphviz DOT 代码，描述模型的完整架构。设计要求：

1. **节点设计**：
   - 使用清晰的矩形框表示层或模块
   - 用颜色区分不同类型的组件（如输入/隐藏层/输出）
   - 每个节点标注名称和关键参数（如 "Embedding (d=256)"）

2. **边设计**：
   - 用箭头表示数据流向（从上到下或从左到右）
   - 标注关键数据维度（如 "tensor(N, T, d)"）

3. **模块划分**：
   - 用子图或虚线框将相关组件分组
   - 标注每个子图的名称（如 "Encoder"、"Decoder"）

4. **布局**：
   - 使用 rankdir=LR（水平布局）或 TB（垂直布局）
   - 整体要清晰、简洁，适合论文排版

请生成以下内容：

### 1. DOT 代码
用 ```dot ...``` 包裹的完整 Graphviz DOT 代码。

### 2. 生成命令
说明如何将 DOT 代码转换为 PDF/SVG：
```bash
dot -Tpdf architecture.dot -o architecture.pdf
dot -Tsvg architecture.dot -o architecture.svg
```

### 3. 图表说明
简要说明图表中各模块的作用和设计思路。

请确保 DOT 代码可以直接使用（语法正确）。"""

    print("\n  🎨 设计模型架构图...")
    result = _gateway.generate(prompt, task_hint=Task.RESEARCH,
                               model="deepseek", temperature=0.3, max_tokens=4096)
    return result.response.strip()


def generate_experiment_plot(
    topic: str,
    results: str = "",
) -> str:
    """
    生成实验结果可视化的 Python（matplotlib）代码。
    """
    prompt = f"""你是一位专业的数据可视化设计师。请为以下研究设计 **实验结果可视化** Python（matplotlib/seaborn）代码。

## 研究主题
{topic}

## 实验结果数据（如果有）
{results}

## 输出要求

请生成完整的 Python 代码，目标是生成适合论文的高质量图表。

### 图表类型（根据需要选择或组合）：

#### A. 主实验对比条形图
- 各方法在多个指标上的性能对比
- 使用 seaborn 的 barplot 或 matplotlib
- 标注显著性（∗、∗∗）

#### B. 消融实验折线图
- 各组件移除/添加后的性能变化
- 多个子图（subplot）展示不同维度

#### C. 敏感性分析热力图
- 超参数敏感性的热力图
- 使用 seaborn.heatmap

#### D. 时间序列图（如金融预测）
- 预测 vs 实际的时间序列对比
- 标注关键区间

## 图表设计规范（论文标准）：

```python
import matplotlib.pyplot as plt
import seaborn as sns

# 设置论文风格
plt.rcParams.update({{
    'font.size': 12,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'legend.fontsize': 10,
    'figure.titlesize': 14,
    'font.family': 'serif',
    'text.usetex': False,  # 如需 LaTeX，设为 True
    'axes.spines.top': False,
    'axes.spines.right': False,
    'figure.dpi': 300,
}})
sns.set_style("whitegrid")

# 颜色方案（色盲友好）
colors = ['#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#9b59b6']
```

请生成以下内容：
1. **Python 代码**：完整可运行的 matplotlib/seaborn 代码
2. **图表说明**：说明图表展示的核心信息
3. **导出命令**：如何保存为 PDF/PNG（300 DPI，适合论文）

代码要完整、可运行，图表要美观、专业。"""

    print("\n  📊 设计实验结果可视化...")
    result = _gateway.generate(prompt, task_hint=Task.RESEARCH,
                               model="deepseek", temperature=0.3, max_tokens=6144)
    return result.response.strip()


def generate_latex_table(
    results: str = "",
    table_type: str = "comparison",
) -> str:
    """
    生成 LaTeX 表格代码。
    """
    prompt = f"""你是一位专业的论文排版设计师。请为以下实验结果生成 **LaTeX 表格** 代码。

## 表格类型
{table_type}

## 实验数据
{results or "请生成示例数据表格作为参考"}

## 输出要求

请生成标准的 LaTeX 表格代码，要求：

### 1. 主实验对比表（\\begin{{table}} ... \\end{{table}}）
- 使用 booktabs 风格（\\toprule, \\midrule, \\bottomrule）
- 数值精确到小数点后 2-4 位
- 最高值加粗（\\mathbf{{...}}）
- 显著性标注（∗、∗∗、∗∗∗）
- 完整的 caption 和 label

### 2. 消融实验表
- 各组件贡献的对比
- 清晰的层次结构

### 3. 数据集描述表
- 数据集基本信息
- 简洁的两列或三列格式

请确保 LaTeX 代码完整、可编译。使用以下包：
```latex
\\usepackage{{booktabs}}
\\usepackage{{multirow}}
\\usepackage{{threeparttable}}
```

请提供完整的 LaTeX 代码，直接复制即可使用。"""

    print("\n  📋 生成 LaTeX 表格...")
    result = _gateway.generate(prompt, task_hint=Task.PAPER_CN,
                               model="deepseek", temperature=0.3, max_tokens=4096)
    return result.response.strip()


def save_visualization(content: str, viz_type: str, topic: str) -> str:
    """保存可视化设计文件。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "_", topic)[:15]
    filename = f"{viz_type}_{safe}_{timestamp}.md"
    filepath = VIS_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"\n💾 已保存: {filepath}")
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="论文图表生成器")
    parser.add_argument("--type", "-t",
                       choices=["architecture", "experiment", "table", "all"],
                       default="all", help="图表类型")
    parser.add_argument("--topic", help="研究主题")
    parser.add_argument("--method", default="", help="方法描述")
    parser.add_argument("--results", default="", help="实验结果数据")
    parser.add_argument("--save", action="store_true", help="保存到知识库")

    args = parser.parse_args()
    topic = args.topic or "研究主题"

    print(f"\n{'='*70}")
    print("  🎨 论文图表生成")
    print(f"  主题: {topic}")
    print(f"{'='*70}")

    all_content = []

    if args.type in ("all", "architecture"):
        content = generate_architecture_diagram(topic, args.method)
        print(f"\n{'─'*70}")
        print(content)
        all_content.append(f"## 1. 模型架构图（Graphviz DOT）\n\n{content}")

    if args.type in ("all", "experiment"):
        content = generate_experiment_plot(topic, args.results)
        print(f"\n{'─'*70}")
        print(content)
        all_content.append(f"## 2. 实验结果可视化（Python/matplotlib）\n\n{content}")

    if args.type in ("all", "table"):
        content = generate_latex_table(args.results)
        print(f"\n{'─'*70}")
        print(content)
        all_content.append(f"## 3. LaTeX 表格\n\n{content}")

    if args.save:
        save_visualization("\n\n".join(all_content), "all", topic)

    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
