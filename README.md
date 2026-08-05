# Forge: Distributed Background Job Queue & Worker Platform

Forge is a high-performance, distributed background job queue and worker platform built to demonstrate deep backend engineering concepts: reliable job execution, retry strategies, queue scheduling, persistence, and real-time observability.

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
- `/api`: FastAPI service handling REST endpoints, job submission, and WebSocket broadcasts.
- `/worker`: Distributed consumer processes polling/popping jobs from Redis and updating status in PostgreSQL.
- `/shared`: Shared schemas, data models, and type definitions used by both API and Worker components.
- `/dashboard`: React + TypeScript frontend built with Vite & Recharts for visualization.

---

## Setup & Quickstart

### Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [Python 3.10+](https://www.python.org/)
- [Node.js 18+](https://nodejs.org/)

### 1. Start Infrastructure (Postgres, Redis, Prometheus, Grafana)
```bash
docker compose up -d
```

### Services Summary

| Service | Endpoint / Port | Credentials / Notes |
|---------|-----------------|---------------------|
| **API Server** | `http://localhost:8000` | Header: `X-API-Key: forge_dev_key_123` |
| **Dashboard** | `http://localhost:5173` | React / Vite UI |
| **Prometheus** | `http://localhost:9090` | Metrics scraper |
| **Grafana** | `http://localhost:3001` | Login: `admin` / `admin` |
| **PostgreSQL** | `localhost:5432` | DB: `forge_db`, User: `forge_user` |
| **Redis** | `localhost:6379` | In-memory queues & Pub/Sub |

### 2. Install Shared Package
```bash
cd shared
pip install -e .
cd ..
```

### 3. Run API
```bash
cd api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run Worker
```bash
cd worker
pip install -r requirements.txt
python -m app.main
```

### 5. Run Dashboard
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

- **Postgres-First Durability**: Jobs are committed to PostgreSQL *before* pushing to Redis. If Redis fails, state remains recoverable in Postgres without data loss.
- **Redis Sorted Sets for Priority & Scheduling**: Priority is calculated as `score = -priority * 1e12 + timestamp_ms`, enabling $O(\log N)$ atomic pops of the highest priority job via `ZPOPMIN`.
- **Atomic Lua Scripts**: Sliding-window rate limiting and delayed job promotion are executed atomically in Redis via Lua scripts to eliminate race conditions.
- **Pub/Sub WebSocket Streaming**: Worker state changes publish events to Redis Pub/Sub, which the API broadcasts over WebSockets to provide real-time UI updates without polling.
