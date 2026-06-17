# ─────────────────────────────────────────────────────────────────────────────
# Chinese Customs MCP Server
# 数据源：中国海关统计数据在线查询系统（https://stats.customs.gov.cn）
# 覆盖：按HS编码/贸易伙伴/省份/企业性质的进出口金额数据
# 注册：https://stats.customs.gov.cn/account/Register
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

# Pin dependency versions (standard library only; mcp is the only external dep)
RUN pip install --no-cache-dir --user \
    "mcp>=1.1.0" \
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
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Labels
LABEL org.opencontainers.image.title="Chinese Customs MCP Server" \
      org.opencontainers.image.description="中国海关进出口数据。按HS编码/贸易伙伴/省份/企业性质获取进出口金额与数量。" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-chinese-customs" \
      finresearch.mcp.api="China Customs Statistics API" \
      finresearch.mcp.apikey="required:CHINESE_CUSTOMS_API_KEY" \
      finresearch.mcp.use_case="关税政策评估/DID分析/出口依存度研究"

EXPOSE 8000

USER mcpuser

CMD ["python", "server.py"]
