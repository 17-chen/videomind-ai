"""Offline, all-or-nothing rotation of stored user credentials, never config."""

import base64

from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.ai_settings import AiSettings


class KeyRotationError(Exception):
    """Fixed reason only; never includes credential material or identities."""


def rotate_stored_keys(db: Session, current_key: str, next_key: str, *, apply=False,
                       writers_stopped=False, max_rows=10000):
    """Use a dedicated session. Apply requires PostgreSQL and stopped writers.

    A table lock blocks concurrent credential inserts, edits, deletes and other
    rotations. It cannot stop old-key API readers or external model calls: the
    operator must stop ALL API/Worker processes before explicitly applying.
    """
    if db.new or db.dirty or db.deleted:
        raise KeyRotationError('dedicated_session_required')
    if not 1 <= max_rows <= 100000:
        raise KeyRotationError('invalid_row_budget')
    try:
        old, new = Fernet(current_key.encode()), Fernet(next_key.encode())
        if base64.urlsafe_b64decode(current_key) == base64.urlsafe_b64decode(next_key):
            raise KeyRotationError('distinct_keys_required')
    except KeyRotationError:
        raise
    except (ValueError, TypeError, AttributeError):
        raise KeyRotationError('invalid_key_format') from None
    if apply and not writers_stopped:
        raise KeyRotationError('stopped_writers_required')
    postgres = db.bind.dialect.name == 'postgresql'
    if apply and not postgres:
        raise KeyRotationError('postgresql_required')
    db.rollback()
    try:
        if postgres:
            if not apply:
                db.connection().exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("SET LOCAL statement_timeout = '30s'"))
            # Match the locked/checked public table even under a role-specific
            # search_path. Reset automatically with this transaction.
            db.execute(text('SET LOCAL search_path = pg_catalog, public'))
            if apply:
                db.execute(text('LOCK TABLE public.ai_settings IN SHARE ROW EXCLUSIVE MODE'))
            if db.scalar(text("SELECT row_security_active('public.ai_settings'::regclass)")):
                raise KeyRotationError('unfiltered_backend_view_required')
        rows = db.scalars(select(AiSettings).order_by(AiSettings.id).limit(max_rows + 1)).all()
        if len(rows) > max_rows:
            raise KeyRotationError('row_budget_exceeded')
        expected = []
        checked = 0
        for row in rows:
            values = []
            for encrypted in (row.encrypted_api_key, row.encrypted_asr_api_key):
                if encrypted is None:
                    values.append(None)
                    continue
                try:
                    plaintext = old.decrypt(encrypted.encode())
                    rotated = new.encrypt(plaintext)
                    if new.decrypt(rotated) != plaintext:
                        raise KeyRotationError('new_key_verification_failed')
                except KeyRotationError:
                    raise
                except Exception:
                    raise KeyRotationError('credential_verification_failed') from None
                values.append(rotated.decode())
                checked += 1
            expected.append((row.id, *values))
        report = {'status': 'inconclusive' if not checked else ('rotated' if apply else 'verified'),
                  'settings_rows': len(rows), 'encrypted_values_checked': checked,
                  'writes_performed': False, 'configuration_changed': False}
        if apply and checked:
            for row, (_, api_key, asr_key) in zip(rows, expected, strict=True):
                row.encrypted_api_key, row.encrypted_asr_api_key = api_key, asr_key
            db.flush()
            # Read database values, not ORM identities; reject trigger mutations,
            # missing/extra rows, or a write that did not persist the exact tokens.
            actual = db.execute(select(AiSettings.id, AiSettings.encrypted_api_key, AiSettings.encrypted_asr_api_key)
                                .order_by(AiSettings.id).limit(max_rows + 1)).all()
            if [tuple(row) for row in actual] != expected:
                raise KeyRotationError('stored_ciphertext_verification_failed')
            for _, api_key, asr_key in actual:
                for value in (api_key, asr_key):
                    if value is not None:
                        new.decrypt(value.encode())
            db.commit()
            report['writes_performed'] = True
        return report
    except KeyRotationError:
        raise
    except Exception:
        # SQL errors can contain bind values; never log or propagate their text.
        raise KeyRotationError('rotation_failed') from None
    finally:
        db.rollback()
