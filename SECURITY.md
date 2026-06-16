# Security Policy

## Supported Versions

| Version | Supported          | Notes |
| ------- | ------------------ | ----- |
| 1.x.x   | :white_check_mark: | Current stable release |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub Issue.
2. Send a private disclosure to the maintainers via:
   - GitHub Security Advisories (preferred): [Report a vulnerability](https://github.com/csmar432/finai-research-workflow/security/advisories/new)
   - Or email the maintainers directly.

3. Please include as much of the following as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (optional)

4. We aim to acknowledge within **48 hours** and provide a timeline for the fix.

## Security Best Practices for Users

When using this project, be aware of the following:

### API Keys

- **Never commit API keys** to the repository. Use environment variables (`.env` files are in `.gitignore`).
- Do not share your `TUSHARE_TOKEN`, `EODHD_API_KEY`, `FRED_API_KEY`, `BRAVE_SEARCH_API_KEY`, or any other credentials.
- Consider using a secrets manager (e.g., macOS Keychain, 1Password CLI) for local development.

### Data Privacy

- User-uploaded data in `data/user_uploaded/` is ignored by git and never committed.
- Research outputs in `papers/` are ignored by git.
- Pipeline telemetry (`data/pipeline_telemetry.jsonl`) is ignored by git.

### Third-Party MCP Servers

- MCP servers communicate with external APIs. Review each server's `server.py` before deploying.
- When using `user-tushare` (requires Tushare Pro token) or `user-brave-search` (requires Brave API key), ensure your credentials are stored securely.
- Docker-based MCP servers run as non-root users (`mcpuser`) inside containers for isolation.

### LLM API Calls

- All LLM calls go through user-provided API keys (DeepSeek, OpenAI, Anthropic, etc.).
- No data is transmitted to third parties beyond the explicitly configured API providers.
- Review `scripts/core/llm_reviewer.py` and `scripts/core/agent_state.py` for data handling.

### Container Security

- All 43 MCP Docker containers run as non-root users.
- Use `docker-compose.yml` with read-only filesystem where possible:
  ```yaml
  services:
    mcp_arxiv:
      read_only: true
      tmpfs:
        - /tmp
  ```

## Dependency Security

- Dependencies are pinned with minimum version constraints in `pyproject.toml`.
- Run `pip audit` periodically to check for known vulnerabilities:
  ```bash
  pip install pip-audit
  pip-audit
  ```
- Use Dependabot (enabled in `.github/dependabot.yml`) to keep dependencies updated.
