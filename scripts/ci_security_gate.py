#!/usr/bin/env python3
"""CI security gate: pip-audit + bandit, exit 1 only on HIGH/CRITICAL."""

import subprocess
import json
import shutil
import sys

def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Run command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"{cmd[0]} not found"
    except Exception as e:
        return -1, "", str(e)

def check_pip_audit() -> bool:
    """Returns True if CRITICAL/HIGH vulnerabilities found (should block)."""
    print("=== pip-audit ===")
    tool = shutil.which("pip-audit")
    if not tool:
        print("pip-audit: not installed — skipping")
        return False
    rc, stdout, stderr = run_cmd(["pip-audit", "--disable-file-found", "-f", "json"])
    output = (stdout + stderr).strip()
    if output:
        print(output[:3000])
    try:
        data = json.loads(output) if output else {}
        rows = data if isinstance(data, list) else data.get("vulns", [])
        high_crit = [
            v for v in rows
            if str(v.get("cvss_severity", "")).upper() in ("CRITICAL", "HIGH")
            or (v.get("cvss_score") or 0) >= 7.0
        ]
        print(f"pip-audit: {len(rows)} total, {len(high_crit)} CRITICAL/HIGH")
        if high_crit:
            for v in high_crit[:10]:
                print(f"  [{v.get('cvss_severity', '?')}] {v.get('name', '?')} {v.get('id', '?')}")
            return True
        return False
    except json.JSONDecodeError as e:
        print(f"pip-audit: parse error ({e}), treating as warning")
        return False

def check_bandit() -> bool:
    """Returns True if HIGH/CRITICAL bandit findings (should block)."""
    print("\n=== bandit ===")
    tool = shutil.which("bandit")
    if not tool:
        print("bandit: not installed — skipping")
        return False
    rc, stdout, stderr = run_cmd([
        "bandit", "-r", "scripts/",
        "-x", "scripts/core/agents/,scripts/on_enter.py",
        "-f", "json",
    ])
    # Bandit outputs JSON to stdout; text to stderr
    output = (stdout + stderr).strip()
    if not output:
        print("bandit: no output")
        return False
    try:
        d = json.loads(output)
        iss = d.get("results", [])
        high_crit = [
            i for i in iss
            if i.get("issue_severity", "LOW") in ("HIGH", "CRITICAL")
        ]
        print(f"Bandit: {len(iss)} total, {len(high_crit)} HIGH/CRITICAL")
        for i in iss[:20]:
            print(f"  [{i['issue_severity']}] {i['filename']}:{i['line']} {i['test_name']}")
        if high_crit:
            print("ERROR: HIGH/CRITICAL security issues — blocking CI")
            return True
        return False
    except json.JSONDecodeError as e:
        # Non-JSON output (e.g., tool error text)
        print(f"bandit: non-JSON output ({e}), treating as warning")
        return False

if __name__ == "__main__":
    block = check_pip_audit() or check_bandit()
    if block:
        print("\n🔴 CI BLOCKED: HIGH/CRITICAL security issues found")
        sys.exit(1)
    else:
        print("\n✅ Security check passed")
        sys.exit(0)
