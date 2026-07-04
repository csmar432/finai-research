#!/usr/bin/env python3
"""
MCP Server Health Check — verify all servers compile and have Dockerfiles.

Usage:
    python scripts/health_check_mcp.py              # Human-readable report
    python scripts/health_check_mcp.py --json       # Machine-readable JSON
    python scripts/health_check_mcp.py --summary   # One-line summary
    python scripts/health_check_mcp.py --server <name>  # Check specific server
    python scripts/health_check_mcp.py --priority-only  # Priority servers only
    python scripts/health_check_mcp.py --project-root /path/to/project  # Custom project
"""
import argparse
import json
import sys
import py_compile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────────────

PROJECT_ROOT_DEFAULT = Path(__file__).parent.parent.resolve()

# Priority servers (most important for research workflow)
PRIORITY_SERVERS = [
    "user-yfinance",
    "user-openalex",
    "user-financial",
    "user-tushare",
    "user-eastmoney-reports",
    "user-fed-data",
    "user-wb-data",
    "user-imf-data",
    "user-brave-search",
    "user-context7",
    "user-arxiv",
    "user-sec-edgar",
    "user-enhanced-finance",
    "user-eastmoney-fund",
    "user-eastmoney-bond",
    "user-eastmoney-option",
    "user-cryptocompare",
    "user-latex-mcp",
    "user-e2b-mcp",
    "user-pandas-mcp",
    "user-playwright-mcp",
    "user-filesystem-mcp",
]


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ToolInfo:
    name: str
    path: str
    has_handler: bool = False


@dataclass
class ServerCheckResult:
    name: str
    dir: str
    exists: bool = False
    has_server_py: bool = False
    has_server_metadata: bool = False
    has_dockerfile: bool = False
    has_tools_dir: bool = False
    tool_count: int = 0
    tools: list = field(default_factory=list)
    compile_ok: bool = False
    compile_error: Optional[str] = None
    status: str = "unknown"
    error: Optional[str] = None


@dataclass
class HealthCheckReport:
    timestamp: str
    project_root: str
    total_servers: int
    servers_with_server_py: int
    servers_with_dockerfile: int
    total_tool_files: int
    priority_servers_status: dict
    servers: list
    summary: dict


# ── Core Check Functions ─────────────────────────────────────────────────────

def check_server(server_dir: Path) -> ServerCheckResult:
    """
    Check a single MCP server directory.

    Checks:
    1. Directory exists
    2. server.py exists and compiles
    3. SERVER_METADATA.json exists
    4. Dockerfile exists
    5. tools/ directory and tool count
    """
    result = ServerCheckResult(name=server_dir.name, dir=str(server_dir))
    result.exists = server_dir.exists() and server_dir.is_dir()

    if not result.exists:
        result.status = "missing"
        result.error = "Directory does not exist"
        return result

    # Check server.py
    server_py = server_dir / "server.py"
    result.has_server_py = server_py.exists()

    if result.has_server_py:
        try:
            py_compile.compile(str(server_py), doraise=True)
            result.compile_ok = True
        except py_compile.PyCompileError as e:
            result.compile_ok = False
            result.compile_error = str(e)
    else:
        result.status = "incomplete"
        result.error = "Missing server.py"
        return result

    # Check SERVER_METADATA.json
    result.has_server_metadata = (server_dir / "SERVER_METADATA.json").exists()

    # Check Dockerfile
    result.has_dockerfile = (server_dir / "Dockerfile").exists()

    # Check tools directory
    tools_dir = server_dir / "tools"
    result.has_tools_dir = tools_dir.exists() and tools_dir.is_dir()

    if result.has_tools_dir:
        tool_files = list(tools_dir.glob("*.json"))
        result.tool_count = len(tool_files)
        result.tools = [
            ToolInfo(name=f.stem, path=str(f.relative_to(server_dir)))
            for f in tool_files
        ]

    # Determine overall status
    if result.compile_ok:
        if result.has_dockerfile:
            result.status = "ready"
        else:
            result.status = "compile_ok_no_docker"
    else:
        result.status = "compile_error"

    return result


def _normalize_name(name: str) -> str:
    """Normalize server name for comparison (hyphen/underscore agnostic)."""
    return name.lower().replace("-", "_").replace("_", "")


def check_all_servers(mcp_dir: Path) -> dict:
    """
    Check all MCP servers in the mcp_servers directory.

    Args:
        mcp_dir: Path to the mcp_servers directory

    Returns:
        dict with keys:
            - timestamp: ISO timestamp of check
            - project_root: absolute path to project
            - total_servers: total directories found
            - servers_with_server_py: count of servers with server.py
            - servers_with_dockerfile: count of servers with Dockerfile
            - total_tool_files: total tool JSON files
            - priority_servers_status: status of priority servers
            - servers: list of ServerCheckResult dicts
            - summary: high-level summary
    """
    timestamp = datetime.now().isoformat()

    # Find all server directories
    all_dirs = sorted([d for d in mcp_dir.iterdir() if d.is_dir()])

    total_servers = len(all_dirs)
    servers_with_server_py = 0
    servers_with_dockerfile = 0
    total_tool_files = 0
    priority_servers_status = {}
    servers_results = []

    for server_dir in all_dirs:
        result = check_server(server_dir)
        servers_results.append(asdict(result))

        if result.has_server_py:
            servers_with_server_py += 1
        if result.has_dockerfile:
            servers_with_dockerfile += 1
        total_tool_files += result.tool_count

        # Track priority servers (normalize names for hyphen/underscore matching)
        server_normalized = _normalize_name(server_dir.name)
        for priority_name in PRIORITY_SERVERS:
            if _normalize_name(priority_name) == server_normalized:
                priority_servers_status[server_dir.name] = {
                    "status": result.status,
                    "has_dockerfile": result.has_dockerfile,
                    "has_server_py": result.has_server_py,
                    "compile_ok": result.compile_ok,
                    "tool_count": result.tool_count,
                }
                break

    # Calculate summary
    ready_count = sum(1 for s in servers_results if s["status"] == "ready")
    compile_ok_no_docker = sum(1 for s in servers_results if s["status"] == "compile_ok_no_docker")
    compile_error_count = sum(1 for s in servers_results if s["status"] == "compile_error")
    missing_count = sum(1 for s in servers_results if s["status"] == "missing")

    summary = {
        "total_servers": total_servers,
        "servers_with_server_py": servers_with_server_py,
        "servers_with_dockerfile": servers_with_dockerfile,
        "total_tool_files": total_tool_files,
        "ready_count": ready_count,
        "compile_ok_no_docker_count": compile_ok_no_docker,
        "compile_error_count": compile_error_count,
        "missing_count": missing_count,
        "coverage_dockerfile": f"{servers_with_dockerfile}/{servers_with_server_py}" if servers_with_server_py > 0 else "N/A",
        "coverage_server_py": f"{servers_with_server_py}/{total_servers}",
    }

    return {
        "timestamp": timestamp,
        "project_root": str(mcp_dir.parent),
        "total_servers": total_servers,
        "servers_with_server_py": servers_with_server_py,
        "servers_with_dockerfile": servers_with_dockerfile,
        "total_tool_files": total_tool_files,
        "priority_servers_status": priority_servers_status,
        "servers": servers_results,
        "summary": summary,
    }


def get_priority_servers_report(mcp_dir: Path) -> dict:
    """Get detailed report for priority servers only."""
    all_results = check_all_servers(mcp_dir)
    priority_names = set(_normalize_name(n) for n in PRIORITY_SERVERS)

    priority_results = [
        s for s in all_results["servers"]
        if _normalize_name(s["name"]) in priority_names
    ]

    # Sort by priority order
    priority_results.sort(
        key=lambda s: next(
            (i for i, n in enumerate(PRIORITY_SERVERS)
             if _normalize_name(n) == _normalize_name(s["name"])),
            999
        )
    )

    return {
        "timestamp": all_results["timestamp"],
        "project_root": all_results["project_root"],
        "priority_count": len(priority_results),
        "servers": priority_results,
    }


def get_single_server_report(mcp_dir: Path, server_name: str) -> dict:
    """Get report for a single server."""
    server_dir = mcp_dir / server_name
    result = check_server(server_dir)
    return asdict(result)


# ── Output Formatters ────────────────────────────────────────────────────────

def print_human_report(report: dict) -> None:
    """Print a human-readable report."""
    print("=" * 70)
    print("MCP SERVER HEALTH CHECK REPORT")
    print("=" * 70)
    print(f"Timestamp: {report['timestamp']}")
    print(f"Project:   {report['project_root']}")
    print()

    # Summary section
    s = report["summary"]
    print("── SUMMARY ──────────────────────────────────────────────────────────")
    print(f"  Total server directories:      {s['total_servers']}")
    print(f"  Servers with server.py:        {s['servers_with_server_py']} ({s['coverage_server_py']})")
    print(f"  Servers with Dockerfile:        {s['servers_with_dockerfile']} ({s['coverage_dockerfile']})")
    print(f"  Total tool JSON files:         {s['total_tool_files']}")
    print()
    print(f"  Status breakdown:")
    print(f"    ✅ Ready (compile + docker):  {s['ready_count']}")
    print(f"    ⚠️  Compile OK, no Docker:    {s['compile_ok_no_docker_count']}")
    print(f"    ❌ Compile error:             {s['compile_error_count']}")
    print(f"    ❌ Missing:                   {s['missing_count']}")
    print()

    # Priority servers section
    if report.get("priority_servers_status"):
        print("── PRIORITY SERVERS ───────────────────────────────────────────────")
        for name, status in report["priority_servers_status"].items():
            status_icon = {
                "ready": "✅",
                "compile_ok_no_docker": "⚠️",
                "compile_error": "❌",
                "missing": "❌",
            }.get(status["status"], "?")

            docker_icon = "🐳" if status["has_dockerfile"] else "📦"
            compile_icon = "✅" if status["compile_ok"] else "❌"
            tools_info = f"[{status['tool_count']} tools]" if status["tool_count"] > 0 else ""

            print(f"  {status_icon} {name:<30} {docker_icon} {compile_icon} {tools_info}")
        print()

    # All servers section
    print("── ALL SERVERS ──────────────────────────────────────────────────────")
    for server in report["servers"]:
        status_icon = {
            "ready": "✅",
            "compile_ok_no_docker": "⚠️",
            "compile_error": "❌",
            "missing": "❌",
            "incomplete": "⚠️",
            "unknown": "?",
        }.get(server["status"], "?")

        docker_icon = "🐳" if server["has_dockerfile"] else "  "
        tools_info = f"[{server['tool_count']:3d} tools]" if server["tool_count"] > 0 else "           "

        # Handle long error messages
        error_info = ""
        if server["compile_error"]:
            error_info = f" | {server['compile_error'][:60]}"
        elif server["error"]:
            error_info = f" | {server['error'][:60]}"

        print(f"  {status_icon} {server['name']:<35} {docker_icon} {tools_info}{error_info}")

    print()
    print("=" * 70)
    print("Legend: ✅ Ready | ⚠️  Warning | ❌ Error | 🐳 Has Dockerfile | 📦 No Dockerfile")
    print("=" * 70)


def print_json_report(report: dict) -> None:
    """Print a JSON report for machine parsing."""
    print(json.dumps(report, indent=2, ensure_ascii=False))


def print_summary_line(report: dict) -> None:
    """Print a one-line summary."""
    s = report["summary"]
    total = s["total_servers"]
    ready = s["ready_count"]
    compile_ok = s["servers_with_server_py"]
    docker = s["servers_with_dockerfile"]
    tools = s["total_tool_files"]

    print(
        f"MCP Health: {total} servers | "
        f"{ready} ready (🐳Docker) | "
        f"{compile_ok}/{total} compile OK | "
        f"{tools} tools"
    )


def print_single_server_report(report: dict) -> None:
    """Print report for a single server."""
    print("=" * 70)
    print(f"SERVER: {report['name']}")
    print("=" * 70)
    print(f"Path:           {report['dir']}")
    print(f"Status:         {report['status']}")
    print(f"Exists:         {report['exists']}")
    print(f"server.py:      {'✅' if report['has_server_py'] else '❌'}")
    print(f"Dockerfile:     {'✅' if report['has_dockerfile'] else '❌'}")
    print(f"SERVER_METADATA: {'✅' if report['has_server_metadata'] else '❌'}")
    print(f"Compile OK:     {'✅' if report['compile_ok'] else '❌'}")
    print(f"Tools:          {report['tool_count']}")

    if report.get("tools"):
        print("Tool files:")
        for tool in report["tools"]:
            print(f"  - {tool['name']} ({tool['path']})")

    if report.get("compile_error"):
        print(f"\n⚠️  Compile Error:")
        print(f"  {report['compile_error']}")

    if report.get("error"):
        print(f"\n❌ Error:")
        print(f"  {report['error']}")

    print("=" * 70)


# ── Main Entry Point ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MCP Server Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/health_check_mcp.py
  python scripts/health_check_mcp.py --json
  python scripts/health_check_mcp.py --summary
  python scripts/health_check_mcp.py --server user-yfinance
  python scripts/health_check_mcp.py --priority-only
  python scripts/health_check_mcp.py --project-root /path/to/project
        """
    )

    parser.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON"
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Output one-line summary"
    )
    parser.add_argument(
        "--server",
        help="Check specific server only (e.g., user-yfinance)"
    )
    parser.add_argument(
        "--priority-only", action="store_true",
        help="Show only priority servers"
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT_DEFAULT),
        help=f"Project root directory (default: {PROJECT_ROOT_DEFAULT})"
    )

    args = parser.parse_args()

    # Resolve project root and mcp directory
    project_root = Path(args.project_root)
    mcp_dir = project_root / "mcp_servers"

    if not mcp_dir.exists():
        print(f"ERROR: MCP directory not found: {mcp_dir}", file=sys.stderr)
        sys.exit(2)

    # Run checks
    if args.server:
        # Check specific server (normalize hyphen/underscore)
        normalized_name = None
        for d in mcp_dir.iterdir():
            if d.is_dir() and _normalize_name(d.name) == _normalize_name(args.server):
                normalized_name = d.name
                break
        if normalized_name:
            report = get_single_server_report(mcp_dir, normalized_name)
        else:
            report = {"name": args.server, "status": "not_found", "error": f"No server matching '{args.server}'"}
        if args.json:
            print_json_report(report)
        else:
            if normalized_name:
                print_single_server_report(report)
            else:
                print(f"ERROR: Server '{args.server}' not found. Available servers:")
                for d in sorted(mcp_dir.iterdir()):
                    if d.is_dir():
                        print(f"  - {d.name}")
    elif args.priority_only:
        # Priority servers only
        report = get_priority_servers_report(mcp_dir)
        if args.json:
            print_json_report(report)
        elif args.summary:
            count = len(report["servers"])
            ready = sum(1 for x in report["servers"] if x["status"] == "ready")
            print(f"Priority: {count} servers | {ready} ready")
        else:
            print("=" * 70)
            print("PRIORITY SERVERS REPORT")
            print("=" * 70)
            print(f"Timestamp: {report['timestamp']}")
            print(f"Project:   {report['project_root']}")
            print(f"Priority servers checked: {report['priority_count']}")
            print()
            for server in report["servers"]:
                status_icon = {
                    "ready": "✅",
                    "compile_ok_no_docker": "⚠️",
                    "compile_error": "❌",
                    "missing": "❌",
                }.get(server["status"], "?")
                docker_icon = "🐳" if server["has_dockerfile"] else "📦"
                print(f"  {status_icon} {server['name']:<35} {docker_icon} [{server['tool_count']} tools]")
            print()
    else:
        # Full check
        report = check_all_servers(mcp_dir)
        if args.json:
            print_json_report(report)
        elif args.summary:
            print_summary_line(report)
        else:
            print_human_report(report)

    # Exit with appropriate code
    if not args.json and not args.summary and not args.server:
        s = report.get("summary", {})
        if s.get("compile_error_count", 0) > 0 or s.get("missing_count", 0) > 0:
            sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
