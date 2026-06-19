# ─────────────────────────────────────────────────────────────────────────────
# CNRDS MCP Server — 中国研究数据服务平台
# 数据源：https://www.cnrds.com（需注册获取 API Key）
# 覆盖：专利数据、学术论文、上市公司财务、高新技术企业认定
# 注册：https://www.cnrds.com/Account/Register
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Security: create non-root user
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcpuser

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin dependency versions (httpx for async HTTP)
RUN pip install --no-cache-dir --user \
    "mcp>=1.1.0" \
    "httpx>=0.27.0" \
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

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD kill -0 1

# Labels
LABEL org.opencontainers.image.title="CNRDS MCP Server" \
      org.opencontainers.image.description="中国研究数据服务平台。专利/学术论文/上市公司财务/高企认定数据。" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-cnrd" \
      finresearch.mcp.api="CNRDS API" \
      finresearch.mcp.apikey="required:CNRDS_API_KEY" \
      finresearch.mcp.use_case="专利分析/企业创新/高新技术企业研究"

EXPOSE 8000

USER mcpuser

CMD ["python", "server.py"]
