# ─────────────────────────────────────────────────────────────────────────────
# SIPO MCP Server — 国家知识产权局专利数据
# 数据源：https://cpquery.cponline.cnipa.gov.cn（需注册）
# 覆盖：专利基本信息/法律状态/引文/质押/许可/转让/诉讼数据
# 注册：https://cponline.cnipa.gov.cn
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

# Pin dependency versions (mcp is the only external dep; uses standard library urllib)
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
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD kill -0 1

# Labels
LABEL org.opencontainers.image.title="SIPO Patent MCP Server" \
      org.opencontainers.image.description="国家知识产权局专利数据。基本信息/法律状态/引文/质押/许可/转让/诉讼。" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-sipo" \
      finresearch.mcp.api="CNIPA Patent Query API" \
      finresearch.mcp.apikey="required:SIPO_API_KEY" \
      finresearch.mcp.use_case="专利分析/企业创新/DID政策评估"

EXPOSE 8000

USER mcpuser

CMD ["python", "server.py"]
