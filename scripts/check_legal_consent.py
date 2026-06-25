#!/usr/bin/env python3
"""check_legal_consent.py — Enforce user consent before running legal-risk MCP servers.

Usage:
    python scripts/check_legal_consent.py                # check all servers
    python scripts/check_legal_consent.py --enforce     # exit with error if no consent
    python scripts/check_legal_consent.py --list        # list all legal-risk servers
    python scripts/check_legal_consent.py --check cnki  # check specific server

Exit code:
    0 = no legal-risk servers found, OR all found servers have consent
    1 = legal-risk server found without consent (only with --enforce)

Environment variables (OR .env.local entry):
    CLI_ACCEPT_RISK=cnki,wanfang,chinese-literature   # enable specific servers
    CLI_ACCEPT_RISK=ALL                                # enable all (explicit, not default)

The full profile includes cnki/wanfang/chinese-literature. These are DISABLED
by default and require explicit user consent via the environment variable above.
This protects the project maintainer from liability for users who enable these
servers without understanding the legal implications.

This script is called by:
    - MCP server registration (register_mcp_servers.py)
    - health_check.py
    - pre-commit hooks
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVERS = PROJECT_ROOT / "mcp_servers"


def get_consent_flags() -> set[str]:
    """Parse CLI_ACCEPT_RISK environment variable."""
    raw = os.environ.get("CLI_ACCEPT_RISK", "")
    if not raw:
        return set()
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def find_legal_risk_servers() -> list[dict]:
    """Find all MCP servers with legal_risk: true in their SERVER_METADATA.json."""
    results = []
    for srv_dir in sorted(MCP_SERVERS.iterdir()):
        if not srv_dir.name.startswith("user_"):
            continue
        meta_file = srv_dir / "SERVER_METADATA.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("legal_risk"):
            results.append({
                "name": srv_dir.name,
                "display_name": meta.get("name", srv_dir.name),
                "description": meta.get("description", "")[:80],
                "disclaimer": meta.get("disclaimer", ""),
                "consent_type": meta.get("consent_type", ""),
                "requires_consent": meta.get("requires_user_consent", True),
            })
    return results


def check_consent(enforce: bool = False) -> bool:
    """Check consent for all legal-risk servers. Return True if OK."""
    servers = find_legal_risk_servers()
    if not servers:
        return True

    consent_flags = get_consent_flags()
    all_consented = consent_flags == {"all"}
    if all_consented:
        return True

    issues: list[str] = []
    for srv in servers:
        identifier = srv["name"].replace("user_", "").replace("_", "-")
        consented = (identifier in consent_flags or
                    srv["name"].lower() in consent_flags or
                    identifier.lower() in consent_flags)
        if not consented:
            issues.append(
                f"  {srv['display_name']} ({srv['name']})\n"
                f"    Consent: CLI_ACCEPT_RISK={srv['consent_type'].replace('CLI_ACCEPT_RISK=', '')}\n"
                f"    Disclaimer: {srv['disclaimer'][:100]}"
            )

    if not issues:
        return True

    print("⚠️  Legal-Risk MCP Servers: User Consent Required", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for issue in issues:
        print(issue, file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("To enable:", file=sys.stderr)
    print("  export CLI_ACCEPT_RISK=cnki,wanfang,chinese-literature", file=sys.stderr)
    print("  # Or in .env.local:", file=sys.stderr)
    print("  CLI_ACCEPT_RISK=cnki,wanfang,chinese-literature", file=sys.stderr)
    print("  # Or for ALL legal-risk servers (explicit, not default):", file=sys.stderr)
    print("  CLI_ACCEPT_RISK=ALL", file=sys.stderr)
    print(file=sys.stderr)
    print("See LEGAL_CONSENT.md for full details.", file=sys.stderr)

    return False


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check user consent for legal-risk MCP servers")
    parser.add_argument("--enforce", action="store_true",
                        help="Exit with error if any legal-risk server lacks consent")
    parser.add_argument("--list", action="store_true",
                        help="List all legal-risk servers")
    parser.add_argument("--check", metavar="SERVER",
                        help="Check a specific server (partial name match)")
    args = parser.parse_args()

    servers = find_legal_risk_servers()
    if args.list:
        print(f"Legal-risk servers ({len(servers)}):")
        for srv in servers:
            print(f"  - {srv['name']} ({srv['display_name']})")
            print(f"    Consent required: {srv['consent_type']}")
            print(f"    Disclaimer: {srv['disclaimer'][:100]}")
        return 0

    if args.check:
        matched = [s for s in servers if args.check.lower() in s["name"].lower()]
        if not matched:
            print(f"Server '{args.check}' is not a legal-risk server.")
            return 0
        srv = matched[0]
        consent_flags = get_consent_flags()
        identifier = srv["name"].replace("user_", "").replace("_", "-")
        consented = (identifier in consent_flags or
                    srv["name"].lower() in consent_flags or
                    identifier.lower() in consent_flags or
                    consent_flags == {"all"})
        status = "✅ CONSENTED" if consented else "⚠️  NO CONSENT"
        print(f"{srv['display_name']}: {status}")
        return 0

    ok = check_consent(enforce=args.enforce)
    if ok:
        print("✅ Legal-risk MCP servers: consent verified or not applicable.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
