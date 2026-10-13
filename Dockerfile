# Safe paper-only TradingView webhook runner
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements_updated.txt .
RUN pip install --no-cache-dir -r requirements_updated.txt

COPY . .
RUN mkdir -p logs data backtest_results state

ENV PYTHONPATH=/app
ENV TZ=Australia/Sydney
ENV LOKI_CONFIG=/app/config.loki.paper.yaml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail http://127.0.0.1:8000/health || exit 1

# This image intentionally runs only the authenticated local-paper/Alpaca-paper
# webhook service. It does not start any live exchange adapter.
CMD ["python", "-m", "loki"]
