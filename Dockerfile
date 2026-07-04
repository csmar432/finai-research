FROM python:3.11-slim

WORKDIR /app

# ── Install system dependencies ─────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────────────────────
# Uses pyproject.toml directly (requirements.txt is deprecated).
# audit-2026-07-04 PR-3: removed the unreachable `hatchling>=1.32` pin.
# As of 2026-07, hatchling's latest stable on PyPI is 1.30.1; the pin was
# historically wrong. The transitive hatchling dep is now resolved by
# `pip install -e .` from pyproject.toml's build-system.requires.
#
# Files/dirs listed in pyproject.toml [tool.hatch.build.targets.wheel.force-include]
# MUST exist in the build context BEFORE `pip install -e .` runs, otherwise
# hatchling raises `Forced include not found: /app/<dir>`. The force-include
# list (pyproject.toml L209) is: config, templates, knowledge, mcp_servers.
COPY pyproject.toml ./
COPY README.md ./
COPY config/ ./config/
COPY templates/ ./templates/
COPY knowledge/ ./knowledge/
COPY mcp_servers/ ./mcp_servers/
RUN pip install --no-cache-dir -e .

# ── Copy project files ────────────────────────────────────────────────────────
COPY scripts/ ./scripts/
# data/ is excluded by .dockerignore for size/security; mount at runtime:
#   docker run -v "$PWD/data:/app/data" ...
# However, an empty data/ dir is needed at build time so apps that
# touch it (e.g. write to data/cache/) don't fail. Create empty.
RUN mkdir -p ./data && touch ./data/.gitkeep
COPY docs/ ./docs/

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# ── Default entrypoint (override per service) ─────────────────────────────────
CMD ["python", "-m", "scripts.core.llm_gateway"]
