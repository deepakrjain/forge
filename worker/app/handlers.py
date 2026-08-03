import asyncio
import random
import logging
from typing import Any, Dict, Callable, Awaitable

logger = logging.getLogger("forge.worker.handlers")


async def handle_send_email(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate sending an email notification."""
    recipient = payload.get("to", "user@example.com")
    subject = payload.get("subject", "Notification from Forge")
    
    duration = random.uniform(0.5, 2.0)
    await asyncio.sleep(duration)

    # Simulate ~30% random failure
    if random.random() < 0.3:
        raise RuntimeError(f"SMTP connection timeout while sending email to {recipient}")

    return {
        "status": "delivered",
        "recipient": recipient,
        "subject": subject,
        "duration_seconds": round(duration, 2),
    }


async def handle_resize_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate processing and resizing an image asset."""
    image_url = payload.get("image_url", "https://example.com/input.png")
    width = payload.get("width", 800)
    height = payload.get("height", 600)

    duration = random.uniform(1.0, 3.0)
    await asyncio.sleep(duration)

    if random.random() < 0.3:
        raise ValueError(f"Corrupted image format at {image_url}")

    return {
        "status": "processed",
        "original_url": image_url,
        "dimensions": f"{width}x{height}",
        "duration_seconds": round(duration, 2),
    }


async def handle_generate_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate generating an asynchronous analytics report."""
    report_type = payload.get("report_type", "monthly_summary")
    user_id = payload.get("user_id", "user_123")

    duration = random.uniform(1.5, 3.5)
    await asyncio.sleep(duration)

    if random.random() < 0.3:
        raise TimeoutError(f"Database query timeout while aggregating report '{report_type}' for user {user_id}")

    return {
        "status": "generated",
        "report_type": report_type,
        "user_id": user_id,
        "download_url": f"https://forge.internal/reports/{report_type}_{user_id}.pdf",
        "duration_seconds": round(duration, 2),
    }


async def handle_default(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback handler for unspecified job types."""
    duration = random.uniform(0.2, 1.0)
    await asyncio.sleep(duration)
    return {
        "status": "executed",
        "payload_echo": payload,
        "duration_seconds": round(duration, 2),
    }


HANDLERS: Dict[str, Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {
    "send_email": handle_send_email,
    "resize_image": handle_resize_image,
    "generate_report": handle_generate_report,
}


def get_handler(job_type: str) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """Retrieve job handler by job_type, falling back to handle_default."""
    return HANDLERS.get(job_type, handle_default)
