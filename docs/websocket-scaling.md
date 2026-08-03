# Forge — Multi-Instance WebSocket Scaling Architecture

This document answers the classic system design follow-up question:
**"If Forge scales horizontally across multiple API instances, will a WebSocket client connected to Instance A still receive updates about a job processed by Worker / Instance B?"**

---

## 1. The Multi-Instance Challenge & Architecture

In a horizontally scaled deployment, a Load Balancer (e.g. AWS ALB, NGINX) distributes incoming HTTP and WebSocket connections across multiple API server instances.

```text
                               +-----------------------+
                               |     Load Balancer     |
                               +-----------+-----------+
                                           |
                    +----------------------+----------------------+
                    |                                             |
                    v                                             v
        +-----------------------+                     +-----------------------+
        |     API Instance A    |                     |     API Instance B    |
        |  (Client 1 WebSocket) |                     |  (Client 2 WebSocket) |
        +-----------+-----------+                     +-----------+-----------+
                    |                                             |
                    | Subscribes to                               | Subscribes to
                    | 'forge:events:jobs'                         | 'forge:events:jobs'
                    v                                             v
        +---------------------------------------------------------------------+
        |                          Redis Pub/Sub                              |
        |                      Channel: 'forge:events:jobs'                   |
        +--------------------------------──+────────────────────────────────--+
                                           ^
                                           | Publishes Status Transitions
                                           |
                                 +---------+---------+
                                 |   Worker Node(s)  |
                                 +-------------------+
```

### How the Architecture Works

1. **Central Message Broker (Redis Pub/Sub)**:
   - When a job transitions state (`queued` → `running` → `succeeded`), the Worker node or API Instance B calls `redis_client.publish('forge:events:jobs', json_payload)`.

2. **Distributed Listener Tasks**:
   - Every running API server instance (Instance A, Instance B, Instance C...) launches a background task at startup that subscribes to `forge:events:jobs`.

3. **Fan-Out & Local Re-broadcasting**:
   - When Redis receives the published message, it **fans out** (broadcasts) the payload to **all** active Pub/Sub subscribers (every API server instance).
   - API Instance A receives the message from Redis and immediately invokes its local `ConnectionManager.broadcast(payload)`, forwarding the event to Client 1 over its open WebSocket connection.

---

## 2. Interview Q&A Summary

### Q: Does a client on Instance A get updates from Instance B?
**Yes.** Because the state change event is published to Redis Pub/Sub, Redis fans out the message to all subscribed API server instances. Instance A receives the event from Redis and re-broadcasts it to its locally connected WebSockets.

### Q: What is the difference between Redis Pub/Sub and Redis Streams here?

| Feature | Redis Pub/Sub (Used for Live UI) | Redis Streams (Persistent Log) |
|---|---|---|
| **Delivery Model** | **Fire-and-forget** (At-most-once) | **Persistent log** (At-least-once / Replayable) |
| **Storage Overhead** | Zero bytes stored in Redis | Messages stored until pruned (`XTRIM`) |
| **Replayability** | Missing subscribers miss the message | New/reconnected subscribers can read historical log (`XREAD`) |
| **Use Case in Forge** | Ideal for live dashboard state overlays where missing an intermediate state transition is harmless (the UI re-fetches state on reconnect). | Ideal for audit logging, Webhooks, or event-driven consumer pipelines requiring strict replay guarantees. |

---

## 3. What If a Client Reconnects?

Because Pub/Sub is fire-and-forget, if an API instance restarts or a client temporarily loses connectivity, any events sent during the downtime are not delivered.

**Resilience Strategy in Forge**:
- When the React Dashboard re-establishes its WebSocket connection, it immediately performs a REST `GET /api/jobs` query to catch up on the latest ground truth from PostgreSQL/Cache, then resumes listening to the live WebSocket stream.
