"""Authenticated HTTP/task integration: synthetic cloud/identity/models, real files."""

from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.video_analysis_agent import VideoAnalysisResult
from app.api import dependencies
from app.api.dependencies import get_db
from app.api.v1.routes import system, videos as routes
from app.core.config import settings
from app.database.base import Base
from app.main import app
from app.models import Video, VideoTask
from app.services import analysis, file_storage, video_tasks, video_upload, videos
from app.services.auth import AuthIdentity
from app.services.object_storage.cleanup import cleanup_requested_objects
from app.services.object_storage.models import ArtifactBase, StoredArtifact
from app.services.object_storage.quotas import logical_bytes
from app.services.object_storage.supabase import SupabaseObjectStore
from app.services.storage_quota import artifact_directory
from app.services.temporary_storage import write_bounded_text
from app.services.video_processing import pipeline
from app.services.video_processing.types import TranscriptResult
from test_object_pipeline import SyntheticStorageWire

REAL_PROBE = video_upload._probe_video


class UploadWire(SyntheticStorageWire):
    def __call__(self, request):
        if request.method == 'DELETE':
            for key in json.loads(request.read())['prefixes']:
                self.objects.pop(key, None)
            return httpx.Response(200)
        return super().__call__(request)


@pytest.fixture
def upload_environment(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "uploads.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    ArtifactBase.metadata.create_all(engine)
    wire = UploadWire()
    closed = []
    def factory():
        store = wire.client()
        close = store.close
        def record_close():
            closed.append(True)
            close()
        store.close = record_close
        return store
    monkeypatch.setattr(settings, 'auth_mode', 'supabase')
    monkeypatch.setattr(settings, 'file_storage_backend', 'supabase')
    monkeypatch.setattr(settings, 'max_upload_mb', 2)
    monkeypatch.setattr(settings, 'max_user_upload_mb', 1)
    monkeypatch.setattr(SupabaseObjectStore, 'from_settings', factory)
    monkeypatch.setattr(dependencies, 'decode_supabase_token', lambda token: AuthIdentity(subject=token, email=f'{token}@example.com'))
    monkeypatch.setattr(video_upload, '_probe_video', lambda path: 1)
    monkeypatch.setattr(system, 'SessionLocal', lambda: Session(engine))
    monkeypatch.setattr(system, 'check_database_connection', lambda: None)
    monkeypatch.setattr(system, 'check_vector_store_connection', lambda: None)
    def sessions():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = sessions
    try:
        with TestClient(app) as client:
            yield client, engine, wire, closed
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def auth(user='alice'):
    return {'Authorization': f'Bearer {user}'}


def upload(client, data=b'synthetic-video', user='alice', filename='source.mp4', mime='video/mp4'):
    return client.post('/api/v1/videos/upload', headers=auth(user), files={'file': (filename, BytesIO(data), mime)})


def test_http_upload_commits_source_and_video_together_and_scopes_dedup(upload_environment):
    client, engine, wire, closed = upload_environment
    first = upload(client)
    assert first.status_code == 201 and first.json()['media_path'].startswith('object://')
    assert upload(client).status_code == 409
    assert upload(client, user='bob').status_code == 201
    with Session(engine) as db:
        assert db.query(Video).count() == 2
        rows = db.scalars(select(StoredArtifact)).all()
        assert len(rows) == 2 and all(row.is_source_upload and row.state == 'ready' for row in rows)
    assert wire.uploads == 2 and len(closed) == 3
    assert not list(Path(settings.video_storage_dir).iterdir())


def test_unknown_upload_response_keeps_reservation_without_visible_video(upload_environment):
    client, engine, wire, _ = upload_environment
    wire.fail_upload = 1
    first = upload(client, b'a' * 700000)
    assert first.status_code == 503
    assert client.get('/api/v1/videos', headers=auth()).json()['total'] == 0
    assert upload(client, b'a' * 700000).status_code == 409
    rejected = upload(client, b'b' * 400000)
    assert rejected.status_code == 413
    with Session(engine) as db:
        row = db.scalar(select(StoredArtifact))
        assert row.state == 'pending' and row.is_source_upload
        assert logical_bytes(db, row.user_id) == 700000
        assert db.query(Video).count() == 0
    assert wire.uploads == 1 and len(wire.objects) == 1
    assert not list(Path(settings.video_storage_dir).iterdir())


@pytest.mark.parametrize('data,filename,mime,status', [(b'', 'source.mp4', 'video/mp4', 415), (b'bad', 'source.exe', 'video/mp4', 415),
    (b'bad', 'source.mp4', 'text/plain', 415), (b'x' * (2 * 1024 * 1024 + 1), 'source.mp4', 'video/mp4', 413)])
def test_invalid_upload_never_reserves_or_transfers(upload_environment, data, filename, mime, status):
    client, engine, wire, _ = upload_environment
    assert upload(client, data, filename=filename, mime=mime).status_code == status
    with Session(engine) as db:
        assert db.query(Video).count() == 0 and db.query(StoredArtifact).count() == 0
    assert wire.uploads == 0


def test_media_probe_failure_keeps_no_reservation(upload_environment, monkeypatch):
    client, engine, wire, _ = upload_environment
    monkeypatch.setattr(video_upload, '_probe_video', REAL_PROBE)
    assert upload(client, b'not-video').status_code == 415
    assert wire.uploads == 0
    with Session(engine) as db:
        assert db.query(StoredArtifact).count() == 0


def test_auth_failure_does_not_create_storage_client(upload_environment):
    client, _, wire, closed = upload_environment
    response = client.post('/api/v1/videos/upload', files={'file': ('a.mp4', b'synthetic', 'video/mp4')})
    assert response.status_code == 401 and not closed and wire.uploads == 0


def test_ready_checks_selected_backend_without_printing_provider_error(upload_environment, monkeypatch):
    client, _, _, _ = upload_environment
    good = client.get('/api/v1/health/ready')
    assert good.status_code == 200 and good.json()['file_storage'] == 'supabase'
    def fail():
        raise RuntimeError('private-key-and-url-sentinel')
    monkeypatch.setattr(SupabaseObjectStore, 'from_settings', fail)
    response = client.get('/api/v1/health/ready')
    assert response.status_code == 503 and response.json()['detail'] == '文件存储尚未就绪'
    assert 'sentinel' not in response.text


def test_unknown_backend_fails_without_local_fallback(upload_environment, monkeypatch):
    client, _, wire, _ = upload_environment
    monkeypatch.setattr(settings, 'file_storage_backend', 'unknown')
    assert upload(client).status_code == 503 and wire.uploads == 0
    assert client.get('/api/v1/health/ready').status_code == 503


def test_local_factory_does_not_construct_cloud_client(upload_environment, monkeypatch):
    _, engine, wire, _ = upload_environment
    monkeypatch.setattr(settings, 'file_storage_backend', 'local')
    monkeypatch.setattr(SupabaseObjectStore, 'from_settings', lambda: pytest.fail('No cloud client for local'))
    with Session(engine) as db, file_storage.managed_file_store(db) as store:
        assert store is None
    assert wire.uploads == 0


def test_missing_schema_blocks_before_cloud_access(upload_environment):
    client, engine, wire, _ = upload_environment
    ArtifactBase.metadata.drop_all(engine)
    assert upload(client).status_code == 503 and wire.uploads == 0
    assert client.get('/api/v1/health/ready').status_code == 503


def test_upload_task_notes_and_explicit_delete_recovery_use_same_backend(upload_environment, monkeypatch, tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg required')
    client, engine, wire, closed = upload_environment
    monkeypatch.setattr(video_upload, '_probe_video', REAL_PROBE)
    source = tmp_path / 'synthetic.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=size=16x16:rate=10',
                    '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '0.5', '-c:v', 'mpeg4', '-c:a', 'aac', str(source)],
                   check=True, capture_output=True, timeout=20)
    response = upload(client, source.read_bytes())
    assert response.status_code == 201
    video_id = response.json()['id']
    source.unlink()
    monkeypatch.setattr(settings, 'asr_provider', 'faster_whisper')
    monkeypatch.setattr(pipeline, 'ensure_local_asr_available', lambda: None)
    def asr(audio_path, video_id, api_key):
        assert api_key is None and Path(audio_path).stat().st_size > 100
        write_bounded_text(artifact_directory('transcript') / f'{video_id}.txt', 'synthetic ASR text')
        return TranscriptResult(video_id, 'synthetic ASR text', 'synthetic')
    def analyze(**kwargs):
        assert kwargs['user'].auth_subject == 'alice'
        return VideoAnalysisResult(title='Synthetic', summary='Synthetic'), 'generated note'
    monkeypatch.setattr(pipeline, 'transcribe_audio', asr)
    monkeypatch.setattr(analysis, 'analyze_video_transcript', analyze)
    monkeypatch.setattr(routes, 'resolve_llm', lambda user: None)  # Synthetic provider acceptance only.
    monkeypatch.setattr(video_tasks, 'index_video', lambda *args: None)
    assert client.post(f'/api/v1/videos/{video_id}/run', headers=auth()).status_code == 202
    with Session(engine) as worker:
        task = video_tasks.claim_next_task(worker, 'synthetic-worker')
        task_id = task.id
        video_tasks.execute_claimed_task(worker, task_id, 'synthetic-worker')
        assert worker.get(VideoTask, task_id).status == 'succeeded'
        assert worker.get(Video, video_id).summary.markdown_note == 'generated note'
    assert client.put(f'/api/v1/videos/{video_id}/note', headers=auth(), json={'markdown_note': 'manual note'}).status_code == 200
    before = wire.uploads
    assert client.put(f'/api/v1/videos/{video_id}/note', headers=auth('bob'), json={'markdown_note': 'wrong owner'}).status_code == 404
    assert wire.uploads == before
    monkeypatch.setattr(videos.vector_store, 'delete_video_document', lambda **kwargs: None)
    assert client.delete(f'/api/v1/videos/{video_id}', headers=auth()).status_code == 204
    store = wire.client()
    try:
        with Session(engine) as db:
            report = cleanup_requested_objects(db, store=store)
            assert report['status'] == 'complete' and report['confirmed_deleted'] >= 5
    finally:
        store.close()
    assert not wire.objects and len(closed) >= 4
    for kind in ('video', 'audio', 'transcript', 'note'):
        assert not list(Path(getattr(settings, f'{kind}_storage_dir')).iterdir())


def test_storage_preflight_failure_closes_client_without_creating_reservation(upload_environment, monkeypatch):
    client, engine, wire, closed = upload_environment
    def fail(self):
        raise RuntimeError('private-provider-sentinel')
    monkeypatch.setattr(SupabaseObjectStore, 'check_connection', fail)
    response = upload(client)
    assert response.status_code == 503 and 'sentinel' not in response.text
    with Session(engine) as db:
        assert db.query(StoredArtifact).count() == 0
    assert wire.uploads == 0 and closed == [True]


def test_total_quota_is_separate_from_source_quota(upload_environment, monkeypatch):
    client, _, wire, _ = upload_environment
    monkeypatch.setattr(settings, 'max_user_upload_mb', 3)
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    assert upload(client, b'a' * 700000).status_code == 201
    response = upload(client, b'b' * 400000)
    assert response.status_code == 413 and '文件存储总量' in response.json()['detail']
    assert wire.uploads == 1


def test_generated_outputs_cannot_spend_a_pending_source_reservation(upload_environment, monkeypatch):
    client, engine, wire, _ = upload_environment
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    wire.fail_upload = 1
    assert upload(client, b'a' * 700000).status_code == 503
    created = client.post('/api/v1/videos', headers=auth(), json={'url': 'https://example.com/synthetic', 'tags': []})
    assert created.status_code == 201
    video_id = created.json()['id']
    with Session(engine) as db:
        from app.models import Transcript
        item = db.get(Video, video_id)
        item.transcript = Transcript(content='synthetic source')
        db.commit()
    monkeypatch.setattr(routes, 'resolve_llm', lambda user: None)
    monkeypatch.setattr(analysis, 'analyze_video_transcript', lambda **kwargs: (VideoAnalysisResult(title='Synthetic', summary='Synthetic'), 'b' * 400000))
    assert client.post(f'/api/v1/videos/{video_id}/analyze', headers=auth()).status_code == 202
    with Session(engine) as db:
        task = video_tasks.claim_next_task(db, 'synthetic-worker')
        video_tasks.execute_claimed_task(db, task.id, 'synthetic-worker')
        assert task.status == 'failed' and '文件存储总量' in task.error
        assert db.get(Video, video_id).summary is None
        assert all(row.state == 'pending' for row in db.scalars(select(StoredArtifact)))


def test_worker_bad_backend_fails_before_provider_processing(upload_environment, monkeypatch):
    client, engine, _, _ = upload_environment
    video_id = upload(client).json()['id']
    assert client.post(f'/api/v1/videos/{video_id}/process', headers=auth()).status_code == 202
    monkeypatch.setattr(settings, 'file_storage_backend', 'unknown')
    monkeypatch.setattr(video_tasks, 'process_video', lambda *args, **kwargs: pytest.fail('Invalid backend must not process'))
    with Session(engine) as db:
        task = video_tasks.claim_next_task(db, 'synthetic-worker')
        video_tasks.execute_claimed_task(db, task.id, 'synthetic-worker')
        assert task.status == 'failed' and task.video.status == 'failed'
        assert task.error == '文件存储暂不可用，请稍后重试'
