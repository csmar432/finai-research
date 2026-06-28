# ─────────────────────────────────────────────────────────────────────────────
# Playwright MCP Server
# 数据源：浏览器自动化 MCP — 网页导航/截图/表格抓取/表单填写/JS执行/文件下载
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Security: create non-root user
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home mcpuser

# Install system dependencies
# P0 修复 2026-06-28: 补齐 playwright + chromium（之前 Dockerfile 缺浏览器）
# user_playwright_mcp 是浏览器自动化 MCP，server.py 调用 playwright.sync_api 启 chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    # Chromium 运行时依赖
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy server code
COPY server.py .
COPY SERVER_METADATA.json .
COPY tools/ ./tools/
# Copy healthcheck (P0 修复 2026-06-28)
COPY mcp_healthcheck.py /app/mcp_healthcheck.py

# Install Python dependencies (version-pinned)
RUN pip install --no-cache-dir --break-system-packages \
    mcp>=1.1.0 \
    playwright>=1.40.0

# 安装 chromium 浏览器（playwright install chromium）
RUN playwright install --with-deps chromium 2>/dev/null || playwright install chromium

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \
    CMD python mcp_healthcheck.py --server-dir /app --timeout 10

# Labels
LABEL org.opencontainers.image.title="Playwright MCP Server" \
      org.opencontainers.image.description="浏览器自动化 MCP — 网页导航/截图/表格抓取/表单填写/JS执行/文件下载" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user_playwright_mcp" \
      finresearch.mcp.api="API" \
      finresearch.mcp.apikey="none"

EXPOSE 8000

# Switch to non-root user
USER mcpuser

CMD ["python", "server.py"]
