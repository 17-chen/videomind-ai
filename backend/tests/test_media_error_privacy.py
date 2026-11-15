"""Synthetic secrets exercise media errors; no provider or external URL is called."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import sys

import httpx
from openai import AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError
import pytest

from app.core.config import settings
from app.core.i18n import t
from app.services.video_processing import audio, downloader, transcriber
from app.services.video_processing.errors import VideoProcessingError


PRIVATE = 'synthetic-secret https://proxy-user:proxy-password@example.com/media?signature=private-signature /private/cookie-file'


@pytest.mark.parametrize('stage', ['init', 'enter', 'extract', 'exit'])
def test_download_library_errors_never_become_public_messages(monkeypatch, stage, capsys):
    class FakeYDL:
        def fail(self, where):
            if stage == where:
                raise RuntimeError(PRIVATE)
        def __init__(self, options):
            self.fail('init')
        def __enter__(self):
            self.fail('enter')
            return self
        def __exit__(self, *args):
            self.fail('exit')
        def extract_info(self, *args, **kwargs):
            self.fail('extract')
            return {}
        def prepare_filename(self, info):
            return '/unused.mp4'

    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=FakeYDL))
    with pytest.raises(VideoProcessingError) as error:
        downloader.download_video('https://example.com/test?signature=private-signature', 'synthetic')
    assert str(error.value) == t('video_download_failed')
    assert PRIVATE not in capsys.readouterr().out


def test_missing_cookie_path_is_not_returned(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'video_cookie_file', str(tmp_path / 'private-cookie-file'))
    with pytest.raises(VideoProcessingError) as error:
        downloader.download_video('https://example.com/test', 'synthetic')
    assert str(error.value) == t('video_cookie_unavailable')
    assert str(tmp_path) not in str(error.value)


def test_bilibili_412_guidance_is_fixed_and_does_not_echo_library_error(monkeypatch):
    class FakeYDL:
        def __init__(self, options):
            raise RuntimeError(f'HTTP Error 412 {PRIVATE}')
    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=FakeYDL))
    with pytest.raises(VideoProcessingError) as error:
        downloader.download_video('https://www.bilibili.com/video/synthetic', 'synthetic')
    assert 'HTTP 412' in str(error.value) and 'Cookie' in str(error.value)
    assert 'synthetic-secret' not in str(error.value)
    assert 'private-signature' not in str(error.value)


@pytest.mark.parametrize('kind,message_key', [
    ('auth', 'whisper_auth_failed'), ('rate', 'whisper_rate_limited'),
    ('timeout', 'whisper_timeout'), ('connection', 'whisper_connection_failed'),
    ('status', 'whisper_failed'), ('unexpected', 'whisper_failed'), ('init', 'whisper_failed'),
])
def test_cloud_asr_maps_typed_errors_without_response_body_or_key(monkeypatch, tmp_path, kind, message_key):
    monkeypatch.setattr(settings, 'asr_provider', 'openai')
    path = tmp_path / 'audio.mp3'
    path.write_bytes(b'synthetic audio')
    request = httpx.Request('POST', 'https://example.com/?signature=private-signature')
    response = httpx.Response(401 if kind == 'auth' else 429 if kind == 'rate' else 500, request=request)
    errors = {
        'auth': AuthenticationError(PRIVATE, response=response, body={'private': PRIVATE}),
        'rate': RateLimitError(PRIVATE, response=response, body={'private': PRIVATE}),
        'timeout': APITimeoutError(request=request),
        'connection': APIConnectionError(message=PRIVATE, request=request),
        'status': APIStatusError(PRIVATE, response=response, body={'private': PRIVATE}),
        'unexpected': RuntimeError(PRIVATE),
        'init': RuntimeError(PRIVATE),
    }
    calls = []
    def create(**kwargs):
        calls.append(kwargs['model'])
        raise errors[kind]
    def client(**kwargs):
        assert kwargs == {'api_key': 'synthetic-personal-key'}
        if kind == 'init':
            raise errors[kind]
        return SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    monkeypatch.setattr(transcriber, 'OpenAI', client)
    with pytest.raises(VideoProcessingError) as error:
        transcriber.transcribe_audio(str(path), 'synthetic', api_key='synthetic-personal-key')
    assert str(error.value) == t(message_key)
    assert len(calls) == (0 if kind == 'init' else 1)  # No application-level retry/fallback.
    assert not Path(settings.transcript_storage_dir).exists()


@pytest.mark.parametrize('provider', ['openai', 'faster_whisper', 'audio'])
def test_missing_input_paths_are_not_exposed(monkeypatch, tmp_path, provider):
    path = str(tmp_path / 'private-user-directory' / 'missing-media')
    if provider == 'audio':
        monkeypatch.setattr(audio.shutil, 'which', lambda _: '/synthetic/ffmpeg')
        def operation():
            return audio.extract_audio(path, 'synthetic')
        key = 'video_file_missing'
    else:
        monkeypatch.setattr(settings, 'asr_provider', provider)
        monkeypatch.setattr(transcriber, 'ensure_local_asr_available', lambda: None)
        def operation():
            return transcriber.transcribe_audio(path, 'synthetic', api_key='synthetic-personal-key')
        key = 'audio_file_missing'
    with pytest.raises(VideoProcessingError) as error:
        operation()
    assert str(error.value) == t(key)


def test_real_local_http_download_failure_is_sanitized(capsys):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(PRIVATE.encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(VideoProcessingError) as error:
            downloader.download_video(f'http://127.0.0.1:{server.server_port}/private.mp4?signature=private-signature', 'synthetic')
        assert str(error.value) == t('video_download_failed')
        captured = capsys.readouterr()
        assert 'private-signature' not in captured.out + captured.err
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
