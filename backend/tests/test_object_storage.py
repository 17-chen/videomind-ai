"""Synthetic Supabase wire responses, real file I/O, and isolated ledger checks."""

import base64
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.models import User, Video
from app.services.object_storage.models import ArtifactBase, StoredArtifact
from app.services.object_storage.repository import materialize_artifact, publish_artifact, purge_retired_artifact, retire_artifact
from app.services.object_storage.spec import ArtifactSpec, INTEGRITY_ERROR, UNAVAILABLE, measure_file
from app.services.object_storage.supabase import SupabaseObjectStore
from scripts.prepare_objects import main as prepare_main

KEY = 'sb_secret_synthetic_storage_test_only'
BUCKET = 'videomind-private'
PROJECT = 'https://storage.example.invalid'


def spec_for(data=b'original', **kwargs):
    video = str(uuid4())
    values = dict(id=str(uuid4()), user_id=str(uuid4()), video_id=video, kind='note', filename=f'{video}.md',
                  bucket=BUCKET, project_fingerprint=hashlib.sha256(PROJECT.encode()).hexdigest(),
                  sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    return ArtifactSpec(**(values | kwargs))


def response(status=200, data=b'', **kwargs):
    # Keep downloads streaming, rather than httpx's already-consumed content shortcut.
    return httpx.Response(status, stream=httpx.ByteStream(data), **kwargs)


def client(handler):
    def route(request):
        assert request.headers['apikey'] == KEY
        assert 'authorization' not in request.headers
        if request.url.path == f'/storage/v1/bucket/{BUCKET}':
            return response(data=json.dumps({'id': BUCKET, 'public': False}).encode())
        return handler(request)
    return SupabaseObjectStore(PROJECT, KEY, BUCKET, transport=httpx.MockTransport(route))


@pytest.mark.parametrize('overrides', [dict(filename='../secret'), dict(kind='unknown'), dict(size_bytes=-1), dict(user_id='other'), dict(bucket='a/b'), dict(sha256='bad')])
def test_unsafe_object_metadata_rejected(overrides):
    with pytest.raises(ValueError):
        spec_for(**overrides)


@pytest.mark.parametrize('url,key', [('http://provider.example', KEY), (PROJECT + '/path', KEY), ('https://private:credential@example.com', KEY), (PROJECT, 'sb_publishable_synthetic'), (PROJECT, 'not-a-server-key')])
def test_configuration_rejected_without_echoing_credentials(url, key):
    with pytest.raises(ApiError) as error:
        SupabaseObjectStore(url, key, BUCKET)
    assert error.value.message == UNAVAILABLE


def test_legacy_service_role_key_uses_bearer_header():
    payload = base64.urlsafe_b64encode(json.dumps({'role': 'service_role'}).encode()).decode().rstrip('=')
    key = f'synthetic.{payload}.synthetic'
    def handler(request):
        assert request.headers['apikey'] == key
        assert request.headers['authorization'] == f'Bearer {key}'
        return response(data=json.dumps({'id': BUCKET, 'public': False}).encode())
    store = SupabaseObjectStore(PROJECT, key, BUCKET, transport=httpx.MockTransport(handler))
    try:
        store._private_bucket()
    finally:
        store.close()


@pytest.mark.parametrize('status,body', [(200, {'id': BUCKET, 'public': True}), (200, {'id': 'wrong', 'public': False}), (200, []), (403, {'error': 'private-provider-sentinel'})])
def test_public_or_unverifiable_bucket_fails_before_object_io(tmp_path, status, body):
    seen = []
    def handler(request):
        seen.append(request.url.path)
        return response(status, json.dumps(body).encode())
    store = SupabaseObjectStore(PROJECT, KEY, BUCKET, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ApiError) as error:
            store.download(spec_for(), tmp_path / 'output')
        assert error.value.message == UNAVAILABLE
        assert seen == [f'/storage/v1/bucket/{BUCKET}']
    finally:
        store.close()


def test_redirect_never_forwards_credentials_or_reads_provider_body(tmp_path):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return response(307, b'private-provider-sentinel', headers={'Location': 'https://untrusted.example'})
    store = client(handler)
    try:
        with pytest.raises(ApiError) as error:
            store.download(spec_for(), tmp_path / 'output')
        assert error.value.message == UNAVAILABLE
        assert len(seen) == 1 and 'untrusted' not in seen[0]
    finally:
        store.close()


def test_upload_is_immutable_and_checks_source_digest(tmp_path):
    spec = spec_for()
    source = tmp_path / spec.filename
    source.write_bytes(b'original')
    seen = []
    def handler(request):
        seen.append(request.read())
        assert request.method == 'POST'
        assert request.url.path.endswith(spec.object_key)
        assert request.headers['x-upsert'] == 'false'
        return response(201)
    store = client(handler)
    try:
        store.put(spec, source)
        source.write_bytes(b'modified')
        with pytest.raises(ApiError) as error:
            store.put(spec, source)
        assert error.value.message == INTEGRITY_ERROR
        assert seen == [b'original', b'modified']
    finally:
        store.close()


@pytest.mark.parametrize('data,headers', [(b'corrupt!', {}), (b'short', {}), (b'too long content', {}), (b'original', {'Content-Length': '100'}), (b'original', {'Content-Encoding': 'gzip'})])
def test_corrupt_download_keeps_previous_and_removes_partial(tmp_path, data, headers):
    target = tmp_path / 'previous'
    target.write_bytes(b'previous-good-version')
    store = client(lambda request: response(data=data, headers=headers))
    try:
        with pytest.raises(ApiError):
            store.download(spec_for(), target)
        assert target.read_bytes() == b'previous-good-version'
        assert list(tmp_path.iterdir()) == [target]
    finally:
        store.close()


def test_transport_failure_is_sanitized_and_keeps_previous(tmp_path):
    def handler(request):
        raise httpx.ReadError('private-provider-sentinel')
    store = client(handler)
    try:
        with pytest.raises(ApiError) as error:
            store.download(spec_for(), tmp_path / 'output')
        assert error.value.message == UNAVAILABLE
        assert not list(tmp_path.iterdir())
    finally:
        store.close()


def test_symbolic_sources_and_destinations_rejected(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'original')
    link = tmp_path / 'link'
    link.symlink_to(source)
    with pytest.raises(ApiError):
        measure_file(link)
    store = client(lambda request: pytest.fail('No object I/O for symbolic destination'))
    try:
        with pytest.raises(ApiError):
            store.download(spec_for(), link)
        assert source.read_bytes() == b'original'
    finally:
        store.close()


def test_scope_mismatch_rejected_before_remote_io(tmp_path):
    store = client(lambda request: pytest.fail('No remote I/O'))
    try:
        with pytest.raises(ApiError):
            store.download(replace(spec_for(), project_fingerprint='0' * 64), tmp_path / 'output')
    finally:
        store.close()


@pytest.mark.parametrize('confirmed', [True, False])
def test_delete_verifies_exact_key_disappeared(confirmed):
    spec = spec_for()
    def handler(request):
        if request.method == 'DELETE':
            assert json.loads(request.read()) == {'prefixes': [spec.object_key]}
            return response(200)
        assert request.url.path.endswith(spec.object_key)
        return response(404 if confirmed else 200)
    store = client(handler)
    try:
        if confirmed:
            store.delete(spec)
        else:
            with pytest.raises(ApiError):
                store.delete(spec)
    finally:
        store.close()


def test_real_loopback_http_roundtrip_with_synthetic_supabase(tmp_path):
    objects = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, content=b''):
            self.send_response(status)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            assert self.headers['apikey'] == KEY
            if self.path == f'/storage/v1/bucket/{BUCKET}':
                return self.reply(200, json.dumps({'id': BUCKET, 'public': False}).encode())
            key = self.path.removeprefix(f'/storage/v1/object/authenticated/{BUCKET}/')
            self.reply(200 if key in objects else 404, objects.get(key, b''))

        def do_POST(self):
            key = self.path.removeprefix(f'/storage/v1/object/{BUCKET}/')
            assert self.headers['x-upsert'] == 'false'
            data = self.rfile.read(int(self.headers['Content-Length']))
            if key in objects:
                return self.reply(409)
            objects[key] = data
            self.reply(201)

        def do_DELETE(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            for key in payload['prefixes']:
                objects.pop(key, None)
            self.reply(200)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = SupabaseObjectStore(f'http://127.0.0.1:{server.server_port}', KEY, BUCKET, allow_insecure_loopback=True)
    try:
        data = b'synthetic-content' * 10000
        spec = spec_for(data, project_fingerprint=store.project_fingerprint)
        source = tmp_path / spec.filename
        source.write_bytes(data)
        store.put(spec, source)
        with pytest.raises(ApiError):
            store.put(spec, source)
        store.download(spec, tmp_path / 'download')
        assert (tmp_path / 'download').read_bytes() == data
        store.delete(spec)
        assert objects == {}
    finally:
        store.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class MemoryStore:
    bucket = BUCKET
    project_fingerprint = hashlib.sha256(PROJECT.encode()).hexdigest()

    def __init__(self):
        self.objects = {}
        self.fail_after_upload = False

    def put(self, spec, path):
        self.objects[spec.object_key] = path.read_bytes()
        if self.fail_after_upload:
            raise ApiError(UNAVAILABLE, 503)

    def download(self, spec, path):
        path.write_bytes(self.objects[spec.object_key])

    def delete(self, spec):
        self.objects.pop(spec.object_key, None)


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "ledger.db"}')
    Base.metadata.create_all(engine)
    ArtifactBase.metadata.create_all(engine)
    with Session(engine) as db:
        alice = User(email='objects-alice@example.com', password_hash='synthetic')
        bob = User(email='objects-bob@example.com', password_hash='synthetic')
        video = Video(user=alice, url='https://example.com/synthetic', tags=[])
        db.add_all([video, bob])
        db.commit()
        yield db, alice.id, bob.id, video.id, MemoryStore()
    engine.dispose()


def publish(db, owner, video, path, store):
    return publish_artifact(db, user_id=owner, video_id=video, kind='note', path=path, store=store)


def test_publication_failure_keeps_old_pointer_and_pending_cleanup_record(ledger, tmp_path):
    db, alice, _, video, store = ledger
    path = tmp_path / f'{video}.md'
    path.write_bytes(b'old-version')
    first = publish(db, alice, video, path, store)
    store.fail_after_upload = True
    path.write_bytes(b'new-version')
    with pytest.raises(ApiError):
        publish(db, alice, video, path, store)
    rows = db.scalars(select(StoredArtifact)).all()
    assert {row.state for row in rows} == {'ready', 'pending'}
    assert db.get(StoredArtifact, first.id).state == 'ready'
    assert len(store.objects) == 2
    store.fail_after_upload = False
    latest = publish(db, alice, video, path, store)
    assert latest.id != first.id
    assert db.get(StoredArtifact, first.id).state == 'retired'
    assert db.get(StoredArtifact, latest.id).state == 'ready'


def test_owner_is_checked_before_remote_io_and_cache_is_private(ledger, tmp_path):
    db, alice, bob, video, store = ledger
    path = tmp_path / f'{video}.md'
    path.write_bytes(b'private-owner-content')
    with pytest.raises(ApiError) as error:
        publish(db, bob, video, path, store)
    assert error.value.status_code == 404 and store.objects == {}
    spec = publish(db, alice, video, path, store)
    for operation in [materialize_artifact, retire_artifact, purge_retired_artifact]:
        kwargs = dict(db=db, user_id=bob, artifact_id=spec.id)
        with pytest.raises(ApiError) as error:
            if operation is materialize_artifact:
                with operation(**kwargs, cache_root=tmp_path / 'cache', store=store):
                    pytest.fail('Cross-user read')
            elif operation is purge_retired_artifact:
                operation(**kwargs, store=store)
            else:
                operation(**kwargs)
        assert error.value.status_code == 404
    with materialize_artifact(db, user_id=alice, artifact_id=spec.id, cache_root=tmp_path / 'cache', store=store) as cached:
        assert cached.read_bytes() == b'private-owner-content'
        assert cached.parent.stat().st_mode & 0o077 == 0
    assert not cached.exists()


def test_delete_requires_retirement_and_ledger_survives_video_deletion(ledger, tmp_path):
    db, alice, _, video, store = ledger
    path = tmp_path / f'{video}.md'
    path.write_bytes(b'content')
    spec = publish(db, alice, video, path, store)
    with pytest.raises(ApiError):
        purge_retired_artifact(db, user_id=alice, artifact_id=spec.id, store=store)
    assert spec.object_key in store.objects
    retire_artifact(db, user_id=alice, artifact_id=spec.id)
    purge_retired_artifact(db, user_id=alice, artifact_id=spec.id, store=store)
    assert db.get(StoredArtifact, spec.id).state == 'deleted'
    assert not store.objects
    purge_retired_artifact(db, user_id=alice, artifact_id=spec.id, store=store)
    spec2 = publish(db, alice, video, path, store)
    db.delete(db.get(Video, video))
    db.commit()
    assert db.get(StoredArtifact, spec2.id).state == 'ready'
    with pytest.raises(ApiError):
        with materialize_artifact(db, user_id=alice, artifact_id=spec2.id, cache_root=tmp_path / 'cache', store=store):
            pytest.fail('Deleted video must not authorize file reads')


def test_quota_uses_net_replacement_and_failed_growth_keeps_old(ledger, tmp_path, monkeypatch):
    db, alice, _, video, store = ledger
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    path = tmp_path / f'{video}.md'
    path.write_bytes(b'a' * 800000)
    first = publish(db, alice, video, path, store)
    path.write_bytes(b'b' * 800000)
    second = publish(db, alice, video, path, store)
    assert db.get(StoredArtifact, first.id).state == 'retired'
    path.write_bytes(b'c' * 1100000)
    with pytest.raises(ApiError) as error:
        publish(db, alice, video, path, store)
    assert error.value.status_code == 413
    assert db.get(StoredArtifact, second.id).state == 'ready'
    monkeypatch.setattr(settings, 'max_user_storage_mb', 0)
    path.write_bytes(b'shorter')
    assert publish(db, alice, video, path, store).size_bytes == 7


def test_optional_ledger_not_in_business_metadata_and_default_prepare_does_not_connect(monkeypatch, capsys):
    from alembic import command
    assert 'vm_storage_objects' not in Base.metadata.tables
    monkeypatch.setattr(command, 'upgrade', lambda *args: pytest.fail('No database access without --apply'))
    assert prepare_main([]) == 2
    assert 'not_applied' in capsys.readouterr().out


def test_optional_prepare_failure_hides_database_error(monkeypatch, capsys):
    from alembic import command
    def fail(*args):
        raise RuntimeError('private-database-sentinel')
    monkeypatch.setattr(command, 'upgrade', fail)
    assert prepare_main(['--apply']) == 1
    assert 'private-database-sentinel' not in capsys.readouterr().out
