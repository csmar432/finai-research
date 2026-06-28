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
# P0 修复 2026-06-28: 补齐 LaTeX 工具链（之前 Dockerfile 缺 texlive）
# user_latex_mcp 是 LaTeX 论文写作工具链，server.py 用 subprocess 调用本地 latex/pdflatex/chktex
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-lang-chinese \
    texlive-bibtex-extra \
    biber \
    chktex \
    latexmk \
    && rm -rf /var/lib/apt/lists/*

# Copy server code
COPY server.py .
COPY SERVER_METADATA.json .
COPY tools/ ./tools/
# Copy healthcheck (P0 修复 2026-06-28)
COPY mcp_healthcheck.py /app/mcp_healthcheck.py

# Install Python dependencies (version-pinned)
RUN pip install --no-cache-dir --break-system-packages \
    mcp>=1.1.0

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \
    CMD python mcp_healthcheck.py --server-dir /app --timeout 10

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
