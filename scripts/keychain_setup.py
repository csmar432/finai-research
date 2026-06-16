"""Cross-platform secret-storage migration tool.

Migrates API keys and tokens from plain-text ``.env`` / ``.env.local`` files into
the operating system's secure credential store:

  - **macOS**  : Keychain (``security`` CLI)
  - **Linux**  : Secret Service (GNOME Keyring / KWallet) via ``secretstorage``
  - **Windows**: Credential Manager via ``keyring``

After migration, scripts that previously relied on ``os.getenv("FOO")`` continue
to work because the :func:`get_key` helper below first checks the credential
store and only falls back to environment variables / ``.env`` if nothing is
stored.

Why?
----
Plain-text ``.env`` files are easy to leak — one stray ``git add .`` and your
keys are in the public history.  Migrating to the platform credential store
keeps the keys encrypted at rest and tied to your OS user account.

Usage
-----

::

    # Interactive: type each value, then store it
    python scripts/keychain_setup.py --register

    # Migrate from an existing .env file (non-interactive; uses current values)
    python scripts/keychain_setup.py --migrate .env.local

    # List what's currently stored
    python scripts/keychain_setup.py --list

    # Delete a single key
    python scripts/keychain_setup.py --delete DEEPSEEK_API_KEY

    # Test that the system can read keys back
    python scripts/keychain_setup.py --test

The script is a no-op if the platform credential store is not available
(``keyring`` library missing); the project continues to read keys from
``os.getenv()`` / ``.env`` as before.
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path
from typing import Iterable


SERVICE_NAME = "finai-research-workflow"

# Keys the project cares about (matches `.env.example`).
KNOWN_KEYS: tuple[str, ...] = (
    "DEEPSEEK_API_KEY",
    "RELAY_API_KEY",
    "TUSHARE_TOKEN",
    "EODHD_API_KEY",
    "FRED_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "NEWSAPI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "TIINGO_API_KEY",
    "E2B_API_KEY",
    "CSMAR_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def _get_keyring():
    """Return the keyring backend or None if unavailable."""
    try:
        import keyring  # type: ignore
        return keyring
    except ImportError:
        return None


def get_key(name: str, default: str | None = None) -> str | None:
    """Read ``name`` from the credential store, falling back to env / default."""
    kr = _get_keyring()
    if kr is not None:
        try:
            val = kr.get_password(SERVICE_NAME, name)
            if val:
                return val
        except Exception:  # noqa: BLE001
            pass
    return os.getenv(name, default)


def set_key(name: str, value: str) -> bool:
    """Write ``name`` to the credential store.  Returns True on success."""
    kr = _get_keyring()
    if kr is None:
        print("ERROR: `keyring` library not installed.  Run: pip install keyring",
              file=sys.stderr)
        return False
    try:
        kr.set_password(SERVICE_NAME, name, value)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to store {name}: {exc}", file=sys.stderr)
        return False


def delete_key(name: str) -> bool:
    kr = _get_keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE_NAME, name)
        return True
    except Exception:  # noqa: BLE001
        return False


def list_keys() -> list[tuple[str, str]]:
    """Return (name, mask) tuples for every key currently stored."""
    kr = _get_keyring()
    if kr is None:
        return []
    found: list[tuple[str, str]] = []
    for name in KNOWN_KEYS:
        try:
            val = kr.get_password(SERVICE_NAME, name)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            mask = val[:4] + "…" + val[-2:] if len(val) > 8 else "***"
            found.append((name, mask))
    return found


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` env file (ignores comments / blanks)."""
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def cmd_register(_args: argparse.Namespace) -> int:
    """Interactively prompt for each known key and store it."""
    print(f"Detected platform: {platform.system()}")
    print(f"Service name: {SERVICE_NAME}")
    print()
    if _get_keyring() is None:
        print("ERROR: `keyring` is not installed.  Install it first:")
        print("    pip install keyring")
        return 1
    stored = 0
    for name in KNOWN_KEYS:
        existing = get_key(name)
        if existing:
            ans = input(f"  {name} already set (****).  Overwrite? [y/N]: ").strip().lower()
            if ans != "y":
                continue
        else:
            ans = input(f"  Set {name}? [y/N]: ").strip().lower()
            if ans != "y":
                continue
        val = input(f"  Value for {name}: ").strip()
        if not val:
            print(f"  Skipping {name} (empty value).")
            continue
        if set_key(name, val):
            print(f"  ✅ {name} stored")
            stored += 1
        else:
            print(f"  ❌ {name} failed")
    print(f"\n{stored} key(s) stored.  Verify with: python scripts/keychain_setup.py --list")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    src = Path(args.migrate).expanduser().resolve()
    env = _parse_env_file(src)
    if not env:
        print(f"ERROR: no key=value pairs found in {src}", file=sys.stderr)
        return 1
    print(f"Migrating {len(env)} entries from {src} → {platform.system()} credential store")
    print()
    stored = 0
    for k, v in env.items():
        if not v or v in {"your_key_here", "dummy", "xxx", "<placeholder>"}:
            print(f"  ⊘ {k}: empty or placeholder, skipping")
            continue
        if set_key(k, v):
            print(f"  ✅ {k}: stored")
            stored += 1
        else:
            print(f"  ❌ {k}: failed")
    print(f"\n{stored} key(s) stored.")
    print("Next steps:")
    print("  1. Verify: python scripts/keychain_setup.py --list")
    print("  2. Test:   python scripts/keychain_setup.py --test")
    print("  3. Manually edit the .env file to clear the values (or delete it).")
    print()
    print("WARNING: Leaving real keys in .env after migration defeats the purpose.")
    print("         Consider `rm .env .env.local` once you've confirmed everything works.")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    rows = list_keys()
    if not rows:
        print("No keys found in credential store.")
        return 0
    print(f"{'KEY':<28} {'VALUE (masked)'}")
    print("─" * 50)
    for name, mask in rows:
        print(f"  {name:<26} {mask}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    if delete_key(args.delete):
        print(f"✅ {args.delete} deleted from credential store")
        return 0
    print(f"❌ {args.delete} not found or delete failed", file=sys.stderr)
    return 1


def cmd_test(_args: argparse.Namespace) -> int:
    """Verify that known keys can be read from the credential store."""
    print("Testing key retrieval from credential store:")
    print()
    ok = 0
    miss = 0
    for name in KNOWN_KEYS:
        v = get_key(name)
        if v:
            print(f"  ✅ {name}: {v[:4]}…{v[-2:]} ({len(v)} chars)")
            ok += 1
        else:
            print(f"  ⊘ {name}: not set")
            miss += 1
    print(f"\nResult: {ok} stored, {miss} missing")
    if miss:
        print("Tip: run `python scripts/keychain_setup.py --register` to set them.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="keychain_setup.py",
        description=__doc__.splitlines()[0] if __doc__ else "Keychain migration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__ if __doc__ else "",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--register", action="store_true",
                      help="Interactively prompt for each known key and store it")
    mode.add_argument("--migrate", metavar="ENV_FILE",
                      help="Read keys from an existing .env file and store them")
    mode.add_argument("--list", action="store_true",
                      help="List all keys currently in the credential store")
    mode.add_argument("--delete", metavar="KEY_NAME",
                      help="Delete a single key from the credential store")
    mode.add_argument("--test", action="store_true",
                      help="Verify that keys can be read back")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "register": cmd_register,
        "migrate": cmd_migrate,
        "list": cmd_list,
        "delete": cmd_delete,
        "test": cmd_test,
    }
    for action in ("register", "migrate", "list", "delete", "test"):
        if getattr(args, action, None) if action != "list" else args.list:
            return dispatch[action](args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
