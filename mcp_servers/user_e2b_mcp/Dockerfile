# ─────────────────────────────────────────────────────────────────────────────
# E2B MCP Server
# 数据源：云端代码执行沙箱 — 在隔离云环境中安全执行任意 Python/JS/Shell 代码
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Security: create non-root user
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcpuser

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy server code
COPY server.py .
COPY SERVER_METADATA.json .
COPY tools/ ./tools/
# Copy healthcheck (P0 修复 2026-06-28)
COPY mcp_healthcheck.py /app/mcp_healthcheck.py

# Install Python dependencies (version-pinned)
# P0 修复 2026-06-28: 补齐 e2b-code-interpreter
RUN pip install --no-cache-dir --break-system-packages \
    mcp>=1.1.0 \
    pandas>=2.0.0 \
    python-dotenv>=1.0.0 \
    e2b-code-interpreter>=1.0.0

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \
    CMD python mcp_healthcheck.py --server-dir /app --timeout 10

# Labels
LABEL org.opencontainers.image.title="E2B MCP Server" \
      org.opencontainers.image.description="云端代码执行沙箱 — 在隔离云环境中安全执行任意 Python/JS/Shell 代码" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user_e2b_mcp" \
      finresearch.mcp.api="API" \
      finresearch.mcp.apikey="none"

EXPOSE 8000

# Switch to non-root user
USER mcpuser

CMD ["python", "server.py"]
