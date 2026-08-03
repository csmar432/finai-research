# Professional audit remediation — 2026-08-03

Baseline: `ec577d2`. This record distinguishes confirmed defects from audit
recommendations that would be unsafe or misleading to apply mechanically.

## Confirmed and remediated

| Finding | Resolution |
|---|---|
| P0-1 mock guard fail-open | Removed every server-local permissive fallback. Servers import the shared fail-closed guard through `mcp_servers.mcp_mock_helper`; regression tests reject any future local redefinition. |
| P0-2 fabricated FOMC data | Replaced hardcoded decisions/rates with official meeting dates and FRED `DFEDTARL`/`DFEDTARU` observations. Missing network data is reported as unavailable. Fabricated Beige Book metadata was also removed. |
| P0-3 CI/dependency drift | Bounded MCP to 1.x, aligned direct constraints, regenerated locks, made CI consume the CI lock, restored Ruff, and declared the missing Graphviz Python dependency. |
| P1-1 generated Python execution | Removed host-process compilation/execution. Dynamic tools and LLM-generated figure code are disabled by default; the compatibility opt-in is explicitly documented as unsafe and requires external isolation. |
| P1-2 security gate fail-open | Missing tools, malformed/empty output, unknown vulnerability severity, and scanner errors now block. Full locked dependencies and all `scripts/` + `mcp_servers/` are scanned. CodeQL was added. |
| P1-4 Actions supply chain | Every third-party Action is pinned to a full commit SHA. Two nonexistent Sigstore Actions were replaced by the official Cosign installer with GitHub OIDC signing and immediate verification. |
| P1-5 dependency SSOT | CI uses `requirements-ci-lock.txt`; constraints match the package bounds. Runtime test dependencies moved to `dev`; four confirmed-unused full-install dependencies were removed. `pandasql` was retained because an MCP server imports it. |
| P1-6 coverage gate | A clean full run measured 58.3%; the aggregate gate was raised from 28% to 55%, retaining a small cross-platform margin toward 60%. Critical remediation paths have dedicated regression tests. |
| P2-1 environment reproducibility | Validation used fresh environments created from universal locks, without modifying the maintainer's existing virtual environment. Python 3.10 and 3.13 boundary installs and smoke tests passed; BLAS threads are bounded in CI to prevent xdist oversubscription. |
| P2-2/P2-3 policy/version drift | Security support and scanner documentation were corrected; the release version and user-facing references now use canonical PEP 440 `0.2.0a0`. |
| P2-5 confirmed static security findings | Bandit's four HIGH findings were remediated; the complete scan now reports zero HIGH/CRITICAL findings. |

## Recommendations not applied mechanically

- The report's statement that all 16 mock imports failed was overstated: most
  package imports worked, but every permissive fallback was still a real
  fail-open defect and was removed.
- A 43-server shared MCP adapter was not introduced during a security repair.
  Pinning MCP 1.x plus import and stdio protocol contracts restores the public
  contract without a high-risk rewrite of every data service.
- Legacy registries, public compatibility facades, Vuong wrappers, and the two
  clustered-SE implementations remain. They have compatibility or numerical
  callers; deleting/consolidating them requires a separately versioned migration
  and cross-software numerical equivalence tests.
- Complexity and LOW/MEDIUM static warnings are review surfaces, not evidence of
  exploitable defects. Mass refactoring statistical code would increase model
  risk; only confirmed security and reproducibility defects were changed here.
- A second human maintainer/release custodian cannot be created by code. Repository
  protection and required checks reduce the current single-maintainer risk.

## Verification evidence

- Follow-up clean-environment suite: 12,871 passed, 157 skipped, 83 xfailed,
  3 xpassed; 58.3% branch coverage. The follow-up also adds exact-word
  mock approval checks and covers all 17 guarded servers.
- The CI coverage job now separately enforces >=75% on an explicit critical
  research-path list (current local branch coverage: 87.4%); the aggregate
  repository metric remains visible and is not artificially narrowed.
- The 10 tests that timed out under unconstrained parallel BLAS all passed in a
  single-thread rerun; the final CI-equivalent run passed with bounded BLAS.
- `audit_guard.py`: 25/25 checks passed.
- `pip-audit`: 109 locked packages, zero known vulnerabilities.
- Bandit: 477 findings reviewed by severity, zero HIGH/CRITICAL.
- Package build and `twine check`: sdist and wheel passed as `0.2.0a0`.
- Universal CI lock: clean installs and 127-test smoke runs passed on both
  Python 3.10 and 3.13 (116 passed, 11 skipped per interpreter).
