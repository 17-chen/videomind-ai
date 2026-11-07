"""One backend choice for authenticated HTTP writes, tasks and readiness.

Never changes environment, creates a bucket/schema or migrates existing files.
"""

from contextlib import contextmanager

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.spec import UNAVAILABLE
from app.services.object_storage.supabase import SupabaseObjectStore


def _close(store):
    try:
        store.close()
    except Exception as exc:
        logger.warning('File storage close error type={}', type(exc).__name__)


@contextmanager
def managed_file_store(db):
    backend = settings.file_storage_backend.lower()
    if backend == 'local':
        yield None
        return
    if backend != 'supabase':
        raise ApiError(UNAVAILABLE, 503)
    store = None
    try:
        # Read only: verify required columns and SQL access, never auto-migrate.
        db.execute(select(StoredArtifact.id, StoredArtifact.delete_requested, StoredArtifact.is_source_upload).limit(0))
        store = SupabaseObjectStore.from_settings()
        store.check_connection()  # Fail before publication or starting paid processing.
    except Exception as exc:
        if store is not None:
            _close(store)
        logger.warning('File storage readiness error type={}', type(exc).__name__)
        raise ApiError(UNAVAILABLE, 503) from None
    try:
        yield store
    finally:
        _close(store)
