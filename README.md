# Forge: Distributed Background Job Queue & Worker Platform

[![Forge CI](https://github.com/deepakrjain/forge/actions/workflows/ci.yml/badge.svg)](https://github.com/deepakrjain/forge/actions)

Forge is a high-performance, distributed background job queue and worker platform built to demonstrate deep backend engineering concepts: reliable job execution, retry strategies, queue scheduling, persistence, and real-time observability.

---

## 🌐 Live Demo & Deployment

## Live Demo & API Docs

- **API Documentation**: Available locally at `http://localhost:8000/docs` when running via Docker Compose.
- **Cloud Deployment**: This project includes a `render.yaml` Blueprint for 1-click deployment to [Render](https://render.com).

---

## Key Features

- **Idempotent Job Submission**: Prevents duplicate execution via client-supplied idempotency keys (`POST /jobs`).
- **Priority Queuing & Delayed Execution**: Score-based priority execution with support for delayed execution (`run_after`).
- **Resilient Execution & Exponential Backoff**: Automatic retries with exponential backoff and randomized jitter on handler failures.
- **Dead Letter Queue (DLQ)**: Isolates terminally failed jobs after exhausting max attempts; supports live re-queueing and discarding.
- **Sliding-Window Rate Limiting**: Per-API-key sliding-window rate limiting backed by atomic Redis Lua scripts.
- **Real-Time Observability**: Event-driven WebSocket stream for live UI updates, Prometheus metrics endpoint (`GET /metrics`), and pre-configured Grafana dashboards.

---

## Architecture

```text
               +-------------------+
               |  React Dashboard  |
               +--------+----------+
                        |
            HTTP / WS   |
                        v
               +-------------------+
               |   FastAPI Server  |
               |     (/api)        |
               +----+---------+----+
                    |         |
    Read/Write Jobs |         | Push Jobs
                    v         v
             +----------+   +----------+
             | PostgreSQL|   |   Redis  |
             | (History)|   | (Queue)  |
             +----------+   +----+-----+
                                 |
                                 | Pop Jobs
                                 v
                        +-------------------+
                        |   Worker Nodes    |
                        |    (/worker)      |
                        +-------------------+
```

### Component Breakdown
- `/api`: FastAPI service handling REST endpoints, job submission, rate limiting, and WebSocket broadcasts.
- `/worker`: Distributed consumer processes polling/popping jobs from Redis and updating status in PostgreSQL.
- `/shared`: Shared schemas, data models, and type definitions used by both API and Worker components.
- `/dashboard`: React + TypeScript frontend built with Vite & Recharts for visualization.

---

## Setup & Quickstart

### Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [Python 3.10+](https://www.python.org/) (optional, for local development/tests)
- [Node.js 18+](https://nodejs.org/) (optional, for local development/tests)

---

### Option A: One-Command Full Stack (Recommended)

Bring up the complete containerized stack (Postgres, Redis, API, Dashboard, Prometheus, Grafana, and 3 scaled Workers) in a single command:

```bash
docker compose up -d --build --scale worker=3
```

### Services Summary

| Service | Endpoint / Port | Credentials / Notes |
|---------|-----------------|---------------------|
| **Dashboard** | `http://localhost:5173` | React / Vite UI (Nginx proxied) |
| **API Server** | `http://localhost:8000` | Header: `X-API-Key: forge_dev_key_123` |
| **Prometheus** | `http://localhost:9090` | Metrics scraper |
| **Grafana** | `http://localhost:3001` | Login: `admin` / `admin` |
| **PostgreSQL** | `localhost:5432` | DB: `forge_db`, User: `forge_user` |
| **Redis** | `localhost:6379` | In-memory queues & Pub/Sub |

---

### Option B: Local Development Setup

1. **Start Infrastructure Services**
   ```bash
   docker compose up -d postgres redis
   ```

2. **Install Shared Package**
   ```bash
   cd shared && pip install -e . && cd ..
   ```

3. **Run API**
   ```bash
   cd api
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

4. **Run Worker**
   ```bash
   cd worker
   pip install -r requirements.txt
   python -m app.main
   ```

5. **Run Dashboard**
   ```bash
   cd dashboard
   npm install
   npm run dev
   ```

---

## Testing

Forge includes a test suite covering unit tests, integration tests, and load tests.

### Unit Tests

```bash
# Worker unit tests (backoff delay calculation)
cd worker
python -m pytest tests/unit -v

# API unit tests (rate limiter, idempotency key logic)
cd api
python -m pytest tests/unit -v
```

### Integration Tests

```bash
# Requires Postgres and Redis running (docker compose up -d)
python -m pytest tests/integration -v
```

### Load Test

```bash
# Requires API server running on port 8000
cd tests/load
node load_test.js
```

See [`docs/load_test_results.md`](docs/load_test_results.md) for benchmark results.

---

## Core Design Decisions

- **Durable-First Write Strategy (Postgres Write-Ahead)**: Jobs are committed to PostgreSQL *before* pushing to Redis. If Redis fails or restarts, state remains fully preserved in Postgres without data loss, and a recovery sweeper can safely re-enqueue missing jobs.
- **Redis Sorted Sets for Priority Queues**: Priority and submission timestamps are encoded into a composite score: `score = -priority * 1e12 + timestamp_ms`. This allows $O(\log N)$ atomic pops of the highest priority job using `ZPOPMIN`, maintaining strict priority order.
- **Sliding-Window Rate Limiting via Lua Scripts**: Rather than fixed-window counters (vulnerable to double-capacity bursts across minute boundaries), Forge uses a sliding-window log backed by Redis Sorted Sets. The evaluation and pruning of logs happens inside a single atomic Lua script to prevent race conditions.
- **Event-Driven Pub/Sub WebSockets**: Instead of having the frontend poll `/api/jobs` continuously, worker state transitions emit events to Redis Pub/Sub (`forge:events:jobs`). The API consumes these channels and broadcasts them over WebSockets directly to connected clients for real-time reactivity with zero API polling overhead.
- **Dead Letter Queue (DLQ) & Exponential Backoff with Jitter**: Failing tasks retry using $2^{\text{attempt}-1} \times \text{base}$ exponential delay supplemented with uniform randomized jitter ($0 \le \text{jitter} \le 0.5 \times \text{delay}$) to prevent thundering herd problems on downstream services. Tasks exhausting `max_attempts` land in the DLQ for manual inspection, retry, or discard.
