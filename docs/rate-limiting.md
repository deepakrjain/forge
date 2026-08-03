# Forge — Rate Limiting & Horizontal Scalability Architecture

This document describes the design and implementation of per-API-key rate limiting in Forge.

---

## 1. Sliding Window Log vs. Fixed Window Counter

### Fixed Window Counter (`INCR` + `EXPIRE`)
- **Mechanism**: Increments a Redis counter key for a fixed time bucket (e.g. `forge:ratelimit:key:12:00`).
- **Drawback — Boundary Burst Vulnerability**:
  Suppose an API key has a rate limit of 60 requests per minute.
  - A client sends 60 requests at `11:59:59` (Window 1).
  - The client sends another 60 requests at `12:00:00` (Window 2).
  Both windows accept the requests because they fall into separate 1-minute key buckets. However, the client successfully executed **120 requests within a 2-second window** (2x the capacity burst limit).

### Sliding Window Log (Implemented in Forge)
- **Mechanism**: Requests are recorded as Unix timestamps inside a Redis Sorted Set (`forge:ratelimit:{api_key}`).
- **Execution Workflow**:
  1. On each request, old timestamps older than `now() - 60s` are removed via `ZREMRANGEBYSCORE`.
  2. The remaining element count in the set is checked via `ZCARD`.
  3. If `count >= limit`, the request is denied with **HTTP 429 Too Many Requests**. The `Retry-After` header is calculated from the oldest remaining timestamp in the window (`(oldest_ts + 60s) - now()`).
  4. If `count < limit`, the request timestamp is inserted via `ZADD` and PEXPIRE is refreshed.
- **Advantage**: Evaluates an exact rolling 60-second window relative to the current millisecond. Traffic bursts across window boundaries are smoothly and strictly enforced.

---

## 2. Horizontal Scalability & Stateless API Servers

### Why No Code Changes Are Required for Horizontal Scaling

If Forge API is scaled horizontally from 1 instance to 50 API server instances behind a Load Balancer (e.g., NGINX, AWS ALB, Envoy):

```text
               +-----------------------+
               |     Load Balancer     |
               +-----------+-----------+
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
+-------------------+             +-------------------+
|   API Instance 1  |             |   API Instance 2  |
|  (Stateless Node) |             |  (Stateless Node) |
+---------+---------+             +---------+---------+
          |                                 |
          +----------------+----------------+
                           |
                           v
              +-------------------------+
              |       Redis Cluster     |
              | (Central Atomic State)  |
              +-------------------------+
```

1. **Centralized Atomic State**:
   - The rate limit counters and timestamps live in **Redis**, not in local API process memory.
   - The sliding-window logic is executed atomically inside Redis via a single Lua script (`EVAL`).

2. **No Inter-Server Communication**:
   - API Server 1 and API Server 2 do not need to communicate, sync state, or share memory.
   - Regardless of which API server receives a request, both execute the Lua script against the same Redis key (`forge:ratelimit:{api_key}`).

3. **Race-Condition Safety**:
   - Redis executes Lua scripts atomically in a single-threaded execution context.
   - Simultaneous requests routed to different API servers serialize inside Redis, preventing race conditions or double-counting errors.

---

## 3. Interview Talking Points

1. **Why HTTP 429 & Retry-After?**
   Standard HTTP semantics (RFC 6585). Returning `Retry-After: <seconds>` instructs client SDKs exactly how long to back off before attempting another request.

2. **Why Fail-Open on Redis Outage?**
   If Redis becomes unreachable, the rate limiter catches the exception, logs an alert, and **fails open** (allows the request through). In production systems, an infrastructure failure in observability/rate limiting should not trigger a complete blackout for valid API callers.
