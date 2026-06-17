# ─────────────────────────────────────────────────────────────────────────────
# Brave Search MCP Server
# 数据源：Brave Search API（需 BRAVE_SEARCH_API_KEY，免费注册）
# 覆盖：中英文网页搜索、学术资源、政策文件
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Security: create non-root user
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcpuser

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin dependency versions for reproducibility
RUN pip install --no-cache-dir --user \
    "mcp>=1.1.0" \
    "requests>=2.31.0" \
    "python-dotenv>=1.0.0"

# Copy application files
COPY --chown=mcpuser:mcpuser server.py .
COPY --chown=mcpuser:mcpuser SERVER_METADATA.json .
COPY --chown=mcpuser:mcpuser tools/ ./tools/

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PATH=/root/.local/bin:$PATH

# Health check: verify the MCP server responds
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Labels
LABEL org.opencontainers.image.title="Brave Search MCP Server" \
      org.opencontainers.image.description="Brave Search 网络搜索服务。需 BRAVE_SEARCH_API_KEY（免费注册）。" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-brave-search" \
      finresearch.mcp.api="Brave Search API" \
      finresearch.mcp.apikey="required:BRAVE_SEARCH_API_KEY"

EXPOSE 8000

USER mcpuser

CMD ["python", "server.py"]
