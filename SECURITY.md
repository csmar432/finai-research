# Security Policy

## Supported Versions

Only the latest minor version receives security updates.

| Version | Supported          |
|---------|-------------------|
| 0.1.x   | :white_check_mark: Latest |

## Report a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Instead, send a private report:

1. Go to [Report a vulnerability](https://github.com/csmar432/FinAI-Research-Workflow/security/advisories/new)
2. Or email the maintainer directly at the address in [MAINTAINERS.md](./MAINTAINERS.md)

Expected response time: within 7 days.

## Security Disclosures

### API Key Handling

This project accesses financial data APIs. **API keys are sensitive credentials.**

- **Never commit real API keys.** All key-related files (`.env`, `*.key`, `token`) are in `.gitignore`.
- **Use environment variables or a secrets manager.** Never hardcode keys in scripts.
- **Rotate keys regularly.** If a key is leaked, revoke it immediately via the provider's dashboard and rotate.
- **Scope minimally.** Use read-only keys where the API provider supports it (e.g., Tushare read-only tokens).

See `.env.example` for the full list of supported environment variables. Copy it to `.env.local` and fill in only the keys you use.

### Data Security

- **Financial data is sensitive.** Do not commit cache databases (`*.db`, `*.sqlite`, `data/*.parquet`) that contain real stock or company data.
- **Provenance tracking** (`scripts/core/provenance.py`) logs data source and timestamp for every fetch. This audit trail is for reproducibility, not for storing credentials.
- **SQLite caching** uses a 7-day TTL. The cache is stored in `~/.cache/finresearch/` by default.

### Third-Party Data Sources

This project aggregates data from ~43 external MCP servers. Each has its own terms of service and data licensing:

| Source | Risk Level | Notes |
|--------|-----------|-------|
| CNKI / Wanfang | :red_circle: **High** | Web scraping. Legal/consent issues. See `LEGAL_CONSENT.md`. **Opt-in required.** |
| Tushare Pro | :yellow_circle: Medium | Requires paid account. Terms prohibit redistribution of scraped data. |
| Wind | :yellow_circle: Medium | Institutional license required. |
| CSMAR | :yellow_circle: Medium | Academic license required. Redistribution restricted. |
| OpenAlex / ArXiv | :green_circle: Low | CC-BY license. Free for research use. |
| SEC EDGAR | :green_circle: Low | US government data. Public domain. |
| World Bank / IMF / FRED | :green_circle: Low | Public data. Open license. |

**Before using any data source, read its terms of service.** The presence of an MCP server in this project does not imply it is legal to use in your jurisdiction or for your intended purpose.

### Dependency Security

- **Dependabot** is enabled. It opens PRs for outdated dependencies weekly. Review and merge security patches promptly.
- **CI security gate** (`scripts/ci_security_gate.py`) runs `pip-audit` and `safety` checks in the CI pipeline. Do not ignore security advisories without justification.

### Known Limitations

- **No authentication on local SQLite cache.** Anyone with filesystem access to `~/.cache/finresearch/` can read cached data.
- **No encryption at rest.** Data fetched from APIs is stored in plain SQLite.
- **No audit log access control.** Provenance logs are world-readable by default.
- **Docker**: If you run this project in Docker, review `docker-compose.yml` before deploying. Some services (CNKI, Wanfang) should be disabled for corporate environments.

---

*Last reviewed: 2026-06-25*
