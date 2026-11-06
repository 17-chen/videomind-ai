"""Real service/file paths with synthetic HTTP Supabase, ASR and LLM responses."""

from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.video_analysis_agent import VideoAnalysisResult
from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.models import User, Video, Transcript
from app.schemas.video import VideoNoteUpdate
from app.services import analysis, videos
from app.services.object_storage.models import ArtifactBase, StoredArtifact
from app.services.object_storage.references import artifact_reference, reference_id
from app.services.object_storage.repository import materialize_artifacts, publish_artifacts
from app.services.object_storage.supabase import SupabaseObjectStore
from app.services.storage_quota import artifact_directory, generate_artifacts
from app.services.video_processing import pipeline
from app.services.video_processing.types import DownloadedVideo, ExtractedAudio, TranscriptResult


class SyntheticStorageWire:
    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.fail_upload = None
        self.fail_download = False
        self.downloads = 0
        self.fail_download_at = None

    def __call__(self, request):
        assert request.headers['apikey'] == 'sb_secret_synthetic_storage_test_only'
        path = request.url.path
        if '/bucket/' in path:
            return httpx.Response(200, json={'id': 'videomind-private', 'public': False})
        if request.method == 'POST':
            self.uploads += 1
            key = path.split('/object/videomind-private/', 1)[1]
            assert key not in self.objects and request.headers['x-upsert'] == 'false'
            self.objects[key] = request.read()
            if self.uploads == self.fail_upload:
                raise httpx.ReadError('synthetic uncertain upload')
            return httpx.Response(201)
        if '/object/authenticated/' in path:
            self.downloads += 1
            key = path.split('/object/authenticated/videomind-private/', 1)[1]
            if self.fail_download or self.downloads == self.fail_download_at:
                raise httpx.ReadError('synthetic download failure')
            if key not in self.objects:
                return httpx.Response(404)
            return httpx.Response(200, stream=httpx.ByteStream(self.objects[key]), headers={'Content-Length': str(len(self.objects[key]))})
        pytest.fail('Unexpected synthetic storage request')

    def client(self):
        return SupabaseObjectStore('https://storage.example.invalid', 'sb_secret_synthetic_storage_test_only',
                                   'videomind-private', transport=httpx.MockTransport(self))


@pytest.fixture
def environment(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "objects.db"}')
    Base.metadata.create_all(engine)
    ArtifactBase.metadata.create_all(engine)
    wire = SyntheticStorageWire()
    store = wire.client()
    with Session(engine) as db:
        alice = User(email='pipeline-alice@example.com', password_hash='synthetic')
        bob = User(email='pipeline-bob@example.com', password_hash='synthetic')
        video = Video(user=alice, url='https://example.com/synthetic', tags=[])
        db.add_all([video, bob])
        db.commit()
        yield db, video, bob, wire, store
    store.close()
    engine.dispose()


def write(kind, video, data, suffix):
    root = artifact_directory(kind)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{video.id}{suffix}'
    path.write_bytes(data)
    return path


def batch_files(root, video, contents):
    root.mkdir(parents=True)
    paths = []
    for suffix, data in contents.items():
        path = root / f'{video.id}{suffix}'
        path.write_bytes(data)
        paths.append(path)
    return paths


def ready(db, video):
    return db.scalars(select(StoredArtifact).where(StoredArtifact.video_id == video.id, StoredArtifact.state == 'ready')).all()


def test_group_failure_preserves_complete_previous_group(environment, tmp_path):
    db, video, _, wire, store = environment
    old = batch_files(tmp_path / 'old', video, {'.mp4': b'old-video', '.zh.vtt': b'old-caption'})
    original = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=old, store=store, replace_kind=True)
    new = batch_files(tmp_path / 'new', video, {'.mp4': b'new-video', '.en.vtt': b'new-caption'})
    wire.fail_upload = wire.uploads + 2
    with pytest.raises(ApiError):
        publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=new, store=store, replace_kind=True)
    assert {row.id for row in ready(db, video)} == {spec.id for spec in original}
    assert len(db.scalars(select(StoredArtifact).where(StoredArtifact.state == 'pending')).all()) == 2
    wire.fail_upload = None
    published = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=new, store=store, replace_kind=True)
    assert {row.id for row in ready(db, video)} == {spec.id for spec in published}
    assert all(db.get(StoredArtifact, spec.id).state == 'retired' for spec in original)


def test_group_quota_is_net_replacement_and_failure_is_atomic(environment, tmp_path, monkeypatch):
    db, video, _, _, store = environment
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    old = batch_files(tmp_path / 'old', video, {'.mp4': b'a' * 600000, '.zh.vtt': b'b' * 300000})
    specs = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=old, store=store, replace_kind=True)
    large = batch_files(tmp_path / 'large', video, {'.mp4': b'c' * 700000, '.en.vtt': b'd' * 400000})
    with pytest.raises(ApiError) as error:
        publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=large, store=store, replace_kind=True)
    assert error.value.status_code == 413 and {row.id for row in ready(db, video)} == {spec.id for spec in specs}
    small = batch_files(tmp_path / 'small', video, {'.mp4': b'e' * 800000})
    result = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=small, store=store, replace_kind=True)
    assert [row.id for row in ready(db, video)] == [result[0].id]


@pytest.mark.parametrize('invalid', ['empty', 'duplicate', 'large'])
def test_invalid_group_does_not_upload(environment, tmp_path, monkeypatch, invalid):
    db, video, _, wire, store = environment
    paths = batch_files(tmp_path / 'input', video, {'.mp4': b'a' * 600000, '.en.vtt': b'b' * 600000})
    if invalid == 'empty':
        paths = []
    elif invalid == 'duplicate':
        paths = [paths[0], paths[0]]
    else:
        monkeypatch.setattr(settings, 'max_media_stage_mb', 1)
    with pytest.raises((ApiError, ValueError)):
        publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=paths, store=store)
    assert wire.uploads == 0 and not db.scalars(select(StoredArtifact)).all()


def test_materialize_scopes_owner_and_cleans_failure(environment, tmp_path):
    db, video, bob, wire, store = environment
    paths = batch_files(tmp_path / 'input', video, {'.mp4': b'video', '.en.vtt': b'caption'})
    specs = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=paths, store=store)
    kwargs = dict(video_id=video.id, kind='video', cache_root=tmp_path / 'cache', store=store, required_id=specs[0].id)
    with pytest.raises(ApiError) as error:
        with materialize_artifacts(db, user_id=bob.id, **kwargs):
            pytest.fail('Cross-user read')
    assert error.value.status_code == 404
    wire.fail_download = True
    with pytest.raises(ApiError):
        with materialize_artifacts(db, user_id=video.user_id, **kwargs):
            pytest.fail('Failed download')
    assert not list((tmp_path / 'cache').iterdir())
    wire.fail_download = False
    with materialize_artifacts(db, user_id=video.user_id, **kwargs) as (root, primary):
        assert primary.read_bytes() == b'video'
        assert len(list(root.iterdir())) == 2 and root.stat().st_mode & 0o077 == 0
    assert not root.exists()


def test_subtitle_processing_reads_private_group_and_persists_only_identity(environment, monkeypatch):
    db, video, _, _, store = environment
    inputs = []
    def download(url, video_id):
        media = write('video', video, b'synthetic-media', '.mp4')
        write('video', video, b'WEBVTT\n\n00:00.000 --> 00:01.000\nPrivate caption\n', '.en.vtt')
        inputs.append(media)
        return DownloadedVideo(video_id, url, str(media))
    monkeypatch.setattr(pipeline, 'download_video', download)
    monkeypatch.setattr(pipeline, 'extract_audio', lambda **kwargs: pytest.fail('Subtitles must avoid ASR'))
    pipeline.process_video(db, video, object_store=store)
    assert video.transcript.content == 'Private caption'
    assert video.media_path.startswith('object://') and not inputs[0].exists()
    assert {row.kind for row in ready(db, video)} == {'video', 'transcript'}
    for kind in ('video', 'transcript'):
        assert not list(Path(getattr(settings, f'{kind}_storage_dir')).iterdir())


def test_fresh_client_processes_uploaded_identity_without_shared_local_files(environment, tmp_path, monkeypatch):
    db, video, _, wire, store = environment
    source = batch_files(tmp_path / 'input', video, {'.mp4': b'synthetic-media'})
    spec = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=source, store=store)[0]
    video.source, video.media_path = 'upload', artifact_reference(spec.id)
    db.commit()
    shutil.rmtree(tmp_path / 'input')
    seen = []
    monkeypatch.setattr(pipeline, 'download_video', lambda **kwargs: pytest.fail('Already stored source'))
    monkeypatch.setattr(pipeline, 'resolve_asr_key', lambda user: 'synthetic-own-asr-key' if user.id == video.user_id else pytest.fail('Wrong user'))
    def extract(video_path, video_id):
        assert Path(video_path).read_bytes() == b'synthetic-media'
        seen.append(Path(video_path))
        return ExtractedAudio(video_id, str(write('audio', video, b'synthetic-audio', '.mp3')))
    def transcribe(audio_path, video_id, api_key):
        assert api_key == 'synthetic-own-asr-key' and Path(audio_path).read_bytes() == b'synthetic-audio'
        seen.append(Path(audio_path))
        write('transcript', video, b'synthetic transcript', '.txt')
        return TranscriptResult(video_id, 'synthetic transcript', 'synthetic')
    monkeypatch.setattr(pipeline, 'extract_audio', extract)
    monkeypatch.setattr(pipeline, 'transcribe_audio', transcribe)
    video_id = video.id
    # A fresh SQL Session and fresh HTTP client use only persisted object identity.
    fresh = wire.client()
    try:
        with Session(db.get_bind()) as other:
            item = other.get(Video, video_id)
            pipeline.process_video(other, item, object_store=fresh)
            assert item.audio_path.startswith('object://') and item.transcript.content == 'synthetic transcript'
    finally:
        fresh.close()
    assert all(not path.exists() for path in seen)


def test_real_ffmpeg_uses_hydrated_media_with_simulated_asr(environment, monkeypatch):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg required')
    db, video, _, _, store = environment
    monkeypatch.setattr(settings, 'asr_provider', 'faster_whisper')
    monkeypatch.setattr(pipeline, 'ensure_local_asr_available', lambda: None)
    def download(url, video_id):
        root = artifact_directory('video')
        path = root / f'{video_id}.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=size=16x16:rate=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '0.5', '-c:v', 'mpeg4', '-c:a', 'aac', str(path)],
                       check=True, capture_output=True, timeout=20)
        return DownloadedVideo(video_id, url, str(path))
    def transcribe(audio_path, video_id, api_key):
        assert api_key is None and Path(audio_path).stat().st_size > 100
        write('transcript', video, b'simulated ASR', '.txt')
        return TranscriptResult(video_id, 'simulated ASR', 'synthetic')
    monkeypatch.setattr(pipeline, 'download_video', download)
    monkeypatch.setattr(pipeline, 'transcribe_audio', transcribe)
    pipeline.process_video(db, video, object_store=store)
    assert video.transcript.content == 'simulated ASR'
    assert {row.kind for row in ready(db, video)} == {'video', 'audio', 'transcript'}


def test_analysis_manual_notes_and_failed_replacement(environment, monkeypatch):
    db, video, _, wire, store = environment
    video.transcript = Transcript(content='synthetic source')
    db.commit()
    monkeypatch.setattr(analysis, 'analyze_video_transcript', lambda **kwargs: (VideoAnalysisResult(title='Synthetic', summary='Synthetic'), 'generated note'))
    analysis.analyze_video(db, video, object_store=store)
    videos.update_note_for_user(db, video.user, video.id, VideoNoteUpdate(markdown_note='manual note'), object_store=store)
    assert video.summary.markdown_note == 'manual note' and video.summary.note_is_manual
    before = wire.uploads
    analysis.analyze_video(db, video, object_store=store)
    assert wire.uploads == before and video.summary.markdown_note == 'manual note'
    previous = ready(db, video)[0].id
    wire.fail_upload = wire.uploads + 1
    with pytest.raises(ApiError):
        videos.update_note_for_user(db, video.user, video.id, VideoNoteUpdate(markdown_note='failed new note'), object_store=store)
    assert video.summary.markdown_note == 'manual note' and ready(db, video)[0].id == previous


@pytest.mark.parametrize('value', [None, '/tmp/local.mp4', 'object://../other', 'https://provider.example/object', 'object://' + uuid4().hex])
def test_invalid_reference_rejected(value):
    with pytest.raises(ApiError):
        reference_id(value)


def test_object_reference_without_client_fails_before_download(environment, monkeypatch):
    db, video, _, _, _ = environment
    video.media_path = artifact_reference(str(uuid4()))
    db.commit()
    monkeypatch.setattr(pipeline, 'download_video', lambda **kwargs: pytest.fail('Must not downgrade to local storage'))
    with pytest.raises(ApiError) as error:
        pipeline.process_video(db, video)
    assert error.value.status_code == 503


def test_wrong_generated_path_rejected_before_publishing(environment):
    db, video, _, wire, store = environment
    def produce():
        write('video', video, b'output', '.mp4')
        return DownloadedVideo(video.id, video.url, '/tmp/incorrect.mp4')
    with pytest.raises(ApiError):
        generate_artifacts(db, video, 'video', produce, object_store=store)
    assert wire.uploads == 0


def test_mid_group_download_failure_removes_earlier_plaintext(environment, tmp_path):
    db, video, _, wire, store = environment
    paths = batch_files(tmp_path / 'input', video, {'.mp4': b'media', '.en.vtt': b'caption'})
    specs = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=paths, store=store)
    wire.fail_download_at = 2
    with pytest.raises(ApiError):
        with materialize_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', cache_root=tmp_path / 'cache', store=store, required_id=specs[0].id):
            pytest.fail('Partially downloaded group must not be exposed')
    assert wire.downloads == 2 and not list((tmp_path / 'cache').iterdir())


def test_hydration_limit_and_foreign_reference_reject_before_download(environment, tmp_path, monkeypatch):
    db, video, _, wire, store = environment
    paths = batch_files(tmp_path / 'input', video, {'.mp4': b'a' * 600000, '.en.vtt': b'b' * 600000})
    specs = publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=paths, store=store)
    kwargs = dict(user_id=video.user_id, video_id=video.id, kind='video', cache_root=tmp_path / 'cache', store=store)
    with pytest.raises(ApiError) as error:
        with materialize_artifacts(db, **kwargs, required_id=str(uuid4())):
            pytest.fail('Reference not in the owned group')
    assert error.value.status_code == 404
    monkeypatch.setattr(settings, 'max_media_stage_mb', 1)
    with pytest.raises(ApiError) as error:
        with materialize_artifacts(db, **kwargs, required_id=specs[0].id):
            pytest.fail('Group exceeds temporary limit')
    assert error.value.status_code == 413 and wire.downloads == 0


def test_missing_generated_output_cannot_persist_a_local_reference(environment):
    db, video, _, wire, store = environment
    with pytest.raises(ApiError):
        generate_artifacts(db, video, 'video', lambda: DownloadedVideo(video.id, video.url, '/tmp/missing.mp4'), object_store=store)
    assert wire.uploads == 0 and video.media_path is None


def test_object_publication_rejects_existing_local_files_before_upload(environment, tmp_path):
    db, video, _, wire, store = environment
    write('note', video, b'legacy-local-file', '.md')
    paths = batch_files(tmp_path / 'new', video, {'.mp4': b'new-media'})
    with pytest.raises(ApiError) as error:
        publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=paths, store=store)
    assert error.value.status_code == 503 and wire.uploads == 0


def test_local_upload_cannot_ignore_existing_object_storage(environment, tmp_path, monkeypatch):
    from io import BytesIO
    from fastapi import UploadFile
    from app.services import video_upload
    db, video, _, _, store = environment
    paths = batch_files(tmp_path / 'input', video, {'.mp4': b'synthetic'})
    publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind='video', paths=paths, store=store)
    monkeypatch.setattr(video_upload, '_probe_video', lambda path: 1)
    with pytest.raises(ApiError) as error:
        video_upload.save_uploaded_video(db, video.user, UploadFile(BytesIO(b'synthetic-new'), filename='new.mp4'))
    assert error.value.status_code == 503 and db.query(Video).count() == 1
    assert not list(artifact_directory('video').glob('*.part'))
