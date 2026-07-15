"""Unit tests for scripts.research_directions.migrate_to_yaml module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def MODULE_ABBREV():
    _p = str(SCRIPTS_DIR)
    if _p not in sys.path:
        sys.path.insert(0, _p)
    from scripts.research_directions import migrate_to_yaml as m

    yield m
    if _p in sys.path:
        sys.path.remove(_p)


def test_module_imports(MODULE_ABBREV):
    assert MODULE_ABBREV is not None
    assert MODULE_ABBREV.__name__ == "scripts.research_directions.migrate_to_yaml"


def test_main_callable(MODULE_ABBREV):
    """Module exposes a `main` function."""
    assert callable(MODULE_ABBREV.main)


def test_main_signature(MODULE_ABBREV):
    import inspect

    sig = inspect.signature(MODULE_ABBREV.main)
    assert sig.return_annotation in ("int", int)


def test_main_dry_run(monkeypatch, capsys):
    """`python migrate_to_yaml.py --dry-run` should print stats and return 0."""
    from scripts.research_directions import migrate_to_yaml as m

    monkeypatch.setattr(sys, "argv", ["migrate_to_yaml.py", "--dry-run"])
    rc = m.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "dry-run" in captured.out or "Would export" in captured.out


def test_project_root_attribute(MODULE_ABBREV):
    """PROJECT_ROOT is the absolute path to the repo root."""
    from pathlib import Path

    pr = MODULE_ABBREV.PROJECT_ROOT
    assert isinstance(pr, Path)
    assert pr.is_absolute()
    assert (pr / "scripts").exists()
    assert (pr / "scripts" / "research_directions").exists()
