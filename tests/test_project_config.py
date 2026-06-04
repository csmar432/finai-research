"""
Tests for ProjectConfig — scripts/core/project_config.py
"""

import pytest
import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.project_config import (
    ProjectConfig,
    ResolvedPaths,
    load_project_config,
    dataclass_replace,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_config_data():
    return {
        "project_name": "测试项目",
        "version": "2.0.0",
        "author": "test@example.com",
        "research": {
            "paper_format": "IEEE",
            "default_language": "English",
        },
        "report": {
            "format": "DOCX",
            "coverage_years": 3,
        },
        "execution": {
            "python_path": ".venv/bin/python",
            "jupyter_port": 8889,
            "output_dir": "results",
        },
        "paths": {
            "templates": "templates",
            "knowledge": "knowledge",
            "scripts": "scripts",
            "data": "projects/shared",
        },
    }


@pytest.fixture
def config_file(tmp_path, sample_config_data):
    # config/project_config.json
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "project_config.json"
    path.write_text(json.dumps(sample_config_data, indent=2), encoding="utf-8")
    return path


# ── ProjectConfig.from_dict ─────────────────────────────────────────────────

class TestProjectConfigFromDict:
    def test_from_dict_basic(self, tmp_path, sample_config_data):
        cfg = ProjectConfig.from_dict(sample_config_data, base_dir=tmp_path)
        assert cfg.project_name == "测试项目"
        assert cfg.version == "2.0.0"
        assert cfg.author == "test@example.com"
        assert cfg.paper_format == "IEEE"
        assert cfg.report_format == "DOCX"
        assert cfg.coverage_years == 3

    def test_from_dict_resolves_relative_paths(self, tmp_path, sample_config_data):
        cfg = ProjectConfig.from_dict(sample_config_data, base_dir=tmp_path)
        # Relative paths should be resolved against base_dir
        assert cfg.paths.data.is_absolute()
        assert str(tmp_path) in str(cfg.paths.data)
        assert cfg.paths.data.name == "shared"

    def test_from_dict_defaults_for_missing_fields(self, tmp_path):
        cfg = ProjectConfig.from_dict({}, base_dir=tmp_path)
        assert cfg.project_name == "金融AI研究工作流"
        assert cfg.version == "1.0.0"
        assert cfg.paper_format == "ACL"
        assert cfg.default_language == "Chinese"


# ── resolve_paths ────────────────────────────────────────────────────────────

class TestResolvePaths:
    def test_resolve_paths_changes_base(self, tmp_path, sample_config_data):
        cfg = ProjectConfig.from_dict(sample_config_data, base_dir=tmp_path)
        new_base = tmp_path / "new_project"
        new_base.mkdir()

        cfg2 = cfg.resolve_paths(new_base)
        assert cfg2.paths.data.is_absolute()
        assert str(new_base) in str(cfg2.paths.data)

    def test_resolve_paths_preserves_other_fields(self, tmp_path, sample_config_data):
        cfg = ProjectConfig.from_dict(sample_config_data, base_dir=tmp_path)
        cfg2 = cfg.resolve_paths(tmp_path / "new")
        assert cfg2.project_name == cfg.project_name
        assert cfg2.version == cfg.version
        assert cfg2.paper_format == cfg.paper_format


# ── load_project_config ─────────────────────────────────────────────────────

class TestLoadProjectConfig:
    def test_load_from_explicit_path(self, config_file):
        cfg = load_project_config(config_file)
        assert cfg.project_name == "测试项目"

    def test_load_returns_defaults_on_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_project_config("does_not_exist.yaml")
        assert cfg.project_name == "金融AI研究工作流"

    def test_load_from_project_root(self, tmp_path, config_file, monkeypatch):
        # Simulate cwd = project root (parent of config/)
        project_root = config_file.parent.parent
        monkeypatch.chdir(project_root)
        cfg = load_project_config()
        assert cfg.project_name == "测试项目"


# ── ResolvedPaths ───────────────────────────────────────────────────────────

class TestResolvedPaths:
    def test_default_paths_exist(self):
        rp = ResolvedPaths()
        assert rp.templates == Path("templates")
        assert rp.projects == Path("projects")

    def test_paths_are_path_objects(self, tmp_path, sample_config_data):
        cfg = ProjectConfig.from_dict(sample_config_data, base_dir=tmp_path)
        assert isinstance(cfg.paths.templates, Path)
        assert isinstance(cfg.paths.data, Path)


# ── dataclass_replace ────────────────────────────────────────────────────────

class TestDataclassReplace:
    def test_replace_preserves_unmodified_fields(self):
        rp = ResolvedPaths(templates=Path("/tmp/t"), projects=Path("/tmp/p"))
        rp2 = dataclass_replace(rp, templates=Path("/new/t"))
        assert rp2.templates == Path("/new/t")
        assert rp2.projects == Path("/tmp/p")  # unchanged


# ── to_dict ──────────────────────────────────────────────────────────────────

class TestToDict:
    def test_to_dict_round_trip(self, tmp_path, sample_config_data):
        cfg1 = ProjectConfig.from_dict(sample_config_data, base_dir=tmp_path)
        d = cfg1.to_dict()
        cfg2 = ProjectConfig.from_dict(d, base_dir=tmp_path)
        assert cfg1.project_name == cfg2.project_name
        assert cfg1.paper_format == cfg2.paper_format
        assert cfg1.paths.data.name == cfg2.paths.data.name
