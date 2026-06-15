# conf.py — Sphinx configuration for FinAI Research Workflow API docs
# Build: cd docs && sphinx-build -b html . _build/html

import os
import sys
from pathlib import Path

# ── Project info ──────────────────────────────────────────────────────────
project = "FinAI Research Workflow"
author = "FinAI Research Workflow Contributors"
copyright = "2026, FinAI Research Workflow Contributors"
release = "1.0.0"
version = "1.0.0"

# ── Path setup ────────────────────────────────────────────────────────────
# 让 sphinx 能 import 项目代码
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DEEPSEEK_API_KEY", "sphinx_dummy")

# ── General configuration ────────────────────────────────────────────────
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",  # Google/NumPy docstring
    "sphinx.ext.viewcode",  # 链接到 GitHub 源码
    "sphinx.ext.intersphinx",  # 跨项目引用
    "sphinx.ext.autosummary",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
    "sphinx.ext.todo",
    "myst_parser",  # Markdown 支持
]
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
master_doc = "index"
language = "zh_CN"

# ── HTML output ──────────────────────────────────────────────────────────
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 4,
    "titles_only": False,
}
html_logo = "_static/logo.png"
html_favicon = "_static/favicon.ico"
html_title = f"{project} v{version} API 文档"
html_short_title = "FinAI API"

# ── Intersphinx (跨项目引用) ──────────────────────────────────────────────
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "statsmodels": ("https://www.statsmodels.org/stable/", None),
    "sklearn": ("https://scikit-learn.org/stable/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}

# ── Napoleon (Google/NumPy docstring) ────────────────────────────────────
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True

# ── Autodoc ──────────────────────────────────────────────────────────────
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}
autodoc_typehints = "description"  # 避免类型提示膨胀
autodoc_typehints_format = "short"
autoclass_content = "class"  # 同时记录 __init__ 和 class docstring

# ── Viewcode: 链接到 GitHub 源码 ─────────────────────────────────────────
# 让 _modules/ 页面链接到 GitHub
viewcode_follow_imported_members = True
viewcode_import = False

# ── Todo ─────────────────────────────────────────────────────────────────
todo_include_todos = True

# ── Markdown 支持 ────────────────────────────────────────────────────────
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
myst_enable_extensions = [
    "colon_fence",
    "dollarmath",
    "amsmath",
    "deflist",
    "fieldlist",
    "html_admonition",
    "linkify",
    "replacements",
    "smartquotes",
    "substitution",
    "tasklist",
]

# ── Coverage ─────────────────────────────────────────────────────────────
coverage_show_missing_items = True
coverage_ignore_modules = [
    "scripts.legacy",
    "scripts.deprecated",
]

# ── Doctest ──────────────────────────────────────────────────────────────
doctest_path = os.environ.get("SPHINX_DOCTEST_PATH", "doctest")
doctest_global_setup = """
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "sphinx_dummy")
"""
