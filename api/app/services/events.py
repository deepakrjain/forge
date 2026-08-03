"""
Real-time Job Event Service using Redis Pub/Sub & WebSockets.

Event Payload Format:
{
    "job_id": "c1f7b0e1-...",
    "old_status": "queued",
    "new_status": "running",
    "timestamp": "2026-08-03T17:10:10.123456+00:00"
}
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket
import redis.asyncio as aioredis

logger = logging.getLogger("forge.events")

EVENTS_CHANNEL = "forge:events:jobs"


async def publish_job_event(
    redis_client: aioredis.Redis,
    job_id: str,
    old_status: Optional[str],
    new_status: str,
) -> None:
    """
    Publish a lightweight job status transition event to Redis Pub/Sub.
    """
    event = {
        "job_id": str(job_id),
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await redis_client.publish(EVENTS_CHANNEL, json.dumps(event))
        logger.debug(f"Published event to {EVENTS_CHANNEL}: {job_id} ({old_status} -> {new_status})")
    except Exception as e:
        logger.error(f"Failed to publish job event for {job_id}: {e}")


class ConnectionManager:
    """
    Manages active client WebSocket connections and broadcasts live events.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return

        disconnected: Set[WebSocket] = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error sending message to WebSocket client: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


async def start_pubsub_listener(redis_url: str):
    """
    Background subscriber task running on each API instance.
    Subscribes to Redis Pub/Sub 'forge:events:jobs' and re-broadcasts
    events to locally connected WebSockets via ConnectionManager.
    """
    logger.info(f"Starting Redis Pub/Sub listener on channel '{EVENTS_CHANNEL}'...")
    redis_sub = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = redis_sub.pubsub()

    try:
        await pubsub.subscribe(EVENTS_CHANNEL)
        logger.info(f"Subscribed to Pub/Sub channel '{EVENTS_CHANNEL}'. Listener ready.")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(data)
                except Exception as e:
                    logger.error(f"Error parsing Pub/Sub message: {e}")
    except asyncio.CancelledError:
        logger.info("Pub/Sub listener task cancelled.")
    except Exception as e:
        logger.error(f"Pub/Sub listener encountered error: {e}")
    finally:
        await pubsub.unsubscribe(EVENTS_CHANNEL)
        await redis_sub.aclose()
        logger.info("Pub/Sub listener connection closed.")
