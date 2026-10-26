"""Print an aggregate task queue snapshot without user or video details."""

import json

from app.database.session import SessionLocal
from app.services.task_monitoring import task_queue_snapshot


def main() -> None:
    with SessionLocal() as db:
        print(json.dumps(task_queue_snapshot(db), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
