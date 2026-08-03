"""
WebSocket Route Endpoint for Live Job Updates.

GET /ws/jobs — Real-time WebSocket connection endpoint
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.events import manager

logger = logging.getLogger("forge.ws")

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/jobs")
async def websocket_jobs_endpoint(websocket: WebSocket):
    """
    WebSocket connection endpoint for real-time job status streaming.

    Clients connect to `ws://host:port/api/ws/jobs` (or `/ws/jobs`).
    The server pushes lightweight JSON events on every job status transition:
    { "job_id": "...", "old_status": "queued", "new_status": "running", "timestamp": "..." }
    """
    await manager.connect(websocket)
    try:
        while True:
            # Maintain connection & listen for incoming client messages or ping/pongs
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client disconnected with exception: {e}")
        manager.disconnect(websocket)
