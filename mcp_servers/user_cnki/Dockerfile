# ─────────────────────────────────────────────────────────────────────────────
# CNKI MCP Server
# 数据源：中国知网（cnki.net）— 通过网页爬虫实现
# 功能：学术论文搜索、论文详情、引用查询
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

# Pin dependency versions
RUN pip install --no-cache-dir --user \
    "mcp>=1.1.0" \
    "requests>=2.31.0" \
    "beautifulsoup4>=4.12.0" \
    "lxml>=4.9.0" \
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
LABEL org.opencontainers.image.title="CNKI MCP Server" \
      org.opencontainers.image.description="中国知网（CNKI）学术论文检索 — 网页爬虫实现，免费无需 Key" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-cnki" \
      finresearch.mcp.api="CNKI Web Scraping" \
      finresearch.mcp.apikey="none" \
      finresearch.mcp.use_case="中文文献综述/CNKI 论文检索/学术研究"

EXPOSE 8000

USER mcpuser

CMD ["python", "server.py"]
