#!/usr/bin/env python3
"""Fail-closed CI security gate for pip-audit and Bandit."""

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
    """Return True when pip-audit finds a blocking issue or cannot be trusted."""
    print("=== pip-audit ===")
    tool = shutil.which("pip-audit")
    if not tool:
        print("pip-audit: not installed — blocking")
        return True
    rc, stdout, stderr = run_cmd([
        "pip-audit", "-r", "requirements-ci-lock.txt", "-f", "json",
    ])
    # 只解析 stdout (JSON 一定在 stdout)。stderr 单独打印为诊断日志，避免污染 JSON。
    output = stdout.strip() if stdout else ""
    if stderr.strip():
        for line in stderr.strip().splitlines()[:5]:
            print(f"  [pip-audit stderr] {line}")
    if output:
        print(output[:3000])
    try:
        # P3-audit-2026-07-03: pip-audit >=2.0 改为 {"dependencies": [{"name": ..., "version": ..., "vulns": [...]}]}
        # 老脚本误以为是 array 或 {vulns: ...}，会 parse error 然后 fallback 静默通过。
        if not output:
            print("pip-audit: no output — blocking")
            return True
        data = json.loads(output)
        if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
            print("pip-audit: unexpected JSON schema — blocking")
            return True
        deps = data["dependencies"]
        all_vulns = [v for d in deps for v in d.get("vulns", [])]
        high_crit = [
            v for v in all_vulns
            if str(v.get("cvss_severity", "")).upper() in ("CRITICAL", "HIGH")
            or (v.get("cvss_score") or 0) >= 7.0
            or not v.get("cvss_severity") and v.get("cvss_score") is None
        ]
        print(f"pip-audit: {len(all_vulns)} total vulns across {len(deps)} packages, "
              f"{len(high_crit)} CRITICAL/HIGH")
        if high_crit:
            for v in high_crit[:10]:
                sev = v.get("cvss_severity") or f"score={v.get('cvss_score', '?')}"
                print(f"  [{sev}] {v.get('name', '?')} {v.get('id', '?')}")
            return True
        return rc not in (0, 1)
    except json.JSONDecodeError as e:
        print(f"pip-audit: parse error ({e}), blocking")
        return True

def check_bandit() -> bool:
    """Return True when Bandit finds a blocking issue or cannot be trusted."""
    print("\n=== bandit ===")
    tool = shutil.which("bandit")
    if not tool:
        print("bandit: not installed — blocking")
        return True
    rc, stdout, stderr = run_cmd([
        "bandit", "-r", "scripts/", "mcp_servers/",
        "-f", "json",
        "-q",  # 静默模式：去掉 progress bar 和 INFO 日志 (写到 stderr)
        "--quiet",
    ])
    output = stdout.strip() if stdout else ""
    if not output:
        print("bandit: no output — blocking")
        return True
    try:
        d = json.loads(output)
        if not isinstance(d, dict) or not isinstance(d.get("results"), list):
            print("bandit: unexpected JSON schema — blocking")
            return True
        iss = d["results"]
        high_crit = [
            i for i in iss
            if i.get("issue_severity", "LOW") in ("HIGH", "CRITICAL")
        ]
        print(f"Bandit: {len(iss)} total, {len(high_crit)} HIGH/CRITICAL")
        for i in iss[:20]:
            # bandit >=1.7 改用 line_number；老版本用 line（同时兼容）
            line = i.get("line_number", i.get("line", "?"))
            print(f"  [{i['issue_severity']}] {i['filename']}:{line} {i['test_name']}")
        if high_crit:
            print("ERROR: HIGH/CRITICAL security issues — blocking CI")
            return True
        return rc not in (0, 1)
    except json.JSONDecodeError as e:
        # Non-JSON output (e.g., tool error text)
        print(f"bandit: non-JSON output ({e}), blocking")
        return True

if __name__ == "__main__":
    pip_block = check_pip_audit()
    bandit_block = check_bandit()
    block = pip_block or bandit_block
    if block:
        print("\n🔴 CI BLOCKED: HIGH/CRITICAL security issues found")
        sys.exit(1)
    else:
        print("\n✅ Security check passed")
        sys.exit(0)
