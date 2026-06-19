# ─────────────────────────────────────────────────────────────────────────────
# Third-Party ESG MCP Server — 第三方ESG评级数据
# 数据源：商道融绿(SynTao)/华证(CSI)/中证ESG/富时ESG（需各自API Key）
# 覆盖：ESG综合评分、评级（AAA-C）、争议事件、排名、碳排放
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

# Pin dependency versions (httpx for async HTTP calls to ESG providers)
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
LABEL org.opencontainers.image.title="Third-Party ESG MCP Server" \
      org.opencontainers.image.description="第三方ESG评级。整合SynTao/CSI/中证ESG/富时ESG，覆盖评分、评级、争议事件。" \
      org.opencontainers.image.source="https://github.com/csmar432/finai-research-workflow" \
      org.opencontainers.image.version="1.0.0" \
      finresearch.mcp.server="user-third-party-esg" \
      finresearch.mcp.api="SynTao/CSI/CSI-ESG/FTSE ESG APIs" \
      finresearch.mcp.apikey="required:SYNTAO_API_KEY,CSI_ESG_API_KEY,THIRD_PARTY_ESG_KEY" \
      finresearch.mcp.use_case="ESG研究/绿色金融/企业社会责任评估"

EXPOSE 8000

USER mcpuser

CMD ["python", "server.py"]
