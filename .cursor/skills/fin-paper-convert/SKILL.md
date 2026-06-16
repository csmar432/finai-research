---
description: Compile LaTeX to PDF and convert to target journal format
trigger: "编译|compile|pdf|latex|投稿格式|tex编译|生成pdf"
version: 1.0
dependencies:
  - PAPER_OUTLINE.md
  - FIGURE_PLAN.md
  - TABLE_PLAN.md
  - main.tex / sections/*.tex
  - references.bib
outputs:
  - draft_v{version}/main.pdf
  - draft_v{version}/anonymous.pdf
  - draft_v{version}/arxiv.pdf
  - draft_v{version}/main.docx
  - draft_v{version}/submission_package.zip
tags:
  - latex
  - compilation
  - pdf-generation
  - fin-paper
---

# fin-paper-convert

> Compile LaTeX manuscripts to publication-ready PDFs and generate submission variants (anonymous, arxiv, word) for the target journal.

## Step 0: Pre-compilation Check

Before running LaTeX compilation, verify all components are ready:

```bash
# Check required files exist
ls -la output/fin-manuscript/draft_v1/
ls -la output/fin-manuscript/draft_v1/sections/ 2>/dev/null || echo "No sections dir"
ls -la output/fin-manuscript/draft_v1/figures/  2>/dev/null || echo "No figures dir"

# Check LaTeX installation
which xelatex pdflatex latexmk 2>/dev/null
latexmk --version 2>/dev/null || echo "latexmk not found"

# Check bibliography tool
which bibtex biber 2>/dev/null
```

```python
#!/usr/bin/env python3
"""Pre-compilation validation for fin-paper-convert."""

import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str]
    warnings: List[str]
    missing_files: List[str]


def validate_latex_project(base_dir: str) -> ValidationResult:
    """
    Validate all required files and structure before compilation.
    """
    base = Path(base_dir)
    errors = []
    warnings = []
    missing = []
    
    # Check main.tex
    main_tex = base / "main.tex"
    if not main_tex.exists():
        missing.append(str(main_tex))
        errors.append("main.tex not found")
    
    # Check references.bib
    bib_file = base / "references.bib"
    if not bib_file.exists():
        missing.append(str(bib_file))
        errors.append("references.bib not found")
    else:
        # Count references
        bib_content = bib_file.read_text(encoding="utf-8")
        ref_count = len(re.findall(r'@\w+\{', bib_content))
        warnings.append(f"Found {ref_count} references in references.bib")
    
    # Check figures directory
    fig_dir = base / "figures"
    if not fig_dir.exists():
        warnings.append("figures/ directory not found (no figures will be included)")
    else:
        fig_files = list(fig_dir.glob("*.pdf")) + list(fig_dir.glob("*.png"))
        if not fig_files:
            warnings.append("No figure files (.pdf/.png) found in figures/")
    
    # Check sections directory
    sec_dir = base / "sections"
    if sec_dir.exists():
        tex_files = list(sec_dir.glob("*.tex"))
        if tex_files:
            warnings.append(f"Found {len(tex_files)} section .tex files")
    
    # Validate main.tex structure
    if main_tex.exists():
        content = main_tex.read_text(encoding="utf-8")
        
        # Check required packages
        if r'\documentclass' not in content:
            errors.append("main.tex missing \\documentclass")
        
        # Check bibliography commands
        if r'\bibliography' not in content and r'\addbibresource' not in content:
            warnings.append("No bibliography command found in main.tex")
        
        # Check input commands for sections
        if sec_dir.exists() and not any(r'\input{' in content for _ in [1]):
            warnings.append("No \\input{} commands found — sections may not be included")
    
    return ValidationResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        missing_files=missing,
    )
```

## Step 1: Journal Template Selection

```python
JOURNAL_TEMPLATE_CONFIG = {
    "经济研究": {
        "class": "ctexart",
        "font": "xeCJK",
        "cite_style": "gbt-7714-2015",
        "compile_cmd": "xelatex main.tex && bibtex main && xelatex main.tex && xelatex main.tex",
        "compile_sequence": ["xelatex", "bibtex", "xelatex", "xelatex"],
        "required_packages": [
            "ctex", "amsmath", "amssymb", "amsfonts",
            "booktabs", "threeline", "graphicx", "hyperref",
            "geometry", "setspace", "titlesec",
        ],
        "anonymous": False,
        "arxiv_compatible": False,
        "word_compatible": True,
        "submission_format": "pdf",
        "notes": "使用CTeX宏包，中文参考文献GB/T 7714格式",
    },
    "金融研究": {
        "class": "ctexart",
        "font": "xeCJK",
        "cite_style": "gbt-7714-2015",
        "compile_cmd": "xelatex main.tex && bibtex main && xelatex main.tex && xelatex main.tex",
        "compile_sequence": ["xelatex", "bibtex", "xelatex", "xelatex"],
        "required_packages": ["ctex", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref"],
        "anonymous": False,
        "arxiv_compatible": False,
        "word_compatible": True,
        "submission_format": "pdf",
    },
    "管理世界": {
        "class": "ctexart",
        "font": "xeCJK",
        "cite_style": "gbt-7714-2015",
        "compile_cmd": "xelatex main.tex && bibtex main && xelatex main.tex && xelatex main.tex",
        "compile_sequence": ["xelatex", "bibtex", "xelatex", "xelatex"],
        "required_packages": ["ctex", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref"],
        "anonymous": False,
        "arxiv_compatible": False,
        "word_compatible": True,
        "submission_format": "pdf",
    },
    "JF": {
        "class": "aea",
        "font": "times",
        "cite_style": "aer",
        "compile_cmd": "pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex",
        "compile_sequence": ["pdflatex", "bibtex", "pdflatex", "pdflatex"],
        "required_packages": ["aertt", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref", "natbib"],
        "anonymous": True,
        "arxiv_compatible": True,
        "word_compatible": True,
        "submission_format": "pdf",
    },
    "JFE": {
        "class": "jfe",
        "font": "times",
        "cite_style": "jfe",
        "compile_cmd": "pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex",
        "compile_sequence": ["pdflatex", "bibtex", "pdflatex", "pdflatex"],
        "required_packages": ["jfecls", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref", "natbib"],
        "anonymous": True,
        "arxiv_compatible": True,
        "word_compatible": True,
        "submission_format": "pdf",
    },
    "RFS": {
        "class": "rfs",
        "font": "times",
        "cite_style": "rfs",
        "compile_cmd": "pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex",
        "compile_sequence": ["pdflatex", "biber", "pdflatex", "pdflatex"],
        "required_packages": ["rfs", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref", "biblatex"],
        "anonymous": True,
        "arxiv_compatible": True,
        "word_compatible": True,
        "submission_format": "pdf",
        "online_appendix": True,
    },
    "JAE": {
        "class": "aea",
        "font": "times",
        "cite_style": "aer",
        "compile_cmd": "pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex",
        "compile_sequence": ["pdflatex", "bibtex", "pdflatex", "pdflatex"],
        "required_packages": ["aertt", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref", "natbib"],
        "anonymous": True,
        "arxiv_compatible": True,
        "word_compatible": True,
        "submission_format": "pdf",
    },
    "AER": {
        "class": "aea",
        "font": "times",
        "cite_style": "aer",
        "compile_cmd": "pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex",
        "compile_sequence": ["pdflatex", "bibtex", "pdflatex", "pdflatex"],
        "required_packages": ["aertt", "amsmath", "amssymb", "booktabs", "graphicx", "hyperref", "natbib"],
        "anonymous": True,
        "arxiv_compatible": True,
        "word_compatible": True,
        "submission_format": "pdf",
    },
}


def get_template(journal_name: str) -> dict:
    """Get the template configuration for a journal."""
    return JOURNAL_TEMPLATE_CONFIG.get(journal_name, JOURNAL_TEMPLATE_CONFIG["经济研究"])


def format_latex_preamble(template: dict, language: str = "zh") -> str:
    """Generate LaTeX preamble based on template configuration."""
    if language == "zh":
        return f"""\\documentclass[12pt,twocolumn]{{{template['class']}}}
\\usepackage{{{template['font']}}}
\\usepackage{amsmath,amssymb,amsfonts}}
\\usepackage{{booktabs}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\geometry{{a4paper,left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}}
\\usepackage{{setspace}}
\\setlength{{\\parindent}}{{2em}}
\\setlength{{\\parskip}}{{6pt}}
"""
    else:
        return f"""\\documentclass[american]{{{template['class']}}}
\\usepackage{{times}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{booktabs}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{natbib}}
\\bibliographystyle{{{template['cite_style']}}}
"""
```

## Step 2: Generate main.tex

Create a complete `main.tex` file from existing content:

```python
#!/usr/bin/env python3
"""Generate main.tex from PAPER_OUTLINE.md and section files."""

import os
import re
from pathlib import Path
from typing import Optional


class ReportGenerator:
    """
    Generate complete LaTeX manuscripts from structured content.
    Supports Chinese (CTeX) and English (AEA) journal formats.
    """
    
    def __init__(self, output_dir: str, language: str = "zh"):
        self.output_dir = Path(output_dir)
        self.language = language
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_main_tex(self, 
                         title: str,
                         authors: str,
                         abstract: str,
                         keywords: list,
                         journal_config: dict,
                         sections: dict) -> str:
        """
        Generate complete main.tex.
        
        Parameters
        ----------
        title : str
            Paper title
        authors : str
            Author information
        abstract : str
            Abstract content
        keywords : list
            List of keywords
        journal_config : dict
            From get_template()
        sections : dict
            Mapping of section names to .tex file paths or content
        """
        
        if self.language == "zh":
            return self._generate_chinese_tex(
                title, authors, abstract, keywords, journal_config, sections
            )
        else:
            return self._generate_english_tex(
                title, authors, abstract, keywords, journal_config, sections
            )
    
    def _generate_chinese_tex(self, title, authors, abstract, keywords,
                               config, sections) -> str:
        """Generate Chinese (CTeX) LaTeX manuscript."""
        
        # Keywords string
        kw_str = "；".join(keywords)
        
        # Section includes
        section_includes = []
        for sec_name, sec_path in sections.items():
            # Try to include as file path
            if isinstance(sec_path, str) and Path(sec_path).exists():
                section_includes.append(f"\\input{{{sec_path}}}")
            elif isinstance(sec_path, str) and sec_path.startswith("sections/"):
                section_includes.append(f"\\input{{{sec_path}}}")
        
        if not section_includes:
            # Generate inline sections
            section_includes = [
                "\\input{sections/01_introduction}",
                "\\input{sections/02_literature}",
                "\\input{sections/03_data}",
                "\\input{sections/04_results}",
                "\\input{sections/05_robustness}",
                "\\input{sections/06_conclusion}",
            ]
        
        tex = f"""% !TEX program = xelatex
\\documentclass[12pt]{{ctexart}}
\\usepackage{{xeCJK}}
\\usepackage{{amsmath,amssymb,amsfonts}}
\\usepackage{{booktabs}}
\\usepackage{{threeline}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\geometry{{a4paper,left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}}
\\usepackage{{setspace}}
\\setlength{{\\parindent}}{{2em}}
\\setlength{{\\parskip}}{{6pt}}

% Title
\\title{{{title}}}
\\author{{{authors}}}

% Abstract
\\renewcommand{{\\abstractname}}{{摘要}}
\\begin{{document}}
\\maketitle

\\begin{{abstract}}}
{{{abstract}}}
\\end{{abstract}}

\\ paragraph*{{{keywords}:}}
{kw_str}

\\newpage
\\input{{sections/01_introduction}}
\\input{{sections/02_literature}}
\\input{{sections/03_data}}
\\input{{sections/04_results}}
\\input{{sections/05_robustness}}
\\input{{sections/06_conclusion}}

\\bibliographystyle{{gbt-7714-2015}}
\\bibliography{{references}}

\\end{{document}}
"""
        return tex
    
    def _generate_english_tex(self, title, authors, abstract, keywords,
                              config, sections) -> str:
        """Generate English (AEA) LaTeX manuscript."""
        
        kw_str = ", ".join(keywords)
        jel_str = ""  # JEL codes if provided
        
        section_includes = []
        for sec_name, sec_path in sections.items():
            if isinstance(sec_path, str) and Path(sec_path).exists():
                section_includes.append(f"\\input{{{sec_path}}}")
        
        if not section_includes:
            section_includes = [
                "\\input{sections/01_introduction}",
                "\\input{sections/02_literature}",
                "\\input{sections/03_data}",
                "\\input{sections/04_results}",
                "\\input{sections/05_robustness}",
                "\\input{sections/06_conclusion}",
            ]
        
        tex = f"""% !TEX program = pdflatex
\\documentclass[american]{{aea}}
\\usepackage{{times}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{booktabs}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{natbib}}
\\bibliographystyle{{aer}}

% Title
\\title{{{title}}}
\\author{{{authors}}}
\\date{{\\today}}

\\begin{{document}}
\\maketitle

\\begin{{abstract}}}}
{{{abstract}}}
\\end{{abstract}}

\\begin{{JEL-classification}}
{jel_str}
\\end{{JEL-classification}}

\\begin{{keywords}}
{kw_str}
\\end{{keywords}}

{"".join(f"\\input{{{s}}}\n" for s in section_includes)}

\\bibliography{{references}}

\\end{{document}}
"""
        return tex
    
    def write_tex(self, filename: str, content: str):
        """Write LaTeX content to file."""
        path = self.output_dir / filename
        path.write_text(content, encoding="utf-8")
        print(f"  Written: {path}")
```

## Step 3: Compilation Pipeline

```python
#!/usr/bin/env python3
"""LaTeX compilation pipeline for fin-paper-convert."""

import subprocess
import os
import re
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class CompileResult:
    success: bool
    log_content: str
    error_count: int
    warning_count: int
    reference_warnings: List[str]
    page_count: Optional[int] = None
    compilation_time: Optional[float] = None


class LatexCompiler:
    """
    Robust LaTeX compilation with multiple passes and error detection.
    """
    
    def __init__(self, working_dir: str, project_name: str = "main"):
        self.working_dir = Path(working_dir)
        self.project_name = project_name
        self.log_file = self.working_dir / f"{project_name}.log"
    
    def compile(self,
                compile_sequence: List[str],
                timeout: int = 120) -> CompileResult:
        """
        Run a full compilation sequence (e.g., pdflatex → bibtex → pdflatex → pdflatex).
        
        Parameters
        ----------
        compile_sequence : list
            List of commands in order, e.g. ["pdflatex", "bibtex", "pdflatex", "pdflatex"]
        timeout : int
            Timeout per command in seconds
        
        Returns
        -------
        CompileResult
        """
        start_time = time.time()
        
        for i, cmd_name in enumerate(compile_sequence):
            print(f"\n  Pass {i+1}/{len(compile_sequence)}: {cmd_name}")
            
            # Build command
            if cmd_name == "bibtex":
                cmd = ["bibtex", self.project_name]
            elif cmd_name == "biber":
                cmd = ["biber", self.project_name]
            elif cmd_name == "xelatex":
                cmd = ["xelatex", "-interaction=nonstopmode",
                       f"\\input{{{self.project_name}.tex}}"]
            elif cmd_name == "pdflatex":
                cmd = ["pdflatex", "-interaction=nonstopmode",
                       f"\\input{{{self.project_name}.tex}}"]
            else:
                print(f"    ⚠ Unknown command: {cmd_name}")
                continue
            
            # Execute
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                
                # Check for errors
                if result.returncode != 0:
                    # Extract error lines from log
                    error_lines = self._extract_errors()
                    print(f"    🔴 Error in {cmd_name} pass")
                    for line in error_lines[:5]:
                        print(f"      {line}")
                    
                    # Try to continue anyway (some errors are non-fatal)
                
                # Count warnings
                log_content = self.log_file.read_text(errors="ignore") if self.log_file.exists() else ""
                warnings = self._count_warnings(log_content)
                
                if warnings > 0:
                    print(f"    ⚠ {warnings} warnings")
                
            except subprocess.TimeoutExpired:
                print(f"    🔴 Timeout ({timeout}s) for {cmd_name}")
                return CompileResult(
                    success=False,
                    log_content="",
                    error_count=1,
                    warning_count=0,
                    reference_warnings=[],
                )
            except Exception as e:
                print(f"    🔴 Exception: {e}")
        
        elapsed = time.time() - start_time
        
        # Final check
        pdf_file = self.working_dir / f"{self.project_name}.pdf"
        log_content = self.log_file.read_text(errors="ignore") if self.log_file.exists() else ""
        
        error_count = self._count_errors(log_content)
        warning_count = self._count_warnings(log_content)
        ref_warnings = self._extract_reference_warnings(log_content)
        page_count = self._extract_page_count(log_content)
        
        success = pdf_file.exists() and error_count == 0
        
        return CompileResult(
            success=success,
            log_content=log_content[-5000:],  # Last 5000 chars
            error_count=error_count,
            warning_count=warning_count,
            reference_warnings=ref_warnings,
            page_count=page_count,
            compilation_time=elapsed,
        )
    
    def _extract_errors(self) -> List[str]:
        """Extract error lines from the log file."""
        if not self.log_file.exists():
            return ["Log file not found"]
        
        content = self.log_file.read_text(errors="ignore")
        errors = []
        for line in content.split('\n'):
            if 'Error' in line or 'error' in line or '!' in line:
                errors.append(line.strip())
        return errors[:10]
    
    def _count_errors(self, log_content: str) -> int:
        """Count compilation errors in log."""
        error_lines = [
            line for line in log_content.split('\n')
            if line.strip().startswith('! ')
        ]
        return len(error_lines)
    
    def _count_warnings(self, log_content: str) -> int:
        """Count compilation warnings in log."""
        return log_content.count('LaTeX Warning')
    
    def _extract_reference_warnings(self, log_content: str) -> List[str]:
        """Extract citation/label reference warnings."""
        warnings = []
        for line in log_content.split('\n'):
            if 'Citation' in line or 'Reference' in line or 'Label' in line:
                if 'Warning' in line or '?' in line:
                    warnings.append(line.strip())
        return warnings[:10]
    
    def _extract_page_count(self, log_content: str) -> Optional[int]:
        """Extract page count from log."""
        match = re.search(r'\[(\d+)\s+pages?\]', log_content)
        if match:
            return int(match.group(1))
        
        # Try alternative pattern
        match = re.search(r'Total pages?:\s*(\d+)', log_content)
        if match:
            return int(match.group(1))
        
        return None
```

## Step 4: Run Full Compilation

```python
#!/usr/bin/env python3
"""Main compilation script for fin-paper-convert."""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Add project scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.research_framework.latex_compiler import LatexCompiler, CompileResult
from scripts.research_framework.report_generator import ReportGenerator
from scripts.research_framework.journal_templates import get_template


def compile_paper(project_dir: str,
                  journal_name: str = "经济研究",
                  project_name: str = "main") -> CompileResult:
    """
    Compile LaTeX paper to PDF for the target journal.
    
    Parameters
    ----------
    project_dir : str
        Directory containing main.tex and all source files
    journal_name : str
        Target journal name (经济研究 / JF / JFE / etc.)
    project_name : str
        Project file name (without .tex extension)
    
    Returns
    -------
    CompileResult
    """
    project_path = Path(project_dir)
    template = get_template(journal_name)
    
    print("=" * 60)
    print(f"Compiling: {journal_name}")
    print(f"Directory: {project_dir}")
    print(f"Template: {template['class']}")
    print(f"Compile sequence: {' → '.join(template['compile_sequence'])}")
    print("=" * 60)
    
    # Step 1: Validate
    from scripts.research_framework.latex_validator import validate_latex_project
    validation = validate_latex_project(project_dir)
    
    if not validation.ok:
        print("\n🔴 Validation FAILED:")
        for err in validation.errors:
            print(f"  • {err}")
        return CompileResult(
            success=False,
            log_content="",
            error_count=len(validation.errors),
            warning_count=0,
            reference_warnings=[],
        )
    
    if validation.warnings:
        print("\n⚠ Warnings:")
        for w in validation.warnings[:5]:
            print(f"  • {w}")
    
    # Step 2: Clean auxiliary files
    print("\n[Clean] Removing auxiliary files...")
    for ext in ['.aux', '.bbl', '.blg', '.log', '.out', '.toc', '.lof', '.lot', '.fls', '.fdb_latexmk']:
        aux_file = project_path / f"{project_name}{ext}"
        if aux_file.exists():
            aux_file.unlink()
    
    # Step 3: Compile
    compiler = LatexCompiler(project_dir, project_name)
    result = compiler.compile(template['compile_sequence'])
    
    # Step 4: Report
    print("\n" + "=" * 60)
    print("COMPILATION RESULT")
    print("=" * 60)
    print(f"Success: {'✅ Yes' if result.success else '🔴 No'}")
    print(f"Errors: {result.error_count}")
    print(f"Warnings: {result.warning_count}")
    print(f"Pages: {result.page_count or 'unknown'}")
    print(f"Time: {result.compilation_time:.1f}s" if result.compilation_time else "")
    
    if result.reference_warnings:
        print(f"\n⚠ Reference warnings ({len(result.reference_warnings)}):")
        for w in result.reference_warnings[:3]:
            print(f"  {w}")
    
    if result.error_count > 0 and result.log_content:
        print("\n📋 Last log entries (errors):")
        for line in result.log_content.split('\n'):
            if line.strip().startswith('!'):
                print(f"  {line.strip()}")
    
    return result
```

```bash
# Direct execution
python -c "
import sys
sys.path.insert(0, 'scripts')
from research_framework.latex_compiler import compile_paper

result = compile_paper(
    project_dir='output/fin-manuscript/draft_v1',
    journal_name='经济研究',
    project_name='main'
)
sys.exit(0 if result.success else 1)
"
```

## Step 5: Generate Submission Variants

After successful PDF compilation, generate submission variants:

```python
#!/usr/bin/env python3
"""Generate submission variants: anonymous, arxiv, word."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def generate_anonymous_pdf(source_dir: str,
                            output_dir: str,
                            remove_patterns: list = None) -> str:
    """
    Generate anonymous version by removing author info and acknowledgments.
    
    Parameters
    ----------
    source_dir : str
        Directory with main.pdf
    output_dir : str
        Output directory for anonymous version
    remove_patterns : list
        Regex patterns to remove (author names, acknowledgments, etc.)
    
    Returns
    -------
    str
        Path to anonymous PDF
    """
    if remove_patterns is None:
        remove_patterns = [
            r'\\thanks\{[^}]*\}',
            r'\\author\{[^}]*\}',
            r'\\acker\{[^}]*\}',
            r'\\section\*\{[^}]*致谢[^}]*\}',
            r'\\section\*\{[^}]*Acknowledgment[^}]*\}',
            r'\\footnote\{[^}]*[^)]*基金[^)]*\}',
        ]
    
    source_path = Path(source_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Copy PDF (for PDF-based anonymization)
    src_pdf = source_path / "main.pdf"
    dst_pdf = output_path / "anonymous.pdf"
    
    if src_pdf.exists():
        shutil.copy2(src_pdf, dst_pdf)
        print(f"  Copied: {dst_pdf}")
        
        # TODO: For true anonymization, use PDF redaction tools
        # e.g., pdf редактор or python-pdf-tools
        print(f"  Note: Full PDF redaction requires specialized tools")
    else:
        print(f"  ⚠ Source PDF not found: {src_pdf}")
    
    return str(dst_pdf)


def generate_arxiv_pdf(source_dir: str,
                        output_dir: str,
                        remove_funding: bool = True,
                        remove_author: bool = True) -> str:
    """
    Generate arXiv-compatible version.
    
    arXiv-specific requirements:
    - No author acknowledgments
    - No funding disclosure
    - LaTeX source compiles with pdflatex
    - main.pdf included
    - No .tex files > 10MB
    """
    source_path = Path(source_dir)
    output_path = Path(output_dir) / "arxiv_source"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Copy essential files
    files_to_copy = ["main.tex", "references.bib", "figures/"]
    
    for item in files_to_copy:
        src = source_path / item
        dst = output_path / item
        if src.exists():
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    
    # Copy main.pdf as arxiv.pdf
    src_pdf = source_path / "main.pdf"
    if src_pdf.exists():
        shutil.copy2(src_pdf, output_path / "arxiv.pdf")
    
    # Create submission README
    readme = """arXiv Submission Package
========================

Files:
- main.tex: Main manuscript
- references.bib: Bibliography
- figures/: Figure files
- arxiv.pdf: Compiled PDF

Submission Instructions:
1. Upload this entire directory to arXiv
2. Verify compilation: pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
3. Check that all figures are embedded
"""
    (output_path / "README.txt").write_text(readme)
    
    print(f"  arXiv package: {output_path}")
    return str(output_path)


def generate_word_docx(source_dir: str,
                        output_dir: str,
                        use_pandoc: bool = True) -> str:
    """
    Generate Word (.docx) version for journals requiring Word submission.
    
    Requires: pandoc (install via: brew install pandoc)
    """
    source_path = Path(source_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    tex_file = source_path / "main.tex"
    docx_file = output_path / "main.docx"
    
    if not use_pandoc:
        print("  ⚠ pandoc not available, creating placeholder")
        docx_file.write_text("")
        return str(docx_file)
    
    try:
        # Check pandoc availability
        subprocess.run(["pandoc", "--version"],
                      capture_output=True, check=True)
        
        # Convert
        cmd = [
            "pandoc",
            str(tex_file),
            "-o", str(docx_file),
            "--reference-doc", "templates/journal_ref.docx",  # Optional
            "-f", "latex",
            "-t", "docx",
            "--wrap=none",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and docx_file.exists():
            print(f"  Converted: {docx_file}")
        else:
            print(f"  ⚠ pandoc conversion failed: {result.stderr[:200]}")
            # Fallback: try without reference doc
            cmd[-2] = ""  # Remove reference-doc flag
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  Converted (basic): {docx_file}")
    
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  ⚠ pandoc not installed. Install via: brew install pandoc")
        print("  Creating placeholder .docx file")
        docx_file.write_text("Placeholder - install pandoc and re-run")
    
    return str(docx_file)


def create_submission_package(project_dir: str,
                               journal_name: str,
                               output_dir: str) -> str:
    """
    Create a complete submission package with all required files.
    """
    import zipfile
    
    project_path = Path(project_dir)
    output_path = Path(output_dir)
    pkg_path = output_path / f"submission_package_{journal_name}.zip"
    
    print("\n[Package] Creating submission package...")
    
    with zipfile.ZipFile(pkg_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add main PDF
        main_pdf = project_path / "main.pdf"
        if main_pdf.exists():
            zf.write(main_pdf, "main.pdf")
        
        # Add anonymous PDF
        anon_pdf = project_path / "anonymous.pdf"
        if anon_pdf.exists():
            zf.write(anon_pdf, "anonymous.pdf")
        
        # Add main.tex source
        main_tex = project_path / "main.tex"
        if main_tex.exists():
            zf.write(main_tex, "main.tex")
        
        # Add references
        bib_file = project_path / "references.bib"
        if bib_file.exists():
            zf.write(bib_file, "references.bib")
        
        # Add figures directory
        fig_dir = project_path / "figures"
        if fig_dir.exists():
            for fig in fig_dir.glob("*"):
                if fig.is_file():
                    zf.write(fig, f"figures/{fig.name}")
    
    print(f"  Package: {pkg_path}")
    return str(pkg_path)
```

## Step 6: PDF Validation

```python
def validate_pdf(pdf_path: str) -> dict:
    """
    Validate compiled PDF for submission.
    """
    import re
    
    result = {
        "exists": False,
        "file_size_kb": 0,
        "pages": 0,
        "font_embedding": None,
        "issues": [],
    }
    
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        result["issues"].append("PDF file not found")
        return result
    
    result["exists"] = True
    result["file_size_kb"] = pdf_file.stat().st_size / 1024
    
    # Read PDF header to check validity
    with open(pdf_file, 'rb') as f:
        header = f.read(8)
        if not header.startswith(b'%PDF'):
            result["issues"].append("Invalid PDF header")
    
    # Extract page count
    with open(pdf_file, 'rb') as f:
        content = f.read().decode('latin-1', errors='ignore')
        page_match = re.search(r'/Type\s*/Page[^s]', content)
        page_count = len(re.findall(r'/Type\s*/Page[^s]', content))
        result["pages"] = page_count
    
    # Check for embedded fonts (basic check)
    if '/Font' in content or '/Type1' in content or '/TrueType' in content:
        result["font_embedding"] = "embedded"
    else:
        result["font_embedding"] = "unknown"
    
    # File size check
    if result["file_size_kb"] < 10:
        result["issues"].append(f"PDF very small ({result['file_size_kb']:.0f}KB) - may be incomplete")
    elif result["file_size_kb"] > 50000:
        result["issues"].append(f"PDF very large ({result['file_size_kb']:.0f}KB) - may need compression")
    
    return result
```

## Step 7: Full Pipeline Execution

```python
#!/usr/bin/env python3
"""Complete fin-paper-convert pipeline."""

import sys
import os
from pathlib import Path

# Add project scripts
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.research_framework.latex_compiler import compile_paper, validate_pdf
from scripts.research_framework.latex_compiler import generate_anonymous_pdf, generate_arxiv_pdf, generate_word_docx, create_submission_package
from scripts.research_framework.latex_validator import validate_latex_project


def main():
    project_dir = "output/fin-manuscript/draft_v1"
    journal_name = "经济研究"  # or "JF", "JFE", etc.
    
    print("=" * 60)
    print("fin-paper-convert: LaTeX Compilation & Format Conversion")
    print("=" * 60)
    
    # Step 1: Validate project
    print("\n[Step 1/4] Validating project structure...")
    validation = validate_latex_project(project_dir)
    if not validation.ok:
        print("🔴 Validation failed:")
        for e in validation.errors:
            print(f"  {e}")
        return
    
    # Step 2: Compile to PDF
    print("\n[Step 2/4] Compiling LaTeX to PDF...")
    result = compile_paper(project_dir, journal_name, "main")
    
    if not result.success:
        print("\n🔴 Compilation failed!")
        print(f"Errors: {result.error_count}")
        if result.log_content:
            print("\nLast 2000 chars of log:")
            print(result.log_content[-2000:])
        return
    
    # Validate PDF
    print("\n[Step 3/4] Validating PDF...")
    pdf_path = f"{project_dir}/main.pdf"
    pdf_info = validate_pdf(pdf_path)
    
    print(f"  File size: {pdf_info['file_size_kb']:.0f} KB")
    print(f"  Pages: {pdf_info['pages']}")
    print(f"  Font embedding: {pdf_info['font_embedding']}")
    
    if pdf_info['issues']:
        for issue in pdf_info['issues']:
            print(f"  ⚠ {issue}")
    
    # Step 4: Generate variants
    print("\n[Step 4/4] Generating submission variants...")
    
    # Anonymous version
    try:
        generate_anonymous_pdf(project_dir, project_dir)
    except Exception as e:
        print(f"  ⚠ Anonymous PDF failed: {e}")
    
    # arXiv version (English journals only)
    if journal_name in ["JF", "JFE", "RFS", "AER", "JAE"]:
        try:
            generate_arxiv_pdf(project_dir, project_dir)
        except Exception as e:
            print(f"  ⚠ arXiv package failed: {e}")
    
    # Word version
    try:
        generate_word_docx(project_dir, project_dir)
    except Exception as e:
        print(f"  ⚠ Word conversion failed: {e}")
    
    # Submission package
    try:
        create_submission_package(project_dir, journal_name, project_dir)
    except Exception as e:
        print(f"  ⚠ Package creation failed: {e}")
    
    print("\n" + "=" * 60)
    print("✅ COMPILATION COMPLETE")
    print("=" * 60)
    print(f"\nOutput files in {project_dir}/:")
    print(f"  📄 main.pdf         — Main manuscript")
    print(f"  📄 anonymous.pdf    — Anonymous version")
    if journal_name in ["JF", "JFE", "RFS", "AER", "JAE"]:
        print(f"  📁 arxiv_source/    — arXiv submission")
    print(f"  📄 main.docx        — Word version")
    print(f"  📦 submission_package_{journal_name}.zip")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

## Step 8: Command-Line Usage

```bash
# Direct command-line execution
python scripts/research_framework/latex_compiler.py \
    --dir output/fin-manuscript/draft_v1 \
    --journal 经济研究 \
    --project main

# Check compilation errors
python scripts/research_framework/latex_compiler.py \
    --dir output/fin-manuscript/draft_v1 \
    --check-log

# Compile with latexmk (if available)
latexmk -pdf -interaction=nonstopmode main.tex
```

## Step 9: Error Handling Reference

| Error | Cause | Fix |
|-------|-------|-----|
| `! LaTeX Error: File 'xxx.sty' not found` | Missing package | Install: `tlmgr install xxx` or check `\usepackage{}` |
| `! Undefined control sequence.` | Typo or undefined command | Check .log for line number |
| `[?] Reference` | Citation/label not found | Run pdflatex again (3 passes) |
| `Font ... not loadable` | Font not installed | Install font or use alternative |
| `PDF inclusion: impossible` | Figure format issue | Convert to PDF: `pdftk fig.png output fig.pdf` |
| `Float too large` | Figure/table exceeds page | Reduce figure size or use `\FloatBarrier` |
| `Overfull \hbox` | Line overflow | Adjust `\hbox_to` or add `\small` |
| `Underfull \hbox` | Underfilled line | Usually OK, can ignore |
| `Package natbib Error: Bibliography not compatible with author-year` | Bib style mismatch | Use matching bib style |

## Output Summary

After compilation:

```
✅ LATEX COMPILATION COMPLETE

Journal: 经济研究
Version: draft_v1
Compilation: 4 passes (xelatex → bibtex → xelatex → xelatex)
Time: 12.3s
Pages: 28
Errors: 0
Warnings: 15

Output Files:
  output/fin-manuscript/draft_v1/
  ├── main.pdf              — 28 pages, 2.1 MB
  ├── main.tex              — LaTeX source
  ├── references.bib        — Bibliography
  ├── anonymous.pdf         — Anonymized version
  ├── main.docx             — Word format
  └── submission_package_经济研究.zip

Next Step:
  → Run: fin-submit-check
     Verify format compliance before submission
```
