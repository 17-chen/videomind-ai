from io import BytesIO
from pathlib import Path
import resource
import shutil
from types import SimpleNamespace
import subprocess
import sys
import wave

from fastapi import UploadFile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.models import User, Video
from app.services import temporary_storage, video_upload
from app.services.storage_quota import artifact_directory, generate_artifacts
from app.services.video_processing.audio import extract_audio


@pytest.fixture
def stage_db(monkeypatch):
    monkeypatch.setattr(settings, 'max_media_stage_mb', 1)
    engine = create_engine('sqlite+pysqlite://')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(email='synthetic-stage@example.com', password_hash='test')
            video = Video(user=user, url='https://example.com/synthetic', tags=[])
            db.add(video)
            db.commit()
            yield db, video
    finally:
        engine.dispose()


def test_low_space_rejects_before_producer_and_never_removes_existing_files(stage_db, monkeypatch):
    db, video = stage_db
    root = Path(settings.video_storage_dir)
    root.mkdir()
    original = root / f'{video.id}.mp4'
    original.write_bytes(b'original')
    monkeypatch.setattr(settings, 'min_media_free_space_mb', 1)
    monkeypatch.setattr(temporary_storage.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    with pytest.raises(ApiError) as exc:
        generate_artifacts(db, video, 'video', lambda: pytest.fail('Producer must not run on low disk'))
    assert exc.value.status_code == 507
    assert original.read_bytes() == b'original'
    assert list(root.iterdir()) == [original]


def test_oversized_stage_is_not_published_and_retry_can_write_smaller_output(stage_db):
    db, video = stage_db
    root = Path(settings.video_storage_dir)
    root.mkdir()
    original = root / f'{video.id}.mp4'
    original.write_bytes(b'original')

    def produce(size):
        (artifact_directory('video') / f'{video.id}.mp4').write_bytes(b'x' * size)

    with pytest.raises(ApiError) as exc:
        generate_artifacts(db, video, 'video', lambda: produce(1024 * 1024 + 1))
    assert exc.value.status_code == 413
    assert original.read_bytes() == b'original'
    assert not list(root.glob('.staging-*'))
    generate_artifacts(db, video, 'video', lambda: produce(3))
    assert original.read_bytes() == b'xxx'


def test_text_uses_utf8_bytes_and_rejects_before_overwriting(stage_db, tmp_path):
    output = tmp_path / 'note.md'
    output.write_bytes(b'original')
    with pytest.raises(ApiError) as exc:
        temporary_storage.write_bounded_text(output, '中' * (1024 * 1024 // 3 + 1))
    assert exc.value.status_code == 413
    assert output.read_bytes() == b'original'


def test_upload_policy_and_stream_respect_stage_budget(stage_db, monkeypatch):
    db, video = stage_db
    monkeypatch.setattr(settings, 'max_upload_mb', 2)
    monkeypatch.setattr(video_upload, '_probe_video', lambda _: pytest.fail('Oversized upload must not reach probe'))
    assert video_upload.upload_policy()['max_bytes'] == 1024 * 1024
    with pytest.raises(ApiError) as exc:
        video_upload.save_uploaded_video(db, video.user, UploadFile(BytesIO(b'x' * (1024 * 1024 + 1)), filename='sample.mp4'))
    assert exc.value.status_code == 413
    assert '临时文件' in exc.value.message
    assert not list(Path(settings.video_storage_dir).iterdir())
    assert db.query(Video).count() == 1


def test_upload_checks_free_space_before_each_stream_write(stage_db, monkeypatch):
    db, video = stage_db
    monkeypatch.setattr(settings, 'min_media_free_space_mb', 1)
    free = iter([3 * 1024 * 1024, 3 * 1024 * 1024, 1024 * 1024])
    monkeypatch.setattr(temporary_storage.shutil, 'disk_usage', lambda _: SimpleNamespace(free=next(free)))
    monkeypatch.setattr(settings, 'max_media_stage_mb', 2)
    monkeypatch.setattr(settings, 'max_upload_mb', 2)
    with pytest.raises(ApiError) as exc:
        video_upload.save_uploaded_video(db, video.user, UploadFile(BytesIO(b'x' * (1024 * 1024 + 1)), filename='sample.mp4'))
    assert exc.value.status_code == 507
    assert not list(Path(settings.video_storage_dir).iterdir())


def test_file_limit_is_enforced_in_child_without_changing_parent(tmp_path):
    limit = 1024 * 1024
    before = resource.getrlimit(resource.RLIMIT_FSIZE)
    before_core = resource.getrlimit(resource.RLIMIT_CORE)
    output = tmp_path / 'bounded.bin'
    result = subprocess.run([
        sys.executable, '-m', 'app.services.video_processing.limited_exec', str(limit),
        sys.executable, '-c', 'import pathlib,sys,resource; assert resource.getrlimit(resource.RLIMIT_CORE) == (0,0); pathlib.Path(sys.argv[1]).write_bytes(b"x" * (4 * 1024 * 1024))', str(output),
    ], capture_output=True, timeout=10)
    assert result.returncode != 0
    assert output.stat().st_size <= limit
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == before
    assert resource.getrlimit(resource.RLIMIT_CORE) == before_core


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='Real ffmpeg is required for the media tool check')
def test_real_ffmpeg_succeeds_normally_but_cannot_publish_truncated_output(stage_db, tmp_path):
    db, video = stage_db
    before = resource.getrlimit(resource.RLIMIT_FSIZE)
    source = tmp_path / 'synthetic.wav'

    def synthesize(seconds):
        with wave.open(str(source), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b'\x00\x00' * (16000 * seconds))

    synthesize(1)
    audio = generate_artifacts(db, video, 'audio', lambda: extract_audio(str(source), video.id))
    original = Path(audio.file_path).read_bytes()
    assert 0 < len(original) < 1024 * 1024
    synthesize(180)
    with pytest.raises(ApiError) as exc:
        generate_artifacts(db, video, 'audio', lambda: extract_audio(str(source), video.id))
    assert exc.value.status_code == 413
    assert Path(audio.file_path).read_bytes() == original
    assert not list(Path(settings.audio_storage_dir).glob('.staging-*'))
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == before


def test_known_low_disk_rejects_analysis_before_provider_call(stage_db, monkeypatch):
    from app.models import Transcript
    from app.services import analysis

    db, video = stage_db
    video.transcript = Transcript(content='synthetic source')
    db.commit()
    monkeypatch.setattr(settings, 'min_media_free_space_mb', 1)
    monkeypatch.setattr(temporary_storage.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    monkeypatch.setattr(analysis, 'analyze_video_transcript', lambda **_: pytest.fail('Known low disk must reject before billing'))
    with pytest.raises(ApiError) as exc:
        analysis.analyze_video(db, video)
    assert exc.value.status_code == 507
    assert video.summary is None


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='Real ffmpeg is required to generate the HTTP media fixture')
@pytest.mark.parametrize('known_length', [True, False], ids=['known-length', 'streamed-length'])
def test_real_http_download_limit_preserves_existing_video(stage_db, monkeypatch, tmp_path, known_length):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import struct
    from threading import Thread

    from app.services.video_processing.downloader import download_video

    db, video = stage_db
    monkeypatch.setattr(settings, 'video_cookie_file', '')
    monkeypatch.setattr(settings, 'video_http_proxy', '')
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    sample = tmp_path / 'synthetic.mp4'
    subprocess.run([
        shutil.which('ffmpeg'), '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=10',
        '-t', '1', '-c:v', 'mpeg4', str(sample),
    ], check=True, capture_output=True, timeout=10)
    payload = sample.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            if known_length:
                self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/synthetic.mp4'
        result = generate_artifacts(db, video, 'video', lambda: download_video(url, video.id))
        original = Path(result.file_path).read_bytes()
        assert original == payload
        # A valid MP4 free atom adds padding without inventing a real-world video claim.
        padding_size = 2 * 1024 * 1024
        payload += struct.pack('>I4s', padding_size + 8, b'free') + b'\0' * padding_size
        with pytest.raises(ApiError) as exc:
            generate_artifacts(db, video, 'video', lambda: download_video(url, video.id))
        assert exc.value.status_code == 413
        assert Path(result.file_path).read_bytes() == original
        assert not list(Path(settings.video_storage_dir).glob('.staging-*'))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
