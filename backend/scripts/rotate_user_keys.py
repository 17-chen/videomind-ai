"""Offline credential rotation. Defaults to a read-only full-dataset preflight.

Never generates, installs, prints or edits a master key or application config.
"""

import argparse
import json
import os
from pathlib import Path
import stat

from app.database.session import SessionLocal
from app.services.key_rotation import KeyRotationError, rotate_stored_keys


def _read_key(path):
    # Open once, reject symlinks/FIFOs, then bound reads and check permissions on
    # that same descriptor. Private parent directories remain operator-owned.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 128:
            raise KeyRotationError('key_file_not_private_or_bounded')
        data = os.read(descriptor, 129)
        if len(data) > 128:
            raise KeyRotationError('key_file_not_private_or_bounded')
        return data.decode('ascii').strip()
    finally:
        os.close(descriptor)


def _row_budget(value):
    value = int(value)
    if not 1 <= value <= 100000:
        raise argparse.ArgumentTypeError('Row budget must be 1-100000')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-key-file', type=Path, required=True)
    parser.add_argument('--next-key-file', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Commit one PostgreSQL rotation transaction')
    parser.add_argument('--writers-stopped', action='store_true', help='Operator confirms all API/Worker writers and readers are stopped')
    parser.add_argument('--max-rows', type=_row_budget, default=10000, help='Full-dataset budget; never rotates a partial batch')
    args = parser.parse_args(argv)
    if args.apply and not args.writers_stopped:
        parser.error('--apply requires --writers-stopped')
    try:
        current, next_key = _read_key(args.current_key_file), _read_key(args.next_key_file)
        with SessionLocal() as db:
            report = rotate_stored_keys(db, current, next_key, apply=args.apply,
                                        writers_stopped=args.writers_stopped, max_rows=args.max_rows)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, KeyRotationError) else 'rotation_unavailable'
        report = {'status': 'failed', 'reason': reason, 'writes_may_have_occurred': args.apply,
                  'configuration_changed': False}
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] in ('verified', 'rotated') else 2


if __name__ == '__main__':
    raise SystemExit(main())
