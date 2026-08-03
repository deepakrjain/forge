# Forge — Job Lifecycle State Machine

This document describes the complete lifecycle of a job in Forge.
Use this as a reference when explaining the system's reliability model
in interviews.

---

## State Diagram (ASCII)

```text
                          ┌───────────────────┐
                          │                   │
      POST /jobs          │     QUEUED        │
    ─────────────────────►│  (initial state)  │
                          │                   │
                          └────────┬──────────┘
                                   │
                          Worker picks up job
                          (BRPOPLPUSH from Redis)
                                   │
                                   ▼
                          ┌───────────────────┐
                          │                   │
                          │     RUNNING       │
                          │  (attempts += 1)  │
                          │                   │
                          └───┬───────────┬───┘
                              │           │
                    Handler   │           │  Handler raises
                    returns   │           │  exception
                    success   │           │
                              ▼           ▼
                 ┌────────────────┐   ┌──────────────────┐
                 │                │   │                   │
                 │   SUCCEEDED   │   │     FAILED        │
                 │  (terminal)   │   │ (transient state) │
                 │               │   │                   │
                 └────────────────┘   └─────────┬────────┘
                                                │
                                     ┌──────────┴──────────┐
                                     │                     │
                            attempts < max_attempts   attempts >= max_attempts
                                     │                     │
                                     ▼                     ▼
                          ┌───────────────────┐   ┌───────────────────┐
                          │                   │   │                   │
                          │    RETRYING       │   │      DEAD         │
                          │ (re-queued with   │   │  (terminal — all  │
                          │  backoff delay)   │   │   retries spent)  │
                          │                   │   │                   │
                          └────────┬──────────┘   └───────────────────┘
                                   │
                                   │ After backoff delay expires,
                                   │ status resets to QUEUED
                                   │
                                   ▼
                          ┌───────────────────┐
                          │                   │
                          │     QUEUED        │  ← re-enters the queue
                          │                   │
                          └───────────────────┘
```

---

## States Explained

### QUEUED (initial)
The job has been accepted by the API and persisted to PostgreSQL.
It is waiting in the Redis queue to be picked up by a worker.

**Entry conditions:**
- A new job is submitted via `POST /jobs`.
- A retrying job's backoff delay has elapsed.

### RUNNING
A worker has claimed the job (popped it from the Redis queue) and is
actively executing the handler function.

**Key detail:** The `attempts` counter is incremented atomically when
entering this state. This ensures that even if the worker crashes
mid-execution, we have an accurate count of how many times the job
was attempted.

### SUCCEEDED (terminal)
The handler function returned successfully. The `result` JSONB column
stores any output data.

This is a **terminal state** — no further transitions occur.

### FAILED (transient)
The handler raised an exception during the current attempt. The `error`
column stores the exception message and traceback.

This is a **decision point**, not a resting state. The system immediately
evaluates whether to retry or mark the job as dead.

### RETRYING
The job failed but has remaining attempts (`attempts < max_attempts`).
It will be re-inserted into the Redis queue after a **backoff delay**.

**Backoff strategy (planned):** Exponential backoff with jitter:
```
delay = min(base_delay * 2^(attempt - 1) + random_jitter, max_delay)
```
This prevents retry storms where many failed jobs all retry simultaneously
and overwhelm the downstream service that caused them to fail.

The `run_after` timestamp is updated to `now() + delay`, and the status
transitions back to `QUEUED` once that timestamp is reached.

### DEAD (terminal)
The job has exhausted all retry attempts (`attempts >= max_attempts`).
It remains in the database for auditing and debugging but will never
be executed again.

This is the **dead-letter** concept: rather than silently discarding
failed work, we preserve it for operators to inspect, manually retry,
or escalate.

---

## Transition Summary Table

| From       | To         | Trigger                                      |
|------------|------------|----------------------------------------------|
| *(new)*    | QUEUED     | `POST /jobs` accepted                        |
| QUEUED     | RUNNING    | Worker claims job from Redis queue            |
| RUNNING    | SUCCEEDED  | Handler returns successfully                  |
| RUNNING    | FAILED     | Handler raises exception                      |
| FAILED     | RETRYING   | `attempts < max_attempts`                     |
| FAILED     | DEAD       | `attempts >= max_attempts`                    |
| RETRYING   | QUEUED     | Backoff delay elapsed, job re-queued          |

---

## Interview Talking Points

1. **Why separate FAILED and RETRYING?**
   FAILED is a momentary decision point. Keeping it as a distinct state
   means dashboards and metrics can distinguish "currently evaluating retry
   logic" from "permanently failed." It also maps cleanly to observability:
   you can alert on FAILED rate even if most jobs eventually succeed on retry.

2. **Why DEAD instead of just staying FAILED?**
   A terminal DEAD state acts as a dead-letter queue. It signals to operators
   "this requires human attention" rather than cluttering the FAILED bucket
   with jobs that are still being retried. It also prevents the worker from
   accidentally re-processing a job that should no longer be attempted.

3. **Why increment attempts on RUNNING, not on FAILED?**
   If the worker crashes (OOM, segfault, network partition) between picking
   up a job and recording the outcome, we still want the attempt counted.
   Incrementing on claim (entering RUNNING) is the conservative choice:
   the worst case is we count an attempt that might not have fully executed,
   rather than missing an attempt that did execute and crash.

4. **Why exponential backoff with jitter?**
   Without jitter, if 1,000 jobs all fail at the same second, they all
   retry at the same second — a "thundering herd." Adding randomised jitter
   spreads retry load over a time window, protecting downstream services.
