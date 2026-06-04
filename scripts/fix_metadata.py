#!/usr/bin/env python3
"""Fix all SERVER_METADATA.json files to include standard fields.

Adds: name, version, is_mock, requires_api_key, api_key_env_var
in standard key order (standard fields first, then original fields).
"""

import json
import re
from pathlib import Path

# 动态检测项目根目录，不硬编码绝对路径
BASE = Path(__file__).resolve().parent.parent / "mcp_servers"

STANDARD_KEYS = ["name", "version", "is_mock", "requires_api_key", "api_key_env_var"]

# Manual name overrides for servers with acronym or generic identifiers
NAME_OVERRIDES = {
    "user_bea_data": "BEA Data",
    "user_csmar": "CSMAR",
    "user_imf_data": "IMF Data",
    "user_nber_wp": "NBER Working Papers",
    "user_oecd_data": "OECD Data",
    "user_province_stats": "Province Stats",
    "user_tushare": "Tushare",
    "user_wb_data": "World Bank Data",
}

# Explicit is_mock overrides (overrides auto-detection)
IS_MOCK_OVERRIDES = {
    "user_bea_data": False,  # Real BEA API when BEA_API_KEY is set
    "user_tushare": False,  # Real Tushare Pro API, needs token
}

# Explicit requires_api_key overrides
REQUIRES_KEY_OVERRIDES = {
    "user_bea_data": ("BEA_API_KEY", True),
    "user_e2b_mcp": ("E2B_API_KEY", True),
    "user_tushare": ("TUSHARE_TOKEN", True),
}


def derive_name(data: dict) -> str:
    """Derive a readable name from server_name or serverIdentifier.

    Skips generic 'user_*' identifiers when no server_name is present.
    """
    server_name = data.get("server_name", "")
    server_id = data.get("serverIdentifier", "")

    raw = server_name or server_id or ""

    # Skip generic user_* patterns when server_name is absent
    if not server_name and raw.startswith("user_"):
        suffix = raw.replace("user_", "").replace("_", " ").replace("-", " ")
        return suffix.title() if suffix else "Unnamed Server"

    return raw.replace("_", " ").replace("-", " ").title()


def derive_is_mock(srv_dir: Path, data: dict, srv_py: Path) -> bool:
    """Determine is_mock by checking description and server.py imports."""
    desc = data.get("description", "")

    # Explicit mock keywords in description
    if any(kw in desc for kw in ["演示", "模拟数据", "示例"]):
        return True

    if not srv_py.exists():
        return False

    content = srv_py.read_text()

    # Has mcp_mock_helper import → mock
    if "mcp_mock_helper" in content:
        return True

    return False


def derive_requires_api_key(srv_dir: Path, data: dict, srv_py: Path) -> tuple[bool, str | None]:
    """Determine requires_api_key and api_key_env_var (fallback for servers not in overrides)."""
    desc = data.get("description", "")

    has_key_kw = any(kw in desc for kw in ["机构账号", "注册", "需注册", "API Key", "API key"])

    if srv_py.exists():
        content = srv_py.read_text()
        if "mcp_mock_helper" in content:
            if has_key_kw:
                match = re.search(r"([A-Z][A-Z0-9_]*)_?API_?KEY", desc, re.IGNORECASE)
                if match:
                    return True, match.group(1).upper() + "_API_KEY"
                return True, None
            return False, None

    if has_key_kw:
        match = re.search(r"([A-Z][A-Z0-9_]*)_?API_?KEY", desc, re.IGNORECASE)
        if match:
            return True, match.group(1).upper() + "_API_KEY"
        return True, None

    return False, None


def fix_metadata(srv_dir: Path) -> None:
    meta_file = srv_dir / "SERVER_METADATA.json"
    srv_py = srv_dir / "server.py"

    if not meta_file.exists():
        return

    data = json.loads(meta_file.read_text())

    srv_key = srv_dir.name  # e.g. "user_tushare"
    is_mock = derive_is_mock(srv_dir, data, srv_py)
    requires_key, api_key_var = derive_requires_api_key(srv_dir, data, srv_py)

    # ── Apply standard fields ─────────────────────────────────────────────────
    # Name: override > existing > derive
    if srv_key in NAME_OVERRIDES:
        data["name"] = NAME_OVERRIDES[srv_key]
    elif "name" not in data or not data["name"]:
        data["name"] = derive_name(data)
    if "version" not in data:
        data["version"] = "1.0.0"
    # is_mock: override > auto-detect
    if srv_key in IS_MOCK_OVERRIDES:
        data["is_mock"] = IS_MOCK_OVERRIDES[srv_key]
    elif "is_mock" not in data:
        data["is_mock"] = is_mock
    # requires_api_key + api_key_env_var: override > auto-detect > existing
    if srv_key in REQUIRES_KEY_OVERRIDES:
        api_key_var, requires_key = REQUIRES_KEY_OVERRIDES[srv_key]
        data["requires_api_key"] = requires_key
        if api_key_var:
            data["api_key_env_var"] = api_key_var
    elif "requires_api_key" not in data:
        data["requires_api_key"] = requires_key
        if api_key_var and "api_key_env_var" not in data:
            data["api_key_env_var"] = api_key_var

    # Rebuild: standard keys first, then the rest
    result = {}
    for k in STANDARD_KEYS:
        if k in data:
            result[k] = data[k]
    for k, v in data.items():
        if k not in STANDARD_KEYS:
            result[k] = v

    meta_file.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    mock_flag = " [MOCK]" if result.get("is_mock") else ""
    key_info = ""
    if result.get("api_key_env_var"):
        key_info = f" [key:{result['api_key_env_var']}]"
    elif result.get("requires_api_key"):
        key_info = " [requires-key]"
    else:
        key_info = " [no-key]"
    print(f"  {srv_key}{mock_flag}{key_info}  →  name={result.get('name')!r}")


def main():
    print("Fixing SERVER_METADATA.json files...\n")
    count = 0
    for srv_dir in sorted(BASE.iterdir()):
        if not srv_dir.is_dir() or not srv_dir.name.startswith("user_"):
            continue
        fix_metadata(srv_dir)
        count += 1
    print(f"\nDone. Fixed {count} files.")


if __name__ == "__main__":
    main()
