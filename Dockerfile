FROM python:3.12-slim

WORKDIR /app

# psycopg2 build deps, curl for health checks, supervisor to run api + voice worker + kb worker
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Production by default: requires SECRET_KEY and disables the local admin seed.
ENV APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_DATA_DIR=/app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# Runs the API (app.main), the LiveKit voice worker, and the KB ingest worker.
CMD ["supervisord", "-c", "/app/supervisord.conf"]
