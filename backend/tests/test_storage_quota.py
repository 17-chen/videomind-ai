from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.video_analysis_agent import VideoAnalysisResult
from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.models import User, Video, Summary, Transcript  # noqa: F401
from app.schemas.video import VideoNoteUpdate
from app.services import analysis, video_upload, videos
from app.services.storage_quota import (
    ARTIFACT_KINDS, artifact_directory, generate_artifacts, user_storage_bytes,
)
from app.services.video_processing import pipeline
from app.services.video_processing.types import DownloadedVideo, ExtractedAudio, TranscriptResult


@pytest.fixture
def storage_db(monkeypatch, tmp_path):
    for kind in ARTIFACT_KINDS:
        monkeypatch.setattr(settings, f'{kind}_storage_dir', str(tmp_path / kind))
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    engine = create_engine('sqlite+pysqlite://', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            alice = User(email='alice@example.com', password_hash='test')
            bob = User(email='bob@example.com', password_hash='test')
            first = Video(user=alice, url='https://example.com/one', tags=[])
            second = Video(user=alice, url='https://example.com/two', tags=[], source='upload')
            foreign = Video(user=bob, url='https://example.com/foreign', tags=[])
            db.add_all([first, second, foreign])
            db.commit()
            yield db, first, second, foreign
    finally:
        engine.dispose()


def write(kind, video, data, suffix):
    directory = artifact_directory(kind)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{video.id}{suffix}'
    path.write_bytes(data)
    return path


def test_counts_all_published_types_and_only_owners_files(storage_db):
    db, first, second, foreign = storage_db
    for kind, suffix in [('video', '.mp4'), ('video', '.zh.vtt'), ('audio', '.mp3'), ('transcript', '.txt'), ('note', '.md')]:
        write(kind, first, b'abc', suffix)
        write(kind, foreign, b'foreign', suffix)
    write('video', second, b'upload', '.mov')
    (artifact_directory('video') / 'unrelated.txt').write_bytes(b'ignore')
    staged = artifact_directory('video') / '.staging-abandoned'
    staged.mkdir()
    (staged / f'{first.id}.mp4').write_bytes(b'not published')
    assert user_storage_bytes(db, first.user_id) == 21
    assert user_storage_bytes(db, foreign.user_id) == 35


def test_group_rejection_preserves_old_files_and_cleans_staging(storage_db):
    db, first, _, _ = storage_db
    original = write('video', first, b'old', '.mp4')

    def produce():
        path = write('video', first, b'x' * (700 * 1024), '.mp4')
        write('video', first, b'y' * (400 * 1024), '.en.vtt')
        return DownloadedVideo(first.id, first.url, str(path))

    with pytest.raises(ApiError) as exc:
        generate_artifacts(db, first, 'video', produce)
    assert exc.value.status_code == 413
    assert original.read_bytes() == b'old'
    assert list(artifact_directory('video').iterdir()) == [original]


def test_replacement_uses_net_growth_and_allows_shrink_when_already_over(storage_db):
    db, first, second, _ = storage_db
    write('note', first, b'x' * (600 * 1024), '.md')
    write('video', second, b'x' * (400 * 1024), '.mp4')
    generate_artifacts(db, first, 'note', lambda: write('note', first, b'y' * (600 * 1024), '.md'))
    write('video', second, b'x' * (1100 * 1024), '.mp4')
    generate_artifacts(db, first, 'note', lambda: write('note', first, b'smaller', '.md'))
    assert (artifact_directory('note') / f'{first.id}.md').read_bytes() == b'smaller'
    with pytest.raises(ApiError):
        generate_artifacts(db, first, 'note', lambda: write('note', first, b'slightly larger', '.md'))


def test_media_result_path_is_published_and_failed_producer_leaves_no_output(storage_db):
    db, first, _, _ = storage_db

    def produce():
        path = write('audio', first, b'audio', '.mp3')
        return ExtractedAudio(first.id, str(path))

    result = generate_artifacts(db, first, 'audio', produce)
    assert Path(result.file_path) == artifact_directory('audio') / f'{first.id}.mp3'
    assert Path(result.file_path).read_bytes() == b'audio'

    def fail():
        write('transcript', first, b'partial', '.txt')
        raise RuntimeError('producer failed')

    with pytest.raises(RuntimeError):
        generate_artifacts(db, first, 'transcript', fail)
    assert list(artifact_directory('transcript').iterdir()) == []


def test_producer_cannot_publish_other_video_or_symlink(storage_db, tmp_path):
    db, first, _, foreign = storage_db
    with pytest.raises(ApiError):
        generate_artifacts(db, first, 'note', lambda: write('note', foreign, b'wrong owner', '.md'))
    target = tmp_path / 'outside.txt'
    target.write_bytes(b'private')

    def symlink():
        (artifact_directory('note') / f'{first.id}.md').symlink_to(target)

    with pytest.raises(ApiError):
        generate_artifacts(db, first, 'note', symlink)
    assert target.read_bytes() == b'private'


def test_upload_counts_existing_downloads_and_generated_files(storage_db, monkeypatch):
    db, first, _, foreign = storage_db
    write('audio', first, b'a' * (700 * 1024), '.mp3')
    monkeypatch.setattr(video_upload, '_probe_video', lambda _: 1)
    with pytest.raises(ApiError) as exc:
        video_upload.save_uploaded_video(db, first.user, UploadFile(BytesIO(b'b' * (400 * 1024)), filename='video.mp4'))
    assert exc.value.status_code == 413
    assert not list(artifact_directory('video').glob('*.part'))
    assert db.query(Video).count() == 3
    other = video_upload.save_uploaded_video(db, foreign.user, UploadFile(BytesIO(b'b' * (400 * 1024)), filename='video.mp4'))
    assert other.source == 'upload'


def test_manual_note_rejection_keeps_database_and_file_then_delete_frees_bytes(storage_db, monkeypatch):
    db, first, second, _ = storage_db
    first.summary = Summary(summary='summary', markdown_note='original')
    db.commit()
    original = write('note', first, b'original', '.md')
    write('video', second, b'x' * (1024 * 1024 - 9), '.mp4')
    with pytest.raises(ApiError):
        videos.update_note_for_user(db, first.user, first.id, VideoNoteUpdate(markdown_note='更长的新笔记'))
    db.refresh(first)
    assert first.summary.markdown_note == 'original'
    assert first.summary.note_is_manual is False
    assert original.read_bytes() == b'original'
    monkeypatch.setattr(videos.vector_store, 'delete_video_document', lambda **_: None)
    videos.delete_video_for_user(db, second.user, second.id)
    videos.update_note_for_user(db, first.user, first.id, VideoNoteUpdate(markdown_note='更长的新笔记'))
    assert original.read_text() == '更长的新笔记'
    assert first.summary.note_is_manual is True


def test_generated_note_rejection_does_not_commit_new_analysis(storage_db, monkeypatch):
    db, first, _, _ = storage_db
    first.transcript = Transcript(content='source')
    db.commit()
    monkeypatch.setattr(analysis, 'analyze_video_transcript', lambda **_: (
        VideoAnalysisResult(title='new', summary='new summary'), 'x' * (1024 * 1024 + 1),
    ))
    with pytest.raises(ApiError):
        analysis.analyze_video(db, first)
    db.refresh(first)
    assert first.summary is None
    assert not list(artifact_directory('note').iterdir())


def test_pipeline_audio_rejection_keeps_admitted_download_and_marks_failure(storage_db, monkeypatch):
    db, first, _, _ = storage_db

    def download(url, video_id):
        path = write('video', first, b'video' * (140 * 1024), '.mp4')
        return DownloadedVideo(video_id, url, str(path))

    def extract(**kwargs):
        path = write('audio', first, b'a' * (400 * 1024), '.mp3')
        return ExtractedAudio(first.id, str(path))

    monkeypatch.setattr(pipeline, 'download_video', download)
    monkeypatch.setattr(pipeline, 'resolve_asr_key', lambda _: 'mock-asr')
    monkeypatch.setattr(pipeline, 'extract_audio', extract)
    monkeypatch.setattr(pipeline, 'transcribe_audio', lambda **_: pytest.fail('ASR must not run after quota rejection'))
    with pytest.raises(ApiError) as exc:
        pipeline.process_video(db, first)
    assert exc.value.status_code == 413
    assert first.status == 'failed'
    assert '存储总量' in first.processing_error
    assert Path(first.media_path).exists() and '.staging-' not in first.media_path
    assert not list(artifact_directory('audio').iterdir())
    assert first.audio_path is None and first.transcript is None


def test_pipeline_transcript_rejection_preserves_audio_and_no_database_transcript(storage_db, monkeypatch):
    db, first, _, _ = storage_db
    first.source = 'upload'
    first.media_path = str(write('video', first, b'x' * (700 * 1024), '.mp4'))
    db.commit()
    monkeypatch.setattr(pipeline, 'resolve_asr_key', lambda _: 'mock-asr')

    def extract(**kwargs):
        return ExtractedAudio(first.id, str(write('audio', first, b'a' * (200 * 1024), '.mp3')))

    def transcribe(**kwargs):
        write('transcript', first, b't' * (200 * 1024), '.txt')
        return TranscriptResult(first.id, 'mock transcript', 'mock')

    monkeypatch.setattr(pipeline, 'extract_audio', extract)
    monkeypatch.setattr(pipeline, 'transcribe_audio', transcribe)
    with pytest.raises(ApiError):
        pipeline.process_video(db, first)
    assert first.status == 'failed'
    assert Path(first.audio_path).exists()
    assert first.transcript is None
    assert not list(artifact_directory('transcript').iterdir())


def test_worker_records_quota_failure_without_publishing_oversized_artifact(storage_db, monkeypatch):
    from app.services import video_tasks

    db, first, _, _ = storage_db
    first.source = 'upload'
    first.media_path = str(write('video', first, b'x' * (700 * 1024), '.mp4'))
    db.commit()
    monkeypatch.setattr(pipeline, 'resolve_asr_key', lambda _: 'mock-asr')

    def extract(**kwargs):
        return ExtractedAudio(first.id, str(write('audio', first, b'x' * (400 * 1024), '.mp3')))

    monkeypatch.setattr(pipeline, 'extract_audio', extract)
    task = video_tasks.enqueue_video_task(db, first.user, first, 'process')
    claimed = video_tasks.claim_next_task(db, 'quota-test-worker')
    assert claimed.id == task.id
    video_tasks.execute_claimed_task(db, task.id, 'quota-test-worker')
    db.refresh(task)
    assert task.status == 'failed' and task.stage == 'transcription'
    assert '存储总量' in task.error
    assert first.status == 'failed'
    assert not list(artifact_directory('audio').iterdir())


def test_video_deleted_during_generation_cannot_publish_orphan_files(storage_db):
    db, first, _, _ = storage_db

    def produce():
        write('note', first, b'do not publish after deletion', '.md')
        db.delete(first)
        db.commit()

    with pytest.raises(ApiError) as exc:
        generate_artifacts(db, first, 'note', produce)
    assert exc.value.status_code == 404
    assert list(artifact_directory('note').iterdir()) == []
