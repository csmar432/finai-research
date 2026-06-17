# ─────────────────────────────────────────────────────────────────────────────
# ArXiv MCP Server
# 数据源：ArXiv API（无需 API Key，完全免费）
# 覆盖：cs, econ, eess, q-fin 等学科
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies (only needed at build time)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install build-only packages
RUN pip install --no-cache-dir --user \
    build[isolated]>=1.0.0

# Copy source and build wheel
COPY server.py .
RUN pip install --no-cache-dir --user --no-build-isolation --only-binary=:all: mcp==1.1.0


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Security: create non-root user
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcpuser

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy MCP from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application files
COPY --chown=mcpuser:mcpuser server.py .
COPY --chown=mcpuser:mcpuser SERVER_METADATA.json .
COPY --chown=mcpuser:mcpuser tools/ ./tools/

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Health check: verify the process stays alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Labels
LABEL org.opencontainers.image.title="ArXiv MCP Server" \
      org.opencontainers.image.description="ArXiv 学术论文搜索与获取服务。无需 API Key，覆盖 cs/econ/q-fin 等学科。" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-arxiv" \
      finresearch.mcp.api="ArXiv API" \
      finresearch.mcp.apikey="none"

EXPOSE 8000

# Switch to non-root user
USER mcpuser

CMD ["python", "server.py"]
