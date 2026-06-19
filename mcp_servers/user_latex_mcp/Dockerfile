# ─────────────────────────────────────────────────────────────────────────────
# LaTeX MCP Server
# 数据源：LaTeX 论文写作工具链 — 编译 PDF、语法检查、公式渲染、BibTeX 检查
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

# Install Python dependencies (version-pinned)
RUN pip install --no-cache-dir --break-system-packages \
    mcp>=1.1.0

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD kill -0 1

# Labels
LABEL org.opencontainers.image.title="LaTeX MCP Server" \
      org.opencontainers.image.description="LaTeX 论文写作工具链 — 编译 PDF、语法检查、公式渲染、BibTeX 检查" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user_latex_mcp" \
      finresearch.mcp.api="API" \
      finresearch.mcp.apikey="none"

EXPOSE 8000

# Switch to non-root user
USER mcpuser

CMD ["python", "server.py"]
