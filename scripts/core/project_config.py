"""
Project configuration loader with runtime path resolution.

Usage:
    from scripts.core.project_config import load_project_config

    # Relative usage (from project root)
    cfg = load_project_config()

    # Explicit root
    cfg = load_project_config("/path/to/project")

    # Access resolved paths
    print(cfg.paths.data)     # -> PosixPath("/path/to/project/projects/_shared_data")
    print(cfg.paths.knowledge)  # -> PosixPath("/path/to/project/knowledge")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default paths relative to project root
_DEFAULT_RELATIVE_PATHS = {
    "templates": "templates",
    "projects": "projects",
    "knowledge": "knowledge",
    "scripts": "scripts",
    "data": "projects/_shared_data",
}


@dataclass
class ResolvedPaths:
    templates: Path = Path("templates")
    projects: Path = Path("projects")
    knowledge: Path = Path("knowledge")
    scripts: Path = Path("scripts")
    data: Path = Path("projects/_shared_data")


@dataclass
class ProjectConfig:
    project_name: str = "金融AI研究工作流"
    version: str = "1.0.0"
    author: str = ""
    paper_format: str = "ACL"
    default_language: str = "Chinese"
    citation_style: str = "acl_natbib"
    latex_engine: str = "xelatex"
    reference_manager: str = "Zotero"
    report_format: str = "Markdown"
    report_style: str = "国泰君安/中金标准"
    default_currency: str = "CNY"
    coverage_years: int = 5
    forecast_years: int = 3
    python_path: Path = Path(".venv/bin/python")
    jupyter_port: int = 8888
    notebook_dir: Path = Path("notebooks")
    output_dir: Path = Path("results")
    paths: ResolvedPaths = field(default_factory=ResolvedPaths)
    _base_dir: Path = field(default_factory=Path)
    # Original relative path strings (used by resolve_paths to re-resolve)
    _relative_paths: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: Path | None = None) -> ProjectConfig:
        """Construct from a loaded JSON dict."""
        base = base_dir or Path.cwd()
        research = data.get("research", {})
        report = data.get("report", {})
        execution = data.get("execution", {})
        raw_paths = data.get("paths", _DEFAULT_RELATIVE_PATHS)

        resolved = ResolvedPaths(
            templates=cls._resolve(raw_paths.get("templates", "templates"), base),
            projects=cls._resolve(raw_paths.get("projects", "projects"), base),
            knowledge=cls._resolve(raw_paths.get("knowledge", "knowledge"), base),
            scripts=cls._resolve(raw_paths.get("scripts", "scripts"), base),
            data=cls._resolve(raw_paths.get("data", "projects/_shared_data"), base),
        )

        return cls(
            project_name=data.get("project_name", "金融AI研究工作流"),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            paper_format=research.get("paper_format", "ACL"),
            default_language=research.get("default_language", "Chinese"),
            citation_style=research.get("citation_style", "acl_natbib"),
            latex_engine=research.get("latex_engine", "xelatex"),
            reference_manager=research.get("reference_manager", "Zotero"),
            report_format=report.get("format", "Markdown"),
            report_style=report.get("style", "国泰君安/中金标准"),
            default_currency=report.get("default_currency", "CNY"),
            coverage_years=report.get("coverage_years", 5),
            forecast_years=report.get("forecast_years", 3),
            python_path=cls._resolve(execution.get("python_path", ".venv/bin/python"), base),
            jupyter_port=execution.get("jupyter_port", 8888),
            notebook_dir=cls._resolve(execution.get("notebook_dir", "notebooks"), base),
            output_dir=cls._resolve(execution.get("output_dir", "results"), base),
            paths=resolved,
            _base_dir=base,
            _relative_paths={
                "templates": raw_paths.get("templates", "templates"),
                "projects": raw_paths.get("projects", "projects"),
                "knowledge": raw_paths.get("knowledge", "knowledge"),
                "scripts": raw_paths.get("scripts", "scripts"),
                "data": raw_paths.get("data", "projects/_shared_data"),
            },
        )

    @staticmethod
    def _resolve(path_str: str, base_dir: Path) -> Path:
        """Resolve a path string relative to base_dir, or return absolute as-is."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return (base_dir / p).resolve()

    def resolve_paths(self, base_dir: str | Path | None = None) -> ProjectConfig:
        """
        Re-resolve all paths relative to a new base directory.

        Uses stored original relative path strings so the base directory
        is correctly changed even after initial resolution.
        """
        new_base = Path(base_dir or self._base_dir).resolve()
        rel_paths = getattr(self, "_relative_paths", {})
        resolved = ResolvedPaths(
            templates=self._resolve(rel_paths.get("templates", "templates"), new_base),
            projects=self._resolve(rel_paths.get("projects", "projects"), new_base),
            knowledge=self._resolve(rel_paths.get("knowledge", "knowledge"), new_base),
            scripts=self._resolve(rel_paths.get("scripts", "scripts"), new_base),
            data=self._resolve(rel_paths.get("data", "projects/_shared_data"), new_base),
        )
        return dataclass_replace(self, paths=resolved, _base_dir=new_base)

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a dict (paths as strings)."""
        return {
            "project_name": self.project_name,
            "version": self.version,
            "author": self.author,
            "research": {
                "paper_format": self.paper_format,
                "default_language": self.default_language,
                "citation_style": self.citation_style,
                "latex_engine": self.latex_engine,
                "reference_manager": self.reference_manager,
            },
            "report": {
                "format": self.report_format,
                "style": self.report_style,
                "default_currency": self.default_currency,
                "coverage_years": self.coverage_years,
                "forecast_years": self.forecast_years,
            },
            "execution": {
                "python_path": str(self.python_path),
                "jupyter_port": self.jupyter_port,
                "notebook_dir": str(self.notebook_dir),
                "output_dir": str(self.output_dir),
            },
            "paths": {
                k: str(v) for k, v in vars(self.paths).items()
            },
        }


def _dataclass_replace(obj: Any, **kwargs) -> Any:
    """Minimal replace() for plain dataclasses without relying on external libs."""
    import dataclasses
    dc_fields = {f.name for f in dataclasses.fields(obj)}
    kw = {k: v for k, v in kwargs.items() if k in dc_fields}
    others = {k: getattr(obj, k) for k in dc_fields if k not in kw}
    return type(obj)(**others, **kw)


def load_project_config(config_path: str | Path | None = None) -> ProjectConfig:
    """
    Load project configuration from JSON and resolve all paths.

    Search order for config_path:
        1. Explicit path argument
        2. PROJECT_CONFIG env var
        3. <cwd>/config/project_config.json
        4. <cwd>/project_config.json
    """
    if config_path:
        path = Path(config_path)
    else:
        env_path = os.environ.get("PROJECT_CONFIG")
        if env_path:
            path = Path(env_path)
        else:
            cwd = Path.cwd()
            candidates = [
                cwd / "config" / "project_config.json",
                cwd / "project_config.json",
            ]
            for c in candidates:
                if c.exists():
                    path = c
                    break
            else:
                # Return defaults if no file found
                return ProjectConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ProjectConfig()

    base_dir = path.parent.parent  # config/project_config.json -> project root
    return ProjectConfig.from_dict(data, base_dir=base_dir)


# Allow the helper function to be used inside the class
def dataclass_replace(obj: Any, **kwargs) -> Any:
    return _dataclass_replace(obj, **kwargs)
