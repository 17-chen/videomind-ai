"""Preview explicit video-deletion intents; --apply retries a bounded safe subset.

Not an orphan collector: uncertain pending uploads and unmarked objects remain.
Only aggregate counts are printed. No bucket/project/key/user/file is printed.
"""

import argparse
import json

from app.database.session import SessionLocal
from app.services.object_storage.cleanup import cleanup_requested_objects, cleanup_snapshot
from app.services.object_storage.supabase import SupabaseObjectStore


def _limit(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError('Limit must be between 1 and 100')
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Execute explicit confirmed-upload deletion intents')
    parser.add_argument('--limit', type=_limit, default=20, help='Maximum attempts, 1-100 (default 20)')
    args = parser.parse_args(argv)
    attempted = False
    try:
        with SessionLocal() as db:
            report = cleanup_snapshot(db)
            report.update(attempted=0, confirmed_deleted=0, failed=0)
            if args.apply and report['eligible']:
                store = SupabaseObjectStore.from_settings()
                try:
                    # A failure after a remote request may have changed remote state.
                    attempted = True
                    report = cleanup_requested_objects(db, store=store, limit=args.limit)
                finally:
                    store.close()
        report['writes_performed'] = report['attempted'] > 0
    except Exception:
        print(json.dumps({'status': 'error', 'reason': 'object_cleanup_failed', 'writes_may_have_occurred': attempted}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 2 if report['status'] == 'needs_attention' or report['pending_uncertain'] or report['blocked'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
