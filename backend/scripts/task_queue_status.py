"""Print an aggregate task queue snapshot without user or video details."""

import json

from app.database.session import SessionLocal
from app.services.task_monitoring import task_queue_snapshot


def main() -> int:
    try:
        with SessionLocal() as db:
            report = task_queue_snapshot(db)
    except Exception:
        print(json.dumps({'status': 'unavailable', 'reason': 'queue_read_failed', 'mutations_performed': False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
