"""Compare an already restored isolated PostgreSQL database without writing it."""

import argparse
import json
import os


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Read budgets must be positive integers')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-rows', type=positive, default=100000)
    parser.add_argument('--max-bytes', type=positive, default=67108864)
    args = parser.parse_args(argv)
    engines = []
    try:
        from sqlalchemy import create_engine
        from app.core.config import settings
        from app.services.database_restore_verification import compare_database_restore
        target = os.environ.get('RESTORE_VERIFICATION_DATABASE_URL')
        if not target:
            report = {'status': 'unavailable', 'reason': 'restore_target_missing', 'writes_performed': False}
        else:
            engines = [create_engine(settings.database_url)]
            engines.append(create_engine(target))
            report = compare_database_restore(*engines, max_rows=args.max_rows, max_bytes=args.max_bytes)
    except Exception:
        report = {'status': 'unavailable', 'reason': 'database_verification_failed', 'writes_performed': False}
    finally:
        for engine in engines:
            engine.dispose()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return {'matched': 0, 'mismatch': 1, 'inconclusive': 2, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
