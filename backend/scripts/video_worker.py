"""Run durable video tasks from PostgreSQL in a separate process."""

import threading
import time

from app.core.logging import configure_logging, logger
from app.database.session import SessionLocal
from app.services.video_tasks import (
    claim_next_task,
    execute_claimed_task,
    extend_task_lease,
    new_worker_id,
    recover_expired_tasks,
)


def _heartbeat(task_id: str, worker_id: str, stop: threading.Event) -> None:
    while not stop.wait(15):
        try:
            with SessionLocal() as db:
                if not extend_task_lease(db, task_id, worker_id):
                    return
        except Exception as exc:
            logger.warning("Task lease heartbeat failed for {}: {}", task_id, type(exc).__name__)


def main() -> None:
    configure_logging()
    worker_id = new_worker_id()
    logger.info("Video worker started: {}", worker_id)
    while True:
        try:
            with SessionLocal() as db:
                recovered = recover_expired_tasks(db)
                if recovered:
                    logger.warning("Recovered {} expired video tasks", recovered)
                task = claim_next_task(db, worker_id)
            if task is None:
                time.sleep(2)
                continue
            stop = threading.Event()
            heartbeat = threading.Thread(target=_heartbeat, args=(task.id, worker_id, stop), daemon=True)
            heartbeat.start()
            try:
                with SessionLocal() as db:
                    execute_claimed_task(db, task.id, worker_id)
            finally:
                stop.set()
                heartbeat.join(timeout=2)
        except Exception as exc:
            logger.error("Video worker loop error: {}", type(exc).__name__)
            time.sleep(2)


if __name__ == "__main__":
    main()
