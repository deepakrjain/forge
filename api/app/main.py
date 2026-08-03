from fastapi import FastAPI
from forge_shared import JobStatus

app = FastAPI(
    title="Forge API",
    description="Distributed Background Job Queue & Worker Platform REST & WebSocket API",
    version="0.1.0"
)

@app.get("/")
def read_root():
    return {
        "service": "Forge API",
        "status": "online",
        "version": "0.1.0"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "supported_statuses": [status.value for status in JobStatus]
    }
