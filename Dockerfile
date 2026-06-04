FROM python:3.11-slim

WORKDIR /app

# ── Install system dependencies ─────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────────────────────
# Uses pyproject.toml directly (requirements.txt is deprecated)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# ── Copy project files ────────────────────────────────────────────────────────
COPY pyproject.toml ./
COPY scripts/ ./scripts/
COPY mcp_servers/ ./mcp_servers/
COPY config/ ./config/
COPY data/ ./data/
COPY docs/ ./docs/
COPY knowledge/ ./knowledge/

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# ── Default entrypoint (override per service) ─────────────────────────────────
CMD ["python", "-m", "scripts.core.llm_gateway"]
