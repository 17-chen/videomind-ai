"""Read-only, bounded ledger/remote observations. Never resolves upload intent."""

from sqlalchemy import exists, func, select

from app.models import Video
from app.services.object_storage.cleanup import ledger_installed
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.repository import SPEC_FIELDS
from app.services.object_storage.spec import ArtifactSpec, BLOCK_SIZE


def _clean(db):
    if db.new or db.dirty or db.deleted:
        raise ValueError('Object audit requires a clean dedicated database session')


def ledger_snapshot(db):
    _clean(db)
    report = {'status': 'not_installed', 'writes_performed': False, 'observations_only': True,
              'counts': {}, 'bytes': {}, 'pending_source_bytes': 0, 'ready_without_owned_video': 0}
    if not ledger_installed(db):
        return report
    for state, count, size in db.execute(select(StoredArtifact.state, func.count(), func.sum(StoredArtifact.size_bytes))
                                        .group_by(StoredArtifact.state)):
        report['counts'][state] = count
        report['bytes'][state] = size
    for state in ('pending', 'ready', 'retired', 'deleted'):
        report['counts'].setdefault(state, 0)
        report['bytes'].setdefault(state, 0)
    report['pending_source_bytes'] = db.scalar(select(func.coalesce(func.sum(StoredArtifact.size_bytes), 0)).where(
        StoredArtifact.state == 'pending', StoredArtifact.is_source_upload.is_(True)))
    owned_video = exists(select(Video.id).where(Video.id == StoredArtifact.video_id, Video.user_id == StoredArtifact.user_id))
    report['ready_without_owned_video'] = db.scalar(select(func.count()).select_from(StoredArtifact).where(
        StoredArtifact.state == 'ready', ~owned_video))
    report['status'] = 'needs_attention' if report['counts']['pending'] or report['ready_without_owned_video'] else 'preview'
    return report


def audit_objects(db, *, store=None, limit=20, max_bytes=512 * 1024 * 1024, offset=0):
    """Trusted maintenance only. No row locks or transaction during remote I/O.

    Budget reserves expected bytes plus one overflow block for each attempted GET,
    including failures. It bounds object-body iteration, not TLS/HTTP overhead.
    An unchanged ledger after a read does not prove an idle remote upload.
    """
    if not 1 <= limit <= 100 or not 1 <= max_bytes <= 10 * 1024**3 or not 0 <= offset <= 1000000:
        raise ValueError('Invalid object audit limits')
    _clean(db)
    db.rollback()
    try:
        # PostgreSQL enforces read-only even if a future query accidentally writes.
        if db.bind.dialect.name == 'postgresql':
            db.connection().exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        report = ledger_snapshot(db)
        report['remote'] = {'enabled': store is not None, 'selected': 0, 'attempted': 0, 'matched': 0, 'absent': 0,
                            'mismatch': 0, 'failed': 0, 'deleted_absent': 0, 'deleted_present': 0, 'changed_during_check': 0, 'skipped_budget': 0,
                            'budget_reserved_bytes': 0, 'offset': offset, 'truncated': False}
        if store is None or report['status'] == 'not_installed':
            return report
        rows = db.scalars(select(StoredArtifact).order_by(StoredArtifact.id).offset(offset).limit(limit + 1)).all()
        # Copy immutable values, then release the SQL transaction before any GET.
        fields = (*SPEC_FIELDS, 'state', 'delete_requested', 'is_source_upload', 'updated_at')
        snapshots = [{name: getattr(row, name) for name in fields} for row in rows[:limit]]
        remote = report['remote']
        remote['truncated'] = len(rows) > limit
        remote['selected'] = len(snapshots)
        db.rollback()
        for before in snapshots:
            reserved = before['size_bytes'] + BLOCK_SIZE
            if reserved > max_bytes - remote['budget_reserved_bytes']:
                remote['skipped_budget'] += 1
                continue
            remote['budget_reserved_bytes'] += reserved
            remote['attempted'] += 1
            try:
                spec = ArtifactSpec(**{name: before[name] for name in SPEC_FIELDS})
                outcome = store.verify(spec)
                if outcome not in ('matched', 'absent', 'mismatch'):
                    raise ValueError('Unknown verification outcome')
            except Exception:
                outcome = 'failed'  # Provider exceptions and metadata never reach output.
            if before['state'] == 'deleted':
                if outcome == 'absent':
                    outcome = 'deleted_absent'
                elif outcome in ('matched', 'mismatch'):
                    outcome = 'deleted_present'
            # Fresh values detect concurrent publication, deletion or metadata edits.
            if db.bind.dialect.name == 'postgresql':
                db.connection().exec_driver_sql('SET TRANSACTION READ ONLY')
            current = db.execute(select(*(getattr(StoredArtifact, name) for name in fields))
                                 .where(StoredArtifact.id == before['id'])).mappings().first()
            changed = current is None or any(current[name] != value for name, value in before.items())
            db.rollback()
            remote['changed_during_check' if changed else outcome] += 1
        if any(remote[name] for name in ('absent', 'mismatch', 'failed', 'deleted_present', 'changed_during_check', 'skipped_budget')) or remote['truncated']:
            report['status'] = 'needs_attention'
        elif report['status'] == 'preview':
            report['status'] = 'observed'
        return report
    finally:
        db.rollback()  # Never commit ledger or business state, including errors.
