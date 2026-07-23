"""
Dependency Upgrader (依赖升级工具)
=====================================

Check for outdated dependencies and suggest safe upgrades.
Helps maintain a healthy, secure, and current dependency tree.

Usage:
    python scripts/dependency_upgrader.py --check       # Check only
    python scripts/dependency_upgrader.py --dry-run     # Show what would change
    python scripts/dependency_upgrader.py --apply       # Update requirements.txt
    python scripts/dependency_upgrader.py --security    # Check for known vulnerabilities
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

import requests

# P5-6 audit-2026-07-23: 模块级 Session，keep-alive + 连接池复用
from requests.adapters import HTTPAdapter as _HTTPAdapter
_SESSION = requests.Session()
_SESSION.mount("https://", _HTTPAdapter(pool_connections=10, pool_maxsize=10))
_SESSION.mount("http://", _HTTPAdapter(pool_connections=10, pool_maxsize=10))


class Dependency(NamedTuple):
    name: str
    current: str
    operator: str  # ==, >=, ~=, etc.
    constraint: str


def parse_requirements(path: str = "requirements.txt") -> list[Dependency]:
    """Parse a requirements.txt file into Dependency objects."""
    deps: list[Dependency] = []
    p = Path(path)
    if not p.exists():
        print(f"⚠ {path} not found", file=sys.stderr)
        return deps

    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip extras, paths, includes
        if line.startswith("-") or "/" in line.split(";")[0] or "[" in line.split(";")[0]:
            continue

        # Parse: package==1.0.0 or package>=1.0.0
        match = re.match(r"^([a-zA-Z0-9._-]+)\s*(>=|<=|==|!=|~=|>|<)\s*([0-9.]+.*?)(?:\s*;.*)?$", line)
        if match:
            name, op, ver = match.groups()
            deps.append(Dependency(name=name, current=ver, operator=op, constraint=line))
    return deps


def get_latest_version(pkg: str) -> str | None:
    """Get the latest stable version of a package from PyPI."""
    try:
        r = _SESSION.get(f"https://pypi.org/pypi/{pkg}/json", timeout=5)
        if r.status_code == 200:
            return r.json()["info"]["version"]
    except Exception as e:
        print(f"  ⚠ Could not fetch {pkg}: {e}", file=sys.stderr)
    return None


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a version string into comparable tuple."""
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts[:3]) if parts else (0,)


def is_outdated(current: str, latest: str) -> bool:
    """Check if latest is newer than current."""
    return parse_version(latest) > parse_version(current)


def check_security(pkg: str, version: str) -> list[dict]:
    """Check for known vulnerabilities via OSV API."""
    try:
        r = _SESSION.post(
            "https://api.osv.dev/v1/query",
            json={"package": {"name": pkg, "ecosystem": "PyPI"}, "version": version},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("vulns", [])
    except Exception:
        pass
    return []


def main():
    parser = argparse.ArgumentParser(description="FinAI dependency upgrader")
    parser.add_argument("--check", action="store_true", help="Only check, don't modify")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--apply", action="store_true", help="Update requirements.txt")
    parser.add_argument("--security", action="store_true", help="Check for known vulnerabilities")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    deps = parse_requirements(args.requirements)
    if not deps:
        print("No dependencies found")
        return

    results: list[dict] = []
    security_issues: list[dict] = []

    print(f"Checking {len(deps)} dependencies...")
    for dep in deps:
        latest = get_latest_version(dep.name)
        if latest is None:
            continue

        outdated = is_outdated(dep.current, latest)
        result = {
            "name": dep.name,
            "current": dep.current,
            "latest": latest,
            "outdated": outdated,
            "constraint": dep.constraint,
        }
        results.append(result)

        if args.security:
            vulns = check_security(dep.name, dep.current)
            if vulns:
                security_issues.extend(
                    {"package": dep.name, "version": dep.current, "vulns": vulns}
                )

        # Print
        if args.json:
            continue
        if outdated:
            print(f"  ⬆  {dep.name}: {dep.current} → {latest}")
        else:
            print(f"  ✓  {dep.name}: {dep.current}")

    # Summary
    outdated_count = sum(1 for r in results if r["outdated"])
    print(f"\nSummary: {outdated_count} outdated of {len(results)} packages")

    if args.security and security_issues:
        print(f"\n🔒 Security issues found: {len(security_issues)}")
        for issue in security_issues:
            print(f"  - {issue['package']} {issue['version']}: {len(issue['vulns'])} vulnerabilities")

    if args.json:
        print(json.dumps({"results": results, "security": security_issues}, indent=2))

    # Apply
    if args.apply and outdated_count > 0:
        if not args.dry_run:
            update_requirements(args.requirements, results)
            print(f"\n✅ Updated {args.requirements}")
        else:
            print(f"\n(Dry run) Would update {outdated_count} packages in {args.requirements}")


def update_requirements(path: str, results: list[dict]) -> None:
    """Update the requirements file with the latest versions."""
    latest_map = {r["name"]: r["latest"] for r in results if r["outdated"]}
    text = Path(path).read_text()
    for pkg, new_ver in latest_map.items():
        text = re.sub(
            rf"^{re.escape(pkg)}\s*[><=~]+\s*[0-9.]+",
            f"{pkg}>={new_ver}",
            text,
            flags=re.MULTILINE,
        )
    Path(path).write_text(text)


if __name__ == "__main__":
    main()
