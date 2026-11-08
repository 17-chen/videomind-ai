"""Aggregate read-only ledger audit; remote GETs require --verify-remote.

Never uploads, deletes, releases quota, changes state, or prints object addresses.
"""

import argparse
import json

from app.database.session import SessionLocal
from app.services.object_storage.audit import audit_objects
from app.services.object_storage.supabase import SupabaseObjectStore


def _bounded(value, minimum, maximum):
    number = int(value)
    if not minimum <= number <= maximum:
        raise argparse.ArgumentTypeError('Value outside supported range')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-remote', action='store_true', help='Read exact keys and verify size/SHA-256; may incur provider egress charges')
    parser.add_argument('--limit', type=lambda value: _bounded(value, 1, 100), default=20)
    parser.add_argument('--offset', type=lambda value: _bounded(value, 0, 1000000), default=0,
                        help='Skip rows in UUID order; only use across batches while writers are stopped')
    parser.add_argument('--max-mb', type=lambda value: _bounded(value, 1, 10240), default=512,
                        help='Object-body budget including overflow allowance; default 512 MiB')
    args = parser.parse_args(argv)
    store = None
    try:
        with SessionLocal() as db:
            # Default and uninstalled schema never instantiate a cloud client.
            report = audit_objects(db)
            if args.verify_remote and report['status'] != 'not_installed':
                store = SupabaseObjectStore.from_settings()
                report = audit_objects(db, store=store, limit=args.limit, max_bytes=args.max_mb * 1024 * 1024, offset=args.offset)
    except Exception:
        report = {'status': 'error', 'reason': 'object_audit_failed', 'writes_performed': False, 'observations_only': True}
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                report = {'status': 'error', 'reason': 'object_audit_failed', 'writes_performed': False, 'observations_only': True}
    print(json.dumps(report, sort_keys=True))
    return 2 if report['status'] in ('needs_attention', 'error') else 0


if __name__ == '__main__':
    raise SystemExit(main())
