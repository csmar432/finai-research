"""Regression checks for the 2026-08-03 audit remediation."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mock_permission_imports_never_fail_open():
    violations = []
    for server in (ROOT / "mcp_servers").glob("user_*/server.py"):
        text = server.read_text(encoding="utf-8")
        if re.search(r"^\s*def\s+check_mock_permission\b", text, re.MULTILINE):
            violations.append(str(server.relative_to(ROOT)))
    assert not violations, f"fail-open mock guards: {violations}"


def test_github_actions_are_pinned_to_full_commit_shas():
    violations = []
    for workflow in (ROOT / ".github").rglob("*.yml"):
        for line_number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"\buses:\s+[^\s@]+@([^\s#]+)", line)
            if match and not re.fullmatch(r"[0-9a-f]{40}", match.group(1)):
                violations.append(f"{workflow.relative_to(ROOT)}:{line_number}")
    assert not violations, f"unpinned GitHub Actions: {violations}"


def test_ci_uses_locked_mcp_1x_dependency_set():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")
    lock = (ROOT / "requirements-ci-lock.txt").read_text(encoding="utf-8")

    assert "pip install -r requirements-ci-lock.txt" in workflow
    assert re.search(r"^mcp>=1\.0\.0,<2\.0$", requirements, re.MULTILINE)
    assert re.search(r"^mcp==1\.", lock, re.MULTILINE)


def test_fomc_uses_official_dates_and_fred_rates(monkeypatch):
    from mcp_servers.user_fed_data import server

    lower = [
        {"date": "2026-06-16", "value": 3.75},
        {"date": "2026-06-17", "value": 3.50},
    ]
    upper = [
        {"date": "2026-06-16", "value": 4.00},
        {"date": "2026-06-17", "value": 3.75},
    ]
    monkeypatch.setattr(
        server,
        "_fetch_fred_csv",
        lambda series, *_args: lower if series == "DFEDTARL" else upper,
    )

    content = asyncio.run(server.handle_fomc({"year": 2026}))
    result = json.loads(content[0].text)

    assert [m["date"] for m in result["meetings"]] == [
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    ]
    june = next(m for m in result["meetings"] if m["date"] == "2026-06-17")
    assert (june["lower"], june["upper"], june["decision"]) == (3.5, 3.75, "cut")
    assert "_is_mock" not in result
    assert result["_source_url"].endswith("fomccalendars.htm")


def test_beige_book_does_not_invent_release_metadata():
    from mcp_servers.user_fed_data import server

    content = asyncio.run(server.handle_beige_book({"year": 2026}))
    result = json.loads(content[0].text)

    assert result["status"] == "official_archive_link"
    assert result["releases"] == []
    assert result["_source_url"].endswith("beige-book-default.htm")


def test_partially_initialized_data_cache_can_be_finalized():
    from scripts.core.data_cache import DataCache

    cache = object.__new__(DataCache)
    cache.close()
