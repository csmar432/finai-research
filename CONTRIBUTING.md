# Contributing to FinAI-Research-Workflow

Thank you for your interest in contributing. This project is in active development — all contributions are welcome, from fixing typos to adding new econometric methods.

## Ways to Contribute

| Type | Description |
|------|-------------|
| :bug: Bug reports | Something doesn't work? Open an issue with minimal reproduction steps. |
| :sparkles: Feature requests | Missing a data source? A new estimator? Open an issue with the use case. |
| :wrench: Code contributions | Fix bugs, add tests, improve documentation. |
| :books: Documentation | Fix unclear docs, add examples, translate to other languages. |
| :chart_with_upwards_trend: New research methods | Add econometric implementations with tests and usage examples. |

## Quick Start

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/FinAI-Research-Workflow.git
cd FinAI-Research-Workflow

# 2. Set up a virtual environment
python -m venv .venv && source .venv/bin/activate  # macOS/Linux
python -m venv .venv && .venv\Scripts\activate     # Windows

# 3. Install in editable mode with all dependencies
pip install -e ".[dev]"

# 4. Run the test suite
pytest tests/ -v

# 5. Run the linter
ruff check scripts/ tests/

# 6. Create a branch for your changes
git checkout -b fix/my-bug-fix
```

## Development Standards

### Code Style

- **Python**: Follow [PEP 8](https://pep8.org/). Run `ruff check` before committing.
- **Docstrings**: All public functions and classes must have docstrings. Use Google style for research framework modules.
- **Type hints**: All new functions should have type hints for parameters and return values.
- **No `print()` for debugging**: Use `logging` module with appropriate log levels.

### Testing

- **Minimum coverage**: New code should have tests. No PR should intentionally decrease coverage.
- **Test location**: Tests live in `tests/`, mirroring the `scripts/` structure.
- **No placeholder tests**: Do not commit `assert True` or empty `pass` as tests.
- **Data fixtures**: Use synthetic/random data for tests. Do not commit real financial data.

```python
# Example test structure
import pytest
import numpy as np

def test_my_function():
    # Arrange: synthetic data
    X = np.random.randn(100, 2)
    y = X @ np.array([1.0, -0.5]) + np.random.randn(100) * 0.1

    # Act
    result = my_function(X, y)

    # Assert
    assert result.shape == (2,)
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
fix(module): resolve null pointer in data fetcher
feat(research_framework): add Callaway-SantAnna estimator
docs(readme): fix typo in installation instructions
test(modern_did): add regression test for event study
```

### File Organization

| Directory | Contents |
|-----------|---------|
| `scripts/` | Core business logic. All Python files must be runnable. |
| `scripts/research_framework/` | Econometric methods. No breaking changes to public APIs. |
| `tests/` | Test files, mirroring `scripts/` structure. |
| `docs/` | Documentation. Markdown files in `mkdocs.yml` nav. |
| `mcp_servers/` | MCP server implementations. |

## Opening a Pull Request

1. **Fork first.** Do not push directly to `main`.
2. **One focus per PR.** A PR fixing a bug and also refactoring unrelated code will be asked to be split.
3. **Fill out the PR template.** Describe what changed, why, and how to test it.
4. **Link the issue.** If your PR fixes an issue, reference it with "Fixes #123".
5. **CI must pass.** All three test batches, lint, and coverage checks must pass before merging.
6. **Minimum reviewers**: 1. Since this is a solo-maintained project, the maintainer (csmar432) will review all PRs.

## Data Source Contributions

Adding a new data source? Follow this checklist:

- [ ] Add MCP server directory under `mcp_servers/user_<name>/`
- [ ] Implement `server.py` with tool definitions
- [ ] Add `SERVER_METADATA.json` with description, auth requirements, rate limits
- [ ] Add `Dockerfile` if the server has runtime dependencies
- [ ] Update `config/mcp_profiles.json` with the new server in the appropriate profile
- [ ] Update `scripts/PROJECT_NUMBERS.json` (run `python scripts/sync_numbers.py --apply` after)
- [ ] Add tests in `tests/test_data_fetcher.py` or `tests/test_mcp_*.py`
- [ ] Update `README.md` and `CLAUDE.md` with the new data source

## Econometric Method Contributions

Adding a new estimator? Follow this checklist:

- [ ] Implement in `scripts/research_framework/<method>.py`
- [ ] Add docstring with mathematical formulation, references, and usage example
- [ ] Return a typed `dataclass` result (not raw dict)
- [ ] Add tests with synthetic data
- [ ] Update `scripts/PROJECT_NUMBERS.json`
- [ ] Add to `scripts/research_framework/regression_engine.py` if applicable
- [ ] Update `docs/` or `CLAUDE.md` if the method changes the documented count

## Questions?

- Open a [GitHub Discussion](https://github.com/csmar432/FinAI-Research-Workflow/discussions) for questions not suitable for an Issue.
- For security issues, see [SECURITY.md](./SECURITY.md) — do **not** open a public Issue.

---

*By contributing, you agree that your contributions will be licensed under the project's MIT License.*
