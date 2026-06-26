# Lightweight image for in-compose Playwright perf verification.
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Minimal deps for runner (playwright + stdlib urllib for health checks)
RUN pip3 install --no-cache-dir playwright==1.49.1 \
    && playwright install --with-deps chromium

COPY scripts/perf_matrix.py /app/scripts/perf_matrix.py

# Default entry overridden by compose
CMD ["python3", "scripts/perf_matrix.py", "--help"]
