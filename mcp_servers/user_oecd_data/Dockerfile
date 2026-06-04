FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy server code
COPY server.py .
COPY SERVER_METADATA.json .
COPY tools/ ./tools/
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir \
    pandas>=2.0.0 \
    numpy>=1.26.0 \
    scikit-learn>=1.4.0 \
    scipy>=1.13.0 \
    statsmodels>=0.14.0 \
    torch>=2.2.0 \
    transformers>=4.40.0 \
    accelerate>=0.30.0 \
    networkx>=3.2.0 \
    faiss-cpu>=1.7.4 \
    sentence-transformers>=2.3.0 \
    chromadb>=0.4.22 \
    jieba>=0.42.0 \
    matplotlib>=3.8.0 \
    seaborn>=0.13.0 \
    plotly>=5.21.0 \
    pdfplumber>=0.11.0 \
    python-docx>=1.1.0 \
    python-pptx>=0.6.23 \
    Pillow>=10.3.0 \
    markdown>=3.4.0 \
    requests>=2.31.0 \
    beautifulsoup4>=4.12.0 \
    lxml>=4.9.0 \
    akshare>=1.18.63 \
    openai>=2.0.0 \
    anthropic>=7.0.0 \
    httpx>=0.27.0 \
    tiktoken>=0.7.0 \
    yfinance>=0.2.0 \
    linearmodels>=4.17 \
    pandas-datareader>=0.10.0 \
    pandasql>=0.7.3 \
    python-dotenv>=1.0.0 \
    pyyaml>=6.0.0 \
    pydantic>=2.0.0 \
    fastapi>=0.115.0 \
    uvicorn[standard]>=0.30.0 \
    streamlit>=1.32.0 \
    pypandoc>=0.8.0 \
    openpyxl>=3.1.0 \
    dotenv \
    mcp

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["python", "server.py"]
