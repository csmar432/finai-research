#!/usr/bin/env python3
"""
Example 03: Auto-generate LaTeX Paper · 自动生成可投稿 LaTeX 论文

演示如何从研究数据自动生成符合经济研究/金融研究格式的 LaTeX 论文。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

OUTPUT_DIR = project_root / "output" / "examples" / "03-paper-latex"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("📄 LaTeX 论文自动生成演示")
    print("=" * 60)

    # 占位 - 真实环境用 fin-paper-draft skill
    print("\n💡 真实使用请用 fin-paper-draft skill：")
    print()
    print("   >>> fin-paper-draft --topic '碳排放权交易' \\")
    print("   ...                  --target-journal '经济研究' \\")
    print("   ...                  --refined-design REFINED_DESIGN.md")
    print()
    print("   或编程式调用：")
    print()
    print("   ```python")
    print("   from scripts.skills.paper_draft import draft_paper")
    print("   paper = draft_paper(topic, journal='经济研究')")
    print("   paper.compile_to_pdf()  # 自动编译")
    print("   ```")
    print()
    print(f"📁 预期输出目录: {OUTPUT_DIR}")
    print("   - main.tex         # 主 LaTeX 文件")
    print("   - refs.bib         # BibTeX 引用")
    print("   - figures/         # 图表 (≥300 DPI)")
    print("   - tables/          # 表格")
    print("   - main.pdf         # 编译产物")
