FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir mcp yfinance pandas requests
COPY server.py /app/
CMD ["python", "server.py"]
