import os
import socket
from dotenv import load_dotenv

load_dotenv()

WORKER_ID = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}-{os.getpid()}")
POSTGRES_URI = os.getenv(
    "POSTGRES_URI",
    "postgresql+asyncpg://forge_user:forge_password@localhost:5432/forge_db",
)
REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")
CONCURRENCY = int(os.getenv("CONCURRENCY", "5"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
