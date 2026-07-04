"""
Root conftest.py — ensure project root is on sys.path for all pytest
test collection, regardless of pytest-xdist worker subprocess behavior.

audit-2026-07-04 PR-2 follow-up: the previous batch architecture
implicitly avoided this issue by using explicit test lists per job.
Unifying into 'pytest tests/' exposes that the only sys.path injection
came from tests/conftest.py, which pytest-xdist worker subprocesses
may run after some module imports have already been attempted.

This root conftest runs before any test module is imported, so the
sys.path insertion is guaranteed to take effect for the entire
collection phase.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.resolve()
print(f"[conftest] project_root={_PROJECT_ROOT}")
print(f"[conftest] sys.path before insert: {[p for p in sys.path if 'runner' in p or 'workspace' in p]}")
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
    print(f"[conftest] inserted {_PROJECT_ROOT}")
print(f"[conftest] scripts.core.debate_arena importable: ", end="")
try:
    import scripts.core.debate_arena  # noqa: F401
    print("YES")
except Exception as e:
    print(f"NO ({e})")