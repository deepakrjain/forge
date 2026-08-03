import time
import logging
from forge_shared import JobStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ForgeWorker")

def main():
    logger.info("Forge Worker node starting...")
    logger.info(f"Initialized job status handler for statuses: {[s.value for s in JobStatus]}")
    logger.info("Worker node online. Ready to consume jobs.")

if __name__ == "__main__":
    main()
