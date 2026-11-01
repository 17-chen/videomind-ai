"""Real Linux media-process faults; SQLite queue and simulated ASR are explicit."""

import ctypes
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import wave

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.i18n import t
from app.database.base import Base
from app.models import User, Video, VideoTask
from app.services import video_tasks
from app.services.video_processing import limited_exec


pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux parent-death supervision')

# Run the actual claim/execute functions in an independent process. Only the ASR
# response and its key resolver are simulated; extraction runs the real ffmpeg.
WORKER = '''
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services import video_tasks
from app.services.video_processing import audio, pipeline
from app.services.video_processing.types import TranscriptResult
root, database, wrapper, timeout = sys.argv[1:]
for kind in ('video', 'audio', 'transcript', 'note'):
    setattr(settings, f'{kind}_storage_dir', str(Path(root) / kind))
settings.min_media_free_space_mb = 0
settings.audio_extraction_timeout_seconds = float(timeout)
pipeline.resolve_asr_key = lambda user: None
pipeline.transcribe_audio = lambda **kw: TranscriptResult(kw['video_id'], 'Simulated ASR after real extraction', 'test')
if wrapper:
    audio.shutil.which = lambda name: wrapper
engine = create_engine(database)
with Session(engine) as db:
    task = video_tasks.claim_next_task(db, 'isolated-media-worker')
    video_tasks.execute_claimed_task(db, task.id, 'isolated-media-worker')
engine.dispose()
'''


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail('Timed out waiting for isolated media-process state')


@pytest.fixture
def media_job(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        pytest.skip('Real ffmpeg is required')
    source = tmp_path / 'synthetic.wav'
    with wave.open(str(source), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\0\0' * (16000 * 10))
    database = f'sqlite+pysqlite:///{tmp_path / "queue.sqlite"}'
    engine = create_engine(database)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email='synthetic-fault@example.com', password_hash='test')
        video = Video(user=user, source='upload', url='https://example.com/synthetic', media_path=str(source), tags=[])
        db.add(video)
        db.commit()
        task_id = video_tasks.enqueue_video_task(db, user, video, 'process').id
        audio_root = Path(settings.audio_storage_dir)
        audio_root.mkdir()
        original = audio_root / f'{video.id}.mp3'
        original.write_bytes(b'previous-published-audio')
    # Pace a real source to keep extraction in progress deterministically. This
    # wrapper exists only in the test; production ffmpeg has no -re option.
    pid_file = tmp_path / 'media.pid'
    wrapper = tmp_path / 'paced-ffmpeg'
    wrapper.write_text(
        f'#!{sys.executable}\nimport os, pathlib, sys\n'
        f'pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n'
        f'os.execv({ffmpeg!r}, [{ffmpeg!r}, "-re", *sys.argv[1:-1], "-flush_packets", "1", sys.argv[-1]])\n'
    )
    wrapper.chmod(0o700)
    try:
        yield tmp_path, database, engine, task_id, original, wrapper, pid_file
    finally:
        engine.dispose()


@pytest.fixture
def reap_orphan():
    # Reap this test's orphan explicitly even when container PID 1 is not an init.
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    children = []
    try:
        yield children
    finally:
        for pid in children:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def spawn_worker(job, *, paced=True, timeout=30):
    root, database, _, _, _, wrapper, _ = job
    return subprocess.Popen(
        [sys.executable, '-c', WORKER, str(root), database, str(wrapper) if paced else '', str(timeout)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def is_stopped(pid):
    try:
        # Zombie is no longer executing or writing; the test reaps it below.
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] == 'Z'
    except FileNotFoundError:
        return True


@pytest.mark.parametrize('stop_signal', [signal.SIGKILL, signal.SIGTERM], ids=['kill', 'terminate'])
def test_worker_death_stops_real_ffmpeg_and_lease_recovery_retries_safely(media_job, reap_orphan, stop_signal):
    root, _, engine, task_id, original, _, pid_file = media_job
    worker = spawn_worker(media_job)
    media_pid = None
    try:
        wait_until(lambda: pid_file.exists() and pid_file.stat().st_size > 0)
        media_pid = int(pid_file.read_text())
        reap_orphan.append(media_pid)
        wait_until(lambda: Path(f'/proc/{media_pid}/exe').resolve().name == 'ffmpeg')
        staged = None

        def has_output():
            nonlocal staged
            files = list((root / 'audio').glob('.staging-*/*.mp3'))
            if files and files[0].stat().st_size > 0:
                staged = files[0]
                return True
            return False

        wait_until(has_output)
        assert worker.poll() is None
        worker.send_signal(stop_signal)
        worker.wait(timeout=10)
        wait_until(lambda: is_stopped(media_pid))
        size = staged.stat().st_size
        assert original.read_bytes() == b'previous-published-audio'
        assert staged.exists()  # Forced death cannot run TemporaryDirectory cleanup.
        with Session(engine) as db:
            task = db.get(VideoTask, task_id)
            assert task.status == 'running'
            assert task.stage == 'transcription'
            assert task.video.audio_path is None  # Interrupted audio was never published.
            # Simulate lease passage, rather than sleeping through the 90s lease.
            task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
            assert video_tasks.recover_expired_tasks(db) == 1
        retry = spawn_worker(media_job, paced=False)
        try:
            assert retry.wait(timeout=30) == 0
        finally:
            if retry.poll() is None:
                retry.kill()
                retry.wait(timeout=10)
        with Session(engine) as db:
            task = db.get(VideoTask, task_id)
            assert task.status == 'succeeded'
            assert task.attempts == 2
            assert task.video.transcript.content == 'Simulated ASR after real extraction'
            assert task.video.audio_path == str(original)
        assert original.read_bytes() != b'previous-published-audio'
        assert staged.stat().st_size == size  # Old stage stays inert; no automatic deletion.
        assert len(list((root / 'audio').glob('.staging-*'))) == 1
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)


def test_audio_timeout_reaps_process_and_cleans_only_its_stage(media_job):
    root, _, engine, task_id, original, _, pid_file = media_job
    worker = spawn_worker(media_job, timeout=1)
    try:
        assert worker.wait(timeout=30) == 0
        assert pid_file.exists()
        assert not Path(f'/proc/{int(pid_file.read_text())}').exists()
        with Session(engine) as db:
            task = db.get(VideoTask, task_id)
            assert task.status == 'failed'
            assert task.error == t('audio_extraction_timeout')
            assert task.video.processing_error == t('audio_extraction_timeout')
            assert task.video.audio_path is None
            assert task.video.transcript is None
        assert original.read_bytes() == b'previous-published-audio'
        assert not list((root / 'audio').glob('.staging-*'))
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)


def test_launcher_rejects_dead_parent_before_executing_command(tmp_path):
    marker = tmp_path / 'must-not-exist'
    result = subprocess.run([
        sys.executable, '-m', 'app.services.video_processing.limited_exec', '1048576', str(os.getpid() + 1),
        sys.executable, '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marker),
    ], capture_output=True, timeout=10)
    assert result.returncode != 0
    assert not marker.exists()


def test_supervision_setup_failure_does_not_allow_execution(monkeypatch):
    class Denied:
        def prctl(self, *args):
            return -1

    monkeypatch.setattr(limited_exec.ctypes, 'CDLL', lambda *args, **kwargs: Denied())
    with pytest.raises(OSError, match='Cannot supervise media process'):
        limited_exec.bind_to_parent(os.getpid())
