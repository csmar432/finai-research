FROM python:3.12-slim
WORKDIR /app
ENV NEWSAPI_API_KEY=${NEWSAPI_API_KEY:-}
RUN pip install --no-cache-dir mcp requests
COPY server.py /app/
CMD ["python", "server.py"]
