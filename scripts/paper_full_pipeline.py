#!/usr/bin/env python3
"""
论文全流程管道
=============
统一入口：一键完成论文生成 → 去AI化润色 → Word三线表导出。

使用方法：
  python scripts/paper_full_pipeline.py                    # 完整流程
  python scripts/paper_full_pipeline.py --no-cache        # 跳过缓存
  python scripts/paper_full_pipeline.py --skip-docx      # 仅生成并润色Markdown
  python scripts/paper_full_pipeline.py --skip-polish     # 仅生成Markdown

修复记录（2026-05-21）：
  1. 模型名：deepseek-v4-pro/v4-flash/reasoner 全部返回空 → 强制降级为 deepseek-chat
  2. ai_router.py：添加空内容检测 + timeout 参数传递
  3. review_layer.py：修复 review_and_fix 方法变量作用域问题
  4. generate_docx_tables.py：修复 LaTeX 块公式、单行公式、行内公式解析
  5. 本脚本：整合所有模块为统一入口

改进记录（2026-05-23）：
  6. econometrics.py：新增程序化回归引擎，真实表格由 statsmodels 计算，不依赖 AI 生成数字
  7. 表格由 RegressionTable.to_markdown() 程序化生成，确保数字真实可靠
  8. prompt 中明确标注"以下所有表格均为程序化计算结果，请直接引用"
"""

import os
import re
import sys
import time
import json
import argparse
import warnings
import subprocess
from pathlib import Path

# ── Keychain 密钥加载 ──────────────────────────────────────
def _get_from_keychain(service: str, account: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service,
             "-a", account, "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None

for _env_name, (_svc, _acct) in [
    ("DEEPSEEK_API_KEY", ("论文工作流", "DEEPSEEK_API_KEY")),
]:
    val = _get_from_keychain(_svc, _acct)
    if val:
        os.environ[_env_name] = val

# ── 路径设置 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
CACHE_DIR = PROJECT_ROOT / ".cache" / "paper_pipeline"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── 环境加载 ──────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env.local", override=False)

import openai

# ── 实证数据路径 ──────────────────────────────────────────────
TARIFF_RESULTS = PROJECT_ROOT / "tariff_research" / "results" / "tables"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ════════════════════════════════════════════════════════════════
# 第1步：加载实证数据
# ════════════════════════════════════════════════════════════════

def load_empirical_data() -> dict:
    """加载所有实证分析结果，用于嵌入论文 prompt。"""
    try:
        from scripts.generate_empirical_tables import load_tables_from_files
        tables = load_tables_from_files()
        if not any(tables.values()):
            from scripts.generate_empirical_tables import generate_all_tables
            print("  首次运行先生成实证表格...")
            generate_all_tables()
            tables = load_tables_from_files()
    except Exception as e:
        print("  表格加载失败，使用 CSV 降级方案: " + str(e))
        tables = _fallback_csv_data()
    return {
        "core_findings": tables.get("core_findings_md", ""),
        "core_findings_md": tables.get("core_findings_md", ""),
        "did_summary": tables.get("did_summary_md", ""),
        "did_summary_md": tables.get("did_summary_md", ""),
        "heterogeneity": tables.get("heterogeneity_md", ""),
        "heterogeneity_md": tables.get("heterogeneity_md", ""),
        "mediation": tables.get("mediation_md", ""),
        "mediation_md": tables.get("mediation_md", ""),
        "descriptive": tables.get("descriptive_md", ""),
        "descriptive_md": tables.get("descriptive_md", ""),
        "robustness_placebo": "",
        "robustness_window": tables.get("robustness_md", ""),
        "innovation_offset": "",
        "final_summary": "",
    }


def _fallback_csv_data() -> dict:
    """降级方案：从旧 CSV 文件加载（格式可能不完美）"""
    def read_csv(name):
        p = TARIFF_RESULTS / (name + ".csv")
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""
    def csv_to_md(text):
        if not text.strip(): return ""
        lines = text.strip().split("\n")
        if len(lines) < 2: return text
        hdrs = [h.strip() for h in lines[0].lstrip(",").split(",")]
        sep = "| " + " | ".join(hdrs) + " |"
        sep2 = "| " + " | ".join(["---"] * len(hdrs)) + " |"
        rows = []
        for ln in lines[1:]:
            cells = [c.strip() for c in ln.lstrip(",").split(",")]
            rows.append("| " + " | ".join(cells) + " |")
        return sep + "\n" + sep2 + "\n" + "\n".join(rows)
    return {
        "core_findings_md": csv_to_md(read_csv("core_findings")),
        "did_summary_md": csv_to_md(read_csv("did_results_summary")),
        "heterogeneity_md": csv_to_md(read_csv("heterogeneity_results")),
        "mediation_md": csv_to_md(read_csv("mediation_effects")),
        "descriptive_md": csv_to_md(read_csv("descriptive_statistics")),
        "robustness_md": csv_to_md(read_csv("robustness_placebo")),
    }

def build_paper_prompt(data: dict) -> str:
    """构建完整的论文生成 prompt（含实证数据）。"""
    return f"""你是一位专业经济学论文写作者。请撰写一篇完整的学术论文（中文，约12000字）。

## 重要声明
以下所有回归表格均为程序化统计计算结果（statsmodels 引擎），每个系数、标准误、t值、p值、R方和样本量均由回归程序直接输出，**请严格直接引用，不得修改任何数值，不得删减列，不得补充任何未给出的数值**。

## 论文主题
关税政策变化的影响机制与效应研究——基于消费、贸易、生产、收入、产业与技术创新六维度的实证分析

## 论文结构要求
1. 摘要（约400字，中英文）
2. 引言（约1500字）：研究背景、问题提出、边际贡献
3. 文献综述（约2000字）：关税政策、贸易效应、创新研究
4. 理论框架与研究假设（约1500字）：六维度机制推导假设
5. 研究设计（约1500字）：数据来源、模型设定、变量定义
6. 实证结果（约2000字）：含下方所有回归表格
7. 稳健性检验（约1000字）：安慰剂检验、样本窗口检验
8. 异质性分析（约1000字）
9. 结论与政策启示（约500字）
10. 参考文献（15-20篇）

## 程序化计算结果（原文引用，不得修改）

### 描述性统计
{data['descriptive_md']}

### 核心发现（Hypothesis检验结果）
{data['core_findings_md']}

### DID基准回归（政策净效应）
{data['did_summary_md']}

### 异质性分析
{data['heterogeneity_md']}

### 中介效应分解
{data['mediation_md']}

## 写作要求
1. 表格用标准三线表格式（表头加粗，内容居中/左对齐）
2. 显著性标注：*** p<0.01, ** p<0.05, * p<0.1
3. 所有数据必须严格来自上方程序化计算结果，不编造任何数字
4. 公式使用 $$...$$ 或 LaTeX 环境
5. 参考文献格式：APA
6. 描述回归结果时，必须引用表格中的具体系数值（如"核心解释变量系数为 0.034***，在1%水平上显著"）
7. 稳健性检验需要说明每种方法的结论是否与基准回归一致
"""


def call_deepseek(prompt: str, system: str = "", temperature: float = 0.7,
                  max_tokens: int = 8192, timeout: int = 180) -> str:
    """
    直接调用 DeepSeek API（绕开 ai_router 避免挂起）。
    实测 deepseek-v4-pro / v4-flash / reasoner 全部返回空内容，
    只用 deepseek-chat 可正常工作。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请在 .env.local 中配置")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        timeout=timeout,
    )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model="deepseek-chat",  # 实测唯一可用的模型名
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(
            "DeepSeek 返回空内容。请检查 API Key、网络连接，"
            "或确认是否触发了频率限制。"
        )
    return content


def generate_paper(data: dict, use_cache: bool = True) -> str:
    """生成论文正文。"""
    cache_file = CACHE_DIR / "paper_draft.md"

    if use_cache and cache_file.exists():
        print(f"📦 使用缓存论文草稿: {cache_file.name}")
        return cache_file.read_text(encoding="utf-8")

    print("🖊️  正在生成论文（deepseek-chat，可能需要 30-60 秒）...")
    t0 = time.time()

    prompt = build_paper_prompt(data)
    paper = call_deepseek(
        prompt=prompt,
        system="你是一位专业经济学论文写作专家，擅长撰写顶刊级别的实证研究论文。",
        temperature=0.7,
        max_tokens=8192,
        timeout=180,
    )

    elapsed = time.time() - t0
    print(f"✅ 论文生成完成，耗时 {elapsed:.1f}s，字数 {len(paper)}")

    cache_file.write_text(paper, encoding="utf-8")
    print(f"📦 已缓存至: {cache_file.name}")
    return paper


# ════════════════════════════════════════════════════════════════
# 第3步：去AI化润色
# ════════════════════════════════════════════════════════════════

DE_AI_PROMPT = """你是一位资深经济学论文编辑，精通学术写作规范。
请对以下论文进行深度语言润色，去除所有AI写作痕迹，使语言更加自然、流畅，
符合人类学者写作风格。

## 具体要求
1. 删除所有AI惯用开场白（如"首先"、"值得注意的是"、"从上述分析可以看出"）
2. 删除所有过渡句式机器人特征（如"接下来"、"此外"、"综上所述"）
3. 删除所有过度自信的表达（如"毫无疑问"、"显然"、"毋庸置疑"）
4. 删除所有机械的连接词堆砌（如"而且"、"并且"、"同时"）
5. 删除所有空洞的总结句（如"综上所述，本文研究了..."）
6. 减少"研究结果表明"、"本文发现"等机械重复
7. 用更自然的学术表达替换以上所有模式
8. 保持所有数据、表格、公式、参考文献完全不变
9. 仅润色语言，不改变任何实质内容

请直接输出润色后的完整论文，不要添加任何说明文字。"""


def de_ai_polish(paper: str, use_cache: bool = True) -> str:
    """去除论文的AI写作痕迹。"""
    cache_file = CACHE_DIR / "paper_de_ai.md"

    if use_cache and cache_file.exists():
        print(f"📦 使用缓存润色版本: {cache_file.name}")
        return cache_file.read_text(encoding="utf-8")

    print("🖊️  正在进行去AI化润色（deepseek-chat）...")
    t0 = time.time()

    polished = call_deepseek(
        prompt=f"【待润色论文】\n\n{paper}",
        system=DE_AI_PROMPT,
        temperature=0.3,
        max_tokens=8192,
        timeout=180,
    )

    elapsed = time.time() - t0
    print(f"✅ 去AI润色完成，耗时 {elapsed:.1f}s")

    cache_file.write_text(polished, encoding="utf-8")
    print(f"📦 已缓存至: {cache_file.name}")
    return polished


# ════════════════════════════════════════════════════════════════
# 第4步：生成 Word 文档（含三线表）
# ════════════════════════════════════════════════════════════════

def generate_word(paper: str) -> Path:
    """将 Markdown 论文转换为 Word 三线表文档。"""
    # 复用已修复的 generate_docx_tables.py 逻辑
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from generate_docx_tables import md_to_docx

    output_file = OUTPUT_DIR / "关税政策影响研究_最终版.docx"
    print(f"📄 正在生成 Word 文档（含三线表）...")
    t0 = time.time()

    md_to_docx(paper, str(output_file))

    elapsed = time.time() - t0
    print(f"✅ Word 文档生成完成，耗时 {elapsed:.1f}s")
    return output_file


# ════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="论文全流程管道")
    parser.add_argument("--no-cache", action="store_true",
                        help="跳过缓存，强制重新生成")
    parser.add_argument("--skip-polish", action="store_true",
                        help="跳过去AI润色步骤")
    parser.add_argument("--skip-docx", action="store_true",
                        help="跳过Word文档生成")
    parser.add_argument("--save-markdown", action="store_true",
                        help="保存中间 Markdown 文件到 output/")
    args = parser.parse_args()

    use_cache = not args.no_cache

    print("=" * 60)
    print("📊 论文全流程管道 v2.0（2026-05-21）")
    print("=" * 60)

    # Step 1: 加载数据
    print("\n📂 Step 1/4: 加载实证数据...")
    data = load_empirical_data()
    print(f"   加载了 {sum(1 for v in data.values() if v)} 个数据文件")

    # Step 2: 生成论文
    print("\n🖊️  Step 2/4: 生成论文草稿...")
    paper = generate_paper(data, use_cache=use_cache)

    # Step 3: 去AI润色
    if args.skip_polish:
        print("\n⏭️  Step 3/4: 跳过去AI润色")
        final_paper = paper
    else:
        print("\n🖊️  Step 3/4: 去AI化润色...")
        final_paper = de_ai_polish(paper, use_cache=use_cache)

    # 保存 Markdown
    if args.save_markdown:
        ts = time.strftime("%Y%m%d_%H%M%S")
        md_path = OUTPUT_DIR / f"关税政策影响研究_{ts}.md"
        md_path.write_text(final_paper, encoding="utf-8")
        print(f"   Markdown 已保存: {md_path.name}")

    # Step 4: Word
    if args.skip_docx:
        print("\n⏭️  Step 4/4: 跳过 Word 生成")
        print("\n✅ 流程完成！")
        return

    print("\n📄 Step 4/4: 生成 Word 文档（含三线表）...")
    word_path = generate_word(final_paper)

    print("\n" + "=" * 60)
    print(f"✅ 全部完成！")
    print(f"   Word 文档: {word_path}")
    print("=" * 60)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    sys.exit(main())
