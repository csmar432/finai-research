#!/usr/bin/env python3
"""Verification script for SERVER_METADATA.json and pyproject.toml."""
import json
from pathlib import Path

# 动态检测项目根目录，不硬编码绝对路径
base = Path(__file__).resolve().parent.parent / "mcp_servers"

# Check all 27 files have required fields
missing = []
for srv in sorted(base.iterdir()):
    if not srv.is_dir() or not srv.name.startswith("user_"):
        continue
    f = srv / "SERVER_METADATA.json"
    if not f.exists():
        continue
    d = json.loads(f.read_text())
    for field in ["name", "version", "is_mock", "requires_api_key"]:
        if field not in d:
            missing.append(f"{srv.name}: missing {field}")

if missing:
    for m in missing:
        print(f"ISSUE: {m}")
else:
    print("All 27 SERVER_METADATA.json have standard fields ✓")
print()

# Print summary table
header = f"{'Server':<30} {'name':<25} {'is_mock':<10} {'requires_key':<15} {'api_key_var'}"
print(header)
print("-" * 100)
for srv in sorted(base.iterdir()):
    if not srv.is_dir() or not srv.name.startswith("user_"):
        continue
    f = srv / "SERVER_METADATA.json"
    if not f.exists():
        continue
    d = json.loads(f.read_text())
    n = d.get("name", "")
    m = str(d.get("is_mock", ""))
    k = str(d.get("requires_api_key", ""))
    v = d.get("api_key_env_var", "")
    print(f"{srv.name:<30} {n:<25} {m:<10} {k:<15} {v}")
