"""Real local HTTP/yt-dlp/DASH/ffmpeg; no provider calls or user data."""

import ctypes
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from threading import Thread, Event
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.base import Base
from app.models import User, Video, VideoTask
from app.services import video_tasks
from app.services.storage_quota import generate_artifacts, staging_directory
from app.services.temporary_storage import STAGE_LIMIT_MESSAGE, FREE_SPACE_MESSAGE
from app.services.video_processing import managed_downloader
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import DownloadedVideo


pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Actual Linux process-group faults')

WORKER = '''
import json, os, sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.errors import ApiError
from app.services import video_tasks
from app.services.video_processing import pipeline, managed_downloader
from app.services.video_processing.types import TranscriptResult
from app.services.temporary_storage import FREE_SPACE_MESSAGE
root, database, fault = sys.argv[1:]
root = Path(root)
for kind in ('video', 'audio', 'transcript', 'note'):
    setattr(settings, f'{kind}_storage_dir', str(root / kind))
settings.asr_provider = 'openai'
settings.video_cookie_file = settings.video_http_proxy = ''
settings.min_media_free_space_mb = 0
settings.max_media_stage_mb = 1 if fault == 'quota' else 16
settings.video_download_timeout_seconds = 8 if fault == 'timeout' else 40
pipeline.resolve_asr_key = lambda user: None
pipeline.transcribe_audio = lambda **kw: TranscriptResult(kw['video_id'], 'Simulated ASR after real DASH merge', 'test')
check = managed_downloader.check_stage_space
def check_space(directory):
    marker = root / 'merge.json'
    if marker.is_file():
        try:
            output = Path(json.loads(marker.read_text())['output'])
            writing = output.is_file() and output.stat().st_size > 0
        except (ValueError, FileNotFoundError):
            writing = False
        if writing and (root / 'fault-armed').exists():
            if fault == 'space':
                raise ApiError(FREE_SPACE_MESSAGE, 507)
            if fault == 'probe':
                raise OSError('synthetic-private-probe-error')
            if fault == 'quota':
                with (directory / 'synthetic-padding').open('wb') as padding:
                    padding.truncate(2 * 1024 * 1024)
    check(directory)
managed_downloader.check_stage_space = check_space
engine = create_engine(database)
with Session(engine) as db:
    task = video_tasks.claim_next_task(db, 'isolated-download-worker')
    video_tasks.execute_claimed_task(db, task.id, 'isolated-download-worker')
engine.dispose()
'''


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail('Timed out waiting for synthetic managed-download state')


def stopped(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] == 'Z'
    except FileNotFoundError:
        return True


@pytest.fixture
def orphans():
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    pids = []
    try:
        yield pids
    finally:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


@pytest.fixture
def download_job(tmp_path, monkeypatch):
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        pytest.skip('Real ffmpeg is required')
    monkeypatch.setattr(settings, 'video_cookie_file', '')
    monkeypatch.setattr(settings, 'video_http_proxy', '')
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    assets = tmp_path / 'assets'
    assets.mkdir()
    subprocess.run([
        ffmpeg, '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=10',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '12',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-f', 'dash', str(assets / 'manifest.mpd'),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    subprocess.run([
        ffmpeg, '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=s=64x64:r=10',
        '-t', '0.3', '-c:v', 'mpeg4', str(assets / 'sample.mp4'),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(assets)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    database = f'sqlite+pysqlite:///{tmp_path / "queue.sqlite"}'
    engine = create_engine(database)
    Base.metadata.create_all(engine)
    root = Path(settings.video_storage_dir)
    root.mkdir()
    with Session(engine) as db:
        user = User(email='synthetic-download@example.com', password_hash='test')
        video = Video(user=user, url=f'http://127.0.0.1:{server.server_port}/manifest.mpd', tags=[])
        db.add(video)
        db.commit()
        task_id = video_tasks.enqueue_video_task(db, user, video, 'process').id
        original = root / f'{video.id}.mp4'
        original.write_bytes(b'previous-published-media')
    keep = root / '.staging-unrelated'
    keep.mkdir()
    (keep / 'keep').write_bytes(b'keep')
    binary = tmp_path / 'bin'
    binary.mkdir()
    (binary / 'ffmpeg').write_text(
        f'#!{sys.executable}\nimport json, os, pathlib, sys\n'
        'args = sys.argv[1:]\n'
        'if args.count("-i") >= 2:\n'
        f'    pathlib.Path({str(tmp_path / "merge.json")!r}).write_text(json.dumps({{"ffmpeg":os.getpid(),"runner":os.getppid(),"output":args[-1].removeprefix("file:")}}))\n'
        '    args = ["-re", *args[:-1], "-flush_packets", "1", args[-1]]\n'
        f'os.execv({ffmpeg!r}, [{ffmpeg!r}, *args])\n'
    )
    (binary / 'ffmpeg').chmod(0o700)
    try:
        yield tmp_path, database, engine, task_id, original, keep, server.server_port
    finally:
        engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def spawn(job, *, paced=True, fault=''):
    root, database, *_ = job
    env = os.environ.copy()
    if paced:
        env['PATH'] = f'{root / "bin"}:{env["PATH"]}'
    return subprocess.Popen([sys.executable, '-c', WORKER, str(root), database, fault],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def merging(job, orphans):
    marker = job[0] / 'merge.json'
    wait_until(lambda: marker.is_file() and marker.stat().st_size > 0)
    info = json.loads(marker.read_text())
    orphans.extend([info['runner'], info['ffmpeg']])
    assert os.getpgid(info['ffmpeg']) == info['runner']
    output = Path(info['output'])
    wait_until(lambda: output.is_file() and output.stat().st_size > 0)
    return info, output


def assert_retry(job):
    with Session(job[2]) as db:
        first = db.get(VideoTask, job[3])
        if first.status == 'failed':
            task_id = video_tasks.enqueue_video_task(db, first.video.user, first.video, 'process').id
        else:
            first.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
            assert video_tasks.recover_expired_tasks(db) == 1
            task_id = first.id
    retry = spawn(job, paced=False)
    try:
        assert retry.wait(timeout=30) == 0
    finally:
        if retry.poll() is None:
            retry.kill()
            retry.wait()
    with Session(job[2]) as db:
        task = db.get(VideoTask, task_id)
        assert task.status == 'succeeded', task.error
        assert task.video.transcript.content == 'Simulated ASR after real DASH merge'
        assert Path(task.video.media_path).is_file()
    assert (job[5] / 'keep').read_bytes() == b'keep'


@pytest.mark.parametrize('stop_signal', [signal.SIGKILL, signal.SIGTERM], ids=['kill', 'terminate'])
def test_worker_death_stops_real_dash_merge_and_retains_unpublished_files(download_job, orphans, stop_signal):
    worker = spawn(download_job)
    try:
        info, output = merging(download_job, orphans)
        worker.send_signal(stop_signal)
        worker.wait(timeout=10)
        wait_until(lambda: stopped(info['runner']) and stopped(info['ffmpeg']))
        assert output.is_file()  # Forced death cannot clean the interrupted staging directory.
        assert download_job[4].read_bytes() == b'previous-published-media'
        with Session(download_job[2]) as db:
            task = db.get(VideoTask, download_job[3])
            assert task.status == 'running'
            assert task.video.transcript is None
        size = output.stat().st_size
        assert_retry(download_job)
        assert output.stat().st_size == size
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


@pytest.mark.parametrize('fault', ['space', 'probe', 'quota', 'timeout'])
def test_merge_supervision_stops_group_cleans_own_staging_and_allows_retry(download_job, orphans, fault):
    worker = spawn(download_job, fault=fault)
    try:
        info, _ = merging(download_job, orphans)
        (download_job[0] / 'fault-armed').touch()
        assert worker.wait(timeout=20) == 0
        wait_until(lambda: stopped(info['runner']) and stopped(info['ffmpeg']))
        assert download_job[4].read_bytes() == b'previous-published-media'
        assert set(download_job[4].parent.glob('.staging-*')) == {download_job[5]}
        with Session(download_job[2]) as db:
            task = db.get(VideoTask, download_job[3])
            assert task.status == 'failed'
            assert task.video.transcript is None
            expected = {'space': FREE_SPACE_MESSAGE, 'quota': STAGE_LIMIT_MESSAGE,
                        'timeout': '视频下载超时，请稍后重试'}
            if fault in expected:
                assert task.error == expected[fault]
            assert 'synthetic-private-probe-error' not in task.error
        assert_retry(download_job)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


def test_successful_download_publishes_a_relative_staging_result(download_job, monkeypatch):
    relative = os.path.relpath(download_job[0] / 'relative-video', Path.cwd())
    monkeypatch.setattr(settings, 'video_storage_dir', relative)
    with Session(download_job[2]) as db:
        video = db.get(VideoTask, download_job[3]).video
        result = generate_artifacts(db, video, 'video', lambda: managed_downloader.download_video(
            f'http://127.0.0.1:{download_job[6]}/sample.mp4', video.id,
        ))
    assert Path(result.file_path).parent == Path(relative)
    assert Path(result.file_path).is_file()
    assert not list(Path(relative).glob('.staging-*'))


def test_blocked_http_times_out_without_a_progress_callback(monkeypatch):
    entered, release = Event(), Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            entered.set()
            release.wait(15)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, 'video_download_timeout_seconds', 4)
    try:
        with staging_directory('video'):
            with pytest.raises(VideoProcessingError, match='视频下载超时'):
                managed_downloader.download_video(f'http://127.0.0.1:{server.server_port}/blocked.mp4', 'synthetic')
        assert entered.is_set()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_child_failure_and_oversized_metadata_use_fixed_errors(download_job):
    with staging_directory('video'):
        with pytest.raises(VideoProcessingError) as error:
            managed_downloader.download_video(f'http://127.0.0.1:{download_job[6]}/missing.mp4?private=synthetic-token', 'synthetic')
    assert str(error.value) == '视频下载失败'
    with pytest.raises(VideoProcessingError, match='视频下载失败'):
        managed_downloader.encode_result(DownloadedVideo('synthetic', 'test', 'test', description='x' * managed_downloader.MAX_RESULT_BYTES))


def test_missing_required_process_apis_fails_closed(monkeypatch):
    monkeypatch.delattr(managed_downloader.os, 'WNOWAIT')
    with pytest.raises(VideoProcessingError, match='进程组保护'):
        managed_downloader.download_video('https://example.com/unused', 'synthetic')


@pytest.mark.parametrize('frame', [b'synthetic-private-invalid\n', b''])
def test_broken_child_protocol_is_sanitized_and_reaped(monkeypatch, frame):
    original_popen = subprocess.Popen
    processes = []
    def broken(command, **kwargs):
        assert 'synthetic-secret' not in repr(command)
        assert 'private-query' not in repr(command)
        code = ('import os,sys,time; '
                f'os.write(int(sys.argv[1]), {frame!r}); '
                + ('time.sleep(30)' if frame else 'sys.exit(2)'))
        process = original_popen([sys.executable, '-c', code, command[-1]], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(managed_downloader.subprocess, 'Popen', broken)
    monkeypatch.setattr(settings, 'video_http_proxy', 'http://synthetic-user:synthetic-secret@127.0.0.1:9')
    with staging_directory('video'):
        with pytest.raises(VideoProcessingError) as error:
            managed_downloader.download_video('https://example.com/private-query', 'synthetic')
    assert str(error.value) == '视频下载失败'
    assert processes[0].returncode == (-signal.SIGKILL if frame else 2)
