"""Explicit, opt-in pgvector schema migration. Back up the target database first."""

import argparse
import json
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic_pgvector"))
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the optional schema after target backup; default makes no changes",
    )
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps({"status": "not_applied", "writes_performed": False}))
        return 2
    try:
        command.upgrade(migration_config(), "head")
    except Exception:
        print(json.dumps({"status": "failed", "reason": "pgvector_migration_failed"}))
        return 1
    print(json.dumps({"status": "applied", "revision": "20261103_v001"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
