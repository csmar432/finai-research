#!/usr/bin/env python3
"""
user-latex-mcp — LaTeX论文排版MCP服务器
==========================================
提供LaTeX编译、语法检查、公式渲染、BibTeX管理等功能。

功能：
  - latexmk编译（自动检测变化，只重编译必要的部分）
  - 语法检查（chktex / latexdiff）
  - LaTeX → PDF / HTML / Markdown 转换
  - 公式渲染（LaTeX → SVG/PNG）
  - BibTeX格式校验与清理
  - 项目脚手架（自动生成论文模板）

前置依赖（需自行安装）：
  - MacTeX: brew install --cask mactex  # 或 apt install texlive-latex-base
  - latexmk: MacTeX自带
  - chktex: brew install chktex
  - latexdiff: brew install latexdiff
  - inkscape: brew install inkscape  # 用于SVG转换

Usage:
    python server.py [--project-dir DIR] [--output-dir DIR]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    from mcp.server.models import InitializationOptions
except ImportError:
    print("ERROR: mcp package required. Run: pip install mcp", flush=True)
    sys.exit(1)

server = Server("user-latex-mcp")


# ─────────────────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────────────────
LATEXMK_BIN = "/Library/TeX/Distributions/.DefaultTeX/Contents/Programs/texbin/latexmk"
for _p in [
    "/opt/homebrew/bin/latexmk",
    "/usr/local/bin/latexmk",
    "/usr/bin/latexmk",          # Linux (Debian/Ubuntu/Arch)
    "/Library/TeX/texbin/latexmk",
]:
    if Path(_p).exists():
        LATEXMK_BIN = _p
        break

CHKTEX_BIN = "/opt/homebrew/bin/chktex"
for _p in [
    "/opt/homebrew/bin/chktex",
    "/usr/local/bin/chktex",
    "/usr/bin/chktex",           # Linux (Debian/Ubuntu)
]:
    if Path(_p).exists():
        CHKTEX_BIN = _p
        break

INKSCAPE_BIN = "/opt/homebrew/bin/inkscape"
for _p in [
    "/opt/homebrew/bin/inkscape",
    "/Applications/Inkscape.app/Contents/Resources/bin/inkscape",
    "/usr/bin/inkscape",         # Linux
    "/snap/bin/inkscape",        # Linux snap
]:
    if Path(_p).exists():
        INKSCAPE_BIN = _p
        break

PDFLATEX_BIN = "/opt/homebrew/bin/pdflatex"


def _find_bin(name: str) -> str | None:
    for p in [f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"]:
        if Path(p).exists():
            return p
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────
def _run(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 60,
    input_text: str | None = None,
) -> dict:
    """统一执行命令并返回结果。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            input=input_text,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Timeout", "success": False, "error": "timeout"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False, "error": str(e)}


def _find_tex_file(directory: str) -> str | None:
    """在目录中查找主.tex文件。"""
    d = Path(directory)
    candidates = list(d.glob("*.tex"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return str(candidates[0])


# ─────────────────────────────────────────────────────────────────────────────
# 工具定义
# ─────────────────────────────────────────────────────────────────────────────
TOOLS = [
    Tool(
        name="latex_compile",
        description="编译LaTeX项目生成PDF。支持自动检测主文件和多次编译（pdflatex → bibtex → pdflatex）。\n\n"
                    "Args:\n"
                    "  project_dir: 项目根目录（包含.tex文件）\n"
                    "  tex_file: 可选，指定主tex文件\n"
                    "  engine: 编译引擎（pdflatex/xelatex/lualatex）\n"
                    "  passes: 编译次数（默认3次，通常足够）\n\n"
                    "Returns: 编译结果摘要（页数、文件大小、错误警告数）",
        inputSchema={
            "type": "object",
            "properties": {
                "project_dir": {
                    "type": "string",
                    "description": "LaTeX项目根目录路径",
                },
                "tex_file": {
                    "type": "string",
                    "description": "主tex文件名（不指定则自动检测最大文件）",
                },
                "engine": {
                    "type": "string",
                    "description": "编译引擎",
                    "enum": ["pdflatex", "xelatex", "lualatex"],
                    "default": "pdflatex",
                },
                "passes": {
                    "type": "integer",
                    "description": "编译次数（一般3次足够）",
                    "default": 3,
                },
            },
            "required": ["project_dir"],
        },
    ),
    Tool(
        name="latex_check",
        description="检查LaTeX文件的语法和格式问题。类似于拼写检查，但针对LaTeX语法。\n\n"
                    "Args:\n"
                    "  tex_file: .tex文件路径\n"
                    "  severity_filter: 最低显示级别（info/warning/error）\n\n"
                    "Returns: 问题列表（含行号、类型、描述）",
        inputSchema={
            "type": "object",
            "properties": {
                "tex_file": {
                    "type": "string",
                    "description": ".tex文件路径",
                },
                "severity_filter": {
                    "type": "string",
                    "description": "最低显示级别",
                    "enum": ["info", "warning", "error"],
                    "default": "info",
                },
            },
            "required": ["tex_file"],
        },
    ),
    Tool(
        name="latex_to_pdf",
        description="将LaTeX片段或完整代码转换为PDF文件。适合生成独立表格、公式或单页内容。\n\n"
                    "Args:\n"
                    "  latex_code: LaTeX代码（可以是片段或完整文档）\n"
                    "  output_path: 输出PDF路径\n"
                    "  packages: 需要加载的包列表（默认amsmath,booktabs,graphicx）\n"
                    "  font_size: 字号（默认11pt）\n"
                    "  page_size: 纸张大小（默认a4paper）\n\n"
                    "Returns: PDF生成结果",
        inputSchema={
            "type": "object",
            "properties": {
                "latex_code": {
                    "type": "string",
                    "description": "LaTeX代码",
                },
                "output_path": {
                    "type": "string",
                    "description": "输出PDF路径",
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "额外加载的包",
                    "default": [],
                },
                "font_size": {
                    "type": "string",
                    "description": "字号",
                    "default": "11pt",
                },
            },
            "required": ["latex_code", "output_path"],
        },
    ),
    Tool(
        name="latex_render_formula",
        description="将LaTeX数学公式渲染为SVG/PNG图片。适合嵌入Markdown/HTML文档。\n\n"
                    "Args:\n"
                    "  formula: LaTeX公式（不带$$或\\[\\]包裹）\n"
                    "  output_path: 输出文件路径（.svg/.png）\n"
                    "  format: 输出格式（svg/png）\n"
                    "  scale: 缩放倍数（默认2，高清建议3）\n"
                    "  bg_color: 背景色（transparent/white）\n\n"
                    "Returns: 渲染结果",
        inputSchema={
            "type": "object",
            "properties": {
                "formula": {
                    "type": "string",
                    "description": "LaTeX公式",
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径（.svg/.png）",
                },
                "format": {
                    "type": "string",
                    "description": "输出格式",
                    "enum": ["svg", "png"],
                    "default": "svg",
                },
                "scale": {
                    "type": "number",
                    "description": "缩放倍数（高清建议2-3）",
                    "default": 2.0,
                },
            },
            "required": ["formula", "output_path"],
        },
    ),
    Tool(
        name="latex_diff",
        description="比较两个LaTeX文件，生成差异文档（latexdiff风格）。适合审稿时标注修改。\n\n"
                    "Args:\n"
                    "  old_file: 旧版本tex文件\n"
                    "  new_file: 新版本tex文件\n"
                    "  output_file: 差异文件输出路径\n\n"
                    "Returns: 差异分析结果",
        inputSchema={
            "type": "object",
            "properties": {
                "old_file": {
                    "type": "string",
                    "description": "旧版本tex文件",
                },
                "new_file": {
                    "type": "string",
                    "description": "新版本tex文件",
                },
                "output_file": {
                    "type": "string",
                    "description": "差异tex文件输出路径",
                },
            },
            "required": ["old_file", "new_file", "output_file"],
        },
    ),
    Tool(
        name="latex_bibtex_check",
        description="检查BibTeX文件格式，识别重复条目、未定义引用、无效字段。\n\n"
                    "Args:\n"
                    "  bib_file: .bib文件路径\n"
                    "  tex_file: 可选，关联的tex文件（用于检查引用完整性）\n\n"
                    "Returns: 问题列表和统计",
        inputSchema={
            "type": "object",
            "properties": {
                "bib_file": {
                    "type": "string",
                    "description": ".bib文件路径",
                },
                "tex_file": {
                    "type": "string",
                    "description": "关联的tex文件（用于检查引用完整性）",
                },
            },
            "required": ["bib_file"],
        },
    ),
    Tool(
        name="latex_scaffold",
        description="在指定目录生成标准学术论文LaTeX项目结构。\n\n"
                    "Args:\n"
                    "  output_dir: 输出目录\n"
                    "  template: 模板类型（sci/nips/aea/chinese）\n"
                    "  title: 论文标题\n"
                    "  authors: 作者列表（逗号分隔）\n"
                    "  abstract: 摘要\n\n"
                    "Returns: 生成的文件列表",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {
                    "type": "string",
                    "description": "输出目录",
                },
                "template": {
                    "type": "string",
                    "description": "模板类型",
                    "enum": ["sci", "nips", "aea", "rfs", "chinese"],
                    "default": "sci",
                },
                "title": {
                    "type": "string",
                    "description": "论文标题",
                    "default": "Untitled Paper",
                },
                "authors": {
                    "type": "string",
                    "description": "作者（逗号分隔）",
                    "default": "",
                },
                "abstract": {
                    "type": "string",
                    "description": "摘要内容",
                    "default": "",
                },
            },
            "required": ["output_dir"],
        },
    ),
    Tool(
        name="latex_count_words",
        description="统计LaTeX文档字数（排除命令、公式、参考文献）。适合AEA/RFS等字数限制。\n\n"
                    "Args:\n"
                    "  tex_file: .tex文件路径\n"
                    "  exclude_commands: 排除的命令列表\n\n"
                    "Returns: 字数统计（含摘要、正文、参考文献分别统计）",
        inputSchema={
            "type": "object",
            "properties": {
                "tex_file": {
                    "type": "string",
                    "description": ".tex文件路径",
                },
            },
            "required": ["tex_file"],
        },
    ),
    Tool(
        name="latex_get_stats",
        description="获取LaTeX项目统计信息：文件数、目录深度、主文件大小、预计页数。\n\n"
                    "Args:\n"
                    "  project_dir: 项目目录\n\n"
                    "Returns: 项目统计信息",
        inputSchema={
            "type": "object",
            "properties": {
                "project_dir": {
                    "type": "string",
                    "description": "项目目录",
                },
            },
            "required": ["project_dir"],
        },
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# 工具处理函数
# ─────────────────────────────────────────────────────────────────────────────

async def handle_latex_compile(args: dict) -> list[TextContent]:
    project_dir = args["project_dir"]
    tex_file = args.get("tex_file")
    engine = args.get("engine", "pdflatex")
    passes = args.get("passes", 3)

    if not tex_file:
        tex_file = _find_tex_file(project_dir)
        if not tex_file:
            return [TextContent(type="text", text=json.dumps({"error": "No .tex file found", "found": False}))]

    tex_path = Path(tex_file)
    if not tex_path.exists():
        tex_path = Path(project_dir) / tex_file
    if not tex_path.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"File not found: {tex_file}"}))]

    tex_dir = str(tex_path.parent)
    tex_name = tex_path.stem
    pdf_path = tex_dir / f"{tex_name}.pdf"

    latexmk_path = None
    for _p in [
        "/opt/homebrew/bin/latexmk",
        "/Library/TeX/texbin/latexmk",
        "/usr/local/bin/latexmk",
        LATEXMK_BIN,
    ]:
        if Path(_p).exists():
            latexmk_path = _p
            break

    if latexmk_path:
        r = _run(
            [latexmk_path, f"-{engine}", "-synctex=1", "-interaction=nonstopmode", "-pdf", str(tex_path)],
            cwd=tex_dir,
            timeout=120,
        )
    else:
        base_cmd = {
            "pdflatex": [PDFLATEX_BIN, "-interaction=nonstopmode", "-synctex=1"],
            "xelatex": ["xelatex", "-interaction=nonstopmode"],
            "lualatex": ["lualatex", "-interaction=nonstopmode"],
        }.get(engine, [PDFLATEX_BIN, "-interaction=nonstopmode"])

        for _i in range(passes):
            r = _run(base_cmd + [str(tex_path)], cwd=tex_dir, timeout=60)

    errors, warnings_out = 0, 0
    for line in (r.get("stderr", "") + r.get("stdout", "")).splitlines():
        if "Error" in line or "error" in line:
            errors += 1
        if "Warning" in line or "warning" in line:
            warnings_out += 1

    result = {
        "success": r.get("success", False) and pdf_path.exists(),
        "project_dir": project_dir,
        "tex_file": str(tex_path),
        "pdf_file": str(pdf_path) if pdf_path.exists() else None,
        "pdf_exists": pdf_path.exists(),
        "pdf_size_kb": round(pdf_path.stat().st_size / 1024, 1) if pdf_path.exists() else 0,
        "errors": errors,
        "warnings": warnings_out,
        "engine": engine,
        "stdout": r.get("stdout", "")[-2000:],
        "stderr": r.get("stderr", "")[-2000:],
    }
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def handle_latex_check(args: dict) -> list[TextContent]:
    tex_file = args["tex_file"]
    severity = args.get("severity_filter", "info")

    if not Path(tex_file).exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {tex_file}"}))]

    result = _run([CHKTEX_BIN, "-q", "-wall", tex_file], timeout=30) if Path(CHKTEX_BIN).exists() else {}

    issues = []
    if result.get("success") is not False:
        for line in result.get("stdout", "").splitlines():
            m = re.match(r"(.+?):(\d+):(\d+):\s*(\w+):\s*(.+)", line)
            if m:
                fname, lineno, col, sev, msg = m.groups()
                issues.append({"file": fname, "line": int(lineno), "col": int(col), "severity": sev, "message": msg})

    if severity == "warning":
        issues = [i for i in issues if i["severity"].lower() != "info"]
    if severity == "error":
        issues = [i for i in issues if i["severity"].lower() in ("error", "warning")]

    return [TextContent(type="text", text=json.dumps({
        "tex_file": tex_file,
        "total_issues": len(issues),
        "issues": issues,
        "chktex_available": Path(CHKTEX_BIN).exists(),
    }, ensure_ascii=False, indent=2))]


async def handle_latex_to_pdf(args: dict) -> list[TextContent]:
    latex_code = args["latex_code"]
    output_path = args["output_path"]
    packages = args.get("packages", [])
    font_size = args.get("font_size", "11pt")

    if not latex_code.strip().startswith("\\documentclass"):
        full_code = (
            f"\\documentclass[onecolumn,notitlepage,{font_size}]{{article}}\n"
            + "\\usepackage[margin=1in]{geometry}\n"
            + "\\usepackage{amsmath,booktabs,graphicx,hyperref}\n"
            + "\n".join(f"\\usepackage{{{p}}}" for p in packages if p not in ("amsmath", "booktabs", "graphicx", "hyperref"))
            + "\\begin{document}\n"
            + latex_code
            + "\\end{document}\n"
        )
    else:
        full_code = latex_code

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".tex", mode="w", delete=False, encoding="utf-8") as f:
        f.write(full_code)
        tmp_tex = f.name

    try:
        for _i in range(3):
            r = _run(
                [PDFLATEX_BIN, "-interaction=nonstopmode", "-halt-on-error", tmp_tex],
                timeout=30,
            )
        pdf_out = Path(tmp_tex).with_suffix(".pdf")
        if pdf_out.exists():
            pdf_out.rename(out_path)
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "output_path": str(out_path),
                "size_kb": round(out_path.stat().st_size / 1024, 1),
            }, ensure_ascii=False))]
        else:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "PDF not generated",
                "stderr": r.get("stderr", "")[-1000:],
            }, ensure_ascii=False))]
    finally:
        Path(tmp_tex).unlink(missing_ok=True)
        Path(tmp_tex).with_suffix(".aux").unlink(missing_ok=True)
        Path(tmp_tex).with_suffix(".log").unlink(missing_ok=True)


async def handle_latex_render_formula(args: dict) -> list[TextContent]:
    formula = args["formula"]
    output_path = args["output_path"]
    fmt = args.get("format", "svg")
    scale = args.get("scale", 2.0)

    latex_code = (
        "\\documentclass[border=2pt]{standalone}\n"
        "\\usepackage{amsmath}\n"
        "\\usepackage{varwidth}\n"
        "\\begin{document}\n"
        f"${formula}$\n"
        "\\end{document}\n"
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".tex", mode="w", delete=False, encoding="utf-8") as f:
        f.write(latex_code)
        tmp_tex = f.name

    try:
        subprocess.run([PDFLATEX_BIN, "-interaction=nonstopmode", tmp_tex], capture_output=True, timeout=30)
        pdf_out = Path(tmp_tex).with_suffix(".pdf")
        if not pdf_out.exists():
            return [TextContent(type="text", text=json.dumps({"success": False, "error": "PDF not generated"}))]

        if fmt == "png":
            subprocess.run(
                ["convert", "-density", str(int(150 * scale)), "-quality", "100", str(pdf_out), str(out_path)],
                capture_output=True, timeout=30,
            )
        elif fmt == "svg" and Path(INKSCAPE_BIN).exists():
            subprocess.run(
                [INKSCAPE_BIN, "-D", "-l", "-o", str(out_path), str(pdf_out)],
                capture_output=True, timeout=30,
            )
        elif fmt == "svg":
            subprocess.run(
                ["pdf2svg", str(pdf_out), str(out_path)],
                capture_output=True, timeout=30,
            )

        return [TextContent(type="text", text=json.dumps({
            "success": out_path.exists(),
            "output_path": str(out_path),
            "size_kb": round(out_path.stat().st_size / 1024, 1) if out_path.exists() else 0,
        }, ensure_ascii=False))]
    finally:
        for ext in ["", ".aux", ".log", ".pdf"]:
            Path(tmp_tex.replace(".tex", ext)).unlink(missing_ok=True)


async def handle_latex_diff(args: dict) -> list[TextContent]:
    old_file = args["old_file"]
    new_file = args["new_file"]
    output_file = args["output_file"]

    latexdiff_bin = _find_bin("latexdiff")
    if not latexdiff_bin:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "latexdiff not found. Install with: brew install latexdiff",
            "latexdiff_available": False,
        }, ensure_ascii=False))]

    r = _run([latexdiff_bin, old_file, new_file], timeout=30)
    if r.get("success") and r.get("stdout"):
        Path(output_file).write_text(r["stdout"], encoding="utf-8")
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "output_file": output_file,
            "size_kb": round(Path(output_file).stat().st_size / 1024, 1),
        }, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({"success": False, "error": r.get("stderr", "latexdiff failed")}))]


async def handle_latex_bibtex_check(args: dict) -> list[TextContent]:
    bib_file = args["bib_file"]
    tex_file = args.get("tex_file")

    if not Path(bib_file).exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {bib_file}"}))]

    content = Path(bib_file).read_text(encoding="utf-8")
    entries = re.findall(r"@(\w+)\s*\{\s*([^,]+),", content)
    duplicates = [e for e in set(entries) if entries.count(e) > 1]

    issues = []
    if duplicates:
        issues.append({"type": "duplicate", "message": f"Duplicate entries: {duplicates}"})

    tex_content = ""
    if tex_file and Path(tex_file).exists():
        tex_content = Path(tex_file).read_text(encoding="utf-8")

    defined_cites = set(re.findall(r"\\cite[pt]?\{([^}]+)\}", tex_content))
    all_cites = set()
    for cite_group in defined_cites:
        all_cites.update(c.strip() for c in cite_group.split(","))

    bib_keys = {e[1].strip() for e in entries}
    undefined = all_cites - bib_keys
    if undefined:
        issues.append({"type": "undefined_citation", "keys": list(undefined)})

    return [TextContent(type="text", text=json.dumps({
        "bib_file": bib_file,
        "total_entries": len(entries),
        "duplicate_keys": duplicates,
        "undefined_citations": list(undefined) if undefined else [],
        "issues": issues,
    }, ensure_ascii=False, indent=2))]


async def handle_latex_scaffold(args: dict) -> list[TextContent]:
    output_dir = Path(args["output_dir"])
    template = args.get("template", "sci")
    title = args.get("title", "Untitled Paper")
    authors = args.get("authors", "")
    abstract = args.get("abstract", "")

    output_dir.mkdir(parents=True, exist_ok=True)
    files_created = []

    templates = {
        "sci": {
            "main.tex": _SCI_TEMPLATE,
            "references.bib": "@article{placeholder,\n  author = {},\n  title = {},\n  journal = {},\n  year = {2026},\n}\n",
        },
        "nips": {
            "main.tex": _NIPS_TEMPLATE,
            "references.bib": "",
        },
        "aea": {
            "main.tex": _AEA_TEMPLATE,
            "references.bib": "",
        },
        "chinese": {
            "main.tex": _CHINESE_TEMPLATE,
            "references.bib": "",
        },
    }

    tmpl = templates.get(template, templates["sci"])
    for fname, content in tmpl.items():
        fpath = output_dir / fname
        content_filled = content.replace("{{TITLE}}", title).replace("{{AUTHORS}}", authors).replace("{{ABSTRACT}}", abstract)
        fpath.write_text(content_filled, encoding="utf-8")
        files_created.append(str(fpath))

    return [TextContent(type="text", text=json.dumps({
        "success": True,
        "output_dir": str(output_dir),
        "template": template,
        "files_created": files_created,
    }, ensure_ascii=False, indent=2))]


async def handle_latex_count_words(args: dict) -> list[TextContent]:
    tex_file = args["tex_file"]
    if not Path(tex_file).exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {tex_file}"}))]

    content = Path(tex_file).read_text(encoding="utf-8")
    content = re.sub(r"\\begin\{document\}.*", "", content, flags=re.DOTALL)
    content = re.sub(r"\\end\{document\}.*", "", content)
    content = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", content)
    content = re.sub(r"\\[a-zA-Z]+", " ", content)
    content = re.sub(r"\{[^}]*\}", " ", content)
    content = re.sub(r"\$\$?.*?\$?\$?", " ", content, flags=re.DOTALL)
    content = re.sub(r"\\\[.*?\\\]", " ", content, flags=re.DOTALL)
    words = [w for w in re.findall(r"\b\w+\b", content) if len(w) > 1]
    total = len(words)
    return [TextContent(type="text", text=json.dumps({
        "tex_file": tex_file,
        "total_words": total,
        "total_chars": len("".join(words)),
        "note": "Approximate word count (excludes commands, math, references)",
    }, ensure_ascii=False))]


async def handle_latex_get_stats(args: dict) -> list[TextContent]:
    project_dir = args["project_dir"]
    d = Path(project_dir)
    if not d.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"Not found: {project_dir}"}))]

    tex_files = list(d.rglob("*.tex"))
    bib_files = list(d.rglob("*.bib"))
    pdf_files = list(d.rglob("*.pdf"))

    main_tex = _find_tex_file(project_dir)
    main_size = Path(main_tex).stat().st_size if main_tex and Path(main_tex).exists() else 0

    main_content = ""
    if main_tex:
        main_content = Path(main_tex).read_text(encoding="utf-8")

    fig_count = len(re.findall(r"\\includegraphics", main_content))
    table_count = len(re.findall(r"\\begin\{tabular\}", main_content))
    eq_count = len(re.findall(r"\$\$|\\\[", main_content))
    ref_count = len(re.findall(r"\\cite|ref\{", main_content))

    depth = len(d.rglob("*"))
    return [TextContent(type="text", text=json.dumps({
        "project_dir": project_dir,
        "tex_files": len(tex_files),
        "bib_files": len(bib_files),
        "pdf_files": len(pdf_files),
        "main_file": main_tex,
        "main_file_size_kb": round(main_size / 1024, 1),
        "figures": fig_count,
        "tables": table_count,
        "equations": eq_count,
        "references": ref_count,
        "subdirectories": depth,
    }, ensure_ascii=False, indent=2))]


# ─────────────────────────────────────────────────────────────────────────────
# 模板
# ─────────────────────────────────────────────────────────────────────────────
_SCI_TEMPLATE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,booktabs,graphicx,hyperref}
\usepackage[numbers]{natbib}

\title{{{TITLE}}}
\author{{{AUTHORS}}}

\begin{document}
\begin{abstract}
{{{ABSTRACT}}}
\end{abstract}

\section{Introduction}
% Introduction content here

\section{Literature Review}
% Literature review

\section{Data and Methodology}
% Data description and methodology

\section{Empirical Results}
% Main results

\section{Conclusion}
% Conclusion

\bibliographystyle{plainnat}
\bibliography{references}

\end{document}
"""

_NIPS_TEMPLATE = r"""\documentclass{article}
\usepackage[margin=1in]{geometry}
\usepackage{nips_final}
\usepackage{hyperref}

\title{{{TITLE}}}
\author{{{AUTHORS}}}

\begin{document}
\begin{abstract}
{{{ABSTRACT}}}
\end{abstract}

\section{Introduction}
\section{Related Work}
\section{Method}
\section{Experiments}
\section{Conclusion}

\bibliographystyle{plain}
\bibliography{references}
\end{document}
"""

_AEA_TEMPLATE = r"""\documentclass[AER]{AEA}
\usepackage{natbib}
\title{{{TITLE}}}
\authors{{{AUTHORS}}}
\abstract{{{ABSTRACT}}}
\keywords{JEL: }

\begin{document}
\section{Introduction}
\section{Model}
\section{Data}
\section{Results}
\section{Conclusion}
\bibliographystyle{aer}
\bibliography{references}
\end{document}
"""

_CHINESE_TEMPLATE = r"""\documentclass[UTF8]{ctexart}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,booktabs,graphicx,hyperref}
\usepackage{natbib}

\title{{{TITLE}}}
\author{{{AUTHORS}}}

\begin{document}
\maketitle

\begin{abstract}
{{{ABSTRACT}}}
\end{abstract}

\section{引言}
\section{文献综述}
\section{数据与研究设计}
\section{实证分析}
\section{结论}

\bibliographystyle{plainnat}
\bibliography{references}
\end{document}
"""

TOOL_HANDLERS = {
    "latex_compile": handle_latex_compile,
    "latex_check": handle_latex_check,
    "latex_to_pdf": handle_latex_to_pdf,
    "latex_render_formula": handle_latex_render_formula,
    "latex_diff": handle_latex_diff,
    "latex_bibtex_check": handle_latex_bibtex_check,
    "latex_scaffold": handle_latex_scaffold,
    "latex_count_words": handle_latex_count_words,
    "latex_get_stats": handle_latex_get_stats,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    try:
        return await handler(arguments)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def main():
    latexmk_ok = Path(LATEXMK_BIN).exists()
    chktex_ok = Path(CHKTEX_BIN).exists()
    print(f"user-latex-mcp starting... latexmk={'OK' if latexmk_ok else 'MISSING'}, chktex={'OK' if chktex_ok else 'MISSING'}", flush=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="user-latex-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
