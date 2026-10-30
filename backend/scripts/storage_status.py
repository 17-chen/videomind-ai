"""Print aggregate local file inventory without deleting or revealing user files."""

import json

from app.database.session import SessionLocal
from app.services.storage_monitoring import storage_snapshot


def main() -> int:
    try:
        with SessionLocal() as db:
            report = storage_snapshot(db)
    except Exception as exc:
        # Do not print exception messages: they may contain database credentials or paths.
        print(json.dumps({'status': 'error', 'error_type': type(exc).__name__, 'cleanup_performed': False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
