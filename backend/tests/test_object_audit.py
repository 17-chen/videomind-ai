"""Read-only reconciliation observations, synthetic provider and isolated SQL."""

from dataclasses import replace
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.models import User, Video
from app.services.object_storage.audit import audit_objects
from app.services.object_storage.models import ArtifactBase, StoredArtifact
from app.services.object_storage.repository import SPEC_FIELDS
from app.services.object_storage.spec import BLOCK_SIZE
from app.services.object_storage.supabase import SupabaseObjectStore
from scripts import audit_objects as cli
from test_object_storage import BUCKET, KEY, PROJECT, client, response, spec_for


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "audit.db"}')
    Base.metadata.create_all(engine)
    ArtifactBase.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email='audit-synthetic@example.com', password_hash='synthetic')
        video = Video(user=user, url='https://example.invalid/synthetic', tags=[])
        db.add(video)
        db.commit()
        yield db, engine, user.id, video.id
    engine.dispose()


def add_row(db, owner, video, *, state='pending', data=b'synthetic', is_source_upload=False, **values):
    spec = spec_for(data, user_id=owner, video_id=video, filename=f'{video}.md', **values)
    row = StoredArtifact(**{name: getattr(spec, name) for name in SPEC_FIELDS}, state=state, is_source_upload=is_source_upload)
    db.add(row)
    db.commit()
    return spec


@pytest.mark.parametrize('status,data,headers,expected', [
    (200, b'original', {}, 'matched'), (404, b'provider-private-sentinel', {}, 'absent'),
    (200, b'changed!', {}, 'mismatch'), (200, b'short', {}, 'mismatch'),
    (200, b'original-more', {}, 'mismatch'),
    (200, b'original', {'Content-Length': '99'}, 'mismatch'),
    (200, b'original', {'Content-Encoding': 'gzip'}, 'mismatch'),
])
def test_verify_exact_key_streaming_without_cache_or_mutations(tmp_path, status, data, headers, expected, monkeypatch):
    seen = []
    spec = spec_for()
    monkeypatch.setattr(settings, 'max_media_stage_mb', 0)
    def handle(request):
        seen.append(request)
        assert request.method == 'GET' and request.url.path.endswith(spec.object_key)
        assert request.headers['Accept-Encoding'] == 'identity'
        return response(status, data, headers=headers)
    store = client(handle)
    try:
        assert store.verify(spec) == expected
        assert len(seen) == 1 and not list(tmp_path.iterdir())
    finally:
        store.close()


@pytest.mark.parametrize('status', [403, 429, 500, 307])
def test_verify_errors_do_not_treat_permission_or_redirect_as_absence(status):
    store = client(lambda request: response(status, b'private-provider-sentinel', headers={'Location': 'https://untrusted.invalid'}))
    try:
        with pytest.raises(ApiError) as error:
            store.verify(spec_for())
        assert 'sentinel' not in error.value.message
    finally:
        store.close()


def test_verify_wrong_project_and_public_bucket_never_reads_object():
    seen = []
    def handle(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={'id': BUCKET, 'public': True})
    store = SupabaseObjectStore(PROJECT, KEY, BUCKET, transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ApiError):
            store.verify(replace(spec_for(), project_fingerprint='0' * 64))
        assert seen == []
        with pytest.raises(ApiError):
            store.verify(spec_for())
        assert seen == [f'/storage/v1/bucket/{BUCKET}']
    finally:
        store.close()


def test_default_aggregates_preserve_intents_and_hide_identifiers(ledger):
    db, _, owner, video = ledger
    source = add_row(db, owner, video, data=b'pending', is_source_upload=True)
    add_row(db, owner, str(uuid4()), state='ready')
    report = audit_objects(db)
    assert report['status'] == 'needs_attention'
    assert report['counts']['pending'] == 1 and report['counts']['ready'] == 1
    assert report['pending_source_bytes'] == 7 and report['ready_without_owned_video'] == 1
    assert report['remote']['enabled'] is False and report['writes_performed'] is False
    output = json.dumps(report)
    assert all(value not in output for value in (source.id, owner, video, source.filename, source.bucket, source.sha256))
    assert db.get(StoredArtifact, source.id).state == 'pending'


def test_remote_match_and_404_never_release_or_publish_pending(ledger):
    db, _, owner, video = ledger
    first = add_row(db, owner, video, is_source_upload=True)
    second = add_row(db, owner, video, data=b'other', is_source_upload=True)
    store = client(lambda request: response(200, b'synthetic') if request.url.path.endswith(first.object_key) else response(404))
    try:
        report = audit_objects(db, store=store)
        assert report['remote']['matched'] == 1 and report['remote']['absent'] == 1
        assert report['status'] == 'needs_attention'
        for spec in (first, second):
            row = db.get(StoredArtifact, spec.id)
            assert row.state == 'pending' and row.is_source_upload and not row.delete_requested
        assert db.query(Video).count() == 1
    finally:
        store.close()


def test_deleted_absence_expected_but_reappearance_requires_attention(ledger):
    db, _, owner, video = ledger
    add_row(db, owner, video, state='deleted')
    for status, expected, state in [(404, 'deleted_absent', 'observed'), (200, 'deleted_present', 'needs_attention')]:
        store = client(lambda request: response(status, b'synthetic'))
        try:
            report = audit_objects(db, store=store)
            assert report['remote'][expected] == 1 and report['status'] == state
            assert db.scalar(select(StoredArtifact.state)) == 'deleted'
        finally:
            store.close()


def test_limits_stop_before_oversize_get_and_report_partial_coverage(ledger):
    db, _, owner, video = ledger
    for _ in range(3):
        add_row(db, owner, video, state='retired')
    class MustNotRead:
        def verify(self, spec):
            pytest.fail('Over-budget object must not be read')
    report = audit_objects(db, store=MustNotRead(), limit=2, max_bytes=BLOCK_SIZE)
    assert report['remote']['selected'] == 2 and report['remote']['truncated'] is True
    assert report['remote']['skipped_budget'] == 2 and report['remote']['attempted'] == 0
    assert report['status'] == 'needs_attention'


def test_changed_ledger_during_get_is_not_reported_as_stable_match(ledger):
    db, engine, owner, video = ledger
    spec = add_row(db, owner, video, state='ready')
    class ConcurrentStore:
        def verify(self, unused):
            assert not db.in_transaction()
            with Session(engine) as writer:
                row = writer.get(StoredArtifact, spec.id)
                row.state = 'retired'
                row.delete_requested = True
                writer.commit()
            return 'matched'
    report = audit_objects(db, store=ConcurrentStore())
    assert report['remote']['changed_during_check'] == 1 and report['remote']['matched'] == 0
    assert db.get(StoredArtifact, spec.id).delete_requested is True


def test_remote_failure_is_redacted_and_does_not_modify_ledger(ledger):
    db, engine, owner, video = ledger
    add_row(db, owner, video)
    writes = []
    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE'):
            writes.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    class FailedStore:
        def verify(self, spec):
            raise RuntimeError('private-key-user-address-sentinel')
    try:
        report = audit_objects(db, store=FailedStore())
        assert report['remote']['failed'] == 1 and not writes
        assert 'sentinel' not in json.dumps(report)
    finally:
        event.remove(engine, 'before_cursor_execute', record)


def test_dirty_session_rejected_without_discarding_user_changes(ledger):
    db, _, owner, video = ledger
    row = db.get(Video, video)
    row.title = 'uncommitted synthetic title'
    with pytest.raises(ValueError):
        audit_objects(db)
    assert row.title == 'uncommitted synthetic title' and db.dirty


def test_cli_uninstalled_and_default_never_create_cloud_client(tmp_path, monkeypatch, capsys):
    engine = create_engine(f'sqlite:///{tmp_path / "local.db"}')
    Base.metadata.create_all(engine)
    monkeypatch.setattr(cli, 'SessionLocal', lambda: Session(engine))
    def forbidden():
        pytest.fail('No cloud client in a local-only environment')
    monkeypatch.setattr(SupabaseObjectStore, 'from_settings', forbidden)
    try:
        assert cli.main([]) == 0
        assert cli.main(['--verify-remote']) == 0
        assert all(json.loads(line)['status'] == 'not_installed' for line in capsys.readouterr().out.splitlines())
    finally:
        engine.dispose()


def test_cli_failure_redacts_and_closes_client(ledger, monkeypatch, capsys):
    _, engine, _, _ = ledger
    closed = []
    class BrokenStore:
        def verify(self, spec):
            raise RuntimeError('private-sentinel')
        def close(self):
            closed.append(True)
    with Session(engine) as db:
        add_row(db, ledger[2], ledger[3])
    monkeypatch.setattr(cli, 'SessionLocal', lambda: Session(engine))
    monkeypatch.setattr(SupabaseObjectStore, 'from_settings', BrokenStore)
    assert cli.main(['--verify-remote']) == 2
    assert closed == [True] and 'sentinel' not in capsys.readouterr().out


def test_offset_batch_reports_position_without_exposing_object_ids(ledger):
    db, _, owner, video = ledger
    specs = sorted([add_row(db, owner, video, state='retired') for _ in range(3)], key=lambda spec: spec.id)
    seen = []
    class Observer:
        def verify(self, spec):
            seen.append(spec.id)
            return 'matched'
    report = audit_objects(db, store=Observer(), offset=1, limit=1)
    assert seen == [specs[1].id]
    assert report['remote']['offset'] == 1 and report['remote']['truncated']
    assert specs[1].id not in json.dumps(report)


def test_unbounded_stream_stops_at_one_overflow_block():
    consumed = []
    class Endless(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(100):
                consumed.append(index)
                yield b'x' * BLOCK_SIZE
        def close(self):
            consumed.append('closed')
    store = client(lambda request: httpx.Response(200, stream=Endless()))
    try:
        assert store.verify(spec_for(b'x')) == 'mismatch'
        assert consumed == [0, 'closed']
    finally:
        store.close()


def test_real_loopback_verifies_stream_without_media_cache(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    data = b'synthetic-local-http' * 10000
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            requests.append(self.path)
            if '/bucket/' in self.path:
                body = json.dumps({'id': BUCKET, 'public': False}).encode()
            else:
                body = data
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    project = f'http://127.0.0.1:{server.server_port}'
    store = SupabaseObjectStore(project, KEY, BUCKET, allow_insecure_loopback=True)
    try:
        spec = spec_for(data, project_fingerprint=store.project_fingerprint)
        assert store.verify(spec) == 'matched'
        assert len(requests) == 2 and requests[1].endswith(spec.object_key)
        assert not list(tmp_path.iterdir())
    finally:
        store.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_failed_get_still_consumes_budget_before_next_object(ledger):
    db, _, owner, video = ledger
    for _ in range(2):
        add_row(db, owner, video)
    calls = []
    class LostResponse:
        def verify(self, spec):
            calls.append(spec.id)
            raise httpx.ReadError('synthetic unknown bytes received')
    report = audit_objects(db, store=LostResponse(), max_bytes=BLOCK_SIZE + len(b'synthetic'))
    assert len(calls) == 1
    assert report['remote']['failed'] == 1 and report['remote']['skipped_budget'] == 1
    assert report['remote']['budget_reserved_bytes'] == BLOCK_SIZE + len(b'synthetic')


def test_invalid_ledger_metadata_is_redacted_before_remote_io(ledger):
    db, _, owner, video = ledger
    spec = add_row(db, owner, video)
    row = db.get(StoredArtifact, spec.id)
    row.filename = '../private-sentinel'
    db.commit()
    class MustNotRead:
        def verify(self, unused):
            pytest.fail('Unsafe metadata must never form a remote address')
    report = audit_objects(db, store=MustNotRead())
    assert report['remote']['failed'] == 1 and 'sentinel' not in json.dumps(report)
    assert db.get(StoredArtifact, spec.id).filename == '../private-sentinel'
