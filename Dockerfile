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
# Pin hatchling>=1.32 to avoid `AttributeError: module 'hatchling.build'
# has no attribute 'prepare_metadata_for_build_editable'`. Older 1.30.x
# releases lack this hook, which modern pip (>=24) calls. See issue
# https://github.com/pypa/pip/issues/12963 for context.
COPY pyproject.toml ./
RUN pip install --no-cache-dir "hatchling>=1.32" && \
    pip install --no-cache-dir -e .

# ── Copy project files ────────────────────────────────────────────────────────
COPY pyproject.toml ./
COPY scripts/ ./scripts/
COPY mcp_servers/ ./mcp_servers/
COPY config/ ./config/
# data/ is in .gitignore; create placeholder so COPY does not fail.
# Mount real data at runtime: docker run -v "$PWD/data:/app/data" ...
COPY data/.gitkeep ./data/.gitkeep
COPY docs/ ./docs/
COPY knowledge/ ./knowledge/

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# ── Default entrypoint (override per service) ─────────────────────────────────
CMD ["python", "-m", "scripts.core.llm_gateway"]
