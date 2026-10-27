"""Read-only check that a saved Fernet master key decrypts every stored user key."""

import argparse
import json
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.ai_settings import AiSettings


class KeyVerificationError(Exception):
    """Expected failure without user IDs, ciphertext, or plaintext in its message."""


def verify_stored_keys(db: Session, key: str) -> dict[str, int | str]:
    try:
        cipher = Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise KeyVerificationError("invalid_key_format") from exc

    rows = 0
    values = 0
    try:
        for api_key, asr_key in db.execute(select(
            AiSettings.encrypted_api_key, AiSettings.encrypted_asr_api_key,
        )).yield_per(100):
            rows += 1
            for encrypted in (api_key, asr_key):
                if encrypted is None:
                    continue
                try:
                    cipher.decrypt(encrypted.encode())
                except (InvalidToken, ValueError, TypeError) as exc:
                    raise KeyVerificationError("decryption_failed") from exc
                values += 1
    except SQLAlchemyError as exc:
        raise KeyVerificationError("database_read_failed") from exc

    return {
        "status": "verified" if values else "inconclusive",
        "settings_rows": rows,
        "encrypted_values_checked": values,
    }


def _read_private_key_file(path: Path) -> str:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
        raise KeyVerificationError("key_file_not_private")
    return path.read_text(encoding="utf-8").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, help="Private 0600 file holding the backed-up key; defaults to configured key")
    args = parser.parse_args(argv)
    try:
        key = _read_private_key_file(args.key_file) if args.key_file else settings.user_api_key_encryption_key
        with SessionLocal() as db:
            result = verify_stored_keys(db, key)
    except (KeyVerificationError, OSError, UnicodeError) as exc:
        reason = str(exc) if isinstance(exc, KeyVerificationError) else "key_file_unavailable"
        print(json.dumps({"status": "failed", "reason": reason}))
        return 1
    print(json.dumps(result))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
