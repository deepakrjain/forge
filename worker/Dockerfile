# Multi-stage build for Forge Worker

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
COPY worker/requirements.txt /app/worker/requirements.txt

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir /app/shared && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/worker/requirements.txt

# Stage 2: Runner
FROM python:3.12-slim AS runner

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY shared/ /app/shared/
COPY worker/ /app/worker/

WORKDIR /app/worker

CMD ["python", "-m", "app.main"]
