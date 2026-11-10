"""Read-only operational thresholds: exit 0 healthy, 1 attention, 2 unavailable."""

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.database.session import SessionLocal
from app.services.operations_monitoring import OperationsThresholds, operations_snapshot
from app.services.storage_quota import ARTIFACT_KINDS


def nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError('Thresholds must be nonnegative integers')
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-queued-seconds', type=nonnegative, default=300)
    parser.add_argument('--max-expired-leases', type=nonnegative, default=0)
    parser.add_argument('--max-failures-last-hour', type=nonnegative, default=0)
    parser.add_argument('--min-free-mb', type=nonnegative, default=settings.min_media_free_space_mb)
    args = parser.parse_args(argv)
    report = operations_snapshot(
        SessionLocal,
        roots=[Path(getattr(settings, f'{kind}_storage_dir')) for kind in ARTIFACT_KINDS],
        thresholds=OperationsThresholds(**vars(args)),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return {'ok': 0, 'attention': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
