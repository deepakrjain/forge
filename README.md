# Forge — Distributed Background Job Queue & Worker Platform

Forge is a high-performance, distributed background job queue and worker platform built to demonstrate deep backend engineering concepts: reliable job execution, retry strategies, queue scheduling, persistence, and real-time observability.

---

## Overview

Forge provides a robust architecture for executing asynchronous tasks in distributed environments:
- **Asynchronous Execution**: Decouples API request lifecycles from heavy background tasks.
- **Reliability & Persistence**: PostgreSQL for immutable job history and Redis for fast, memory-backed queue management.
- **Real-Time Monitoring**: Live status tracking and metrics via WebSocket connections to a modern React dashboard.

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

## Setup

### Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [Python 3.10+](https://www.python.org/)
- [Node.js 18+](https://nodejs.org/)

### Quickstart

1. **Start Infrastructure Services (Postgres & Redis)**
   ```bash
   docker-compose up -d
   ```

2. **Verify Services**
   - PostgreSQL running on `localhost:5432`
   - Redis running on `localhost:6379`

3. **Install Shared Package**
   ```bash
   cd shared
   pip install -e .
   cd ..
   ```

4. **Run API**
   ```bash
   cd api
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

5. **Run Worker**
   ```bash
   cd worker
   pip install -r requirements.txt
   python -m app.main
   ```

6. **Run Dashboard**
   ```bash
   cd dashboard
   npm install
   npm run dev
   ```

---

## Testing

Forge includes a comprehensive test suite covering unit tests, integration tests, and load tests.

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

## Design Decisions

*(Reserved for personal technical decision notes and design rationale)*

<!-- Add your notes here as you build out each phase -->
